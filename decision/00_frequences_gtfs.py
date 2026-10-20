"""Étape 0 — Fréquence de desserte des arrêts des Alpes-Maritimes (GTFS), pour ne plus compter un arrêt à 1 bus par
jour comme une station de tram.

Réseaux : ceux déjà identifiés par citiz_azur (Lignes d'Azur, Envibus, Palmbus, Sillages, Zest, ZOU, trains régionaux).
Pour chaque flux : jour ouvré type = premier mardi couvert par le calendrier du flux ; services actifs d'après
calendar.txt et calendar_dates.txt ; départs = nombre de passages (stop_times) ce jour-là.
Les arrêts de plusieurs réseaux ou quais à moins de 30 m sont regroupés en un « pôle » (départs additionnés).

Sorties : decision/donnees/poles_arrets_06.csv (pôle, nom, réseaux, départs par jour ouvré, lat, lon)
Caches : data/raw/gtfs_06/ (non versionné)
"""
import hashlib
import io
import json
import zipfile
from datetime import date, timedelta

import pandas as pd
import requests

from communs import DONNEES, ROOT, xy

CACHE = ROOT / "data" / "raw" / "gtfs_06"
CACHE.mkdir(parents=True, exist_ok=True)
log = json.loads((ROOT / "citiz_azur" / "data" / "collection_log.json").read_text())
flux = [(s["title"], s["url"]) for s in log["sources"] if s["type"] == "gtfs" and s["status"] == "ok"]


def telecharger(url):
    p = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:16] + ".zip")
    if not p.exists():
        r = requests.get(url, timeout=(15, 180), headers={"User-Agent": "hackathon-citiz-epitech"})
        r.raise_for_status()
        p.write_bytes(r.content)
    return zipfile.ZipFile(p)


def lire(z, nom, **kw):
    noms = {n.split("/")[-1]: n for n in z.namelist()}
    if nom not in noms:
        return None
    return pd.read_csv(io.BytesIO(z.read(noms[nom])), dtype=str, **kw)


def services_actifs(z):
    cal, cd = lire(z, "calendar.txt"), lire(z, "calendar_dates.txt")
    if cal is not None and len(cal):
        debut, fin = pd.to_datetime(cal.start_date).min(), pd.to_datetime(cal.end_date).max()
    else:
        debut, fin = pd.to_datetime(cd.date).min(), pd.to_datetime(cd.date).max()
    jour = max(debut.date(), date.today())
    if jour > fin.date():
        jour = debut.date()
    while jour.weekday() != 1:                                   # mardi
        jour += timedelta(days=1)
    actifs = set()
    if cal is not None and len(cal):
        c = cal[(pd.to_datetime(cal.start_date).dt.date <= jour) & (pd.to_datetime(cal.end_date).dt.date >= jour)]
        actifs |= set(c.loc[c.tuesday == "1", "service_id"])
    if cd is not None and len(cd):
        j = cd[cd.date == jour.strftime("%Y%m%d")]
        actifs |= set(j.loc[j.exception_type == "1", "service_id"])
        actifs -= set(j.loc[j.exception_type == "2", "service_id"])
    return actifs, jour


lignes, journal = [], []
for titre, url in flux:
    try:
        z = telecharger(url)
        actifs, jour = services_actifs(z)
        trips = lire(z, "trips.txt", usecols=["trip_id", "service_id"])
        trips = trips[trips.service_id.isin(actifs)]
        st = lire(z, "stop_times.txt", usecols=["trip_id", "stop_id"])
        st = st[st.trip_id.isin(trips.trip_id)]
        dep = st.groupby("stop_id").size().rename("departs")
        stops = lire(z, "stops.txt")
        stops = stops[stops.get("location_type", pd.Series("0", index=stops.index)).fillna("0").isin(["0", ""])]
        stops = stops.join(dep, on="stop_id").fillna({"departs": 0})
        stops["reseau"] = titre
        lignes.append(stops[["stop_name", "stop_lat", "stop_lon", "departs", "reseau"]])
        journal.append({"reseau": titre, "jour_type": str(jour), "services_actifs": len(actifs),
                        "arrets": len(stops), "passages": int(stops.departs.sum())})
        print(f"{titre:<60} {jour}  {len(stops):>5} arrêts  {int(stops.departs.sum()):>7} passages")
    except Exception as e:                                       # un flux en panne ne bloque pas les autres
        journal.append({"reseau": titre, "erreur": str(e)})
        print(f"{titre}: ERREUR {e}")

a = pd.concat(lignes, ignore_index=True)
a["lat"], a["lon"] = a.stop_lat.astype(float), a.stop_lon.astype(float)
a = a[a.lat.between(43.4, 44.4) & a.lon.between(6.6, 7.8)]
P = xy(a.lon, a.lat)
a["k"] = (P[:, 0] // 30).astype(int).astype(str) + "_" + (P[:, 1] // 30).astype(int).astype(str)
poles = a.groupby("k").agg(nom=("stop_name", "first"), lat=("lat", "mean"), lon=("lon", "mean"), departs=("departs", "sum"),
                           reseaux=("reseau", lambda s: " | ".join(sorted(set(s)))), quais=("stop_name", "size")).reset_index(drop=True)
poles["train"] = poles.reseaux.str.contains("Train", case=False)
poles.to_csv(DONNEES / "poles_arrets_06.csv", index=False)
(DONNEES / "journal_gtfs_06.json").write_text(json.dumps(journal, ensure_ascii=False, indent=2))
print(f"\n{len(poles):,} pôles d'arrêts ; {int((poles.departs == 0).sum())} sans passage le jour type ; "
      f"départs médians {poles.departs.median():.0f}/jour")
