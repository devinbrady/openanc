"""
Build all district pages
"""

import pandas as pd
from bs4 import BeautifulSoup


def build_commissioner_table(smd):
    
    officeholders = pd.read_csv('data/officeholders.csv')
    
    current_officeholder = officeholders[officeholders['smd'] == smd]
    
    if len(current_officeholder) == 0:
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
        """.format(full_name=current_officeholder['full_name'].values[0])
            
        commissioner_table += f"""
            <tr>
              <th>Email</th>
              <td><a href="mailto:{smd}@anc.dc.gov">{smd}@anc.dc.gov</a></td>
            </tr>
            """

        commissioner_table += """
                </tbody>
            </table>
        """
    
    return commissioner_table


def add_candidates(smd):
    """Add multiple candidates"""
    
    candidates = pd.read_csv('data/candidates_dcboe.csv')
    candidates['source'] = 'DCBOE'
    
    # randomize the order of candidates
    current_candidates = candidates[candidates['smd'] == smd].sample(frac=1)
    
    if len(current_candidates) == 0:
        candidate_block = '<p><em>No known candidates.</em></p>'
        
    else:

        candidate_block = ''

        for idx, cand_row in current_candidates.iterrows():
            candidate_block += build_candidate_table(cand_row)

    return candidate_block


def build_candidate_table(cand_row):
    """Create HTML table for one candidate"""
        
    candidate_table = """
        <table border="1">
          <tbody>
          """

    if 'full_name' in cand_row:
        candidate_table += """
            <tr>
              <th>Name</th>
              <td>{full_name}</td>
            </tr>
        """.format(full_name=cand_row['full_name'])


    if 'pickup_date' in cand_row:
        candidate_table += """
            <tr>
              <th>Announced</th>
              <td>{pickup_date}</td>
            </tr>
        """.format(pickup_date=cand_row['pickup_date'])

        
    if 'source' in cand_row:
        candidate_table += """
            <tr>
              <th>Source</th>
              <td>{source}</td>
            </tr>
        """.format(source=cand_row['source'])


    candidate_table += """
            </tbody>
        </table>
        <br/>
    """
    
    return candidate_table


def build_district_pages():
    """Build pages for each SMD"""

    districts = pd.read_csv('data/districts.csv')

    for idx, district in districts.iterrows():
        
        if district['smd'] not in ('1A02', '1A06', '1B05'):
            continue
        
        with open('templates/smd.html') as f:
            output = f.read()
            
        output = output.replace('<!-- replace with smd -->', district['smd'])
        
        output = output.replace('<!-- replace with commissioner table -->', build_commissioner_table(district['smd']))
        
        output = output.replace('<!-- replace with candidate table -->', add_candidates(district['smd']))
        
        output = output.replace('REPLACE_WITH_ANC', district['anc'])
        output = output.replace('REPLACE_WITH_WARD', str(district['ward']))

        soup = BeautifulSoup(output, 'html.parser')
        output_pretty = soup.prettify()

        with open('docs/districts/{smd}.html'.format(smd=district['smd']), 'w') as f:
            f.write(output_pretty)


if __name__ == '__main__':

    build_district_pages()
    