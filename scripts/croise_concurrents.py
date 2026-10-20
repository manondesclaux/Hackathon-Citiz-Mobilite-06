"""Carte Citiz + concurrents sur la grille Filosofi 2021 (métropole) et indicateurs de couverture.

Concurrents (données ouvertes) : Clem', Rémi+ (Centre-Val de Loire), Optymo (Belfort),
Communauto (Grand Paris Seine Ouest) en stations ; Leo&Go (Lyon) en free-floating (positions des véhicules) ;
Getaround (voitures de particuliers, toute la France, collecte_getaround.py) en positions de véhicules.

Usage :
    python scripts/croise_concurrents.py DOSSIER_CITIZ DOSSIER_CONCURRENTS carreaux_200m_met.csv [rayon_m=500] [sortie.html]
"""
import json
import sys
from pathlib import Path

import folium
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from analyse_citiz import charger  # noqa: E402

TUILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
COULEURS = {"Citiz": "#1d4ed8", "Clem'": "#16a34a", "Rémi+": "#9333ea", "Optymo": "#ea580c",
            "Communauto": "#db2777", "Leo&Go": "#0891b2", "Getaround": "#ca8a04"}
GBFS_STATIONS = {"clem": "Clem'", "remi": "Rémi+", "optymo": "Optymo"}


def texte(n) -> str:
    return n[0]["text"] if isinstance(n, list) else str(n)


def stations_gbfs(dossier: Path, cle: str, operateur: str) -> pd.DataFrame:
    info = json.load(open(dossier / cle / "station_information.json"))["data"]["stations"]
    stat = {s["station_id"]: s for s in json.load(open(dossier / cle / "station_status.json"))["data"]["stations"]}
    lignes = []
    for s in info:
        r = stat.get(s["station_id"], {})
        lignes.append(dict(operateur=operateur, nom=texte(s["name"]), lat=s["lat"], lon=s["lon"],
                           dispo=r.get("num_vehicles_available", r.get("num_bikes_available"))))
    return pd.DataFrame(lignes)


def charger_concurrents(dossier: Path):
    parts = [stations_gbfs(dossier, k, o) for k, o in GBFS_STATIONS.items()]
    g = json.load(open(dossier / "gpso.geojson"))["features"]
    parts.append(pd.DataFrame([dict(operateur="Communauto", nom=f["properties"]["nom_station"],
                                    lat=f["geometry"]["coordinates"][1], lon=f["geometry"]["coordinates"][0],
                                    dispo=None) for f in g]))
    st = pd.concat(parts, ignore_index=True)
    v = json.load(open(dossier / "leogo" / "free_bike_status.json"))["data"]["bikes"]
    leogo = pd.DataFrame([dict(operateur="Leo&Go", nom="Véhicule free-floating", lat=b["lat"], lon=b["lon"],
                               dispo=int(not b.get("is_reserved") and not b.get("is_disabled"))) for b in v])
    ga = json.load(open(dossier / "getaround" / "vehicles.json"))
    getaround = pd.DataFrame([dict(operateur="Getaround", nom="Voiture de particulier", lat=v["lat"], lon=v["lon"],
                                   dispo=int(not v.get("is_reserved") and not v.get("is_disabled"))) for v in ga])
    return st, leogo, getaround


def vers_3035(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df.lat.between(41, 52) & df.lon.between(-6, 10)].copy()
    df["x"], df["y"] = Transformer.from_crs(4326, 3035, always_xy=True).transform(df.lon.values, df.lat.values)
    return df.reset_index(drop=True)


def couvert(c: pd.DataFrame, pts: pd.DataFrame, rayon: float):
    d, _ = cKDTree(pts[["x", "y"]].to_numpy()).query(c[["x", "y"]].to_numpy())
    return d <= rayon


