"""Ordre d'installation des 20 sites (sorties/vingt_stations_azur.csv, produit par vingt_stations_azur.py --repartition).

⚠ Script d'exploration conservé pour l'historique. Le modèle d'usage utilisé ici (régression linéaire, R² = 0,03
sur les données d'apprentissage, sans validation) ne distingue pas les sites. La recommandation de référence est
produite par decision/ (modèle de potentiel validé hors échantillon, coûts et budget) : voir decision/README.md.

À chaque étape on choisit le site qui maximise :
    0,6 · succès attendu (occupation prédite, normalisée) + 0,2 · transports + 0,2 · effet de grappe
Effet de grappe = nombre de sites déjà installés à moins de 1,5 km (saturé à 2) : sur les stations existantes,
les véhicules entourés d'autres véhicules Citiz sont plus souvent réservés. Le premier site est donc le meilleur
succès attendu, puis on étend autour des sites déjà en place.

Usage : python scripts/ordre_installation.py [cout_par_station_eur=50000]
Sorties : sorties/ordre_installation.csv, sorties/ordre_installation.html
"""
import sys

import folium
import numpy as np
import pandas as pd

W = (0.6, 0.2, 0.2)
GRAPPE_M = 1500
VAGUES = [(1, 7, "Vague 1 — noyau"), (8, 14, "Vague 2 — extension"), (15, 20, "Vague 3 — élargissement")]


def dist_m(a, b):
    return np.hypot((a.lat - b.lat) * 111000, (a.lon - b.lon) * 111000 * np.cos(np.radians(a.lat)))


def main(cout):
    s = pd.read_csv("sorties/vingt_stations_azur.csv")
    s["succes"] = (s.usage_attendu - s.usage_attendu.min()) / (s.usage_attendu.max() - s.usage_attendu.min())
    t = np.log1p(s.arrets_400m); s["transport"] = t / t.max()
    reste, ordre = list(s.index), []
    while reste:
        sc = {}
        for i in reste:
            voisins = sum(dist_m(s.loc[i], s.loc[j]) <= GRAPPE_M for j in ordre)
            sc[i] = (W[0] * s.succes[i] + W[1] * s.transport[i] + W[2] * min(voisins, 2) / 2, voisins)
        i = max(reste, key=lambda k: sc[k][0])
        s.loc[i, "score_ordre"] = 100 * sc[i][0]; s.loc[i, "voisins_deja_installes"] = sc[i][1]
        ordre.append(i); reste.remove(i)
    o = s.loc[ordre].copy().reset_index(drop=True)
    o.insert(0, "ordre", range(1, len(o) + 1))
    o["vague"] = [next(n for a, b, n in VAGUES if a <= k <= b) for k in o.ordre]
    o["cout_cumule_eur"] = o.ordre * cout
    o["habitants_cumules"] = o.habitants_supplementaires.cumsum().round(0)
    cols = ["ordre", "vague", "commune", "arret_proche", "lat", "lon", "usage_attendu", "population_400m", "habitants_supplementaires",
            "arrets_400m", "part_sans_voiture", "voisins_deja_installes", "score_ordre", "cout_cumule_eur", "habitants_cumules"]
    o[cols].round(1).to_csv("sorties/ordre_installation.csv", index=False)
    pd.set_option("display.width", 250)
    print(o[["ordre", "vague", "commune", "arret_proche", "usage_attendu", "habitants_supplementaires", "arrets_400m",
             "voisins_deja_installes", "score_ordre", "cout_cumule_eur"]].round(1).to_string(index=False))
    for a, b, n in VAGUES:
        v = o[(o.ordre >= a) & (o.ordre <= b)]
        print(f"\n{n} : {len(v)} sites | {v.habitants_supplementaires.sum():,.0f} habitants | occupation attendue {v.usage_attendu.mean():.1f} % "
              f"| communes : {v.commune.value_counts().to_dict()} | coût {len(v) * cout:,.0f} €")
    m = folium.Map(location=[43.68, 7.15], zoom_start=10, tiles=None)
    folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
                     attr="Tiles © Esri", control=False).add_to(m)
    coul = {"Vague 1 — noyau": "#b91c1c", "Vague 2 — extension": "#ea580c", "Vague 3 — élargissement": "#2563eb"}
    for n in coul:
        fg = folium.FeatureGroup(name=n)
        for r in o[o.vague == n].itertuples():
            folium.Circle([r.lat, r.lon], radius=400, color=coul[n], fill=True, fill_opacity=0.10, weight=1).add_to(fg)
            folium.Marker([r.lat, r.lon], tooltip=f"#{r.ordre} {r.commune} — {r.arret_proche}",
                          popup=(f"<b>#{r.ordre} {r.commune}</b> ({r.vague})<br>repère : {r.arret_proche}<br>occupation attendue ≈ {r.usage_attendu:.0f} %"
                                 f"<br>{r.habitants_supplementaires:,.0f} habitants à 400 m · {r.arrets_400m} pôles d'arrêts"
                                 f"<br>sites déjà installés à ≤1,5 km : {int(r.voisins_deja_installes)}"),
                          icon=folium.DivIcon(html=f'<div style="background:{coul[n]};color:white;border-radius:50%;width:26px;height:26px;'
                                                   f'text-align:center;line-height:26px;font-weight:bold">{r.ordre}</div>')).add_to(fg)
        fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save("sorties/ordre_installation.html")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 50000)
