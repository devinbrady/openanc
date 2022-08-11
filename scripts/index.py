"""
Build Index page
"""

import pandas as pd

from scripts.common import (
    add_footer
    , edit_form_link
    , add_google_analytics
    , build_smd_html_table
    , mapbox_slugs
)

from scripts.urls import (
    generate_url
    , generate_link
    )

from scripts.data_transformations import (
    districts_candidates_commissioners
    , incumbent_df
    , list_commissioners
    , list_candidates
    )

from scripts.counts import Counts



class BuildIndex():

    def __init__(self):
        self.candidate_statuses = pd.read_csv('data/candidate_statuses.csv')



    def district_tables(self):
        """
        Build HTML containing each ANC and its child SMDs with commissioners and candidates
        """

        ancs = pd.read_csv('data/ancs.csv')
        districts = pd.read_csv('data/districts.csv')
        district_comm_commelect = districts_candidates_commissioners(link_source='root')

        html = ''

        redist_header = ['Election 2022', 'Election 2020']

        for idx, redistricting_yr in enumerate([2022, 2012]):

            html += f'<h2>{redist_header[idx]}</h2>'

            districts_cycle = districts[districts.redistricting_year == redistricting_yr].copy()
            ancs_cycle = ancs[ancs.redistricting_year == redistricting_yr].sort_values(by='sort_order').copy()

            for _, row in ancs_cycle.iterrows():

                anc_link = generate_url(row.anc_id, link_source='root')
                html += f'<h3><a href="{anc_link}">{row.anc_name}</a></h3>'

                smds_in_anc = districts_cycle[districts_cycle['anc_id'] == row.anc_id]['smd_id'].to_list()

                html += build_smd_html_table(smds_in_anc, link_source='root', district_comm_commelect=district_comm_commelect, candidate_statuses=self.candidate_statuses)

        return html



    def incumbent_tables(self):
        """
        Build HTML containing the status of each incumbent
        """

        comm_candidates_nrd = incumbent_df()
        status_count = comm_candidates_nrd.groupby('reelection_status').size()

        display_columns = ['Incumbent SMD', '2022 Candidate SMD', 'full_name']
        html = ''

        for incumbent_status in ['Not Running', 'Is Running', 'Unknown']:

            html += f'<h2>2022 Candidate Status: {incumbent_status} ({status_count[incumbent_status]} people)</h2>'

            # css_uuid = hashlib.sha224(display_df[columns_to_html].to_string().encode()).hexdigest() + '_'
            css_uuid = 'temp'

            html += (
                comm_candidates_nrd[comm_candidates_nrd.reelection_status == incumbent_status][display_columns]
                .fillna('')
                .style
                .set_properties(
                    subset=['full_name']
                    , **{'width': '230px', 'text-align': 'left'} # 230px fits the longest commissioner name on one row
                    )
                .set_uuid(css_uuid)
                .hide_index()
                .render()
                )


        return html



    def list_page(self):
        """Build List View page"""

        with open('templates/list_all.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)

        output = output.replace('REPLACE_WITH_DISTRICT_LIST', self.district_tables())

        output = add_footer(output, link_source='root')

        with open('docs/list.html', 'w') as f:
            f.write(output)

        print('built: list.html')



    def incumbent_page(self):
        """Build page with list of incumbents by status"""

        with open('templates/incumbents.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)

        output = output.replace('REPLACE_WITH_INCUMBENT_LIST', self.incumbent_tables())

        output = add_footer(output, link_source='root')

        with open('docs/incumbents.html', 'w') as f:
            f.write(output)

        print('built: incumbents.html')



    def count_page(self):
        """Build Count page"""

        with open('templates/counts.html', 'r') as f:
            output = f.read()

        c = Counts()

        output = output.replace('REPLACE_WITH_STATUS_COUNT', c.candidate_status_count())
        output = output.replace('REPLACE_WITH_CONTESTED_COUNT', c.contested_count_html())
        output = output.replace('REPLACE_WITH_WARD_CONTESTED_COUNT', c.contested_count_by_grouping('ward_link'))
        output = output.replace('REPLACE_WITH_ANC_CONTESTED_COUNT', c.contested_count_by_grouping('anc_link'))
        output = output.replace('REPLACE_WITH_PICKUPS_BY_DAY', c.pickups_by_day())
        output = output.replace('REPLACE_WITH_COMMISSIONER_COUNT', c.commissioner_count())
        c.pickups_plot()

        # output = output.replace('REPLACE_WITH_DC_COUNT', c.smd_vote_counts('dc', '#fdbf6f')) # light orange
        # output = output.replace('REPLACE_WITH_WARD_COUNT', c.smd_vote_counts('ward_id', '#b2df8a')) # light green
        # output = output.replace('REPLACE_WITH_ANC_COUNT', c.smd_vote_counts('anc_id', '#a6cee3')) # light blue

        output = add_google_analytics(output)
        output = add_footer(output, link_source='root')

        with open('docs/counts.html', 'w') as f:
            f.write(output)

        print('built: counts.html')



    def about_page(self):
        """
        Build About page
        """

        with open('templates/about.html', 'r') as f:
            output = f.read()

        output = output.replace('REPLACE_WITH_EDIT_LINK', edit_form_link('please fill out this form'))
        output = output.replace('REPLACE_WITH_PLEASE_SUBMIT', edit_form_link('Please submit your information'))
        output = add_google_analytics(output)
        output = add_footer(output, link_source='root')

        with open('docs/about.html', 'w') as f:
            f.write(output)

        print('built: about.html')



    def build_map_page(self, html_name) -> None:
        """
        Builds HTML page from template that is a full-page map, inserting the necessary Mapbox styles from CSV
        """

        with open(f'templates/{html_name}.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)
        output = add_footer(output, link_source='root')

        mb_style_slugs = mapbox_slugs()
        output = output.replace('REPLACE_WITH_SMD_SLUG', mb_style_slugs['smd'])
        output = output.replace('REPLACE_WITH_SMD_2022_SLUG', mb_style_slugs['smd-2022'])
        output = output.replace('REPLACE_WITH_SMD_2022_NO_CANDIDATES_SLUG', mb_style_slugs['smd-2022-no-candidates'])

        with open(f'docs/{html_name}.html', 'w') as f:
            f.write(output)

        print(f'built: {html_name}.html')



    def build_map_page_contested(self, html_name) -> None:
        """
        Builds HTML page from template that is a full-page map, inserting the necessary Mapbox styles from CSV
        """

        with open(f'templates/{html_name}.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)
        output = add_footer(output, link_source='root')

        mb_style_slugs = mapbox_slugs()
        output = output.replace('REPLACE_WITH_SMD_2022_NO_CANDIDATES_SLUG', mb_style_slugs['smd-2022-no-candidates'])
        output = output.replace('REPLACE_WITH_SMD_2022_ONE_CANDIDATE_SLUG', mb_style_slugs['smd-2022-one-candidate'])
        output = output.replace('REPLACE_WITH_SMD_2022_TWO_PLUS_CANDIDATES_SLUG', mb_style_slugs['smd-2022-two-plus-candidates'])

        # c = Counts()
        # election_status_count, _ = c.contested_count_df()
        # election_status_count.set_index('Election Status', inplace=True)

        # output = output.replace(
        #     'REPLACE_WITH_NO_CANDIDATE_COUNT'
        #     , str(election_status_count.loc['No Candidates Running', 'Count of Districts'])
        #     )
        # output = output.replace(
        #     'REPLACE_WITH_ONE_CANDIDATE_COUNT'
        #     , str(election_status_count.loc['Uncontested (1 candidate)', 'Count of Districts'])
        #     )
        # output = output.replace(
        #     'REPLACE_WITH_TWO_PLUS_CANDIDATES_COUNT'
        #     , str(election_status_count.loc['Contested (2 or more candidates)', 'Count of Districts'])
        #     )

        with open(f'docs/{html_name}.html', 'w') as f:
            f.write(output)

        print(f'built: {html_name}.html')



    def build_single_page(self, html_name, link_source='root'):
        """
        Build a single page that just needs Google Analytics and the footer
        """

        with open(f'templates/{html_name}.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)
        output = add_footer(output, link_source=link_source)

        with open(f'docs/{html_name}.html', 'w') as f:
            f.write(output)

        print(f'built: {html_name}.html')



    def run(self):

        self.build_map_page('index')
        self.incumbent_page()
        self.count_page()
        self.about_page()
        # self.build_single_page('index')
        self.build_map_page_contested('contested')
        self.build_single_page('404', link_source='absolute')
        self.build_single_page('nav')
        self.list_page()

