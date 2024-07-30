# counts.py

import pytz
import pandas as pd
from datetime import datetime

import matplotlib as mpl
from matplotlib import rc
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.font_manager as fm
from matplotlib._color_data import TABLEAU_COLORS

from scripts.common import (
    assemble_divo
    , current_date_str
    )

from scripts.data_transformations import (
    list_commissioners
    , list_candidates
    , districts_candidates_commissioners
    )

from scripts.urls import generate_link

import config


class Counts():

    def commissioner_count(self):
        """
        Return HTML table with count of vacant districts
        """

        districts = pd.read_csv('data/districts.csv')
        districts = districts[districts.redistricting_year == config.current_redistricting_year].copy()

        commissioners = list_commissioners(status='current')

        df = pd.DataFrame(index=[0])
        df['Single Member Districts'] = len(districts)
        df['Current Vacancies'] = len(districts) - len(commissioners)

        html = (
            df.style
            .set_uuid('commissioners_count')
            .hide(axis='index')
            .to_html()
            )

        return html



    def contested_count_by_grouping(self, groupby_field):
        """Count of districts by number of candidates by ward or ANC"""

        districts = pd.read_csv('data/districts.csv')
        districts = districts[districts.redistricting_year == config.current_redistricting_year].copy()
        ancs = pd.read_csv('data/ancs.csv')
        wards = pd.read_csv('data/wards.csv')
        
        ancs['anc_link'] = ancs.apply(lambda x: generate_link(x.anc_id, x.anc_name, link_source='root'), axis=1)
        wards['ward_link'] = wards.apply(lambda x: generate_link(x.ward_id, x.ward_name, link_source='root'), axis=1)

        districts = pd.merge(districts, ancs[['anc_id', 'anc_link']], how='inner', on='anc_id')
        districts = pd.merge(districts, wards[['ward_id', 'ward_link']], how='inner', on='ward_id')

        smd_df = districts_candidates_commissioners(redistricting_year=config.current_redistricting_year)
        districts = pd.merge(
            districts
            , smd_df
            , how='left'
            , on='smd_id'
        )

        cand_count = pd.pivot_table(
            data=districts
            , columns='number_of_candidates'
            , index=groupby_field
            , aggfunc='size'
            , fill_value=0
        )

        cand_count.columns = [f'{c} candidate' if c == 1 else f'{c} candidates' for c in cand_count.columns]

        cand_count['Total'] = cand_count.sum(axis=1)
        cand_count.loc['Total'] = cand_count.sum(axis=0)

        cand_count['Percent Unfilled'] = cand_count['0 candidates'] / cand_count['Total']

        cand_count.index.name = ''
        cand_count.columns.name = ''
        
        html = (
            cand_count
            .style
            .format({'Percent Unfilled': '{:.1%}'.format})
            .applymap(lambda x: 'background: yellow' if x >= 0.5 else '', subset='Percent Unfilled')
            .set_uuid(f'cand_count_{groupby_field}_')
            .to_html()
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
                .hide(axis='index')
                .to_html()
            )
        
        return smd_html



    def smd_candidate_count(self, groupby_field, bar_color):
        """
        Count the number of SMDs and number of SMDs with candidates in each ANC or ward
        """

        df = districts_candidates_commissioners(redistricting_year=config.current_redistricting_year)

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
                .hide(axis='index')
                .to_html()
            )
        
        return smd_html



    def contested_count_df(self):
        """Return DataFrame with the count of contested districts"""

        smd_df = districts_candidates_commissioners(redistricting_year=config.current_redistricting_year)
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
            .hide(axis='index')
            .to_html()
            )
        html += '</p>'

        html += '<p>'
        html += (
            candidate_count.style
            .format({
                'Percentage': '{:.1%}'
                })
            .set_uuid('candidate_count_')
            .hide(axis='index')
            .to_html()
            )
        html += '</p>'

        return html



    def candidate_status_count(self):
        """
        Return HTML table with count of candidates by candidate status
        """

        candidates = list_candidates()
        statuses = pd.read_csv('data/candidate_statuses.csv')

        candidate_statuses = pd.merge(candidates, statuses, how='inner', on='candidate_status')

        # status_count = candidate_statuses.groupby(['display_order', 'candidate_status']).size()
        # status_count.loc[('Total', 'Total')] = len(candidate_statuses)
        
        # status_count_df = pd.DataFrame(status_count, columns=['Count']).reset_index()
        status_count_df = pd.pivot_table(
            data=candidate_statuses
            , index=['display_order', 'candidate_status']
            , columns='count_as_candidate'
            , aggfunc='size'
            , fill_value=0
            ).reset_index()

        status_count_df.rename(columns={
            'candidate_status': 'Candidate Status'
            , False: 'Inactive'
            , True: 'Active'
            }, inplace=True)

        status_count_df.loc['Total'] = status_count_df.sum(axis=0)
        status_count_df.loc['Total', 'Candidate Status'] = 'Total'
        
        status_html = (
            status_count_df[['Candidate Status', 'Active', 'Inactive']]
                .style
                .set_uuid('status_count_df_')
                .hide(axis='index')
                .to_html()
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
            '<p><em>Some candidates who have filled out the OpenANC Candidate Declaration form have not '
            + 'yet picked up petitions from DCBOE, so they do not have a pickup date yet, and thus the total '
            + 'number of candidates here does not match the actual number of candidates. Excludes withdrawn candidates.</em></p>'
            )

        pickups_html += (
            g.style
                .format({
                    ('Candidates Filed', 'Count'): '{:.0f}'
                    , ('Candidates Filed', 'Running Total'): '{:.0f}'
                    , ('', 'Percentage Filed'): '{:.1%}'
                })
                .bar(subset=[('', 'Percentage Filed')], color='#B3B3B3', vmin=0, vmax=1) # gray
                .set_uuid('g_')
                .hide(axis='index')
                .to_html()
            )


        pickups_html += (
            '<p><img src="images/Candidates_Picking_Up_and_Filing.png" '
            + f'alt="Line graph showing candidates picking up and filing petitions comparing {config.current_election_year-2} and {config.current_election_year}"></p>'
            )

        return pickups_html



    def pickups_plot(self):
        """
        Plot showing the running total of candidates who picked up and filed petitions by date,
        comparing the current election year with the previous cycle.
        """

        # Set the font to Helvetica
        rc('font',**{'family':'sans-serif','sans-serif':['Helvetica']})
        # prop = fm.FontProperties(fname='templates/WorkSans[wght].ttf')


        candidates = pd.read_csv('data/candidates.csv')
        candidates['pickup_date'] = pd.to_datetime(candidates['pickup_date'])
        candidates['filed_date'] = pd.to_datetime(candidates['filed_date'])
        years = sorted(candidates[candidates.pickup_date.notnull()].pickup_date.dt.year.unique())

        deadlines = {
            2020: pd.to_datetime('2020-08-05')
            , 2022: pd.to_datetime('2022-08-10')
        }

        start_date = {
            2020: pd.to_datetime('2020-06-26')
            , 2022: pd.to_datetime('2022-07-20')
        }

        pickup_by_day = candidates.groupby('pickup_date').size()
        filed_by_day = candidates.groupby('filed_date').size()

        pickup_by_year = {}
        filed_by_year = {}
        for y in years:
            pickup_by_year[y] = pd.DataFrame(pickup_by_day[pickup_by_day.index.year == y], columns=['pickups'])
            filed_by_year[y] = pd.DataFrame(filed_by_day[filed_by_day.index.year == y], columns=['filers'])

        # Start with 2020 data and calculate sums
        comp = pd.DataFrame(index=pd.date_range(start=start_date[2020], end=deadlines[2020]))
        comp = pd.merge(comp, pickup_by_year[2020].pickups, how='left', left_index=True, right_index=True)
        comp = pd.merge(comp, filed_by_year[2020].filers, how='left', left_index=True, right_index=True)
        comp.pickups = comp.pickups.fillna(0)
        comp.filers = comp.filers.fillna(0)
        comp['cumulative_pickups_2020'] = comp.pickups.cumsum()
        comp['cumulative_filers_2020'] = comp.filers.cumsum()
        comp['days_to_deadline'] = (comp.index - deadlines[2020]).days
        comp.drop(columns=['pickups', 'filers'], inplace=True)

        # Join 2022 data and calculate sums
        pickup_by_year[2022]['days_to_deadline'] = (pickup_by_year[2022].index - deadlines[2022]).days
        filed_by_year[2022]['days_to_deadline'] = (filed_by_year[2022].index - deadlines[2022]).days

        comp = pd.merge(comp, pickup_by_year[2022], how='left', on='days_to_deadline')
        comp = pd.merge(comp, filed_by_year[2022], how='left', on='days_to_deadline')

        comp['cumulative_pickups_2022'] = comp.pickups.cumsum().ffill()
        comp['cumulative_filers_2022'] = comp.filers.cumsum().ffill()

        # Fill in NULLs where 2022 dates haven't happened yet
        comp.loc[
            comp.days_to_deadline.isin(range(pickup_by_year[2022].days_to_deadline.max() + 1, 1))
            , ['cumulative_pickups_2022', 'cumulative_filers_2022']
        ] = None

        comp.drop(columns=['pickups', 'filers'], inplace=True)

        rc('font', family='sans-serif')
        rc('font', serif='Helvetica Neue')
        rc('text', usetex='false')
        mpl.rcParams.update({'font.size': 12})

        fig, ax = plt.subplots(figsize=(9,6))

        plt.plot(comp['cumulative_pickups_2020'], label='2020 Picked Up Petitions', color='tab:blue', linestyle='dotted')
        plt.plot(comp['cumulative_pickups_2022'], label='2022 Picked Up Petitions', color='tab:blue', linestyle='solid')
        plt.plot(comp['cumulative_filers_2020'], label='2020 Filed Petitions', color='tab:orange', linestyle='dotted')
        plt.plot(comp['cumulative_filers_2022'], label='2022 Filed Petitions', color='tab:orange', linestyle='solid')

        xtick_range = list(range(0,len(comp), 5))
        plt.xticks(ticks=xtick_range, labels=abs(comp.loc[xtick_range, 'days_to_deadline']))
        plt.xlabel(f'Days to Filing Deadline (updated {current_date_str()})')
        plt.ylabel('Running Total of Candidates')
        plt.legend()
        plt.title('ANC Candidates Picking Up Petitions: 2020 vs 2022')

        plt.savefig(
            'docs/images/Candidates_Picking_Up_and_Filing.png', transparent=False, facecolor='white', bbox_inches='tight')