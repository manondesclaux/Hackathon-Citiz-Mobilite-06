"""Étape 3 — Modèle prédictif de l'usage d'une station, évalué hors échantillon, puis appliqué aux candidats du 06.

Protocole (ce qu'un data scientist du jury demandera) :
- validation croisée « un réseau Citiz laissé de côté » (GroupKFold, 15 réseaux) : on prédit chaque réseau sans
  l'avoir vu, ce qui imite le cas de la Côte d'Azur, où Citiz n'est pas présent ;
- comparaison à deux références : prédiction constante (moyenne) et ancien modèle de l'équipe
  (ln population à 400 m + motorisation de la commune) ;
- métriques : erreur absolue moyenne (MAE), R², corrélation de rang de Spearman à l'intérieur de chaque réseau
  (c'est ce qui compte pour classer des sites dans une même ville) ;
- pondération par le nombre de véhicules (une station d'un véhicule donne une mesure très bruitée) ;
- intervalle de prédiction à 80 % par les quantiles des erreurs hors échantillon (conformal simple) ;
- contrôle d'extrapolation : un candidat dont une variable sort de l'étendue observée (1er-99e centile) est signalé.

Règle de décision écrite AVANT de lancer : le modèle n'est utilisé pour classer les sites que s'il réduit la MAE
d'au moins 3 % par rapport à la moyenne ET si sa corrélation de rang intra-réseau est positive dans au moins
70 % des réseaux. Sinon le classement repose sur la population nouvellement desservie, et on le dit.

Sorties : decision/resultats/modele_usage.json, decision/resultats/importance_variables.csv,
          decision/donnees/candidats_06_predits.csv.gz, decision/resultats/modele_usage.joblib
"""
import json

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from communs import DONNEES, RESULTATS, VARIABLES

CIBLE = "occupation_jour"
st = pd.read_csv(DONNEES / "variables_stations.csv")
st = st[st.pop_400m > 0].reset_index(drop=True)
X, y, w, g = st[VARIABLES], st[CIBLE].to_numpy(), st.vehicules.to_numpy(float), st.jeu.to_numpy()

MODELES = {
    "moyenne": None,
    "ancien_modele_equipe": ("lin", ["log_pop_400m", "part_sans_voiture_commune"]),
    "ridge": ("ridge", VARIABLES),
    "gradient_boosting": ("gb", VARIABLES),
}


def construire(kind):
    if kind == "lin":
        return make_pipeline(SimpleImputer(strategy="median"), LinearRegression())
    if kind == "ridge":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20)))
    return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.04, max_iter=250, min_samples_leaf=40,
                                         l2_regularization=1.0, random_state=0)


def wmae(y_true, y_pred, poids):
    return float(np.average(np.abs(y_true - y_pred), weights=poids))


gkf = GroupKFold(n_splits=g.size and len(np.unique(g)))
oof = {k: np.zeros(len(y)) for k in MODELES}
importances = []
for tr, te in gkf.split(X, y, g):
    for nom, spec in MODELES.items():
        if spec is None:
            oof[nom][te] = np.average(y[tr], weights=w[tr])
            continue
        kind, cols = spec
        m = construire(kind)
        fit_kw = {"sample_weight": w[tr]} if kind == "gb" else {f"{m.steps[-1][0]}__sample_weight": w[tr]}
        m.fit(X.iloc[tr][cols], y[tr], **fit_kw)
        oof[nom][te] = np.clip(m.predict(X.iloc[te][cols]), 0, 1)
        if nom == "gradient_boosting" and len(te) >= 30:
            pi = permutation_importance(m, X.iloc[te][cols], y[te], n_repeats=5, random_state=0,
                                        scoring="neg_mean_absolute_error", sample_weight=w[te])
            importances.append(pd.Series(pi.importances_mean, index=cols))


def evaluer(pred):
    par_reseau = []
    for res in np.unique(g):
        m = g == res
        if m.sum() >= 10 and np.std(pred[m]) > 0:
            par_reseau.append(spearmanr(pred[m], y[m])[0])
    par_reseau = np.array([r for r in par_reseau if np.isfinite(r)])
    ss_res = np.average((y - pred) ** 2, weights=w)
    ss_tot = np.average((y - np.average(y, weights=w)) ** 2, weights=w)
    return {"mae": round(wmae(y, pred, w), 4), "r2_hors_echantillon": round(1 - ss_res / ss_tot, 4),
            "spearman_global": round(float(spearmanr(pred, y)[0]), 3) if len(np.unique(pred)) > len(np.unique(g)) else None,
            "spearman_intra_reseau_moyen": round(float(np.nanmean(par_reseau)), 3) if len(par_reseau) else None,
            "part_reseaux_spearman_positif": round(float(np.mean(par_reseau > 0)), 2) if len(par_reseau) else None}


