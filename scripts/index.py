"""
Build Index page
"""

import pandas as pd

from scripts.common import (
    anc_names
    , add_footer
    , edit_form_link
    , add_google_analytics
    , build_smd_html_table
    , mapbox_slugs
)

from scripts.counts import Counts
from scripts.refresh_data import RefreshData


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
        districts = districts[districts.redistricting_year == 2012].copy()

        html = ''

        for anc_id in sorted(ancs['anc_id']):

            anc_upper, anc_lower, anc_neighborhoods = anc_names(anc_id)

            html += f'<h3><a href="ancs/{anc_lower}.html">{anc_upper}</a> ({anc_neighborhoods})</h3>'

            smds_in_anc = districts[districts['anc_id'] == anc_id]['smd_id'].to_list()

            html += build_smd_html_table(smds_in_anc, link_path='ancs/districts/')

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
        rd = RefreshData()
        smd_df = rd.assemble_smd_info()

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

        self.count_page()
        self.list_page()
        self.about_page()
        # self.build_single_page('index')
        self.build_map_page('map')
        self.build_single_page('404')

