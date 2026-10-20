"""Arrêts de transport en commun en France : nettoyage de l'agrégat national GTFS (non dédoublonné à la source).

Source : « Arrêts de transport en France », data.gouv.fr (export du 13/01/2026, 437 Mo)
https://www.data.gouv.fr/datasets/arrets-de-transport-en-france

Nettoyage :
- on garde les points d'arrêt (location_type 0 ou vide) ; les gares « parentes », entrées et nœuds sont écartés ;
- coordonnées aberrantes écartées ;
- dédoublonnage : un même arrêt publié par plusieurs réseaux, ou les deux quais d'un arrêt de part et d'autre
  de la rue, sont fusionnés (même nom normalisé dans une maille de 50 m) ;
- mode « train » repéré quand le réseau est SNCF / TER / Intercités / TGV (le fichier ne donne pas le mode).

Produit : DATA clean/model/transport_stops.csv.gz
Usage : python3 scripts/clean_transport_stops.py
"""
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
SRC = sorted((ROOT / "data" / "raw" / "transport_download").glob("gtfs_stops_france_*.csv"))[-1]
OUT = ROOT / "DATA clean" / "model" / "transport_stops.csv.gz"
to3035 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

cols = ["dataset_custom_title", "dataset_organisation", "stop_name", "stop_lat", "stop_lon", "location_type"]
parts, n_raw = [], 0
for ch in pd.read_csv(SRC, usecols=cols, chunksize=500_000, dtype={"location_type": str}, low_memory=False):
    n_raw += len(ch)
    lt = ch.location_type.fillna("0").str.strip().replace("", "0")
    ch = ch[lt.isin(["0", "0.0"])]
    ch = ch.dropna(subset=["stop_lat", "stop_lon"])
    ch = ch[ch.stop_lat.between(-22, 52) & ch.stop_lon.between(-62, 56) & ~((ch.stop_lat == 0) & (ch.stop_lon == 0))]
    parts.append(ch)
df = pd.concat(parts, ignore_index=True)
n_stops = len(df)

txt = (df.dataset_custom_title.fillna("") + " " + df.dataset_organisation.fillna("")).str.lower()
df["mode"] = np.where(txt.str.contains(r"sncf|\bter\b|intercit|tgv|ouigo|transilien|rer\b"), "train", "bus/tram/métro/car")
x, y = to3035.transform(df.stop_lon.values, df.stop_lat.values)
df["x"], df["y"] = np.round(x, 1), np.round(y, 1)
df["_k"] = df.stop_name.map(norm) + "|" + (df.x // 50).astype(int).astype(str) + "|" + (df.y // 50).astype(int).astype(str)
agg = (df.groupby("_k", as_index=False)
         .agg(nom=("stop_name", "first"), lat=("stop_lat", "mean"), lon=("stop_lon", "mean"),
              x=("x", "mean"), y=("y", "mean"), mode=("mode", lambda s: "train" if (s == "train").any() else s.iloc[0]),
              reseau=("dataset_custom_title", "first"), n_sources=("_k", "size"))
         .drop(columns="_k"))
OUT.parent.mkdir(parents=True, exist_ok=True)
agg.round({"lat": 6, "lon": 6, "x": 1, "y": 1}).to_csv(OUT, index=False)
print(f"{n_raw:,} lignes brutes -> {n_stops:,} points d'arrêt valides -> {len(agg):,} arrêts uniques "
      f"(dont {int((agg['mode'] == 'train').sum()):,} ferroviaires) -> {OUT}")
