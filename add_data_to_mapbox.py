"""
Add fresh data to GeoJSON file for upload to Mapbox
"""

import pandas as pd
import geopandas as gpd


def assemble_smd_info():
    """
    Make CSV, one row per district, with candidate names and counts

    Destination is a Mapbox dataset
    """


    districts = pd.read_csv('data/districts.csv')
    candidates = pd.read_csv('data/candidates.csv')
    commissioners = pd.read_csv('data/commissioners.csv')
    people = pd.read_csv('data/people.csv')


    candidate_people = pd.merge(candidates, people, how='inner', on='person_id')
    candidate_people.rename(columns={'full_name': 'full_name_candidate'}, inplace=True)

    commissioner_people = pd.merge(commissioners, people, how='inner', on='person_id')
    commissioner_people.rename(columns={'full_name': 'full_name_commissioner'}, inplace=True)

    district_candidates = pd.merge(districts, candidate_people, how='left', on='smd_id')



    district_info = district_candidates.groupby('smd_id').agg({
        'full_name_candidate': list
        , 'candidate_id': 'count'
        })



    district_info_comm = pd.merge(district_info, commissioner_people[['smd_id', 'full_name_commissioner']], how='left', on='smd_id')


    district_info_comm.rename(columns={
        'full_name_commissioner': 'current_commissioner'
        , 'full_name_candidate': 'list_of_candidates'
        , 'candidate_id': 'number_of_candidates'
        }, inplace=True)


    district_info_comm['current_commissioner'] = district_info_comm['current_commissioner'].fillna('(vacant)')
    district_info_comm.loc[district_info_comm['number_of_candidates'] == 0, 'list_of_candidates'] = "['No known candidates']"

    # district_info_comm.loc[district_info_comm['number_of_candidates'] > 0, 'list_of_candidates'] = district_info_comm.loc[district_info_comm['number_of_candidates'] > 0, 'list_of_candidates'].apply(eval).apply(', '.join)
    district_info_comm['list_of_candidates'] = district_info_comm['list_of_candidates'].astype(str)
    # district_info_comm['list_of_candidates'] = district_info_comm['list_of_candidates'].str.replace('[', '')

    print(district_info_comm.head(10))
    
    # district_info_comm.to_csv('data/to_mapbox/smd_info.csv', index=False)

    # Maybe add Last Updated to this? 

    return district_info_comm


def add_data_to_geojson():

    df = assemble_smd_info()

    smd = gpd.read_file('maps/smd.geojson')

    smd_df = smd.merge(df, on='smd_id')

    smd_df.to_file('maps/smd-data.geojson', driver='GeoJSON')


    lp = pd.read_csv('maps/label_points.csv')
    lp_df = pd.merge(lp, df[['smd_id', 'current_commissioner', 'number_of_candidates', 'list_of_candidates']], how='inner', on='smd_id')
    lp_df.to_csv('maps/label_points_data.csv', index=False)



if __name__ == '__main__':

    add_data_to_geojson()