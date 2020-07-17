"""
Build Single Member District pages
"""

import numpy as np
import pandas as pd
from tqdm import tqdm
from bs4 import BeautifulSoup

from scripts.common import build_district_list, build_data_table, build_footer


class BuildDistricts():

    def __init__(self):
        pass

    def build_commissioner_table(self, smd_id):

        smd_display = smd_id.replace('smd_','')
        
        people = pd.read_csv('data/people.csv')
        commissioners = pd.read_csv('data/commissioners.csv')

        people_commissioners = pd.merge(people, commissioners, how='inner', on='person_id')
        
        current_commissioner = people_commissioners[people_commissioners['smd_id'] == smd_id]
        
        if len(current_commissioner) == 0:
            commissioner_table = '<p><em>Office is vacant.</em></p>'

        else:

            commissioner_table = """
                <table border="1">
                  <tbody>
                  """
            
            commissioner_table += """
                <tr>
                  <th>Name</th>
                  <td>{full_name}</td>
                </tr>
            """.format(full_name=current_commissioner['full_name'].values[0])
                
            commissioner_table += f"""
                <tr>
                  <th>Email</th>
                  <td><a href="mailto:{smd_display}@anc.dc.gov">{smd_display}@anc.dc.gov</a></td>
                </tr>
                """

            commissioner_table += """
                    </tbody>
                </table>
            """
        
        return commissioner_table


    def add_candidates(self, smd_id):
        """Add multiple candidates"""
        
        people = pd.read_csv('data/people.csv')
        candidates = pd.read_csv('data/candidates.csv')

        people_candidates = pd.merge(people, candidates, how='inner', on='person_id')
        
        # randomize the order of candidates
        current_candidates = people_candidates[people_candidates['smd_id'] == smd_id].sample(frac=1).reset_index()
        
        num_candidates = len(current_candidates)

        if num_candidates == 0:
            candidate_block = '<p><em>No known candidates.</em></p>'
            
        else:

            candidate_block = ''

            for idx, candidate_row in current_candidates.iterrows():

                # Add break between candidate tables if there is more than one candidate
                if idx > 0:
                    candidate_block += '<br/>'

                fields_to_try = [
                    'full_name'
                    , 'twitter_link'
                    , 'facebook_link'
                    , 'candidate_announced_date'
                    , 'candidate_source'
                    , 'candidate_source_link'
                    ]

                candidate_block += build_data_table(candidate_row, fields_to_try)
                

            if num_candidates > 1:
                candidate_block += '<p><em>Candidate order is randomized</em></p>'


        return candidate_block


    def build_district_table(self, smd_id):
        """Create HTML table for one district"""
        
        districts = pd.read_csv('data/districts.csv')

        district_row = districts[districts['smd_id'] == smd_id].squeeze().dropna()

        fields_to_try = ['description', 'landmarks', 'notes']

        district_table = build_data_table(district_row, fields_to_try)

        if any([(f in district_row.index) for f in fields_to_try]):

            district_table = """
                <table border="1">
                  <tbody>
                  """


            for field_name in fields_to_try:

                if field_name in district_row:

                    field_value = district_row[field_name]

                    if pd.notna(field_value):

                        district_table += f"""
                            <tr>
                              <th>{field_name}</th>
                              <td>{field_value}</td>
                            </tr>
                        """


            district_table += """
                    </tbody>
                </table>
            """

        else:
            district_table = ''
        
        return district_table






    def run(self):
        """Build pages for each SMD"""

        districts = pd.read_csv('data/districts.csv')
        map_colors = pd.read_csv('data/map_colors.csv')
        district_colors = pd.merge(districts, map_colors, how='inner', on='map_color_id')

        
        for idx, row in tqdm(district_colors.iterrows(), total=len(district_colors), desc='SMDs'):

            smd_id = row['smd_id']
            smd_display = smd_id.replace('smd_','')

            anc_id = row['anc_id']
            anc_display_upper = 'ANC' + anc_id
            anc_display_lower = anc_display_upper.lower()

            # if smd_id != 'smd_1C07':
            #     continue
                    
            with open('templates/smd.html', 'r') as f:
                output = f.read()
                
            output = output.replace('REPLACE_WITH_SMD', smd_display)
            
            output = output.replace('<!-- replace with commissioner table -->', self.build_commissioner_table(smd_id))
            output = output.replace('<!-- replace with candidate table -->', self.add_candidates(smd_id))
            output = output.replace('<!-- replace with better know a district -->', self.build_district_table(smd_id))

            neighbor_smd_ids = [('smd_' + d) for d in row['neighbor_smds'].split(', ')]
            output = output.replace('<!-- replace with neighbors -->', build_district_list(neighbor_smd_ids, level=2))


            output = output.replace('REPLACE_WITH_ANC_UPPER', anc_display_upper)
            output = output.replace('REPLACE_WITH_ANC_LOWER', anc_display_lower)

            output = output.replace('REPLACE_WITH_LONGITUDE', str(row['centroid_lon']))
            output = output.replace('REPLACE_WITH_LATITUDE', str(row['centroid_lat']))

            output = output.replace('REPLACE_WITH_COLOR', row['color_hex'])

            output = output.replace('<!-- replace with footer -->', build_footer())

            soup = BeautifulSoup(output, 'html.parser')
            output_pretty = soup.prettify()

            with open(f'docs/ancs/districts/{smd_display}.html', 'w') as f:
                f.write(output_pretty)



