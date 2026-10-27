"""Nettoyage des données d'offre d'autopartage (Citiz, concurrents, Getaround).

Entrées  : data/raw/ (relevés GBFS bruts, derniers fichiers datés) + data/raw/getaround_<date>/ (cache par flux)
Sorties  : donnees/citiz_stations.csv, competitor_sites.csv (+ getaround_vehicles.csv, non versionné)
           donnees/data_quality_report.md (ce qui a été corrigé ou écarté, et pourquoi)

Chaque point est rattaché à sa commune (API Géo, etalab) et à son département. Le géocodage inverse est mis en cache
dans data/raw/geocode_cache.json : le script peut être relancé sans refaire les appels.

Usage : python3 collecte/clean_data.py
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
RAW, CLEAN = ROOT / "data" / "raw", ROOT / "donnees"
CLEAN.mkdir(parents=True, exist_ok=True)
report = []
log = lambda s: (print(s, flush=True), report.append(s))

# Emprise grossière France métropolitaine + DROM, pour repérer les coordonnées aberrantes
def in_france(lat, lon):
    metro = lat.between(41, 51.5) & lon.between(-5.5, 9.7)
    drom = lat.between(-22, 18) & lon.between(-62, 56)
    return metro | drom

# ---------- Géocodage inverse (commune) avec cache ----------
CACHE_FILE = RAW / "geocode_cache.json"
cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}

def commune_of(lat, lon):
    key = f"{lat:.4f},{lon:.4f}"
    if key in cache:
        return cache[key]
    url = f"https://geo.api.gouv.fr/communes?lat={lat:.5f}&lon={lon:.5f}&fields=code,nom,codeDepartement&limit=1"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                j = json.load(r)
            cache[key] = [j[0]["code"], j[0]["nom"], j[0]["codeDepartement"]] if j else [None, None, None]
            return cache[key]
        except Exception:
            time.sleep(1 + attempt)
    return [None, None, None]

def add_commune(df):
    pts = list(zip(df.lat.round(4), df.lon.round(4)))
    todo = [p for p in set(pts) if f"{p[0]:.4f},{p[1]:.4f}" not in cache]
    if todo:
        log(f"- géocodage inverse : {len(todo)} nouveaux points (API Géo)")
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(lambda p: commune_of(*p), todo))
        CACHE_FILE.write_text(json.dumps(cache))
    res = [cache.get(f"{la:.4f},{lo:.4f}", [None, None, None]) for la, lo in pts]
    df = df.copy()
    df["commune_code"], df["commune_nom"], df["dep"] = zip(*res)
    return df

latest = lambda pattern: sorted(RAW.glob(pattern))[-1]

# =====================================================================
log("# Rapport de qualité des données\n")
log(f"*Généré le {pd.Timestamp.now():%d/%m/%Y %H:%M}.*\n")

# ---------- 1. Citiz ----------
src = latest("citiz_stations_*.csv")
c = pd.read_csv(src, dtype={"id": str})
log(f"## 1. Stations Citiz\n\nFichier : `{src.name}` — **{len(c)} lignes** brutes, {c.network.nunique()} réseaux régionaux.\n")
n0 = len(c)
c["name"] = c["name"].fillna("").str.strip().str.replace(r"\s+", " ", regex=True)
bad = ~in_france(c.lat, c.lon) | c.lat.isna() | c.lon.isna()
log(f"- coordonnées manquantes ou hors France : **{int(bad.sum())}**")
c = c[~bad]
c["_k"] = c.lat.round(4).astype(str) + "," + c.lon.round(4).astype(str)
n1 = len(c)
c = c.sort_values("n_vehicles", ascending=False).drop_duplicates("_k").drop(columns="_k")
log(f"- doublons de lieu (mêmes coordonnées à 10 m près, p. ex. Lyon présent dans deux flux) : **{n1 - len(c)}** supprimés")
c["flex"] = c.name.str.contains(r"\bflex\b", case=False, regex=True)
c["sans_vehicule"] = c.n_vehicles == 0
log(f"- stations « Flex » (zone d'usage à part, non assimilables à une station classique) : **{int(c.flex.sum())}** conservées, marquées `flex`")
log(f"- stations sans véhicule rattaché : **{int(c.sans_vehicule.sum())}** conservées, marquées `sans_vehicule` "
    f"(à exclure du comptage de flotte, utiles pour l'emprise)")
c = add_commune(c)
miss = int(c.commune_code.isna().sum())
log(f"- rattachement à une commune : {len(c) - miss}/{len(c)} (échecs : {miss})")
c.drop(columns=["vehicles_source", "model"]).to_csv(CLEAN / "citiz_stations.csv", index=False)
log(f"\n**Résultat : {len(c)} stations, {int(c.n_vehicles.sum())} véhicules** → `donnees/citiz_stations.csv` "
    f"({n0 - len(c)} lignes écartées au total).\n")

# ---------- 2. Concurrents en station / free-floating ----------
src = latest("competitors_*.csv")
o = pd.read_csv(src, dtype={"id": str})
log(f"## 2. Concurrents (Clem', Optymo, Leo&Go)\n\nFichier : `{src.name}` — **{len(o)} lignes** brutes.\n")
bad = ~in_france(o.lat, o.lon)
log(f"- coordonnées aberrantes : **{int(bad.sum())}**")
o = o[~bad]
o["site"] = o.lat.round(4).astype(str) + "," + o.lon.round(4).astype(str)
agg = (o.groupby(["operator", "network", "model", "site"], as_index=False)
         .agg(lat=("lat", "mean"), lon=("lon", "mean"), name=("name", "first"),
              n_stations=("id", "size"), n_vehicles=("n_vehicles", "sum")))
log(f"- Clem' publie une station par place : {len(o[o.operator == chr(67)+'lem'+chr(39)])} stations pour "
    f"{int(agg[agg.operator == 'Clem'+chr(39)].shape[0])} sites distincts → **regroupées par site** (un site = plusieurs véhicules)")
zero = agg[(agg.operator == "Optymo") & (agg.n_vehicles == 0)]
log(f"- Optymo : {len(zero)} stations sans véhicule disponible au moment du relevé (conservées, `n_vehicles = 0`)")
log("- Leo&Go : véhicules en free-floating, **photo à un instant T** (pas une implantation fixe)")
agg = add_commune(agg).drop(columns="site")
agg.to_csv(CLEAN / "competitor_sites.csv", index=False)
log(f"\n**Résultat : {len(agg)} sites, {int(agg.n_vehicles.sum())} véhicules** → `donnees/competitor_sites.csv`.\n")

# ---------- 3. Getaround ----------
gdir = sorted(d for d in RAW.glob("getaround_20*") if d.is_dir())[-1]
files = [p for p in gdir.glob("*.json") if not p.name.startswith("_")]
n_total = len(json.loads((gdir / "_manifest.json").read_text()))
rows = [r for p in files for r in json.loads(p.read_text())]
g = pd.DataFrame(rows, columns=["id", "lat", "lon"])
log(f"## 3. Getaround\n\nCache : `{gdir.name}` — **{len(files)}/{n_total} flux** ({len(files) / n_total:.0%}), {len(g):,} lignes brutes.\n")
n1 = len(g)
g = g.drop_duplicates("id")
log(f"- doublons entre flux voisins (un véhicule apparaît dans plusieurs villes) : **{n1 - len(g):,}** supprimés")
bad = ~in_france(g.lat, g.lon)
log(f"- coordonnées aberrantes : **{int(bad.sum())}**")
g = g[~bad]
deps = json.loads((RAW / "departements-avec-outre-mer.geojson").read_text())["features"]
shapes = [shape(f["geometry"]) for f in deps]
tree = shapely.STRtree(shapes)
pts = shapely.points(g.lon.values, g.lat.values)
pi, di = tree.query(pts, predicate="within")
g["dep"] = None
g.iloc[pi, g.columns.get_loc("dep")] = np.array([f["properties"]["code"] for f in deps], dtype=object)[di]
out = int(g.dep.isna().sum())
log(f"- hors territoire (mer, pays frontaliers) : **{out}** écartés")
g = g.dropna(subset=["dep"])
g.to_csv(CLEAN / "getaround_vehicles.csv", index=False)
log(f"\n**Résultat : {len(g):,} véhicules uniques** → `donnees/getaround_vehicles.csv`. "
    + ("" if len(files) >= n_total else f"⚠️ **Collecte partielle ({len(files) / n_total:.0%} des flux)** : les volumes Getaround sont des planchers."))

# ---------- 4. Limites générales ----------
log("""
## 4. Limites qui ne se corrigent pas par le nettoyage

- **Photo à un instant T** : aucune mesure d'usage (locations, taux d'occupation) dans les flux ouverts.
- **Opérateurs sans flux GBFS** (Modulauto, Zity, Free2Move, Ubeeqo, Marcel, Mobilize Share) : absents.
- **Getaround** : voitures de particuliers, pas comparables une à une à des véhicules Citiz.
- **Fichiers datés en double** (19 et 20 octobre) : seul le plus récent est utilisé ; les anciens sont conservés dans `data/raw/`.
""")
(CLEAN / "data_quality_report.md").write_text("\n".join(report), encoding="utf-8")
print(f"\nRapport : {CLEAN / 'data_quality_report.md'}")
