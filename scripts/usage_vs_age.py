"""Relie l'usage des stations Citiz (relevés Fabric) à la structure d'âge des habitants alentour (Filosofi).

Usage :
    python scripts/usage_vs_age.py releves.parquet DOSSIER_CITIZ carreaux_200m_met.csv [rayon_m=500]
Sortie : stations_usage_age.csv + corrélations affichées. Corrélation à l'échelle des stations, pas des individus.
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

TR = {"18-24": ["ind_18_24"], "25-39": ["ind_25_39"], "40-54": ["ind_40_54"], "55-64": ["ind_55_64"],
      "65-79": ["ind_65_79"], "80+": ["ind_80p"], "moins de 18": ["ind_0_3", "ind_4_5", "ind_6_10", "ind_11_17"]}
AGES = {"ind_0_3": 1.5, "ind_4_5": 5, "ind_6_10": 8.5, "ind_11_17": 14.5, "ind_18_24": 21.5, "ind_25_39": 32.5,
        "ind_40_54": 47.5, "ind_55_64": 60, "ind_65_79": 72.5, "ind_80p": 85}


def usage(releves: str) -> pd.DataFrame:
    d = pd.read_parquet(releves).sort_values(["jeu", "vehicle_id", "releve_utc"])
    d = d[d.groupby("releve_utc").vehicle_id.transform("size") >= 2600]  # relevés complets
    d["debut"] = (d.groupby(["jeu", "vehicle_id"]).is_reserved.shift() == False) & d.is_reserved  # noqa: E712
    d["h"] = d.releve_utc.dt.tz_convert("Europe/Paris").dt.hour
    jour = d[d.h.between(7, 19)]
    s = d.groupby(["jeu", "station_id"]).agg(vehicules=("vehicle_id", "nunique"), occupation=("is_reserved", "mean"),
                                           debuts=("debut", "sum"))
    s["debuts_par_veh"] = s.debuts / s.vehicules
    s["occupation_jour"] = jour.groupby(["jeu", "station_id"]).is_reserved.mean()
    return s.reset_index()


def main(releves, citiz, csv, rayon):
    st, _, _ = charger(Path(citiz))
    st = st.drop_duplicates(["jeu", "station_id"])[["jeu", "station_id", "lat", "lon"]]
    u = usage(releves).merge(st, on=["jeu", "station_id"], how="left")
    print(f"Stations avec usage : {len(u)} | rattachées à une position : {u.lat.notna().sum()}")
    u = u[u.lat.between(41, 52) & u.lon.between(-6, 10)].copy()
    u["x"], u["y"] = Transformer.from_crs(4326, 3035, always_xy=True).transform(u.lon.values, u.lat.values)

    cols = ["idcar_200m", "ind"] + list(AGES)
    c = pd.read_csv(csv, usecols=cols)
    e = c.idcar_200m.str.extract(r"RES200mN(\d+)E(\d+)").astype(float)
    c["y"], c["x"] = e[0] + 100, e[1] + 100
    voisins = cKDTree(c[["x", "y"]].to_numpy()).query_ball_point(u[["x", "y"]].to_numpy(), r=rayon)
    tot = np.array([c.ind.to_numpy()[i].sum() for i in voisins])
    u["pop"] = tot
    for nom, v in TR.items():
        arr = c[v].sum(axis=1).to_numpy()
        u[f"part_{nom}"] = [arr[i].sum() for i in voisins] / np.where(tot > 0, tot, np.nan) * 100
    num = sum(c[k].to_numpy() * a for k, a in AGES.items())
    den = c[list(AGES)].sum(axis=1).to_numpy()
    u["age_moyen"] = [num[i].sum() / den[i].sum() if den[i].sum() > 0 else np.nan for i in voisins]
    u = u[u["pop"] >= 500].dropna(subset=["age_moyen"])
    u.drop(columns=["x", "y"]).to_csv("stations_usage_age.csv", index=False)
    print(f"Stations analysées (≥500 hab. dans {rayon:.0f} m) : {len(u)} | véhicules : {int(u.vehicules.sum())}")

    var = ["part_18-24", "part_25-39", "part_40-54", "part_55-64", "part_65-79", "part_moins de 18", "age_moyen"]
    cibles = ["occupation", "occupation_jour", "debuts_par_veh"]
    print("\nCorrélation de Spearman (stations ; pondérer = non) — ρ [p]")
    print(f"{'':<20}" + "".join(f"{t:>26}" for t in cibles))
    for v in var:
        print(f"{v:<20}" + "".join(f"{spearmanr(u[v], u[t])[0]:>+16.3f} [{spearmanr(u[v], u[t])[1]:.3f}]" for t in cibles))

    # même corrélation en retirant les écarts entre jeux (effet territoire) : on centre par jeu
    print("\nIdem, après retrait de la moyenne de chaque jeu (compare les stations d'un même territoire) :")
    for v in var:
        r = []
        for t in cibles:
            a = u[v] - u.groupby("jeu")[v].transform("mean")
            b = u[t] - u.groupby("jeu")[t].transform("mean")
            r.append(spearmanr(a, b))
        print(f"{v:<20}" + "".join(f"{x[0]:>+16.3f} [{x[1]:.3f}]" for x in r))

    print("\nUsage par quartile d'âge moyen autour de la station (Q1 = plus jeune) :")
    u["quartile_age"] = pd.qcut(u.age_moyen, 4, labels=["Q1 (jeune)", "Q2", "Q3", "Q4 (âgé)"])
    q = u.groupby("quartile_age", observed=True).agg(stations=("jeu", "size"), age_moyen=("age_moyen", "mean"),
                                                   occupation=("occupation", "mean"), debuts_par_veh=("debuts_par_veh", "mean"),
                                                   pop_500m=("pop", "mean"))
    q["occupation"] = (100 * q.occupation).round(1)
    print(q.round(2).to_string())
    print("\nUsage par quartile de part 18-24 ans :")
    u["q1824"] = pd.qcut(u["part_18-24"], 4, labels=["Q1 (peu)", "Q2", "Q3", "Q4 (beaucoup)"])
    q = u.groupby("q1824", observed=True).agg(stations=("jeu", "size"), part_18_24=("part_18-24", "mean"),
                                           occupation=("occupation", "mean"), debuts_par_veh=("debuts_par_veh", "mean"))
    q["occupation"] = (100 * q.occupation).round(1)
    print(q.round(2).to_string())


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    a = sys.argv
    main(a[1], a[2], a[3], float(a[4]) if len(a) > 4 else 500.0)
