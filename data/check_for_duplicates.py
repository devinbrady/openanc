# check_for_duplicates.py

import pandas as pd


people = pd.read_csv('data/people.csv')
candidates = pd.read_csv('data/candidates.csv')
candidates.rename(columns={'smd_id': 'running_for_smd'}, inplace=True)

people_candidates = pd.merge(people, candidates, how='left', on='person_id')

people_candidates.loc[people_candidates['current_smd_id'] == 'not_currently_serving', 'current_smd_id'] = None
people_candidates['smd_either'] = people_candidates['current_smd_id'].fillna(people_candidates['running_for_smd'])

people_candidates.sort_values(by=['smd_either', 'full_name'], inplace=True)

columns_to_save = [
    'smd_either'
    , 'full_name'
    , 'candidate_name'
    , 'person_id'
    , 'candidate_id'
    , 'current_smd_id'
    , 'running_for_smd'
]

people_candidates[columns_to_save].to_csv('data/check_for_duplicates.csv', index=False)