"""Étape 9 — Carte de démonstration unique (objectifs 1, 2 et 3), à ouvrir dans un navigateur.

Couches (activables séparément) :
- Objectif 1 : carreaux de 200 m colorés du plus froid au plus chaud selon les options de mobilité à 5 min de marche
  pour 1 000 habitants (quintiles) ;
- Objectif 2 : points d'accès par type (arrêts, gares, zones free-floating, Getaround, scooters), taille selon les
  habitants desservis à 400 m ;
- Objectif 3 : stations Citiz recommandées (numéro = ordre, couleur = vague), arrêts de bus et stations vélo proposés.
Vie privée : la population n'est pas affichée pour les carreaux imputés par l'INSEE (moins de 11 ménages).
Vocabulaire : « accès plus limité » plutôt que « mal desservi », pour ne pas stigmatiser un quartier.

Sortie : decision/resultats/carte_decision_06.html
"""
import json

import folium
import numpy as np
import pandas as pd
from folium.plugins import Fullscreen

from communs import DONNEES, RESULTATS, to4326

acc = pd.read_csv(DONNEES / "acces_carreaux_06.csv.gz")
pts = pd.read_csv(RESULTATS / "population_par_point_acces_06.csv")
cz = pd.read_csv(RESULTATS / "stations_citiz_recommandees.csv")
bus = pd.read_csv(RESULTATS / "arrets_bus_recommandes.csv")
vel = pd.read_csv(RESULTATS / "stations_velo_recommandees.csv")
syn = json.loads((RESULTATS / "synthese_decision.json").read_text())
mod = json.loads((RESULTATS / "modele_implantation.json").read_text())
try:
    iso = pd.read_csv(RESULTATS / "isochrones_sites.csv")
    iso = iso.dropna(subset=["ratio_a_pied"]).set_index(["equipement", "rang"])
except (FileNotFoundError, KeyError):
    iso = pd.DataFrame()

m = folium.Map(location=[43.70, 7.18], zoom_start=11, tiles="CartoDB positron", control_scale=True)
Fullscreen().add_to(m)

# ---------------------------------------------------------------- Objectif 1
COUL = {"1 très faible": "#2c7bb6", "2 faible": "#abd9e9", "3 moyen": "#ffffbf", "4 bon": "#fdae61", "5 très bon": "#d7191c"}
LIB = {"1 très faible": "accès plus limité", "2 faible": "accès modéré", "3 moyen": "accès moyen", "4 bon": "accès bon",
       "5 très bon": "accès très riche"}
feats = []
for r in acc.itertuples():
    lon, lat = to4326.transform([r.x - 100, r.x + 100, r.x + 100, r.x - 100, r.x - 100],
                                [r.y - 100, r.y - 100, r.y + 100, r.y + 100, r.y - 100])
    classe = r.classe_acces if isinstance(r.classe_acces, str) else None
    habit = "non diffusé (carreau imputé)" if r.i_est_200 == 1 else f"{r.pop_carreau:,.0f}".replace(",", " ")
    feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[round(a, 5), round(b, 5)] for a, b in zip(lon, lat)]]},
                  "properties": {"c": COUL.get(classe, "#d9d9d9"),
                                 "t": f"<b>{r.commune}</b><br>{LIB.get(classe, 'moins de 200 habitants à 400 m')}"
                                      f"<br>{r.options_400m} options à 5 min ({r.options_pour_1000_hab:.1f} pour 1 000 hab.)"
                                      f"<br>{r.passages_tc_jour_400m:,.0f} passages TC / jour à 400 m<br>habitants du carreau : {habit}"}})
fg1 = folium.FeatureGroup(name="Objectif 1 — options à 5 min pour 1 000 habitants", show=True)
folium.GeoJson({"type": "FeatureCollection", "features": feats},
               style_function=lambda f: {"fillColor": f["properties"]["c"], "color": f["properties"]["c"], "weight": 0, "fillOpacity": 0.55},
               tooltip=folium.GeoJsonTooltip(fields=["t"], labels=False)).add_to(fg1)
fg1.add_to(m)

# ---------------------------------------------------------------- Objectif 2
STYLE = {"arrêt bus / tram": "#555555", "gare": "#000000", "zone free-floating": "#1a9850", "voiture Getaround": "#7b3294",
         "scooter partagé": "#e66101", "station VLS": "#1f78b4", "station autopartage": "#d01c8b"}
for t, d in pts.groupby("type"):
    fg = folium.FeatureGroup(name=f"Objectif 2 — {t} ({len(d)})", show=t in ("gare",))
    for r in d.itertuples():
        folium.CircleMarker([r.lat, r.lon], radius=float(np.clip(np.sqrt(r.habitants_400m) / 12, 2, 10)),
                            color=STYLE.get(t, "#333"), weight=1, fill=True, fill_opacity=0.7,
                            tooltip=f"{t} — {r.nom}<br>{r.habitants_400m:,.0f} habitants à 400 m"
                                    + (f"<br>{r.departs:.0f} passages / jour" if pd.notna(r.departs) else "")).add_to(fg)
    fg.add_to(m)

