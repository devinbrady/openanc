"""
Build Index page
"""

import pandas as pd
from bs4 import BeautifulSoup

from scripts.common import build_district_list


class BuildIndex():


    def run(self):
        """Add information to index page"""

        districts = pd.read_csv('data/districts.csv')
        commissioners = pd.read_csv('data/commissioners.csv')
        candidates = pd.read_csv('data/candidates.csv')

        district_candidates = pd.merge(districts, candidates, how='left', on='smd')

        no_candidate_districts = district_candidates[district_candidates['candidate_id'].isnull()]['smd'].nunique()

        with open('templates/index-template.html', 'r') as f:
            output = f.read()

        output = output.replace('NUMBER_OF_COMMISSIONERS', str(len(commissioners)))
        output = output.replace('NUMBER_OF_VACANCIES', str(296 - len(commissioners)))
        output = output.replace('NUMBER_OF_CANDIDATES', str(len(candidates)))
        output = output.replace('NUMBER_OF_NO_CANDIDATES', str(no_candidate_districts))

        output = output.replace('REPLACE_WITH_DISTRICT_LIST', build_district_list())

        soup = BeautifulSoup(output, 'html.parser')
        output_pretty = soup.prettify()

        with open('docs/index.html', 'w') as f:
            f.write(output_pretty)

        print('Index built.')
