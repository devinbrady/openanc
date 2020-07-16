"""
Build Index page
"""

import pandas as pd
from bs4 import BeautifulSoup


class BuildIndex():

    def build_district_list(self):
        """Bulleted list of districts and current commmissioners"""

        districts = pd.read_csv('data/districts.csv')
        commissioners = pd.read_csv('data/commissioners.csv')
        people = pd.read_csv('data/people.csv')

        dc = pd.merge(districts, commissioners, how='left', on='smd')
        dcp = pd.merge(dc, people, how='left', on='person_id')

        dcp['full_name'] = dcp['full_name'].fillna('(vacant)')

        district_list = '<ul>'

        for idx, district_row in dcp.iterrows():

            smd_id = district_row['smd']
            smd_display = smd_id.replace('smd_','')

            if district_row['full_name'] == '(vacant)':
                commmissioner_name = '(vacant)'            
            else:
                commmissioner_name = 'Commissioner ' + district_row['full_name']

            district_list += f'<li><a href="districts/{smd_display}.html">{smd_display}: {commmissioner_name}</a></li>'


        district_list += '</ul>'

        return district_list


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

        output = output.replace('REPLACE_WITH_DISTRICT_LIST', self.build_district_list())

        soup = BeautifulSoup(output, 'html.parser')
        output_pretty = soup.prettify()

        with open('docs/index.html', 'w') as f:
            f.write(output_pretty)

        print('Index built.')
