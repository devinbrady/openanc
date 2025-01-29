"""
Match new people to existing people in OpenANC

Sources of new people:
1. Candidates
    a) On ballot
    b) Write-ins
2. Write-in winners
3. New commissioners between elections. 

Theoretically, every winning ballot candidate should have been in OpenANC before Election Day.
"""

import numpy as np
import pandas as pd
from tqdm import tqdm
from pathlib import Path

from fuzzywuzzy import (
    fuzz
    , process
)

from scripts.data_transformations import (
    confirm_key_uniqueness
    , most_recent_smd
)

from scripts.common import (
    hash_dataframe
)

from scripts.refresh_data import RefreshData


class MatchPeople():

    def __init__(self):
        # todo: maybe pass variables to the class?

        self.match_dir = Path('data/matching')
        self.match_dir.mkdir(exist_ok=True)

        self.csv_files = {}
        self.csv_files['eval'] = self.match_dir / 'matches_to_evaluate.csv'
        self.csv_files['people_insert'] = self.match_dir / 'insert_people.csv'
        self.csv_files['external_id_lookup_insert'] = self.match_dir / 'insert_external_id_lookup.csv'

        self.matching_files_exist = any([self.csv_files[key].exists() for key in self.csv_files])



    def read_files_to_memory(self):
        self.external_id_lookup = pd.read_csv('data/external_id_lookup.csv')

        # candidates = pd.read_csv('data/candidates.csv')
        # max_id_candidate = candidates['candidate_id'].max()

        self.people = pd.read_csv('data/people.csv')
        self.people = most_recent_smd(self.people)
        self.max_id_person = self.people.person_id.max()



    def match_to_openanc(self, input_csv_path, source_name, name_column):

        if self.matching_files_exist:
            print('Matching files exist.    ')
            print('\n**** Matching Process Step 3 of 3: Refreshing Data ****')
            print('Downloading fresh data from Google Sheets')
            rd = RefreshData()
            rd.download_google_sheets(do_full_refresh=False)

        self.read_files_to_memory()

        input_csv_path = Path(input_csv_path)
        print(f'Input file: {input_csv_path}')

        # The input CSV must have external_id as its primary key
        confirm_key_uniqueness(input_csv_path, 'external_id')

        input_df = pd.read_csv(input_csv_path)

        input_join_external = pd.merge(input_df, self.external_id_lookup, how='left', on='external_id')

        input_external_ids_known = input_join_external.person_id.notnull()
        input_external_ids_unknown = ~(input_external_ids_known)
        
        print(f'People in input: {len(input_df)}')
        print(f'Known people in input: {input_external_ids_known.sum()}')
        print(f'Unknown people in input: {input_external_ids_unknown.sum()}')
        
        if input_external_ids_unknown.sum() == 0:
            print('Everyone in the input file is already matched to OpenANC.')
            print('\n**** Matching Process Complete ****')
            return # return what?

        people_to_match = input_df.loc[input_external_ids_unknown].copy()

        if self.csv_files['eval'].exists():
            print(f"Evaluation file exists: {self.csv_files['eval']}")
            eval_results = pd.read_csv(self.csv_files['eval'])

            match_unknown = (eval_results.good_match == '?')
            if match_unknown.sum() > 0:
                print(f"Number of potential matches in {self.csv_files['eval']} that still need to be evaluated (?s): {match_unknown.sum()}")
                return # return what?

        else:
            # Evaluation file does not exist, create it
            print('\n**** Matching Process Step 1 of 3: Evaluate Matches ****')
            self.create_match_evaluation_csv(people_to_match, name_column)
            return # return what?


        print('\n**** Matching Process Step 2 of 3: Insert Data to OpenANC Tables ****')
        eval_matches = eval_results.loc[eval_results.good_match == 'y'].copy()
        eval_did_not_match = eval_results.loc[eval_results.good_match == 'n'].copy()

        print(f'Number of people in input who match existing people in OpenANC: {len(eval_matches)}')
        print(f'Number of people in input who do not match existing people in OpenANC: {len(eval_did_not_match)}')


        # todo: turn these next steps into functions
        # Save CSV to be inserted into the Person table
        eval_did_not_match['person_id_suggested'] = 1 + self.max_id_person + np.arange(0, len(eval_did_not_match))

        eval_did_not_match['full_name'] = eval_did_not_match[name_column]
        eval_did_not_match[['person_id_suggested', 'full_name']].to_csv(self.csv_files['people_insert'], index=False)
        print(f"Saved {len(eval_did_not_match)} people to be inserted into Person table: {self.csv_files['people_insert']}")

        # Save CSV to be inserted into the External ID Lookup table
        eval_matches['person_id'] = eval_matches['match_person_id']
        eval_matches['full_name'] = eval_matches['match_full_name']
        eval_did_not_match['person_id'] = eval_did_not_match['person_id_suggested']

        insert_to_external_id_lookup = pd.concat([eval_matches, eval_did_not_match])
        insert_to_external_id_lookup['source'] = source_name

        external_id_columns = ['external_id', 'person_id', 'source', 'full_name']
        insert_to_external_id_lookup[external_id_columns].to_csv(self.csv_files['external_id_lookup_insert'], index=False)
        print(f"Saved {len(insert_to_external_id_lookup)} records to be inserted into External ID Lookup table: {self.csv_files['external_id_lookup_insert']}")

        # Save input file with person_ids appended
        output_df = pd.merge(
            input_df
            , insert_to_external_id_lookup[['external_id', 'person_id', 'full_name']]
            , how='inner'
            , on='external_id'
            )

        print(input_csv_path.stem)
        output_path = self.match_dir /  f'{input_csv_path.stem}_matched_person_id.csv'
        output_df.to_csv(output_path, index=False)
        print(f'Match results saved to: {output_path}')



    def create_match_evaluation_csv(self, match_df, name_column):

        # def match_to_openanc(df, name_column):
        """
        Take a DataFrame with a name_column and find the one best match for each row
        in the OpenANC people database.

        todo: consider including SMD name in the matching logic somehow.
        """

        print('Creating match evaluation file.')

        for idx, row in tqdm(match_df.iterrows(), total=len(match_df), desc='Matching input to OpenANC people'):
                    
            best_id, best_score = self.match_names(row[name_column], self.people['full_name'], self.people['person_id'])

            match_df.loc[idx, 'match_score'] = best_score
            match_df.loc[idx, 'match_person_id'] = best_id
            match_df.loc[idx, 'match_full_name'] = self.people[self.people.person_id == best_id].full_name.iloc[0]
            match_df.loc[idx, 'match_smd_id'] = self.people[self.people.person_id == best_id].most_recent_smd_id.iloc[0]

        match_df['good_match'] = '?'
        
        match_df.sort_values(by='match_score', ascending=False).to_csv(self.csv_files['eval'], index=False)

        print(f"Evaluate the {len(match_df)} potential matches in: {self.csv_files['eval']}")

        return None



    def match_names(self, search_string, list_to_search, list_of_ids):
        """
        Take one name, compare to list of names, return the best match and the match score
        """ 

        matches = process.extract(search_string, list_to_search, scorer=fuzz.ratio, limit=1)

        best_id = list_of_ids[matches[0][2]]
        best_score = matches[0][1]

        return best_id, best_score



    def external_id_match_counts(self, input_df, reference_df): #-> (list, pd.Series)
        """
        Check existing and new external_ids to see where there are mismatches

        When a candidate's name changes, the hash from the new file should be written to the OpenANC Source candidate sheet

        Replaces process_candidates.candidate_counts()
        """

        print(f'\nLength of input dataframe: {len(input_df)}')

        input_in_openanc = [h for h in input_df.external_id.tolist() if h in reference_df.external_id.tolist()]
        print(f'Input external_ids in OpenANC reference list: {len(input_in_openanc)}')

        input_not_in_openanc = [h for h in input_df.external_id.tolist() if h not in reference_df.external_id.tolist()]
        print(f'Input external_ids *not* in OpenANC reference list: {len(input_not_in_openanc)}')

        reference_not_in_input_file = ~( reference_df['external_id'].isin(input_df['external_id']) )
        print(f'OpenANC reference external_ids not in input: {reference_not_in_input_file.sum()}')

        return input_not_in_openanc, reference_not_in_input_file




