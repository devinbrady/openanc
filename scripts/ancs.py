"""
Build ANC pages
"""

import hashlib
import numpy as np
import pandas as pd
from tqdm import tqdm
import geopandas as gpd

import config

from scripts.common import (
    build_smd_html_table
    , build_data_table
    , build_link_block
    , add_footer
    , calculate_zoom
    , add_google_analytics
    , add_geojson
    , anc_geojson
    , mapbox_slugs
    )

from scripts.urls import (
    generate_link
    , generate_url
    , relative_link_prefix
    )

from scripts.data_transformations import districts_candidates_commissioners



class BuildANCs():

    def __init__(self):

        # Load GeoJSON for all ANCs to memory
        self.geojson_shape = anc_geojson()
        self.mapbox_style_slugs = mapbox_slugs()

        self.candidate_statuses = pd.read_csv('data/candidate_statuses.csv')
        self.dcc = districts_candidates_commissioners(link_source='anc')

        self.ancs = pd.read_csv('data/ancs.csv')
        self.ancs['link_block'] = self.ancs.apply(lambda row: build_link_block(row, fields_to_try=['dc_oanc_link', 'anc_homepage_link', 'twitter_link']), axis=1)

        self.districts = pd.read_csv('data/districts.csv')



    def anc_list_page(self, redistricting_year):
        """Build a page showing a list of all the ANCs"""
        
        with open('templates/list.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)

        output = output.replace('REPLACE_WITH_MAPBOX_GL_JS_VERSION', config.mapbox_gl_js_version)
        output = output.replace('REPLACE_WITH_LIST_NAME', f'List of ANCs (Redistricting Year {redistricting_year})')
        output = output.replace('REPLACE_WITH_LINK_PATH___', relative_link_prefix(source='anc', destination='root'))

        output = output.replace('REPLACE_WITH_LIST_VALUES', self.list_of_ancs(redistricting_year))
        
        with open(f'docs/map_{redistricting_year}/ancs/index.html', 'w') as f:
            f.write(output)



    def list_of_ancs(self, redistricting_year):

        anc_districts = pd.merge(
            self.ancs[self.ancs.redistricting_year == redistricting_year]
            , self.districts[['smd_id', 'anc_id']], how='inner', on='anc_id'
            )

        display_df = anc_districts.groupby(['anc_id', 'anc_name', 'sort_order']).agg(count_of_smds=('smd_id', 'size')).reset_index().sort_values(by='sort_order')
        display_df['ANC'] = display_df.apply(lambda x: generate_link(x.anc_id, x.anc_name, link_source='anc'), axis=1)
        display_df['Count of SMDs'] = display_df['count_of_smds']

        columns_to_html = ['ANC', 'Count of SMDs']
        css_uuid = hashlib.sha224(display_df[columns_to_html].to_string().encode()).hexdigest() + '_'

        html = (
            display_df[columns_to_html]
            .fillna('')
            .style
            .set_uuid(css_uuid)
            .hide(axis='index')
            .to_html()
            )

        return html



    def old_new_heading(self, anc_id):

        if '2022' in anc_id:
            heading = (
                '<h2>Old ANCs</h2>'
                + '<p>These Advisory Neighborhood Commissions, from the previous redistricting cycle, cover the same area as this ANC.</p>'
                )
        else:
            heading = (
                '<h2>New ANCs</h2>'
                + '<p>These Advisory Neighborhood Commissions, from the next redistricting cycle, cover the same area as this ANC.</p>'
                )

        return heading



    def overlap_list(self, anc_id):
        """
        For one ANC, list the districts that overlap it with the percentage of overlap
        """

        try:
            overlap_anc_id_list = self.ancs[self.ancs.anc_id == anc_id].squeeze().overlap_ancs.split(', ')
        except:
            print('bad: ' + anc_id)
            print(self.ancs[self.ancs.anc_id == anc_id].squeeze().overlap_ancs)

        overlap_percentage_list = self.ancs[self.ancs.anc_id == anc_id].squeeze().overlap_percentage.split(', ')
        anc_name = self.ancs[self.ancs.anc_id == anc_id].anc_name.iloc[0]

        district_list = '<ul>'

        for i, overlap_anc_id in enumerate(overlap_anc_id_list):

            district_row = self.ancs[self.ancs.anc_id == overlap_anc_id].squeeze()

            if district_row['redistricting_year'] == 2022:
                oldnew = ['New', 'old']
            else:
                oldnew = ['Old', 'new']

            overlap_percentage_display = '{:.1%}'.format(float(overlap_percentage_list[i]))

            link_body = f'{oldnew[0]} {district_row.anc_name} ({overlap_percentage_display} of {oldnew[1]} {anc_name})'
            link_url = generate_url(district_row.anc_id, link_source='anc')

            district_list += f'<li><a href="{link_url}">{link_body}</a></li>'

        district_list += '</ul>'

        return district_list



    def build_all_anc_pages(self):
        """Build pages for each ANC"""

        for _, anc in tqdm(self.ancs.iterrows(), total=len(self.ancs), desc='ANCs   '):

            self.build_anc_page(anc)



    def build_anc_page(self, anc):
        """Build one ANC page"""

        with open('templates/anc.html', 'r') as f:
            output = f.read()
        
        output = add_google_analytics(output)
        output = add_geojson(self.geojson_shape, 'anc_id', anc.anc_id, output)
        
        output = output.replace('REPLACE_WITH_ANC_NAME', f'{anc.anc_name} [{anc.redistricting_cycle} Cycle]')
        
        if anc['redistricting_year'] == 2012:
            mapbox_slug_id = 'smd'
        else:
            mapbox_slug_id = 'smd-2022'

        output = output.replace('REPLACE_WITH_MAPBOX_SLUG', self.mapbox_style_slugs[mapbox_slug_id])


        smds_in_anc = self.districts[self.districts['anc_id'] == anc.anc_id]['smd_id'].to_list()
        output = output.replace('<!-- replace with district list -->', build_smd_html_table(
            smds_in_anc
            , link_source='anc'
            , district_comm_commelect=self.dcc
            , candidate_statuses=self.candidate_statuses
            ))

        fields_to_try = ['notes', 'link_block']
        output = output.replace('<!-- replace with anc link list -->', build_data_table(anc, fields_to_try, link_source='anc'))

        output = output.replace('<!-- replace with old/new heading -->', self.old_new_heading(anc.anc_id))
        output = output.replace('<!-- replace with overlap -->', self.overlap_list(anc.anc_id))
        
        output = output.replace('REPLACE_WITH_LONGITUDE', str(anc['centroid_lon']))
        output = output.replace('REPLACE_WITH_LATITUDE', str(anc['centroid_lat']))
        output = output.replace('REPLACE_WITH_ZOOM_LEVEL', str(calculate_zoom(anc['area'])))

        output = add_footer(output, link_source='anc')

        with open('docs/' + generate_url(anc.anc_id, link_source='root'), 'w') as f:
            f.write(output)



    def run(self):
        """Build pages for each ANC"""

        for ry in [2012, 2022]:
            self.anc_list_page(redistricting_year=ry)


        self.build_all_anc_pages()

        
