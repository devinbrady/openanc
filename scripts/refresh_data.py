"""
Pull down fresh data from Google Sheets to CSV
"""

import pickle
import os.path
import pandas as pd
import geopandas as gpd
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


class RefreshData():

    def __init__(self):

        # If modifying these scopes, delete the file token.pickle.
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets']

        # The ID and range of a sample spreadsheet.
        self.source_spreadsheet_id = '1QGki43vKLKJyG65Rd3lSKJwO_B3yX96SCljzmd9YJhk' # OpenANC Source

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


    def assemble_smd_info(self, duplicate_check=False, print_counts=False, publish_to_google_sheets=False):
        """
        Make CSV, one row per district, with candidate names and counts

        Destination is a Mapbox dataset
        """

        districts = pd.read_csv('data/districts.csv')
        candidates = pd.read_csv('data/candidates.csv')
        commissioners = pd.read_csv('data/commissioners.csv')
        people = pd.read_csv('data/people.csv')


        candidate_people = pd.merge(candidates, people, how='inner', on='person_id')
        candidate_people.rename(columns={'full_name': 'full_name_candidate'}, inplace=True)

        commissioner_people = pd.merge(commissioners, people, how='inner', on='person_id')
        commissioner_people.rename(columns={'full_name': 'full_name_commissioner'}, inplace=True)

        district_candidates = pd.merge(districts, candidate_people, how='left', on='smd_id')



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
            print('\nDistricts by number of candidates: ')
            print(district_info_comm.groupby('number_of_candidates').size())
            print()

        if publish_to_google_sheets:

            district_info_comm['openanc_link'] = 'https://openanc.org/ancs/districts/' + district_info_comm['smd_id'].str.replace('smd_', '') + '.html'

            columns_to_publish = ['smd_id', 'current_commissioner', 'number_of_candidates', 'list_of_candidates', 'openanc_link']
            values = [columns_to_publish]
            values += district_info_comm[columns_to_publish].values.tolist()

            body = {'values': values}

            value_input_option = 'RAW'

            result = self.service.spreadsheets().values().update(
                spreadsheetId='1XoT92wFBKdmnUc6AXwABeWNjsjcwrGMPMKu1XsBOygU', range='Single_Member_Districts!A:E',
                valueInputOption=value_input_option, body=body).execute()

            print('{0} cells updated in Google Sheets.'.format(result.get('updatedCells')))

        return district_info_comm


    def add_data_to_geojson(self):
        """
        Save new GeoJSON files with updated data fields
        """

        df = self.assemble_smd_info(duplicate_check=True, print_counts=True, publish_to_google_sheets=True)

        # Add data to GeoJSON file with SMD shapes
        smd = gpd.read_file('maps/smd.geojson')

        # Use the map_color_id field from the Google Sheets over what is stored in the GeoJSON
        smd.drop(columns=['map_color_id'], inplace=True)

        smd_df = smd.merge(df, on='smd_id')
        smd_df.to_file('maps/to_mapbox/smd-data.geojson', driver='GeoJSON')

        # Add data to CSV with lat/long of SMD label points
        lp = pd.read_csv('maps/label-points.csv')
        lp_df = pd.merge(lp, df[['smd_id', 'current_commissioner', 'number_of_candidates', 'list_of_candidates']], how='inner', on='smd_id')
        lp_df.to_csv('maps/to_mapbox/label-points-data.csv', index=False)



    def refresh_csv(self, csv_name, sheet_range, filter_dict=None):
        """
        Pull down one sheet to CSV
        """

        sheet = self.service.spreadsheets()
        result = sheet.values().get(spreadsheetId=self.source_spreadsheet_id, range=f'{csv_name}!{sheet_range}').execute()
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

        self.refresh_csv('ancs', 'A:H')
        self.refresh_csv('candidates', 'A:J')
        self.refresh_csv('commissioners', 'A:H', filter_dict={'commissioner_status': 'current'})
        self.refresh_csv('districts', 'A:K')
        self.refresh_csv('field_names', 'A:B')
        # self.refresh_csv('map_colors', 'A:B') # Doesn't need to be run every time
        self.refresh_csv('people', 'A:G')

        self.add_data_to_geojson()


