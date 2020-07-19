"""
Build Single Member District pages
"""

import numpy as np
import pandas as pd
from tqdm import tqdm
from bs4 import BeautifulSoup

from scripts.common import build_district_list, build_data_table, build_footer, edit_form_link, google_analytics_block


class BuildDistricts():


    def build_commissioner_table(self, smd_id):

        smd_display = smd_id.replace('smd_','')
        
        people = pd.read_csv('data/people.csv')
        commissioners = pd.read_csv('data/commissioners.csv')

        people_commissioners = pd.merge(people, commissioners, how='inner', on='person_id')
        
        current_commissioner = people_commissioners[people_commissioners['smd_id'] == smd_id].squeeze()
        
        if len(current_commissioner) == 0:
            commissioner_table = '<p>Office is vacant.</p>'

        else:

            fields_to_try = ['full_name', 'commissioner_email']
            commissioner_table = build_data_table(current_commissioner, fields_to_try)
        
        return commissioner_table


    def add_candidates(self, smd_id):
        """Add multiple candidates"""
        
        people = pd.read_csv('data/people.csv')
        candidates = pd.read_csv('data/candidates.csv')

        people_candidates = pd.merge(people, candidates, how='inner', on='person_id')
        
        # randomize the order of candidates
        current_candidates = people_candidates[people_candidates['smd_id'] == smd_id].sample(frac=1).reset_index()
        
        num_candidates = len(current_candidates)

        if num_candidates == 0:
            candidate_block = '<p>No known candidates.</p>'
            
        else:

            candidate_block = ''

            for idx, candidate_row in current_candidates.iterrows():

                # Add break between candidate tables if there is more than one candidate
                if idx > 0:
                    candidate_block += '<br/>'

                fields_to_try = [
                    'full_name'
                    , 'candidate_status'
                    , 'candidate_announced_date'
                    , 'candidate_source'
                    , 'candidate_source_link'
                    , 'pickup_date'
                    , 'filed_date'
                    , 'twitter_link'
                    , 'facebook_link'
                    ]

                candidate_block += build_data_table(candidate_row, fields_to_try)
                

            candidate_block += (
                "<p>The list of candidates comes from the Board of Elections and from edits to OpenANC. "
                + "Write-in candidates are included. If you know a candidate who isn't listed, please {}.</p>"
                ).format(edit_form_link('submit an edit'))

            if num_candidates > 1:
                candidate_block += '<p><em>Candidate order is randomized</em></p>'


        return candidate_block


    def build_better_know_a_district(self, smd_id):
        """Create table for district landmarks"""
        
        districts = pd.read_csv('data/districts.csv')

        district_row = districts[districts['smd_id'] == smd_id].squeeze().dropna()

        fields_to_try = ['description', 'landmarks', 'notes']

        district_table = build_data_table(district_row, fields_to_try)

        if district_table == '':
            district_table = '<p>No landmarks for this district. {}</p>'.format(edit_form_link('Submit one!'))
        
        return district_table




    def run(self):
        """Build pages for each SMD"""

        districts = pd.read_csv('data/districts.csv')
        map_colors = pd.read_csv('data/map_colors.csv')
        district_colors = pd.merge(districts, map_colors, how='inner', on='map_color_id')

        
        for idx, row in tqdm(district_colors.iterrows(), total=len(district_colors), desc='SMDs'):

            smd_id = row['smd_id']
            smd_display = smd_id.replace('smd_','')

            anc_id = row['anc_id']
            anc_display_upper = 'ANC' + anc_id
            anc_display_lower = anc_display_upper.lower()

            # if smd_id != 'smd_1C07':
            #     continue
                    
            with open('templates/smd.html', 'r') as f:
                output = f.read()
                
            output = output.replace('REPLACE_WITH_SMD', smd_display)
            
            output = output.replace('<!-- replace with google analytics -->', google_analytics_block())
            output = output.replace('<!-- replace with commissioner table -->', self.build_commissioner_table(smd_id))
            output = output.replace('<!-- replace with candidate table -->', self.add_candidates(smd_id))
            output = output.replace('<!-- replace with better know a district -->', self.build_better_know_a_district(smd_id))

            neighbor_smd_ids = [('smd_' + d) for d in row['neighbor_smds'].split(', ')]
            output = output.replace('<!-- replace with neighbors -->', build_district_list(neighbor_smd_ids, level=2))


            output = output.replace('REPLACE_WITH_ANC_UPPER', anc_display_upper)
            output = output.replace('REPLACE_WITH_ANC_LOWER', anc_display_lower)

            output = output.replace('REPLACE_WITH_LONGITUDE', str(row['centroid_lon']))
            output = output.replace('REPLACE_WITH_LATITUDE', str(row['centroid_lat']))

            output = output.replace('REPLACE_WITH_COLOR', row['color_hex'])

            output = output.replace('<!-- replace with footer -->', build_footer())

            # soup = BeautifulSoup(output, 'html.parser')
            # output_pretty = soup.prettify()

            with open(f'docs/ancs/districts/{smd_display}.html', 'w') as f:
                f.write(output)



