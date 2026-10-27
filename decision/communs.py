"""Fonctions partagées par le pipeline de décision (decision/0*_*.py).

Toutes les distances sont calculées en mètres dans la projection européenne EPSG:3035 (celle de la grille INSEE),
jamais en degrés. Un même calcul de variables sert aux stations Citiz existantes (apprentissage) et aux emplacements
candidats des Alpes-Maritimes (prédiction) : c'est la condition pour que le modèle soit applicable.
"""
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent.parent
DEC = ROOT / "decision"
DONNEES = DEC / "donnees"            # tables dérivées, légères, versionnées
RESULTATS = DEC / "resultats"        # sorties lisibles (CSV, JSON, cartes)
INSEE = ROOT / "data_insee"          # archives INSEE nationales (non versionnées, voir README)
CLEAN = ROOT / "donnees"
for d in (DONNEES, RESULTATS):
    d.mkdir(parents=True, exist_ok=True)

RAYON = 400            # ~5 minutes de marche (4,8 km/h)
R_REQ = RAYON + 1      # rayon de recherche : inclut les carreaux dont le centre est à 400 m pile, malgré les arrondis
RAYON_CONTEXTE = 1500  # densité urbaine du quartier
DEP = "06"

to3035 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
to4326 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)

# Opérateurs de free-floating : leurs « stations » GBFS sont des zones de stationnement conseillées, pas des
# stations de vélos en libre-service (VLS). Les compter comme des stations gonfle l'offre (≈ 26 700 points sur 32 000).
FREE_FLOATING = re.compile(r"dott|pony|voi\b|voi technology|lime|tier|bird|bolt|cooltra|yego|cityscoot|trottinette", re.I)


def xy(lon, lat):
    x, y = to3035.transform(np.asarray(lon, float), np.asarray(lat, float))
    return np.c_[x, y]


def type_station_velo(df):
    """« VLS » pour une vraie station de vélos en libre-service, « zone free-floating » sinon."""
    txt = df.operateur.fillna("") + " " + df.reseau.fillna("")
    return np.where(txt.str.contains(FREE_FLOATING), "zone free-floating", "VLS")


# ---------------------------------------------------------------- Carroyage INSEE Filosofi 2021 (200 m)
COLS_CARREAUX = ["idcar_200m", "i_est_200", "lcog_geo", "ind", "men", "men_pauv", "men_1ind", "men_prop", "men_coll",
                 "ind_snv", "log_soc", "ind_0_3", "ind_4_5", "ind_6_10", "ind_11_17", "ind_18_24", "ind_25_39",
                 "ind_40_54", "ind_55_64", "ind_65_79", "ind_80p"]


def carreaux():
    """Carreaux habités de France métropolitaine, centres en EPSG:3035. Mis en cache en Parquet (data_insee/)."""
    cache = INSEE / "carreaux_200m_met.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    zpath = INSEE / "carreaux_200m_2021.zip"
    if not zpath.exists():
        raise SystemExit(f"Archive absente : {zpath}\nTélécharger https://www.insee.fr/fr/statistiques/8735162 "
                         "(carreaux 200 m, CSV) et la placer dans data_insee/.")
    with zipfile.ZipFile(zpath) as z:
        c = pd.read_csv(z.open("carreaux_200m_met.csv"), usecols=COLS_CARREAUX, dtype={"lcog_geo": str})
    e = c.idcar_200m.str.extract(r"N(\d+)E(\d+)").astype(float)
    c["y"], c["x"] = e[0] + 100, e[1] + 100                      # centre du carreau
    c["code_commune"] = c.lcog_geo.str[:5]                      # première commune listée
    c["ind_25_54"] = c.ind_25_39 + c.ind_40_54
    c["ind_65p"] = c.ind_65_79 + c.ind_80p
    c = c.drop(columns=["lcog_geo", "ind_0_3", "ind_4_5", "ind_6_10", "ind_11_17", "ind_25_39", "ind_40_54",
                        "ind_55_64", "ind_65_79", "ind_80p"])
    c.to_parquet(cache, index=False)
    return c


def logement_communes():
    """Part de résidences secondaires par commune (INSEE, logement 2022) : proxy de la population touristique."""
    with zipfile.ZipFile(INSEE / "logement_2022.zip") as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.lower().startswith("meta")][0]
        lg = pd.read_csv(z.open(name), sep=";", dtype={"CODGEO": str}, usecols=["CODGEO", "P22_LOG", "P22_RSECOCC"])
    lg = lg[lg.P22_LOG > 0]
    return (lg.P22_RSECOCC / lg.P22_LOG).rename("part_res_secondaires").set_axis(lg.CODGEO)


def motorisation_communes():
    m = pd.read_csv(CLEAN / "motorisation_communes.csv", dtype={"code_commune": str})
    return m.set_index("code_commune").part_sans_voiture / 100


