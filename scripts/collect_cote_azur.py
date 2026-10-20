"""Secteur Côte d'Azur (Alpes-Maritimes, 06) : concurrents de Citiz, population et activité.

Ce script récupère les données EN LIGNE, les nettoie et les enregistre en CSV dans DATA clean/cote_azur/,
pour qu'un notebook puisse les charger directement.

Concurrents (relevé en direct des flux GBFS, transport.data.gouv.fr) :
- Getaround (autopartage entre particuliers et flotte connectée) : position exacte de chaque véhicule, modèle
- Lime (Nice, Sophia Antipolis), Pony (Nice), Yego (Nice), Dott (flux national) : vélos, trottinettes, scooters
- stations de vélos en libre-service (DATA clean/model/bike_stations.csv, issu de scripts/collect_bike_stations.py)
Opérateurs sans flux ouvert : table documentée à la main (sources en colonne).

Territoire et population (INSEE, API Géo) :
- communes du 06 : contours, intercommunalité (API Géo)
- population par âge, ménages sans voiture, locataires (DATA clean/communes_demo.csv)
- emploi au lieu de travail, actifs, chômeurs, étudiants, retraités (INSEE, recensement 2022)
- lits touristiques (INSEE, capacité d'hébergement 2025) et résidences secondaires (INSEE, logement 2022)
- population au carreau de 200 m (INSEE Filosofi 2021)
- arrêts de transport en commun (DATA clean/model/transport_stops.csv.gz)

Usage : python3 scripts/collect_cote_azur.py
"""
import csv
import io
import json
import re
import time
import unicodedata
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
RAW, CLEAN = ROOT / "data" / "raw", ROOT / "DATA clean"
DL = RAW / "insee_download"
OUT = CLEAN / "cote_azur"
OUT.mkdir(parents=True, exist_ok=True)
DEP = "06"
UA = {"User-Agent": "hackathon-mobility-citiz/0.1 (projet etudiant Epitech)"}
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")
report = []
log = lambda s: (print(s, flush=True), report.append(s))


def get(url, retries=6):
    wait = 20
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:                                    # limite de débit : on attend
                time.sleep(int(e.headers.get("Retry-After", wait))); wait = min(wait * 2, 300); continue
            if e.code == 404:
                return None
            time.sleep(2 + attempt)
        except Exception:
            time.sleep(2 + attempt)
    return None


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# =============================================================== 1. Communes du 06 (API Géo)
geo = get(f"https://geo.api.gouv.fr/departements/{DEP}/communes?fields=nom,code,codesPostaux,population,surface,"
          f"centre,contour,codeEpci&format=geojson&geometry=contour")
feats = geo["features"]
log(f"# Secteur Côte d'Azur (département {DEP}) — relevé du {NOW}\n\n- {len(feats)} communes (API Géo)")
epci_codes = sorted({f["properties"].get("codeEpci") for f in feats if f["properties"].get("codeEpci")})
epci_names = {c: (get(f"https://geo.api.gouv.fr/epcis/{c}?fields=nom") or {}).get("nom", "") for c in epci_codes}
(OUT / "communes_cote_azur.geojson").write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")

shapes = [shape(f["geometry"]) for f in feats]
codes = np.array([f["properties"]["code"] for f in feats], dtype=object)
names = {f["properties"]["code"]: f["properties"]["nom"] for f in feats}
tree = shapely.STRtree(shapes)


def locate(df):
    """Ajoute la commune (code, nom) de chaque point ; écarte les points hors du département."""
    pts = shapely.points(df.lon.values, df.lat.values)
    pi, ci = tree.query(pts, predicate="within")
    df = df.copy()
    df["commune_code"] = None
    df.iloc[pi, df.columns.get_loc("commune_code")] = codes[ci]
    df = df.dropna(subset=["commune_code"])
    df["commune_nom"] = df.commune_code.map(names)
    return df


