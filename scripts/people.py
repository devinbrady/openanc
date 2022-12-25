"""
Build People list and individual person pages
"""

import pandas as pd
from tqdm import tqdm
from nameparser import HumanName
from unidecode import unidecode
from string import ascii_uppercase


import config

from scripts.common import (
    add_footer
    , add_google_analytics
    , build_data_table
    , make_ordinal
)

from scripts.data_transformations import (
    list_commissioners
    , people_dataframe
    , results_candidate_people
    , incumbent_df
)


from scripts.urls import (
    generate_url
    , generate_link
    )



class BuildPeople():

    def __init__(self):

        self.commissioners = list_commissioners()
        self.people = people_dataframe()
        self.rcp = results_candidate_people()
        self.candidates = pd.read_csv('data/candidates.csv')

        # Only build person pages for people who have been candidates or commissioners
        all_person_ids = pd.concat([self.candidates.person_id, self.commissioners.person_id]).reset_index()
        valid_person_ids = sorted(all_person_ids.person_id.unique())
        self.people_valid = self.people[self.people.person_id.isin(valid_person_ids)].copy()

        self.districts = pd.read_csv('data/districts.csv')
        self.districts['smd_url'] = self.districts.apply(
            lambda x: generate_link(
                x.smd_id
                , link_source='person'
                , link_body=x.smd_name
                )
            , axis=1
            )

        self.comm_districts = pd.merge(self.commissioners, self.districts, how='inner', on='smd_id')
        self.people_comm = pd.merge(self.people, self.comm_districts, how='inner', on='person_id')

        self.rcp['ranking_ordinal'] = self.rcp['ranking'].apply(lambda x: make_ordinal(x))
        self.rcp['votes'] = self.rcp['votes'].apply(lambda x: '{:,.0f}'.format(x)).fillna('')

        self.candidates_districts = pd.merge(self.candidates, self.districts, how='inner', on='smd_id')
        self.candidates_districts_results = pd.merge(
            self.candidates_districts
            , self.rcp[['candidate_id', 'ranking_ordinal', 'votes']]
            , how='left'
            , on='candidate_id'
            )

        """
        During an election after redistricting, it's necessary to show whether current incumbents
        are running, and what district they're running in. 
        
        In other election years, it's not necessary to include the incumbents in the dataframe of candidates,
        since they are likely running in the district that they currently represent.
        """

        # incumbents = incumbent_df()
        # incumbents_not_candidates = incumbents[incumbents.reelection_status != 'Is Running'].copy()
        # incumbents_not_candidates['election_year'] = config.current_election_year
        # self.candidates_districts_results['reelection_status'] = None

        # self.candidates_districts_results_incumbents = pd.concat([
        #     self.candidates_districts_results
        #     , incumbents_not_candidates[['person_id', 'election_year', 'reelection_status']]
        #     ], ignore_index=True
        #     )

        self.candidates_districts_results_incumbents = self.candidates_districts_results.copy()



    def people_list_page(self):
        """
        Build People List page
        """

        with open('templates/people_list.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)

        output = output.replace('REPLACE_WITH_PEOPLE_LIST', self.list_of_people())

        output = add_footer(output, link_source='person')

        with open('docs/people/index.html', 'w') as f:
            f.write(output)

        print('built: people index.html')



    def list_of_people(self):
        """
        Build HTML list containing each person
        """

        self.people_valid['last_name'] = self.people_valid.full_name.apply(lambda x: HumanName(x).last)
        self.people_valid['not_last_name'] = self.people_valid.apply(lambda x: x.full_name.replace(x.last_name, '').strip(), axis=1)
        self.people_valid['last_first_name'] = self.people_valid.last_name + ', ' + self.people_valid.not_last_name
        self.people_valid = self.people_valid.sort_values(by='last_first_name')

        """
        In the event that we have people whose first letters of their last name contain an accent, this line removes the accent
        for the purpose of putting them into a letter section. when this case actually comes up, maybe ask the person how they prefer
        their last name to be alphabetized.
        """
        self.people_valid['last_name_first_letter'] = self.people_valid.last_name.apply(lambda x: unidecode(x.upper()[0]))

        # html = '<h4 id="last_name_top"></h4>'
        html = ''

        for i, letter in enumerate(ascii_uppercase):
            if i != 0:
                html += ' — '

            html += f'<a href="#last_name_{letter}">{letter}</a>'

        for letter in ascii_uppercase:

            # html += f'<h3 id="last_name_{letter}">{letter} (<a href="#last_name_top">top</a>)</h3>'
            html += f'<h3 id="last_name_{letter}">{letter}</h3>'

            people_in_letter = self.people_valid[self.people_valid.last_name_first_letter == letter].copy()

            if len(people_in_letter) > 0:
                
                html += '<ul>'

                for _, person in people_in_letter.iterrows():

                    html += '<li>' + generate_link(person.person_name_id, link_source='person', link_body=person.last_first_name) + '</li>'

                html += '</ul>'

        return html



    def build_all_person_pages(self):
        """
        Loop through all people and build a page for each
        """

        for _, person in tqdm(self.people_valid.iterrows(), total=len(self.people_valid), desc='People '):

            # debug
            # if person.person_id != 10380:
            #     continue

            self.build_person_page(person)



    def build_person_page(self, person):
        """
        Build a page for one person
        """

        with open('templates/person.html', 'r') as f:
            output = f.read()

        output = add_google_analytics(output)
        output = output.replace('REPLACE_WITH_PERSON_FULL_NAME', person.full_name)

        # Determine if this person has run for office or served as a commissioner
        person_districts = self.people_comm.loc[self.people_comm.person_id == person.person_id].copy()
        person_candidacies = self.candidates_districts_results_incumbents.loc[self.candidates_districts_results_incumbents.person_id == person.person_id].copy()
        person_candidacies.sort_values(by='election_year', ascending=False, inplace=True)

        # Only add the link for people with active candidacy, currently serving as commissioner, or will serve as commissioner in the future
        if (
                (person_districts['is_current'].sum() > 0)
                or (person_districts['is_future'].sum() > 0)
                or ((person_candidacies.election_year == config.current_election_year).sum() > 0)
            ):

            link_table = build_data_table(person, ['website_link', 'twitter_link', 'facebook_link'])
            if link_table != '':
                link_table = '<h2>Links</h2><ul>' + link_table + '</ul>'
            output = output.replace('<!-- replace with person links -->', link_table)
        

        if len(person_districts) > 0:
            district_block = '<h2>Districts Represented</h2><ul>'

            for idx, pd in person_districts.reset_index().iterrows():
                
                # Add break between commission tables if there is more than one commission
                if idx > 0:
                    district_block += '<br/>'

                district_block += build_data_table(pd, ['smd_url', 'term_in_office'], link_source='person')

            district_block += '</ul>'

            output = output.replace('<!-- replace with districts represented -->', district_block)


        if len(person_candidacies) > 0:
            candidacies_block = '<h2>Candidacies</h2><ul>'

            for idx, pd in person_candidacies.reset_index().iterrows():

                # Add break between candidate tables if there is more than one candidacy
                if idx > 0:
                    candidacies_block += '<br/>'

                candidacies_block += build_data_table(pd, ['election_year', 'smd_url', 'votes', 'ranking_ordinal', 'candidate_status', 'reelection_status'], link_source='person')

            candidacies_block += '</ul>'

            output = output.replace('<!-- replace with candidacies -->', candidacies_block)
            

        output = add_footer(output, link_source='person')

        with open('docs/' + generate_url(person.person_name_id, link_source='root'), 'w') as f:
            f.write(output)



    def run(self):

        self.people_list_page()
        self.build_all_person_pages()

