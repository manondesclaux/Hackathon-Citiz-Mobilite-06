"""Étape 4 — Modèle de potentiel d'implantation : « ce carreau ressemble-t-il aux lieux où Citiz tient une station ? »

Pourquoi ce modèle : l'étape 3 montre que l'usage à court terme (moins d'un jour de relevés) n'est pas prévisible
mieux qu'une moyenne. En revanche, les 1 500 stations Citiz actives sont le résultat de 20 ans d'essais : les
emplacements sans demande ont été fermés ou déplacés. Leur localisation est donc une demande « révélée » et stable.

Apprentissage : carreaux habités des communes où Citiz est présent.
- positif : carreau habité le plus proche de chaque station Citiz avec au moins un véhicule ;
- négatif : carreau habité de ces communes à plus de 400 m de toute station (zone non desservie, sans ambiguïté) ;
- validation : GroupKFold par réseau Citiz (on prédit un réseau sans l'avoir vu) ; AUC, précision moyenne,
  part des stations captées par les 10 % de carreaux les mieux notés de leur réseau ;
- validation externe : le potentiel prédit hors échantillon aux stations existantes est-il lié à leur usage observé
  (relevés Fabric) ? C'est le test qui relie « où Citiz s'installe » et « où ses voitures roulent ».

Biais assumés : le modèle apprend aussi les contraintes de Citiz (stationnement disponible, partenariats locaux,
historique de chaque réseau) ; les stations fermées ne sont pas observées ; un carreau très bien noté reste un
secteur à étudier sur le terrain.

Sorties : decision/resultats/modele_implantation.json, decision/resultats/usage_par_potentiel.csv,
          decision/donnees/candidats_06_scores.csv.gz, decision/resultats/modele_implantation.joblib
"""
import json

import joblib
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold

from communs import (CLEAN, DONNEES, RESULTATS, RAYON, VARIABLES, arrets, carreaux, logement_communes,
                     motorisation_communes, to4326, variables, velos, xy)

rng = np.random.default_rng(0)
car = carreaux()
ctx = dict(car=car, stops=arrets(), vls=velos(), mot=motorisation_communes(), rs=logement_communes())

cz = pd.read_csv(CLEAN / "citiz_stations.csv", dtype={"commune_code": str})
cz = cz[~cz.sans_vehicule & ~cz.flex & cz.lat.between(41, 52) & cz.lon.between(-6, 10)].reset_index(drop=True)
P = xy(cz.lon, cz.lat)
tree_car = cKDTree(car[["x", "y"]].to_numpy())
_, idx = tree_car.query(P)
cz["carreau"] = idx
communes = set(car.code_commune.iloc[idx])
zone = car[car.code_commune.isin(communes)].copy()
d_station, i_station = cKDTree(P).query(zone[["x", "y"]].to_numpy())
zone["reseau"] = cz.network.to_numpy()[i_station]                       # réseau du secteur = celui de la station la plus proche
pos = zone.index.isin(cz.carreau)
neg = (~pos) & (d_station > RAYON)
neg_idx = zone.index[neg]
neg_idx = rng.choice(neg_idx, size=min(len(neg_idx), 40_000), replace=False)
train = zone.loc[np.r_[zone.index[pos], neg_idx]].copy()
train["station"] = train.index.isin(cz.carreau).astype(int)
train["lon"], train["lat"] = to4326.transform(train.x.values, train.y.values)
train = train.reset_index(drop=True)
train = train.join(variables(train, **ctx), rsuffix="_v")
print(f"Apprentissage : {train.station.sum():,} carreaux avec station, {(1 - train.station).sum():,} sans (échantillon), "
      f"{train.reseau.nunique()} réseaux, {len(communes)} communes")

X, y, g = train[VARIABLES], train.station.to_numpy(), train.reseau.to_numpy()
poids = np.where(y == 1, (1 - y).sum() / y.sum(), 1.0)                 # rééquilibrage des classes


def modele():
    return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=50,
                                          l2_regularization=1.0, random_state=0)


oof = np.zeros(len(y))
imps = []
for tr, te in GroupKFold(n_splits=len(np.unique(g))).split(X, y, g):
    m = modele().fit(X.iloc[tr], y[tr], sample_weight=poids[tr])
    oof[te] = m.predict_proba(X.iloc[te])[:, 1]
    if y[te].sum() >= 20:
        pi = permutation_importance(m, X.iloc[te], y[te], scoring="roc_auc", n_repeats=3, random_state=0)
        imps.append(pd.Series(pi.importances_mean, index=VARIABLES))

par_reseau, capte = {}, []
for r in np.unique(g):
    k = g == r
    if y[k].sum() >= 5 and (1 - y[k]).sum() >= 20:
        par_reseau[r] = round(float(roc_auc_score(y[k], oof[k])), 3)
        seuil = np.quantile(oof[k], 0.9)
        capte.append(y[k][oof[k] >= seuil].sum() / y[k].sum())