res = {nom: evaluer(p) for nom, p in oof.items()}
base = res["moyenne"]["mae"]
for nom in res:
    res[nom]["gain_mae_vs_moyenne_pct"] = round(100 * (base - res[nom]["mae"]) / base, 1)
cand = ["ridge", "gradient_boosting"]
meilleur = max(cand, key=lambda k: res[k]["gain_mae_vs_moyenne_pct"])
valide = (res[meilleur]["gain_mae_vs_moyenne_pct"] >= 3) and ((res[meilleur]["part_reseaux_spearman_positif"] or 0) >= 0.7)

# bootstrap par réseau du gain de MAE (incertitude due au faible nombre de réseaux)
rng = np.random.default_rng(0)
reseaux = np.unique(g)
gains = []
for _ in range(1000):
    tirage = rng.choice(reseaux, len(reseaux))
    idx = np.concatenate([np.flatnonzero(g == r) for r in tirage])
    gains.append(100 * (wmae(y[idx], oof["moyenne"][idx], w[idx]) - wmae(y[idx], oof[meilleur][idx], w[idx]))
                 / wmae(y[idx], oof["moyenne"][idx], w[idx]))
ic_gain = [round(float(np.percentile(gains, 5)), 1), round(float(np.percentile(gains, 95)), 1)]

# modèle final, entraîné sur toutes les stations
kind, cols = MODELES[meilleur]
final = construire(kind)
fit_kw = {"sample_weight": w} if kind == "gb" else {f"{final.steps[-1][0]}__sample_weight": w}
final.fit(X[cols], y, **fit_kw)
joblib.dump({"modele": final, "variables": cols, "cible": CIBLE}, RESULTATS / "modele_usage.joblib")
residus = y - oof[meilleur]
q10, q90 = np.percentile(residus, [10, 90])

imp = pd.concat(importances, axis=1).mean(axis=1).sort_values(ascending=False) if importances else pd.Series(dtype=float)
imp.rename("baisse_mae_si_permutee").to_csv(RESULTATS / "importance_variables.csv")

c = pd.read_csv(DONNEES / "candidats_06.csv.gz", dtype={"code_commune": str, "commune_carreau": str})
c["usage_predit"] = np.clip(final.predict(c[cols]), 0, 1)
c["usage_bas"] = np.clip(c.usage_predit + q10, 0, 1)
c["usage_haut"] = np.clip(c.usage_predit + q90, 0, 1)
lo, hi = st[VARIABLES].quantile(0.01), st[VARIABLES].quantile(0.99)
hors = ((c[VARIABLES] < lo) | (c[VARIABLES] > hi))
c["variables_hors_domaine"] = hors.apply(lambda r: ", ".join(r.index[r]), axis=1)
c["hors_domaine"] = hors.any(axis=1)
c.to_csv(DONNEES / "candidats_06_predits.csv.gz", index=False)

dense = c[c.pop_400m >= 3000]
sortie = {
    "cible": CIBLE, "stations": int(len(st)), "reseaux": int(len(reseaux)), "validation": "GroupKFold, un réseau laissé de côté",
    "resultats_hors_echantillon": res, "modele_retenu": meilleur,
    "gain_mae_ic90_bootstrap_reseaux_pct": ic_gain,
    "valide_pour_classer": bool(valide),
    "regle": "gain MAE >= 3 % vs moyenne ET Spearman intra-réseau > 0 dans >= 70 % des réseaux",
    "intervalle_80pct_residus": [round(float(q10), 3), round(float(q90), 3)],
    "candidats_06_hors_domaine_pct": round(100 * float(c.hors_domaine.mean()), 1),
    "candidats_denses_06_hors_domaine_pct": round(100 * float(dense.hors_domaine.mean()), 1),
    "variables_les_plus_hors_domaine_06": hors[c.pop_400m >= 3000].mean().sort_values(ascending=False).head(4).round(3).to_dict(),
    "usage_predit_candidats_denses": {"min": round(float(dense.usage_predit.min()), 3),
                                      "mediane": round(float(dense.usage_predit.median()), 3),
                                      "max": round(float(dense.usage_predit.max()), 3)},
}
(RESULTATS / "modele_usage.json").write_text(json.dumps(sortie, ensure_ascii=False, indent=2))
print(json.dumps(sortie, ensure_ascii=False, indent=2))
print("\nImportance (baisse de MAE quand la variable est mélangée, hors échantillon) :\n", imp.round(4).to_string())
