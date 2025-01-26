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


class MatchPeople():

    def __init__(self):

        self.match_dir = Path('data/matching')
        self.match_dir.mkdir(exist_ok=True)
        self.eval_file = self.match_dir / 'matches_to_evaluate.csv'



    def match_to_openanc(self, input_csv_path, source_name, name_column):

        # def match_to_openanc(df, name_column):
        """
        Take a DataFrame with a name_column and find the one best match for each row
        in the OpenANC people database.

        todo: consider including SMD name in the matching logic somehow.
        """

        # The input CSV must have external_id as its primary key
        confirm_key_uniqueness(input_csv_path, 'external_id')

        input_df = pd.read_csv(input_csv_path)
        # reference_df = pd.read_csv(reference_csv_path)

        # Silence the SettingWithCopyWarning
        # df = df.copy()

        people = pd.read_csv('data/people.csv')
        people = most_recent_smd(people)

        for idx, row in tqdm(input_df.iterrows(), total=len(input_df), desc='Matching input to OpenANC people'):
                    
            best_id, best_score = self.match_names(row[name_column], people['full_name'], people['person_id'])

            input_df.loc[idx, 'match_score'] = best_score
            input_df.loc[idx, 'match_person_id'] = best_id
            input_df.loc[idx, 'match_full_name'] = people[people.person_id == best_id].full_name.iloc[0]
            input_df.loc[idx, 'match_smd_id'] = people[people.person_id == best_id].most_recent_smd_id.iloc[0]

        input_df['good_match'] = '?'
        
        input_df.sort_values(by='match_score', ascending=False).to_csv(self.eval_file, index=False)

        print(f'Evaluate the {len(input_df)} potential matches in: {self.eval_file}')

        return None



    def match_names(self, source_value, list_to_search, list_of_ids):
        """
        Take one name, compare to list of names, return the best match and the match score
        """

        matches = process.extract(source_value, list_to_search, scorer=fuzz.ratio, limit=1)

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