# =============================================================== 2. Concurrents : relevé GBFS en direct
def feeds_of(gbfs_url):
    j = get(gbfs_url)
    if not j:
        return {}
    data = j.get("data", {})
    lst = data["feeds"] if "feeds" in data else (next(iter(data.values())).get("feeds", []) if data else [])
    return {f["name"]: f["url"] for f in lst}


def vehicle_types(f):
    if "vehicle_types" not in f:
        return {}
    j = get(f["vehicle_types"]) or {}
    return {str(t.get("vehicle_type_id")): t for t in j.get("data", {}).get("vehicle_types", [])}


def name_of(t):
    n = t.get("name")
    return n[0].get("text", "") if isinstance(n, list) and n else (n or "")


rows = []
# --- Getaround : un flux par commune ; on interroge ceux des communes du 06
manifest = (get("https://fr.getaround.com/gbfs/manifest?country_code=FR") or {}).get("data", {}).get("datasets", [])
ga_systems = {d["system_id"].replace("getaround_", ""): d["versions"][0]["url"] for d in manifest}
targets = [s for s in sorted({slug(n) for n in names.values()}) if s in ga_systems]
log(f"- Getaround : {len(targets)} flux de communes du 06 à interroger (sur {len(ga_systems)} en France)")
ga_types = {}
for i, s in enumerate(targets):
    base = ga_systems[s].rsplit("/gbfs", 1)[0]
    if not ga_types:
        ga_types = vehicle_types({"vehicle_types": base + "/vehicle_types"})
    vs = (get(base + "/vehicle_status") or {}).get("data", {}).get("vehicles", [])
    for v in vs:
        uri = (v.get("rental_uris") or {}).get("web", "")
        m = re.search(r"/location-voiture/[^/]+/([a-z0-9-]+?)-\d+$", uri)
        model = m.group(1).replace("-", " ") if m else ""
        t = ga_types.get(str(v.get("vehicle_type_id")), {})
        rows.append({"operateur": "Getaround", "service": "Getaround", "categorie": "autopartage (particuliers + flotte connectée)",
                     "type_vehicule": t.get("form_factor", "car"), "motorisation": t.get("propulsion_type", ""),
                     "modele": model, "id": v.get("vehicle_id"), "lat": v.get("lat"), "lon": v.get("lon"),
                     "station_id": "", "reserve": v.get("is_reserved"), "indisponible": v.get("is_disabled"),
                     "url": uri, "source": "GBFS Getaround (" + s + ")"})
    time.sleep(1.2)                                                      # respect de la limite de débit

# --- Micromobilité (free-floating) dont le flux couvre le 06
MICRO = {
    ("Lime", "Lime Nice"): "https://data.lime.bike/api/partners/v2/gbfs/nice/gbfs.json",
    ("Lime", "Lime Sophia Antipolis"): "https://data.lime.bike/api/partners/v2/gbfs/casa/gbfs.json",
    ("Pony", "Pony Nice"): "https://proxy.transport.data.gouv.fr/resource/pony-nice-gbfs/gbfs.json",
    ("Yego", "Yego Nice"): "https://services.rideyego.com/gbfs/2-2/nice/fr/gbfs",
    ("Dott", "Dott (flux national)"): "https://gbfs.api.ridedott.com/public/v2/countries/fr/gbfs.json",
}
for (op, service), url in MICRO.items():
    f = feeds_of(url)
    if not f:
        log(f"- {service} : flux indisponible"); continue
    types = vehicle_types(f)
    feed = "vehicle_status" if "vehicle_status" in f else ("free_bike_status" if "free_bike_status" in f else None)
    data = (get(f[feed]) or {}).get("data", {}) if feed else {}
    n0 = len(rows)
    for v in data.get("vehicles", data.get("bikes", [])):
        if v.get("lat") is None:
            continue
        t = types.get(str(v.get("vehicle_type_id")), {})
        rows.append({"operateur": op, "service": service, "categorie": "micromobilité (free-floating)",
                     "type_vehicule": t.get("form_factor", "bicycle"), "motorisation": t.get("propulsion_type", ""),
                     "modele": name_of(t), "id": v.get("vehicle_id", v.get("bike_id")), "lat": v.get("lat"), "lon": v.get("lon"),
                     "station_id": v.get("station_id", ""), "reserve": v.get("is_reserved"), "indisponible": v.get("is_disabled"),
                     "url": "", "source": f"GBFS {service}"})
    log(f"- {service} : {len(rows) - n0} véhicules dans le flux")

