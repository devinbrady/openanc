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
    , anc_url
)

from scripts.data_transformations import districts_candidates_commissioners

from scripts.counts import Counts



class BuildIndex():

    def __init__(self):
        # todo: find a cleaner way to track insert text and related functions
        self.html_inserts = {}



    def district_tables(self):
        """
        Build HTML containing each ANC and its child SMDs with commissioners and candidates
        """

        ancs = pd.read_csv('data/ancs.csv')
        districts = pd.read_csv('data/districts.csv')

        html = ''

        redist_header = ['Election 2022', 'Election 2020']

        for idx, redistricting_yr in enumerate([2022, 2012]):

            html += f'<h2>{redist_header[idx]}</h2>'

            districts_cycle = districts[districts.redistricting_year == redistricting_yr].copy()
            ancs_cycle = ancs[ancs.redistricting_year == redistricting_yr].copy()

            for _, row in ancs_cycle.iterrows():

                html += f'<h3><a href="{anc_url(row.anc_id)}">{row.anc_name}</a></h3>'

                smds_in_anc = districts_cycle[districts_cycle['anc_id'] == row.anc_id]['smd_id'].to_list()

                html += build_smd_html_table(smds_in_anc, level=0)

        return html



    def list_page(self):
        """
        Build List View page
        """

        with open('templates/list.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)

        output = output.replace('REPLACE_WITH_DISTRICT_LIST', self.district_tables())

        output = add_footer(output, level=0)

        with open('docs/list.html', 'w') as f:
            f.write(output)

        print('built: list.html')



    def count_page(self):
        """
        Build Count page
        """

        with open('templates/counts.html', 'r') as f:
            output = f.read()

        c = Counts()
        # smd_df = districts_candidates_commissioners()

        output = output.replace('REPLACE_WITH_COMMISSIONER_COUNT', c.commissioner_count())
        output = output.replace('REPLACE_WITH_DC_COUNT', c.smd_vote_counts('dc', '#fdbf6f')) # light orange
        output = output.replace('REPLACE_WITH_WARD_COUNT', c.smd_vote_counts('ward', '#b2df8a')) # light green
        output = output.replace('REPLACE_WITH_ANC_COUNT', c.smd_vote_counts('anc_id', '#a6cee3')) # light blue
        output = output.replace('REPLACE_WITH_CONTESTED_COUNT', c.contested_count())
        output = output.replace('REPLACE_WITH_STATUS_COUNT', c.candidate_status_count())
        # output = output.replace('REPLACE_WITH_PICKUPS_BY_DAY', c.pickups_by_day())

        output = add_google_analytics(output)
        output = add_footer(output, level=0)

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
        output = add_footer(output, level=0)

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
        output = add_footer(output, level=0)

        mb_style_slugs = mapbox_slugs()
        output = output.replace('REPLACE_WITH_SMD_SLUG', mb_style_slugs['smd'])
        output = output.replace('REPLACE_WITH_SMD_2022_SLUG', mb_style_slugs['smd-2022'])
        output = output.replace('REPLACE_WITH_SMD_2022_NO_CANDIDATES_SLUG', mb_style_slugs['smd-2022-no-candidates'])

        with open(f'docs/{html_name}.html', 'w') as f:
            f.write(output)

        print(f'built: {html_name}.html')



    def build_single_page(self, html_name):
        """
        Build a single page that just needs Google Analytics and the footer
        """

        with open(f'templates/{html_name}.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)
        output = add_footer(output, level=0)

        with open(f'docs/{html_name}.html', 'w') as f:
            f.write(output)

        print(f'built: {html_name}.html')



    def run(self):

        # self.count_page()
        self.list_page()
        self.about_page()
        # self.build_single_page('index')
        self.build_map_page('index')
        self.build_single_page('404')

