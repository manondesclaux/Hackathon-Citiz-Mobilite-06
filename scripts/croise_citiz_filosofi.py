"""Croise les stations Citiz (GBFS) avec la grille Filosofi 2021 (carreaux 200 m, métropole).

Pour chaque station : population, ménages pauvres et seniors dans un rayon R.
Pour la métropole : part de la population située à moins de R d'une station.

Usage :
    python scripts/croise_citiz_filosofi.py DOSSIER_FLUX carreaux_200m_met.csv [rayon_m=500] [sortie.html]
"""
import sys
from pathlib import Path

import folium
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from analyse_citiz import charger  # noqa: E402

COLS = ["idcar_200m", "lcog_geo", "ind", "men", "men_pauv", "ind_65_79", "ind_80p"]


def carreaux(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=COLS, dtype={"lcog_geo": str})
    ext = df.idcar_200m.str.extract(r"RES200mN(\d+)E(\d+)").astype(float)
    df["y"], df["x"] = ext[0] + 100, ext[1] + 100  # centre du carreau, EPSG:3035
    df["dep"] = df.lcog_geo.str[:2].where(~df.lcog_geo.str.startswith("97"), df.lcog_geo.str[:3])
    df["seniors"] = df.ind_65_79 + df.ind_80p
    return df


def main(flux: Path, csv: str, rayon: float, sortie: str):
    st, _, _ = charger(flux)
    st = st.drop_duplicates(["lat", "lon"]).reset_index(drop=True)
    st = st[st.lat.between(41, 52) & st.lon.between(-6, 10)].reset_index(drop=True)  # métropole
    x, y = Transformer.from_crs(4326, 3035, always_xy=True).transform(st.lon.values, st.lat.values)
    st["x"], st["y"] = x, y

    c = carreaux(csv)
    tree = cKDTree(c[["x", "y"]].to_numpy())
    voisins = tree.query_ball_point(st[["x", "y"]].to_numpy(), r=rayon)
    for col, nom in [("ind", "pop"), ("men", "menages"), ("men_pauv", "men_pauvres"), ("seniors", "seniors")]:
        vals = c[col].to_numpy()
        st[f"{nom}_{int(rayon)}m"] = [vals[i].sum() for i in voisins]
    p = f"pop_{int(rayon)}m"
    st["taux_pauvrete"] = (100 * st[f"men_pauvres_{int(rayon)}m"] / st[f"menages_{int(rayon)}m"]).round(1)

    # couverture : carreaux à moins de `rayon` d'une station
    d, _ = cKDTree(st[["x", "y"]].to_numpy()).query(c[["x", "y"]].to_numpy())
    c["couvert"] = d <= rayon
    tot = c.ind.sum()
    print(f"Carreaux métropole : {len(c):,} | population : {tot:,.0f}")
    print(f"Population à moins de {rayon:.0f} m d'une station : {c.loc[c.couvert,'ind'].sum():,.0f} "
          f"({100*c.loc[c.couvert,'ind'].sum()/tot:.1f} %)")
    print(f"Stations : {len(st)} | pop médiane dans {rayon:.0f} m : {st[p].median():.0f} "
          f"| stations à <500 hab. : {(st[p] < 500).sum()}")

    dep = c.groupby("dep").apply(lambda g: pd.Series({
        "pop": g.ind.sum(), "pop_couverte": g.loc[g.couvert, "ind"].sum()}), include_groups=False)
    dep["couv_%"] = (100 * dep.pop_couverte / dep["pop"]).round(2)
    print("\nDépartements les mieux couverts :\n", dep[dep["pop"] > 100000].sort_values("couv_%", ascending=False).head(10).round(0).to_string())
    print("\nGrands départements (>500 000 hab.) les moins couverts :\n",
          dep[dep["pop"] > 500000].sort_values("couv_%").head(10).round(0).to_string())

    st["dispo"] = st.dispo.fillna(0)
    print("\nPar jeu :\n", st.groupby("jeu").agg(stations=("nom", "count"), pop_moy=(p, "mean")).round(0).to_string())
    tot_pop = st[p].sum()
    print(f"\nVéhicules disponibles / 1000 hab. (rayon {rayon:.0f} m, cumulé) : "
          f"{1000*st.dispo.sum()/tot_pop:.2f}")
    st.drop(columns=["x", "y", "cle"], errors="ignore").to_csv("stations_citiz_filosofi.csv", index=False)

    # carte : stations colorées par population desservie, carreaux non couverts en arrière-plan
    m = folium.Map(location=[46.6, 2.5], zoom_start=6, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", attr="Tiles © Esri")
    inv = Transformer.from_crs(3035, 4326, always_xy=True)
    gros = c[~c.couvert & (c.ind >= 400)]  # carreaux très denses sans station
    lon, lat = inv.transform(gros.x.values, gros.y.values)
    fg0 = folium.FeatureGroup(name=f"Carreaux ≥400 hab. sans station à {rayon:.0f} m ({len(gros)})", show=False)
    for la, lo, pop in zip(lat, lon, gros.ind):
        folium.CircleMarker([la, lo], radius=2, color="#dc2626", weight=0, fill=True, fill_opacity=0.6,
                            tooltip=f"{pop:.0f} hab.").add_to(fg0)
    fg0.add_to(m)
    fg = folium.FeatureGroup(name=f"Stations ({len(st)})")
    q = st[p].quantile([.25, .5, .75]).tolist()
    for r in st.itertuples():
        v = getattr(r, p)
        col = "#9ca3af" if v < q[0] else "#facc15" if v < q[1] else "#fb923c" if v < q[2] else "#15803d"
        folium.CircleMarker([r.lat, r.lon], radius=4, color=col, fill=True, fill_opacity=0.85, weight=1,
                            tooltip=f"{r.nom} — {v:.0f} hab. dans {rayon:.0f} m",
                            popup=f"{r.nom}<br>{r.jeu}<br>pop. {v:.0f} · pauvreté {r.taux_pauvrete:.1f} %"
                            ).add_to(fg)
    fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(sortie)
    print("Carte écrite :", sortie)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    a = sys.argv
    main(Path(a[1]), a[2], float(a[3]) if len(a) > 3 else 500.0, a[4] if len(a) > 4 else "carte_citiz_filosofi.html")
