"""
Functions for transforming raw data from CSVs into useful DataFrames
"""

import pytz
import pandas as pd
from datetime import datetime


from scripts.urls import (
    relative_link_prefix
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



def districts_candidates_commissioners(
    duplicate_check=False
    , print_counts=False
    , link_source=None
    , redistricting_year=None
    ):

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
        link_prefix = relative_link_prefix(source=link_source, destination='person')
        people['name_url'] = people.apply(lambda x: f'<a href="{link_prefix}{x.name_slug}.html">{x.full_name}</a>', axis=1)
    else:
        people['name_url'] = 'x'

    candidate_people = pd.merge(candidates, people, how='inner', on='person_id')
    candidate_people.rename(columns={'name_url': 'name_url_candidate', 'full_name': 'full_name_candidate'}, inplace=True)
    cps = pd.merge(candidate_people, candidate_statuses, how='inner', on='candidate_status')

    """
    Group candidates by district so that each row has a string containing
    all candidates for that district. Only include active candidates.

    todo: make this candidate order also randomized
    """

    candidates_by_district = cps[cps['count_as_candidate']].groupby('smd_id').agg({
        'name_url_candidate': list
        , 'full_name_candidate': list
        , 'candidate_id': 'count'
        }).reset_index()

    district_candidates = pd.merge(districts, candidates_by_district, how='left', on='smd_id')


    """
    Add current and future commissioners to the district DataFrame
    """

    commissioner_people = pd.merge(commissioners, people, how='inner', on='person_id')

    comm_columns = ['smd_id', 'name_url']
    orange = pd.merge(district_candidates, commissioner_people[commissioner_people.is_current][comm_columns], how='left', on='smd_id')
    orange.rename(columns={'name_url': 'name_url_commissioner'}, inplace=True)

    banana = pd.merge(orange, commissioner_people[commissioner_people.is_future][comm_columns], how='left', on='smd_id')
    banana.rename(columns={'name_url': 'name_url_commissioner_elect'}, inplace=True)


    district_info_comm = banana.copy()

    # todo: use the new agg() format to obviate this
    district_info_comm.rename(columns={
        'name_url_commissioner': 'current_commissioner'
        , 'name_url_commissioner_elect': 'commissioner_elect'
        , 'name_url_candidate': 'list_of_candidates_to_join'
        , 'full_name_candidate': 'list_of_candidate_names_to_join'
        , 'candidate_id': 'number_of_candidates'
        }, inplace=True)

    district_info_comm['number_of_candidates'] = district_info_comm['number_of_candidates'].fillna(0)

    district_info_comm['current_commissioner'] = district_info_comm['current_commissioner'].fillna('(vacant)')

    district_info_comm.loc[district_info_comm['number_of_candidates'] == 0, 'list_of_candidates_to_join'] = (
        district_info_comm.loc[district_info_comm['number_of_candidates'] == 0, 'list_of_candidates_to_join'].apply(
            lambda x: ['(no known candidates)'])
        )

    district_info_comm.loc[district_info_comm['number_of_candidates'] == 0, 'list_of_candidate_names_to_join'] = (
        district_info_comm.loc[district_info_comm['number_of_candidates'] == 0, 'list_of_candidate_names_to_join'].apply(
            lambda x: ['(no known candidates)'])
        )

    district_info_comm['list_of_candidates'] = district_info_comm['list_of_candidates_to_join'].apply(', '.join)
    district_info_comm['list_of_candidate_names'] = district_info_comm['list_of_candidate_names_to_join'].apply(', '.join)

    # Maybe add Last Updated to this? 

    # todo: remove this option, the test should be done somewhere else
    if duplicate_check:
        district_info_comm[district_info_comm['number_of_candidates'] > 1][['smd_id', 'current_commissioner', 'list_of_candidates']].to_csv('data/check_for_duplicates.csv', index=False)

    if print_counts:
        print('Candidate Count: {}'.format( cps['count_as_candidate'].sum()))

        print('\nDistricts by number of candidates: ')
        print(district_info_comm.groupby('number_of_candidates').size())
        print()


    district_info_comm['number_of_candidates'] = district_info_comm['number_of_candidates'].astype(int)

    if redistricting_year:
        district_info_comm = district_info_comm[district_info_comm.redistricting_year == redistricting_year].copy()

    output_columns = [
        'smd_id'
        , 'redistricting_year'
        , 'smd_name'
        , 'map_color_id'
        , 'list_of_candidates'
        , 'list_of_candidate_names'
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
    people['name_slug'] = people.full_name.apply(lambda x: format_name_for_url(x))

    return people



def format_name_for_url(name):
    """
    Strip out the non-ASCII characters from a person's full name to use as the URL.
    This is somewhat like Wikipedia's URL formatting but not exactly.

    Spaces become underscores, numbers and letters with accents are preserved as they are.
    """

    name_formatted = name.replace(' ', '_')

    characters_to_strip = ['"' , '(' , ')' , '.' , '-' , ',' , '\'']
    for c in characters_to_strip:
        name_formatted = name_formatted.replace(c, '')

    return name_formatted