def main(citiz: Path, conc: Path, csv: str, rayon: float, sortie: str):
    ci, _, _ = charger(citiz)
    ci = vers_3035(ci.drop_duplicates(["lat", "lon"]).assign(operateur="Citiz")[["operateur", "nom", "lat", "lon", "dispo"]])
    co, leogo, ga = charger_concurrents(conc)
    co, leogo, ga = vers_3035(co), vers_3035(leogo), vers_3035(ga)
    print("Stations :", ci.shape[0], "Citiz |", co.groupby("operateur").size().to_dict(),
          "| véhicules Leo&Go :", len(leogo), "| Getaround :", len(ga))

    c = pd.read_csv(csv, usecols=["idcar_200m", "ind"])
    ext = c.idcar_200m.str.extract(r"RES200mN(\d+)E(\d+)").astype(float)
    c["y"], c["x"] = ext[0] + 100, ext[1] + 100
    c["citiz"] = couvert(c, ci, rayon)
    for op, g in co.groupby("operateur"):
        c[op] = couvert(c, g, rayon)
    c["concurrents"] = couvert(c, co, rayon)
    c["leogo"] = couvert(c, leogo, rayon)
    c["getaround"] = couvert(c, ga, rayon)
    c["tous"] = c.citiz | c.concurrents | c.leogo | c.getaround
    tot = c.ind.sum()

    def pct(m):
        return f"{c.loc[m, 'ind'].sum():>12,.0f}  ({100 * c.loc[m, 'ind'].sum() / tot:.2f} %)"

    print(f"\nPopulation métropole : {tot:,.0f} | rayon {rayon:.0f} m")
    print("Citiz seul                    ", pct(c.citiz))
    for op in sorted(co.operateur.unique()):
        print(f"{op:<30}", pct(c[op]))
    print("Leo&Go (positions de ce relevé)", pct(c.leogo))
    print("Getaround (voitures de particuliers)", pct(c.getaround))
    conc_tous = c.concurrents | c.leogo | c.getaround
    print("Concurrents (tous, Getaround inclus)", pct(conc_tous))
    print("Citiz ET un concurrent        ", pct(c.citiz & conc_tous))
    print("Citiz SANS concurrent         ", pct(c.citiz & ~conc_tous))
    print("Concurrent SANS Citiz         ", pct(~c.citiz & conc_tous))
    print("Concurrent hors Getaround, SANS Citiz", pct(~c.citiz & (c.concurrents | c.leogo)))
    print("Citiz ou concurrent           ", pct(c.tous))

    # stations Citiz avec un concurrent à proximité
    tree = cKDTree(pd.concat([co, leogo, ga])[["x", "y"]].to_numpy())
    ci["concurrents_proches"] = [len(v) for v in tree.query_ball_point(ci[["x", "y"]].to_numpy(), r=rayon)]
    print(f"\nStations Citiz avec ≥1 concurrent à moins de {rayon:.0f} m : "
          f"{(ci.concurrents_proches > 0).sum()} / {len(ci)}")

    # carte
    m = folium.Map(location=[46.6, 2.5], zoom_start=6, tiles=None)
    folium.TileLayer(TUILES, attr="Tiles © Esri", control=False).add_to(m)
    inv = Transformer.from_crs(3035, 4326, always_xy=True)
    blanc = c[~c.tous & (c.ind >= 400)]
    lon, lat = inv.transform(blanc.x.values, blanc.y.values)
    fg = folium.FeatureGroup(name=f"Carreaux ≥400 hab. sans aucun service à {rayon:.0f} m ({len(blanc)})", show=False)
    for la, lo, p in zip(lat, lon, blanc.ind):
        folium.CircleMarker([la, lo], radius=2, color="#dc2626", weight=0, fill=True, fill_opacity=0.6,
                            tooltip=f"{p:.0f} hab.").add_to(fg)
    fg.add_to(m)
    for op, df in [("Citiz", ci)] + list(co.groupby("operateur")) + [("Leo&Go", leogo), ("Getaround", ga)]:
        vehicules = op in ("Leo&Go", "Getaround")
        fg = folium.FeatureGroup(name=f"{op} ({len(df)}{' véhicules' if vehicules else ''})", show=op != "Getaround")
        for r in df.itertuples():
            d = "" if pd.isna(r.dispo) else f" — {int(r.dispo)} dispo"
            folium.CircleMarker([r.lat, r.lon], radius=3 if vehicules else 4, color=COULEURS[op], fill=True,
                                fill_opacity=0.8, weight=0.5, tooltip=f"{op} · {r.nom}{d}").add_to(fg)
        fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(sortie)
    print("Carte écrite :", sortie)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    a = sys.argv
    main(Path(a[1]), Path(a[2]), a[3], float(a[4]) if len(a) > 4 else 500.0,
         a[5] if len(a) > 5 else "carte_citiz_concurrents.html")
