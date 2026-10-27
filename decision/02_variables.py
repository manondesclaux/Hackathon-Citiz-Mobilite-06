"""Étape 2 — Mêmes variables pour les stations Citiz existantes (apprentissage) et les candidats du 06 (prédiction).

Candidats : centre de chaque carreau habité de 200 m des Alpes-Maritimes (Filosofi 2021). Ce sont des secteurs à
étudier, pas des places de stationnement disponibles.
Sorties : decision/donnees/variables_stations.csv, decision/donnees/candidats_06.csv.gz
"""
import pandas as pd

from communs import DEP, DONNEES, arrets, carreaux, logement_communes, motorisation_communes, to4326, variables, velos

car, stops, vls, mot, rs = carreaux(), arrets(), velos(), motorisation_communes(), logement_communes()
ctx = dict(car=car, stops=stops, vls=vls, mot=mot, rs=rs)
print(f"{len(car):,} carreaux | {len(stops):,} arrêts | VLS : {(vls.type_station == 'VLS').sum():,} vraies stations, "
      f"{(vls.type_station != 'VLS').sum():,} zones free-floating écartées")

u = pd.read_csv(DONNEES / "usage_stations.csv")
st = u.join(variables(u, **ctx))
st.to_csv(DONNEES / "variables_stations.csv", index=False)
print(f"Stations avec variables : {len(st)} (population à 400 m nulle : {(st.pop_400m == 0).sum()})")

c = car[car.code_commune.str.startswith(DEP)].copy()
c["lon"], c["lat"] = to4326.transform(c.x.values, c.y.values)
c = c[["idcar_200m", "lat", "lon", "x", "y", "ind", "men", "men_pauv", "i_est_200", "code_commune"]].rename(
    columns={"ind": "pop_carreau", "men": "men_carreau", "men_pauv": "men_pauv_carreau", "code_commune": "commune_carreau"})
c = c.reset_index(drop=True)
c = c.join(variables(c, **ctx))
noms = pd.read_csv(DONNEES.parent.parent / "donnees" / "cote_azur" / "communes_cote_azur.csv", dtype={"code": str})
c["commune"] = c.commune_carreau.map(noms.set_index("code").nom)
c.round(5).to_csv(DONNEES / "candidats_06.csv.gz", index=False)
print(f"Candidats 06 : {len(c):,} carreaux, {c.pop_carreau.sum():,.0f} habitants")
for col in ["part_sans_voiture_commune", "part_res_secondaires_commune"]:
    print(f"  valeurs manquantes {col} : stations {st[col].isna().mean():.1%}, candidats {c[col].isna().mean():.1%}")
