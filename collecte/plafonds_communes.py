"""Plafond de nouvelles stations par commune, d'après les communes Citiz de même densité.

Densité = habitants par km² de carreaux habités (Filosofi, 0,04 km² par carreau de 200 m).
Pour chaque classe de densité, on mesure le nombre de stations Citiz pour 10 000 habitants dans les communes déjà
équipées (taux médian), puis plafond d'une commune = taux médian de sa classe × population / 10 000, arrondi
(minimum 2). Écrit donnees/plafonds_communes.csv.

Usage : python collecte/plafonds_communes.py DOSSIER_CITIZ carreaux_200m_met.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from analyse_citiz import charger  # noqa: E402

CLASSES = [0, 1500, 3000, 5000, 7500, 10000, 1e9]
NOMS = ["<1 500", "1 500-3 000", "3 000-5 000", "5 000-7 500", "7 500-10 000", ">10 000"]


def main(citiz, csv):
    c = pd.read_csv(csv, usecols=["idcar_200m", "lcog_geo", "ind"], dtype={"lcog_geo": str})
    e = c.idcar_200m.str.extract(r"RES200mN(\d+)E(\d+)").astype(float)
    c["y"], c["x"] = e[0] + 100, e[1] + 100
    c["code_commune"] = c.lcog_geo.str[:5]
    com = c.groupby("code_commune").agg(population=("ind", "sum"), carreaux=("ind", "size"))
    com["densite_bati"] = com.population / (com.carreaux * 0.04)          # hab/km² de surface habitée
    com["classe_densite"] = pd.cut(com.densite_bati, CLASSES, labels=NOMS)

    st, _, _ = charger(Path(citiz))
    st = st.drop_duplicates(["lat", "lon"])
    st = st[st.lat.between(41, 52) & st.lon.between(-6, 10)]
    x, y = Transformer.from_crs(4326, 3035, always_xy=True).transform(st.lon.values, st.lat.values)
    _, idx = cKDTree(c[["x", "y"]].to_numpy()).query(np.c_[x, y])
    n = pd.Series(c.code_commune.iloc[idx].to_numpy()).value_counts().rename("stations_citiz")
    com = com.join(n).fillna({"stations_citiz": 0})
    com["stations_pour_10k"] = 10000 * com.stations_citiz / com.population

    eq = com[(com.stations_citiz > 0) & (com.population >= 5000)]           # communes équipées, assez grandes
    taux = eq.groupby("classe_densite", observed=True).agg(communes=("population", "size"), pop_mediane=("population", "median"),
                                                          stations_mediane=("stations_citiz", "median"),
                                                          taux_p25=("stations_pour_10k", lambda s: s.quantile(.25)),
                                                          taux_median=("stations_pour_10k", "median"),
                                                          taux_p75=("stations_pour_10k", lambda s: s.quantile(.75)))
    print("Communes Citiz (≥5 000 habitants) par classe de densité du bâti :\n", taux.round(2).to_string())
    com = com.join(taux.taux_median.rename("taux_classe"), on="classe_densite")
    com["plafond"] = np.maximum(2, np.round(com.taux_classe * com.population / 10000)).astype("Int64")
    com.reset_index().to_csv(Path(__file__).resolve().parent.parent / "donnees" / "plafonds_communes.csv", index=False)
    am = com[com.index.str.startswith("06")]
    ref = {"06088": "Nice", "06029": "Cannes", "06004": "Antibes", "06083": "Menton", "06027": "Le Cannet", "06123": "Cagnes-sur-Mer",
           "06155": "Vallauris", "06018": "Beausoleil", "06069": "Grasse"}
    print("\nAlpes-Maritimes — communes clés :")
    print(am.loc[[k for k in ref if k in am.index], ["population", "densite_bati", "classe_densite", "taux_classe", "plafond"]]
          .rename(index=ref).round(1).to_string())


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