veh = pd.DataFrame(rows)
veh["lat"], veh["lon"] = pd.to_numeric(veh.lat), pd.to_numeric(veh.lon)
n_raw = len(veh)
veh = veh.dropna(subset=["lat", "lon"]).drop_duplicates(["operateur", "id"])
veh = locate(veh)
veh["date_releve"] = NOW
veh.to_csv(OUT / "concurrents_vehicules.csv", index=False)
log(f"- **Véhicules concurrents dans le 06 : {len(veh):,}** (sur {n_raw:,} lignes brutes ; doublons et points hors 06 écartés)")
for (op, typ), n in veh.groupby(["operateur", "type_vehicule"]).size().items():
    log(f"  - {op} / {typ} : {n}")

# --- Stations : vélos en libre-service + Citiz/Clem' éventuels
bike = pd.read_csv(CLEAN / "model" / "bike_stations.csv")
bike = locate(bike.rename(columns={"capacite": "capacite"}))
cit = locate(pd.read_csv(CLEAN / "citiz_stations.csv"))
comp = locate(pd.read_csv(CLEAN / "competitor_sites.csv"))
stations = pd.concat([
    pd.DataFrame({"operateur": bike.operateur, "service": bike.reseau,
                  # Lime et Pony publient leurs zones de stationnement recommandées comme des « stations »
                  "categorie": np.where(bike.operateur.str.contains("Lime|Pony", case=False) | bike.reseau.str.contains("Lime|Pony", case=False),
                                        "zone de stationnement free-floating", "vélos en libre-service (station)"),
                  "nom": bike.nom, "lat": bike.lat, "lon": bike.lon, "capacite": bike.capacite,
                  "commune_code": bike.commune_code, "commune_nom": bike.commune_nom}),
    pd.DataFrame({"operateur": "Citiz", "service": cit.get("network", pd.Series(dtype=str)), "categorie": "autopartage en station",
                  "nom": cit.get("name", pd.Series(dtype=str)), "lat": cit.lat, "lon": cit.lon,
                  "capacite": cit.get("n_vehicles", pd.Series(dtype=float)), "commune_code": cit.commune_code, "commune_nom": cit.commune_nom}),
    pd.DataFrame({"operateur": comp.get("operator", pd.Series(dtype=str)), "service": comp.get("network", pd.Series(dtype=str)),
                  "categorie": "autopartage en station", "nom": comp.get("name", pd.Series(dtype=str)), "lat": comp.lat, "lon": comp.lon,
                  "capacite": comp.get("n_vehicles", pd.Series(dtype=float)), "commune_code": comp.commune_code, "commune_nom": comp.commune_nom}),
], ignore_index=True)
stations.to_csv(OUT / "concurrents_stations.csv", index=False)
log(f"- Stations et zones dans le 06 : {len(stations)} — " + ", ".join(f"{k} : {v}" for k, v in stations.categorie.value_counts().items()) + f" (Citiz : {len(cit)}, autres autopartages : {len(comp)})")

