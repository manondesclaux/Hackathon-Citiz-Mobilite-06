"""Étape 5 — Objectifs 1 et 2 du sujet sur les Alpes-Maritimes.

Objectif 1 : pour chaque carreau habité de 200 m, options de mobilité joignables à 5 minutes de marche (400 m) et
options pour 1 000 habitants. Une « option » est un point d'accès distinct :
- pôle d'arrêt de transport en commun desservi le jour type (GTFS, étape 0) ;
- station de vélos en libre-service (aucune dans le 06 au relevé : Vélo Bleu n'existe plus, seules des zones
  free-floating sont publiées) ;
- zone de stationnement free-floating (Lime, Pony) et véhicule partagé observé (Getaround, scooters Yego) ;
- station d'autopartage (Citiz, Clem' : aucune dans le 06 au relevé).
Le niveau de service TC est mesuré séparément en passages par jour à 400 m, car un pôle à 2 bus par jour n'est pas
une vraie option.
Les carreaux dont la population à 400 m est inférieure à 200 habitants n'ont pas de ratio par habitant (instable).

Objectif 2 : pour chaque point d'accès, population résidente à 400 m (habitants « desservis »).

Sorties : decision/donnees/acces_carreaux_06.csv.gz, decision/resultats/population_par_point_acces_06.csv,
          decision/resultats/acces_communes_06.csv, decision/resultats/equite_acces_06.json
"""
import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from communs import CLEAN, DONNEES, R_REQ, RESULTATS, xy

c = pd.read_csv(DONNEES / "candidats_06.csv.gz", dtype={"commune_carreau": str})
C = c[["x", "y"]].to_numpy()
tree = cKDTree(C)

poles = pd.read_csv(DONNEES / "poles_arrets_06.csv")
poles = poles[poles.departs > 0].copy()
poles["type"] = np.where(poles.train, "gare", "arrêt bus / tram")
veh = pd.read_csv(CLEAN / "cote_azur" / "concurrents_vehicules.csv")
zones = pd.read_csv(CLEAN / "cote_azur" / "concurrents_stations.csv")
ff = zones[zones.categorie.str.contains("free-floating")].assign(type="zone free-floating")
vls = zones[zones.categorie.str.contains("vélos en libre-service")].assign(type="station VLS")
autop = zones[zones.categorie.str.contains("autopartage")].assign(type="station autopartage")
ga = veh[veh.operateur == "Getaround"].assign(type="voiture Getaround", nom="Getaround")
scoot = veh[veh.type_vehicule == "moped"].assign(type="scooter partagé", nom=veh.operateur)

points = pd.concat([poles.assign(nom=poles.nom)[["nom", "lat", "lon", "type", "departs", "reseaux"]],
                    ff[["nom", "lat", "lon", "type"]].assign(reseaux=ff.operateur),
                    vls[["nom", "lat", "lon", "type"]].assign(reseaux=vls.operateur),
                    autop[["nom", "lat", "lon", "type"]].assign(reseaux=autop.operateur),
                    ga[["nom", "lat", "lon", "type"]].assign(reseaux="Getaround"),
                    scoot[["nom", "lat", "lon", "type"]].assign(reseaux=scoot.operateur)], ignore_index=True)
P = xy(points.lon, points.lat)
points["x"], points["y"] = P[:, 0], P[:, 1]

# ---------- Objectif 1 : options à 400 m par carreau
ptree = cKDTree(P)
voisins = ptree.query_ball_point(C, r=R_REQ)
types = points.type.to_numpy()
dep = points.departs.fillna(0).to_numpy()
for t in ["arrêt bus / tram", "gare", "zone free-floating", "station VLS", "station autopartage", "voiture Getaround", "scooter partagé"]:
    c[f"n_{t}"] = [int((types[i] == t).sum()) for i in voisins]
