"""
Functions for transforming raw data from CSVs into useful DataFrames
"""

import pytz
import numpy as np
import pandas as pd
from datetime import datetime


from scripts.urls import (
    generate_link
    )

def results_candidate_people():
    """
    Return DataFrame containing results, candidates, and people joined
    """

    people = people_dataframe()
    candidates = list_candidates(election_year=2020)
    results = pd.read_csv('data/results.csv')

    results_candidates = pd.merge(
        results #[['candidate_id', 'person_id', 'smd_id']]
        , candidates #[['candidate_id']]
        , how='left'
        , on=['candidate_id', 'smd_id']
        )
    rcp = pd.merge(results_candidates, people, how='left', on='person_id') # results-candidates-people

    # Determine who were incumbent candidates at the time of the election
    election_date = datetime(2020, 11, 3, tzinfo=pytz.timezone('America/New_York'))
    commissioners = list_commissioners(status=None)
    incumbents = commissioners[(commissioners.start_date < election_date) & (election_date < commissioners.end_date)]
    incumbent_candidates = pd.merge(incumbents, candidates, how='inner', on='person_id')
    incumbent_candidates['is_incumbent'] = True

    rcp = pd.merge(rcp, incumbent_candidates[['candidate_id', 'is_incumbent']], how='left', on='candidate_id')
    rcp['is_incumbent'] = rcp['is_incumbent'].fillna(False)

    # Sort by SMD ascenting, Votes descending
    rcp = rcp.sort_values(by=['smd_id', 'votes'], ascending=[True, False])

    # Placeholder name for all write-in candidates. 
    # We do not know the combination of name and vote count for write-in candidates
    # We only know the name of the write-in winners
    rcp['full_name'] = rcp['full_name'].fillna('Write-ins combined')
    rcp['write_in_winner_int'] = rcp['write_in_winner'].astype(int)

    return rcp



def incumbent_df():
    """DataFrame showing re-election status of every incumbent"""

    districts = pd.read_csv('data/districts.csv')
    people = pd.read_csv('data/people.csv')
    comm = list_commissioners(status='current')
    comm.rename(columns={'smd_id': 'commissioner_smd_id'}, inplace=True)
    pc = pd.merge(people[['person_id', 'full_name']], comm, how='inner', on='person_id')

    candidates = list_candidates(election_year=2022)
    candidate_statuses = pd.read_csv('data/candidate_statuses.csv')
    candidates = pd.merge(candidates, candidate_statuses, how='inner', on='candidate_status')
    candidates.rename(columns={'smd_id': 'candidate_smd_id'}, inplace=True)

    not_running = pd.read_csv('data/incumbents_not_running.csv')
    not_running['confirmed_not_running'] = True
            
    comm_candidates = pd.merge(
        pc
        , candidates[['person_id', 'candidate_id', 'candidate_smd_id', 'count_as_candidate']]
        , how='left'
        , on='person_id'
    )

    comm_candidates_nr = pd.merge(
        comm_candidates
        , not_running[['person_id', 'confirmed_not_running']]
        , how='left'
        , on='person_id'
    )

    # Tag the incumbents who dropped out as confirmed_not_running
    comm_candidates_nr.loc[comm_candidates_nr.count_as_candidate == False, 'confirmed_not_running'] = True

    comm_candidates_nr['reelection_status'] = 'Unknown'
    comm_candidates_nr.loc[comm_candidates_nr.confirmed_not_running.fillna(False), 'reelection_status'] = 'Not Running'
    comm_candidates_nr.loc[comm_candidates_nr.count_as_candidate.fillna(False), 'reelection_status'] = 'Is Running'

    comm_candidates_nrd = pd.merge(comm_candidates_nr, districts.rename(columns={'smd_name': 'commissioner_smd_name'}), how='left', left_on='commissioner_smd_id', right_on='smd_id')
    comm_candidates_nrd = pd.merge(comm_candidates_nrd, districts.rename(columns={'smd_name': 'candidate_smd_name'}), how='left', left_on='candidate_smd_id', right_on='smd_id')

    comm_candidates_nrd['Incumbent SMD'] = comm_candidates_nrd.apply(lambda x: 
        generate_link(x.commissioner_smd_id, link_source='root', link_body=x.commissioner_smd_name)
        , axis=1
    )
    comm_candidates_nrd['2022 Candidate SMD'] = comm_candidates_nrd.apply(lambda x:
        '(none)' if pd.isnull(x.candidate_smd_id) else
        generate_link(x.candidate_smd_id, link_source='root', link_body=x.candidate_smd_name)
        , axis=1
    )

    comm_candidates_nrd['candidate_smd_id'] = comm_candidates_nrd['candidate_smd_id'].fillna('(none)')

    comm_candidates_nrd.sort_values(by=['commissioner_smd_id', 'full_name'], inplace=True)

    return comm_candidates_nrd