# --- Opérateurs : qui sont-ils ? (y compris ceux sans flux ouvert)
fleet = veh.groupby("operateur").size()
OPS = [
    ("Getaround", "Getaround (groupe danois GoMore depuis mai 2026)", "autopartage entre particuliers + flotte connectée", "actif",
     int(fleet.get("Getaround", 0)), "relevé GBFS", "200+ véhicules dans la Métropole (2023), occupation 60-76 %, partenariat avec la Métropole depuis 2021",
     "https://www.tesla-mag.com/getaround-et-la-metropole-nice-cote-dazur-renforcent-leur-partenariat-pour-lautopartage-electrique/"),
    ("Mobilize Share", "Renault", "autopartage en boucle, 100 % électrique", "arrêté le 30/06/2026", 0, "presse",
     "65 véhicules, 38 stations sur 6 communes (Nice, Saint-Laurent-du-Var, Cagnes, Villefranche, Beaulieu, Carros) ; 86 bornes reprises par la Métropole",
     "https://www.automobile-propre.com/articles/nice-bornes-recharge-ex-mobilize-share-reseau-public/"),
    ("Auto Bleue", "Venap (Veolia-Transdev / EDF), délégation de service public", "autopartage électrique, boucle + aller simple", "arrêté le 31/12/2018", 0, "presse",
     "~210 véhicules, 66-68 stations, 8 100 adhérents (2015)", "https://fr.wikipedia.org/wiki/Auto_Bleue"),
    ("Lime", "Lime", "vélos et trottinettes électriques en free-floating", "actif",
     int(fleet.get("Lime", 0)), "relevé GBFS", "Nice et 6 communes de la CASA (Antibes, Biot, Valbonne, Vallauris, Opio, Villeneuve-Loubet)",
     "https://www.agglo-sophiaantipolis.fr/vivre-et-habiter/se-deplacer/le-velo/votre-service-de-location-de-velo-en-libre-service"),
    ("Pony", "Pony", "vélos et trottinettes en free-floating", "actif", int(fleet.get("Pony", 0)), "relevé GBFS", "Nice, CASA", ""),
    ("Yego", "Yego Urban Mobility", "scooters électriques en free-floating", "actif", int(fleet.get("Yego", 0)), "relevé GBFS", "Nice", ""),
    ("Dott", "Dott", "vélos et trottinettes en free-floating", "à vérifier", int(fleet.get("Dott", 0)), "relevé GBFS (flux national)",
     "0 véhicule = absent du 06 au moment du relevé", ""),
    ("Label autopartage CASA", "Communauté d'agglomération Sophia Antipolis", "appel à opérateurs (véhicules électriques, dès 18 ans)", "ouvert, aucun opérateur nommé", 0, "site de la CASA",
     "Opportunité : territoire sans autopartage, label prêt", "https://www.agglo-sophiaantipolis.fr/vivre-et-habiter/se-deplacer/autopartage"),
    ("Free2Move", "Stellantis (cession à Mutares annoncée en 2026)", "autopartage free-floating", "non présent / retrait du secteur", 0, "presse",
     "Stellantis abandonne l'autopartage (2026)", "https://www.avem.fr/2026/08/01/stellantis-cede-sa-participation-dans-free2move-et-abandonne-lautopartage/"),
    ("Zity", "Renault", "autopartage free-floating", "non présent / arrêté", 0, "presse", "Renault quitte l'autopartage (déc. 2025)",
     "https://www.largus.fr/pros/actualite-automobile/groupe-renault-clap-de-fin-pour-mobilize-beyond-automotive-l-autopartage-et-les-quadricycles-30044789.html"),
]
ops = pd.DataFrame(OPS, columns=["operateur", "groupe", "modele", "statut", "vehicules_releves_06", "source_flotte", "precision", "url"])
ops["date_releve"] = NOW
ops.to_csv(OUT / "concurrents_operateurs.csv", index=False)

# =============================================================== 3. Transports en commun
stops = pd.read_csv(CLEAN / "model" / "transport_stops.csv.gz")
stops = locate(stops[stops.lat.between(43.4, 44.4) & stops.lon.between(6.6, 7.8)])
stops[["nom", "mode", "reseau", "lat", "lon", "commune_code", "commune_nom", "n_sources"]].to_csv(OUT / "arrets_transport.csv", index=False)
log(f"- Arrêts de transport en commun dans le 06 : {len(stops):,} (dont {int((stops['mode'] == 'train').sum())} ferroviaires)")

