"""
Test Links

Scan HTML files to confirm that all internal links are working.
"""


import os
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
from tqdm import tqdm


class TestLinks():

    def __init__(self):
        """
        Create DataFrame with every link in the project
        """

        here = Path.cwd()
        html_root = (here / 'docs/').resolve()
        html_files = sorted(list(html_root.rglob('*.html')))

        # Add the Mapbox CSVs to test their links as well
        html_files += [Path(html_root / '../uploads/to-mapbox-label-points-2012-data.csv').resolve()]
        html_files += [Path(html_root / '../uploads/to-mapbox-label-points-2022-data.csv').resolve()]


        self.link_df = pd.DataFrame()

        for h in tqdm(html_files, desc='Scanning HTML files'):

            with h.open('r') as f:
                html_text = f.read()

            df_file = pd.DataFrame()
            soup = BeautifulSoup(html_text, features='html.parser')
            links = [link.get('href') for link in soup.find_all('a')]
            
            df_file['destination'] = links
            df_file['source'] = h
            
            self.link_df = pd.concat([self.link_df, df_file], ignore_index=True)




        self.link_df['is_local'] = True
        self.link_df.loc[self.link_df.destination.str.contains('http'), 'is_local'] = False
        self.link_df_local = self.link_df[self.link_df.is_local].copy()


        # Resolve the destination of relative links
        self.link_df_local['destination_resolved'] = self.link_df_local.apply(
            lambda x: (x.source.parent / x.destination).resolve(), axis=1
        )


        # Total number of links
        # len(df_local)

        # Unique link destinations
        # len(df_local.destination.unique())

        # Unique link destinations
        # len(df_local.destination_resolved.unique())

        # Unique link sources
        # len(df_local.source.unique())



    def test_internal_links(self):
        """
        Make sure that every local link points to a file that exists under the HTML root
        """

        print('Checking validity of each link')
        self.link_df_local['exists'] = self.link_df_local.apply(
            lambda x: (Path(x.source).parent / Path(x.destination_resolved)).exists(), axis=1
        )


        self.link_df_local['is_broken'] = (self.link_df_local.is_local) & ~(self.link_df_local.exists)

        self.link_df_local['source_filename'] = self.link_df_local.source.apply(lambda x: Path(x).name)


        num_broken_links = self.link_df_local.is_broken.sum()
        print(f'Number of broken links: {num_broken_links}')

        if num_broken_links > 0:
            print('\nSources of broken links:')
            print(sorted(self.link_df_local[self.link_df_local.is_broken].source.unique().tolist()))

            print('\nDestinations of broken links:')
            print(sorted(self.link_df_local[self.link_df_local.is_broken].destination_resolved.unique().tolist()))



        # Find orphan HTML pages, those not linked by anything else
        # [x for x in self.link_df_local.destination_resolved.unique() if x not in self.link_df_local.source.unique()]



        # [x for x in self.link_df_local.source.unique() if x not in self.link_df_local.destination_resolved.unique()]

