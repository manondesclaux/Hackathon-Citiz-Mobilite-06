"""Analyse des flux GBFS Citiz (transport.data.gouv.fr) + carte.

Usage :
    python collecte/analyse_citiz.py DOSSIER_FLUX [carte_citiz.html]
DOSSIER_FLUX contient un sous-dossier par jeu de données (station_information.json, ...).
"""
import json
import sys
from pathlib import Path

import folium
import pandas as pd


def lire(p: Path):
    return json.load(open(p))["data"] if p.exists() else {}


def charger(racine: Path):
    st, veh, typ = [], [], []
    for d in sorted(p for p in racine.iterdir() if p.is_dir()):
        info = lire(d / "station_information.json").get("stations", [])
        stat = {s["station_id"]: s for s in lire(d / "station_status.json").get("stations", [])}
        for s in info:
            r = stat.get(s["station_id"], {})
            st.append(dict(jeu=d.name, station_id=s["station_id"], nom=s["name"][0]["text"],
                           lat=s["lat"], lon=s["lon"], adresse=s.get("address", ""),
                           capacite=s.get("capacity"), dispo=r.get("num_vehicles_available"),
                           louable=r.get("is_renting"), last=r.get("last_reported")))
        vt = {t["vehicle_type_id"]: t for t in lire(d / "vehicle_types.json").get("vehicle_types", [])}
        for t in vt.values():
            typ.append(dict(jeu=d.name, marque=t.get("make", [{}])[0].get("text"),
                            modele=t.get("model", [{}])[0].get("text"), propulsion=t.get("propulsion_type")))
        for v in lire(d / "vehicle_status.json").get("vehicles", []):
            t = vt.get(v.get("vehicle_type_id"), {})
            veh.append(dict(jeu=d.name, vehicle_id=v["vehicle_id"], lat=v.get("lat"), lon=v.get("lon"),
                            reserve=v.get("is_reserved"), hors_service=v.get("is_disabled"),
                            propulsion=t.get("propulsion_type"),
                            modele=t.get("model", [{}])[0].get("text"), station_id=v.get("station_id"),
                            last=v.get("last_reported")))
    return pd.DataFrame(st), pd.DataFrame(veh), pd.DataFrame(typ)


def main(racine: Path, sortie: str):
    st, veh, typ = charger(racine)
    st["last"] = pd.to_datetime(st["last"], utc=True, errors="coerce")
    veh["last"] = pd.to_datetime(veh["last"], utc=True, errors="coerce")

    # doublons : une même station apparaît-elle dans plusieurs jeux ?
    st["cle"] = st.lat.round(5).astype(str) + "," + st.lon.round(5).astype(str)
    dup = st.groupby("cle").jeu.nunique()
    print(f"Stations (lignes) : {len(st)} | positions uniques : {st.cle.nunique()} "
          f"| positions présentes dans >1 jeu : {(dup > 1).sum()}")
    uniq = st.drop_duplicates("cle")

    par_jeu = st.groupby("jeu").agg(stations=("station_id", "count"), capacite=("capacite", "sum"),
                                    vehicules_dispo=("dispo", "sum"))
    par_jeu["vehicules_flux"] = veh.groupby("jeu").size()
    par_jeu["taux_dispo_%"] = (100 * par_jeu.vehicules_dispo / par_jeu.capacite).round(1)
    print("\n", par_jeu.sort_values("stations", ascending=False).to_string())

    print("\nPropulsion (véhicules) :\n", veh.propulsion.value_counts().to_string())
    print("\nTop modèles :\n", veh.modele.value_counts().head(10).to_string())
    print(f"\nVéhicules réservés : {veh.reserve.sum()} | hors service : {veh.hors_service.sum()}")
    print("Fraîcheur station_status : médiane", st["last"].median(), "| plus ancien", st["last"].min())
    print("Fraîcheur vehicle_status : médiane", veh["last"].median(), "| plus ancien", veh["last"].min())
    print("Stations avec 0 véhicule :", int((st.dispo == 0).sum()), "/", len(st))

    m = folium.Map(location=[46.6, 2.5], zoom_start=6, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
                   attr="Tiles © Esri")
    coul = {"electric": "green", "combustion": "red", "hybrid": "orange"}
    for j, g in uniq.groupby("jeu"):
        fg = folium.FeatureGroup(name=f"{j} ({len(g)})")
        for r in g.itertuples():
            d = 0 if pd.isna(r.dispo) else int(r.dispo)
            folium.CircleMarker([r.lat, r.lon], radius=4 + 2 * d, color="#1d4ed8" if d else "#9ca3af",
                                fill=True, fill_opacity=0.7, weight=1,
                                tooltip=f"{r.nom} — {d} véhicule(s) / cap. {r.capacite}",
                                popup=f"{r.nom}<br>{r.adresse}<br>{j}").add_to(fg)
        fg.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    m.save(sortie)
    print("\nCarte écrite :", sortie)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "carte_citiz.html")
