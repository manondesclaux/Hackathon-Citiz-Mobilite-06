"""Étape 6b — Combien de véhicules par station, et lesquels ? D'après la pratique de Citiz et l'usage mesuré.

1. Pratique du réseau (GBFS, DATA clean/citiz_stations.csv) : véhicules par station, par réseau, dans les grandes
   villes comparables et selon la densité autour de la station.
2. Disponibilité (relevés Fabric, 7 h - 21 h) : part du temps où TOUTES les voitures d'une station sont réservées,
   selon le nombre de véhicules. Véhicules « toujours réservés » écartés (comme à l'étape 1).
3. Types de véhicules (flux GBFS vehicle_types de chaque réseau Citiz, mis en cache) : composition de la flotte, et
   occupation de journée de chaque véhicule comparée à la moyenne de SA station (stations mixtes seulement), ce qui
   neutralise l'effet du lieu. L'âge du véhicule n'est pas publié : il peut expliquer une partie des écarts.

Limites : Citiz met déjà plus de véhicules là où la demande est forte (pas une expérience contrôlée) ; 22 h de relevés
en semaine, sans week-end (les utilitaires servent surtout le week-end).
Sorties : decision/resultats/flotte_analyse.json, decision/resultats/flotte_types.csv
"""
import json

import numpy as np
import pandas as pd
import requests

from communs import CLEAN, DONNEES, RESULTATS, ROOT

CACHE = ROOT / "data" / "raw" / "citiz_types" / "vehicle_types.csv"
VILLES = {"Marseille": ("13055", "132"), "Toulouse": ("31555",), "Bordeaux": ("33063",), "Lyon": ("69123", "6938"),
          "Strasbourg": ("67482",), "Grenoble": ("38185",), "Lille": ("59350",), "Rennes": ("35238",), "Nantes": ("44109",)}


def types_vehicules():
    if CACHE.exists():
        return pd.read_csv(CACHE, dtype={"vehicle_type_id": str})
    S = requests.Session()
    S.headers["User-Agent"] = "hackathon-citiz-epitech"
    txt = lambda x: x[0]["text"] if isinstance(x, list) and x else x
    rows = []
    for j in S.get("https://transport.data.gouv.fr/api/datasets", timeout=120).json():
        g = [r for r in j["resources"] if r.get("format") == "gbfs"]
        if "citiz" not in j["title"].lower() or not g:
            continue
        try:
            feeds = {f["name"]: f["url"] for f in S.get(g[0].get("original_url") or g[0]["url"], timeout=30).json()["data"]["feeds"]}
            vt = S.get(feeds["vehicle_types"], timeout=30).json()["data"]["vehicle_types"]
        except Exception as e:                                     # un flux en panne ne bloque pas les autres
            print(f"{j['slug']}: {e}")
            continue
        rows += [dict(jeu=j["slug"], vehicle_type_id=str(t["vehicle_type_id"]), propulsion=t.get("propulsion_type"),
                      marque=txt(t.get("make")), modele=txt(t.get("model"))) for t in vt]
    df = pd.DataFrame(rows)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE, index=False)
    return df


def categorie(marque, modele):
    m = f"{marque} {modele}".lower()
    if any(k in m for k in ["kangoo", "trafic", "jumpy", "berlingo", "partner", "expert", "master", "vito", "proace",
                            "jogger", "fourgon", "minibus", "rifter", "combo", "doblo", "touran", "scenic"]):
        return "grand volume / utilitaire"
    if any(k in m for k in ["twingo", "aygo", "c1", "108", " up", "spring", "i10", "panda", "sandero", "yaris", "clio",
                            "208", "swift", "zoe", "zoé", "polo", "corsa", "micra", "c3", "i20", "500", "forfour", "jazz"]):
        return "citadine"
    return "compacte / berline / SUV"


def ic95(x):
    x = x.dropna()
    m, se = x.mean(), x.std() / np.sqrt(len(x))
    return {"ecart_pts": round(100 * m, 1), "ic95": [round(100 * (m - 1.96 * se), 1), round(100 * (m + 1.96 * se), 1)], "n": int(len(x))}


# ---------------------------------------------------------------- 1. pratique du réseau
cz = pd.read_csv(CLEAN / "citiz_stations.csv", dtype={"commune_code": str})
cz = cz[~cz.flex & ~cz.sans_vehicule]
repartition = lambda s: {str(int(k)) + (" et plus" if k == 3 else ""): round(float(v), 3)
                         for k, v in s.clip(upper=3).value_counts(normalize=True).sort_index().items()}
pratique = {"reseau": {"stations": int(len(cz)), "vehicules_par_station": round(float(cz.n_vehicles.mean()), 2),
                       "repartition": repartition(cz.n_vehicles)}, "villes": {}}
for v, pre in VILLES.items():
    s = cz[cz.commune_code.fillna("").str.startswith(pre)]
    if len(s):
        pratique["villes"][v] = {"stations": int(len(s)), "vehicules_par_station": round(float(s.n_vehicles.mean()), 2),
                                 "repartition": repartition(s.n_vehicles)}
