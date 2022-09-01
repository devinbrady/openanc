"""
Process list of candidates from the DC Board of Elections

How it should work:
Here is a list of dcboe_hash_id not currently in the OpenANC candidate list
The goal is to get them all in

Does this new dcboe_hash_id closely match an existing person, who is not already a candidate this year?
    Then use that matching person_id
    Else create a new person_id
"""

import os
import sys
import hashlib
import numpy as np
import pandas as pd
from pathlib import Path

from scripts.refresh_data import RefreshData
from scripts.data_transformations import (
    districts_candidates_commissioners
    , most_recent_smd
    )

from scripts.common import (
    match_names
    , hash_dataframe
    , CURRENT_ELECTION_YEAR
    , CURRENT_REDISTRICTING_YEAR
    )

pd.set_option('display.max_colwidth', 180)
pd.set_option('display.max_columns', 100)



class ProcessCandidates():

    def clean_csv(self):
        """
        Process CSV made by Tabula from PDF from the DC Board of Elections

        Result is a CSV of current candidates with dcboe_hash_id
        """

        excel_file_dir = 'data/dcboe/excel-clean/'
        excel_file = self.most_recent_file(excel_file_dir, 'dcboe-')
        dcboe_updated_at = excel_file.replace(excel_file_dir, '').replace('dcboe-', '').replace('a.xlsx', '').replace('b.xlsx', '').replace('c.xlsx', '').replace('d.xlsx', '').replace('e.xlsx', '').replace('.xlsx', '')
        print('Reading Excel file: ' + excel_file)

        df = pd.read_excel(excel_file)
        df['dcboe_updated_at'] = dcboe_updated_at

        df['candidate_source'] = 'DCBOE'
        df['candidate_source_link'] = 'https://dcboe.org/Elections/2022-Elections'

        df.rename(
            columns={
                'ANC/SMD': 'smd'
                , 'ANC-SMD': 'smd'
                , 'Name': 'candidate_name'
                , 'Date of Pick-up': 'pickup_date'
                , 'Date Filed': 'filed_date'
                }, inplace=True
            )

        print('Number of districts in this file: {} (should be 345, ideally)'.format(df.smd.nunique()))

        # drop header rows interspersed in data
        df = df[df['smd'] != 'ANC/SMD'].copy()

        # drop rows with NULL name
        df.dropna(subset=['candidate_name'], inplace=True)

        # trim bad characters from all fields
        for c in ['smd', 'candidate_name']:
            df[c] = df[c].apply(lambda row: row.strip())

        # Title-case the candidate names
        df['candidate_name'] = df['candidate_name'].str.title()

        # Rename the 3/4G districts to match the smd_id pattern
        df['smd_id'] = 'smd_2022_' + df['smd'].str.replace('3G', '3/4G')

        # Assign a candidate status based on the fields from DCBOE
        df['candidate_status'] = '(unknown status)'
        df.loc[df.pickup_date.notnull(), 'candidate_status'] = 'Pulled Papers for Ballot'
        df.loc[df.filed_date.notnull(), 'candidate_status'] = 'Filed Signatures'
        df.loc[df.candidate_name.str.contains('Withdrew'), 'candidate_status'] = 'Withdrew'
        print('\nCount of candidates by status:')
        print(df.groupby('candidate_status').size())

        # Fix bad dates and names
        df.loc[df['candidate_name'] == 'Hasan Rasheedah', 'candidate_name'] = "Rasheedah Hasan"
        # df.loc[df['candidate_name'] == 'Robin Mckinney', 'candidate_name'] = "Robin McKinney"
        # df.loc[df['candidate_name'] == 'Brian J. Mccabe', 'candidate_name'] = "Brian J. McCabe"
        # df.loc[df['candidate_name'] == 'Clyde Darren Thopson', 'candidate_name'] = "Clyde Darren Thompson"

        # Fix data entry errors and convert to dates
        # df.loc[df['pickup_date'] == '6/302020', 'pickup_date'] = '6/30/2020'
        df['pickup_date'] = pd.to_datetime(df['pickup_date']).dt.strftime('%Y-%m-%d')

        # There are some candidate rows that don't have a pickup date, but I think we should assume they have picked up
        df['pickup_date'] = df['pickup_date'].fillna('unknown pickup date')    

        # df.loc[df['filed_date'] == '7F06', 'filed_date'] = None
        df['filed_date'] = pd.to_datetime(df['filed_date']).dt.strftime('%Y-%m-%d')

        # Make sure each district matches the actual list of districts
        districts = pd.read_csv('data/districts.csv')
        valid_smd_ids = sorted(districts[districts.redistricting_year == CURRENT_REDISTRICTING_YEAR].smd_id.unique())
        invalid_smd_ids = [d for d in df.smd_id if d not in valid_smd_ids]

        if invalid_smd_ids:
            print('\nThese candidates in the DCBOE file will be dropped because their smd_id is not valid:')
            print(df[df.smd_id.isin(invalid_smd_ids)][['smd_id', 'candidate_name']])

            df = df[~df.smd_id.isin(invalid_smd_ids)].copy()

        # Create a new ID for this data based off of a hash of the district and candidate name
        df['candidate_name_upper'] = df['candidate_name'].str.upper()
        df['dcboe_hash_id'] = hash_dataframe(df, ['smd_id', 'candidate_name_upper'])

        columns_to_save = [
            'dcboe_hash_id'
            , 'smd_id'
            , 'candidate_name'
            , 'pickup_date'
            , 'filed_date'
            , 'candidate_status'
            ]

        df.sort_values(by='smd_id', inplace=True)
        df[columns_to_save].to_csv('data/dcboe/candidates_dcboe.csv', index=False)

        return df



    def upload_dcboe_to_google_sheets(self, df):

        rd = RefreshData()

        columns_to_save_to_google = [
            'dcboe_hash_id'
            , 'smd_id'
            , 'candidate_name'
            , 'pickup_date'
            , 'filed_date'
            , 'candidate_source'
            , 'candidate_source_link'
            , 'dcboe_updated_at'
            , 'candidate_status'
            ]

        print()
        rd.upload_to_google_sheets(df, columns_to_save_to_google, 'openanc_source', 'dcboe')



    def most_recent_file(self, directory_name, filename_pattern):
        """
        Returns the most recent file in a directory. 
        The filenames must have a timestamp in them. It's the max of the sorted text.

        directory_name: the directory to search in. Include the slash at the end
        filename_pattern: the text in the filename to narrow the results by
        """

        list_of_files = sorted(
            [f for f in os.listdir(directory_name) if (filename_pattern in f and '~' not in f)]
            )
        mrf = directory_name + list_of_files[-1]

        return mrf



    def run_matching_process(self):
        """
        For candidates not yet in the OpenANC system, prepare a spreadsheet for manual evaluation of matches against
        the OpenANC people list.
        """

        people = pd.read_csv('data/people.csv')
        people = most_recent_smd(people)
        candidates = pd.read_csv('data/candidates.csv')
        candidates_dcboe = pd.read_csv('data/dcboe/candidates_dcboe.csv')

        # Exclude the hash_ids that are currently in the OpenANC candidates table
        candidates_to_match = candidates_dcboe[ ~(candidates_dcboe['dcboe_hash_id'].isin(candidates['dcboe_hash_id'])) ].copy()

        candidates_to_match['match_person_id'] = pd.NA
        candidates_to_match['match_person_id'] = candidates_to_match['match_person_id'].astype('Int64')
        candidates_to_match['match_score'] = pd.NA
        candidates_to_match['match_person_id'] = pd.NA
        candidates_to_match['match_person_full_name'] = pd.NA
        candidates_to_match['match_person_smd_id'] = pd.NA

        # Look for the OpenANC person that has the highest match score against each new candidate

        for idx, row in candidates_to_match.iterrows():

            # In most years, we should match only to people with the same smd_id
            # current_comm = people[people['most_recent_smd_id'] == row['smd_id']].copy()

            # In the redistricting year, a lot of people are changing districts, so match to all people
            current_comm = people.copy()

            if len(current_comm) == 0:
                continue

            best_id, best_score = match_names(row['candidate_name'], current_comm['full_name'], current_comm['person_id'])

            # if best_score >= 80:

            candidates_to_match.loc[idx, 'match_score'] = best_score
            candidates_to_match.loc[idx, 'match_person_id'] = best_id
            candidates_to_match.loc[idx, 'match_person_full_name'] = people[people.person_id == best_id].full_name.iloc[0]
            candidates_to_match.loc[idx, 'match_person_smd_id'] = people[people.person_id == best_id].most_recent_smd_id.iloc[0]

        
        candidates_to_match['good_match'] = '?'
        match_columns = [
            'dcboe_hash_id'
            , 'match_score'
            , 'candidate_name'
            , 'match_person_full_name'
            , 'smd_id'
            , 'match_person_smd_id'
            , 'match_person_id'
            , 'good_match'
            ]

        candidates_to_match[match_columns].sort_values(by='match_score', ascending=False).to_csv(
            'data/dcboe/1_candidates_dcboe_match.csv', index=False
            )



    def candidate_counts(self):
        """
        Check existing and new candidate hashes to see where there are mismatches

        When a candidate's name changes, the hash from the new file should be written to the OpenANC Source candidate sheet
        """

        candidates = pd.read_csv('data/candidates.csv')
        candidates = candidates[candidates.election_year == CURRENT_ELECTION_YEAR].copy()
        dcboe = pd.read_csv('data/dcboe/candidates_dcboe.csv')

        print(f'\nValid DCBOE candidates: {len(dcboe)}')

        dcboe_in_openanc = [h for h in dcboe.dcboe_hash_id.tolist() if h in candidates.dcboe_hash_id.tolist()]
        print(f'DCBOE candidate IDs in OpenANC candidate list: {len(dcboe_in_openanc)}')

        dcboe_not_in_openanc = [h for h in dcboe.dcboe_hash_id.tolist() if h not in candidates.dcboe_hash_id.tolist()]
        print(f'DCBOE candidate IDs *not* in OpenANC candidate list: {len(dcboe_not_in_openanc)} (will be zero once this update is complete)')    

        openanc_candidates_not_in_dcboe_file = ~( candidates['dcboe_hash_id'].isin(dcboe['dcboe_hash_id']) )
        print(f'OpenANC candidates not in current DCBOE candidate list: {openanc_candidates_not_in_dcboe_file.sum()}')

        return dcboe_not_in_openanc, openanc_candidates_not_in_dcboe_file



    def list_candidates_to_add(self):
        """
        List candidates that need to be added to the OpenANC candidate table
        """

        candidates = pd.read_csv('data/candidates.csv')
        max_id_candidate = candidates['candidate_id'].max()

        people = pd.read_csv('data/people.csv')
        max_id_person = people['person_id'].max()

        candidates_this_year = candidates[candidates.election_year == CURRENT_ELECTION_YEAR].copy()
        dcboe = pd.read_csv('data/dcboe/candidates_dcboe.csv')

        match_file = Path('data/dcboe/1_candidates_dcboe_match.csv')

        if not match_file.exists():
            self.run_matching_process()

        matches = pd.read_csv(match_file)

        if any(matches.good_match.isin(['?'])):
            print(f'Evaluate the matches in "1_candidates_dcboe_match.csv" before continuing')
            return

        good_matches = matches[matches.good_match == 1].copy()
        people_create = matches[matches.good_match == 0].copy()


        mc = pd.merge(good_matches, candidates_this_year[['candidate_id', 'person_id']], how='left', left_on='match_person_id', right_on='person_id')

        # Candidates who need a hash ID change
        candidates_change_hash_id = mc[mc.candidate_id.notnull()].copy()
        print(f'\nExisting candidates need the dcboe_hash_id changed ({len(candidates_change_hash_id)} people): 2a_candidates_change_hash_id.csv')
        change_hash_columns = ['candidate_id', 'person_id', 'dcboe_hash_id', 'smd_id', 'candidate_name']
        candidates_change_hash_id[change_hash_columns].sort_values(by='candidate_id').to_csv('data/dcboe/2a_candidates_change_hash_id.csv', index=False)

        # Candidates who are existing people
        candidates_create = mc[mc.candidate_id.isnull()].copy()
        print(f'\nExisting people need to be added to the candidates table ({len(candidates_create)} people): 2b_candidates_create.csv')
        candidates_create = candidates_create.sort_values(by='match_person_id')

        candidates_create['candidate_id_suggested'] = None
        for idx, row in candidates_create.iterrows():
            candidates_create.loc[idx, 'candidate_id_suggested'] = max_id_candidate + 1
            max_id_candidate += 1

        candidates_create_columns = ['candidate_id_suggested', 'match_person_id', 'dcboe_hash_id', 'smd_id', 'candidate_name']
        candidates_create[candidates_create_columns].to_csv('data/dcboe/2b_candidates_create.csv', index=False)

        print(f'\nNew people need to be created ({len(people_create)} people): 2c_people_create.csv')

        people_create = people_create.sort_values(by='smd_id')

        people_create['candidate_id_suggested'] = None
        people_create['person_id_suggested'] = None
        for idx, row in people_create.iterrows():
            people_create.loc[idx, 'candidate_id_suggested'] = max_id_candidate + 1
            max_id_candidate += 1

            people_create.loc[idx, 'person_id_suggested'] = max_id_person + 1
            max_id_person += 1

        people_create_columns = [
            'candidate_id_suggested'
            , 'person_id_suggested'
            , 'dcboe_hash_id'
            , 'smd_id'
            , 'candidate_name'
        ]
        
        people_create[people_create_columns].to_csv('data/dcboe/2c_people_create.csv', index=False)                

        openanc_not_in_dcboe = [h for h in candidates_this_year[candidates_this_year.dcboe_hash_id.notnull()].dcboe_hash_id.tolist() if h not in dcboe.dcboe_hash_id.tolist()]
        print(f'\nCandidates hash_ids in OpenANC that are no longer in the DCBOE list (should be zero): {len(openanc_not_in_dcboe)}')
        
        if openanc_not_in_dcboe:
            print('\nThese candidates have a hash_id in the OpenANC candidates list but are no longer on the DCBOE list:')

            print('(a lot of them, because candidates who did not submit signatures were taken out of the candidate list)\n')
            # print(candidates_this_year[candidates_this_year.dcboe_hash_id.isin(openanc_not_in_dcboe)][['dcboe_hash_id', 'smd_id', 'candidate_name']])



    def run(self):

        df = self.clean_csv()

        dcboe_not_in_openanc, openanc_candidates_not_in_dcboe_file = self.candidate_counts()

        if len(dcboe_not_in_openanc) == 0:
            print('\nAll DCBOE candidates are in OpenANC. Update complete!')
            return

        self.upload_dcboe_to_google_sheets(df)

        self.list_candidates_to_add()


        
