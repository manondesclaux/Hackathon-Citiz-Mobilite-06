"""Étape 1 — Cible d'usage par station Citiz, nettoyée, à partir des relevés GBFS collectés dans Microsoft Fabric.

Entrée : releves_fabric/citiz_releves.parquet (un relevé toutes les 15 min, vehicle_status de tous les flux Citiz)
Sortie : decision/donnees/usage_stations.csv, decision/resultats/qualite_cible.json

Ce que mesure le flux : `is_reserved` vaut vrai quand le véhicule est réservé (location en cours ou imminente).
Ce n'est pas un nombre de trajets. Nettoyage :
- relevés incomplets écartés (moins de 2 600 véhicules : un flux régional n'a pas répondu) ;
- véhicules « toujours réservés » sur toute la fenêtre écartés : location longue, immobilisation ou blocage
  administratif, impossible à distinguer d'une forte demande ;
- `is_disabled` n'est PAS utilisé : il vaut vrai pour 100 % des véhicules de certains flux (Grand Poitiers) et
  n'est pas corrélé à `is_reserved` ; c'est une convention propre à chaque flux, pas un état du véhicule ;
- l'occupation est mesurée en journée (7 h - 21 h, heure de Paris), là où se joue la demande.
Cible retenue : `occupation_jour` = part des relevés de journée où un véhicule de la station est réservé.
"""
import json

import pandas as pd

from communs import DONNEES, RESULTATS, ROOT

d = pd.read_parquet(ROOT / "releves_fabric" / "citiz_releves.parquet")
d["releve_utc"] = pd.to_datetime(d.releve_utc, utc=True)
n_brut = d.releve_utc.nunique()
complet = d.groupby("releve_utc").vehicle_id.transform("size") >= 2600
d = d[complet].sort_values(["jeu", "vehicle_id", "releve_utc"])
d["heure"] = d.releve_utc.dt.tz_convert("Europe/Paris").dt.hour

v = d.groupby(["jeu", "vehicle_id"]).is_reserved.agg(["mean", "size"])
toujours = v[v["mean"] == 1].index
d = d.set_index(["jeu", "vehicle_id"])
d["toujours_reserve"] = d.index.isin(toujours)
d = d.reset_index()
valide = d[~d.toujours_reserve]

d_jour = valide[valide.heure.between(7, 20)]
debut = (valide.groupby(["jeu", "vehicle_id"]).is_reserved.shift() == False) & valide.is_reserved  # noqa: E712
valide = valide.assign(debut=debut)
duree_j = (d.releve_utc.max() - d.releve_utc.min()).total_seconds() / 86400

s = valide.groupby(["jeu", "station_id"]).agg(vehicules=("vehicle_id", "nunique"), occupation=("is_reserved", "mean"),
                                              debuts=("debut", "sum"), lat=("lat", "median"), lon=("lon", "median"))
s["occupation_jour"] = d_jour.groupby(["jeu", "station_id"]).is_reserved.mean()
s["debuts_par_vehicule_jour"] = s.debuts / s.vehicules / duree_j
exclus = d[d.toujours_reserve].groupby(["jeu", "station_id"]).vehicle_id.nunique().rename("vehicules_exclus")
s = s.join(exclus).fillna({"vehicules_exclus": 0}).reset_index()
s = s.dropna(subset=["occupation_jour", "lat", "lon"])
s = s[s.lat.between(41, 52) & s.lon.between(-6, 10)]          # métropole (la grille INSEE utilisée est métropolitaine)
s.to_csv(DONNEES / "usage_stations.csv", index=False)

profil = (100 * d[~d.toujours_reserve].groupby("heure").is_reserved.mean()).round(1)
q = {
    "fenetre": [str(d.releve_utc.min()), str(d.releve_utc.max())],
    "duree_jours": round(duree_j, 2),
    "releves_bruts": int(n_brut), "releves_complets": int(d.releve_utc.nunique()),
    "vehicules": int(v.shape[0]), "vehicules_toujours_reserves_exclus": int(len(toujours)),
    "stations_avec_cible": int(len(s)), "reseaux": int(s.jeu.nunique()),
    "occupation_jour_moyenne": round(float(s.occupation_jour.mean()), 3),
    "stations_occupation_nulle": round(float((s.occupation_jour == 0).mean()), 3),
    "profil_horaire_pct": profil.to_dict(),
    "limites": ["Fenêtre de moins d'une journée, deux jours ouvrés d'octobre, sans week-end ni saison touristique.",
                "is_reserved n'est pas un trajet ; aucune durée ni recette n'est observée.",
                "Les stations à un seul véhicule ont une occupation très bruitée (0 ou 1 la plupart du temps)."],
}
(RESULTATS / "qualite_cible.json").write_text(json.dumps(q, ensure_ascii=False, indent=2))
print(json.dumps({k: q[k] for k in q if k != "profil_horaire_pct"}, ensure_ascii=False, indent=2))
