"""Génère la carte de France Citiz vs concurrents à partir des données en cache (data/raw).

Usage : python3 scripts/build_map.py
Produit : sorties/carte_citiz_concurrents.html
"""
import json
import math
from pathlib import Path

import folium
import pandas as pd
from folium.plugins import FastMarkerCluster

ROOT = Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "sorties"

COLORS = {"Citiz": "#00843D", "Getaround": "#7B2CBF", "Clem'": "#F77F00", "Optymo": "#D62828", "Leo&Go": "#0077B6"}

latest = lambda pattern: sorted(RAW.glob(pattern))[-1]

citiz = pd.read_csv(latest("citiz_stations_*.csv"), dtype={"id": str})
citiz = (citiz.assign(_k=citiz["lat"].round(4).astype(str) + "," + citiz["lon"].round(4).astype(str))
              .sort_values("n_vehicles", ascending=False).drop_duplicates("_k").drop(columns="_k"))
others = pd.read_csv(latest("competitors_*.csv"), dtype={"id": str})

ga_dir = sorted(d for d in RAW.glob("getaround_20*") if d.is_dir())[-1]
feeds = [p for p in ga_dir.glob("*.json") if not p.name.startswith("_")]
n_total = len(json.loads((ga_dir / "_manifest.json").read_text()))
ga = (pd.DataFrame([r for p in feeds for r in json.loads(p.read_text())], columns=["id", "lat", "lon"])
        .drop_duplicates("id"))
coverage = len(feeds) / n_total

m = folium.Map(location=[46.6, 2.4], zoom_start=6, tiles=None, control_scale=True)
folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", attr="Tiles © Esri — Esri, DeLorme, NAVTEQ", name="Fond clair (Esri)").add_to(m)

# Getaround (en dessous, en clusters)
callback = f"""function (row) {{
    return L.circleMarker(new L.LatLng(row[0], row[1]),
        {{radius: 3, color: "{COLORS['Getaround']}", fillOpacity: 0.6, weight: 0}});
}}"""
fg = folium.FeatureGroup(name=f"Getaround ({len(ga):,} véhicules, {coverage:.0%} des flux)")
FastMarkerCluster(ga[["lat", "lon"]].values.tolist(), callback=callback).add_to(fg)
fg.add_to(m)

# Autres concurrents
for op in ["Clem'", "Optymo", "Leo&Go"]:
    d = others[others["operator"] == op]
    fg = folium.FeatureGroup(name=f"{op} ({int(d['n_vehicles'].sum())} véhicules)")
    for r in d.itertuples():
        folium.CircleMarker([r.lat, r.lon], radius=3 + math.sqrt(r.n_vehicles), color=COLORS[op],
                            fill=True, fill_opacity=0.7, weight=1,
                            tooltip=f"{r.network} — {r.name} ({int(r.n_vehicles)} véh.)").add_to(fg)
    fg.add_to(m)

# Citiz (au-dessus)
fg = folium.FeatureGroup(name=f"Citiz ({len(citiz)} stations, {int(citiz['n_vehicles'].sum())} véhicules)")
for r in citiz.itertuples():
    folium.CircleMarker([r.lat, r.lon], radius=3 + 1.5 * math.sqrt(r.n_vehicles), color=COLORS["Citiz"],
                        fill=True, fill_opacity=0.8, weight=1,
                        tooltip=f"<b>{r.network}</b><br>{r.name}<br>{int(r.n_vehicles)} véhicule(s)").add_to(fg)
fg.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
legend = "".join(f'<div><span style="display:inline-block;width:12px;height:12px;border-radius:6px;'
                 f'background:{c};margin-right:6px"></span>{op}</div>' for op, c in COLORS.items())
note = "" if coverage > 0.99 else (f'<div style="margin-top:6px;color:#a00;font-size:11px">Getaround partiel : '
                                  f'{coverage:.0%} des flux collectés</div>')
m.get_root().html.add_child(folium.Element(
    f'<div style="position:fixed;bottom:30px;left:30px;z-index:9999;background:white;padding:8px 12px;'
    f'border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);font:13px sans-serif">{legend}{note}</div>'))

OUT.mkdir(exist_ok=True)
out = OUT / "carte_citiz_concurrents.html"
m.save(str(out))
print(f"{out} — Citiz {len(citiz)} stations, Getaround {len(ga):,} véhicules ({coverage:.0%} des flux)")
