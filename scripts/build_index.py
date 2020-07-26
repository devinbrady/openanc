"""
Build Index page
"""

import pandas as pd

from scripts.common import (
    build_anc_html_table
    , anc_names
    , build_footer
    , list_of_smds_without_candidates
    , edit_form_link
    , google_analytics_block
)


class BuildIndex():

    def __init__(self):
        # todo: find a cleaner way to track insert text and related functions
        self.html_inserts = {}


    def district_tables(self):
        """
        Build HTML containing each ANC and its child SMDs with commissioners and candidates
        """

        ancs = pd.read_csv('data/ancs.csv')

        html = ''

        for anc_id in sorted(ancs['anc_id']):

            anc_upper, anc_lower = anc_names(anc_id)

            html += f'<h3><a href="ancs/{anc_lower}.html">{anc_upper}</a></h3>'

            html += build_anc_html_table(anc_id)

        return html


    def list_page(self):
        """
        Build List View page
        """

        districts = pd.read_csv('data/districts.csv')
        commissioners = pd.read_csv('data/commissioners.csv')
        candidates = pd.read_csv('data/candidates.csv')
        candidate_statuses = pd.read_csv('data/candidate_statuses.csv')
        cs = pd.merge(candidates, candidate_statuses, how='inner', on='candidate_status')

        district_candidates = pd.merge(districts, candidates, how='left', on='smd_id')

        num_no_candidate_districts = len(list_of_smds_without_candidates())

        with open('templates/list.html', 'r') as f:
            output = f.read()

        output = output.replace('<!-- replace with google analytics -->', google_analytics_block())

        output = output.replace('NUMBER_OF_COMMISSIONERS', str(len(commissioners)))
        output = output.replace('NUMBER_OF_VACANCIES', str(296 - len(commissioners)))
        output = output.replace('NUMBER_OF_CANDIDATES', str(cs['count_as_candidate'].sum()))
        output = output.replace('NUMBER_OF_NO_CANDIDATES', str(num_no_candidate_districts))

        output = output.replace('REPLACE_WITH_DISTRICT_LIST', self.district_tables())

        output = output.replace('<!-- replace with footer -->', build_footer())

        with open('docs/list.html', 'w') as f:
            f.write(output)

        print('built: list.html')


    def about_page(self):
        """
        Build About page
        """

        with open('templates/about.html', 'r') as f:
            output = f.read()

        output = output.replace('REPLACE_WITH_EDIT_LINK', edit_form_link('please fill out this form'))
        output = output.replace('REPLACE_WITH_PLEASE_SUBMIT', edit_form_link('Please submit your information'))
        output = output.replace('<!-- replace with google analytics -->', google_analytics_block())
        output = output.replace('<!-- replace with footer -->', build_footer())

        with open('docs/about.html', 'w') as f:
            f.write(output)

        print('built: about.html')


    def build_single_page(self, html_name):
        """
        Build a single page that just needs Google Analytics
        """

        with open(f'templates/{html_name}.html', 'r') as f:
            output = f.read()

        output = output.replace('<!-- replace with google analytics -->', google_analytics_block())

        with open(f'docs/{html_name}.html', 'w') as f:
            f.write(output)

        print(f'built: {html_name}.html')


    def run(self):

        self.list_page()
        self.about_page()
        self.build_single_page('index')
        self.build_single_page('needs-candidates')
        self.build_single_page('find-my-district')

