"""
Build Ward pages
"""

import numpy as np
import pandas as pd
from tqdm import tqdm
from bs4 import BeautifulSoup

from scripts.common import (
    build_anc_html_table
    , anc_names
    , build_data_table
    , build_smd_html_table
    , add_footer
    , calculate_zoom
    , add_google_analytics
    )


class BuildWards():


    def run(self):
        """Build pages for each ANC"""

        ancs = pd.read_csv('data/ancs.csv')
        districts = pd.read_csv('data/districts.csv')

        wards = sorted(districts['ward'].unique())
        
        for ward in tqdm(wards, total=len(wards), desc='Wards'):
                    
            with open('templates/ward.html', 'r') as f:
                output = f.read()
            
            output = add_google_analytics(output)
            
            output = output.replace('REPLACE_WITH_WARD', str(ward))
            
            ward_smd_ids = districts[districts['ward'] == ward]['smd_id'].to_list()
            output = output.replace(
                '<!-- replace with district list -->'
                , build_smd_html_table(ward_smd_ids, link_path='../ancs/districts/')
                )


            if ward in (3,4):
                output = output.replace(
                    '<!-- replace with 3/4 info -->'
                    , '<p>Note that the Single Member Districts 3G01, 3G02, 3G03, and 3G04 are a part of ANC 3G but located in Ward 4.</p>'
                    )
            
            output = output.replace('REPLACE_WITH_LONGITUDE', '-77.03412954884507')
            output = output.replace('REPLACE_WITH_LATITUDE', '38.9361129455516')
            output = output.replace('REPLACE_WITH_ZOOM_LEVEL', '11')

            output = add_footer(output, level=1)

            with open(f'docs/wards/ward{ward}.html', 'w') as f:
                f.write(output)