auc = roc_auc_score(y, oof)

# Référence naïve : densité seule (population à 400 m)
auc_densite = roc_auc_score(y, train.log_pop_400m.fillna(0))

# Validation externe : potentiel hors échantillon aux stations, contre l'usage observé dans Fabric
train["potentiel_oof"] = oof
u = pd.read_csv(DONNEES / "usage_stations.csv")
_, iu = tree_car.query(xy(u.lon, u.lat))
pot_car = pd.Series(oof[y == 1], index=train.loc[y == 1, "idcar_200m"].to_numpy())
pot_car = pot_car.groupby(level=0).mean()
u["potentiel_oof"] = car.idcar_200m.iloc[iu].map(pot_car).to_numpy()
u = u.dropna(subset=["potentiel_oof"])
rho_usage, p_usage = spearmanr(u.potentiel_oof, u.occupation_jour)
u["quintile_potentiel"] = pd.qcut(u.potentiel_oof, 5, labels=["Q1 (faible)", "Q2", "Q3", "Q4", "Q5 (fort)"])


def occ_ponderee(df):
    t = df.assign(ow=df.occupation_jour * df.vehicules).groupby("quintile_potentiel", observed=True)[["ow", "vehicules"]].sum()
    return t.ow / t.vehicules


boot = [occ_ponderee(u.sample(len(u), replace=True, random_state=int(rng.integers(1e9)))) for _ in range(500)]
boot = pd.concat(boot, axis=1)
upq = pd.DataFrame({
    "stations": u.groupby("quintile_potentiel", observed=True).size(),
    "potentiel_min": u.groupby("quintile_potentiel", observed=True).potentiel_oof.min().round(3),
    "occupation_jour": occ_ponderee(u).round(3),
    "ic90_bas": boot.quantile(0.05, axis=1).round(3), "ic90_haut": boot.quantile(0.95, axis=1).round(3)})
upq.to_csv(RESULTATS / "usage_par_potentiel.csv")

# Modèle final et application aux candidats du 06
final = modele().fit(X, y, sample_weight=poids)
joblib.dump({"modele": final, "variables": VARIABLES}, RESULTATS / "modele_implantation.joblib")
c = pd.read_csv(DONNEES / "candidats_06_predits.csv.gz", dtype={"code_commune": str, "commune_carreau": str})
c["potentiel"] = final.predict_proba(c[VARIABLES])[:, 1]
ref = np.sort(final.predict_proba(X[y == 1])[:, 1])                      # potentiel des vraies stations Citiz
c["percentile_vs_stations_citiz"] = 100 * np.searchsorted(ref, c.potentiel) / len(ref)
bornes = upq.potentiel_min.to_numpy()
q = np.clip(np.searchsorted(bornes, c.potentiel, side="right") - 1, 0, 4)
c["occupation_attendue"] = upq.occupation_jour.to_numpy()[q]
c["occupation_bas"] = upq.ic90_bas.to_numpy()[q]
c["occupation_haut"] = upq.ic90_haut.to_numpy()[q]
c.to_csv(DONNEES / "candidats_06_scores.csv.gz", index=False)

imp = pd.concat(imps, axis=1).mean(axis=1).sort_values(ascending=False)
imp.rename("baisse_auc_si_permutee").round(4).to_csv(RESULTATS / "importance_implantation.csv")
sortie = {
    "apprentissage": {"positifs": int(y.sum()), "negatifs": int((1 - y).sum()), "reseaux": int(len(np.unique(g))),
                      "communes": len(communes)},
    "validation": "GroupKFold par réseau Citiz (hors échantillon)",
    "auc": round(float(auc), 3), "auc_reference_densite_seule": round(float(auc_densite), 3),
    "precision_moyenne": round(float(average_precision_score(y, oof)), 3), "taux_positifs": round(float(y.mean()), 3),
    "auc_par_reseau": par_reseau,
    "part_stations_dans_top10pct_de_leur_reseau": round(float(np.mean(capte)), 3),
    "validation_externe_usage": {"stations": int(len(u)), "spearman_potentiel_vs_occupation": round(float(rho_usage), 3),
                                 "p_valeur": float(f"{p_usage:.2g}"),
                                 "occupation_par_quintile": upq.occupation_jour.to_dict()},
    "candidats_06": {"n": int(len(c)), "comparables_a_station_citiz_mediane": int((c.percentile_vs_stations_citiz >= 50).sum()),
                     "habitants_dans_ces_carreaux": round(float(c.loc[c.percentile_vs_stations_citiz >= 50, "pop_carreau"].sum()))},
    "importance": imp.round(4).head(8).to_dict(),
}
(RESULTATS / "modele_implantation.json").write_text(json.dumps(sortie, ensure_ascii=False, indent=2))
print(json.dumps(sortie, ensure_ascii=False, indent=2))
print(upq.to_string())
