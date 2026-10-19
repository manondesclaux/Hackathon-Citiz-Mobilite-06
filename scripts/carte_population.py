"""Carte de la population par carreau INSEE de 200 m (version locale, sans Fabric).

Usage :
    pip install pandas geopandas folium
    python scripts/carte_population.py carreaux_200m_mart.csv [sortie.html]
"""
import sys

import folium
import geopandas as gpd
import pandas as pd
from shapely.geometry import box

ID = "idcar_200m"  # sinon "idcar_nat"
POP = "ind"        # population du carreau


def charger(path: str) -> gpd.GeoDataFrame:
    df = pd.read_csv(path, sep=None, engine="python")
    ext = df[ID].str.extract(r"CRS(\d+)RES200mN(\d+)E(\d+)").astype(float)
    ext.columns = ["crs", "N", "E"]
    df = pd.concat([df, ext], axis=1).dropna(subset=["crs", POP])
    crs_code = int(df["crs"].iloc[0])
    print("CRS détecté :", crs_code)

    geom = [box(e, n, e + 200, n + 200) for e, n in zip(df.E, df.N)]
    gdf = gpd.GeoDataFrame(df[[ID, POP]], geometry=geom, crs=f"EPSG:{crs_code}")
    return gdf.to_crs(4326)


def carte(gdf: gpd.GeoDataFrame, sortie: str) -> None:
    minx, miny, maxx, maxy = gdf.total_bounds
    m = folium.Map(location=[(miny + maxy) / 2, (minx + maxx) / 2], zoom_start=11,
                   tiles="cartodbpositron")
    folium.Choropleth(
        geo_data=gdf.to_json(),
        data=gdf,
        columns=[ID, POP],
        key_on=f"feature.properties.{ID}",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0,
        legend_name="Habitants par carreau de 200 m",
    ).add_to(m)
    m.save(sortie)
    print("Carte écrite :", sortie)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    gdf = charger(sys.argv[1])
    print(gdf.shape, gdf.total_bounds)  # Martinique : lon ≈ -61.2..-60.8, lat ≈ 14.4..14.9
    carte(gdf, sys.argv[2] if len(sys.argv) > 2 else "carte_pop.html")
