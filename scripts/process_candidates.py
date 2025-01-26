"""
Process list of candidates from the DC Board of Elections

How it should work:
Here is a list of dcboe_hash__id not currently in the OpenANC candidate list
The goal is to get them all in

Does this new dcboe_hash__id closely match an existing person, who is not already a candidate this year?
    Then use that matching person_id
    Else create a new person_id
"""

import os
import sys
import hashlib
import numpy as np
import pandas as pd
from pathlib import Path

import config

from scripts.refresh_data import RefreshData
from scripts.data_transformations import (
    districts_candidates_commissioners
    , most_recent_smd
    , confirm_key_uniqueness
    )

from scripts.common import (
    match_names
    , hash_dataframe
    , validate_smd_ids
    )

pd.set_option('display.max_colwidth', 180)
pd.set_option('display.max_columns', 100)



class ProcessCandidates():

    def __init__(self):

        self.match_file = Path('data/dcboe/1_candidates_dcboe_match.csv')



    def read_dcboe_excel(self, filename_pattern, election_year=config.current_election_year):
        """
        Read in Excel file, whether for Ballot candidates or Write-Ins (specified by filename_pattern), and pre-process it.
        """

        excel_file_dir = 'data/dcboe/excel-clean/'
        excel_file = self.most_recent_file(excel_file_dir, filename_pattern, election_year=election_year)
        if not excel_file:
            return pd.DataFrame()

        characters_to_strip = [
            excel_file_dir
            , 'dcboe-'
            , 'ballot-'
            , 'write-in-'
            , 'a.xlsx'
            , 'b.xlsx'
            , 'c.xlsx'
            , 'd.xlsx'
            , 'e.xlsx'
            , '.xlsx'
            ]

        dcboe_updated_at = excel_file
        for c in characters_to_strip:
            dcboe_updated_at = dcboe_updated_at.replace(c, '')

        print('Reading Excel file: ' + excel_file)

        df = pd.read_excel(excel_file)

        # Take everything before the newline as the candidate name
        df['Name'] = df['Name'].apply(lambda x: x.split('\r')[0] if isinstance(x, str) else x)

        df['dcboe_updated_at'] = dcboe_updated_at

        df['candidate_source'] = 'DCBOE'
        df['candidate_source_link'] = 'https://dcboe.org/elections/2024-elections'

        # Strip out leading and trailing spaces and empty characters from column names
        for c in df.columns:
            df.rename(columns={c: c.strip()}, inplace=True)

        df.rename(
            columns={
                'ANC/SMD': 'smd'
                , 'ANC-SMD': 'smd'
                , 'Office': 'smd'
                , 'Name': 'candidate_name'
                , 'Date of Pick-up': 'pickup_date'
                , 'Date Filed': 'filed_date'
                }, inplace=True
            )

        # BOE has started putting 'O' instead of zeroes in the SMD name for some write-ins. Change back to zero here
        df['smd'] = df['smd'].str.replace('O', '0')

        return df



    def clean_csv(self):
        """
        Process CSV made by Tabula from PDF from the DC Board of Elections

        Result is a CSV of current candidates with external_id

        todo: rename this function
        """

        df_ballot = self.read_dcboe_excel('dcboe-ballot-')
        df_ballot['is_write_in'] = False

        # Remove candidates who DNQFB on ballot list and then filed as write-ins. todo: fix
        df_ballot = df_ballot[~((df_ballot['candidate_name'] == 'Ellen E. Armstead') & (df_ballot['smd'] == '1E05'))].copy()
        df_ballot = df_ballot[~((df_ballot['candidate_name'] == 'Harold Cunningham') & (df_ballot['smd'] == '7F08'))].copy()

        df_write_in = self.read_dcboe_excel('dcboe-write-in-')
        if not df_write_in.empty:
            df_write_in['is_write_in'] = True
            df = pd.concat([df_ballot, df_write_in], ignore_index=True)

        else:
            df = df_ballot.copy()

        # todo: need to handle the case when a candidate is DNQFB on the DCBOE list and also on the write-in list
        # how to resolve the duplicate? within the same election year

        print('Number of districts in this file: {} (should be 345, ideally)'.format(df.smd.nunique()))

        # drop header rows interspersed in data
        df = df[df['smd'] != 'ANC/SMD'].copy()

        # set write-in rows to have a NULL candidate_name
        df.loc[df.candidate_name.str.upper().str.contains('WRITE IN, IF ANY').fillna(False), 'candidate_name'] = None

        # drop rows with NULL name
        df.dropna(subset=['candidate_name'], inplace=True)

        # trim bad characters from all fields
        for c in ['smd', 'candidate_name']:
            df[c] = df[c].apply(lambda row: row.strip())

        # Title-case the candidate names
        df['candidate_name'] = df['candidate_name'].str.title()

        # Rename the 3/4G districts and 6/8F districts to match the smd_id pattern
        df['smd_id'] = (
            'smd_2022_'
            + df['smd']
            .str.replace('3G', '3/4G')
            .str.replace('6/8F', '8F')
            .str.replace('6/8/F', '8F')
            )

        # Fix bad dates and names
        # df.loc[df['candidate_name'] == 'Hasan Rasheedah', 'candidate_name'] = "Rasheedah Hasan"
        # df.loc[df['candidate_name'] == 'Robin Mckinney', 'candidate_name'] = "Robin McKinney"
        # df.loc[df['candidate_name'] == 'Brian J. Mccabe', 'candidate_name'] = "Brian J. McCabe"
        # df.loc[df['candidate_name'] == 'Clyde Darren Thopson', 'candidate_name'] = "Clyde Darren Thompson"
        # df.loc[df['candidate_name'] == 'Taylor Taranto', 'pickup_date'] = "2024-07-30"

        # Fix data entry errors and convert to dates
        # df.loc[df['pickup_date'] == '6/302020', 'pickup_date'] = '6/30/2020'

        # Assign a candidate status based on the fields from DCBOE
        df['candidate_status'] = '(unknown status)'
        df.loc[df.pickup_date.notnull(), 'candidate_status'] = 'Pulled Papers for Ballot'

        # todo: Before ballots deadline, they are 'Filed Signatures'
        # After ballot deadline, they are 'On the Ballot'
        # df.loc[df.filed_date.notnull(), 'candidate_status'] = 'Filed Signatures'
        df.loc[df.filed_date.notnull(), 'candidate_status'] = 'On the Ballot'

        # df.loc[df.candidate_name.str.contains('Withdrew'), 'candidate_status'] = 'Withdrew' # old way
        df.loc[df['Date of Withdrawal'].notnull(), 'candidate_status'] = 'Withdrew' # new way

        df.loc[df['Challenge Notes'].notnull(), 'candidate_status'] = 'Did Not Qualify for Ballot'

        df.loc[df.is_write_in, 'candidate_status'] = 'Write-In Candidate'

        print('\nCount of candidates by status:')
        candidate_count_by_status = df.candidate_status.value_counts()
        candidate_count_by_status.loc['Total'] = candidate_count_by_status.sum()
        print(candidate_count_by_status)

        df['pickup_date'] = pd.to_datetime(df['pickup_date']).dt.strftime('%Y-%m-%d')

        # There are some candidate rows that don't have a pickup date, but I think we should assume they have picked up
        df['pickup_date'] = df['pickup_date'].fillna('unknown pickup date')    

        # df.loc[df['filed_date'] == '7F06', 'filed_date'] = None
        df['filed_date'] = pd.to_datetime(df['filed_date']).dt.strftime('%Y-%m-%d')

        # Make sure each district matches the actual list of districts
        validate_smd_ids(df)

        # Create a new ID for this data based off of a hash of the district, candidate name, and election year
        df['candidate_name_upper'] = df['candidate_name'].str.upper()
        df['election_year'] = str(config.current_election_year)
        df['external_id'] = hash_dataframe(df, ['election_year', 'smd_id', 'candidate_name_upper'])

        # Add the write-in winners to the write-in dataframe, then dedupe it
        # todo 2024: remove this bit
        # df_write_in_winners = pd.read_csv('data/dcboe/write_in_winners.csv')
        # df_write_in_winners = df_write_in_winners[df_write_in_winners.election_year == 2022].copy()
        # df_write_in_winners['candidate_source'] = 'DCBOE Write-In Winners'
        # df_write_in_winners['candidate_source_link'] = 'https://electionresults.dcboe.org/election_results/2022-General-Election'
        # df_write_in_winners['is_write_in'] = True
        # df_write_in_winners['candidate_status'] = 'Write-In Candidate'
        # df_write_in_winners['dcboe_updated_at'] = '2022-11-30'
        
        # df = pd.concat([df, df_write_in_winners], ignore_index=True)
        df = df.drop_duplicates(subset='external_id', keep='first')


        columns_to_save = [
            'external_id'
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
            'external_id'
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



    def most_recent_file(self, directory_name, filename_pattern, election_year=config.current_election_year):
        """
        Returns the most recent file in a directory. 
        The filenames must have a timestamp in them. It's the max of the sorted text.

        directory_name: the directory to search in. Include the slash at the end
        filename_pattern: the text in the filename to narrow the results by

        The current_election_year must also be in the file name.
        """

        list_of_files = sorted(
            [f for f in os.listdir(directory_name) if (
                filename_pattern in f
                and '~' not in f
                and str(election_year) in f
                )
            ]
            )

        if len(list_of_files) == 0:
            print(f'No files match the pattern "{filename_pattern}" in directory "{directory_name}" in the election year {election_year}.')
            mrf = None
        else:
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

        # Remove the part of the DCBOE candidate name string matchng "(Withdrew 9/4/24)"
        candidates_dcboe['candidate_name'] = (
            candidates_dcboe['candidate_name']
            .str.replace(r'\(withdrew [^)]*\)', '', regex=True, case=False)
            .str.replace(r'\(challenge [^)]*\)', '', regex=True, case=False)
            )

        # Exclude the hash_ids that are currently in the OpenANC candidates table
        candidates_to_match = candidates_dcboe[ ~(candidates_dcboe['external_id'].isin(candidates['external_id'])) ].copy()

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

            candidates_to_match.loc[idx, 'match_score'] = best_score
            candidates_to_match.loc[idx, 'match_person_id'] = best_id
            candidates_to_match.loc[idx, 'match_person_full_name'] = people[people.person_id == best_id].full_name.iloc[0]
            candidates_to_match.loc[idx, 'match_person_smd_id'] = people[people.person_id == best_id].most_recent_smd_id.iloc[0]

        
        candidates_to_match['good_match'] = '?'
        match_columns = [
            'external_id'
            , 'match_score'
            , 'candidate_name'
            , 'match_person_full_name'
            , 'smd_id'
            , 'match_person_smd_id'
            , 'match_person_id'
            , 'good_match'
            ]

        candidates_to_match[match_columns].sort_values(by='match_score', ascending=False).to_csv(self.match_file, index=False)



    def candidate_counts(self):
        """
        Check existing and new candidate hashes to see where there are mismatches

        When a candidate's name changes, the hash from the new file should be written to the OpenANC Source candidate sheet

        todo: delete when branch `merge` is well... merged
        """

        candidates = pd.read_csv('data/candidates.csv')
        candidates = candidates[candidates.election_year == config.current_election_year].copy()
        dcboe = pd.read_csv('data/dcboe/candidates_dcboe.csv')

        print(f'\nValid DCBOE candidates: {len(dcboe)}')

        dcboe_in_openanc = [h for h in dcboe.external_id.tolist() if h in candidates.external_id.tolist()]
        print(f'DCBOE candidate IDs in OpenANC candidate list: {len(dcboe_in_openanc)}')

        dcboe_not_in_openanc = [h for h in dcboe.external_id.tolist() if h not in candidates.external_id.tolist()]
        print(f'DCBOE candidate IDs *not* in OpenANC candidate list: {len(dcboe_not_in_openanc)}')

        openanc_candidates_not_in_dcboe_file = ~( candidates['external_id'].isin(dcboe['external_id']) )
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

        candidates_this_year = candidates[candidates.election_year == config.current_election_year].copy()
        dcboe = pd.read_csv('data/dcboe/candidates_dcboe.csv')

        if not self.match_file.exists():
            self.run_matching_process()

        matches = pd.read_csv(self.match_file)

        if any(matches.good_match.isin(['?'])):
            print(f'Next, evaluate the person name matches in: {self.match_file.name}')
            return

        good_matches = matches[matches.good_match == 1].copy()
        people_create = matches[matches.good_match == 0].copy()


        mc = pd.merge(good_matches, candidates_this_year[['candidate_id', 'person_id']], how='left', left_on='match_person_id', right_on='person_id')

        # Candidates who need a hash ID change
        candidates_change_hash_id = mc[mc.candidate_id.notnull()].copy()
        print(f'\nExisting candidates need the external_id changed ({len(candidates_change_hash_id)} people): 2a_candidates_change_hash_id.csv')
        change_hash_columns = ['candidate_id', 'person_id', 'external_id', 'smd_id', 'candidate_name']
        candidates_change_hash_id[change_hash_columns].sort_values(by='candidate_id').to_csv('data/dcboe/2a_candidates_change_hash_id.csv', index=False)

        # Candidates who are existing people
        candidates_create = mc[mc.candidate_id.isnull()].copy()
        print(f'Existing people need to be added to the candidates table ({len(candidates_create)} people): 2b_candidates_create.csv')
        candidates_create = candidates_create.sort_values(by='match_person_id')

        candidates_create['candidate_id_suggested'] = None
        for idx, row in candidates_create.iterrows():
            candidates_create.loc[idx, 'candidate_id_suggested'] = max_id_candidate + 1
            max_id_candidate += 1

        candidates_create['election_year'] = config.current_election_year
        candidates_create_columns = ['candidate_id_suggested', 'match_person_id', 'election_year', 'external_id', 'smd_id', 'candidate_name']
        candidates_create[candidates_create_columns].to_csv('data/dcboe/2b_candidates_create.csv', index=False)

        print(f'New people need to be created ({len(people_create)} people): 2c_people_create.csv')

        people_create = people_create.sort_values(by='smd_id')

        people_create['candidate_id_suggested'] = None
        people_create['person_id_suggested'] = None
        for idx, row in people_create.iterrows():
            people_create.loc[idx, 'candidate_id_suggested'] = max_id_candidate + 1
            max_id_candidate += 1

            people_create.loc[idx, 'person_id_suggested'] = max_id_person + 1
            max_id_person += 1


        people_create['election_year'] = config.current_election_year
        people_create_columns = [
            'candidate_id_suggested'
            , 'person_id_suggested'
            , 'election_year'
            , 'external_id'
            , 'smd_id'
            , 'candidate_name'
        ]
        
        people_create[people_create_columns].to_csv('data/dcboe/2c_people_create.csv', index=False)

        openanc_not_in_dcboe = [h for h in candidates_this_year[candidates_this_year.external_id.notnull()].external_id.tolist() if h not in dcboe.external_id.tolist()]
        print(f'\nCandidates hash_ids in OpenANC that are no longer in the DCBOE list (should be zero): {len(openanc_not_in_dcboe)}')
        
        if openanc_not_in_dcboe:
            print('\nThese candidates have a hash_id in the OpenANC candidates list but are no longer on the DCBOE list:')

            # before ballot deadline
            # print(candidates_this_year[candidates_this_year.external_id.isin(openanc_not_in_dcboe)][['external_id', 'smd_id', 'candidate_name']])

            # after ballot deadline
            print('(a lot of them, because candidates who did not submit signatures were taken out of the candidate list)\n')



    def confirm_districts_match(self):
        """
        Confirm that the districts in the DCBOE candidate list match the OpenANC candidate list.

        Candidate districts can change, if there was a data entry error or something. This catches those.
        """

        dcboe_candidates = pd.read_csv('data/dcboe/candidates_dcboe.csv')
        openanc_candidates = pd.read_csv('data/candidates.csv')

        combine = pd.merge(dcboe_candidates, openanc_candidates, how='inner', on='external_id', suffixes=['_dcboe', '_openanc'])

        mismatch_smd_ids = combine.smd_id_dcboe != combine.smd_id_openanc

        if mismatch_smd_ids.sum() > 0:
            print(f'\nNumber of SMD IDs that do not match between DCBOE and OpenANC: {mismatch_smd_ids.sum()}')
            combine.loc[mismatch_smd_ids, ['candidate_id', 'candidate_name_openanc', 'external_id', 'smd_id_dcboe', 'smd_id_openanc']].to_csv('data/dcboe/3_smd_mismatch.csv', index=False)
            print('Fix these before continuing: 3_smd_mismatch.csv')
            return False
        else:
            return True




    def run(self):

        df = self.clean_csv()

        confirm_key_uniqueness('data/dcboe/candidates_dcboe.csv', 'external_id')

        dcboe_not_in_openanc, openanc_candidates_not_in_dcboe_file = self.candidate_counts()

        self.upload_dcboe_to_google_sheets(df)

        if len(dcboe_not_in_openanc) == 0:
            print('\nAll DCBOE candidates are in OpenANC.')
            
            if not self.confirm_districts_match():
                return

            if self.match_file.exists():
                print(f'Please delete the file: {self.match_file.name}')
                return

            print('Update complete!')
            return

        self.list_candidates_to_add()


        
