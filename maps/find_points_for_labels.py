"""
Find good points for labels within each GeoJSON feature

Output is slighly different than centroids, see:
https://blog.mapbox.com/a-new-algorithm-for-finding-a-visual-center-of-a-polygon-7c77e6492fbc
"""

import numpy as np
import pandas as pd
import geopandas as gpd
from polylabel import polylabel


smd = gpd.read_file('smd.geojson')

label_points = pd.DataFrame(columns=['smd_id', 'lon', 'lat'])

for i, row in smd.iterrows():
    district_outline = np.dstack(row.geometry.boundary[0].coords.xy).tolist()
    
    [lon, lat] = polylabel(district_outline)
    
    label_points.loc[i, 'smd_id'] = 'smd_' + row['SMD_ID']
    label_points.loc[i, 'smd'] = row['SMD_ID']
    label_points.loc[i, 'lon'] = lon
    label_points.loc[i, 'lat'] = lat


label_points.sort_values(by='smd_id', inplace=True)
label_points.to_csv('label_points.csv', index=False)