c["options_400m"] = [len(i) for i in voisins]
c["passages_tc_jour_400m"] = [dep[i].sum() for i in voisins]
c["options_pour_1000_hab"] = np.where(c.pop_400m >= 200, 1000 * c.options_400m / c.pop_400m.clip(lower=1), np.nan)
# niveau de service TC : pas d'arrêt / faible (< 60 passages, < 4 par heure) / correct / fort (>= 240 : tram, axes)
c["service_tc"] = pd.cut(c.passages_tc_jour_400m, [-1, 0, 59, 239, 1e9], labels=["aucun", "faible", "correct", "fort"])
c["classe_acces"] = pd.qcut(c.options_pour_1000_hab, 5, labels=["1 très faible", "2 faible", "3 moyen", "4 bon", "5 très bon"])
c.to_csv(DONNEES / "acces_carreaux_06.csv.gz", index=False)

# ---------- Objectif 2 : population desservie par chaque point d'accès
pop = c.pop_carreau.to_numpy()
desservis = tree.query_ball_point(P, r=R_REQ)
points["habitants_400m"] = [round(float(pop[i].sum())) for i in desservis]
points.drop(columns=["x", "y"]).to_csv(RESULTATS / "population_par_point_acces_06.csv", index=False)
print(points.groupby("type").agg(points=("nom", "size"), habitants_moyens=("habitants_400m", "mean"),
                                 habitants_max=("habitants_400m", "max")).round(0).to_string())

# ---------- Synthèse par commune et équité
com = c.groupby("commune").apply(lambda d: pd.Series({
    "habitants": d.pop_carreau.sum(),
    "part_sans_tc_400m": np.average(d.passages_tc_jour_400m == 0, weights=d.pop_carreau),
    "part_tc_correct_ou_fort": np.average(d.service_tc.isin(["correct", "fort"]), weights=d.pop_carreau),
    "options_400m_moyennes": np.average(d.options_400m, weights=d.pop_carreau)}), include_groups=False)
com = com.sort_values("habitants", ascending=False).round(3)
com.to_csv(RESULTATS / "acces_communes_06.csv")

# quintiles d'habitants (chaque classe ≈ 20 % de la population), d'après le niveau de vie moyen à 400 m
o = c.niveau_vie_k.fillna(c.niveau_vie_k.median()).sort_values().index
part_cumulee = c.loc[o, "pop_carreau"].cumsum() / c.pop_carreau.sum()
c["quintile_niveau_vie"] = pd.cut(part_cumulee, [-1, .2, .4, .6, .8, 1.01], labels=["Q1 modestes", "Q2", "Q3", "Q4", "Q5 aisés"]).reindex(c.index)
eq = c.groupby("quintile_niveau_vie", observed=True).apply(lambda d: pd.Series({
    "habitants": round(float(d.pop_carreau.sum())),
    "part_tc_correct_ou_fort": round(float(np.average(d.service_tc.isin(["correct", "fort"]), weights=d.pop_carreau)), 3),
    "options_400m_moyennes": round(float(np.average(d.options_400m, weights=d.pop_carreau)), 1)}), include_groups=False)
dense = c.pop_400m >= 3000
eq_dense = {"part_population_zones_denses": round(float(c.loc[dense, "pop_carreau"].sum() / c.pop_carreau.sum()), 3),
            "tc_correct_ou_fort_denses": round(float(np.average(c.loc[dense].service_tc.isin(["correct", "fort"]), weights=c.loc[dense].pop_carreau)), 3),
            "tc_correct_ou_fort_peu_denses": round(float(np.average(c.loc[~dense].service_tc.isin(["correct", "fort"]), weights=c.loc[~dense].pop_carreau)), 3)}
sortie = {"habitants_06": round(float(c.pop_carreau.sum())),
          "part_habitants_sans_arret_tc_400m": round(float(np.average(c.passages_tc_jour_400m == 0, weights=c.pop_carreau)), 3),
          "part_habitants_tc_correct_ou_fort": round(float(np.average(c.service_tc.isin(["correct", "fort"]), weights=c.pop_carreau)), 3),
          "par_quintile_de_niveau_de_vie": eq.to_dict(orient="index"), "dense_vs_peu_dense": eq_dense}
(RESULTATS / "equite_acces_06.json").write_text(json.dumps(sortie, ensure_ascii=False, indent=2))
print(json.dumps(sortie, ensure_ascii=False, indent=2))
print(com.head(12).to_string())
