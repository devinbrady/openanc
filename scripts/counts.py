# counts.py

import pytz
import imgkit
import pandas as pd
from datetime import datetime

from scripts.common import (
    assemble_divo
    )

from scripts.data_transformations import (
    list_commissioners
    , list_candidates
    , districts_candidates_commissioners
    )



class Counts():

    def commissioner_count(self):
        """
        Return HTML table with count of vacant districts
        """

        districts = pd.read_csv('data/districts.csv')
        districts = districts[districts.redistricting_year == 2012].copy()

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



    def smd_vote_counts(self, groupby_field, bar_color):
        """
        Count the number of votes in each grouping
        """

        divo = assemble_divo()

        # Since ANC is the smallest grouping, it should always have the highest number of average votes
        average_votes_by_anc = divo.groupby('anc_id').votes.mean()
        highest_average_votes_for_bar_chart = average_votes_by_anc.max()


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

        if groupby_field == 'anc_id':
            # Join in the ANC table to get neighborhood names
            ancs = pd.read_csv('data/ancs.csv')
            smd_count = pd.merge(smd_count, ancs[['anc_id', 'neighborhoods']], how='inner', on='anc_id')

        smd_count.rename(columns={
            'ward_id': 'Ward'
            , 'anc_id': 'ANC'
            , 'num_smds': 'Count of SMDs'
            , 'total_votes': 'Total ANC Votes'
            }, inplace=True
            )

        if 'Ward' in smd_count.columns:
            smd_count['Ward'] = smd_count['Ward'].apply(lambda row: '<a href="wards/ward{0}.html">Ward {0}</a>'.format(row))
            first_column = 'Ward'
        elif 'ANC' in smd_count.columns:
            smd_count['ANC'] = smd_count.apply(
                lambda row: '<a href="ancs/anc{0}.html">ANC {1}</a> ({2})'.format(row['ANC'].lower(), row['ANC'], row['neighborhoods'])
                , axis=1
                )
            first_column = 'ANC'
        else:
            first_column = 'District'
        
        # Remove the 'neighborhoods' field from display, keep all others
        fields_to_html = [c for c in list(smd_count.columns) if c != 'neighborhoods']

        smd_html = (
            smd_count[fields_to_html].style
                .set_properties(
                    subset=first_column
                    , **{'text-align': 'left'}
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

        df = districts_candidates_commissioners()

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
            'ward_id': 'Ward'
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



    def contested_count_df(self):
        """Return DataFrame with the count of contested districts"""

        smd_df = districts_candidates_commissioners(redistricting_year=2022)
        smd_df.rename(columns={'number_of_candidates': 'Number of Candidates'}, inplace=True)

        election_status_count = pd.DataFrame(columns=['Election Status', 'Count of Districts', 'Percentage'])
        election_status_count.loc[0] = ['No Candidates Running', sum(smd_df['Number of Candidates'] == 0), 0]
        election_status_count.loc[1] = ['Uncontested (1 candidate)', sum(smd_df['Number of Candidates'] == 1), 0]
        election_status_count.loc[2] = ['Contested (2 or more candidates)', sum(smd_df['Number of Candidates'] > 1), 0]

        election_status_count['Percentage'] = election_status_count['Count of Districts'] / election_status_count['Count of Districts'].sum()
        election_status_count.loc[3] = ['Total', smd_df.smd_id.nunique(), 1]

        # Count by number of candidates
        candidate_count = pd.DataFrame(
            smd_df.groupby('Number of Candidates').size()
            , columns=['Count of Districts']
            ).reset_index()

        candidate_count['Percentage'] = candidate_count['Count of Districts'] / candidate_count['Count of Districts'].sum()

        return election_status_count, candidate_count



    def contested_count_html(self):
        """
        Return HTML with number of candidates in each district, shows how many races are contested
        """

        election_status_count, candidate_count = self.contested_count_df()

        html = (
            '<p>These counts include both candidates on the ballot and write-in candidates who fill out the OpenANC Candidate Declaration Form.</p>'
            )
            # + 'Sources of write-in candidates include those who filled out the OpenANC Edit Form, as well as write-in candidates who won their election. '
            # + 'There were almost certainly other write-in candidates who did not fall into those categories. </p>'
            # )

        html += '<p>'
        html += (
            election_status_count.style
            .set_properties(
                subset=['Election Status']
                , **{'text-align': 'left'}
                )
            .format({
                'Percentage': '{:.1%}'
                })
            .set_uuid('election_status_count_')
            .hide_index()
            .render()
            )
        html += '</p>'

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

        candidates = list_candidates(election_year=2022)
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



