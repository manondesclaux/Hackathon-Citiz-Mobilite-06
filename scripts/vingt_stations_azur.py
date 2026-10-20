"""Sélectionne 20 sites candidats pour de nouvelles stations Citiz dans les Alpes-Maritimes.

⚠ Script d'exploration conservé pour l'historique. Le modèle d'usage utilisé ici (régression linéaire, R² = 0,03
sur les données d'apprentissage, sans validation) ne distingue pas les sites. La recommandation de référence est
produite par decision/ (modèle de potentiel validé hors échantillon, coûts et budget) : voir decision/README.md.

Lecture seule sur citiz_azur/results/candidats.csv. Critères tirés de l'usage observé des stations existantes :
  - l'usage observé monte avec la population à 400 m ET avec la part de ménages sans voiture de la commune
    (INSEE) : régression ajustée sur les stations existantes (sorties/stations_usage_motorisation.csv,
    produit par scripts/motorisation.py) ;
  - la concurrence n'est PAS pénalisée (elle accompagne la demande dans les données) ;
  - les transports servent de critère secondaire (non validé par les données d'usage) ;
  - un seul site par zone de 800 m, population jamais comptée deux fois ;
  - plafond par commune = nombre de stations typique des communes Citiz de même densité (scripts/plafonds_communes.py).

Usage : python scripts/vingt_stations_azur.py citiz_azur [N=20] [--repartition]
  --repartition : les N sites sont répartis entre communes au prorata de leur plafond (sinon le plafond est un simple maximum).
Prérequis : scripts/motorisation.py (motorisation + modèle d'usage) et scripts/plafonds_communes.py (plafond par commune)
Sorties : sorties/vingt_stations_azur.csv, sorties/vingt_stations_azur.html
"""
import sys
from pathlib import Path

import folium
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

R = 6371000


def modele_usage():
    """Occupation ~ a + b·ln(population 400 m) + c·(% ménages sans voiture), ajusté sur les stations existantes."""
    u = pd.read_csv("sorties/stations_usage_motorisation.csv")
    u = u[u.population_400m > 0]
    X = np.c_[np.ones(len(u)), np.log(u.population_400m), u.part_sans_voiture]
    b, *_ = np.linalg.lstsq(X, 100 * u.occupation, rcond=None)
    r = 100 * u.occupation - X @ b
    r2 = 1 - (r @ r) / (((100 * u.occupation) - (100 * u.occupation).mean()) ** 2).sum()
    print(f"Modèle d'usage : occupation(%) = {b[0]:.1f} + {b[1]:.2f}·ln(pop) + {b[2]:.3f}·sans_voiture | R² = {r2:.3f} | {len(u)} stations")
    return b


