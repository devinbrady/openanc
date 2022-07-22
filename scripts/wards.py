"""
Build Ward pages
"""

import numpy as np
import pandas as pd
from tqdm import tqdm
import geopandas as gpd

from scripts.common import (
    build_smd_html_table
    , add_footer
    , calculate_zoom
    , add_google_analytics
    , add_geojson
    )

from scripts.urls import (
    ward_url
    )


class BuildWards():


    def run(self):
        """Build pages for each ANC"""

        ancs = pd.read_csv('data/ancs.csv')
        districts = pd.read_csv('data/districts.csv')
        mapbox_styles = pd.read_csv('data/mapbox_styles.csv')
        wards = pd.read_csv('data/wards.csv')
        # ward_gdf = gpd.read_file('maps/ward-from-smd.geojson')
        
        for idx, row in tqdm(wards.iterrows(), total=len(wards), desc='Wards  '):
                    
            with open('templates/ward.html', 'r') as f:
                output = f.read()
            
            output = add_google_analytics(output)
            # output = add_geojson(ward_gdf, 'ward_id', ward_id, output)
            
            output = output.replace('REPLACE_WITH_WARD_NAME', row.ward_name)
            # output = output.replace('REPLACE_WITH_CM', row.councilmember)
            
            ward_smd_ids = districts[districts['ward_id'] == row.ward_id]['smd_id'].to_list()
            output = output.replace(
                '<!-- replace with district list -->'
                , build_smd_html_table(ward_smd_ids, link_source='ward')
                )


            # if row.ward_name in (3,4):
            #     output = output.replace(
            #         '<!-- replace with 3/4 info -->'
            #         , '<p>Note that the Single Member Districts 3G01, 3G02, 3G03, and 3G04 are a part of ANC 3G but located in Ward 4.</p>'
            #         )
            
            # mb_style_name = f'smd-ward-{ward}'
            # mb_style_link = mapbox_styles.loc[mapbox_styles['id'] == mb_style_name]['mapbox_link'].values[0]
            
            # output = output.replace('REPLACE_WITH_MAPBOX_STYLE', mb_style_link)
            output = output.replace('REPLACE_WITH_LONGITUDE', '-77.03412954884507')
            output = output.replace('REPLACE_WITH_LATITUDE', '38.9361129455516')
            output = output.replace('REPLACE_WITH_ZOOM_LEVEL', '11')

            output = add_footer(output, level=2)

            with open(f'docs/' + ward_url(row.ward_id, level=0), 'w') as f:
                f.write(output)

