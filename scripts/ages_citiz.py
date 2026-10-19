"""Structure d'âge de la population autour des stations Citiz (Filosofi 2021, carreaux 200 m).

Tranches : 18-24, 25-64, 65-79. Indice = part dans le rayon / part nationale (100 = moyenne).

Usage :
    python scripts/ages_citiz.py DOSSIER_FLUX carreaux_200m_met.csv [rayon_m=500] [sortie.html]
"""
import sys
from pathlib import Path

import folium
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from analyse_citiz import charger  # noqa: E402

TRANCHES = {
    "18-24": ["ind_18_24"],
    "25-64": ["ind_25_39", "ind_40_54", "ind_55_64"],
    "65-79": ["ind_65_79"],
}
TUILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"


def couleur(indice: float) -> str:
    return ("#1d4ed8" if indice >= 130 else "#60a5fa" if indice >= 110 else "#d1d5db" if indice >= 90
            else "#fb923c" if indice >= 70 else "#b91c1c")


def main(flux: Path, csv: str, rayon: float, sortie: str):
    cols = ["idcar_200m", "ind"] + [c for v in TRANCHES.values() for c in v]
    c = pd.read_csv(csv, usecols=cols)
    ext = c.idcar_200m.str.extract(r"RES200mN(\d+)E(\d+)").astype(float)
    c["y"], c["x"] = ext[0] + 100, ext[1] + 100
    for t, v in TRANCHES.items():
        c[t] = c[v].sum(axis=1)
    nat = {t: c[t].sum() / c.ind.sum() for t in TRANCHES}

    st, _, _ = charger(flux)
    st = st.drop_duplicates(["lat", "lon"])
    st = st[st.lat.between(41, 52) & st.lon.between(-6, 10)].reset_index(drop=True)
    st["x"], st["y"] = Transformer.from_crs(4326, 3035, always_xy=True).transform(st.lon.values, st.lat.values)
    voisins = cKDTree(c[["x", "y"]].to_numpy()).query_ball_point(st[["x", "y"]].to_numpy(), r=rayon)

    pop = c.ind.to_numpy()
    st["pop"] = [pop[i].sum() for i in voisins]
    for t in TRANCHES:
        v = c[t].to_numpy()
        st[f"n_{t}"] = [v[i].sum() for i in voisins]
        st[f"part_{t}_%"] = (100 * st[f"n_{t}"] / st["pop"]).round(1)
        st[f"indice_{t}"] = (100 * st[f"part_{t}_%"] / (100 * nat[t])).round(0)
    st = st[st["pop"] > 0]

    print("Part nationale :", {t: f"{100*p:.1f} %" for t, p in nat.items()}, "(sur la population totale)")
    g = st.groupby("jeu")[["pop"] + [f"n_{t}" for t in TRANCHES]].sum()
    for t in TRANCHES:
        g[f"indice_{t}"] = (100 * g[f"n_{t}"] / g["pop"] / nat[t]).round(0)
    g["stations"] = st.groupby("jeu").size()
    g.index = g.index.str.replace("offre-et-disponibilite-temps-reel-du-service-citiz-en-autopartage-", "").str[:42]
    print("\nIndice par jeu (100 = moyenne nationale) :\n",
          g[["stations"] + [f"indice_{t}" for t in TRANCHES]].to_string())
    tot = st[[f"n_{t}" for t in TRANCHES] + ["pop"]].sum()
    print("\nEnsemble des stations :", {t: int(100 * tot[f"n_{t}"] / tot["pop"] / nat[t]) for t in TRANCHES})
    for t in TRANCHES:
        print(f"\nTop 5 stations, indice {t} (pop > 2000) :\n",
              st[st["pop"] > 2000].nlargest(5, f"indice_{t}")[["jeu", "nom", "pop", f"part_{t}_%", f"indice_{t}"]]
              .assign(jeu=lambda d: d.jeu.str[-20:]).to_string(index=False))
    st.drop(columns=["x", "y", "cle"], errors="ignore").to_csv("stations_citiz_ages.csv", index=False)

    m = folium.Map(location=[46.6, 2.5], zoom_start=6, tiles=None)
    folium.TileLayer(TUILES, attr="Tiles © Esri", control=False).add_to(m)
    for i, t in enumerate(TRANCHES):
        fg = folium.FeatureGroup(name=f"{t} ans : indice (100 = moyenne)", overlay=False, show=(i == 0))
        for r in st.itertuples():
            ind = st.at[r.Index, f"indice_{t}"]
            folium.CircleMarker(
                [r.lat, r.lon], radius=5, color=couleur(ind), fill=True, fill_opacity=0.85, weight=0.5,
                tooltip=f"{r.nom} — {t} ans : {st.at[r.Index, f'part_{t}_%']} % (indice {ind:.0f})",
                popup=(f"{r.nom}<br>{r.jeu}<br>pop. {r.pop:.0f} dans {rayon:.0f} m<br>" + "<br>".join(
                    f"{u} ans : {st.at[r.Index, f'part_{u}_%']} % (indice {st.at[r.Index, f'indice_{u}']:.0f})"
                    for u in TRANCHES))).add_to(fg)
        fg.add_to(m)
    legende = ("<div style='position:fixed;bottom:25px;left:25px;z-index:9999;background:white;padding:8px 10px;"
               "border-radius:4px;font:12px sans-serif;box-shadow:0 0 4px #888'><b>Indice vs moyenne nationale</b><br>"
               + "".join(f"<span style='color:{couleur(v)}'>●</span> {l}<br>" for v, l in
                         [(140, "≥ 130 : très sur-représenté"), (120, "110-130"), (100, "90-110 : moyenne"),
                          (80, "70-90"), (50, "< 70 : sous-représenté")]) + "</div>")
    m.get_root().html.add_child(folium.Element(legende))
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(sortie)
    print("\nCarte écrite :", sortie)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    a = sys.argv
    main(Path(a[1]), a[2], float(a[3]) if len(a) > 3 else 500.0, a[4] if len(a) > 4 else "carte_citiz_ages.html")
