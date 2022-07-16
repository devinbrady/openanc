"""
Functions for transforming raw data from CSVs into useful DataFrames
"""

import pytz
import pandas as pd
from datetime import datetime

# from scripts.refresh_data import RefreshData


def districts_candidates_commissioners(duplicate_check=False, print_counts=False):
    """
    Return DataFrame, one row per district, with candidate names and counts

    Technically there can't be candidates and commissioners-elect at the same time,
    but I'm putting them in the same function for cohesion.
    """

    districts = pd.read_csv('data/districts.csv')
    candidates = pd.read_csv('data/candidates.csv')
    commissioners = list_commissioners(status=None)
    people = pd.read_csv('data/people.csv')
    candidate_statuses = pd.read_csv('data/candidate_statuses.csv')


    candidate_people = pd.merge(candidates, people, how='inner', on='person_id')
    candidate_people.rename(columns={'full_name': 'full_name_candidate'}, inplace=True)
    cps = pd.merge(candidate_people, candidate_statuses, how='inner', on='candidate_status')


    """
    Group candidates by district so that each row has a string containing
    all candidates for that district. Only include active candidates.

    todo: make this candidate order also randomized
    """

    candidates_by_district = cps[cps['count_as_candidate']].groupby('smd_id').agg({
        'full_name_candidate': list
        , 'candidate_id': 'count'
        }).reset_index()

    district_candidates = pd.merge(districts, candidates_by_district, how='left', on='smd_id')


    """
    Add current and future commissioners to the district DataFrame
    """

    commissioner_people = pd.merge(commissioners, people, how='inner', on='person_id')

    comm_columns = ['smd_id', 'full_name']
    orange = pd.merge(district_candidates, commissioner_people[commissioner_people.is_current][comm_columns], how='left', on='smd_id')
    orange.rename(columns={'full_name': 'full_name_commissioner'}, inplace=True)

    banana = pd.merge(orange, commissioner_people[commissioner_people.is_future][comm_columns], how='left', on='smd_id')
    banana.rename(columns={'full_name': 'full_name_commissioner_elect'}, inplace=True)


    district_info_comm = banana.copy()

    # todo: use the new agg() format to obviate this
    district_info_comm.rename(columns={
        'full_name_commissioner': 'current_commissioner'
        , 'full_name_commissioner_elect': 'commissioner_elect'
        , 'full_name_candidate': 'list_of_candidates_to_join'
        , 'candidate_id': 'number_of_candidates'
        }, inplace=True)

    district_info_comm['number_of_candidates'] = district_info_comm['number_of_candidates'].fillna(0)

    district_info_comm['current_commissioner'] = district_info_comm['current_commissioner'].fillna('(vacant)')

    district_info_comm.loc[district_info_comm['number_of_candidates'] == 0, 'list_of_candidates_to_join'] = (
        district_info_comm.loc[district_info_comm['number_of_candidates'] == 0, 'list_of_candidates_to_join'].apply(
            lambda x: ['(no known candidates)'])
        )

    district_info_comm['list_of_candidates'] = district_info_comm['list_of_candidates_to_join'].apply(', '.join)

    # Maybe add Last Updated to this? 

    if duplicate_check:
        district_info_comm[district_info_comm['number_of_candidates'] > 1][['smd_id', 'current_commissioner', 'list_of_candidates']].to_csv('data/check_for_duplicates.csv', index=False)

    if print_counts:
        print('Candidate Count: {}'.format( cps['count_as_candidate'].sum()))

        print('\nDistricts by number of candidates: ')
        print(district_info_comm.groupby('number_of_candidates').size())
        print()


    district_info_comm['number_of_candidates'] = district_info_comm['number_of_candidates'].astype(int)

    output_columns = [
        'smd_id'
        , 'redistricting_year'
        , 'smd_name'
        , 'map_color_id'
        , 'list_of_candidates'
        , 'number_of_candidates'
        , 'current_commissioner'
        , 'commissioner_elect'
    ]

    return district_info_comm[output_columns]



def districts_comm_commelect():
    """
    Build DataFrame showing commissioner and commissioner-elect for every district
    """

    districts = pd.read_csv('data/districts.csv')
    commissioners = list_commissioners(status=None)
    people = pd.read_csv('data/people.csv')

    cp = pd.merge(commissioners, people, how='inner', on='person_id')
    
    # left join to both current commissioners and commissioners-elect
    cp_current = pd.merge(districts, cp.loc[cp['is_current'], ['smd_id', 'person_id', 'full_name']], how='left', on='smd_id')
    cp_current = cp_current.rename(columns={'full_name': 'current_commissioner', 'person_id': 'current_person_id'})

    cp_current_future = pd.merge(cp_current, cp.loc[cp['is_future'], ['smd_id', 'person_id', 'full_name']], how='left', on='smd_id')
    cp_current_future = cp_current_future.rename(columns={'full_name': 'commissioner_elect', 'person_id': 'future_person_id'})

    # If there is not a current commissioner for the SMD, mark the row as "vacant"
    cp_current_future['current_commissioner'] = cp_current_future['current_commissioner'].fillna('(vacant)')

    return cp_current_future



def list_commissioners(status=None, date_point=None):
    """
    Return dataframe with list of commissioners by status

    todo: make status a list, not just one option, for districts_candidates_commissioners
    (it wants current and future but not former)

    Options:
    status=None (all statuses returned) -- default
    status='former'
    status='current'
    status='future'

    date_point=None -- all statuses calculated from current DC time (default)
    date_point=(some other datetime) -- all statuses calculated from that datetime
    """

    commissioners = pd.read_csv('data/commissioners.csv')

    if not date_point:
        tz = pytz.timezone('America/New_York')
        date_point = datetime.now(tz)

    commissioners['start_date'] = pd.to_datetime(commissioners['start_date']).dt.tz_localize(tz='America/New_York')
    commissioners['end_date'] = pd.to_datetime(commissioners['end_date']).dt.tz_localize(tz='America/New_York')

    # Create combined field with start and end dates, showing ambiguity
    commissioners['start_date_str'] = commissioners['start_date'].dt.strftime('%B %-d, %Y')
    commissioners['end_date_str'] = commissioners['end_date'].dt.strftime('%B %-d, %Y')

    # We don't have exact dates when these commissioners started, so show "circa 2019"
    commissioners.loc[commissioners['start_date_str'] == 'January 2, 2019', 'start_date_str'] = '~2019'

    # Combine start and end dates into one field
    commissioners['term_in_office'] = commissioners['start_date_str'] + ' to ' + commissioners['end_date_str']

    commissioners['is_former'] = commissioners.end_date < date_point
    commissioners['is_current'] = (commissioners.start_date < date_point) & (date_point < commissioners.end_date)
    commissioners['is_future'] = date_point < commissioners.start_date

    # Test here that there is, at most, one "Current" and one "Future" commissioner per SMD. 
    # Multiple "Former" commissioners is allowed
    smd_count = commissioners.groupby('smd_id')[['is_former', 'is_current', 'is_future']].sum().astype(int)
    # smd_count.to_csv('smd_commissioner_count.csv')
    
    if smd_count['is_current'].max() > 1 or smd_count['is_future'].max() > 1:
        raise Exception('Too many commissioners per SMD')

    if status:
        commissioner_output = commissioners[commissioners['is_' + status]].copy()
    else:
        commissioner_output = commissioners.copy()

    return commissioner_output