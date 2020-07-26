"""
Build Index page
"""

import pandas as pd

from scripts.common import build_district_list, build_footer, list_of_smds_without_candidates, edit_form_link, google_analytics_block


class BuildIndex():

    def __init__(self):
        self.html_inserts = {}

    def homepage_list(self):
        """Build a nested HTML list of ANCs and SMDs"""

        ancs = pd.read_csv('data/ancs.csv')
        districts = pd.read_csv('data/districts.csv')

        anc_html = '<ul>'
        for idx, anc_row in ancs.iterrows():

            anc_id = anc_row['anc_id']
            anc_upper = 'ANC' + anc_id
            anc_lower = anc_upper.lower()

            anc_html += f'<li><a href="ancs/{anc_lower}.html">{anc_upper}</a></li>'

            smds_in_anc = districts[districts['anc_id'] == anc_id]['smd_id'].tolist()
            anc_html += build_district_list(smd_id_list=smds_in_anc, level=0)

        anc_html += '</ul>'

        return anc_html


    def index_page(self):
        """Add information to index page"""

        districts = pd.read_csv('data/districts.csv')
        commissioners = pd.read_csv('data/commissioners.csv')
        candidates = pd.read_csv('data/candidates.csv')

        district_candidates = pd.merge(districts, candidates, how='left', on='smd_id')

        num_no_candidate_districts = len(list_of_smds_without_candidates())

        with open('templates/index.html', 'r') as f:
            output = f.read()

        output = output.replace('<!-- replace with google analytics -->', google_analytics_block())

        output = output.replace('NUMBER_OF_COMMISSIONERS', str(len(commissioners)))
        output = output.replace('NUMBER_OF_VACANCIES', str(296 - len(commissioners)))
        output = output.replace('NUMBER_OF_CANDIDATES', str(len(candidates)))
        output = output.replace('NUMBER_OF_NO_CANDIDATES', str(num_no_candidate_districts))

        output = output.replace('REPLACE_WITH_DISTRICT_LIST', self.homepage_list())

        output = output.replace('<!-- replace with footer -->', build_footer())

        with open('docs/index.html', 'w') as f:
            f.write(output)

        print('built: index.html')


    def list_page(self):
        """Add information to List View"""

        districts = pd.read_csv('data/districts.csv')
        commissioners = pd.read_csv('data/commissioners.csv')
        candidates = pd.read_csv('data/candidates.csv')

        district_candidates = pd.merge(districts, candidates, how='left', on='smd_id')

        num_no_candidate_districts = len(list_of_smds_without_candidates())

        with open('templates/list.html', 'r') as f:
            output = f.read()

        output = output.replace('<!-- replace with google analytics -->', google_analytics_block())

        output = output.replace('NUMBER_OF_COMMISSIONERS', str(len(commissioners)))
        output = output.replace('NUMBER_OF_VACANCIES', str(296 - len(commissioners)))
        output = output.replace('NUMBER_OF_CANDIDATES', str(len(candidates)))
        output = output.replace('NUMBER_OF_NO_CANDIDATES', str(num_no_candidate_districts))

        output = output.replace('REPLACE_WITH_DISTRICT_LIST', self.homepage_list())

        output = output.replace('<!-- replace with footer -->', build_footer())

        with open('docs/list.html', 'w') as f:
            f.write(output)

        print('built: list.html')


    def about_page(self):

        # Build About page
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

        self.index_page()
        self.list_page()
        self.about_page()
        self.build_single_page('needs-candidates')
        self.build_single_page('find-my-district')

