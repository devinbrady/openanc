"""
Build People list and individual person pages
"""

import pandas as pd
import urllib.parse

from scripts.common import (
    add_footer
    , add_google_analytics
)

from scripts.counts import Counts
from scripts.refresh_data import RefreshData


class BuildPeople():

    def __init__(self):
        pass



    def people_list_page(self):
        """
        Build People List page
        """

        with open('templates/people_list.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)

        output = output.replace('REPLACE_WITH_PEOPLE_LIST', self.list_of_people())

        output = add_footer(output, level=1)

        with open('docs/people/people_list.html', 'w') as f:
            f.write(output)

        print('built: people_list.html')



    def list_of_people(self):
        """
        Build HTML containing each person
        """

        people = pd.read_csv('data/people.csv')
        people = people.sort_values(by='full_name').copy()

        html = '<ul>'

        for p in people['full_name']:

            name_url = urllib.parse.quote(p)

            html += f'<li><a href="people/{name_url}.html">{p}</a> {name_url} </li>'

        html += '</ul>'

        return html



    def run(self):

        self.people_list_page()
