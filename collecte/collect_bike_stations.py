"""Stations de vélos en libre-service (VLS) en France, à partir des flux GBFS de transport.data.gouv.fr.

On parcourt les jeux « vehicles-sharing » qui contiennent des vélos, et on garde ceux qui publient des stations
(station_information). Les vélos/trottinettes en free-floating n'ont pas de station : ils ne sont pas retenus.

Produit : donnees/model/bike_stations.csv (une ligne par station, dédoublonnée, colonne type_station :
« VLS » ou « zone free-floating »)
Usage : python3 collecte/collect_bike_stations.py
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "donnees" / "model" / "bike_stations.csv"
UA = {"User-Agent": "hackathon-mobility-citiz/0.1 (projet etudiant Epitech)"}


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(1 + attempt)
    return None


def feeds(gbfs_url):
    j = get(gbfs_url)
    if not j:
        return {}
    data = j.get("data", {}) if isinstance(j, dict) else {}
    if isinstance(data, dict) and "feeds" in data:
        lst = data["feeds"]
    elif isinstance(data, dict) and data and isinstance(next(iter(data.values())), dict):
        lst = next(iter(data.values())).get("feeds", [])
    else:
        lst = []                      # format non standard : ignoré
    return {f["name"]: f["url"] for f in lst if isinstance(f, dict) and "name" in f}


def txt(x):
    if isinstance(x, list):
        return x[0].get("text", "") if x else ""
    return x or ""


def stations_of(ds):
    try:
        return _stations_of(ds)
    except Exception as e:            # un flux défaillant ne doit pas bloquer les autres
        print(f"  ignoré : {ds.get('title')} ({e})", flush=True)
        return []


def _stations_of(ds):
    gbfs = [r for r in ds.get("resources", []) if (r.get("format") or "").lower() == "gbfs"]
    rows = []
    for r in gbfs:
        url = r.get("original_url") or r.get("url")
        f = feeds(url)
        if "station_information" not in f:
            continue
        info = get(f["station_information"])
        for s in (info or {}).get("data", {}).get("stations", []):
            if s.get("lat") is None or s.get("lon") is None:
                continue
            rows.append({"reseau": ds["title"], "operateur": ds.get("publisher", {}).get("name", ""),
                         "station_id": str(s.get("station_id")), "nom": txt(s.get("name")),
                         "lat": float(s["lat"]), "lon": float(s["lon"]), "capacite": s.get("capacity")})
    return rows


catalog = get("https://transport.data.gouv.fr/api/datasets")
bikes = [d for d in catalog if d.get("type") == "vehicles-sharing"
         and "bicycle" in (d.get("sub_types") or []) and "carsharing" not in (d.get("sub_types") or [])]
print(f"{len(bikes)} jeux de données vélos à examiner…", flush=True)
with ThreadPoolExecutor(max_workers=6) as ex:
    rows = [r for chunk in ex.map(stations_of, bikes) for r in chunk]

df = pd.DataFrame(rows)
n0 = len(df)
df = df[df.lat.between(-22, 52) & df.lon.between(-62, 56)]
df["_k"] = df.lat.round(4).astype(str) + "," + df.lon.round(4).astype(str)
df = df.drop_duplicates("_k").drop(columns="_k")
# Les opérateurs de free-floating (Dott, Pony, Voi, Lime…) publient leurs zones de stationnement conseillées comme des
# « stations » : ce ne sont pas des stations de vélos en libre-service. Sans ce marquage, ≈ 26 700 des 32 000 points
# sont comptés à tort comme des stations (voir decision/communs.py).
FREE_FLOATING = r"dott|pony|voi\b|voi technology|lime|tier|bird|bolt|cooltra|yego|cityscoot|trottinette"
df["type_station"] = (df.operateur.fillna("") + " " + df.reseau.fillna("")).str.contains(FREE_FLOATING, case=False).map(
    {True: "zone free-floating", False: "VLS"})
OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False)
print(f"{n0} stations brutes -> {len(df)} points uniques ({(df.type_station == 'VLS').sum()} vraies stations VLS, "
      f"{(df.type_station != 'VLS').sum()} zones free-floating), {df.reseau.nunique()} réseaux -> {OUT}")
