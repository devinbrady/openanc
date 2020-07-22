# counts.py

import pandas as pd
from refresh_data import RefreshData


def smd_candidate_count(groupby_field):
    """
    Count the number of SMDs and number of SMDs with candidates in each ANC or ward
    """

    rd = RefreshData()
    df = rd.assemble_smd_info()

    df['has_candidate'] = df['number_of_candidates'] > 0

    districts = pd.read_csv('data/districts.csv')
    dfd = pd.merge(df, districts, how='inner', on='smd_id')

    smd_count = dfd.groupby(groupby_field).agg(
        num_smds = ('smd_id', 'count')
        , has_candidate = ('has_candidate', 'sum')
        )

    smd_count['percentage_with_candidate'] = smd_count['has_candidate'] / smd_count['num_smds']

    print(smd_count)
    # smd_count.to_csv(groupby_field + '.csv')


if __name__ == '__main__':

    smd_candidate_count('anc_id')
    smd_candidate_count('ward')
