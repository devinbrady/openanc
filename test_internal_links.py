"""
Test Internal Links

Scan HTML files to confirm that all internal links are working.
"""


import os
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
from tqdm import tqdm


here = Path.cwd()
html_root = (here / 'docs/').resolve()
html_files = sorted(list(html_root.rglob('*.html')))

# Add the Mapbox CSVs to test their links as well
html_files += [Path(html_root / '../uploads/to-mapbox-label-points-2012-data.csv').resolve()]
html_files += [Path(html_root / '../uploads/to-mapbox-label-points-2022-data.csv').resolve()]


df = pd.DataFrame()

for h in tqdm(html_files, desc='Scanning HTML files'):

    with h.open('r') as f:
        html_text = f.read()

    df_file = pd.DataFrame()
    soup = BeautifulSoup(html_text, features='html.parser')
    links = [link.get('href') for link in soup.find_all('a')]
    
    df_file['destination'] = links
    df_file['source'] = h
    
    df = pd.concat([df, df_file], ignore_index=True)




df['is_local'] = True
df.loc[df.destination.str.contains('http'), 'is_local'] = False
df_local = df[df.is_local].copy()


# Resolve the destination of relative links
df_local['destination_resolved'] = df_local.apply(
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



print('Checking validity of each link')
df_local['exists'] = df_local.apply(
    lambda x: (Path(x.source).parent / Path(x.destination_resolved)).exists(), axis=1
)


df_local['is_broken'] = (df_local.is_local) & ~(df_local.exists)

df_local['source_filename'] = df_local.source.apply(lambda x: Path(x).name)


num_broken_links = df_local.is_broken.sum()
print(f'Number of broken links: {num_broken_links}')

if num_broken_links > 0:
    print('\nSources of broken links:')
    print(sorted(df_local[df_local.is_broken].source.unique().tolist()))

    print('\nDestinations of broken links:')
    print(sorted(df_local[df_local.is_broken].destination_resolved.unique().tolist()))



# Find orphan HTML pages, those not linked by anything else
# [x for x in df_local.destination_resolved.unique() if x not in df_local.source.unique()]



# [x for x in df_local.source.unique() if x not in df_local.destination_resolved.unique()]

