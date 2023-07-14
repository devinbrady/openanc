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

import config

from scripts.common import (
    build_district_list
    , build_data_table
    , build_link_block
    , add_footer
    , add_google_analytics
    , add_geojson
    , assemble_divo
    , mapbox_slugs
    , candidate_form_link
    , smd_geojson
    )

from scripts.urls import (
    generate_url
    , generate_link
    )


from scripts.data_transformations import (
    list_commissioners
    , list_candidates
    , people_dataframe
    , results_candidate_people
    , today_as_int
)



class BuildDistricts():

    def __init__(self):

        self.smd_shape = smd_geojson()

        self.mapbox_style_slugs = mapbox_slugs()

        self.commissioners = list_commissioners(status=None)
        self.commissioners_current = list_commissioners(status='current')
        self.people = people_dataframe()
        self.candidates_this_year = list_candidates(election_year=2022)
        
        self.rcp = results_candidate_people()
        self.rcp.loc[self.rcp.is_incumbent, 'full_name'] = self.rcp.loc[self.rcp.is_incumbent, 'full_name'] + ' (incumbent)'

        self.districts = pd.read_csv('data/districts.csv')
        write_in_winners = pd.read_csv('data/dcboe/write_in_winners.csv')
        self.field_names = pd.read_csv('data/field_names.csv')
        self.ancs = pd.read_csv('data/ancs.csv')
        self.wards = pd.read_csv('data/wards.csv')
        self.statuses = pd.read_csv('data/candidate_statuses.csv')
        lookup = pd.read_csv('data/external_id_lookup.csv').drop('full_name', axis=1)

        self.people_commissioners = pd.merge(self.people, self.commissioners, how='inner', on='person_id')
        write_in_winners_lookup = pd.merge(write_in_winners, lookup, how='inner', on='external_id')
        self.write_in_winners_people = pd.merge(write_in_winners_lookup, self.people, how='inner', on='person_id')

        people_candidates = pd.merge(self.people, self.candidates_this_year, how='inner', on='person_id')
        self.people_candidate_statuses = pd.merge(people_candidates, self.statuses, how='inner', on='candidate_status')

        # Merge the order and status fields for sorting
        self.people_candidate_statuses['order_status'] = self.people_candidate_statuses['display_order'].astype(str) + ';' + self.people_candidate_statuses['candidate_status']

        self.people_candidate_statuses['link_block'] = self.people_candidate_statuses.apply(
            lambda row: build_link_block(
                row, fields_to_try=['website_link', 'mastodon_link', 'twitter_link', 'facebook_link'])
            , axis=1
            )

        # Shuffle the order of candidates. Changes every day
        self.people_candidate_statuses.sample(frac=1, random_state=today_as_int())



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
        
        smd_commissioners = self.people_commissioners[self.people_commissioners['smd_id'] == smd_id].sort_values(by='start_date', ascending=False).copy()

        vacant_string = '<h2>Current Commissioner</h2><p>This office is vacant.</p>'
        if len(smd_commissioners) == 0:

            if '_2022_' in smd_id:
                commissioner_block = vacant_string
        
        else:

            commissioner_block = ''

            smd_commissioners['link_block'] = smd_commissioners.apply(
                lambda row: build_link_block(
                    row, fields_to_try=['website_link', 'mastodon_link', 'twitter_link', 'facebook_link'])
                , axis=1
                )

            for status in comm_status:

                commissioners_in_status = smd_commissioners[smd_commissioners['is_' + status]].copy()

                if len(commissioners_in_status) == 0:

                    # If there are former commissioners but no one currently, note that. 
                    # todo Jan 2023: remove this second clause of IF statement
                    if status == 'current' and '_2022_' not in smd_id:
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
                    fields_to_try = ['full_name', 'link_block', 'term_in_office']

                for idx, row in commissioners_in_status.iterrows():

                    # Add line breaks between commissioners
                    if commissioner_block[-5:] != '</h2>':
                        commissioner_block += '<br/>'

                    commissioner_block += build_data_table(row, fields_to_try, link_source='district')
        
        return commissioner_block



    def add_results(self, smd_id):
        """Add block of information about the results of the election"""

        smd_results_all_years = self.rcp[self.rcp['smd_id'] == smd_id].copy()

        for election_year in smd_results_all_years.election_year.unique():
            
            # Show the candidate with the most votes first
            smd_results = smd_results_all_years[smd_results_all_years.election_year == election_year].sort_values(by='votes', ascending=False).copy().copy()

            num_candidates = len(smd_results)

            results_block = f'<h2>{election_year} Election Results</h2>'

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

                smd_results['full_name'] = smd_results.apply(
                    lambda x: generate_link(x.person_name_id, link_source='district', link_body=x.full_name)
                            if x.full_name not in ['Write-ins combined', 'Total Votes'] else x.full_name
                    , axis=1
                    )

                smd_results['votes'] = smd_results['votes'].apply(lambda x: '{:,.0f}'.format(x)).fillna('')

                fields_to_html = []
                for field_name in fields_to_try:
                    display_name = self.field_names.loc[self.field_names['field_name'] == field_name, 'display_name'].values[0]
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
                    .hide(axis='index')
                    .to_html()
                    )

                if smd_id in ('smd_2022_1E01', 'smd_2022_6E08', 'smd_2022_7D10'):
                    results_block += ('<p>There was a named candidate on the ballot who withdrew but still received the most votes. '
                        + 'As such, there was no winner for this contest and the office was vacant after the election.</p>'
                        )

                if smd_results['write_in_winner_int'].sum() > 0:

                    # If there is a write-in winner, include their name here. Otherwise, no one won and the district will be vacant.

                    if (self.write_in_winners_people.smd_id == smd_id).sum() > 0:

                        commissioner_elect = self.write_in_winners_people[self.write_in_winners_people.smd_id == smd_id]['full_name'].values[0]

                        results_block += (
                            f'<p>This election was won by <strong>{commissioner_elect}</strong>, a write-in candidate whose "Affirmation of Write-in Candidacy" was accepted by the DC Board of Elections.</p>'
                            )

                    else:

                        smd_name = self.districts[self.districts['smd_id'] == smd_id]['smd_name'].iloc[0]

                        if smd_id in ('smd_2022_3E07', 'smd_2022_6E02'):
                            results_block += ('<p>Two write-in candidates tied in this election. See "Notes" below.</p>')

                        else:
                            results_block += (
                                '<p>There was no winner in this election. None of the write-in candidates filed an "Affirmation of Write-in Candidacy" '
                                + 'that was accepted by the DC Board of Elections. '
                                + f'The office of {smd_name} Commissioner was vacant after the {election_year} election.</p>'
                                )

                    results_block += '<p>Vote counts for individual write-in candidates are not published by the DC Board of Elections.</p>'


        return results_block



    def candidate_status_block(self, smd_candidates, status, fields_to_try):
        """Return string containing a long table of the attributes of all candidates in a particular status"""

        csb = ''

        csb += '<h3>Status: ' + status[status.find(';')+1:] + '</h3>'
        candidates_in_status = len(smd_candidates[smd_candidates['order_status'] == status])

        for idx, candidate_row in smd_candidates[smd_candidates['order_status'] == status].reset_index().iterrows():

            # Add break between candidate tables if there is more than one candidate
            if idx > 0:
                csb += '<br/>'

            csb += build_data_table(candidate_row, fields_to_try, link_source='district')

        if candidates_in_status > 1:
            csb += '<p><em>Candidate order is randomized.</em></p>'

        return csb



    def add_candidates(self, smd_id):
        """
        Add blocks of information for each candidate in SMD
        """
        
        if '_2022_' not in smd_id:
            return ''

        smd_candidates = self.people_candidate_statuses[self.people_candidate_statuses['smd_id'] == smd_id].reset_index()
        num_candidates = len(smd_candidates)

        active_candidate_fields = [
            'full_name'
            , 'candidate_announced_date'
            , 'candidate_source'
            , 'candidate_source_description'
            , 'manual_source_link'
            , 'link_block'
            , 'updated_at'
            ]

        inactive_candidate_fields = [
            'full_name'
            , 'updated_at'
            ]


        candidate_block = '<h2>2022 Candidates</h2>'

        if num_candidates == 0:
            # candidate_form = candidate_form_link('Declare your candidacy using this form', smd_id=smd_id)
            candidate_block += f'<p>No known candidates.</p>'
            
        else:

            if sum(smd_candidates['count_as_candidate'] == True) == 0:
                candidate_block += '<p>No active candidates.</p>'

            else:

                for status in sorted(smd_candidates.loc[smd_candidates['count_as_candidate'] == True, 'order_status'].unique()):
                    candidate_block += self.candidate_status_block(smd_candidates=smd_candidates, status=status, fields_to_try=active_candidate_fields)


            if sum(smd_candidates['count_as_candidate'] == False) > 0:

                candidate_block += '<h2>2022 Former Candidates</h2>'

                for status in sorted(smd_candidates.loc[smd_candidates['count_as_candidate'] == False, 'order_status'].unique()):
                    candidate_block += self.candidate_status_block(smd_candidates=smd_candidates, status=status, fields_to_try=inactive_candidate_fields)


        candidate_block += (
            "<p>The list of candidates comes from the DC Board of Elections and from submissions to OpenANC. "
            + "Write-in candidates are included."
            )
            # If you know a candidate who isn't listed, please {}.</p>"
            # ).format(candidate_form_link('fill out this form', smd_id=smd_id))

        return candidate_block



    def build_better_know_a_district(self, smd_id):
        """
        Create table for district landmarks
        """
        
        district_row = self.districts[self.districts['smd_id'] == smd_id].squeeze().dropna()

        fields_to_try = ['landmarks', 'notes']

        district_table = build_data_table(district_row, fields_to_try, link_source='district')

        # Only display district info section if district info exists for this district.
        if district_table != '':
            district_table = '<h2>Better Know a District</h2>\n' + district_table
        
        return district_table



    def old_new_heading(self, smd_id):
        """Alternate between different language for the overlap section based on which redistricting cycle this is."""

        if '_2022_' in smd_id:
            heading = (
                '<h2>Old Districts</h2>'
                + '<p>These districts, from the previous redistricting cycle, cover the same area as this district.</p>'
                )
        else:
            heading = (
                '<h2>New Districts</h2>'
                + '<p>These districts, from the next redistricting cycle, cover the same area as this district.</p>'
                )

        return heading



    def overlap_list(self, smd_id):
        """
        For one SMD, list the districts that overlap it with the percentage of overlap

        Bulleted list of districts and current commmissioners

        If smd_id_list is None, all districts are returned
        If smd_id_list is a list, those SMDs are returned

        If show_redistricting_cycle is True, then the year of the cycle will be displayed.
        """

        dc = pd.merge(self.districts, self.commissioners_current, how='left', on='smd_id')
        dcp = pd.merge(dc, self.people, how='left', on='person_id')

        dcp['full_name'] = dcp['full_name'].fillna('(vacant)')

        try:
            overlap_smd_id_list = self.districts[self.districts.smd_id == smd_id].squeeze().overlap_smds.split(', ')
        except:
            print('bad: ' + smd_id)
            print(self.districts[self.districts.smd_id == smd_id].squeeze().overlap_smds)

        overlap_percentage_list = self.districts[self.districts.smd_id == smd_id].squeeze().overlap_percentage.split(', ')
        smd_name = dcp[dcp.smd_id == smd_id].smd_name.iloc[0]

        district_list = '<ul>'

        for i, overlap_smd_id in enumerate(overlap_smd_id_list):

            district_row = dcp[dcp.smd_id == overlap_smd_id].squeeze()

            if district_row['full_name'] == '(vacant)':
                if district_row['redistricting_year'] == 2022:
                    commissioner_name = ''
                else:
                    commissioner_name = ': (vacant)'
            else:
                commissioner_name = ': Commissioner ' + district_row['full_name']

            if district_row['redistricting_year'] == 2022:
                oldnew = ['New', 'old']
            else:
                oldnew = ['Old', 'new']

            overlap_percentage_display = '{:.1%}'.format(float(overlap_percentage_list[i]))

            link_body = f'{oldnew[0]} {district_row.smd_name}{commissioner_name} ({overlap_percentage_display} of {oldnew[1]} {smd_name})'
            link_url = generate_url(district_row.smd_id, link_source='district')

            district_list += f'<li><a href="{link_url}">{link_body}</a></li>'


        district_list += '</ul>'

        return district_list



    def run(self):
        """
        Build pages for each SMD
        """

        district_ancs = pd.merge(self.districts, self.ancs[['anc_id', 'anc_name']], how='inner', on='anc_id')
        district_wards = pd.merge(district_ancs, self.wards[['ward_id', 'ward_name']], how='inner', on='ward_id')

        # Calculate the updated_at for each SMD. Where the SMD has no more active candidates, use the max updated_at across all candidates
        district_candidates = pd.merge(self.districts, self.candidates_this_year, how='left', on='smd_id')
        max_updated_at = district_candidates['updated_at'].dropna().max()
        smd_updated_at = district_candidates[['smd_id', 'updated_at']].fillna(value={'updated_at': max_updated_at})
        smd_max_updated_at = smd_updated_at.groupby('smd_id').agg({'updated_at': max})
        smd_max_updated_at['updated_at'] = pd.to_datetime(smd_max_updated_at['updated_at'])
        smd_max_updated_at['updated_at_formatted'] = smd_max_updated_at['updated_at'].dt.strftime('%B %-d, %Y')

        # Process SMDs in order by smd_id
        district_wards = district_wards.sort_values(by=['redistricting_year', 'smd_id'])

        for idx, row in tqdm(district_wards.iterrows(), total=len(district_wards), desc='SMDs   '):
        # for idx, row in district_wards.iterrows():

            smd_id = row['smd_id']

            # debug: Dorchester House
            # if smd_id not in ('smd_1C06', 'smd_2022_1C09'):
            #     continue

            # debug: Santiago Lakatos
            # if smd_id not in ('smd_2022_1B04'):
            #     continue


            with open('templates/district.html', 'r') as f:
                output = f.read()
                
            output = output.replace('REPLACE_WITH_MAPBOX_GL_JS_VERSION', config.mapbox_gl_js_version)
            output = output.replace('REPLACE_WITH_SMD_NAME', f'{row.smd_name} [{row.redistricting_cycle} Cycle]')

            if row['redistricting_year'] == 2012:
                mapbox_slug_id = 'smd'
            else:
                mapbox_slug_id = 'smd-2022'

            output = output.replace('REPLACE_WITH_MAPBOX_SLUG', self.mapbox_style_slugs[mapbox_slug_id])
            
            output = add_google_analytics(output)
            output = add_geojson(self.smd_shape, 'smd_id', smd_id, output)

            output = output.replace('<!-- replace with commissioner table -->', self.build_commissioner_table(smd_id))
            # output = output.replace('<!-- replace with candidate table -->', self.add_candidates(smd_id))
            output = output.replace('<!-- replace with results table -->', self.add_results(smd_id))
            output = output.replace('<!-- replace with better know a district -->', self.build_better_know_a_district(smd_id))

            output = output.replace('<!-- replace with old/new heading -->', self.old_new_heading(smd_id))
            output = output.replace('<!-- replace with overlap -->', self.overlap_list(smd_id))

            neighbor_smd_ids = row['neighbor_smds'].split(', ')
            output = output.replace('<!-- replace with neighbors -->', build_district_list(neighbor_smd_ids, link_source='district', show_redistricting_cycle=True))

            output = output.replace('REPLACE_WITH_WARD_URL', generate_url(row.ward_id, link_source='district'))
            output = output.replace('REPLACE_WITH_WARD_NAME', row.ward_name)
            output = output.replace('REPLACE_WITH_ANC_URL', generate_url(row.anc_id, link_source='district'))
            output = output.replace('REPLACE_WITH_ANC_NAME', row.anc_name)

            output = output.replace('REPLACE_WITH_LONGITUDE', str(row['centroid_lon']))
            output = output.replace('REPLACE_WITH_LATITUDE', str(row['centroid_lat']))

            output = add_footer(output, link_source='district')


            with open('docs/' + generate_url(smd_id, link_source='root'), 'w') as f:
                f.write(output)



