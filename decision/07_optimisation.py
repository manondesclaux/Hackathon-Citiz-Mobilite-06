"""Étape 7 — Liste priorisée d'emplacements sous contrainte de budget, pour trois équipements et trois payeurs.

1. Stations Citiz (payeur : Citiz). Valeur d'un site = habitants NOUVELLEMENT desservis à 400 m (jamais comptés deux
   fois) × potentiel d'implantation (modèle validé de l'étape 4). Coût = installation + véhicules la 1re année.
   Contraintes : budget, 800 m entre deux stations, plafond par commune (scripts/plafonds_communes.py), quota
   d'équité (part minimale de stations dans les quartiers modestes), population à 400 m >= 1 500.
   Pour chaque site : occupation attendue (avec intervalle), recettes, résultat d'exploitation, CO2 évité.
2. Arrêts de bus (payeur : autorité organisatrice). Trous de desserte sur le réseau existant : carreaux entre 400 et
   800 m d'un arrêt actif. Valeur = habitants sans arrêt actif à 400 m qui en gagnent un.
3. Stations de vélos en libre-service (payeur : collectivité). Près des pôles de transport les plus desservis
   (rabattement), en réseau (chaque station à moins de 1,5 km d'une autre, sinon une station isolée ne sert pas).

Méthode : glouton sur le ratio « valeur marginale / coût », recalculé à chaque choix (la valeur est sous-modulaire :
un habitant déjà desservi ne compte plus). Ce n'est pas un optimum garanti, mais la garantie classique du glouton
pour la couverture maximale sous budget s'applique approximativement, et le résultat reste explicable ligne à ligne.

Sorties (decision/resultats/) : stations_citiz_recommandees.csv, arrets_bus_recommandes.csv,
stations_velo_recommandees.csv, sensibilite_citiz.csv, synthese_decision.json
"""
import json
import math

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from communs import DEC, DONNEES, R_REQ, RAYON, RESULTATS, ROOT, xy

PAR = json.loads((DEC / "parametres.json").read_text())
c = pd.read_csv(DONNEES / "candidats_06_scores.csv.gz", dtype={"code_commune": str, "commune_carreau": str})
acc = pd.read_csv(DONNEES / "acces_carreaux_06.csv.gz", usecols=["idcar_200m", "passages_tc_jour_400m", "n_voiture Getaround"])
c = c.merge(acc, on="idcar_200m", how="left")
C = c[["x", "y"]].to_numpy()
tree = cKDTree(C)
couv = tree.query_ball_point(C, r=R_REQ)                   # carreaux desservis par un site placé au centre de chaque carreau
pop = c.pop_carreau.to_numpy()

# quintiles d'habitants selon le niveau de vie du quartier (400 m) : Q1-Q2 = 40 % des habitants les plus modestes
o = c.niveau_vie_k.fillna(c.niveau_vie_k.median()).sort_values().index
cum = c.loc[o, "pop_carreau"].cumsum() / pop.sum()
c["quartier_modeste"] = (cum <= 0.4).reindex(c.index)

poles = pd.read_csv(DONNEES / "poles_arrets_06.csv")
pa = poles[poles.departs > 0]
P_actif = xy(pa.lon, pa.lat)
c["dist_pole_actif_m"] = cKDTree(P_actif).query(C)[0]
pf = poles[poles.departs >= 240]
c["dist_pole_fort_m"] = cKDTree(xy(pf.lon, pf.lat)).query(C)[0]

plaf = pd.read_csv(ROOT / "sorties" / "plafonds_communes.csv", dtype={"code_commune": str}).set_index("code_commune").plafond
c["plafond_commune"] = c.commune_carreau.map(plaf).fillna(2).astype(int)

u = pd.read_csv(DONNEES / "usage_stations.csv")
OCC_MOY = float(np.average(u.occupation_jour, weights=u.vehicules))   # occupation moyenne du réseau Citiz