st = pd.read_csv(DONNEES / "variables_stations.csv")
st["classe"] = pd.cut(st.pop_400m, [0, 3000, 6000, 9000, 12000, 1e9], labels=["<3 000", "3-6 000", "6-9 000", "9-12 000", ">12 000"])
pratique["selon_habitants_400m"] = {str(k): {"stations": int(len(g)), "vehicules_par_station": round(float(g.vehicules.mean()), 2),
                                             "part_1_vehicule": round(float((g.vehicules == 1).mean()), 2)}
                                    for k, g in st.groupby("classe", observed=True)}

# ---------------------------------------------------------------- 2. disponibilité selon la taille de station
d = pd.read_parquet(ROOT / "releves_fabric" / "citiz_releves.parquet")
d["releve_utc"] = pd.to_datetime(d.releve_utc, utc=True)
d = d[d.groupby("releve_utc").vehicle_id.transform("size") >= 2600]
occ_tot = d.groupby(["jeu", "vehicle_id"]).is_reserved.transform("mean")
d = d[occ_tot < 1]
d["h"] = d.releve_utc.dt.tz_convert("Europe/Paris").dt.hour
j = d[d.h.between(7, 20)]
s = j.groupby(["jeu", "station_id", "releve_utc"]).agg(n=("vehicle_id", "size"), res=("is_reserved", "sum")).reset_index()
s["vide"] = s.res == s.n
s["taille"] = s.groupby(["jeu", "station_id"]).n.transform("max").clip(upper=4)
par_station = s.groupby(["jeu", "station_id", "taille"]).vide.mean().reset_index()
dispo = {str(int(k)): {"stations": int(len(g)), "rupture_part_du_temps": round(float(s[s.taille == k].vide.mean()), 3),
                       "part_stations_vides_plus_15pct": round(float((g.vide > 0.15).mean()), 3)}
         for k, g in par_station.groupby("taille")}

# ---------------------------------------------------------------- 3. types de véhicules
ty = types_vehicules()
v = d.groupby(["jeu", "vehicle_id"]).agg(type=("vehicle_type_id", "first"), station=("station_id", "first")).reset_index()
v = v.join(j.groupby(["jeu", "vehicle_id"]).is_reserved.mean().rename("occ"), on=["jeu", "vehicle_id"])
v = v.merge(ty, left_on=["jeu", "type"], right_on=["jeu", "vehicle_type_id"], how="left")
v["motorisation"] = v.propulsion.map({"combustion": "thermique", "hybrid": "hybride", "electric": "électrique"}).fillna("autre")
v["categorie"] = [categorie(a, b) for a, b in zip(v.marque, v.modele)]
v["ecart_station"] = v.occ - v.groupby(["jeu", "station"]).occ.transform("mean")
ecarts = {}
for col in ["motorisation", "categorie"]:
    mixte = v.groupby(["jeu", "station"])[col].transform("nunique") > 1
    ecarts[col] = {k: ic95(g.ecart_station) for k, g in v[mixte].groupby(col) if len(g) >= 20}
compo = lambda w: {"motorisation": (w.motorisation.value_counts(normalize=True) * 100).round(1).to_dict(),
                   "categorie": (w.categorie.value_counts(normalize=True) * 100).round(1).to_dict(),
                   "modeles": (w.marque + " " + w.modele).value_counts().head(6).to_dict()}
modeles = (v.assign(modele_complet=v.marque + " " + v.modele).groupby(["modele_complet", "motorisation", "categorie"])
           .agg(vehicules=("vehicle_id", "size"), occupation_jour=("occ", "mean")).reset_index()
           .sort_values("vehicules", ascending=False))
modeles.round(3).to_csv(RESULTATS / "flotte_types.csv", index=False)

sortie = {
    "pratique_citiz": pratique, "disponibilite_selon_taille": dispo,
    "flotte": {"reseau": compo(v), "provence": compo(v[v.jeu == "citiz-autopartage-provence"])},
    "ecart_occupation_intra_station": ecarts,
    "recommandation": {
        "vehicules_par_station": 2,
        "regle": "2 au lancement ; +1 si la station est entièrement réservée plus de 15 % du temps de journée pendant 2 semaines ; −1 si l'occupation par véhicule reste sous 15 %",
        "type_socle": "citadine hybride (catégorie Toyota Yaris / Renault Clio hybride)",
        "electrique": "test dans 1 ou 2 stations proches de bornes publiques (ex-Mobilize Share), non généralisé : écart non significatif",
        "grand_volume": "pas au lancement ; à réévaluer avec des relevés de week-end",
    },
    "limites": ["Citiz place déjà plus de véhicules là où la demande est forte : comparaison non contrôlée.",
                "22 h de relevés en semaine, sans week-end ni été.",
                "L'âge des véhicules n'est pas publié : les hybrides, plus récents, peuvent être préférés pour cette raison."],
}
(RESULTATS / "flotte_analyse.json").write_text(json.dumps(sortie, ensure_ascii=False, indent=2))
print(json.dumps({k: sortie[k] for k in ["disponibilite_selon_taille", "ecart_occupation_intra_station", "recommandation"]},
                 ensure_ascii=False, indent=2))
print(json.dumps(pratique["villes"], ensure_ascii=False))