# ---------------------------------------------------------------- Objectif 3
VAGUE = {"Vague 1": "#b2182b", "Vague 2": "#ef8a62", "Vague 3": "#2166ac"}
fg3 = folium.FeatureGroup(name=f"Objectif 3 — {len(cz)} stations Citiz recommandées", show=True)
for r in cz.itertuples():
    k = ("station Citiz", r.rang)
    pied = f"<br>à pied (OSM) : {iso.loc[k, 'habitants_400m_a_pied']:,.0f} habitants (x{iso.loc[k, 'ratio_a_pied']:.2f})" if k in iso.index else ""
    alerte = f"<br>⚠ hors du domaine d'apprentissage : {r.variables_hors_domaine}" if r.hors_domaine else ""
    folium.Circle([r.lat, r.lon], radius=400, color=VAGUE[r.vague], weight=1, fill=True, fill_opacity=0.08).add_to(fg3)
    folium.Marker([r.lat, r.lon], tooltip=f"#{r.rang} {r.commune} — {r.arret_proche}",
                  popup=folium.Popup(
                      f"<b>#{r.rang} {r.commune}</b> ({r.vague})<br>repère : {r.arret_proche}"
                      f"<br>{r.habitants_nouveaux:,.0f} habitants nouvellement desservis à 400 m{pied}"
                      f"<br>potentiel : {r.potentiel:.2f} (plus que {r.percentile_vs_stations_citiz:.0f} % des stations Citiz)"
                      f"<br>occupation attendue : {100 * r.occupation_attendue:.0f} % [{100 * r.occupation_bas:.0f}-{100 * r.occupation_haut:.0f}]"
                      f"<br>{r.vehicules} véhicules · coût année 1 : {r.cout_annee1_eur:,.0f} €"
                      f"<br>résultat annuel : {r.resultat_eur_an_bas:,.0f} à {r.resultat_eur_an_haut:,.0f} €"
                      f"<br>CO₂ évité : {r.co2_evite_t_an_bas:.0f}-{r.co2_evite_t_an_haut:.0f} t/an{alerte}", max_width=330),
                  icon=folium.DivIcon(html=f'<div style="background:{VAGUE[r.vague]};color:#fff;border-radius:50%;width:24px;height:24px;'
                                           f'text-align:center;line-height:24px;font:bold 12px sans-serif">{r.rang}</div>')).add_to(fg3)
fg3.add_to(m)
fgb = folium.FeatureGroup(name=f"Objectif 3 — {len(bus)} arrêts de bus proposés", show=False)
for r in bus.itertuples():
    folium.RegularPolygonMarker([r.lat, r.lon], number_of_sides=4, radius=8, color="#4d4d4d", fill_color="#fee08b", fill_opacity=1,
                                tooltip=f"Arrêt proposé #{r.rang} — {r.commune}<br>{r.habitants_gagnant_un_arret:,.0f} habitants gagnent un arrêt"
                                        f"<br>{r.cout_eur:,.0f} € ({r.cout_par_habitant_eur:.0f} €/habitant)").add_to(fgb)
fgb.add_to(m)
fgv = folium.FeatureGroup(name=f"Objectif 3 — {len(vel)} stations vélo proposées", show=False)
for r in vel.itertuples():
    folium.RegularPolygonMarker([r.lat, r.lon], number_of_sides=3, radius=9, color="#08519c", fill_color="#6baed6", fill_opacity=1,
                                tooltip=f"Station vélo proposée #{r.rang} — {r.arret_proche}<br>{r.habitants_nouveaux:,.0f} habitants à 400 m"
                                        f"<br>{r.cout_eur_an:,.0f} €/an").add_to(fgv)
fgv.add_to(m)
folium.LayerControl(collapsed=False).add_to(m)

s = syn["citiz"]
fr = lambda n: f"{n:,.0f}".replace(",", "\u202f")
legende = f"""
<div style="position:fixed;bottom:18px;left:18px;z-index:9999;background:#fff;padding:10px 12px;border-radius:6px;
box-shadow:0 1px 4px rgba(0,0,0,.3);font:12px/1.4 sans-serif;max-width:330px">
<b>Alpes-Maritimes — où ajouter de la mobilité partagée ?</b><br>
Objectif 1 : options à 5 min pour 1 000 habitants<br>
{''.join(f'<span style="display:inline-block;width:12px;height:12px;background:{c};margin-right:4px"></span>{LIB[k]}<br>' for k, c in COUL.items())}
<hr style="margin:6px 0">
<b>Citiz</b> : {s['stations']} stations, {s['vehicules']} véhicules, {fr(s['budget_annee1_eur'])} € la 1re année,
{fr(s['habitants_nouveaux'])} habitants nouvellement desservis (vol d'oiseau).<br>
Potentiel : modèle validé hors échantillon (AUC {mod['auc']}, réseau laissé de côté).<br>
<span style="color:#666">Secteurs à étudier, pas des places réservées. Sources : INSEE Filosofi 2021, GTFS/GBFS
transport.data.gouv.fr, relevés Citiz (Microsoft Fabric), OSM.</span></div>"""
m.get_root().html.add_child(folium.Element(legende))
m.save(RESULTATS / "carte_decision_06.html")
print(f"Carte : {RESULTATS / 'carte_decision_06.html'} ({(RESULTATS / 'carte_decision_06.html').stat().st_size / 1e6:.1f} Mo)")
