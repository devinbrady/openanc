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
from collections import OrderedDict

from scripts.common import (
    build_district_list
    , build_data_table
    , build_link_block
    , add_footer
    , edit_form_link
    , add_google_analytics
    , add_geojson
    , list_commissioners
    , assemble_divo
    , build_results_candidate_people
    )



class BuildDistricts():

    def __init__(self):

        # Load GeoJSON for all SMDs to memory
        self.smd_shape = gpd.read_file('maps/smd.geojson')

        self.commissioners = list_commissioners(status=None)

        self.write_in_winners = pd.read_csv('data/write_in_winners.csv')



    def build_commissioner_table(self, smd_id):
        """
        Build table with information about the current commissioner
        """

        # Dict is status_name: display_name
        comm_status = OrderedDict({
            'future': 'Commissioner-Elect'
            , 'current': 'Current Commissioner'
            , 'former': 'Former Commissioner'
            })

        smd_display = smd_id.replace('smd_','')
        
        people = pd.read_csv('data/people.csv')

        people_commissioners = pd.merge(people, self.commissioners, how='inner', on='person_id')
        
        smd_commissioners = people_commissioners[people_commissioners['smd_id'] == smd_id].sort_values(by='start_date').copy()

        vacant_string = '<h2>Current Commissioner</h2><p>This office is vacant.</p>'
        if len(smd_commissioners) == 0:
            commissioner_block = vacant_string
        
        else:

            commissioner_block = ''

            smd_commissioners['link_block'] = smd_commissioners.apply(
                lambda row: build_link_block(
                    row, fields_to_try=['website_link', 'twitter_link', 'facebook_link'])
                , axis=1
                )

            for status in comm_status:

                commissioners_in_status = smd_commissioners[smd_commissioners['is_' + status]].copy()

                if len(commissioners_in_status) == 0:

                    # If there are former commissioners but no one currently, note that. 
                    if status == 'current':
                        commissioner_block += vacant_string
                    
                    # There are no commissioners in this status, display nothing, continue to next iteration
                    continue
                elif len(commissioners_in_status) == 1:
                    plural = ''
                else:
                    plural = 's'

                commissioner_block += f'<h2>{comm_status[status]}{plural}</h2>'

                # Don't display links for former commissioners
                if status == 'former':
                    fields_to_try = ['full_name', 'term_in_office']
                else:
                    fields_to_try = ['full_name', 'link_block', 'term_in_office', 'ok']

                for idx, row in commissioners_in_status.iterrows():

                    # Add line breaks between commissioners
                    if commissioner_block[-5:] != '</h2>':
                        commissioner_block += '<br/>'

                    commissioner_block += build_data_table(row, fields_to_try)
        
        return commissioner_block



    def add_results(self, smd_id):
        """
        Add block of information about the results of the election
        """

        smd_display = smd_id.replace('smd_','')

        people = pd.read_csv('data/people.csv')
        candidates = pd.read_csv('data/candidates.csv')
        results = pd.read_csv('data/results.csv')
        field_names = pd.read_csv('data/field_names.csv')

        write_in_winners_people = pd.merge(self.write_in_winners, people, how='inner', on='person_id')

        rcp = build_results_candidate_people()
        rcp.loc[rcp.is_incumbent, 'full_name'] = rcp.loc[rcp.is_incumbent, 'full_name'] + ' (incumbent)'

        # Show the candidate with the most votes first
        smd_results = rcp[rcp['smd_id'] == smd_id].sort_values(by='votes', ascending=False).copy()

        num_candidates = len(smd_results)

        results_block = '<h2>2020 Election Results</h2>'

        if num_candidates == 0:
            results_block += '<p>No known candidates.</p>'

        else:

            # Add total row
            smd_results.loc[9999, 'full_name'] = 'Total Votes'
            smd_results.loc[9999, 'votes'] = smd_results.votes.sum()
            smd_results.loc[9999, 'vote_share'] = '100.00%'

            fields_to_try = [
                'full_name'
                , 'votes'
                , 'vote_share'
                , 'margin_of_victory'
                , 'margin_of_victory_percentage'
            ]

            smd_results['margin_of_victory'] = smd_results['margin_of_victory'].apply(lambda x: '' if pd.isnull(x) else '+{:,.0f}'.format(x))
            smd_results['margin_of_victory_percentage'] = smd_results['margin_of_victory_percentage'].apply(lambda x: '' if pd.isnull(x) else '+' + x )
            smd_results['votes'] = smd_results['votes'].apply(lambda x: '{:,.0f}'.format(x)).fillna('')

            fields_to_html = []
            for field_name in fields_to_try:
                display_name = field_names.loc[field_names['field_name'] == field_name, 'display_name'].values[0]
                smd_results[display_name] = smd_results[field_name]
                fields_to_html += [display_name]

            results_block += (
                smd_results[fields_to_html]
                .fillna('')
                .style
                .set_properties(**{'text-align': 'right'})
                .set_properties(
                    subset=['Name']
                    , **{'text-align': 'left'}
                    )
                .apply(
                    lambda x: ['font-weight: bold' if x.Name == 'Total Votes' else '' for i in x]
                    , axis=1
                    )
                .set_uuid('results_')
                .hide_index()
                .render()
                )

            if smd_results['write_in_winner_int'].sum() > 0:

                # If there is a write-in winner, include their name here. Otherwise, no one won and the district will be vacant.

                if (write_in_winners_people.smd_id == smd_id).sum() > 0:

                    commissioner_elect = write_in_winners_people[write_in_winners_people.smd_id == smd_id]['full_name'].values[0]

                    results_block += (
                        f'<p>This election was won by <strong>{commissioner_elect}</strong>, a write-in candidate whose "Affirmation of Write-in Candidacy" was accepted by the DC Board of Elections.</p>'
                        )

                else:

                    results_block += (
                        '<p>There was no winner in this election. None of the write-in candidates filed an "Affirmation of Write-in Candidacy" '
                        + 'that was accepted by the the DC Board of Elections. '
                        + f'The office of {smd_display} Commissioner will be vacant.</p>'
                        )

                results_block += '<p>Vote counts for individual write-in candidates are not published by the DC Board of Elections.</p>'


        # Add comparison of votes in this SMD to others
        # results_block += '<h3>SMD Vote Ranking</h3>'

        # divo = assemble_divo()
        # divo_smd = divo[divo['smd_id'] == smd_id].squeeze()
        
        # fields_to_try = ['string_dc', 'string_ward', 'string_anc']
        # results_block += build_data_table(divo_smd, fields_to_try)

        return results_block



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

        candidate_block = '<h2>2020 Candidates</h2>'

        if num_candidates == 0:
            candidate_block += '<p>No known candidates.</p>'
            
        else:

            # todo: clean this up

            if sum(smd_candidates['count_as_candidate'] == True) == 0:

                candidate_block += '<p>No active candidates.</p>'

            else:

                for status in sorted(smd_candidates.loc[smd_candidates['count_as_candidate'] == True, 'order_status'].unique()):

                    candidate_block += '<h3>' + status[status.find(';')+1:] + '</h3>'
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
                            , 'manual_source_link'
                            , 'website_link'
                            , 'twitter_link'
                            , 'facebook_link'
                            , 'updated_at'
                            ]

                        candidate_block += build_data_table(candidate_row, fields_to_try)
                    
                    if candidates_in_status > 1:
                        candidate_block += '<p><em>Candidate order is randomized</em></p>'


            if sum(smd_candidates['count_as_candidate'] == False) > 0:

                candidate_block += '<h2>Former Candidates</h2>'

                for status in sorted(smd_candidates.loc[smd_candidates['count_as_candidate'] == False, 'order_status'].unique()):

                    candidate_block += '<h3>' + status[status.find(';')+1:] + '</h3>'
                    candidates_in_status = len(smd_candidates[smd_candidates['order_status'] == status])

                    for idx, candidate_row in smd_candidates[smd_candidates['order_status'] == status].reset_index().iterrows():

                        # Add break between candidate tables if there is more than one candidate
                        if idx > 0:
                            candidate_block += '<br/>'

                        fields_to_try = [
                            'full_name'
                            , 'updated_at'
                            ]

                        candidate_block += build_data_table(candidate_row, fields_to_try)
                    
                    if candidates_in_status > 1:
                        candidate_block += '<p><em>Candidate order is randomized</em></p>'

        candidate_block += (
            "<p>The list of candidates comes from the DC Board of Elections and from edits to OpenANC. "
            + "Write-in candidates are included. If you know a candidate who isn't listed, please {}.</p>"
            ).format(edit_form_link('submit an edit'))

        return candidate_block



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

        fields_to_try = ['landmarks', 'notes']

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

        # Calculate the updated_at for each SMD. Where the SMD has no more active candidates, use the max updated_at across all candidates
        candidates = pd.read_csv('data/candidates.csv')
        district_candidates = pd.merge(districts, candidates, how='left', on='smd_id')
        max_updated_at = district_candidates['updated_at'].dropna().max()
        smd_updated_at = district_candidates[['smd_id', 'updated_at']].fillna(value={'updated_at': max_updated_at})
        smd_max_updated_at = smd_updated_at.groupby('smd_id').agg({'updated_at': max})
        smd_max_updated_at['updated_at'] = pd.to_datetime(smd_max_updated_at['updated_at'])
        smd_max_updated_at['updated_at_formatted'] = smd_max_updated_at['updated_at'].dt.strftime('%B %-d, %Y')

        # Process SMDs in order by smd_id
        district_colors = district_colors.sort_values(by='smd_id')

        for idx, row in tqdm(district_colors.iterrows(), total=len(district_colors), desc='SMDs '):
        # for idx, row in district_colors.iterrows():

            smd_id = row['smd_id']
            smd_display = smd_id.replace('smd_','')
            smd_display_lower = smd_display.lower()

            anc_id = row['anc_id']
            anc_display_upper = 'ANC' + anc_id
            anc_display_lower = anc_display_upper.lower()

            # if smd_id != 'smd_1C07':
            #     continue

            with open('templates/district.html', 'r') as f:
                output = f.read()
                
            output = output.replace('REPLACE_WITH_SMD', smd_display)
            
            output = add_google_analytics(output)
            output = add_geojson(self.smd_shape, 'smd_id', smd_id, output)

            output = output.replace('<!-- replace with commissioner table -->', self.build_commissioner_table(smd_id))
            output = output.replace('<!-- replace with candidate table -->', self.add_results(smd_id))
            output = output.replace('<!-- replace with better know a district -->', self.build_better_know_a_district(smd_id))

            neighbor_smd_ids = [('smd_' + d) for d in row['neighbor_smds'].split(', ')]
            output = output.replace('<!-- replace with neighbors -->', build_district_list(neighbor_smd_ids, level=2))


            output = output.replace('REPLACE_WITH_WARD', str(row['ward']))
            output = output.replace('REPLACE_WITH_ANC_UPPER', anc_display_upper)
            output = output.replace('REPLACE_WITH_ANC_LOWER', anc_display_lower)

            output = output.replace('REPLACE_WITH_LONGITUDE', str(row['centroid_lon']))
            output = output.replace('REPLACE_WITH_LATITUDE', str(row['centroid_lat']))

            output = output.replace('REPLACE_WITH_COLOR', row['color_hex'])

            # Use the date this script was run on as the updated_at date
            tz = pytz.timezone('America/New_York')
            dc_now = datetime.now(tz).strftime('%B %-d, %Y')
            output = add_footer(output, level=2, updated_at=dc_now)

            # Use the date when the underlying data was updated as the updated_at date
            # output = add_footer(output, level=2, updated_at=smd_max_updated_at.loc[smd_id, 'updated_at_formatted'])

            with open(f'docs/ancs/districts/{smd_display_lower}.html', 'w') as f:
                f.write(output)