def districts_candidates_commissioners(link_source=None, redistricting_year=None):
    """
    Return DataFrame, one row per district, with candidate names and counts

    Technically there can't be candidates and commissioners-elect at the same time,
    but I'm putting them in the same function for cohesion.
    """

    districts = pd.read_csv('data/districts.csv')
    candidates = list_candidates(election_year=2022)
    commissioners = list_commissioners(status=None)
    candidate_statuses = pd.read_csv('data/candidate_statuses.csv')

    people = people_dataframe()
    
    if link_source:
        # create links for each person's page, if a link is requested by the calling function
        people['name_link'] = people.apply(lambda x: generate_link(x.person_name_id, link_source=link_source, link_body=x.full_name), axis=1)
    else:
        people['name_link'] = 'x'

    candidate_people = pd.merge(candidates, people, how='inner', on='person_id')
    candidate_people.rename(columns={'name_link': 'name_link_candidate'}, inplace=True)
    candidate_people_status = pd.merge(candidate_people, candidate_statuses, how='inner', on='candidate_status')

    # Randomly shuffle the order of candidates in this DataFrame, and thus the resulting lists
    candidate_people_status = candidate_people_status.sample(frac=1, random_state=today_as_int()).reset_index()

    """
    Group candidates by district so that each row has a string containing
    all candidates for that district. Only include active candidates.
    """

    candidates_by_district = candidate_people_status[candidate_people_status['count_as_candidate']].groupby('smd_id').agg({
        'name_link_candidate': list
        , 'candidate_name': list
        , 'candidate_id': 'count'
        }).reset_index()

    district_candidates = pd.merge(districts, candidates_by_district, how='left', on='smd_id')

    """
    Repeat this above grouping for each possible status of candidate, so the statuses can be
    displayed as different columns in the resulting HTML table.
    """

    active_statuses = sorted(candidate_people_status.display_order.unique())

    for s in active_statuses:
        candidates_in_status_by_district = (
            candidate_people_status[candidate_people_status.display_order == s]
            .groupby('smd_id')
            .agg({
                'name_link_candidate': list
                , 'candidate_id': 'count'
                })
            .reset_index()
            )

        candidates_in_status_by_district.rename(columns={
            'name_link_candidate': f'name_link_candidate_status_{s}'
            , 'candidate_id': f'number_of_candidates_status_{s}'
            }, inplace=True)

        columns_to_merge = ['smd_id', f'name_link_candidate_status_{s}', f'number_of_candidates_status_{s}']

        district_candidates = pd.merge(district_candidates, candidates_in_status_by_district[columns_to_merge], how='left', on='smd_id')




    """
    Add current and future commissioners to the district DataFrame
    """

    commissioner_people = pd.merge(commissioners, people, how='inner', on='person_id')

    comm_columns = ['smd_id', 'name_link']
    comm_temp = pd.merge(district_candidates, commissioner_people[commissioner_people.is_current][comm_columns], how='left', on='smd_id')
    comm_temp.rename(columns={'name_link': 'name_link_commissioner'}, inplace=True)

    district_info_comm = pd.merge(comm_temp, commissioner_people[commissioner_people.is_future][comm_columns], how='left', on='smd_id')
    district_info_comm.rename(columns={'name_link': 'name_link_commissioner_elect'}, inplace=True)


    # todo: use the new agg() format to obviate this
    district_info_comm.rename(columns={
        'name_link_commissioner': 'current_commissioner'
        , 'name_link_commissioner_elect': 'commissioner_elect'
        , 'candidate_name': 'list_of_candidate_names_to_join'
        , 'name_link_candidate': 'list_of_candidate_links_to_join'
        , 'candidate_id': 'number_of_candidates'
        }, inplace=True)

    district_info_comm['number_of_candidates'] = district_info_comm['number_of_candidates'].fillna(0)

    district_info_comm['current_commissioner'] = district_info_comm['current_commissioner'].fillna('(vacant)')

    district_info_comm['list_of_candidate_names'] = district_info_comm.apply(lambda x: ', '.join(x.list_of_candidate_names_to_join) if x.number_of_candidates > 0 else '(no known candidates)', axis=1)
    district_info_comm['list_of_candidate_links'] = district_info_comm.apply(lambda x: ', '.join(x.list_of_candidate_links_to_join) if x.number_of_candidates > 0 else '(no known candidates)', axis=1)

    for s in active_statuses:
        district_info_comm[f'list_of_candidates_status_{s}'] = district_info_comm.apply(lambda x: ', '.join(x[f'name_link_candidate_status_{s}']) if x[f'number_of_candidates_status_{s}'] > 0 else '', axis=1)

    district_info_comm['number_of_candidates'] = district_info_comm['number_of_candidates'].astype(int)

    if redistricting_year:
        district_info_comm = district_info_comm[district_info_comm.redistricting_year == redistricting_year].copy()

    output_columns = [
        'smd_id'
        , 'redistricting_year'
        , 'smd_name'
        , 'map_color_id'
        , 'list_of_candidate_names'
        , 'list_of_candidate_links'
        , 'number_of_candidates'
        , 'current_commissioner'
        , 'commissioner_elect'
    ]

    for s in active_statuses:
        output_columns += [f'list_of_candidates_status_{s}']

    return district_info_comm[output_columns]