def glouton(cand, valeur_fn, cout, budget, sep, deja=None, plafond=None, quota=None, reseau_km=None):
    """Sélection gloutonne paresseuse : maximise valeur marginale / coût sous budget et contraintes."""
    deja = np.zeros(len(c), bool) if deja is None else deja.copy()
    choisis, depense, par_commune, n_quota = [], 0.0, {}, 0
    restant = set(cand)
    n_cible = None
    if quota:
        n_cible = max(1, int(budget // np.median(cout[list(cand)])))
    while restant:
        meilleur, best = None, -1.0
        besoin_quota = quota and (math.ceil(quota * n_cible) - n_quota) >= (n_cible - len(choisis))
        for i in restant:
            if depense + cout[i] > budget:
                continue
            if plafond is not None and par_commune.get(c.commune_carreau[i], 0) >= plafond[i]:
                continue
            if besoin_quota and not c.quartier_modeste[i]:
                continue
            if reseau_km and choisis and np.min(np.hypot(*(C[choisis] - C[i]).T)) > reseau_km * 1000:
                continue
            v = valeur_fn(i, deja)
            if v / cout[i] > best:
                meilleur, best = i, v / cout[i]
        if meilleur is None or best <= 0:
            break
        gain = pop[couv[meilleur]][~deja[couv[meilleur]]].sum()
        choisis.append(meilleur)
        depense += cout[meilleur]
        deja[couv[meilleur]] = True
        par_commune[c.commune_carreau[meilleur]] = par_commune.get(c.commune_carreau[meilleur], 0) + 1
        n_quota += bool(c.quartier_modeste[meilleur])
        for j in tree.query_ball_point(C[meilleur], r=sep):
            restant.discard(j)
        c.loc[meilleur, "_gain"] = gain
    return choisis, depense


# ============================================================== 1. Stations Citiz
pc = PAR["citiz"]


def scenario_citiz(budget=None, cout_niveau="centrale", poids_potentiel=1.0, quota=None, nom="référence"):
    budget = pc["budget_annee1_eur"]["centrale"] if budget is None else budget
    quota = pc["quota_equite_part_min"]["centrale"] if quota is None else quota
    veh = np.where(c.pop_400m >= 9000, 3, 2)
    cout = (pc["installation_station_eur"][cout_niveau]
            + veh * (pc["exploitation_vehicule_eur_an"][cout_niveau] + pc["stationnement_vehicule_eur_an"][cout_niveau]))
    pot = c.potentiel.to_numpy() ** poids_potentiel
    cand = np.flatnonzero((c.pop_400m >= pc["population_400m_min"]).to_numpy())
    valeur = lambda i, deja: pop[couv[i]][~deja[couv[i]]].sum() * pot[i]
    choisis, depense = glouton(cand, valeur, cout, budget, pc["espacement_min_m"], plafond=c.plafond_commune.to_numpy(),
                               quota=quota)
    s = c.loc[choisis].copy()
    s["habitants_nouveaux"] = c.loc[choisis, "_gain"].to_numpy()
    s["vehicules"] = veh[choisis]
    s["cout_annee1_eur"] = cout[choisis]
    return s, depense


ref, depense = scenario_citiz()
r = ref
r.insert(0, "rang", range(1, len(r) + 1))
r["vague"] = pd.cut(r.cout_annee1_eur.cumsum() / r.cout_annee1_eur.sum(), [0, 1 / 3, 2 / 3, 1.0001],
                    labels=["Vague 1", "Vague 2", "Vague 3"])
recette = pc["recette_vehicule_eur_an_a_occupation_moyenne"]["centrale"]
for k, col in [("bas", "occupation_bas"), ("centrale", "occupation_attendue"), ("haut", "occupation_haut")]:
    r[f"recettes_eur_an_{k}"] = (r.vehicules * recette * r[col] / OCC_MOY).round(-2)
charges = r.vehicules * (pc["exploitation_vehicule_eur_an"]["centrale"] + pc["stationnement_vehicule_eur_an"]["centrale"])
for k in ["bas", "centrale", "haut"]:
    r[f"resultat_eur_an_{k}"] = (r[f"recettes_eur_an_{k}"] - charges).round(-2)
pco = PAR["carbone"]
co2 = lambda n, a: n * pco["voitures_personnelles_remplacees_par_vehicule"][a] * pco["km_annuels_voiture_personnelle"]["centrale"] \
    * pco["part_km_voiture_evites"][a] * pco["facteur_emission_kgco2e_km"][a] / 1000
r["co2_evite_t_an_bas"] = co2(r.vehicules, "bas").round(1)
r["co2_evite_t_an_haut"] = co2(r.vehicules, "haut").round(1)
cols = ["rang", "vague", "commune", "arret_proche", "lat", "lon", "x", "y", "pop_400m", "habitants_nouveaux", "potentiel",
        "percentile_vs_stations_citiz", "occupation_bas", "occupation_attendue", "occupation_haut", "vehicules",
        "cout_annee1_eur", "recettes_eur_an_centrale", "resultat_eur_an_bas", "resultat_eur_an_centrale",
        "resultat_eur_an_haut", "co2_evite_t_an_bas", "co2_evite_t_an_haut", "quartier_modeste", "niveau_vie_k",
        "part_sans_voiture_commune", "part_res_secondaires_commune", "passages_tc_jour_400m", "n_voiture Getaround",
        "hors_domaine", "variables_hors_domaine", "part_pop_imputee"]
r[cols].round({"lat": 6, "lon": 6, "potentiel": 4, "occupation_bas": 3, "occupation_attendue": 3, "occupation_haut": 3,
               "niveau_vie_k": 2, "part_sans_voiture_commune": 4, "part_res_secondaires_commune": 4, "part_pop_imputee": 3,
               "percentile_vs_stations_citiz": 1}).to_csv(RESULTATS / "stations_citiz_recommandees.csv", index=False)
pd.set_option("display.width", 250)
print(r[["rang", "vague", "commune", "arret_proche", "pop_400m", "habitants_nouveaux", "potentiel", "occupation_attendue",
         "vehicules", "cout_annee1_eur", "resultat_eur_an_centrale", "quartier_modeste", "hors_domaine"]].round(3).to_string(index=False))

# ---- sensibilité : ce qui change quand on bouge une hypothèse
def proches(a, b, d=400):
    if len(a) == 0 or len(b) == 0:
        return 0
    return int((cKDTree(b[["x", "y"]].to_numpy()).query(a[["x", "y"]].to_numpy())[0] <= d).sum())


sens = []
for nom, kw in [("référence", {}), ("sans quota d'équité", {"quota": 0}), ("population seule (ancien score)", {"poids_potentiel": 0}),
                ("potentiel renforcé", {"poids_potentiel": 2}), ("budget 250 k€", {"budget": 250000}),
                ("budget 1 M€", {"budget": 1000000}), ("coûts bas", {"cout_niveau": "bas"}), ("coûts hauts", {"cout_niveau": "haut"})]:
    s, dep = scenario_citiz(**kw)
    sens.append({"scenario": nom, "stations": len(s), "vehicules": int(s.vehicules.sum()), "budget_utilise_eur": int(dep),
                 "habitants_nouveaux": int(s.habitants_nouveaux.sum()), "potentiel_moyen": round(float(s.potentiel.mean()), 3),
                 "part_quartiers_modestes": round(float(s.quartier_modeste.mean()), 2),
                 "communes": s.commune.nunique(), "sites_communs_avec_reference_400m": proches(s, ref)})
sens = pd.DataFrame(sens)
sens.to_csv(RESULTATS / "sensibilite_citiz.csv", index=False)
print("\n", sens.to_string(index=False))

# comparaison avec les anciennes listes de l'équipe
anciens = {}
for nom, f in [("vingt_stations_azur", ROOT / "sorties" / "vingt_stations_azur.csv"), ("citiz_azur_top10", ROOT / "citiz_azur" / "results" / "top10.csv")]:
    a = pd.read_csv(f)
    a[["x", "y"]] = xy(a.lon, a.lat)
    anciens[nom] = {"sites": len(a), "repris_a_moins_de_400m": proches(a, ref)}

# ============================================================== 2. Arrêts de bus
pb = PAR["arret_bus"]
sans_arret = (c.dist_pole_actif_m > RAYON).to_numpy()
cand_b = np.flatnonzero(((c.dist_pole_actif_m > pb["distance_arret_existant_m"]["min"]) &
                         (c.dist_pole_actif_m <= pb["distance_arret_existant_m"]["max"])).to_numpy())
cout_b = np.full(len(c), pb["cout_investissement_eur"]["centrale"], float)
deja_b = ~sans_arret
val_b = lambda i, deja: pop[couv[i]][~deja[couv[i]]].sum()
ch_b, dep_b = glouton(cand_b, val_b, cout_b, pb["budget_eur"]["centrale"], RAYON, deja=deja_b)
b = c.loc[ch_b, ["commune", "lat", "lon", "x", "y", "pop_carreau", "dist_pole_actif_m", "niveau_vie_k", "quartier_modeste"]].copy()
b["habitants_gagnant_un_arret"] = c.loc[ch_b, "_gain"].to_numpy()
b["cout_eur"] = pb["cout_investissement_eur"]["centrale"]
b["cout_par_habitant_eur"] = (b.cout_eur / b.habitants_gagnant_un_arret).round(1)
b.insert(0, "rang", range(1, len(b) + 1))
b.round({"lat": 6, "lon": 6, "niveau_vie_k": 2, "dist_pole_actif_m": 0}).to_csv(RESULTATS / "arrets_bus_recommandes.csv", index=False)
print("\nArrêts de bus :\n", b.round(1).to_string(index=False))

# ============================================================== 3. Stations de vélos en libre-service
pv = PAR["station_velo"]
cout_v = np.full(len(c), pv["velos_par_station"]["centrale"] * pv["cout_velo_eur_an"]["centrale"])
cand_v = np.flatnonzero(((c.pop_400m >= pv["population_400m_min"]) &
                         (c.dist_pole_fort_m <= pv["distance_pole_tc_fort_max_m"]["centrale"])).to_numpy())
ch_v, dep_v = glouton(cand_v, val_b, cout_v, pv["budget_eur_an"]["centrale"], 500, reseau_km=1.5)
v = c.loc[ch_v, ["commune", "arret_proche", "lat", "lon", "x", "y", "pop_400m", "dist_pole_fort_m", "passages_tc_jour_400m", "quartier_modeste"]].copy()
v["habitants_nouveaux"] = c.loc[ch_v, "_gain"].to_numpy()
v["cout_eur_an"] = cout_v[ch_v]
v.insert(0, "rang", range(1, len(v) + 1))
v.round({"lat": 6, "lon": 6, "dist_pole_fort_m": 0}).to_csv(RESULTATS / "stations_velo_recommandees.csv", index=False)
print("\nStations vélo :\n", v.round(1).to_string(index=False))

proj = pd.read_csv(RESULTATS / "projections_06.csv")
f2035 = proj[(proj.annee == 2035)].set_index("scenario").facteur_25_54_vs_2021
synthese = {
    "citiz": {"stations": len(r), "vehicules": int(r.vehicules.sum()), "budget_annee1_eur": int(depense),
              "habitants_nouveaux": int(r.habitants_nouveaux.sum()),
              "cible_25_54_2035_facteur": f2035.to_dict(),
              "resultat_exploitation_eur_an": {k: int(r[f"resultat_eur_an_{k}"].sum()) for k in ["bas", "centrale", "haut"]},
              "co2_evite_t_an": [round(float(r.co2_evite_t_an_bas.sum())), round(float(r.co2_evite_t_an_haut.sum()))],
              "part_stations_quartiers_modestes": round(float(r.quartier_modeste.mean()), 2),
              "stations_hors_domaine_du_modele": int(r.hors_domaine.sum()),
              "occupation_moyenne_reseau_citiz": round(OCC_MOY, 3),
              "communes": r.commune.value_counts().to_dict(), "comparaison_anciennes_listes": anciens},
    "arrets_bus": {"arrets": len(b), "budget_eur": int(dep_b), "habitants_gagnant_un_arret": int(b.habitants_gagnant_un_arret.sum()),
                   "habitants_sans_arret_actif_avant": int(pop[sans_arret].sum())},
    "stations_velo": {"stations": len(v), "budget_eur_an": int(dep_v), "habitants_nouveaux": int(v.habitants_nouveaux.sum()),
                      "communes": v.commune.value_counts().to_dict()},
}
(RESULTATS / "synthese_decision.json").write_text(json.dumps(synthese, ensure_ascii=False, indent=2, default=str))
print(json.dumps(synthese, ensure_ascii=False, indent=2, default=str))
