"""Collecte un relevé GBFS vehicle_status de tous les jeux Citiz et l'ajoute à un dossier parquet.

À planifier toutes les 5 minutes (TTL des flux = 300 s). Compatible notebook Microsoft Fabric :
    python scripts/citiz_collecte.py /lakehouse/default/Files/citiz_snapshots
Sortie : DOSSIER/date=AAAA-MM-JJ/releve_HHMMSS.parquet (une ligne par véhicule et par relevé).
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

CATALOGUE = "https://transport.data.gouv.fr/api/datasets"
S = requests.Session()
S.headers["User-Agent"] = "citiz-surveillance/1.0"


def flux_gbfs() -> dict[str, str]:
    jeux = S.get(CATALOGUE, timeout=120).json()
    return {j["slug"]: next(r["url"] for r in j["resources"] if r["format"] == "gbfs")
            for j in jeux if "citiz" in j["title"].lower()
            and any(r["format"] == "gbfs" for r in j["resources"])}


def vehicle_status(item: tuple[str, str]) -> list[dict]:
    jeu, url = item
    try:
        feeds = {f["name"]: f["url"] for f in S.get(url, timeout=30).json()["data"]["feeds"]}
        vs = S.get(feeds["vehicle_status"], timeout=30).json()["data"]["vehicles"]
    except Exception as e:  # un jeu en panne ne doit pas bloquer les autres
        print(f"{jeu}: ERREUR {e}", file=sys.stderr)
        return []
    return [dict(jeu=jeu, vehicle_id=v["vehicle_id"], lat=v.get("lat"), lon=v.get("lon"),
                 station_id=v.get("station_id"), home_station_id=v.get("home_station_id"),
                 vehicle_type_id=v.get("vehicle_type_id"), is_reserved=v.get("is_reserved"),
                 is_disabled=v.get("is_disabled"), fuel_pct=v.get("current_fuel_percent"),
                 range_m=v.get("current_range_meters"), last_reported=v.get("last_reported")) for v in vs]


def main(sortie: Path):
    t = datetime.now(timezone.utc)
    with ThreadPoolExecutor(8) as ex:
        lignes = [r for res in ex.map(vehicle_status, flux_gbfs().items()) for r in res]
    df = pd.DataFrame(lignes)
    df["releve_utc"] = t
    df["last_reported"] = pd.to_datetime(df["last_reported"], utc=True, errors="coerce")
    dossier = sortie / f"date={t:%Y-%m-%d}"
    dossier.mkdir(parents=True, exist_ok=True)
    f = dossier / f"releve_{t:%H%M%S}.parquet"
    df.to_parquet(f, index=False)
    print(f"{len(df)} véhicules, {df.jeu.nunique()} jeux -> {f}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "releves_citiz"))