def districts_comm_commelect():
    """
    Build DataFrame showing commissioner and commissioner-elect for every district
    """

    districts = pd.read_csv('data/districts.csv')
    commissioners = list_commissioners(status=None)
    people = people_dataframe()

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

    if status and status not in ('former', 'current', 'future'):
        raise ValueError(f'Commissioner status "{status}" is not valid. Must be: former, current, future')

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
    
    if smd_count['is_current'].max() > 1 or smd_count['is_future'].max() > 1:
        raise Exception('Too many commissioners per SMD')

    if status:
        commissioner_output = commissioners[commissioners['is_' + status]].copy()
    else:
        commissioner_output = commissioners.copy()

    return commissioner_output



def list_candidates(election_year=2022):
    """
    Return DataFrame with candidates, either in a particular year or for all time

    election_year=2022 : only return candidates with the election year of 2022 (default)
    election_year=None : return candidates from all years
    """

    candidates = pd.read_csv('data/candidates.csv')

    if election_year:
        candidates_year = candidates[candidates.election_year == election_year].copy()
    else:
        candidates_year = candidates.copy()

    return candidates_year



def people_dataframe():
    """Return dataframe of people.csv with the name URLs added."""

    people = pd.read_csv('data/people.csv')
    # people['name_slug'] = people.full_name.apply(lambda x: format_name_for_url(x))

    return people



def most_recent_smd(people_df):
    """For every person, check the commissioner and candidate table for the most recent SMD they're connected to"""

    candidates = list_candidates(election_year=None)
    commissioners = list_commissioners()

    # Sort data in reverse chronological order
    candidates = candidates.sort_values(by='candidate_id', ascending=False)
    commissioners = commissioners.sort_values(by='start_date', ascending=False)

    # Prefer the SMD from the candidates table, it's more likely to be up to date
    columns_to_concat = ['person_id', 'smd_id']
    any_smd = pd.concat([candidates[columns_to_concat], commissioners[columns_to_concat]])
    latest_smd_id = any_smd.groupby('person_id').smd_id.first()

    people_df = pd.merge(people_df, latest_smd_id, how='left', on='person_id')
    people_df = people_df.rename(columns={'smd_id': 'most_recent_smd_id'})

    return people_df



def today_as_int():
    """
    Return today's date in Eastern Time as an integer. Use as a seed for candidate order randomization
    """

    tz = pytz.timezone('America/New_York')
    dc_now = datetime.now(tz)
    dc_now_str = dc_now.strftime('%Y%m%d')

    return int(dc_now_str)
