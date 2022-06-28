"""
Find good points for labels within each GeoJSON feature

Output is slighly different than centroids, see:
https://blog.mapbox.com/a-new-algorithm-for-finding-a-visual-center-of-a-polygon-7c77e6492fbc
"""

import numpy as np
import pandas as pd
import geopandas as gpd
from polylabel import polylabel


smd = gpd.read_file('to-mapbox-2022-smd-data.geojson')

label_points = pd.DataFrame(columns=['smd_id', 'lon', 'lat'])

for i, row in smd.iterrows():
    print(row.smd_id)
    district_outline = np.dstack(row.geometry.boundary.coords.xy).tolist()
    
    [lon, lat] = polylabel(district_outline)
    
    label_points.loc[i, 'smd_id'] = row['smd_id']
    label_points.loc[i, 'smd'] = row['smd_id'].replace('smd_', '')
    label_points.loc[i, 'lon'] = lon
    label_points.loc[i, 'lat'] = lat


# Specify the column names that will be in the final label-points CSV sent to Mapbox
output_columns = [
    'smd_id'
    , 'lon'
    , 'lat'
    , 'smd'
    , 'current_commissioner'
    , 'commissioner_elect'
    , 'map_display_box'
]

for c in output_columns:
    if c not in label_points.columns:
        label_points[c] = None

label_points.sort_values(by='smd_id', inplace=True)
label_points[output_columns].to_csv('label-points-2022.csv', index=False)
