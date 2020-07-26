"""
Build ANC pages
"""

import numpy as np
import pandas as pd
from tqdm import tqdm
from bs4 import BeautifulSoup

from scripts.common import build_district_list, build_data_table, build_footer, calculate_zoom, google_analytics_block


class BuildANCs():


    def build_anc_dataframe(self, anc_id, level=0):

        anc_upper = 'ANC' + anc_id
        anc_lower = anc_upper.lower()

        ancs = pd.read_csv('data/ancs.csv')
        districts = pd.read_csv('data/districts.csv')
        commissioners = pd.read_csv('data/commissioners.csv')
        people = pd.read_csv('data/people.csv')
        candidates = pd.read_csv('data/candidates.csv')
        candidate_statuses = pd.read_csv('data/candidate_statuses.csv')

        dc = pd.merge(districts, commissioners, how='left', on='smd_id')
        dcp = pd.merge(dc, people, how='left', on='person_id')

        cp = pd.merge(candidates, people, how='inner', on='person_id')
        cpd = pd.merge(cp, districts, how='inner', on='smd_id')

        dcp['Current Commissioner'] = dcp['full_name'].fillna('(vacant)')

        anc_df = dcp[dcp['anc_id'] == anc_id].copy()

        # Construct link to SMD page
        if level == 0:
            link_path = 'ancs/districts/'
        elif level == 1:
            link_path = 'districts/'
        elif level == 2:
            link_path = ''

        anc_df['SMD'] = (
            f'<a href="{link_path}' + anc_df['smd_id'].str.replace('smd_','') + '.html">' 
            + anc_df['smd_id'].str.replace('smd_','') + '</a>'
            )

        columns_to_html = ['SMD', 'Current Commissioner']


        cpd['order_status'] = cpd['display_order'].astype(str) + ';' + cpd['candidate_status']

        candidates_in_anc = cpd[cpd['anc_id'] == anc_id].copy()
        statuses_in_anc = sorted(candidates_in_anc['order_status'].unique())
        
        for status in statuses_in_anc:

            status_name = status[status.find(';')+1:]
            columns_to_html += [status_name]
            
            cs_df = candidates_in_anc[candidates_in_anc['order_status'] == status][['smd_id', 'full_name']].copy()
            cs_smd = cs_df.groupby('smd_id').agg({'full_name': list}).reset_index()
            cs_smd[status_name] = cs_smd['full_name'].apply(lambda row: ', '.join(row))
            
            anc_df = pd.merge(anc_df, cs_smd, how='left', on='smd_id')            

        html = anc_df[columns_to_html].to_html(index=False, na_rep='', justify='left', escape=False)

        return html


    def run(self):
        """Build pages for each ANC"""

        ancs = pd.read_csv('data/ancs.csv')
        districts = pd.read_csv('data/districts.csv')

        
        for idx, row in tqdm(ancs.iterrows(), total=len(ancs), desc='ANCs'):

            anc_id = row['anc_id']
            anc_display = 'ANC' + anc_id
            anc_display_lower = anc_display.lower()
                    
            with open('templates/anc.html', 'r') as f:
                output = f.read()
            
            output = output.replace('<!-- replace with google analytics -->', google_analytics_block())
            
            output = output.replace('REPLACE_WITH_ANC', anc_display)
            
            anc_smd_ids = districts[districts['anc_id'] == anc_id]['smd_id'].to_list()
            output = output.replace('<!-- replace with district list -->', self.build_anc_dataframe(anc_id, level=1))

            fields_to_try = ['notes', 'dc_oanc_link', 'anc_homepage_link', 'twitter_link']
            output = output.replace('<!-- replace with anc link list -->', build_data_table(row, fields_to_try))

            
            output = output.replace('REPLACE_WITH_LONGITUDE', str(row['centroid_lon']))
            output = output.replace('REPLACE_WITH_LATITUDE', str(row['centroid_lat']))
            output = output.replace('REPLACE_WITH_ZOOM_LEVEL', str(calculate_zoom(row['area'])))

            output = output.replace('<!-- replace with footer -->', build_footer())

            # soup = BeautifulSoup(output, 'html.parser')
            # output_pretty = soup.prettify()

            with open(f'docs/ancs/{anc_display_lower}.html', 'w') as f:
                f.write(output)

