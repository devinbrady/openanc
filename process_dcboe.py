"""
Process data from the DC Board of Elections
"""

import hashlib
import numpy as np
import pandas as pd
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

from scripts.refresh_data import RefreshData


def clean_csv():
    """
    Process CSV made by Tabula from PDF from the DC Board of Elections

    Result is a CSV of current candidates
    """

    df = pd.read_excel('data/dcboe/excel/dcboe-2020-07-28_1743.xlsx')
    df['dcboe_updated_at'] = '2020-07-28 17:43'

    df['candidate_source'] = 'DCBOE'
    df['candidate_source_link'] = 'https://www.dcboe.org/Candidates/2020-Candidates'

    df.rename(
        columns={
            'ANC/SMD': 'smd'
            , 'Name': 'candidate_name'
            , 'Address': 'address'
            , 'Zip': 'zip'
            , 'Phone': 'phone'
            , 'Email Address': 'campaign_email'
            , 'Date of Pick-up': 'pickup_date'
            , 'Date Filed': 'filed_date'
            }, inplace=True
        )

    # drop header rows interspersed in data
    df = df[df['smd'] != 'ANC/SMD'].copy()

    # drop rows with NULL name
    df.dropna(subset=['candidate_name'], inplace=True)

    # Drop bad data

    # trim bad characters from all fields
    for c in ['smd', 'candidate_name']:
        df[c] = df[c].apply(lambda row: row.strip())

    df['smd_id'] = 'smd_' + df['smd']


    # Lisa Palmer is duplicated by DCBOE. She IS NOT running in 2B03. She IS running in 2E05
    # df = df[ ~((df['candidate_name'] == 'Lisa Palmer') & (df['smd_id'] == 'smd_2B03') )]

    # Exclude candidates who dropped out
    df = df[df['candidate_name'] != 'Andrew Spencer DeFrank']
    df = df[df['candidate_name'] != 'Randy D Downs (withdrew 7/24/20)']
    df = df[df['candidate_name'] != 'Pete Stamper (Withdrew 7/27/2020)']

    # Fix data entry errors and convert to dates
    # df.loc[df['pickup_date'] == '6/302020', 'pickup_date'] = '6/30/2020'
    df['pickup_date'] = pd.to_datetime(df['pickup_date']).dt.strftime('%Y-%m-%d')

    # There are some candidate rows that don't have a pickup date, but I think we should assume they have picked up
    df['pickup_date'] = df['pickup_date'].fillna('unknown pickup date')    

    # df.loc[df['filed_date'] == '7F06', 'filed_date'] = None
    df['filed_date'] = pd.to_datetime(df['filed_date']).dt.strftime('%Y-%m-%d')

    # Create a new ID for this data based off of the district and candidate name
    df['dcboe_hash_id'] = hash_dataframe(df, ['smd_id', 'candidate_name'])

    columns_to_save = [
        'dcboe_hash_id'
        , 'smd_id'
        , 'candidate_name'
        , 'pickup_date'
        , 'filed_date'
        , 'candidate_source'
        , 'candidate_source_link'
        , 'dcboe_updated_at'
        ]

    df.sort_values(by='smd_id', inplace=True)
    df[columns_to_save].to_csv('data/dcboe/candidates_dcboe.csv', index=False)

    rd = RefreshData()
    rd.upload_to_google_sheets(df, columns_to_save, 'openanc_source', 'dcboe')


def hash_dataframe(df, columns_to_hash):
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



def match_names(source_value, list_to_search, list_of_ids):
    """
    Take one name, compare to list of names, return the best match and the match score
    """

    matches = process.extract(source_value, list_to_search, scorer=fuzz.ratio, limit=1)

    best_id = list_of_ids[matches[0][2]]
    best_score = matches[0][1]
        
    return best_id, best_score



def run_matching_process():

    people = pd.read_csv('data/people.csv')
    candidates = pd.read_csv('data/candidates.csv')
    candidates_dcboe = pd.read_csv('data/dcboe/candidates_dcboe.csv')

    # Exclude the hash_ids that are currently in the OpenANC candidates table
    candidates_dcboe = candidates_dcboe[ ~(candidates_dcboe['dcboe_hash_id'].isin(candidates['dcboe_hash_id'])) ]

    # candidates_dcboe['new_person'] = True
    candidates_dcboe['person_id'] = pd.NA
    candidates_dcboe['person_id'] = candidates_dcboe['person_id'].astype('Int64')

    """
    If the candidate name has a high match score to the name of the current 
    officeholder for that SMD, consider that a match
    """

    for idx, row in candidates_dcboe.iterrows():

        current_comm = people[people['current_smd_id'] == row['smd_id']]
        
        if len(current_comm) == 0:
            continue

        best_id, best_score = match_names(row['candidate_name'], current_comm['full_name'], current_comm['person_id'])

        if best_score >= 80:

            candidates_dcboe.loc[idx, 'person_id'] = best_id
            # candidates_dcboe.loc[idx, 'new_person'] = False
    
    candidates_dcboe.to_csv('data/dcboe/candidates_dcboe_match.csv', index=False)


    # prepare records for adding to Google Sheets
    add_records_to_people = pd.DataFrame(columns=['person_id', 'full_name'])
    add_records_to_candidates = pd.DataFrame(columns=['candidate_id', 'person_id', 'dcboe_hash_id', 'smd_id', 'candidate_name'])

    max_id_person = people['person_id'].max()
    if pd.isnull(max_id_person):
        max_id_person = 10000
    
    max_id_candidate = candidates['candidate_id'].max()
    if pd.isnull(max_id_candidate):
        max_id_candidate = 50000

    for idx, row in candidates_dcboe.iterrows():

        # new person
        if pd.isnull(row['person_id']):

            # add to person
            new_person_id = 1 + max_id_person
            max_id_person = new_person_id

            new_person = pd.DataFrame({
                'person_id': new_person_id
                , 'full_name': row['candidate_name']
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
    add_records_to_people.to_csv('data/dcboe/to_google_sheets/add_records_to_people.csv', index=False)

    add_records_to_candidates.reset_index(inplace=True)
    add_records_to_candidates.drop(columns=['index'], inplace=True)
    add_records_to_candidates.to_csv('data/dcboe/to_google_sheets/add_records_to_candidates.csv', index=False)



if __name__ == '__main__':

    clean_csv()

    run_matching_process()
