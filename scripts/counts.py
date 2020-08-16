# counts.py

import imgkit
import pandas as pd
from scripts.refresh_data import RefreshData
from scripts.common import current_commissioners


class Counts():



    def commissioner_count(self):
        """
        Return HTML table with count of vacant districts
        """

        districts = pd.read_csv('data/districts.csv')
        commissioners = current_commissioners()

        df = pd.DataFrame(index=[0])
        df['Single Member Districts'] = len(districts)
        df['Vacancies'] = len(districts) - len(commissioners)

        html = (
            df.style
            .set_properties(**{
                'border-color': 'black'
                , 'border-style': 'solid'
                , 'border-width': '1px'
                , 'text-align': 'center'
                , 'padding': '4px'
                # , 'border-collapse': 'collapse'
                })
            .set_uuid('commissioners_count')
            .hide_index()
            .render()
            )

        return html

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
                .set_properties(**{
                    'border-color': 'black'
                    , 'border-style': 'solid'
                    , 'border-width': '1px'
                    , 'text-align': 'center'
                    , 'padding': '4px'
                    # , 'border-collapse': 'collapse'
                    })
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
            .set_properties(**{
                'border-color': 'black'
                , 'border-style' :'solid'
                , 'border-width': '1px'
                , 'border-collapse':'collapse'
                , 'padding': '4px'
                })
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
            .set_properties(**{
                'border-color': 'black'
                , 'border-style' :'solid'
                , 'border-width': '1px'
                , 'border-collapse':'collapse'
                , 'padding': '4px'
                })
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
                .set_properties(**{
                    'border-color': 'black'
                    , 'border-style' :'solid'
                    , 'border-width': '1px'
                    , 'border-collapse':'collapse'
                    , 'padding': '4px'
                    })
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
                .set_properties(**{
                    'border-color': 'black'
                    , 'border-style' :'solid'
                    , 'border-width': '1px'
                    , 'border-collapse':'collapse'
                    , 'padding': '4px'
                    })
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



