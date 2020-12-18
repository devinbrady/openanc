"""
Pull down fresh data from Google Sheets to CSV
"""

import pytz
import pickle
import string
import os.path
import pandas as pd
import geopandas as gpd
from datetime import datetime
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from scripts.common import (
    list_commissioners
    , assemble_divo
    , build_district_comm_commelect
    )



class RefreshData():

    def __init__(self):

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



    def test_google_connection(self):
        """
        Write some data to the OpenANC Published sheet to confirm that Google connection works
        """

        df = pd.DataFrame({'a': [1,2], 'b': [3,4]})

        tz = pytz.timezone('America/New_York')
        dc_now = datetime.now(tz)
        dc_timestamp = dc_now.strftime('%Y-%m-%d %H:%M:%S') # Hour of day: %-I:%M %p

        df['updated_at'] = dc_timestamp

        self.upload_to_google_sheets(df, list(df.columns), 'openanc_published', 'ConnectionTest')

        print('Successfully wrote data to Google Sheets.')



    def upload_to_google_sheets(self, df, columns_to_publish, destination_spreadsheet, destination_sheet):
        """
        Push values to a Google Sheet

        Note that dates are not JSON serializable, so dates have to be converted to strings
        """

        for c in columns_to_publish:
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



    def assemble_smd_info(self, duplicate_check=False, print_counts=False, publish_to_google_sheets=False):
        """
        Return DataFrame, one row per district, with candidate names and counts

        Destination is a Mapbox dataset
        """

        districts = pd.read_csv('data/districts.csv')
        candidates = pd.read_csv('data/candidates.csv')
        commissioners = list_commissioners(status='current')
        people = pd.read_csv('data/people.csv')
        candidate_statuses = pd.read_csv('data/candidate_statuses.csv')


        candidate_people = pd.merge(candidates, people, how='inner', on='person_id')
        candidate_people.rename(columns={'full_name': 'full_name_candidate'}, inplace=True)
        cps = pd.merge(candidate_people, candidate_statuses, how='inner', on='candidate_status')

        commissioner_people = pd.merge(commissioners, people, how='inner', on='person_id')
        commissioner_people.rename(columns={'full_name': 'full_name_commissioner'}, inplace=True)

        # Only include active candidates
        district_candidates = pd.merge(districts, cps[cps['count_as_candidate']].copy(), how='left', on='smd_id')


        # todo: make this candidate order also randomized
        district_info = district_candidates.groupby(['smd_id', 'map_color_id']).agg({
            'full_name_candidate': list
            , 'candidate_id': 'count'
            }).reset_index()


        district_info_comm = pd.merge(district_info, commissioner_people[['smd_id', 'full_name_commissioner']], how='left', on='smd_id')


        district_info_comm.rename(columns={
            'full_name_commissioner': 'current_commissioner'
            , 'full_name_candidate': 'list_of_candidates'
            , 'candidate_id': 'number_of_candidates'
            }, inplace=True)


        district_info_comm['current_commissioner'] = district_info_comm['current_commissioner'].fillna('(vacant)')

        district_info_comm.loc[district_info_comm['number_of_candidates'] == 0, 'list_of_candidates'] = (
            district_info_comm.loc[district_info_comm['number_of_candidates'] == 0, 'list_of_candidates'].apply(
                lambda x: ['(no known candidates)'])
            )

        district_info_comm['list_of_candidates'] = district_info_comm['list_of_candidates'].apply(', '.join)

        # Maybe add Last Updated to this? 

        if duplicate_check:
            district_info_comm[district_info_comm['number_of_candidates'] > 1][['smd_id', 'current_commissioner', 'list_of_candidates']].to_csv('data/check_for_duplicates.csv', index=False)

        if print_counts:
            print('Candidate Count: {}'.format( cps['count_as_candidate'].sum()))

            print('\nDistricts by number of candidates: ')
            print(district_info_comm.groupby('number_of_candidates').size())
            print()

        if publish_to_google_sheets:

            if len(district_info_comm) != 296:
                raise ValueError('The number of districts to publish to Google Sheets is not correct.')

            district_info_comm['openanc_link'] = 'https://openanc.org/ancs/districts/' + district_info_comm['smd_id'].str.replace('smd_', '').str.lower() + '.html'

            columns_to_publish = ['smd_id', 'current_commissioner', 'number_of_candidates', 'list_of_candidates', 'openanc_link']

            self.upload_to_google_sheets(district_info_comm, columns_to_publish, 'openanc_published', 'SMD Candidates 2020')

        return district_info_comm



    def build_map_display_box(self, cp):
        """
        Build a string containing names of the commissioner and commissioner-elect. 
        This entire string will be displayed in the map display box on the lower right of all maps
        """

        for idx, row in cp.iterrows():

            smd_id = row['smd_id']
            smd_display = smd_id.replace('smd_','')
            smd_display_lower = smd_display.lower()

            map_display_box = (
                f'<b>District {smd_display}</b>'
                + f'<br/><a href="ancs/districts/{smd_display_lower}.html">District Page</a>'
                + f'<br/>Commissioner: {row.current_commissioner}'
                )

            # If a commissioner with a future start_date exists for the SMD, append the Commissioner-Elect string
            if pd.notnull(row.commissioner_elect):
                map_display_box += f'<br/>Commissioner-Elect: {row.commissioner_elect}'

            cp.loc[idx, 'map_display_box'] = map_display_box

        return cp



    def add_data_to_geojson(self):
        """
        Save new GeoJSON files with updated data fields based off of the results of the election
        # todo: push these tilesets to Mapbox via API
        """

        district_comm_commelect = build_district_comm_commelect()

        cp_current_future = self.build_map_display_box(district_comm_commelect)

        divo = assemble_divo()

        cp_divo = pd.merge(cp_current_future, divo[['smd_id', 'votes']], how='inner', on='smd_id')
        cp_divo = cp_divo.rename(columns={'votes': 'votes_2020'})

        # Add data to GeoJSON file with SMD shapes
        smd = gpd.read_file('maps/smd.geojson')

        # Use the map_color_id field from the Google Sheets over what is stored in the GeoJSON
        smd.drop(columns=['map_color_id'], inplace=True)

        smd_df = smd.merge(cp_divo, on='smd_id')

        # add ward to the SMD dataframe
        
        smd_df.to_file('uploads/to-mapbox-smd-data.geojson', driver='GeoJSON')

        # Add data to CSV with lat/long of SMD label points
        lp = pd.read_csv('maps/label-points.csv')
        lp_df = pd.merge(lp, cp_divo[['smd_id', 'current_commissioner', 'commissioner_elect', 'votes_2020']], how='inner', on='smd_id')
        lp_df_cp = pd.merge(lp_df, cp_current_future[['smd_id', 'map_display_box']], how='inner', on='smd_id')
        lp_df_cp.to_csv('uploads/to-mapbox-label-points-data.csv', index=False)



    def add_data_to_geojson_candidates(self):
        """
        Save new GeoJSON files with updated data fields
        # todo: push these tilesets to Mapbox via API
        """

        df = self.assemble_smd_info(
            duplicate_check=False
            , print_counts=False
            , publish_to_google_sheets=False
            )

        # Add data to GeoJSON file with SMD shapes
        smd = gpd.read_file('maps/smd.geojson')

        # Use the map_color_id field from the Google Sheets over what is stored in the GeoJSON
        smd.drop(columns=['map_color_id'], inplace=True)

        smd_df = smd.merge(df, on='smd_id')

        # add ward to the SMD dataframe
        districts = pd.read_csv('data/districts.csv')
        smd_df_ward = pd.merge(smd_df, districts[['smd_id', 'ward']], how='inner', on='smd_id')

        smd_df_ward.to_file('uploads/to-mapbox-smd-data.geojson', driver='GeoJSON')

        # Add data to CSV with lat/long of SMD label points
        lp = pd.read_csv('maps/label-points.csv')
        lp_df = pd.merge(lp, df[['smd_id', 'current_commissioner', 'number_of_candidates', 'list_of_candidates']], how='inner', on='smd_id')
        lp_df.to_csv('uploads/to-mapbox-label-points-data.csv', index=False)



    def publish_commissioner_list(self):
        """
        Publish list of commissioners to OpenANC Published

        Based off of the notebook, Twitter_Accounts_of_Commissioners.ipynb
        """

        # Commissioners active in 2021
        # TODO_JAN set this to be active commissioners
        date_point_2021 = datetime(2021, 1, 5, tzinfo=pytz.timezone('America/New_York'))
        commissioners_2021 = list_commissioners(status='current', date_point=date_point_2021)

        people = pd.read_csv('data/people.csv')
        districts = pd.read_csv('data/districts.csv')

        dc = pd.merge(districts, commissioners_2021, how='left', on='smd_id')
        dcp = pd.merge(dc, people, how='left', on='person_id')

        dcp['start'] = dcp['start_date'].dt.strftime('%Y-%m-%d')
        dcp['end'] = dcp['end_date'].dt.strftime('%Y-%m-%d')

        twttr = dcp.sort_values(by='smd_id')

        if len(twttr) != 296:
            raise ValueError('The number of districts to publish to Google Sheets is not correct.')

        twttr['openanc_link'] = 'https://openanc.org/ancs/districts/' + twttr['smd_id'].str.replace('smd_', '').str.lower() + '.html'

        columns_to_publish = ['smd_id', 'person_id', 'full_name', 'start', 'end', 'twitter_link', 'openanc_link']

        self.upload_to_google_sheets(twttr, columns_to_publish, 'openanc_published', 'Commissioners 2021')



    def publish_results(self):
        """
        Publish results from 2020 elections to OpenANC Published
        """

        people = pd.read_csv('data/people.csv')
        candidates = pd.read_csv('data/candidates.csv')
        results = pd.read_csv('data/results.csv')
        write_in_winners = pd.read_csv('data/write_in_winners.csv')

        cp = pd.merge(
            candidates[['candidate_id', 'person_id', 'smd_id', 'candidate_status']]
            , people[['person_id', 'full_name']]
            , how='inner'
            , on='person_id'
            )

        # Determine who were incumbent candidates at the time of the election
        election_date = datetime(2020, 11, 3, tzinfo=pytz.timezone('America/New_York'))
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



    def run(self):

        # self.refresh_csv('candidates', 'A:W', filter_dict={'publish_candidate': 'TRUE'})
        self.refresh_csv('districts', 'A:K')
        # self.refresh_csv('people', 'A:H')
        # self.refresh_csv('results', 'A:P') #, filter_dict={'candidate_matched': 1})
        # self.refresh_csv('write_in_winners', 'A1:G26')
        
        # Tables that don't need to be refreshed every time
        # self.refresh_csv('ancs', 'A:I')
        # self.refresh_csv('candidate_statuses', 'A:D')
        # self.refresh_csv('commissioners', 'A:G')
        # self.refresh_csv('field_names', 'A:B')
        # self.refresh_csv('mapbox_styles', 'A:C')
        # self.refresh_csv('map_colors', 'A:B') 
        # self.refresh_csv('wards', 'A:B')

        # self.add_data_to_geojson()

        # self.publish_commissioner_list()
        # self.publish_results()


