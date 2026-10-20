"""Quels véhicules Citiz « fonctionnent » (réservés) et lesquels non ? Facteurs associés.

Usage :
    python scripts/vehicules_succes.py releves.parquet DOSSIER_CITIZ DOSSIER_CONCURRENTS carreaux_200m_met.csv
Sortie : sorties/vehicules_succes.csv + analyses affichées.
Groupes : jamais réservé / actif (>=1 début de réservation observé) / toujours réservé (sans transition).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
from scipy.stats import mannwhitneyu, spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

sys.path.insert(0, str(Path(__file__).parent))
from analyse_citiz import charger  # noqa: E402
from croise_concurrents import charger_concurrents  # noqa: E402

AGES = {"ind_0_3": 1.5, "ind_4_5": 5, "ind_6_10": 8.5, "ind_11_17": 14.5, "ind_18_24": 21.5, "ind_25_39": 32.5,
        "ind_40_54": 47.5, "ind_55_64": 60, "ind_65_79": 72.5, "ind_80p": 85}


def txt(n):
    return n[0]["text"] if isinstance(n, list) and n else None


def types(citiz: Path) -> pd.DataFrame:
    rows = []
    for d in sorted(p for p in citiz.iterdir() if p.is_dir()):
        for t in json.load(open(d / "vehicle_types.json"))["data"]["vehicle_types"]:
            rows.append(dict(jeu=d.name, vehicle_type_id=str(t["vehicle_type_id"]), propulsion=t.get("propulsion_type"),
                             marque=txt(t.get("make")), modele=txt(t.get("model"))))
    return pd.DataFrame(rows)


def vehicules(releves: str) -> pd.DataFrame:
    d = pd.read_parquet(releves).sort_values(["jeu", "vehicle_id", "releve_utc"])
    d = d[d.groupby("releve_utc").vehicle_id.transform("size") >= 2600]  # relevés complets
    d["debut"] = (d.groupby(["jeu", "vehicle_id"]).is_reserved.shift() == False) & d.is_reserved  # noqa: E712
    d["rep_change"] = d.groupby(["jeu", "vehicle_id"]).last_reported.transform(lambda s: s.nunique() > 1)
    fin = d.releve_utc.max()
    v = d.groupby(["jeu", "vehicle_id"]).agg(
        station_id=("station_id", "first"), type_id=("vehicle_type_id", "first"), lat=("lat", "first"), lon=("lon", "first"),
        occupation=("is_reserved", "mean"), debuts=("debut", "sum"), disabled=("is_disabled", "max"),
        fuel=("fuel_pct", "mean"), fuel_min=("fuel_pct", "min"), range_m=("range_m", "mean"),
        last_rep=("last_reported", "max"), rep_change=("rep_change", "max"), n_rel=("releve_utc", "size")).reset_index()
    v["age_donnee_h"] = (fin - v.last_rep).dt.total_seconds() / 3600
    v["groupe"] = np.select([v.occupation == 0, (v.occupation == 1) & (v.debuts == 0)], ["jamais", "toujours"], "actif")
    return v


def voisinage(v, citiz, conc, csv):
    xf = Transformer.from_crs(4326, 3035, always_xy=True)
    v["x"], v["y"] = xf.transform(v.lon.values, v.lat.values)
    c = pd.read_csv(csv, usecols=["idcar_200m", "ind"] + list(AGES))
    e = c.idcar_200m.str.extract(r"RES200mN(\d+)E(\d+)").astype(float)
    c["y"], c["x"] = e[0] + 100, e[1] + 100
    nb = cKDTree(c[["x", "y"]].to_numpy()).query_ball_point(v[["x", "y"]].to_numpy(), r=500)
    pop, den = c.ind.to_numpy(), c[list(AGES)].sum(axis=1).to_numpy()
    num = sum(c[k].to_numpy() * a for k, a in AGES.items())
    v["pop_500m"] = [pop[i].sum() for i in nb]
    v["age_moyen_hab"] = [num[i].sum() / den[i].sum() if den[i].sum() else np.nan for i in nb]
    for k, n in [("ind_18_24", "part_18_24"), ("ind_25_39", "part_25_39"), ("ind_65_79", "part_65_79")]:
        a = c[k].to_numpy()
        v[n] = [100 * a[i].sum() / pop[i].sum() if pop[i].sum() else np.nan for i in nb]
    # voisinage Citiz (autres véhicules proches) et concurrence
    t = cKDTree(v[["x", "y"]].to_numpy())
    v["autres_citiz_500m"] = [len(i) - 1 for i in t.query_ball_point(v[["x", "y"]].to_numpy(), r=500)]
    v["veh_meme_station"] = v.groupby(["jeu", "station_id"]).vehicle_id.transform("size")
    co, leogo, ga = charger_concurrents(conc)
    for nom, df in [("conc_stations_500m", co), ("getaround_500m", ga)]:
        df = df[df.lat.between(41, 52) & df.lon.between(-6, 10)]
        x, y = xf.transform(df.lon.values, df.lat.values)
        v[nom] = [len(i) for i in cKDTree(np.c_[x, y]).query_ball_point(v[["x", "y"]].to_numpy(), r=500)]
    return v


def main(releves, citiz, conc, csv):
    v = vehicules(releves).merge(types(Path(citiz)), left_on=["jeu", "type_id"], right_on=["jeu", "vehicle_type_id"], how="left")
    v = v[v.lat.between(41, 52) & v.lon.between(-6, 10)].reset_index(drop=True)
    v = voisinage(v, Path(citiz), Path(conc), csv)
    v.drop(columns=["x", "y"]).to_csv("sorties/vehicules_succes.csv", index=False)
    print(f"{len(v)} véhicules | groupes : {v.groupe.value_counts().to_dict()}")

    print("\n=== Taux de véhicules actifs (≥1 réservation) selon la catégorie ===")
    a = v[v.groupe != "toujours"]
    for col in ["propulsion", "marque", "disabled"]:
        t = a.groupby(col).agg(n=("groupe", "size"), actifs_pct=("groupe", lambda s: round(100 * (s == "actif").mean(), 1)),
                               occupation=("occupation", lambda s: round(100 * s.mean(), 1)))
        print(f"\n{col} :\n{t[t.n >= 15].sort_values('actifs_pct', ascending=False).to_string()}")
    t = a.groupby("modele").agg(n=("groupe", "size"), actifs_pct=("groupe", lambda s: round(100 * (s == "actif").mean(), 1)))
    print("\nmodèles (≥25 véhicules) :\n", t[t.n >= 25].sort_values("actifs_pct", ascending=False).to_string())

    print("\n=== Variables numériques : actifs vs jamais réservés (médianes) + Mann-Whitney ===")
    num = ["fuel", "range_m", "age_donnee_h", "veh_meme_station", "autres_citiz_500m", "pop_500m", "age_moyen_hab",
           "part_18_24", "part_25_39", "part_65_79", "conc_stations_500m", "getaround_500m"]
    jam, act = a[a.groupe == "jamais"], a[a.groupe == "actif"]
    lignes = []
    for c in num:
        x, y = jam[c].dropna(), act[c].dropna()
        lignes.append(dict(variable=c, mediane_jamais=x.median(), mediane_actif=y.median(),
                           rho_occupation=spearmanr(a[c], a.occupation, nan_policy="omit")[0], p=mannwhitneyu(x, y)[1]))
    print(pd.DataFrame(lignes).round(3).to_string(index=False))

    print("\n=== Modèle : prédire « actif » (régression logistique, validation croisée 5 plis) ===")
    X = pd.concat([a[num], pd.get_dummies(a.propulsion, prefix="prop"), pd.get_dummies(a.jeu, prefix="jeu")], axis=1)
    X = X.fillna(X.median())
    y = (a.groupe == "actif").astype(int)
    m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.3))
    p = cross_val_predict(m, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0), method="predict_proba")[:, 1]
    print(f"AUC = {roc_auc_score(y, p):.3f}  (0,5 = hasard ; part d'actifs = {100 * y.mean():.1f} %)")
    m.fit(X, y)
    coef = pd.Series(m[-1].coef_[0], index=X.columns).sort_values()
    print("Plus forts effets (coef standardisés) — négatif = moins de chances d'être actif :")
    print(pd.concat([coef.head(7), coef.tail(7)]).round(2).to_string())
    X2 = X[[c for c in X if not c.startswith("jeu_")]]
    p2 = cross_val_predict(m, X2, y, cv=StratifiedKFold(5, shuffle=True, random_state=0), method="predict_proba")[:, 1]
    print(f"AUC sans l'effet territoire = {roc_auc_score(y, p2):.3f}")

    print("\n=== Les « toujours réservés » (sans transition) ===")
    tt = v[v.groupe == "toujours"]
    print(f"{len(tt)} véhicules | is_disabled vrai : {100 * tt.disabled.mean():.0f} % (contre {100 * v[v.groupe != 'toujours'].disabled.mean():.0f} % pour les autres)")
    print(tt.jeu.value_counts().head(6).to_string())


if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    main(*sys.argv[1:5])
