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
    , CURRENT_ELECTION_YEAR
    , CURRENT_REDISTRICTING_YEAR
    )

pd.set_option('display.max_colwidth', 180)
pd.set_option('display.max_columns', 100)



class ProcessCandidates():

    def __init__(self):
        pass



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

        print('Number of districts in this file: {}'.format(df.smd.nunique()))

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
        df['dcboe_hash_id'] = self.hash_dataframe(df, ['smd_id', 'candidate_name_upper'])

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



    def remove_withdrew_candidates(self, df):
        """
        Remove withdrew candidates from the DCBOE dataframe
        """

        # List of names as they appear in the current DCBOE sheet
        # todo: maybe just search for "withdrew" in name
        # list_of_withdrew_names = [
        #     'Andrew Spencer DeFrank'
        #     , 'Randy D Downs (Withdrew 7/24/20)'
        #     , 'Pete Stamper (Withdrew 7/27/2020)'
        #     , 'Alexandra Morgan (Withdrew 7/30/20)'
        #     , 'Rebecca Maydak (Withdrew 7/30/20)'
        #     , 'Jonathan Alfuth (withdrew 8/4/20)'
        #     , 'Carol E. Fletcher (withdrew 8/4/20)'
        # ]


        list_of_withdrew_names = ['Andrew Spencer DeFrank'] + df[df['candidate_name'].str.contains('withdrew', case=False)]['candidate_name'].tolist()

        print('Withdrawn candidates:')
        for c in list_of_withdrew_names:
            print('    ' + c)

        # print('List of withdrew candidates match DCBOE candidate names: {}'.format(
        #     len(df[df['candidate_name'].isin(list_of_withdrew_names)]) == len(list_of_withdrew_names)
        #     ))

        return df[ ~(df['candidate_name'].isin(list_of_withdrew_names)) ].copy()    



    def hash_dataframe(self, df, columns_to_hash):
        """
        Given a DataFrame, hash certain columns

        df = pandas DataFrame
        columns_to_hash = a list containing the column names that should be hashed
        """

        hash_of_data = []

        for idx, row in df.iterrows():
            list_to_hash = row[columns_to_hash]
            string_to_hash = ','.join(list_to_hash)
            hash_of_data += [hashlib.sha224(string_to_hash.encode()).hexdigest()]
        
        return hash_of_data



    def run_matching_process(self):
        """
        For candidates not yet in the OpenANC system, check them against OpenANC people to see
        if there are any obvious matches.
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


        """
        If the candidate name has a high match score to the name of the current 
        officeholder for that SMD, consider that a match
        """

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



    def prep_new_records(self):

        # prepare records for adding to Google Sheets
        add_records_to_people = pd.DataFrame(columns=['person_id', 'full_name'])
        add_records_to_candidates = pd.DataFrame(columns=['candidate_id', 'person_id', 'dcboe_hash_id', 'smd_id', 'candidate_name'])

        max_id_person = people['person_id'].max()
        if pd.isnull(max_id_person):
            max_id_person = 10000
        
        max_id_candidate = candidates['candidate_id'].max()
        if pd.isnull(max_id_candidate):
            max_id_candidate = 50000

        for idx, row in candidates_to_match.iterrows():

            # new person
            if pd.isnull(row['person_id']):

                # add to person
                new_person_id = 1 + max_id_person
                max_id_person = new_person_id

                new_person = pd.DataFrame({
                    'person_id': new_person_id
                    , 'full_name': row['candidate_name']
                    , 'dcboe_hash_id': row['dcboe_hash_id']
                    , 'smd_id': row['smd_id']
                    }, index=[1 + add_records_to_people.index.max()])
                
                add_records_to_people = add_records_to_people.append(new_person)


                # add to candidates
                new_candidate_id = 1 + max_id_candidate
                max_id_candidate = new_candidate_id

                new_candidate = pd.DataFrame({
                    'candidate_id': new_candidate_id
                    , 'person_id': new_person_id
                    , 'dcboe_hash_id': row['dcboe_hash_id']
                    , 'smd_id': row['smd_id']
                    , 'candidate_name': row['candidate_name']
                    }, index=[1 + add_records_to_candidates.index.max()])

                add_records_to_candidates = add_records_to_candidates.append(new_candidate)


            # existing person, new candidate
            elif row['person_id'] not in candidates['person_id'].tolist():

                new_candidate_id = 1 + max_id_candidate
                max_id_candidate = new_candidate_id

                new_candidate = pd.DataFrame({
                    'candidate_id': new_candidate_id
                    , 'person_id': row['person_id']
                    , 'dcboe_hash_id': row['dcboe_hash_id']
                    , 'smd_id': row['smd_id']
                    , 'candidate_name': row['candidate_name']
                    }, index=[1 + add_records_to_candidates.index.max()])

                add_records_to_candidates = add_records_to_candidates.append(new_candidate)


        add_records_to_people.reset_index(inplace=True)
        add_records_to_people.drop(columns=['index'], inplace=True)
        add_records_to_people.to_csv('uploads/to-google-sheets-people.csv', index=False)
        print('Number of new people: {}'.format(len(add_records_to_people)))

        add_records_to_candidates.reset_index(inplace=True)
        add_records_to_candidates.drop(columns=['index'], inplace=True)
        add_records_to_candidates.to_csv('uploads/to-google-sheets-candidates.csv', index=False)
        print('Number of new candidates: {}'.format(len(add_records_to_candidates)))



    def check_new_candidates_for_duplicates_against_candidates(self):
        """
        Look at the most recent records and confirm they don't duplicate any records in the same district
        """

        new_candidates = pd.read_csv('uploads/to-google-sheets-candidates.csv')

        if len(new_candidates) == 0:
            return

        # rd = RefreshData()
        smd_df = districts_candidates_commissioners()

        comparison = pd.merge(new_candidates, smd_df, how='inner', on='smd_id')

        if (comparison['list_of_candidate_names'] != '(no known candidates)').sum() > 0:
            print('Make sure that none of the new candidates duplicate existing candidates. Paste the dcboe_hash_id into the candidates table:')
            print(comparison.loc[comparison['list_of_candidate_names'] != '(no known candidates)', ['smd_id', 'candidate_name', 'dcboe_hash_id', 'list_of_candidate_names']])



    def check_new_candidates_for_duplicates_against_people(self):
        """
        Look at the most recent records and confirm they don't duplicate any existing people
        """

        new_candidates = pd.read_csv('uploads/to-google-sheets-candidates.csv')
        people = pd.read_csv('data/people.csv')

        df = pd.merge(new_candidates[['candidate_name', 'smd_id', 'dcboe_hash_id']], people, how='inner', left_on='candidate_name', right_on='full_name')

        if len(df) > 0:
            print('\nPossible matches to existing people, add these hashes directly to candidates table and delete any manual info if it is there:')
            print(df[['person_id', 'dcboe_hash_id', 'smd_id', 'candidate_name']].head())



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
        print(f'DCBOE candidate IDs *not* in OpenANC candidate list (should be zero once this update is complete): {len(dcboe_not_in_openanc)}')    

        openanc_candidates_not_in_dcboe_file = ~( candidates['dcboe_hash_id'].isin(dcboe['dcboe_hash_id']) )
        print(f'\nOpenANC candidates not in current DCBOE candidate list (this should go to zero as candidates file): {openanc_candidates_not_in_dcboe_file.sum()}')



    def something_else(self):
        new_hashes = ~( dcboe['dcboe_hash_id'].isin(candidates['dcboe_hash_id']) )

        pd.set_option('display.max_colwidth', 60)
        
        # print(candidates.loc[existing_hashes_not_in_new_file, ['dcboe_hash_id', 'smd_id', 'candidate_name', 'candidate_status']])
        candidates.loc[existing_hashes_not_in_new_file].to_csv('data/dcboe/existing_hashes_not_in_new_file.csv', index=False)
        
        if sum(new_hashes) > 0:
            print('\nNew hashes not in OpenANC candidates table (add them, delete manual status): {}'.format(sum(new_hashes)))
            print(dcboe.loc[new_hashes, ['dcboe_hash_id', 'smd_id', 'candidate_name']].head(5))
            print()



    def read_match_file(self):
        pass



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

        # todo: change this logic so the file doesn't have to be deleted every time
        if match_file.exists():
            matches = pd.read_csv(match_file)

            if any(matches.good_match.isin(['?'])):
                print(f'Evaluate the matches in "1_candidates_dcboe_match.csv" before continuing')
                return
        else:
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

        # todo: suggest person_id and candidate_id here
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

        self.upload_dcboe_to_google_sheets(df)

        self.candidate_counts()

        self.list_candidates_to_add()

        # check_new_candidates_for_duplicates_against_candidates()
        # check_new_candidates_for_duplicates_against_people()

        
