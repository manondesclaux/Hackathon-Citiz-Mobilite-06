"""Collecte des véhicules Getaround France (GBFS), avec reprise et respect de la limite de débit.

Getaround publie ~3 700 flux (un par ville) qui se recoupent. Le serveur répond 429 si on va trop vite :
on interroge donc les flux un par un, on attend quand il le demande, et chaque flux est mis en cache
dans data/raw/getaround_<date>/ pour pouvoir relancer le script sans tout refaire.

Usage : python3 scripts/collect_getaround.py [--max-minutes 60]
Produit : data/raw/getaround_vehicles_<date>.csv (véhicules uniques) une fois tous les flux collectés.
"""
import argparse
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "https://fr.getaround.com/gbfs/manifest?country_code=FR"
DELAY_S = 0.6  # pause entre deux requêtes

session = requests.Session()
session.headers["User-Agent"] = "hackathon-mobility-citiz/0.1 (projet etudiant Epitech)"


def get(url):
    wait = 30
    for _ in range(8):
        r = session.get(url, timeout=30)
        if r.status_code == 429:
            pause = int(r.headers.get("Retry-After", wait))
            print(f"  429 : pause {pause} s", flush=True)
            time.sleep(pause)
            wait = min(wait * 2, 600)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"toujours limité après plusieurs essais : {url}")


def collect(max_minutes, day=None):
    day = day or date.today().isoformat()
    cache_dir = ROOT / "data" / "raw" / f"getaround_{day}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = cache_dir / "_manifest.json"
    if not manifest_file.exists():
        manifest_file.write_text(json.dumps(get(MANIFEST)["data"]["datasets"]))
    systems = json.loads(manifest_file.read_text())

    t0 = time.time()
    todo = [s for s in systems if not (cache_dir / f"{s['system_id']}.json").exists()]
    print(f"{len(systems) - len(todo)}/{len(systems)} flux déjà en cache, {len(todo)} à collecter", flush=True)
    for i, s in enumerate(todo, 1):
        if time.time() - t0 > max_minutes * 60:
            print("budget de temps atteint, relancer pour continuer", flush=True)
            break
        url = s["versions"][0]["url"].rsplit("/gbfs", 1)[0] + "/vehicle_status"
        try:
            vehicles = get(url)["data"]["vehicles"]
        except Exception as e:
            print(f"  échec {s['system_id']} : {e}", flush=True)
            continue
        rows = [[v["vehicle_id"], v["lat"], v["lon"]] for v in vehicles]
        (cache_dir / f"{s['system_id']}.json").write_text(json.dumps(rows))
        if i % 100 == 0:
            print(f"  {i}/{len(todo)} ({time.time() - t0:.0f} s)", flush=True)
        time.sleep(DELAY_S)

    done = [p for p in cache_dir.glob("*.json") if not p.name.startswith("_")]
    rows = [r for p in done for r in json.loads(p.read_text())]
    df = pd.DataFrame(rows, columns=["id", "lat", "lon"]).drop_duplicates("id")
    complete = len(done) == len(systems)
    out = ROOT / "data" / "raw" / f"getaround_vehicles_{day}{'' if complete else '_partiel'}.csv"
    df.to_csv(out, index=False)
    print(f"{len(done)}/{len(systems)} flux, {len(df):,} véhicules uniques -> {out.name}", flush=True)
    return df, len(done), len(systems)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=90)
    collect(ap.parse_args().max_minutes)
