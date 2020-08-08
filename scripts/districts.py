"""
Build Single Member District pages
"""

import sys
import pytz
import numpy as np
import pandas as pd
from tqdm import tqdm
import geopandas as gpd
from datetime import datetime

from scripts.common import (
    build_district_list
    , build_data_table
    , add_footer
    , edit_form_link
    , add_google_analytics
    , add_geojson
    , current_commissioners
    )



class BuildDistricts():

    def __init__(self):

        # Load GeoJSON for all SMDs to memory
        self.smd_shape = gpd.read_file('maps/smd.geojson')


    def build_commissioner_table(self, smd_id):
        """
        Build table with information about the current commissioner
        """

        smd_display = smd_id.replace('smd_','')
        
        people = pd.read_csv('data/people.csv')
        commissioners = current_commissioners()

        people_commissioners = pd.merge(people, commissioners, how='inner', on='person_id')
        
        current_commissioner = people_commissioners[people_commissioners['smd_id'] == smd_id].squeeze()
        
        if len(current_commissioner) == 0:
            commissioner_table = '<p>Office is vacant.</p>'

        else:

            fields_to_try = ['full_name', 'commissioner_email']
            commissioner_table = build_data_table(current_commissioner, fields_to_try)
        
        return commissioner_table



    def add_candidates_in_status(self, html, candidates, status):
        pass



    def add_candidates(self, smd_id):
        """
        Add blocks of information for each candidate in SMD
        """
        
        people = pd.read_csv('data/people.csv')
        candidates = pd.read_csv('data/candidates.csv')
        statuses = pd.read_csv('data/candidate_statuses.csv')

        people_candidates = pd.merge(people, candidates, how='inner', on='person_id')
        people_candidate_statuses = pd.merge(people_candidates, statuses, how='inner', on='candidate_status')

        # Merge the order and status fields for sorting
        people_candidate_statuses['order_status'] = people_candidate_statuses['display_order'].astype(str) + ';' + people_candidate_statuses['candidate_status']
        
        # Randomize the order of candidates. Changes every day
        smd_candidates = people_candidate_statuses[people_candidate_statuses['smd_id'] == smd_id].sample(
            frac=1, random_state=self.today_as_int()).reset_index()
        
        num_candidates = len(smd_candidates)

        if num_candidates == 0:
            candidate_block = '<p>No known candidates.</p>'
            
        else:

            candidate_block = ''

            # todo: clean this up

            if len(smd_candidates['count_as_candidate'] == True) > 0:

                candidate_block += '<h3>Active Candidates</h3>'

                for status in sorted(smd_candidates.loc[smd_candidates['count_as_candidate'] == True, 'order_status'].unique()):

                    candidate_block += '<h4>' + status[status.find(';')+1:] + '</h4>'
                    candidates_in_status = len(smd_candidates[smd_candidates['order_status'] == status])

                    for idx, candidate_row in smd_candidates[smd_candidates['order_status'] == status].reset_index().iterrows():

                        # Add break between candidate tables if there is more than one candidate
                        if idx > 0:
                            candidate_block += '<br/>'

                        fields_to_try = [
                            'full_name'
                            , 'candidate_announced_date'
                            , 'candidate_source'
                            , 'candidate_source_description'
                            , 'candidate_source_link'
                            , 'pickup_date'
                            , 'filed_date'
                            , 'website_link'
                            , 'twitter_link'
                            , 'facebook_link'
                            , 'updated_at'
                            ]

                        candidate_block += build_data_table(candidate_row, fields_to_try)
                    
                    if candidates_in_status > 1:
                        candidate_block += '<p><em>Candidate order is randomized</em></p>'


            if len(smd_candidates['count_as_candidate'] == False) > 0:

                candidate_block += '<h3>Former Candidates</h3>'

                for status in sorted(smd_candidates.loc[smd_candidates['count_as_candidate'] == False, 'order_status'].unique()):

                    candidate_block += '<h4>' + status[status.find(';')+1:] + '</h4>'
                    candidates_in_status = len(smd_candidates[smd_candidates['order_status'] == status])

                    for idx, candidate_row in smd_candidates[smd_candidates['order_status'] == status].reset_index().iterrows():

                        # Add break between candidate tables if there is more than one candidate
                        if idx > 0:
                            candidate_block += '<br/>'

                        fields_to_try = [
                            'full_name'
                            , 'candidate_announced_date'
                            , 'candidate_source'
                            , 'candidate_source_description'
                            , 'candidate_source_link'
                            , 'pickup_date'
                            , 'filed_date'
                            , 'website_link'
                            , 'twitter_link'
                            , 'facebook_link'
                            , 'updated_at'
                            ]

                        candidate_block += build_data_table(candidate_row, fields_to_try)
                    
                    if candidates_in_status > 1:
                        candidate_block += '<p><em>Candidate order is randomized</em></p>'

        candidate_block += (
            "<p>The list of candidates comes from the Board of Elections and from edits to OpenANC. "
            + "Write-in candidates are included. If you know a candidate who isn't listed, please {}.</p>"
            ).format(edit_form_link('submit an edit'))

        return candidate_block


    def add_former_commissioners(self, smd_id):
        """
        Add blocks of information about former commissioners, if any are known
        """

        commissioners = pd.read_csv('data/commissioners.csv')
        people = pd.read_csv('data/people.csv')
        cp = pd.merge(commissioners, people, how='inner', on='person_id')

        former_comms = cp[(cp['commissioner_status'] == 'former') & (cp['smd_id'] == smd_id)].copy()
        former_comms.sort_values(by='term_start_date', inplace=True)

        fc_html = ''

        if len(former_comms) > 0:

            if len(former_comms) == 1:
                former_plural = ''
            else:
                former_plural = 's'

            fc_html += f'<h2>Former Commissioner{former_plural}</h2>'
            
            for idx, row in former_comms.reset_index().iterrows():

                # Add break between former commissioner tables if there is more than one former commissioner
                if idx > 0:
                    fc_html += '<br/>'

                fields_to_try = [
                    'full_name'
                    , 'term_start_date'
                    , 'term_end_date'
                    ]

                fc_html += build_data_table(row, fields_to_try)

        return fc_html




    def today_as_int(self):
        """
        Return today's date in Eastern Time as an integer. Use as a seed for candidate order randomization
        """

        tz = pytz.timezone('America/New_York')
        dc_now = datetime.now(tz)
        dc_now_str = dc_now.strftime('%Y%m%d')

        return int(dc_now_str)



    def build_better_know_a_district(self, smd_id):
        """
        Create table for district landmarks
        """
        
        districts = pd.read_csv('data/districts.csv')

        district_row = districts[districts['smd_id'] == smd_id].squeeze().dropna()

        fields_to_try = ['description', 'landmarks', 'notes']

        district_table = build_data_table(district_row, fields_to_try)

        if district_table == '':
            district_table = '<p>No landmarks for this district. {}</p>'.format(edit_form_link('Submit one!'))
        
        return district_table



    def run(self):
        """
        Build pages for each SMD
        """

        districts = pd.read_csv('data/districts.csv')
        map_colors = pd.read_csv('data/map_colors.csv')
        district_colors = pd.merge(districts, map_colors, how='inner', on='map_color_id')

        # todo: sort by smd_id first
        for idx, row in tqdm(district_colors.iterrows(), total=len(district_colors), desc='SMDs '):
        # for idx, row in district_colors.iterrows():

            smd_id = row['smd_id']
            smd_display = smd_id.replace('smd_','')
            smd_display_lower = smd_display.lower()

            anc_id = row['anc_id']
            anc_display_upper = 'ANC' + anc_id
            anc_display_lower = anc_display_upper.lower()

            # if smd_id != 'smd_1B05':
            #     continue

            with open('templates/district.html', 'r') as f:
                output = f.read()
                
            output = output.replace('REPLACE_WITH_SMD', smd_display)
            
            output = add_google_analytics(output)
            output = add_geojson(self.smd_shape, 'smd_id', smd_id, output)

            output = output.replace('<!-- replace with commissioner table -->', self.build_commissioner_table(smd_id))
            output = output.replace('<!-- replace with candidate table -->', self.add_candidates(smd_id))
            output = output.replace('<!-- replace with former commissioner table -->', self.add_former_commissioners(smd_id))
            output = output.replace('<!-- replace with better know a district -->', self.build_better_know_a_district(smd_id))

            neighbor_smd_ids = [('smd_' + d) for d in row['neighbor_smds'].split(', ')]
            output = output.replace('<!-- replace with neighbors -->', build_district_list(neighbor_smd_ids, level=2))


            output = output.replace('REPLACE_WITH_WARD', str(row['ward']))
            output = output.replace('REPLACE_WITH_ANC_UPPER', anc_display_upper)
            output = output.replace('REPLACE_WITH_ANC_LOWER', anc_display_lower)

            output = output.replace('REPLACE_WITH_LONGITUDE', str(row['centroid_lon']))
            output = output.replace('REPLACE_WITH_LATITUDE', str(row['centroid_lat']))

            output = output.replace('REPLACE_WITH_COLOR', row['color_hex'])

            output = add_footer(output, level=2)

            with open(f'docs/ancs/districts/{smd_display_lower}.html', 'w') as f:
                f.write(output)



