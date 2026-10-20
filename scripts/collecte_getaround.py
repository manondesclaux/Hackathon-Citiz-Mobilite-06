"""Télécharge les positions des véhicules Getaround (GBFS 3.0, un sous-flux par commune) et dédoublonne.

Usage :
    python scripts/collecte_getaround.py DOSSIER_SORTIE
Sortie : DOSSIER_SORTIE/vehicles.json (liste de véhicules uniques : id, lat, lon, is_reserved, is_disabled).
"""
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ressource GBFS du jeu transport.data.gouv.fr « flotte-getaround-en-libre-service-france »
INDEX = "https://www.data.gouv.fr/api/1/datasets/r/b9a4aeb4-7689-47ea-83a8-992378985381"
HEADERS = {"User-Agent": "citiz-analyse/1.0"}


def get(url: str):
    for essai in range(3):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60).read())
        except Exception:
            time.sleep(1 + essai)
    return None


def vehicules(url: str) -> list[dict]:
    g = get(url)
    if not g:
        return []
    feeds = {f["name"]: f["url"] for f in g["data"]["feeds"]}
    nom = next((n for n in ("vehicle_status", "free_bike_status") if n in feeds), None)
    d = get(feeds[nom]) if nom else None
    return [] if not d else (d["data"].get("vehicles") or d["data"].get("bikes") or [])


def main(sortie: Path):
    systemes = [d["versions"][0]["url"] for d in get(INDEX)["data"]["datasets"]]
    print(len(systemes), "sous-flux")
    uniques, vides = {}, 0
    with ThreadPoolExecutor(12) as ex:
        for i, vs in enumerate(ex.map(vehicules, systemes), 1):
            vides += not vs
            for v in vs:
                uniques.setdefault(v["vehicle_id"], dict(id=v["vehicle_id"], lat=v["lat"], lon=v["lon"],
                                   is_reserved=v.get("is_reserved"), is_disabled=v.get("is_disabled")))
            if i % 500 == 0:
                print(f"  {i}/{len(systemes)} | {len(uniques)} véhicules uniques", flush=True)
    sortie.mkdir(parents=True, exist_ok=True)
    json.dump(list(uniques.values()), open(sortie / "vehicles.json", "w"))
    print(f"{len(uniques)} véhicules uniques ({vides} sous-flux vides) -> {sortie / 'vehicles.json'}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "getaround"))
