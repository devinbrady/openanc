"""
Pull down fresh data from Google Sheets to CSV
"""

import pytz
import pickle
import string
import os.path
import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path
from datetime import datetime
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow


import config

from scripts.common import (
    assemble_divo
    , match_to_openanc
    )

from scripts.urls import (
    generate_url
    , format_name_for_url
    )

from scripts.data_transformations import (
    list_commissioners
    , list_candidates
    , people_dataframe
    , districts_candidates_commissioners
    , confirm_key_uniqueness
    )



class RefreshData():

    def __init__(self):

        self.match_file = Path('data/matches_to_evaluate.csv')

        # If modifying these scopes, delete the file token.pickle.
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets']

        # The ID and range of a sample spreadsheet.

        self.spreadsheet_ids = {
            'openanc_source': '1QGki43vKLKJyG65Rd3lSKJwO_B3yX96SCljzmd9YJhk'
            , 'openanc_published': '1XoT92wFBKdmnUc6AXwABeWNjsjcwrGMPMKu1XsBOygU'
        }

        self.service = self.google_auth()



    def google_auth(self):
        """
        Autheticate to Google Sheets API
        Source: https://developers.google.com/sheets/api/quickstart/python
        """

        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.

        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.scopes)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        service = build('sheets', 'v4', credentials=creds)
        
        return service



    def upload_to_google_sheets(self, df, columns_to_publish, destination_spreadsheet, destination_sheet):
        """
        Push values to a Google Sheet

        Note that dates are not JSON serializable, so dates have to be converted to strings
        """

        for c in columns_to_publish:
            if c not in df.columns:
                raise ValueError(f'Column "{c}" not in the DataFrame to be uploaded to Google Sheets.')

            df[c] = df[c].fillna('')

        values = [columns_to_publish]
        values += df[columns_to_publish].to_numpy().tolist()

        body = {'values': values}

        # value_input_option = 'RAW'
        value_input_option = 'USER_ENTERED'

        spreadsheet_id = self.spreadsheet_ids[destination_spreadsheet]

        destination_range = destination_sheet + '!A:' + string.ascii_uppercase[len(columns_to_publish) - 1]

        result = self.service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=destination_range,
            valueInputOption=value_input_option, body=body).execute()

        cells_updated = result.get('updatedCells')
        print(f'{cells_updated} cells updated in Google Sheet: {destination_spreadsheet}, sheet: {destination_sheet}')



    def build_map_display_box(self, cp):
        """
        Build a string containing names of the commissioner and commissioner-elect. 
        This entire string will be displayed in the map display box on the lower right of all maps

        todo: make this function more like a usual pandas function, with an 'apply' perhaps

        todo: make this more sensible. difficult to handle for future districts that don't have a current
        commissioner but do have a commissioner-elect
        """

        for idx, row in cp.iterrows():

            # smd_id = row['smd_id']

            map_display_box = (
                f'<b><a href="{generate_url(row.smd_id)}">District {row.smd_name}</a></b>'
                )

            # todo 2024: enable for active candidates
            if '_2022_' in row.smd_id:
                map_display_box += f'<br/>Candidates: {row.list_of_candidate_links}'

            # todo: what labels should be put on old map, if any?
            # If a current commissioner exists in the district, append the Commissioner string
            if pd.notnull(row.current_commissioner):
                map_display_box += f'<br/>Commissioner: {row.current_commissioner}'

            # If a commissioner with a future start_date exists for the SMD, append the Commissioner-Elect string
            if pd.notnull(row.commissioner_elect):
                map_display_box += f'<br/>Commissioner-Elect: {row.commissioner_elect}'
            # else:
            #     map_display_box += f'<br/>Commissioner-Elect: (vacant)'

            cp.loc[idx, 'map_display_box'] = map_display_box

        """
        Mapbox Styles, in order to display the "contested" map, needs the number_of_candidates to be 2,
        even if the actual number is higher. It's the only way I could figure out how to do it
        """
        cp.loc[cp.number_of_candidates >= 2, 'number_of_candidates'] = 2

        return cp[['smd_id', 'smd_name', 'map_color_id', 'number_of_candidates', 'map_display_box']]



    def add_data_to_geojson(self, source_geojson, destination_filename):
        """
        Save new GeoJSON files with updated information in map_display_df (commissioner and candidate names)
        # todo: push these tilesets to Mapbox via API
        """

        smd = gpd.read_file(source_geojson)
        smd = smd[['smd_id', 'geometry']].copy()

        smd_df = smd.merge(self.map_display_df, on='smd_id')

        smd_df.to_file(destination_filename, driver='GeoJSON')

        print(f'GeoJSON file saved: {destination_filename}')



    def add_data_to_label_points(self, source_csv, destination_filename):
        """Add data to CSV with lat/long of SMD label points"""

        lp = pd.read_csv(source_csv)

        lp_df = pd.merge(lp, self.map_display_df, how='inner', on='smd_id')
        
        lp_gdf = gpd.GeoDataFrame(lp_df, geometry=gpd.points_from_xy(lp_df.lon, lp_df.lat))
        lp_gdf.to_file(destination_filename, driver='GeoJSON')



    def publish_candidate_list(self):
        """
        Publish list of candidates to OpenANC Published
        """

        district_info_comm = districts_candidates_commissioners(link_source='absolute', redistricting_year=2022)

        district_info_comm['openanc_link'] = district_info_comm['smd_id'].apply(lambda x: generate_url(x, link_source='absolute'))

        columns_to_publish = ['smd_id', 'number_of_candidates', 'list_of_candidate_names', 'openanc_link']

        self.upload_to_google_sheets(district_info_comm, columns_to_publish, 'openanc_published', 'SMD Candidates 2022')



    def publish_commissioner_list(self):
        """
        Publish list of commissioners to OpenANC Published

        Based off of the notebook, Twitter_Accounts_of_Commissioners.ipynb
        """

        # Commissioners currently active
        commissioners = list_commissioners(status='current')
        people = people_dataframe()
        districts = pd.read_csv('data/districts.csv')

        if len(commissioners) == 0:
            print('There are no current commissioners in the database to publish to Google Sheets.')
            return

        # Only use the current districts for the list of active commissioners
        districts = districts[districts.redistricting_year == config.current_redistricting_year].copy()

        dc = pd.merge(districts, commissioners, how='left', on='smd_id')
        dcp = pd.merge(dc, people, how='left', on='person_id')

        dcp['start'] = dcp['start_date'].dt.strftime('%Y-%m-%d')
        dcp['end'] = dcp['end_date'].dt.strftime('%Y-%m-%d')

        twttr = dcp.sort_values(by='smd_id')

        if len(twttr) != 345:
            raise ValueError('The number of districts to publish to Google Sheets is not correct.')

        twttr['openanc_link'] = twttr['smd_id'].apply(lambda x: generate_url(x, link_source='absolute'))

        twttr['commissioner_name'] = twttr['full_name']
        columns_to_publish = [
            'smd_id'
            , 'smd_name'
            , 'person_id'
            , 'commissioner_name'
            , 'start'
            , 'end'
            , 'twitter_link'
            , 'mastodon_link'
            , 'facebook_link'
            , 'website_link'
            , 'openanc_link'
        ]

        self.upload_to_google_sheets(twttr, columns_to_publish, 'openanc_published', 'Commissioners')



    def publish_anc_list(self):
        """
        Publish list of ANCs to OpenANC Published
        """

        ancs = pd.read_csv('data/ancs.csv')
        ancs = ancs[ancs.redistricting_year == config.current_redistricting_year].copy()

        ancs['openanc_link'] = ancs['anc_id'].apply(lambda x: generate_url(x, link_source='absolute'))

        columns_to_publish = [
            'anc_id'
            , 'anc_name'
            # , 'neighborhoods'
            , 'openanc_link'
            , 'dc_oanc_link'
            , 'anc_homepage_link'
            , 'twitter_link'
            , 'notes'
            ]

        self.upload_to_google_sheets(ancs, columns_to_publish, 'openanc_published', 'ANCs')



    def publish_results(self):
        """
        Publish results from 2020 elections to OpenANC Published

        todo: make this work with new write-in winners table
        """

        people = people_dataframe()
        candidates = list_candidates(election_year=2020)
        results = pd.read_csv('data/results.csv')
        write_in_winners = pd.read_csv('data/write_in_winners.csv')

        cp = pd.merge(
            candidates[['candidate_id', 'person_id', 'smd_id', 'candidate_status']]
            , people[['person_id', 'full_name']]
            , how='inner'
            , on='person_id'
            )

        # Determine who were incumbent candidates at the time of the election
        election_date = datetime(2020, 11, 3, tzinfo=pytz.timezone(config.site_timezone))
        commissioners = list_commissioners(status=None)
        incumbents = commissioners[(commissioners.start_date < election_date) & (election_date < commissioners.end_date)]
        incumbent_candidates = pd.merge(incumbents, candidates, how='inner', on='person_id')
        incumbent_candidates['is_incumbent'] = True

        cpi = pd.merge(cp, incumbent_candidates[['candidate_id', 'is_incumbent']], how='left', on='candidate_id')
        cpi['is_incumbent'] = cpi['is_incumbent'].fillna(False)


        results['is_on_ballot_winner'] = results['winner']
        cpr = pd.merge(
            cpi[['candidate_id', 'person_id', 'full_name', 'smd_id', 'candidate_status', 'is_incumbent']]
            , results[['candidate_id', 'votes', 'is_on_ballot_winner']]
            , how='left'
            , on='candidate_id'
            )

        write_in_winners['is_write_in_winner'] = True
        cpr_ww = pd.merge(
            cpr
            , write_in_winners[['candidate_id', 'is_write_in_winner']]
            , how='left'
            , on='candidate_id'
            )

        write_in_results = results.loc[
            results['name_from_results'] == 'Write-in'
            , ['smd_id', 'votes']
            ].copy()

        write_in_results['full_name'] = 'Write-ins combined'
        write_in_results['person_id'] = None
        write_in_results['candidate_id'] = None
        write_in_results['candidate_status'] = None
        write_in_results['is_write_in_winner'] = None
        write_in_results['is_on_ballot_winner'] = None
        write_in_results['is_incumbent'] = None

        # Do a UNION ALL
        columns_to_concat = [
            'candidate_id'
            , 'person_id'
            , 'smd_id'
            , 'full_name'
            , 'candidate_status'
            , 'is_incumbent'
            , 'votes'
            , 'is_write_in_winner'
            , 'is_on_ballot_winner'
            ]

        cpr_ww_wr = pd.concat([
            cpr_ww[columns_to_concat]
            , write_in_results[columns_to_concat]
            ])

        cpr_ww_wr['is_winner'] = cpr_ww_wr[['is_write_in_winner', 'is_on_ballot_winner']].any(axis=1)
        print(f'Winners: {cpr_ww_wr.is_winner.sum()}')

        cpr_ww_wr = cpr_ww_wr.sort_values(by=['smd_id', 'person_id'])
        print(f'Total votes: {cpr_ww_wr.votes.sum():,.0f}')

        self.upload_to_google_sheets(cpr_ww_wr, list(cpr_ww_wr.columns), 'openanc_published', 'Results 2020')



    def refresh_csv(self, csv_name, sheet_range, filter_dict=None):
        """
        Pull down one sheet to CSV
        """

        sheet = self.service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=self.spreadsheet_ids['openanc_source']
            , range=f'{csv_name}!{sheet_range}'
            ).execute()

        values = result.get('values', [])

        if not values:
            print('No data found.')

        else:
            df = pd.DataFrame(values[1:], columns=values[0])

            # Sort by the first field
            first_field = df.columns[0]
            df.sort_values(by=first_field, inplace=True)

            # filter rows out of CSV
            if filter_dict:
                for column_name in filter_dict:
                    df = df[df[column_name] == filter_dict[column_name]]

            destination_path = f'data/{csv_name}.csv'
            df.to_csv(destination_path, index=False)
            print(f'Data written to: {destination_path}')



    def confirm_column_notnull_candidates(self):
        """Throw an error if a column has NULLs in it, if those NULLs are not supposed to be there"""

        df = pd.read_csv('data/candidates.csv')
        df = df[df.election_year == config.current_election_year].copy()
        col = 'updated_at'
        table = 'candidates'

        null_count = df[col].isnull().sum()

        if null_count > 0:
            raise ValueError(f'The column "{col}" has at least one NULL value in table "{table}"')



    def confirm_commissioner_date_validity(self):
        """Confirm that end dates are after start dates for every commissioner record."""

        commissioners = pd.read_csv('data/commissioners.csv')

        invalid_dates = commissioners.start_date > commissioners.end_date
        
        if any(invalid_dates):
            print('\nDates to correct:')
            print(commissioners.loc[invalid_dates])
            raise ValueError('Commissioners table has a end date before a start date.')



    def confirm_one_person_per_candidate_election_year(self):
        """Each person should only be in the candidates table once in an election year."""

        candidates = pd.read_csv('data/candidates.csv')
        person_election_year = candidates.groupby(['election_year', 'person_id', 'candidate_name']).size()

        if any(person_election_year > 1):
            print(person_election_year[person_election_year > 1])
            raise ValueError('This person is in the Candidates table more than once in the same election year.')



    def generate_external_id_lookup_table(self):
        """
        Take the external_id_list field on the people table, a comma-separated list of external IDs,
        and split them into a table with one row per external_id

        todo: no longer needed, delete this
        """

        people = pd.read_csv('data/people.csv')

        people['external_id_list_split'] = people.external_id_list.str.split(', ')

        external_id_list_split = []

        for idx, row in people[people.external_id_list.notnull()].iterrows():            
            for eid in row.external_id_list_split:
                external_id_list_split += [[eid, row.person_id, row.full_name]]

        external_id_lookup = pd.DataFrame(external_id_list_split,columns=['external_id', 'person_id', 'full_name'])

        external_id_lookup.to_csv('data/temp/external_id_person_id_lookup.csv', index=False)

        print('Table generated: external_id_person_id_lookup.csv')



    def add_name_id_to_people_csv(self):
        """Calculate the name slug once for the people CSV and save it"""

        people = pd.read_csv('data/people.csv')
        people['person_name_id'] = 'person_' + people.full_name.apply(lambda x: format_name_for_url(x))
        people.to_csv('data/people.csv', index=False)



    def check_database_for_new_external_ids(self):
        """Cycle through each data file that contains external_ids to make sure they have all been matched."""

        tables_with_external_ids = [
            'data/dcboe/candidate_votes.csv'
            , 'data/dcboe/write_in_winners.csv'
            # , 'data/candidates.csv'
            ]

        self.lookup = pd.read_csv('data/external_id_lookup.csv')

        for table_file in tables_with_external_ids:
            self.check_table_for_new_external_ids(table_file, 'candidate_name')



    def check_table_for_new_external_ids(self, table_file, name_column):

        # todo: make this work for multiple source files of external_ids

        external_id_df = pd.read_csv(table_file)
        external_id_df = external_id_df[external_id_df.external_id.notnull()].copy()

        new_external_ids = external_id_df[~external_id_df.external_id.isin(self.lookup.external_id)]

        if len(new_external_ids) == 0:
            print(f'All external_ids have been accounted for in table {table_file}')
            return

        if not self.match_file.exists():
            print(f'Running matching process for table: {table_file}')
            self.run_matching_process(new_external_ids, name_column)

        matches = pd.read_csv(self.match_file)

        if any(matches.good_match.isin(['?'])):
            raise SystemExit(f'Evaluate the "?" matches in "{self.match_file.name}" before continuing')


        good_matches = matches[matches.good_match == 1].copy()
        people_create = matches[matches.good_match == 0].copy()

        # todo: second round of matching that returns the top 5 people matches
        # todo 2024: consolidate this code with the similar code in process_candidates.py

        if len(good_matches) > 0:
            good_matches[['external_id', 'match_person_id', 'match_full_name']].to_csv('data/add_to_external_id_lookup.csv', index=False)
            print('Good matches saved to: data/add_to_external_id_lookup.csv')

        if len(people_create) > 0:
            people = pd.read_csv('data/people.csv')
            max_id_person = people['person_id'].max()

            people_create['full_name'] = people_create[name_column].str.title()
            people_create['person_id_suggested'] = 1 + max_id_person + np.arange(0, len(people_create))

            people_create[['person_id_suggested', 'full_name']].to_csv('data/add_to_people.csv', index=False)
            print('People to create saved to: data/add_to_people.csv')

        if len(good_matches) > 0 or len(people_create) > 0:
            raise SystemExit('Add data to source spreadsheet before continuing.')



    def run_matching_process(self, new_external_ids, name_column):

        match_df = match_to_openanc(new_external_ids, name_column)
        match_df['good_match'] = '?'

        columns_to_csv = [
            'external_id'
            , 'match_score'
            , 'smd_id'
            , 'match_smd_id'
            , name_column
            , 'match_full_name'
            , 'match_person_id'
            , 'good_match'
        ]

        (
            match_df[columns_to_csv]
            .sort_values(by='match_score', ascending=False)
            .to_csv(self.match_file, index=False)
        )



    def download_google_sheets(self, do_full_refresh):

        self.refresh_csv('people', 'A:F')
        self.refresh_csv('candidates', 'A:X', filter_dict={'publish_candidate': 'TRUE'})
        self.refresh_csv('commissioners', 'A:E')
        # self.refresh_csv('external_id_lookup', 'A:C')

        # Related to election results
        # self.refresh_csv('results', 'A:Q') #, filter_dict={'candidate_matched': 1})
        # self.refresh_csv('write_in_winners', 'A1:G26')
        
        if do_full_refresh:
            # Tables that don't change very frequently and thus don't need to be refreshed every time
            self.refresh_csv('incumbents_not_running', 'A:C')
            self.refresh_csv('districts', 'A:Q')
            self.refresh_csv('ancs', 'A:P')
            self.refresh_csv('wards', 'A:E')

            self.refresh_csv('candidate_statuses', 'A:D')
            self.refresh_csv('field_names', 'A:B')
            self.refresh_csv('mapbox_styles', 'A:C')
            self.refresh_csv('map_colors', 'A:B')
            self.refresh_csv('election_dates', 'A:D')



    def run(self, do_full_refresh=False):

        self.download_google_sheets(do_full_refresh)
        self.add_name_id_to_people_csv()
        # self.generate_external_id_lookup_table()

        self.check_database_for_new_external_ids()
        
        confirm_key_uniqueness('data/people.csv', 'person_id')
        confirm_key_uniqueness('data/candidates.csv', 'candidate_id')
        confirm_key_uniqueness('data/external_id_lookup.csv', 'external_id')
        self.confirm_column_notnull_candidates()
        self.confirm_commissioner_date_validity()
        self.confirm_one_person_per_candidate_election_year()

        dcc = districts_candidates_commissioners(link_source='root')
        self.map_display_df = self.build_map_display_box(cp=dcc)

        self.add_data_to_geojson('maps/smd-2012-preprocessed.geojson', 'uploads/to-mapbox-smd-2012-data.geojson')
        self.add_data_to_geojson('maps/smd-2022-preprocessed.geojson', 'uploads/to-mapbox-smd-2022-data.geojson')
        self.add_data_to_label_points('maps/label-points-2012.csv', 'uploads/to-mapbox-label-points-2012-data.geojson')
        self.add_data_to_label_points('maps/label-points-2022.csv', 'uploads/to-mapbox-label-points-2022-data.geojson')

        # self.publish_candidate_list()
        self.publish_commissioner_list()
        self.publish_anc_list()
        # self.publish_results()


