"""
Open shapefile in QGIS
Create centroids from it
Save centroid layer as geojson
Use this script to turn geojson lat/long points into a CSV
"""

import json
import pandas as pd
import geopandas as gpd

c = gpd.read_file('anc_centroids.geojson')
print(c.head())

df = pd.DataFrame()
df['anc'] = c['ANC_ID']
df['longitude'] = c['geometry'].centroid.x
df['latitude'] = c['geometry'].centroid.y

df.sort_values(by='anc', inplace=True)

df.to_csv('anc_centroids.csv', index=False)