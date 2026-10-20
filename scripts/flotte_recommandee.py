"""Nombre et type de véhicules recommandés par site — version prudente, proche de la pratique du réseau Citiz.

Réseau existant : 49 % des stations ont 1 voiture, 37 % en ont 2, seulement 14 % en ont 3 ou plus et 5 % en ont 4 ou plus.
Règle : 2 véhicules par site, 3 si la population à 400 m dépasse 9 000 habitants, jamais 4 au démarrage.
(À 2 véhicules la rupture de disponibilité en journée est ≈14 %, à 3 ≈10 %.) À ajuster ensuite avec l'usage réel :
+1 véhicule si la station est vide (tout réservé) plus de 15 % de la journée sur 2 semaines, −1 si l'occupation par véhicule < 15 %.
Types : modèles à plus fort taux de véhicules actifs (sorties/vehicules_succes.csv).

Usage : python scripts/flotte_recommandee.py     (après ordre_installation.py)
"""
import numpy as np
import pandas as pd

SEUIL_3_VEHICULES = 9000


def composition(n: int) -> str:
    base = {2: "2 × Toyota Yaris hybride",
            3: "2 × Toyota Yaris hybride + 1 × Clio hybride ou Peugeot 208"}
    return base[n]


def main():
    o = pd.read_csv("sorties/ordre_installation.csv")
    o["vehicules"] = np.where(o.population_400m >= SEUIL_3_VEHICULES, 3, 2)
    o["composition"] = o.vehicules.map(composition)
    o["habitants_par_vehicule"] = (o.population_400m / o.vehicules).round(0)
    o.to_csv("sorties/flotte_recommandee.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 80)
    print(o[["ordre", "commune", "arret_proche", "population_400m", "vehicules", "habitants_par_vehicule", "composition"]]
          .round(0).to_string(index=False))
    print("\nTotal véhicules :", o.vehicules.sum(), "| répartition :", o.vehicules.value_counts().sort_index().to_dict())
    print(o.groupby("vague").vehicules.agg(["sum", "count"]).rename(columns={"sum": "véhicules", "count": "stations"}).to_string())
    print(f"Moyenne : {o.vehicules.mean():.1f} véhicules par station (réseau existant : médiane 2, moyenne 1,7)")


if __name__ == "__main__":
    main()
