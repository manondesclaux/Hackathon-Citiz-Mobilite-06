"""Ménages par catégorie socioprofessionnelle de la personne de référence et nombre de voitures (INSEE).

Source : INSEE, Résidences principales en 2021, tableaux détaillés, table PRINC18
https://www.insee.fr/fr/statistiques/8202355  (TD_PRINC18_2021 : type de logement x CSP x nombre de voitures)

Permet de savoir QUI sont les ménages sans voiture (actifs, retraités, autres inactifs dont étudiants).
Produit : data/raw/insee/menages_csp_voiture_2021.csv (villes du Sud + villes de référence Citiz)
Usage : python3 -I scripts/extract_menages_csp.py
"""
import csv
import io
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DL = ROOT / "data" / "raw" / "insee_download"
OUT = ROOT / "data" / "raw" / "insee" / "menages_csp_voiture_2021.csv"
URL = "https://www.insee.fr/fr/statistiques/fichier/8202355/TD_PRINC18_2021_csv.zip"

VILLES = {"13055": "Marseille", "06088": "Nice", "34172": "Montpellier", "31555": "Toulouse", "33063": "Bordeaux",
          "83137": "Toulon", "30189": "Nîmes", "66136": "Perpignan", "13001": "Aix-en-Provence", "84007": "Avignon",
          "34032": "Béziers", "67482": "Strasbourg", "38185": "Grenoble", "69123": "Lyon"}

DL.mkdir(parents=True, exist_ok=True)
zip_path = DL / "princ18_2021.zip"
if not zip_path.exists():
    urllib.request.urlretrieve(URL, zip_path)

with zipfile.ZipFile(zip_path) as z, open(OUT, "w", newline="", encoding="utf-8") as f:
    member = [n for n in z.namelist() if n.lower().endswith(".csv") and "meta" not in n.lower()][0]
    w = csv.writer(f)
    w.writerow(["ville", "CODGEO", "CS1_8", "TYPLR", "VOIT", "NB"])
    n = 0
    with z.open(member) as raw:
        for r in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter=";"):
            if r["NIVGEO"] == "COM" and r["CODGEO"] in VILLES:
                w.writerow([VILLES[r["CODGEO"]], r["CODGEO"], r["CS1_8"], r["TYPLR"], r["VOIT"], r["NB"]])
                n += 1
print(f"{n} lignes écrites dans {OUT}")
