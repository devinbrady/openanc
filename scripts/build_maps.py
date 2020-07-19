"""
Build Maps pages
"""

import pandas as pd
from bs4 import BeautifulSoup

from scripts.common import build_district_list, build_footer, list_of_smds_without_candidates


class BuildMaps():


    def run(self):
        """Add information to maps page"""

        with open('templates/needs-candidates.html', 'r') as f:
            output = f.read()

        output = output.replace('REPLACE_WITH_NEEDS_CANDIDATES_LIST', build_district_list(smd_id_list=list_of_smds_without_candidates(), level=0))

        output = output.replace('<!-- replace with footer -->', build_footer())

        # soup = BeautifulSoup(output, 'html.parser')
        # output_pretty = soup.prettify()

        with open('docs/needs-candidates.html', 'w') as f:
            f.write(output)

        print('Map built.')
