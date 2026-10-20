"""Confronte le score « où ouvrir » du projet citiz_azur à l'usage observé des stations Citiz existantes.

Lecture seule sur citiz_azur/. Reproduit son protocole (rayon 400 m, centres de carreaux, concurrence = stations
+ 0,25 × véhicules mobiles) sur les stations existantes, puis mesure le lien avec l'usage (relevés Fabric).
Le critère transport (25 % du score) n'est pas testable : pas d'arrêts de transport hors Alpes-Maritimes.

Usage :
    python scripts/croise_citiz_azur.py releves.parquet DOSSIER_CITIZ DOSSIER_CONCURRENTS carreaux_200m_met.csv citiz_azur
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).parent))
from analyse_citiz import charger  # noqa: E402
from croise_concurrents import charger_concurrents, vers_3035  # noqa: E402
from usage_vs_age import usage  # noqa: E402

R, W_MOBILE = 400, 0.25
POIDS = (0.60, 0.25, 0.15)


def scale(x):
    x = np.log1p(np.asarray(x, float))
    return x / x.max() if x.max() > 0 else np.zeros(len(x))


def main(releves, citiz, conc, csv, azur):
    cand = pd.read_csv(Path(azur) / "results/candidats.csv", dtype={"code_commune": str})
    top = pd.read_csv(Path(azur) / "results/top10.csv", dtype={"code_commune": str})

    # --- stations existantes : usage + features au protocole citiz_azur
    st, _, _ = charger(Path(citiz))
    u = usage(releves).merge(st.drop_duplicates(["jeu", "station_id"])[["jeu", "station_id", "lat", "lon"]],
                             on=["jeu", "station_id"])
    u = vers_3035(u)
    xf = Transformer.from_crs(4326, 3035, always_xy=True)
    c = pd.read_csv(csv, usecols=["idcar_200m", "ind"])
    e = c.idcar_200m.str.extract(r"RES200mN(\d+)E(\d+)").astype(float)
    c["y"], c["x"] = e[0] + 100, e[1] + 100
    nb = cKDTree(c[["x", "y"]].to_numpy()).query_ball_point(u[["x", "y"]].to_numpy(), r=R)
    u["population_400m"] = [c.ind.to_numpy()[i].sum() for i in nb]
    co, leogo, ga = charger_concurrents(Path(conc))

    def compte(df):
        df = df[df.lat.between(41, 52) & df.lon.between(-6, 10)]
        x, y = xf.transform(df.lon.values, df.lat.values)
        return [len(i) for i in cKDTree(np.c_[x, y]).query_ball_point(u[["x", "y"]].to_numpy(), r=R)]

    u["stations_conc_400m"] = compte(co)
    u["veh_conc_400m"] = np.array(compte(leogo)) + np.array(compte(ga))
    u["pression"] = u.stations_conc_400m + W_MOBILE * u.veh_conc_400m
    u = u[u.population_400m > 0].copy()
    u["s_pop"] = scale(u.population_400m)
    u["s_conc"] = 1 / (1 + u.pression)
    u["score_partiel"] = 100 * (POIDS[0] * u.s_pop + POIDS[2] * u.s_conc) / (POIDS[0] + POIDS[2])  # sans transport
    print(f"Stations existantes : {len(u)} | véhicules : {int(u.vehicules.sum())} | communes/jeux : {u.jeu.nunique()}")
    print(f"Concurrence à 400 m : {(u.pression > 0).sum()} stations avec ≥1 concurrent ({100 * (u.pression > 0).mean():.0f} %)")

    # --- 1. lien score <-> usage observé
    print("\n=== 1. Spearman entre les critères du score et l'usage observé (stations Citiz existantes) ===")
    cibles = ["occupation", "occupation_jour", "debuts_par_veh"]
    print(f"{'critère':<30}" + "".join(f"{t:>26}" for t in cibles))
    for nom, col in [("population 400 m (60 %)", "s_pop"), ("faible concurrence (15 %)", "s_conc"),
                     ("score partiel pop+concu", "score_partiel")]:
        print(f"{nom:<30}" + "".join(f"{spearmanr(u[col], u[t])[0]:>+16.3f} [{spearmanr(u[col], u[t])[1]:.3f}]" for t in cibles))
    print("\nIdem à l'intérieur de chaque jeu (moyenne du jeu retirée) :")
    for nom, col in [("population 400 m", "s_pop"), ("faible concurrence", "s_conc"), ("score partiel", "score_partiel")]:
        r = [spearmanr(u[col] - u.groupby("jeu")[col].transform("mean"), u[t] - u.groupby("jeu")[t].transform("mean")) for t in cibles]
        print(f"{nom:<30}" + "".join(f"{x[0]:>+16.3f} [{x[1]:.3f}]" for x in r))

    # --- 2. usage par quartile de score partiel
    u["quartile"] = pd.qcut(u.score_partiel, 4, labels=["Q1 (bas)", "Q2", "Q3", "Q4 (haut)"])
    q = u.groupby("quartile", observed=True).agg(stations=("jeu", "size"), pop_400m=("population_400m", "median"),
                                                occupation=("occupation", "mean"), debuts_par_veh=("debuts_par_veh", "mean"))
    q["occupation"] = (100 * q.occupation).round(1)
    print("\n=== 2. Usage par quartile de score partiel ===\n", q.round(2).to_string())

    # --- 3. effet de la population en classes
    u["classe_pop"] = pd.cut(u.population_400m, [0, 1500, 3000, 5000, 8000, 12000, 1e9],
                             labels=["<1 500", "1,5-3 k", "3-5 k", "5-8 k", "8-12 k", ">12 k"])
    k = u.groupby("classe_pop", observed=True).agg(stations=("jeu", "size"), occupation=("occupation", "mean"),
                                                  debuts_par_veh=("debuts_par_veh", "mean"))
    k["occupation"] = (100 * k.occupation).round(1)
    print("\n=== 3. Usage selon la population à 400 m ===\n", k.round(2).to_string())

    # --- 4. les candidats citiz_azur positionnés par rapport aux stations existantes
    ref = u.population_400m.to_numpy()
    top = top.copy()
    top["pop_400m"] = top.population_400m
    top["percentile_pop"] = [round(100 * (ref < p).mean()) for p in top.pop_400m]
    top["classe_pop"] = pd.cut(top.pop_400m, [0, 1500, 3000, 5000, 8000, 12000, 1e9], labels=k.index.tolist())
    top["occupation_comparable_%"] = top.classe_pop.map(k.occupation)
    top["debuts_veh_comparable"] = top.classe_pop.map(k.debuts_par_veh)
    print("\n=== 4. Top 10 de citiz_azur vs stations existantes de même densité (usage observé, 22 h) ===")
    print(top[["rang", "commune", "arret_proche", "score", "pop_400m", "percentile_pop", "arrets_400m", "pression_concurrentielle",
               "occupation_comparable_%", "debuts_veh_comparable"]].round(2).to_string(index=False))
    print(f"\nPopulation médiane à 400 m : stations existantes {np.median(ref):,.0f} | candidats top 10 {top.pop_400m.median():,.0f}"
          f" | tous candidats {cand.population_400m.median():,.0f}")
    cand["percentile_pop"] = [round(100 * (ref < p).mean()) for p in cand.population_400m]
    print(f"Candidats dont la population à 400 m dépasse la médiane des stations existantes : "
          f"{100 * (cand.population_400m > np.median(ref)).mean():.1f} %")
    print(f"Concurrence des candidats (pression > 0) : {100 * (cand.pression_concurrentielle > 0).mean():.1f} % "
          f"| stations existantes : {100 * (u.pression > 0).mean():.1f} %")

    u.drop(columns=["x", "y", "quartile", "classe_pop"]).to_csv("sorties/stations_existantes_protocole_azur.csv", index=False)
    top.to_csv("sorties/top10_azur_vs_usage.csv", index=False)
    print("\nFichiers : sorties/stations_existantes_protocole_azur.csv, sorties/top10_azur_vs_usage.csv")


if __name__ == "__main__":
    if len(sys.argv) < 6:
        sys.exit(__doc__)
    main(*sys.argv[1:6])
