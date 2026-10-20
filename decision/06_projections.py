"""Étape 6 — Projections démographiques des Alpes-Maritimes (INSEE Omphale 2022).

Ce que l'on en tire : l'évolution de la population totale et de la tranche 25-54 ans (cœur de la clientèle de
l'autopartage) entre la population de référence de Filosofi (2021) et 2030 / 2035 / 2040.
La structure par âge n'est publiée que pour 2018 et 2070 : elle est interpolée linéairement entre les deux.
Ces facteurs sont départementaux : ils changent les volumes (habitants desservis demain), pas le classement des
sites à l'intérieur du 06. Ils servent à vérifier que le marché ne disparaît pas avec le vieillissement.

Entrée : data/raw/omphale/projections_scenario_*.xlsx (téléchargées automatiquement si absentes)
Sortie : decision/resultats/projections_06.csv
"""
import json

import pandas as pd
import requests

from communs import DEC, DEP, RESULTATS, ROOT

P = json.loads((DEC / "parametres.json").read_text())["projections"]
DOSSIER = ROOT / "data" / "raw" / "omphale"
DOSSIER.mkdir(parents=True, exist_ok=True)
URL = "https://www.insee.fr/fr/statistiques/fichier/6652134/projections_scenario_{}.xlsx"
TRANCHES_25_54 = ["[25,30)", "[30,35)", "[35,40)", "[40,45)", "[45,50)", "[50,55)"]

lignes = []
for scen in ["central", "population_basse", "population_haute"]:
    f = DOSSIER / f"projections_scenario_{scen}.xlsx"
    if not f.exists():
        f.write_bytes(requests.get(URL.format(scen), timeout=120, headers={"User-Agent": "Mozilla/5.0"}).content)
    pop = pd.read_excel(f, "Population_DEP", header=5, dtype={"DEP": str}).set_index("DEP").loc[DEP]
    age = pd.read_excel(f, "Structure_Age_DEP", header=5, dtype={"DEP": str}).set_index("DEP").loc[DEP]
    p18, p70 = sum(age[f"{t}_2018"] for t in TRANCHES_25_54), sum(age[f"{t}_2070"] for t in TRANCHES_25_54)
    part = lambda an: (p18 + (p70 - p18) * (an - 2018) / (2070 - 2018)) / 100
    ref = pop["POP_2021"] * part(2021)
    for an in P["horizons"]:
        lignes.append({"scenario": scen, "annee": an, "population_milliers": pop[f"POP_{an}"],
                       "evolution_population_vs_2021_pct": round(100 * (pop[f"POP_{an}"] / pop["POP_2021"] - 1), 1),
                       "part_25_54_pct": round(100 * part(an), 1),
                       "facteur_25_54_vs_2021": round(pop[f"POP_{an}"] * part(an) / ref, 3)})
t = pd.DataFrame(lignes)
t.to_csv(RESULTATS / "projections_06.csv", index=False)
print(t.to_string(index=False))
