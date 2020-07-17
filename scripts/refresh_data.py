"""
Pull down fresh data from Google Sheets to CSV
"""

import pickle
import os.path
import pandas as pd
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


class RefreshData():

    def __init__(self):

        # If modifying these scopes, delete the file token.pickle.
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']

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


    def refresh_csv(self, csv_name, sheet_range):
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

            destination_path = f'data/{csv_name}.csv'
            df.to_csv(destination_path, index=False)
            print(f'Data written to: {destination_path}')


    def run(self):

        self.refresh_csv('ancs', 'A:F')
        self.refresh_csv('candidates', 'A:J')
        self.refresh_csv('commissioners', 'A:K')
        self.refresh_csv('districts', 'A:J')
        # self.refresh_csv('map_colors', 'A:B') # Doesn't need to be run every time
        self.refresh_csv('people', 'A:J')
