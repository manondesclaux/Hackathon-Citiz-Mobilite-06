"""Indicateurs d'utilisation des véhicules Citiz à partir des relevés collectés par citiz_collecte.py.

Usage :
    python scripts/citiz_usage.py DOSSIER_RELEVES

Signaux (le flux n'expose pas les trajets, ce sont des proxys à valider sur plusieurs jours) :
  - réservation   : is_reserved passe de False à True entre deux relevés ;
  - taux d'occupation : part des relevés où le véhicule est réservé ;
  - déplacement   : le véhicule change de station_id ;
  - conso         : baisse de fuel_pct entre deux relevés.
"""
import sys

import pandas as pd

df = pd.read_parquet(sys.argv[1] if len(sys.argv) > 1 else "releves_citiz")
df = df.sort_values(["jeu", "vehicle_id", "releve_utc"])
g = df.groupby(["jeu", "vehicle_id"])
prec = g.is_reserved.shift()
df["debut_resa"] = (prec == False) & df.is_reserved  # noqa: E712  (ignore le 1er relevé)
df["deplace"] = g.station_id.shift().notna() & (df.station_id != g.station_id.shift())
df["baisse_fuel"] = (df.fuel_pct - g.fuel_pct.shift()) < -0.02
df["heure"] = df.releve_utc.dt.tz_convert("Europe/Paris").dt.hour

n = df.releve_utc.nunique()
duree = (df.releve_utc.max() - df.releve_utc.min()).total_seconds() / 3600
print(f"{n} relevés sur {duree:.1f} h, {df.groupby(['jeu', 'vehicle_id']).ngroups} véhicules\n")
if n < 2:
    print("Un seul relevé : taux d'occupation instantané uniquement (planifier la collecte pour avoir plus).\n")

par_jeu = df.groupby("jeu").agg(vehicules=("vehicle_id", "nunique"), occupation_pct=("is_reserved", "mean"),
                                 debuts_resa=("debut_resa", "sum"), deplacements=("deplace", "sum"))
par_jeu["occupation_pct"] = (100 * par_jeu.occupation_pct).round(1)
print(par_jeu.sort_values("occupation_pct", ascending=False).to_string(), "\n")

print("Occupation par heure (Paris) :\n", (100 * df.groupby("heure").is_reserved.mean()).round(1).to_string(), "\n")

v = df.groupby(["jeu", "vehicle_id"]).agg(occ=("is_reserved", "mean"), resas=("debut_resa", "sum"))
if n >= 288:  # au moins ~1 jour de relevés
    print("Véhicules jamais réservés :", int((v.occ == 0).sum()), "/", len(v))
print("Top stations par occupation :\n",
      (100 * df.groupby(["jeu", "station_id"]).is_reserved.mean()).round(1).sort_values(ascending=False).head(10).to_string())
