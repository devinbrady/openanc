"""
Build Index page
"""

import pandas as pd
from bs4 import BeautifulSoup

from scripts.common import build_district_list, build_footer


class BuildIndex():

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


    def list_of_smds_without_candidates(self):
        """Return a list of SMDs that don't currently have a candidate"""

        districts = pd.read_csv('data/districts.csv')
        candidates = pd.read_csv('data/candidates.csv')

        district_candidates = pd.merge(districts, candidates, how='left', on='smd_id')

        no_candidate_districts = district_candidates[district_candidates['candidate_id'].isnull()]['smd_id'].unique()
        districts_with_candidates = district_candidates[district_candidates['candidate_id'].notnull()]['smd_id'].unique()

        return no_candidate_districts


    def run(self):
        """Add information to index page"""

        districts = pd.read_csv('data/districts.csv')
        commissioners = pd.read_csv('data/commissioners.csv')
        candidates = pd.read_csv('data/candidates.csv')

        district_candidates = pd.merge(districts, candidates, how='left', on='smd_id')

        num_no_candidate_districts = len(self.list_of_smds_without_candidates())

        with open('templates/index.html', 'r') as f:
            output = f.read()

        output = output.replace('NUMBER_OF_COMMISSIONERS', str(len(commissioners)))
        output = output.replace('NUMBER_OF_VACANCIES', str(296 - len(commissioners)))
        output = output.replace('NUMBER_OF_CANDIDATES', str(len(candidates)))
        output = output.replace('NUMBER_OF_NO_CANDIDATES', str(num_no_candidate_districts))

        output = output.replace('REPLACE_WITH_DISTRICT_LIST', self.homepage_list())

        output = output.replace('<!-- replace with footer -->', build_footer())

        soup = BeautifulSoup(output, 'html.parser')
        output_pretty = soup.prettify()

        with open('docs/index.html', 'w') as f:
            f.write(output_pretty)

        print('Index built.')
