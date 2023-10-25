"""
Build Ward pages
"""

import hashlib
import numpy as np
import pandas as pd
from tqdm import tqdm
import geopandas as gpd

import config

from scripts.common import (
    build_smd_html_table
    , add_footer
    , add_google_analytics
    , add_geojson
    , ward_geojson
    , mapbox_slugs
    )

from scripts.urls import (
    generate_url
    , generate_link
    , relative_link_prefix
    )

from scripts.data_transformations import districts_candidates_commissioners



class BuildWards():

    def __init__(self):
        self.geojson_shape = ward_geojson()
        self.mapbox_style_slugs = mapbox_slugs()

        self.districts = pd.read_csv('data/districts.csv')
        self.mapbox_styles = pd.read_csv('data/mapbox_styles.csv')
        self.wards = pd.read_csv('data/wards.csv')
        self.candidate_statuses = pd.read_csv('data/candidate_statuses.csv')
        self.dcc = districts_candidates_commissioners(link_source='ward')



    def ward_list_page(self, redistricting_year):
        """Build a page showing a list of all the wards"""
        
        with open('templates/list.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)

        output = output.replace('REPLACE_WITH_MAPBOX_GL_JS_VERSION', config.mapbox_gl_js_version)
        output = output.replace('REPLACE_WITH_LIST_NAME', f'List of Wards (Redistricting Year {redistricting_year})')
        output = output.replace('REPLACE_WITH_LINK_PATH___', relative_link_prefix(source='ward', destination='root'))

        output = output.replace('REPLACE_WITH_LIST_VALUES', self.list_of_wards(redistricting_year))
        
        with open(f'docs/map_{redistricting_year}/wards/index.html', 'w') as f:
            f.write(output)



    def list_of_wards(self, redistricting_year):

        ward_districts = pd.merge(
            self.wards[self.wards.redistricting_year == redistricting_year]
            , self.districts, how='inner', on='ward_id'
            )

        display_df = ward_districts.groupby(['ward_id', 'ward_name', 'councilmember']).agg(count_of_smds=('smd_id', 'size')).reset_index()
        display_df['Ward'] = display_df.apply(lambda x: generate_link(x.ward_id, x.ward_name, link_source='ward'), axis=1)
        display_df['Council Member'] = display_df['councilmember']
        display_df['Count of SMDs'] = display_df['count_of_smds']

        columns_to_html = ['Ward', 'Council Member', 'Count of SMDs']

        html = (
            display_df[columns_to_html]
            .fillna('')
            .style
            .set_uuid('list_of_wards_')
            .hide(axis='index')
            .to_html()
            )

        return html



    def build_all_ward_pages(self):
        """Build pages for each ward"""

        for _, ward in tqdm(self.wards.iterrows(), total=len(self.wards), desc='Wards  '):
            self.build_ward_page(ward)



    def build_ward_page(self, ward):
        """Build one ward page"""

        with open('templates/ward.html', 'r') as f:
            output = f.read()
        
        output = add_google_analytics(output)
        output = add_geojson(self.geojson_shape, 'ward_id', ward.ward_id, output)
        
        output = output.replace('REPLACE_WITH_MAPBOX_GL_JS_VERSION', config.mapbox_gl_js_version)
        output = output.replace('REPLACE_WITH_WARD_NAME', f'{ward.ward_name} [{ward.redistricting_cycle} Cycle]')
        output = output.replace('REPLACE_WITH_CM', ward.councilmember)
        
        ward_smd_ids = self.districts[self.districts['ward_id'] == ward.ward_id]['smd_id'].to_list()
        output = output.replace(
            '<!-- replace with district list -->'
            , build_smd_html_table(ward_smd_ids, link_source='ward', district_comm_commelect=self.dcc, candidate_statuses=self.candidate_statuses)
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

        for ry in [2012, 2022]:
            self.ward_list_page(redistricting_year=ry)

        self.build_all_ward_pages()

