"""
Build ANC pages
"""

import numpy as np
import pandas as pd
from tqdm import tqdm
import geopandas as gpd


from scripts.common import (
    build_smd_html_table
    , build_data_table
    , build_link_block
    , add_footer
    , calculate_zoom
    , add_google_analytics
    , add_geojson
    , anc_geojson
    , anc_url
    , mapbox_slugs
    )


class BuildANCs():

    def __init__(self):

        # Load GeoJSON for all ANCs to memory
        self.geojson_shape = anc_geojson()

        self.mapbox_style_slugs = mapbox_slugs()



    def run(self):
        """Build pages for each ANC"""

        ancs = pd.read_csv('data/ancs.csv')
        districts = pd.read_csv('data/districts.csv')

        ancs['link_block'] = ancs.apply(lambda row: build_link_block(row, fields_to_try=['dc_oanc_link', 'anc_homepage_link', 'twitter_link']), axis=1)
        
        for idx, row in tqdm(ancs.iterrows(), total=len(ancs), desc='ANCs   '):

            anc_id = row['anc_id']

            # debug
            # if anc_id != '6D':
            #     continue
                    
            with open('templates/anc.html', 'r') as f:
                output = f.read()
            
            output = add_google_analytics(output)
            output = add_geojson(self.geojson_shape, 'anc_id', anc_id, output)
            
            output = output.replace('REPLACE_WITH_ANC_NAME', f'{row.anc_name} [{row.redistricting_cycle} Cycle]')
            

            if row['redistricting_year'] == 2012:
                mapbox_slug_id = 'smd'
            else:
                mapbox_slug_id = 'smd-2022'

            output = output.replace('REPLACE_WITH_MAPBOX_SLUG', self.mapbox_style_slugs[mapbox_slug_id])


            smds_in_anc = districts[districts['anc_id'] == anc_id]['smd_id'].to_list()
            output = output.replace('<!-- replace with district list -->', build_smd_html_table(smds_in_anc, level=1))

            fields_to_try = ['notes', 'link_block']
            output = output.replace('<!-- replace with anc link list -->', build_data_table(row, fields_to_try))

            
            output = output.replace('REPLACE_WITH_LONGITUDE', str(row['centroid_lon']))
            output = output.replace('REPLACE_WITH_LATITUDE', str(row['centroid_lat']))
            output = output.replace('REPLACE_WITH_ZOOM_LEVEL', str(calculate_zoom(row['area'])))

            output = add_footer(output, level=2)

            with open(f'docs/' + anc_url(row.anc_id, level=0), 'w') as f:
                f.write(output)

