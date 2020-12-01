# counts.py

import imgkit
import pandas as pd
from scripts.refresh_data import RefreshData
from scripts.common import (
    list_commissioners
    , make_ordinal
    )


class Counts():



    def commissioner_count(self):
        """
        Return HTML table with count of vacant districts
        """

        districts = pd.read_csv('data/districts.csv')
        commissioners = list_commissioners(status='current')

        df = pd.DataFrame(index=[0])
        df['Single Member Districts'] = len(districts)
        df['Current Vacancies'] = len(districts) - len(commissioners)

        html = (
            df.style
            .set_uuid('commissioners_count')
            .hide_index()
            .render()
            )

        return html


    def assemble_divo(self):
        """
        Return DataFrame with one row per SMD and various stats about each SMD's ranking

        divo = district-votes
        """

        results = pd.read_csv('data/results.csv')
        districts = pd.read_csv('data/districts.csv')

        votes_per_smd = pd.DataFrame(results.groupby('smd_id').votes.sum()).reset_index()

        # Calculate number of SMDs in each Ward and ANC
        smds_per_ward = pd.DataFrame(districts.groupby('ward').size(), columns=['smds_in_ward']).reset_index()
        smds_per_anc = pd.DataFrame(districts.groupby('anc_id').size(), columns=['smds_in_anc']).reset_index()

        divo = pd.merge(districts, votes_per_smd, how='inner', on='smd_id')
        divo = pd.merge(divo, smds_per_ward, how='inner', on='ward')
        divo = pd.merge(divo, smds_per_anc, how='inner', on='anc_id')
        divo['smds_in_dc'] = len(districts)

        # Rank each SMD by the number of votes recorded for ANC races within that SMD
        # method = min: assigns the lowest rank when multiple rows are tied
        divo['rank_dc'] = divo['votes'].rank(method='min', ascending=False)
        divo['rank_ward'] = divo.groupby('ward').votes.rank(method='min', ascending=False)
        divo['rank_anc'] = divo.groupby('anc_id').votes.rank(method='min', ascending=False)

        # Create strings showing the ranking of each SMD within its ANC, Ward, and DC-wide
        divo['string_dc'] = divo.apply(
            lambda row: f"{make_ordinal(row['rank_dc'])} out of {row['smds_in_dc']} SMDs", axis=1)

        divo['string_ward'] = divo.apply(
            lambda row: f"{make_ordinal(row['rank_ward'])} out of {row['smds_in_ward']} SMDs", axis=1)

        divo['string_anc'] = divo.apply(
            lambda row: f"{make_ordinal(row['rank_anc'])} out of {row['smds_in_anc']} SMDs", axis=1)


        average_votes_in_dc = divo.votes.mean()
        average_votes_by_ward = divo.groupby('ward').votes.mean()
        average_votes_by_anc = divo.groupby('anc_id').votes.mean()

        # Since ANC is the smallest grouping, it should always have the highest number of average votes
        highest_average_votes_for_bar_chart = average_votes_by_anc.max()

        return divo, highest_average_votes_for_bar_chart



    def smd_vote_counts(self, groupby_field, bar_color):
        """
        Count the number of votes in each grouping
        """

        divo, highest_average_votes_for_bar_chart = self.assemble_divo()

        if groupby_field == 'dc':

            divo['District'] = 'DC'

            smd_count = divo.groupby('District').agg(
                num_smds = ('smd_id', 'count')
                , total_votes = ('votes', 'sum')
                )

        else:

            smd_count = divo.groupby(groupby_field).agg(
                num_smds = ('smd_id', 'count')
                , total_votes = ('votes', 'sum')
                )

        smd_count['Average Votes per SMD'] = smd_count['total_votes'] / smd_count['num_smds']

        smd_count = smd_count.reset_index()
        smd_count.rename(columns={
            'ward': 'Ward'
            , 'anc_id': 'ANC'
            , 'num_smds': 'Count of SMDs'
            , 'total_votes': 'Total ANC Votes'
            }, inplace=True
            )

        if 'Ward' in smd_count.columns:
            smd_count['Ward'] = smd_count['Ward'].apply(lambda row: '<a href="wards/ward{0}.html">Ward {0}</a>'.format(row))
            first_column = 'Ward'
        elif 'ANC' in smd_count.columns:
            smd_count['ANC'] = smd_count['ANC'].apply(lambda row: '<a href="ancs/anc{0}.html">ANC {1}</a>'.format(row.lower(), row))
            first_column = 'ANC'
        else:
            first_column = 'District'
        
        smd_html = (
            smd_count.style
                .set_properties(
                    subset=first_column
                    , **{'width': '80px'}
                    )
                .set_properties(
                    subset=['Average Votes per SMD']
                    , **{
                        'text-align': 'left'
                        , 'width': '700px'
                        }
                    )
                .format({
                    'Total ANC Votes': '{:,.0f}'
                    , 'Average Votes per SMD': '{:,.1f}'
                    })
                .bar(
                    subset=['Average Votes per SMD']
                    , color=bar_color
                    , vmin=0
                    , vmax=highest_average_votes_for_bar_chart
                    )
                .set_uuid(groupby_field + '_')
                .hide_index()
                .render()
            )
        
        return smd_html



    def smd_candidate_count(self, groupby_field, bar_color):
        """
        Count the number of SMDs and number of SMDs with candidates in each ANC or ward
        """

        rd = RefreshData()
        df = rd.assemble_smd_info()

        df['has_candidate'] = df['number_of_candidates'] > 0

        districts = pd.read_csv('data/districts.csv')
        dfd = pd.merge(df, districts, how='inner', on='smd_id')

        if groupby_field == 'dc':

            dfd['District'] = 'DC'

            smd_count = dfd.groupby('District').agg(
                num_smds = ('smd_id', 'count')
                , has_candidate = ('has_candidate', 'sum')
                )

        else:

            smd_count = dfd.groupby(groupby_field).agg(
                num_smds = ('smd_id', 'count')
                , has_candidate = ('has_candidate', 'sum')
                )

        smd_count['Needs Candidate'] = smd_count['num_smds'] - smd_count['has_candidate']
        smd_count['Percentage with Candidate'] = smd_count['has_candidate'] / smd_count['num_smds']

        smd_count = smd_count.reset_index()
        smd_count.rename(columns={
            'ward': 'Ward'
            , 'anc_id': 'ANC'
            , 'num_smds': 'Count of SMDs'
            , 'has_candidate': 'Has Candidate'
            }, inplace=True
            )

        if 'Ward' in smd_count.columns:
            smd_count['Ward'] = smd_count['Ward'].apply(lambda row: '<a href="wards/ward{0}.html">Ward {0}</a>'.format(row))
            first_column = 'Ward'
        elif 'ANC' in smd_count.columns:
            smd_count['ANC'] = smd_count['ANC'].apply(lambda row: '<a href="ancs/anc{0}.html">ANC {1}</a>'.format(row.lower(), row))
            first_column = 'ANC'
        else:
            first_column = 'District'
        
        smd_html = (
            smd_count.style
                .set_properties(
                    subset=first_column
                    , **{'width': '80px'}
                    )
                .set_properties(
                    subset=['Percentage with Candidate']
                    , **{
                        'text-align': 'left'
                        , 'width': '700px'
                        }
                    )
                .format({
                    'Has Candidate': '{:.0f}'
                    , 'Needs Candidate': '{:.0f}'
                    , 'Percentage with Candidate': '{:.0%}'
                    })
                .bar(subset=['Percentage with Candidate'], color=bar_color, vmin=0, vmax=1)
                .set_uuid(groupby_field + '_')
                .hide_index()
                .render()
            )
        
        return smd_html



    def contested_count(self):
        """
        Return HTML with number of candidates in each district, shows how many races are contested
        """

        rd = RefreshData()
        smd_df = rd.assemble_smd_info()
        smd_df.rename(columns={'number_of_candidates': 'Number of Candidates'}, inplace=True)
        html = ''


        # Count of contested vs uncontested
        election_status_count = pd.DataFrame(columns=['Election Status', 'Count of Districts', 'Percentage'])
        election_status_count.loc[0] = ['No Candidates Running', sum(smd_df['Number of Candidates'] == 0), 0]
        election_status_count.loc[1] = ['Uncontested (1 candidate)', sum(smd_df['Number of Candidates'] == 1), 0]
        election_status_count.loc[2] = ['Contested (2 or more candidates)', sum(smd_df['Number of Candidates'] > 1), 0]

        election_status_count['Percentage'] = election_status_count['Count of Districts'] / election_status_count['Count of Districts'].sum()

        html += '<p>'
        html += (
            election_status_count.style
            .format({
                'Percentage': '{:.1%}'
                })
            .set_uuid('election_status_count_')
            .hide_index()
            .render()
            )
        html += '</p>'


        # Count by number of candidates

        candidate_count = pd.DataFrame(
            smd_df.groupby('Number of Candidates').size()
            , columns=['Count of Districts']
            ).reset_index()

        candidate_count['Percentage'] = candidate_count['Count of Districts'] / candidate_count['Count of Districts'].sum()

        html += '<p>'
        html += (
            candidate_count.style
            .format({
                'Percentage': '{:.1%}'
                })
            .set_uuid('candidate_count_')
            .hide_index()
            .render()
            )
        html += '</p>'

        return html



    def candidate_status_count(self):
        """
        Return HTML table with count of candidates by candidate status
        """

        candidates = pd.read_csv('data/candidates.csv')
        statuses = pd.read_csv('data/candidate_statuses.csv')

        candidate_statuses = pd.merge(candidates, statuses, how='inner', on='candidate_status')

        status_count = candidate_statuses.groupby(['display_order', 'candidate_status']).size()
        status_count.loc[('Total', 'Total')] = len(candidate_statuses)
        
        status_count_df = pd.DataFrame(status_count, columns=['Count']).reset_index()
        status_count_df.rename(columns={'candidate_status': 'Candidate Status'}, inplace=True)

        # status_html = status_count_df[['Candidate Status', 'Count']].to_html(index=False, justify='left')
        
        status_html = (
            status_count_df[['Candidate Status', 'Count']].style
                .set_uuid('status_count_df_')
                .hide_index()
                .render()
            )

        return status_html



    def pickups_by_day(self):
        """
        Table showing candidates picking up and filing by date
        """

        df = pd.read_csv('data/dcboe/candidates_dcboe.csv')


        p = pd.DataFrame(df[df['pickup_date'] != 'unknown pickup date'].groupby('pickup_date').size(), columns=['Candidates Picked Up'])
        p['Candidates Picked Up Running Total'] = p['Candidates Picked Up'].cumsum()
        p = p.reset_index()
        p.rename(columns={'pickup_date': 'Date'}, inplace=True)


        f = pd.DataFrame(df.groupby('filed_date').size(), columns=['Candidates Filed'])
        f['Candidates Filed Running Total'] = f['Candidates Filed'].cumsum()
        f = f.reset_index()
        f.rename(columns={'filed_date': 'Date'}, inplace=True)

        g = pd.merge(p, f, how='outer', on='Date').fillna(0)

        g['Percentage Filed'] = g['Candidates Filed Running Total'] / g['Candidates Picked Up Running Total']

        column_tuples = [
            ('', 'Date')
            , ('Candidates Picked Up', 'Count')
            , ('Candidates Picked Up', 'Running Total')
            , ('Candidates Filed', 'Count')
            , ('Candidates Filed', 'Running Total')
            , ('', 'Percentage Filed')
            ]

        g.columns = pd.MultiIndex.from_tuples(column_tuples, names=('a', 'b'))


        pickups_html = (
            g.style
                .format({
                    ('Candidates Filed', 'Count'): '{:.0f}'
                    , ('Candidates Filed', 'Running Total'): '{:.0f}'
                    , ('', 'Percentage Filed'): '{:.1%}'
                })
                .bar(subset=[('', 'Percentage Filed')], color='#B3B3B3', vmin=0, vmax=1) # gray
                .set_uuid('g_')
                .hide_index()
                .render()
            )

        # imgkit.from_string(pickups_html, 'pickups_by_day.png')

        return pickups_html