# =============================================================== 4. Population et activité par commune
cd = pd.read_csv(CLEAN / "communes_demo.csv", dtype={"code": str}).set_index("code")
com = pd.DataFrame([{**{k: f["properties"].get(k) for k in ("code", "nom", "codeEpci", "surface")},
                     "codes_postaux": " ".join(f["properties"].get("codesPostaux", [])),
                     "lat_centre": round(shp.representative_point().y, 5), "lon_centre": round(shp.representative_point().x, 5)}
                    for f, shp in zip(feats, shapes)]).set_index("code")
com["epci"] = com.codeEpci.map(epci_names)
com["surface_km2"] = com.surface / 100
for c in ["pop", "p0_17", "p18_26", "p27_34", "p35_44", "p45_54", "p55_64", "p65_plus", "p25_44", "menages",
          "sans_voiture", "part_locataires", "part_appart"]:
    com[c] = cd[c].reindex(com.index)
com["densite_hab_km2"] = com["pop"] / com.surface_km2
com["menages_sans_voiture"] = com.menages * com.sans_voiture

with zipfile.ZipFile(DL / "emploi_2022" / "emploi_2022.zip") as z:
    em = pd.read_csv(z.open("base-cc-emploi-pop-active-2022.CSV"), sep=";", dtype={"CODGEO": str},
                     usecols=["CODGEO", "P22_EMPLT", "P22_ACT1564", "P22_ACTOCC1564", "P22_CHOM1564", "P22_ETUD1564", "P22_RETR1564"])
em = em.set_index("CODGEO").reindex(com.index)
com["emplois_au_lieu_de_travail"] = em.P22_EMPLT
com["actifs_occupes_15_64"] = em.P22_ACTOCC1564
com["chomeurs_15_64"] = em.P22_CHOM1564
com["etudiants_15_64"] = em.P22_ETUD1564
com["retraites_15_64"] = em.P22_RETR1564
com["ratio_emplois_actifs"] = com.emplois_au_lieu_de_travail / com.actifs_occupes_15_64   # >1 : pôle d'emploi

with zipfile.ZipFile(DL / "tourisme_2025" / "tourisme_2025.zip") as z:
    tr = pd.read_csv(z.open("DS_TOUR_CAP_2025_data.csv"), sep=";", dtype={"GEO": str})
tr = tr[(tr.GEO_OBJECT == "COM") & (tr.UNIT_LOC_RANKING == "_T") & (tr.L_STAY == "_T")]
cap = tr.pivot_table(index="GEO", columns=["ACTIVITY", "TOUR_MEASURE"], values="OBS_VALUE", aggfunc="sum")
pick = lambda a, m: cap[(a, m)].reindex(com.index) if (a, m) in cap.columns else pd.Series(np.nan, index=com.index)
com["chambres_hotels"] = pick("I551", "PLACE")
com["lits_hebergements_collectifs"] = pick("I552", "BEDPLACE")          # résidences de tourisme, villages vacances, auberges
com["emplacements_campings"] = pick("I553", "PLACE")
# convention de l'INSEE pour les lits touristiques : 2 lits par chambre d'hôtel, 3 par emplacement de camping
com["lits_touristiques_marchands"] = (2 * com.chambres_hotels.fillna(0) + com.lits_hebergements_collectifs.fillna(0)
                                      + 3 * com.emplacements_campings.fillna(0))

with zipfile.ZipFile(DL / "logement_2022.zip") as z:
    member = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.lower().startswith("meta")][0]
    lg = pd.read_csv(z.open(member), sep=";", dtype={"CODGEO": str}, usecols=["CODGEO", "P22_LOG", "P22_RSECOCC"])
