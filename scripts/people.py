"""
Build People list and individual person pages
"""

import pandas as pd
from tqdm import tqdm
from nameparser import HumanName
from string import ascii_letters

from scripts.common import (
    add_footer
    , add_google_analytics
    , build_data_table
    , district_link
    , make_ordinal
)

from scripts.data_transformations import (
    list_commissioners
    , people_dataframe
    , results_candidate_people
)



class BuildPeople():

    def __init__(self):

        self.commissioners = list_commissioners()
        self.people = people_dataframe()
        self.rcp = results_candidate_people()

        self.districts = pd.read_csv('data/districts.csv')
        self.districts['smd_url'] = self.districts.apply(
            lambda x: district_link(
                x.smd_id
                , x.smd_name
                , x.redistricting_year
                , level=-1
                , show_redistricting_cycle=False
                )
            , axis=1
            )

        self.comm_districts = pd.merge(self.commissioners, self.districts, how='inner', on='smd_id')
        self.people_comm = pd.merge(self.people, self.comm_districts, how='inner', on='person_id')

        self.rcp['ranking_ordinal'] = self.rcp['ranking'].apply(lambda x: make_ordinal(x))
        self.rcp['votes'] = self.rcp['votes'].apply(lambda x: '{:,.0f}'.format(x)).fillna('')

        self.candidates = pd.read_csv('data/candidates.csv')
        self.cd = pd.merge(self.candidates, self.districts, how='inner', on='smd_id')
        self.hemispheres = pd.merge(
            self.cd
            , self.rcp[['candidate_id', 'ranking_ordinal', 'votes']]
            , how='left'
            , on='candidate_id'
            )


    def people_list_page(self):
        """
        Build People List page
        """

        with open('templates/people_list.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)

        output = output.replace('REPLACE_WITH_PEOPLE_LIST', self.list_of_people())

        output = add_footer(output, level=1)

        with open('docs/people/index.html', 'w') as f:
            f.write(output)

        print('built: people index.html')



    def list_of_people(self):
        """
        Build HTML list containing each person
        """

        self.people['last_name'] = self.people.full_name.apply(lambda x: HumanName(x).last)
        self.people['first_letter'] = self.people.last_name.str.upper().str[0]
        first_letter_list = sorted(self.people['first_letter'].unique())

        html = ''

        for letter in first_letter_list:

            html += f'<h3>{letter}</h3>'

            html += '<ul>'

            for idx, person in self.people[self.people.first_letter == letter].sort_values(by='full_name').iterrows():

                html += f'<li><a href="{person.name_url}.html">{person.full_name}</a></li>'

            html += '</ul>'

        return html



    def build_all_person_pages(self):
        """
        Loop through all people and build a page for each
        """

        for idx, person in tqdm(self.people.iterrows(), total=len(self.people), desc='People '):

            # debug
            # if person.person_id != 11362:
            #     continue

            self.build_person_page(person)



    def build_person_page(self, person):
        """
        Build a page for one person
        """

        with open('templates/person.html', 'r') as f:
            output = f.read()

        output = output.replace('REPLACE_WITH_PERSON_FULL_NAME', person.full_name)

        person_districts = self.people_comm.loc[self.people_comm.person_id == person.person_id].copy()

        if len(person_districts) > 0:
            district_block = '<h2>Districts Represented</h2><ul>'

            for idx, pd in person_districts.iterrows():
                district_block += build_data_table(pd, ['smd_url', 'term_in_office'])

            district_block += '</ul>'

            output = output.replace('<!-- replace with districts represented -->', district_block)


        person_candidacies = self.hemispheres.loc[self.hemispheres.person_id == person.person_id].copy()

        if len(person_candidacies) > 0:
            candidacies_block = '<h2>Candidacies</h2><ul>'

            for idx, pd in person_candidacies.reset_index().iterrows():

                # Add break between candidate tables if there is more than one candidate
                if idx > 0:
                    candidacies_block += '<br/>'

                candidacies_block += build_data_table(pd, ['election_year', 'smd_url', 'votes', 'ranking_ordinal'])



            candidacies_block += '</ul>'

            output = output.replace('<!-- replace with candidacies -->', candidacies_block)
            

        output = add_footer(output, level=1)

        with open(f'docs/people/{person.name_url}.html', 'w') as f:
            f.write(output)



    def run(self):

        self.people_list_page()
        self.build_all_person_pages()

