"""
Build Index page
"""

import pandas as pd
from bs4 import BeautifulSoup

from scripts.common import build_district_list


class BuildIndex():

    def homepage_list(self):
        """Build list of ANCs and SMDs"""

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



    def run(self):
        """Add information to index page"""

        districts = pd.read_csv('data/districts.csv')
        commissioners = pd.read_csv('data/commissioners.csv')
        candidates = pd.read_csv('data/candidates.csv')

        district_candidates = pd.merge(districts, candidates, how='left', on='smd_id')

        no_candidate_districts = district_candidates[district_candidates['candidate_id'].isnull()]['smd_id'].nunique()

        with open('templates/index.html', 'r') as f:
            output = f.read()

        output = output.replace('NUMBER_OF_COMMISSIONERS', str(len(commissioners)))
        output = output.replace('NUMBER_OF_VACANCIES', str(296 - len(commissioners)))
        output = output.replace('NUMBER_OF_CANDIDATES', str(len(candidates)))
        output = output.replace('NUMBER_OF_NO_CANDIDATES', str(no_candidate_districts))

        output = output.replace('REPLACE_WITH_DISTRICT_LIST', self.homepage_list())

        soup = BeautifulSoup(output, 'html.parser')
        output_pretty = soup.prettify()

        with open('docs/index.html', 'w') as f:
            f.write(output_pretty)

        print('Index built.')
