"""
Build all pages
"""

import pandas as pd
from bs4 import BeautifulSoup


def build_index():
    """Add information to index page"""

    districts = pd.read_csv('data/districts.csv')
    commissioners = pd.read_csv('data/commissioners.csv')
    candidates = pd.read_csv('data/candidates.csv')

    district_candidates = pd.merge(districts, candidates, how='left', on='smd')

    no_candidate_districts = district_candidates[district_candidates['candidate_id'].isnull()]['smd'].nunique()

    with open('templates/index-template.html', 'r') as f:
        output = f.read()

    output = output.replace('NUMBER_OF_COMMISSIONERS', str(len(commissioners)))
    output = output.replace('NUMBER_OF_VACANCIES', str(296 - len(commissioners)))
    output = output.replace('NUMBER_OF_CANDIDATES', str(len(candidates)))
    output = output.replace('NUMBER_OF_NO_CANDIDATES', str(no_candidate_districts))

    output = output.replace('REPLACE_WITH_DISTRICT_LIST', build_district_list())

    soup = BeautifulSoup(output, 'html.parser')
    output_pretty = soup.prettify()

    with open('docs/index.html', 'w') as f:
        f.write(output_pretty)



def build_district_list():
    """Bulleted list of districts and current commmissioners"""

    districts = pd.read_csv('data/districts.csv')
    commissioners = pd.read_csv('data/commissioners.csv')

    do = pd.merge(districts, commissioners, how='left', on='smd')
    do['full_name'] = do['full_name'].fillna('(vacant)')

    district_list = '<ul>'

    for idx, d in do.iterrows():

        if d['full_name'] == '(vacant)':
            commmissioner_name = '(vacant)'            
        else:
            commmissioner_name = 'Commissioner ' + d['full_name']


        district_list += '<li><a href="districts/{smd}.html">{smd}: {officeholder}</a></li>'.format(
            smd=d['smd'].replace('smd_','')
            , officeholder=commmissioner_name
            )

    district_list += '</ul>'

    return district_list





def build_commissioner_table(smd_id):
    
    commissioners = pd.read_csv('data/commissioners.csv')
    
    current_commissioner = commissioners[commissioners['smd'] == smd_id]
    
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
              <td><a href="mailto:{smd_id}@anc.dc.gov">{smd_id}@anc.dc.gov</a></td>
            </tr>
            """

        commissioner_table += """
                </tbody>
            </table>
        """
    
    return commissioner_table


def add_candidates(smd_id):
    """Add multiple candidates"""
    
    candidates = pd.read_csv('data/candidates.csv')
    
    # randomize the order of candidates
    current_candidates = candidates[candidates['smd'] == smd_id].sample(frac=1)
    
    if len(current_candidates) == 0:
        candidate_block = '<p><em>No known candidates.</em></p>'
        
    else:

        candidate_block = ''

        for idx, candidate_row in current_candidates.iterrows():
            candidate_block += build_candidate_table(candidate_row)

    return candidate_block


def build_candidate_table(candidate_row):
    """Create HTML table for one candidate"""
        
    candidate_table = """
        <table border="1">
          <tbody>
          """

    if 'full_name' in candidate_row:
        candidate_table += """
            <tr>
              <th>Name</th>
              <td>{full_name}</td>
            </tr>
        """.format(full_name=candidate_row['full_name'])


    if 'candidacy_announced_date' in candidate_row:
        candidate_table += """
            <tr>
              <th>Announced</th>
              <td>{candidacy_announced_date}</td>
            </tr>
        """.format(candidacy_announced_date=candidate_row['candidacy_announced_date'])

        
    if 'candidacy_source' in candidate_row:
        candidate_table += """
            <tr>
              <th>Source</th>
              <td>{candidacy_source}</td>
            </tr>
        """.format(candidacy_source=candidate_row['candidacy_source'])


    candidate_table += """
            </tbody>
        </table>
        <br/>
    """
    
    return candidate_table




def build_district_pages():
    """Build pages for each SMD"""

    districts = pd.read_csv('data/districts.csv')
    
    map_colors = pd.read_csv('data/map_colors.csv')
    district_colors = pd.merge(districts, map_colors, how='inner', on='map_color_id')

    for idx, district in district_colors.iterrows():

        smd_id = district['smd']
        smd_display = smd_id.replace('smd_','')
                
        with open('templates/smd.html', 'r') as f:
            output = f.read()
            
        output = output.replace('REPLACE_WITH_SMD', smd_display)
        
        output = output.replace('<!-- replace with commissioner table -->', build_commissioner_table(smd_id))
        
        output = output.replace('<!-- replace with candidate table -->', add_candidates(smd_id))
        
        output = output.replace('REPLACE_WITH_ANC', district['anc'])
        output = output.replace('REPLACE_WITH_WARD', str(district['ward']))

        output = output.replace('REPLACE_WITH_LONGITUDE', str(district['centroid_lon']))
        output = output.replace('REPLACE_WITH_LATITUDE', str(district['centroid_lat']))

        output = output.replace('REPLACE_WITH_COLOR', district['color_hex'])

        soup = BeautifulSoup(output, 'html.parser')
        output_pretty = soup.prettify()

        with open(f'docs/districts/{smd_display}.html', 'w') as f:
            f.write(output_pretty)


if __name__ == '__main__':

    build_index()

    build_district_pages()
