"""Population par âge (année par année) des grandes villes du sud et de leur périphérie — INSEE, recensement 2023.

Source : INSEE, « Population en 2023 — Base des tableaux détaillés », fichier
DS_RP_TD_POPULATION_AGESEX_PRINC_2023 (population par âge détaillé et sexe, toutes géographies).
https://www.insee.fr/fr/statistiques/9006235

Le fichier d'origine pèse 73 Mo (650 Mo décompressé). On le lit en flux et on ne garde que les lignes utiles
(sexes confondus, 11 villes x 3 niveaux géographiques) dans data/raw/insee/pop_age_sud_2023.csv.

Usage : python3 -I scripts/collect_insee.py
"""
import csv
import io
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DL_DIR = ROOT / "data" / "raw" / "insee_download"   # dossier dédié aux téléchargements externes
OUT = ROOT / "data" / "raw" / "insee" / "pop_age_sud_2023.csv"
URL = "https://www.insee.fr/fr/statistiques/fichier/9006235/DS_RP_TD_POPULATION_AGESEX_PRINC_2023_CSV_FR.zip"
MEMBER = "DS_RP_TD_POPULATION_AGESEX_PRINC_2023_data.csv"

# ville -> (code commune, code EPCI de la métropole/agglo, code aire d'attraction 2020)
VILLES = {
    "Marseille":       ("13055", "200054807", "003"),
    "Nice":            ("06088", "200030195", "017"),
    "Montpellier":     ("34172", "243400017", "012"),
    "Toulouse":        ("31555", "243100518", "005"),
    "Bordeaux":        ("33063", "243300316", "006"),
    "Toulon":          ("83137", "248300543", "018"),
    "Nîmes":           ("30189", "243000643", "037"),
    "Perpignan":       ("66136", "200027183", "030"),
    "Aix-en-Provence": ("13001", None,        "003"),   # même métropole et même aire que Marseille
    "Avignon":         ("84007", "248400251", "040"),
    "Béziers":         ("34032", "243400769", "060"),
}

wanted = {}  # (type géographique, code) -> [(ville, niveau), ...]
for ville, (com, epci, aav) in VILLES.items():
    wanted.setdefault(("COM", com), []).append((ville, "commune"))
    if epci:
        wanted.setdefault(("EPCI", epci), []).append((ville, "metropole"))
    wanted.setdefault(("AAV2020", aav), []).append((ville, "aire_attraction"))  # Aix et Marseille partagent l'aire 003

DL_DIR.mkdir(parents=True, exist_ok=True)
zip_path = DL_DIR / "agesex_2023.zip"
if not zip_path.exists():
    print("Téléchargement INSEE (73 Mo)…", flush=True)
    urllib.request.urlretrieve(URL, zip_path)

OUT.parent.mkdir(parents=True, exist_ok=True)
n = 0
with zipfile.ZipFile(zip_path) as z, z.open(MEMBER) as raw, open(OUT, "w", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter=";")
    w = csv.writer(f)
    w.writerow(["ville", "niveau", "geo_type", "geo_code", "age", "population"])
    for row in reader:
        if row["SEX"] != "_T":
            continue
        for ville, niveau in wanted.get((row["GEO_OBJECT"], row["GEO"]), []):
            w.writerow([ville, niveau, row["GEO_OBJECT"], row["GEO"], row["AGE"], row["OBS_VALUE"]])
            n += 1
print(f"{n} lignes écrites dans {OUT}")
