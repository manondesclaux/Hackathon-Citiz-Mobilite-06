"""Base nationale des communes : population par tranche d'âge + motorisation + logement (INSEE).

Sources :
- INSEE, Population en 2023, tableaux détaillés, âge détaillé x sexe
  https://www.insee.fr/fr/statistiques/9006235  (DS_RP_TD_POPULATION_AGESEX_PRINC_2023)
- INSEE, Logement en 2022, base communale (voitures du ménage, type de logement, statut d'occupation)
  https://www.insee.fr/fr/statistiques/8581474  (base-cc-logement-2022)

Produit : donnees/communes_demo.csv  (une ligne par commune, toutes les communes de France)
Usage : python3 -I collecte/prepare_communes.py
"""
import csv
import io
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DL = ROOT / "data" / "raw" / "insee_download"          # dossier dédié aux téléchargements externes
OUT = ROOT / "donnees" / "communes_demo.csv"
AGE_URL = "https://www.insee.fr/fr/statistiques/fichier/9006235/DS_RP_TD_POPULATION_AGESEX_PRINC_2023_CSV_FR.zip"
LOG_URL = "https://www.insee.fr/fr/statistiques/fichier/8581474/base-cc-logement-2022_csv.zip"

DL.mkdir(parents=True, exist_ok=True)
for url, name in [(AGE_URL, "agesex_2023.zip"), (LOG_URL, "logement_2022.zip")]:
    if not (DL / name).exists():
        print(f"Téléchargement {name}…", flush=True)
        urllib.request.urlretrieve(url, DL / name)

BINS = {"p0_17": (0, 17), "p18_26": (18, 26), "p27_34": (27, 34), "p35_44": (35, 44), "p45_54": (45, 54),
        "p55_64": (55, 64), "p65_plus": (65, 200),
        # tranches de lecture (se recoupent avec les précédentes) : cible évoquée, cœur observé en autopartage en boucle
        "p25_44": (25, 44), "p35_54": (35, 54), "p40_50": (40, 50)}
acc = defaultdict(lambda: defaultdict(float))
names = {}

with zipfile.ZipFile(DL / "agesex_2023.zip") as z:
    meta = [n for n in z.namelist() if n.endswith("_metadata.csv")][0]
    data = [n for n in z.namelist() if n.endswith("_data.csv")][0]
    with z.open(meta) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter=";"):
            if r["COD_VAR"] == "GEO" and r["GEO_OBJECT"] == "COM":
                names[r["COD_MOD"]] = r["LIB_MOD"]
    with z.open(data) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter=";"):
            if r["GEO_OBJECT"] != "COM" or r["SEX"] != "_T":
                continue
            a, v, g = r["AGE"], float(r["OBS_VALUE"]), r["GEO"]
            if a == "_T":
                acc[g]["pop"] = v
                continue
            n = 100 if a == "Y_GE100" else int(a[1:])
            for k, (lo, hi) in BINS.items():
                if lo <= n <= hi:
                    acc[g][k] += v

log = {}
with zipfile.ZipFile(DL / "logement_2022.zip") as z:
    member = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.lower().startswith("meta")][0]
    with z.open(member) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter=";"):
            try:
                rp, v1p = float(r["P22_RP"]), float(r["P22_RP_VOIT1P"])
                log[r["CODGEO"]] = {
                    "menages": rp,
                    "sans_voiture": (1 - v1p / rp) if rp > 0 else None,
                    "part_appart": (float(r["P22_APPART"]) / float(r["P22_LOG"])) if float(r["P22_LOG"]) > 0 else None,
                    "part_locataires": (float(r["P22_RP_LOC"]) / rp) if rp > 0 else None,
                }
            except (KeyError, ValueError):
                continue

OUT.parent.mkdir(parents=True, exist_ok=True)
cols = ["code", "nom", "pop"] + list(BINS) + [
        "menages", "sans_voiture", "part_appart", "part_locataires"]
n = 0
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(cols)
    for code, d in sorted(acc.items()):
        if d["pop"] <= 0:
            continue
        l = log.get(code, {})
        w.writerow([code, names.get(code, ""), round(d["pop"], 1)] +
                   [round(d[k], 1) for k in BINS] +
                   [l.get("menages"), l.get("sans_voiture"), l.get("part_appart"), l.get("part_locataires")])
        n += 1
print(f"{n} communes écrites dans {OUT}")
