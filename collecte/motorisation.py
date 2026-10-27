"""Motorisation des ménages par commune (INSEE, recensement 2021, base infracommunale logement) + lien avec l'usage Citiz.

Données : https://www.insee.fr/fr/statistiques/8268838  (base-ic-logement-2021_csv.zip, à placer dans data_insee/)
Variables : P21_RP (résidences principales = ménages), P21_RP_VOIT1P (≥1 voiture), P21_RP_VOIT1, P21_RP_VOIT2P.
C'est une part de MÉNAGES, pas d'habitants. Paris, Lyon, Marseille : agrégées aussi au niveau commune.

Usage :
    python collecte/motorisation.py data_insee/base-ic-logement-2021.CSV                      # écrit donnees/motorisation_communes.csv
    python collecte/motorisation.py INSEE.CSV releves.parquet DOSSIER_CITIZ carreaux_200m_met.csv   # + lien avec l'usage
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
from usage_vs_age import usage  # noqa: E402

AGREG = {"75056": "751", "69123": "6938", "13055": "132"}   # préfixes des arrondissements


def motorisation(csv: str) -> pd.DataFrame:
    d = pd.read_csv(csv, sep=";", usecols=["COM", "P21_RP", "P21_RP_VOIT1P", "P21_RP_VOIT1", "P21_RP_VOIT2P"], dtype={"COM": str})
    g = d.groupby("COM").sum()
    for com, pref in AGREG.items():
        sel = g[g.index.str.startswith(pref) & (g.index.str.len() == 5) & (g.index != com)]
        if len(sel):
            g.loc[com] = sel.sum()
    g = g[g.P21_RP > 0].copy()
    g["menages"] = g.P21_RP
    g["part_sans_voiture"] = 100 * (1 - g.P21_RP_VOIT1P / g.P21_RP)
    g["part_1_voiture"] = 100 * g.P21_RP_VOIT1 / g.P21_RP
    g["part_2_voitures_plus"] = 100 * g.P21_RP_VOIT2P / g.P21_RP
    return g[["menages", "part_sans_voiture", "part_1_voiture", "part_2_voitures_plus"]].round(2).rename_axis("code_commune").reset_index()


def main(insee, releves=None, citiz=None, csv=None):
    m = motorisation(insee)
    m.to_csv(Path(__file__).resolve().parent.parent / "donnees" / "motorisation_communes.csv", index=False)
    print(f"{len(m)} communes | ménages sans voiture : médiane {m.part_sans_voiture.median():.1f} %"
          f" | pondérée France : {np.average(m.part_sans_voiture, weights=m.menages):.1f} %")
    for c, n in [("06088", "Nice"), ("06029", "Cannes"), ("06004", "Antibes"), ("75056", "Paris"), ("69123", "Lyon"),
                 ("13055", "Marseille"), ("33063", "Bordeaux"), ("35238", "Rennes"), ("67482", "Strasbourg")]:
        r = m[m.code_commune == c]
        if len(r):
            r = r.iloc[0]; print(f"  {n:<11} sans voiture {r.part_sans_voiture:>5.1f} % | 1 voiture {r.part_1_voiture:>5.1f} % | 2+ {r.part_2_voitures_plus:>5.1f} %")
    if releves is None:
        return
    # lien avec l'usage : commune de chaque station = commune du carreau Filosofi le plus proche
    st, _, _ = charger(Path(citiz))
    u = usage(releves).merge(st.drop_duplicates(["jeu", "station_id"])[["jeu", "station_id", "lat", "lon"]], on=["jeu", "station_id"])
    u = u[u.lat.between(41, 52) & u.lon.between(-6, 10)].copy()
    u["x"], u["y"] = Transformer.from_crs(4326, 3035, always_xy=True).transform(u.lon.values, u.lat.values)
    c = pd.read_csv(csv, usecols=["idcar_200m", "lcog_geo", "ind"], dtype={"lcog_geo": str})
    e = c.idcar_200m.str.extract(r"RES200mN(\d+)E(\d+)").astype(float)
    c["y"], c["x"] = e[0] + 100, e[1] + 100
    t = cKDTree(c[["x", "y"]].to_numpy()); dist, idx = t.query(u[["x", "y"]].to_numpy())
    u["code_commune"] = c.lcog_geo.iloc[idx].str[:5].to_numpy()
    nb = t.query_ball_point(u[["x", "y"]].to_numpy(), r=400)
    u["population_400m"] = [c.ind.to_numpy()[i].sum() for i in nb]
    u = u.merge(m, on="code_commune", how="left")
    print(f"\nStations rattachées à une commune avec données de motorisation : {u.part_sans_voiture.notna().sum()}/{len(u)}")
    u = u.dropna(subset=["part_sans_voiture"])
    u = u[u.population_400m > 0]
    cibles = ["occupation", "occupation_jour", "debuts_par_veh"]
    print("\nSpearman : usage observé vs motorisation de la COMMUNE de la station — ρ [p]")
    print(f"{'':<26}" + "".join(f"{t:>26}" for t in cibles))
    for v in ["part_sans_voiture", "part_1_voiture", "part_2_voitures_plus"]:
        print(f"{v:<26}" + "".join(f"{spearmanr(u[v], u[t_])[0]:>+16.3f} [{spearmanr(u[v], u[t_])[1]:.3f}]" for t_ in cibles))
    print("\nIdem en retirant l'effet territoire (moyenne du jeu) :")
    for v in ["part_sans_voiture", "part_2_voitures_plus"]:
        r = [spearmanr(u[v] - u.groupby("jeu")[v].transform("mean"), u[t_] - u.groupby("jeu")[t_].transform("mean")) for t_ in cibles]
        print(f"{v:<26}" + "".join(f"{x[0]:>+16.3f} [{x[1]:.3f}]" for x in r))
    print("\nIdem, à population locale égale (partial) :")
    for v in ["part_sans_voiture"]:
        lp = np.log1p(u.population_400m)
        for t_ in cibles:
            a = pd.Series(np.polyfit(lp, u[v], 1)[0] * lp + np.polyfit(lp, u[v], 1)[1], index=u.index)
            b = pd.Series(np.polyfit(lp, u[t_], 1)[0] * lp + np.polyfit(lp, u[t_], 1)[1], index=u.index)
            print(f"  {v} → {t_}: ρ = {spearmanr(u[v] - a, u[t_] - b)[0]:+.3f}")
    u["quartile_sans_voiture"] = pd.qcut(u.part_sans_voiture, 4, labels=["Q1 (très motorisé)", "Q2", "Q3", "Q4 (peu motorisé)"])
    q = u.groupby("quartile_sans_voiture", observed=True).agg(stations=("jeu", "size"), sans_voiture=("part_sans_voiture", "mean"),
                                                             pop_400m=("population_400m", "median"), occupation=("occupation", "mean"),
                                                             debuts_par_veh=("debuts_par_veh", "mean"))
    q["occupation"] = (100 * q.occupation).round(1)
    print("\nUsage par quartile de ménages sans voiture (commune) :\n", q.round(2).to_string())
    u.drop(columns=["x", "y", "quartile_sans_voiture"]).to_csv(Path(__file__).resolve().parent.parent / "donnees" / "stations_usage_motorisation.csv", index=False)


if __name__ == "__main__":
    if len(sys.argv) not in (2, 5):
        sys.exit(__doc__)
    main(*sys.argv[1:])
