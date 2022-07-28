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
    , ward_geojson
    , mapbox_slugs
    )

from scripts.urls import (
    generate_url
    )


class BuildWards():

    def __init__(self):
        self.geojson_shape = ward_geojson()
        self.mapbox_style_slugs = mapbox_slugs()

        self.districts = pd.read_csv('data/districts.csv')
        self.mapbox_styles = pd.read_csv('data/mapbox_styles.csv')
        self.wards = pd.read_csv('data/wards.csv')



    def ward_list_page(self):
        pass



    def build_all_ward_pages(self):
        """Build pages for each ward"""

        # ward_gdf = gpd.read_file('maps/ward-from-smd.geojson')
        
        for _, ward in tqdm(self.wards.iterrows(), total=len(self.wards), desc='Wards  '):
            self.build_ward_page(ward)



    def build_ward_page(self, ward):

        with open('templates/ward.html', 'r') as f:
            output = f.read()
        
        output = add_google_analytics(output)
        output = add_geojson(self.geojson_shape, 'ward_id', ward.ward_id, output)
        
        output = output.replace('REPLACE_WITH_WARD_NAME', f'{ward.ward_name} [{ward.redistricting_cycle} Cycle]')
        output = output.replace('REPLACE_WITH_CM', ward.councilmember)
        
        ward_smd_ids = self.districts[self.districts['ward_id'] == ward.ward_id]['smd_id'].to_list()
        output = output.replace(
            '<!-- replace with district list -->'
            , build_smd_html_table(ward_smd_ids, link_source='ward')
            )

        if ward.ward_name in (3,4):
            output = output.replace(
                '<!-- replace with 3/4 info -->'
                , '<p>Note that the Single Member Districts 3G01, 3G02, 3G03, and 3G04 are a part of ANC 3G but located in Ward 4.</p>'
                )

        if ward.redistricting_year == 2012:
            mapbox_slug_id = 'smd'
        else:
            mapbox_slug_id = 'smd-2022'

        output = output.replace('REPLACE_WITH_MAPBOX_SLUG', self.mapbox_style_slugs[mapbox_slug_id])
        output = output.replace('REPLACE_WITH_LONGITUDE', '-77.03412954884507')
        output = output.replace('REPLACE_WITH_LATITUDE', '38.9361129455516')
        output = output.replace('REPLACE_WITH_ZOOM_LEVEL', '11')

        output = add_footer(output, link_source='ward')

        with open('docs/' + generate_url(ward.ward_id, link_source='root'), 'w') as f:
            f.write(output)



    def run(self):

        self.ward_list_page()
        self.build_all_ward_pages()

