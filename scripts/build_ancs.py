"""
Build ANC pages
"""

import numpy as np
import pandas as pd
from tqdm import tqdm
from bs4 import BeautifulSoup

from scripts.common import build_district_list, build_data_table, build_footer, calculate_zoom


class BuildANCs():

    def __init__(self):
        pass


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
                
            output = output.replace('REPLACE_WITH_ANC', anc_display)
            
            anc_smd_ids = districts[districts['anc_id'] == anc_id]['smd_id'].to_list()
            output = output.replace('<!-- replace with district list -->', build_district_list(anc_smd_ids, level=1))

            fields_to_try = ['dc_oanc_link', 'anc_homepage_link', 'twitter_link']
            output = output.replace('<!-- replace with anc link list -->', build_data_table(row, fields_to_try))

            
            output = output.replace('REPLACE_WITH_LONGITUDE', str(row['centroid_lon']))
            output = output.replace('REPLACE_WITH_LATITUDE', str(row['centroid_lat']))
            output = output.replace('REPLACE_WITH_ZOOM_LEVEL', str(calculate_zoom(row['area'])))

            output = output.replace('<!-- replace with footer -->', build_footer())

            soup = BeautifulSoup(output, 'html.parser')
            output_pretty = soup.prettify()

            with open(f'docs/ancs/{anc_display_lower}.html', 'w') as f:
                f.write(output_pretty)
