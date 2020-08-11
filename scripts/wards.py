"""
Build Ward pages
"""

import numpy as np
import pandas as pd
from tqdm import tqdm
import geopandas as gpd

from scripts.common import (
    build_data_table
    , build_smd_html_table
    , add_footer
    , calculate_zoom
    , add_google_analytics
    , add_geojson
    )


class BuildWards():


    def run(self):
        """Build pages for each ANC"""

        ancs = pd.read_csv('data/ancs.csv')
        districts = pd.read_csv('data/districts.csv')
        mapbox_styles = pd.read_csv('data/mapbox_styles.csv')
        ward_df = pd.read_csv('data/wards.csv')
        ward_gdf = gpd.read_file('maps/ward.geojson')

        wards = sorted(districts['ward'].unique())
        
        for ward in tqdm(wards, total=len(wards), desc='Wards'):
                    
            with open('templates/ward.html', 'r') as f:
                output = f.read()
            
            output = add_google_analytics(output)
            output = add_geojson(ward_gdf, 'WARD', ward, output)
            
            output = output.replace('REPLACE_WITH_WARD', str(ward))
            output = output.replace('REPLACE_WITH_CM', ward_df.loc[ward_df['ward'] == ward, 'councilmember'].values[0])
            
            ward_smd_ids = districts[districts['ward'] == ward]['smd_id'].to_list()
            output = output.replace(
                '<!-- replace with district list -->'
                , build_smd_html_table(ward_smd_ids, link_path='../ancs/districts/')
                )


            if ward in (3,4):
                output = output.replace(
                    '<!-- replace with 3/4 info -->'
                    , '<p>Note that the Single Member Districts 3G01, 3G02, 3G03, and 3G04 are a part of ANC 3G but located in Ward 4.</p>'
                    )
            
            mb_style_name = f'smd-ward-{ward}'
            mb_style_link = mapbox_styles.loc[mapbox_styles['id'] == mb_style_name]['mapbox_link'].values[0]
            
            output = output.replace('REPLACE_WITH_MAPBOX_STYLE', mb_style_link)
            output = output.replace('REPLACE_WITH_LONGITUDE', '-77.03412954884507')
            output = output.replace('REPLACE_WITH_LATITUDE', '38.9361129455516')
            output = output.replace('REPLACE_WITH_ZOOM_LEVEL', '11')

            output = add_footer(output, level=1)

            with open(f'docs/wards/ward{ward}.html', 'w') as f:
                f.write(output)

