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

            # Read HTML files as text
            if h.suffix == '.html':
                with h.open('r') as f:
                    html_text = f.read()
                link_source = h

            # Read CSV files with pandas, then output as text
            elif h.suffix == '.csv':
                temp_df = pd.read_csv(h)
                html_text = pd.DataFrame(temp_df['map_display_box']).to_string(index=False)

                # CSVs are being used by the Mapbox map, which is embedded in index.html
                link_source = Path(html_root / 'index.html')

            else:
                raise Exception(f'Unsupported file type: {h}')


            df_file = pd.DataFrame()
            soup = BeautifulSoup(html_text, features='html.parser')
            links = [link.get('href') for link in soup.find_all('a')]
            
            df_file['destination'] = links
            df_file['source'] = link_source
            
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

        print(f'Count of internal links: {len(self.link_df_local):,.0f}')

        print('Checking validity of each link')
        self.link_df_local['exists'] = self.link_df_local.apply(
            lambda x: (Path(x.source).parent / Path(x.destination_resolved)).exists(), axis=1
        )


        self.link_df_local['is_broken'] = (self.link_df_local.is_local) & ~(self.link_df_local.exists)

        self.link_df_local['source_filename'] = self.link_df_local.source.apply(lambda x: Path(x).name)

        link_problems = 0

        num_broken_links = self.link_df_local.is_broken.sum()
        link_problems += num_broken_links
        print(f'Number of broken links: {num_broken_links}')

        self.link_df_local[self.link_df_local.is_broken].to_csv('tests/results/broken_links.csv', index=False)
        
        if num_broken_links > 0:
            unique_bad_destinations = self.link_df_local[self.link_df_local.is_broken].destination_resolved.unique()
            print(f'Number of unique bad destinations: {len(unique_bad_destinations)}')
            
            unique_bad_sources = self.link_df_local[self.link_df_local.is_broken].source.unique()
            print(f'Number of unique bad sources: {len(unique_bad_sources)}')


        # Find orphan HTML pages, those not linked by anything else
        print('Checking for orphan pages')
        destination_unique = self.link_df_local.destination_resolved.unique()
        source_unique = self.link_df_local.source.unique()

        orphan_destinations = [x for x in destination_unique if x not in source_unique]

        # 404 page is an orphan on purpose - no pages should link to it
        orphan_sources = [x for x in source_unique if (x not in destination_unique)]

        # These pages don't have any links to them and that's OK
        orphan_whitelist = ['404.html', 'nav.html']
        for ow in orphan_whitelist:
            orphan_sources = [x for x in orphan_sources if ow not in str(x)]

        num_orphan_destinations = len(orphan_destinations)
        link_problems += num_orphan_destinations
        # todo: should be assert?
        print(f'Number of orphan destinations: {num_orphan_destinations}')

        with open('tests/results/orphan_destinations.txt', 'w') as f:
            for x in orphan_destinations:
                f.write(str(x) + '\n')


        num_orphan_sources = len(orphan_sources)
        link_problems += num_orphan_sources
        print(f'Number of orphan sources: {num_orphan_sources}')

        with open('tests/results/orphan_sources.txt', 'w') as f:
            for x in orphan_sources:
                f.write(str(x) + '\n')

        if link_problems > 0:
            print(f'Link problems to resolve: {link_problems}. Opening folder with test results.')
            os.system('open tests/results')