def main(azur, n=20, sep=800, repartition=False):
    c = pd.read_csv(Path(azur) / "results/candidats.csv", dtype={"code_commune": str})
    c = c[~c.already_citiz & (c.population_400m >= 3000)].copy().reset_index(drop=True)
    mot = pd.read_csv("sorties/motorisation_communes.csv", dtype={"code_commune": str})
    c = c.merge(mot, left_on="code_commune", right_on="code_commune", how="left")
    c["part_sans_voiture"] = c.part_sans_voiture.fillna(mot.part_sans_voiture.median())
    plaf = pd.read_csv("sorties/plafonds_communes.csv", dtype={"code_commune": str}).set_index("code_commune").plafond
    c["plafond"] = c.code_commune.map(plaf).fillna(2).astype(int)
    if repartition:   # quota = part de la commune dans la somme des plafonds des communes candidates, au moins 1
        un = c.drop_duplicates("code_commune")
        quota = (n * un.set_index("code_commune").plafond / un.plafond.sum()).clip(lower=1)
        c["plafond"] = np.ceil(c.code_commune.map(quota)).astype(int)
        print("Quotas par commune (ceil de n × plafond / Σ plafonds) :",
              {r.commune: int(r.plafond) for r in c.drop_duplicates("code_commune").sort_values("plafond", ascending=False).head(10).itertuples()})
    b = modele_usage()
    c["usage_attendu"] = b[0] + b[1] * np.log(c.population_400m) + b[2] * c.part_sans_voiture
    us = c.usage_attendu
    c["s_usage"] = (us - us.min()) / (us.max() - us.min())
    t = np.log1p(c.arrets_400m); c["s_transport"] = t / t.max()
    c["score"] = 100 * (0.8 * c.s_usage + 0.2 * c.s_transport)
    print(f"{len(c)} candidats ≥3 000 habitants à 400 m (hors 800 m d'une station Citiz)")

    xy = np.radians(c[["lat", "lon"]].to_numpy())
    tree = BallTree(xy, metric="haversine")
    cover = tree.query_radius(xy, r=400 / R)          # voisins à 400 m, pour la population commune
    pop = c.population.to_numpy()
    couvert = np.zeros(len(c), bool)                  # carreaux déjà comptés par un site retenu
    choisis, par_commune = [], {}
    restant = set(range(len(c)))
    while len(choisis) < n and restant:
        best, best_u = None, -1
        for i in restant:
            if par_commune.get(c.commune[i], 0) >= c.plafond[i]:
                continue
            ix = cover[i]
            gain = pop[ix][~couvert[ix]].sum()
            u = c.score[i] * gain / max(c.population_400m[i], 1)   # score pondéré par la part de population nouvelle
            if u > best_u:
                best, best_u, best_gain = i, u, gain
        if best is None:
            break
        choisis.append((best, best_gain)); par_commune[c.commune[best]] = par_commune.get(c.commune[best], 0) + 1
        couvert[cover[best]] = True
        # écarter les candidats à moins de 800 m du site retenu
        for j in tree.query_radius(xy[[best]], r=sep / R)[0]:
            restant.discard(j)
    s = c.loc[[i for i, _ in choisis]].copy()
    s["habitants_supplementaires"] = [g for _, g in choisis]
    s.insert(0, "rang", range(1, len(s) + 1))
    cols = ["rang", "commune", "arret_proche", "lat", "lon", "population_400m", "habitants_supplementaires", "arrets_400m",
            "stations_concurrentes_400m", "vehicules_concurrents_400m", "part_sans_voiture", "plafond", "usage_attendu", "score", "distance_arret_m"]
    s[cols].round(2).to_csv("sorties/vingt_stations_azur.csv", index=False)
    pd.set_option("display.width", 220)
    print(s[["rang", "commune", "arret_proche", "population_400m", "habitants_supplementaires", "arrets_400m",
             "stations_concurrentes_400m", "vehicules_concurrents_400m", "part_sans_voiture", "usage_attendu", "score"]].round(1).to_string(index=False))
    print(f"\nHabitants supplémentaires (sans double compte) : {s.habitants_supplementaires.sum():,.0f}")
    print("Répartition par commune :", s.commune.value_counts().to_dict())
    top10 = pd.read_csv(Path(azur) / "results/top10.csv")
    print("Sites communs avec le top 10 de citiz_azur (≤200 m) :",
          sum(((np.hypot((top10.lat - r.lat) * 111000, (top10.lon - r.lon) * 111000 * np.cos(np.radians(r.lat)))) < 200).any()
              for r in s.itertuples()))

    m = folium.Map(location=[43.70, 7.20], zoom_start=10, tiles=None)
    folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
                     attr="Tiles © Esri", control=False).add_to(m)
    for r in s.itertuples():
        folium.Circle([r.lat, r.lon], radius=400, color="#167d9a", fill=True, fill_opacity=0.10, weight=1).add_to(m)
        folium.Marker([r.lat, r.lon], tooltip=f"#{r.rang} {r.commune} — {r.arret_proche}",
                      popup=(f"<b>#{r.rang} {r.commune}</b><br>repère : {r.arret_proche}<br>{r.population_400m:,.0f} hab. à 400 m "
                             f"(+{r.habitants_supplementaires:,.0f} nouveaux)<br>{r.arrets_400m} pôles d'arrêts · "
                             f"concurrence : {r.stations_concurrentes_400m} stations, {r.vehicules_concurrents_400m} véhicules"
                             f"<br>ménages sans voiture (commune) : {r.part_sans_voiture:.0f} %"
                             f"<br>occupation attendue ≈ {r.usage_attendu:.0f} %"),
                      icon=folium.DivIcon(html=f'<div style="background:#143f63;color:white;border-radius:50%;width:26px;height:26px;'
                                               f'text-align:center;line-height:26px;font-weight:bold">{r.rang}</div>')).add_to(m)
    m.save("sorties/vingt_stations_azur.html")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0], int(args[1]) if len(args) > 1 else 20, repartition="--repartition" in sys.argv)