def arrets():
    s = pd.read_csv(CLEAN / "model" / "transport_stops.csv.gz")
    return s


def velos():
    v = pd.read_csv(CLEAN / "model" / "bike_stations.csv")
    v["type_station"] = type_station_velo(v)
    return v


# ---------------------------------------------------------------- Variables autour d'un point
VARIABLES = ["log_pop_400m", "log_pop_1500m", "part_25_54", "part_18_24", "part_65p", "part_men_1pers",
             "part_men_collectif", "part_men_proprietaires", "part_men_pauvres", "part_log_sociaux",
             "niveau_vie_k", "log_arrets_400m", "log_dist_gare", "vls_400m", "part_sans_voiture_commune",
             "part_res_secondaires_commune"]


def variables(points, car=None, stops=None, vls=None, mot=None, rs=None):
    """Variables explicatives pour des points (colonnes lon, lat). Mêmes définitions partout.

    Population et structure : carreaux dont le centre est à <= 400 m (et 1 500 m pour le contexte).
    Offre : arrêts de transport en commun dédoublonnés, gares, vraies stations VLS (free-floating exclu).
    Commune : motorisation des ménages (INSEE 2021) et résidences secondaires (INSEE 2022) de la commune du carreau
    le plus proche. Ce sont des moyennes communales : elles décrivent le contexte, pas le quartier.
    """
    car = carreaux() if car is None else car
    stops = arrets() if stops is None else stops
    vls = velos() if vls is None else vls
    mot = motorisation_communes() if mot is None else mot
    rs = logement_communes() if rs is None else rs

    P = xy(points.lon, points.lat)
    tree = cKDTree(car[["x", "y"]].to_numpy())
    out = pd.DataFrame(index=points.index)
    sums = {c: car[c].to_numpy() for c in ["ind", "men", "men_pauv", "men_1ind", "men_prop", "men_coll", "ind_snv",
                                           "log_soc", "ind_18_24", "ind_25_54", "ind_65p"]}
    imp = (car.i_est_200.to_numpy() == 1) * car.ind.to_numpy()
    voisins = tree.query_ball_point(P, r=R_REQ)
    agg = {k: np.array([v[i].sum() for i in voisins]) for k, v in sums.items()}
    out["pop_400m"] = agg["ind"]
    out["part_pop_imputee"] = np.array([imp[i].sum() for i in voisins]) / np.where(agg["ind"] > 0, agg["ind"], np.nan)
    ctx = tree.query_ball_point(P, r=RAYON_CONTEXTE)
    out["pop_1500m"] = np.array([sums["ind"][i].sum() for i in ctx])
    ind = np.where(agg["ind"] > 0, agg["ind"], np.nan)
    men = np.where(agg["men"] > 0, agg["men"], np.nan)
    out["part_25_54"] = agg["ind_25_54"] / ind
    out["part_18_24"] = agg["ind_18_24"] / ind
    out["part_65p"] = agg["ind_65p"] / ind
    out["part_men_1pers"] = agg["men_1ind"] / men
    out["part_men_collectif"] = agg["men_coll"] / men
    out["part_men_proprietaires"] = agg["men_prop"] / men
    out["part_men_pauvres"] = agg["men_pauv"] / men
    out["part_log_sociaux"] = agg["log_soc"] / men
    out["niveau_vie_k"] = agg["ind_snv"] / ind / 1000

    S = stops[["x", "y"]].to_numpy()
    out["arrets_400m"] = [len(i) for i in cKDTree(S).query_ball_point(P, r=R_REQ)]
    g = stops[stops["mode"] == "train"]
    out["dist_gare_m"] = cKDTree(g[["x", "y"]].to_numpy()).query(P)[0]
    dist_arret, idx_arret = cKDTree(S).query(P)
    out["dist_arret_m"] = dist_arret
    out["arret_proche"] = stops.nom.to_numpy()[idx_arret]
    V = xy(vls[vls.type_station == "VLS"].lon, vls[vls.type_station == "VLS"].lat)
    out["vls_400m"] = [len(i) for i in cKDTree(V).query_ball_point(P, r=R_REQ)]

    _, near = tree.query(P)
    com = car.code_commune.to_numpy()[near]
    out["code_commune"] = com
    out["part_sans_voiture_commune"] = pd.Series(com).map(mot).to_numpy()
    out["part_res_secondaires_commune"] = pd.Series(com).map(rs).to_numpy()

    out["log_pop_400m"] = np.log1p(out.pop_400m)
    out["log_pop_1500m"] = np.log1p(out.pop_1500m)
    out["log_arrets_400m"] = np.log1p(out.arrets_400m)
    out["log_dist_gare"] = np.log1p(out.dist_gare_m)
    return out
