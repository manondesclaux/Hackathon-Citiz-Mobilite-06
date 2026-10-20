"""Étape 8 — Distances à pied réelles (réseau piéton OpenStreetMap) pour les sites recommandés.

Le reste du pipeline compte les habitants à 400 m à vol d'oiseau. Sur la Côte d'Azur (relief, voies ferrées,
autoroute, Paillon), cela surestime l'accès. Pour chaque site retenu à l'étape 7, on télécharge le réseau piéton
OSM autour du point et on compte les habitants dont le centre de carreau est à moins de 400 m À PIED
(distance réseau + raccordement du carreau et du site au réseau).

Téléchargement : extrait OSM de ~1,4 km de côté autour de chaque site via l'API principale d'OpenStreetMap
(les serveurs Overpass n'étaient pas joignables), une requête par site, mise en cache. On garde les voies où l'on
peut marcher (ni autoroute, ni voie interdite aux piétons, ni accès privé).

Sortie : decision/resultats/isochrones_sites.csv (habitants à vol d'oiseau, à pied, ratio). Cache OSM : data/raw/osm/
"""
import math
import time

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import requests
from scipy.spatial import cKDTree

from communs import DONNEES, R_REQ, RAYON, RESULTATS, ROOT, xy

CACHE = ROOT / "data" / "raw" / "osm"
CACHE.mkdir(parents=True, exist_ok=True)
ox.settings.log_console = False
NON_PIETON = {"motorway", "motorway_link", "trunk", "trunk_link", "construction", "proposed", "abandoned", "raceway", "bus_guideway"}


def reseau_pieton(lat, lon, demi_cote_m=700):
    dlat = demi_cote_m / 111_320
    dlon = demi_cote_m / (111_320 * math.cos(math.radians(lat)))
    f = CACHE / f"osm_{lat:.5f}_{lon:.5f}.xml"
    for essai in range(6):
        if f.exists():
            break
        r = requests.get("https://api.openstreetmap.org/api/0.6/map",
                         params={"bbox": f"{lon - dlon:.6f},{lat - dlat:.6f},{lon + dlon:.6f},{lat + dlat:.6f}"},
                         headers={"User-Agent": "hackathon-citiz-epitech/1.0"}, timeout=120)
        if r.status_code in (429, 509):                            # quota de bande passante : on attend
            time.sleep(int(r.headers.get("Retry-After", 60 * (essai + 1))))
            continue
        r.raise_for_status()
        f.write_bytes(r.content)
        time.sleep(2)                                              # politesse envers l'API OSM
    G = ox.graph_from_xml(f, bidirectional=True, simplify=False, retain_all=True)
    garder = []
    for u, v, k, d in G.edges(keys=True, data=True):
        h = d.get("highway")
        h = h[0] if isinstance(h, list) else h
        if h and h not in NON_PIETON and d.get("foot") != "no" and d.get("access") not in ("private", "no"):
            garder.append((u, v, k))
    H = G.edge_subgraph(garder).copy()
    return ox.project_graph(H, to_crs="EPSG:3035")


c = pd.read_csv(DONNEES / "candidats_06.csv.gz", usecols=["x", "y", "lat", "lon", "pop_carreau"])
tree = cKDTree(c[["x", "y"]].to_numpy())
sites = pd.concat([
    pd.read_csv(RESULTATS / "stations_citiz_recommandees.csv").assign(equipement="station Citiz"),
    pd.read_csv(RESULTATS / "stations_velo_recommandees.csv").assign(equipement="station vélo"),
    pd.read_csv(RESULTATS / "arrets_bus_recommandes.csv").assign(equipement="arrêt de bus"),
], ignore_index=True)

lignes = []
for s in sites.itertuples():
    try:
        G = reseau_pieton(s.lat, s.lon)
        nodes = ox.graph_to_gdfs(G, edges=False)
        N = np.c_[nodes.geometry.x, nodes.geometry.y]
        ntree = cKDTree(N)
        P = np.array([s.x, s.y]) if pd.notna(getattr(s, "x", np.nan)) else xy([s.lon], [s.lat])[0]
        d0, i0 = ntree.query(P)
        dist = nx.single_source_dijkstra_path_length(G, nodes.index[i0], cutoff=RAYON - d0, weight="length")
        voisins = tree.query_ball_point(P, r=R_REQ)
        car = c.iloc[voisins]
        dc, ic = ntree.query(car[["x", "y"]].to_numpy())
        reseau = np.array([dist.get(nodes.index[k], np.inf) for k in ic]) + dc + d0
        pop_vol = car.pop_carreau.sum()
        pop_pied = car.pop_carreau[reseau <= RAYON].sum()
        lignes.append({"equipement": s.equipement, "rang": s.rang, "commune": s.commune, "lat": s.lat, "lon": s.lon,
                       "habitants_400m_vol_oiseau": round(pop_vol), "habitants_400m_a_pied": round(pop_pied),
                       "ratio_a_pied": round(pop_pied / pop_vol, 2) if pop_vol else None, "raccordement_site_m": round(d0)})
        print(f"{s.equipement:<14} #{s.rang:<3} {s.commune:<18} {pop_vol:>8,.0f} -> {pop_pied:>8,.0f} à pied")
    except Exception as e:                                       # un échec OSM ne bloque pas les autres sites
        lignes.append({"equipement": s.equipement, "rang": s.rang, "commune": s.commune, "erreur": str(e)[:200]})
        print(f"{s.equipement} #{s.rang}: ERREUR {e}")

iso = pd.DataFrame(lignes)
iso.to_csv(RESULTATS / "isochrones_sites.csv", index=False)
ok = iso.dropna(subset=["ratio_a_pied"])
print("\nRatio habitants à pied / à vol d'oiseau, par équipement :\n",
      ok.groupby("equipement").agg(sites=("rang", "size"), ratio_moyen=("ratio_a_pied", "mean"),
                                   ratio_min=("ratio_a_pied", "min")).round(2).to_string())