lg = lg.set_index("CODGEO").reindex(com.index)
com["part_residences_secondaires"] = lg.P22_RSECOCC / lg.P22_LOG
com["residences_secondaires"] = lg.P22_RSECOCC
# lits touristiques par habitant : marchands + 5 lits par résidence secondaire (convention des comptes du tourisme)
com["lits_touristiques_par_habitant"] = (com.lits_touristiques_marchands + 5 * lg.P22_RSECOCC.fillna(0)) / com["pop"]

# offre de mobilité par commune
agg = veh.groupby(["commune_code", "operateur"]).size().unstack(fill_value=0).add_prefix("veh_")
com = com.join(agg).fillna({c: 0 for c in agg.columns})
com["zones_free_floating"] = stations[stations.categorie == "zone de stationnement free-floating"].groupby("commune_code").size().reindex(com.index).fillna(0)
com["arrets_tc"] = stops.groupby("commune_code").size().reindex(com.index).fillna(0)
com["gares"] = stops[stops["mode"] == "train"].groupby("commune_code").size().reindex(com.index).fillna(0)
com["stations_velos"] = stations[stations.categorie == "vélos en libre-service (station)"].groupby("commune_code").size().reindex(com.index).fillna(0)
com["citiz_vehicules"] = cit.groupby("commune_code").n_vehicles.sum().reindex(com.index).fillna(0) if len(cit) else 0
if "veh_Getaround" in com:
    com["getaround_pour_10000_hab"] = 1e4 * com.veh_Getaround / com["pop"]
com = com.drop(columns=["codeEpci", "surface"]).reset_index().sort_values("pop", ascending=False)
com.round(4).to_csv(OUT / "communes_cote_azur.csv", index=False)
log(f"- Communes : {len(com)} lignes, {com['pop'].sum():,.0f} habitants, {com.emplois_au_lieu_de_travail.sum():,.0f} emplois")

# =============================================================== 5. Population au carreau de 200 m (Filosofi 2021)
from pyproj import Transformer
to4326 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
cols = ["idcar_200m", "i_est_200", "lcog_geo", "ind", "men", "men_pauv", "men_prop", "men_coll", "ind_snv", "log_soc",
        "ind_0_3", "ind_4_5", "ind_6_10", "ind_11_17", "ind_18_24", "ind_25_39", "ind_40_54", "ind_55_64", "ind_65_79", "ind_80p"]
parts = []
with zipfile.ZipFile(DL / "carreaux_2021" / "carreaux_200m_2021.zip") as z:
    for ch in pd.read_csv(z.open("carreaux_200m_met.csv"), usecols=cols, dtype={"lcog_geo": str}, chunksize=400_000):
        parts.append(ch[ch.lcog_geo.str.startswith(DEP)])
car = pd.concat(parts, ignore_index=True)
xy = car.idcar_200m.str.extract(r"N(\d+)E(\d+)").astype(int)
lon, lat = to4326.transform((xy[1] + 100).values, (xy[0] + 100).values)
car["lat"], car["lon"] = np.round(lat, 5), np.round(lon, 5)
car["commune_code"] = car.lcog_geo.str[:5]
car["commune_nom"] = car.commune_code.map(names)
car["ind_0_17"] = car[["ind_0_3", "ind_4_5", "ind_6_10", "ind_11_17"]].sum(axis=1)
car["ind_65_plus"] = car.ind_65_79 + car.ind_80p
car["niveau_vie_moyen"] = (car.ind_snv / car.ind.replace(0, np.nan)).round(0)
car = car.drop(columns=["ind_0_3", "ind_4_5", "ind_6_10", "ind_11_17", "ind_65_79", "ind_80p", "ind_snv", "lcog_geo"])
car.to_csv(OUT / "carreaux_200m_cote_azur.csv", index=False)
log(f"- Carreaux de 200 m : {len(car):,} carreaux habités, {car.ind.sum():,.0f} habitants (Filosofi 2021)")

(OUT / "RAPPORT_COLLECTE.md").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\nTerminé :", ", ".join(sorted(p.name for p in OUT.iterdir())))
