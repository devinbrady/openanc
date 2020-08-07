
import sys
import pytz
import numpy as np
import pandas as pd
from datetime import datetime



def edit_form_link(link_text='Submit edits'):
    """Return HTML for link to form for edits"""

    return f'<a href="https://docs.google.com/forms/d/e/1FAIpQLScw8EUGIOtUj994IYEM1W7PfBGV0anXjEmz_YKiKJc4fm-tTg/viewform">{link_text}</a>'



def add_google_analytics(input_html):
    """
    Return HTML with Google Analytics block added
    """

    ga_block = """
        <!-- Global site tag (gtag.js) - Google Analytics -->
        <script async src="https://www.googletagmanager.com/gtag/js?id=UA-173043454-1"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){dataLayer.push(arguments);}
          gtag('js', new Date());

          gtag('config', 'UA-173043454-1');
        </script>
        """

    output_html = input_html.replace('<!-- replace with google analytics -->', ga_block)

    return output_html



def add_geojson(shape_gdf, field_name, field_value, input_html):
    """
    Add a GeoJSON feature as a Javascript variable to an HTML string

    This variable will be used to calculate the bounds of the map
    """
    
    shape_row = shape_gdf[shape_gdf[field_name] == field_value].copy() 

    shape_geo = shape_row.geometry.iloc[0]
    
    geo_bounds = shape_geo.boundary[0].xy

    output_string = '[['

    for idx, value in enumerate(geo_bounds[0]):

        if idx > 0: 
            output_string += ','
        
        output_string += '['

        x = geo_bounds[0][idx]
        output_string += '{}'.format(x)

        y = geo_bounds[1][idx]
        output_string += ', {}'.format(y)

        output_string += ']\n'

    output_string += ']]'

    output_html = input_html.replace('REPLACE_WITH_XY', output_string)

    return output_html



def dc_coordinates():
    """Return coordinates for a DC-wide map"""

    dc_longitude = -77.016243706276569
    dc_latitude = 38.894858329321485
    dc_zoom_level = 10.3

    return dc_longitude, dc_latitude, dc_zoom_level



def anc_names(anc_id):
    """
    Return formatted ANC names
    """

    anc_upper = 'ANC' + anc_id
    anc_lower = anc_upper.lower()

    return anc_upper, anc_lower



def current_commissioners():
    """
    Return dataframe with only current commissioners (exclude former)
    """

    commissioners = pd.read_csv('data/commissioners.csv')
    return commissioners[commissioners['commissioner_status'] == 'current'].copy()



def build_smd_html_table(list_of_smds, link_path=''):
    """
    Return an HTML table with one row per district for a given list of SMDs

    Contains current commissioner and all candidates by status
    """

    districts = pd.read_csv('data/districts.csv')
    commissioners = current_commissioners()
    people = pd.read_csv('data/people.csv')
    candidates = pd.read_csv('data/candidates.csv')
    candidate_statuses = pd.read_csv('data/candidate_statuses.csv')

    dc = pd.merge(districts, commissioners, how='left', on='smd_id')
    dcp = pd.merge(dc, people, how='left', on='person_id')

    cp = pd.merge(candidates, people, how='inner', on='person_id')
    cpd = pd.merge(cp, districts, how='inner', on='smd_id')

    dcp['Current Commissioner'] = dcp['full_name'].fillna('(vacant)')

    display_df = dcp[dcp['smd_id'].isin(list_of_smds)].copy()


    display_df['SMD'] = (
        f'<a href="{link_path}' + display_df['smd_id'].str.replace('smd_','').str.lower() + '.html">' 
        + display_df['smd_id'].str.replace('smd_','') + '</a>'
        )


    # Number of candidates in each SMD
    # todo: make this a function
    cps = pd.merge(cp, candidate_statuses, how='inner', on='candidate_status')

    # Only include active candidates
    district_candidates = pd.merge(districts, cps[cps['count_as_candidate']].copy(), how='left', on='smd_id')

    candidate_count = pd.DataFrame(district_candidates.groupby('smd_id')['candidate_id'].count()).reset_index()
    candidate_count.rename(columns={'candidate_id': 'Number of Candidates'}, inplace=True)
    display_df = pd.merge(display_df, candidate_count, how='inner', on='smd_id')



    columns_to_html = ['SMD', 'Current Commissioner', 'Number of Candidates']



    cpd['order_status'] = cpd['display_order'].astype(str) + ';' + cpd['candidate_status']

    candidates_in_smds = cpd[cpd['smd_id'].isin(list_of_smds)].copy()
    statuses_in_smds = sorted(candidates_in_smds['order_status'].unique())
    
    for status in statuses_in_smds:

        status_name = status[status.find(';')+1:]
        columns_to_html += [status_name]
        
        cs_df = candidates_in_smds[candidates_in_smds['order_status'] == status][['smd_id', 'full_name']].copy()
        cs_smd = cs_df.groupby('smd_id').agg({'full_name': list}).reset_index()
        cs_smd[status_name] = cs_smd['full_name'].apply(lambda row: ', '.join(row))
        
        display_df = pd.merge(display_df, cs_smd, how='left', on='smd_id')            

    html = (
        display_df[columns_to_html]
        .fillna('')
        .style
        .set_properties(**{
            'border-color': 'black'
            , 'border-style': 'solid'
            , 'border-width': '1px'
            , 'text-align': 'center'
            , 'padding': '4px'
            })
        .hide_index()
        .render()
        )

    return html



def build_district_list(smd_id_list=None, level=0):
    """
    Bulleted list of districts and current commmissioners

    If smd_id_list is None, all districts are returned
    If smd_id_list is a list, those SMDs are returned

    link level: 
        0: homepage
        1: ANC page
        2: SMD page
    """

    districts = pd.read_csv('data/districts.csv')
    commissioners = current_commissioners()
    people = pd.read_csv('data/people.csv')

    dc = pd.merge(districts, commissioners, how='left', on='smd_id')
    dcp = pd.merge(dc, people, how='left', on='person_id')

    dcp['full_name'] = dcp['full_name'].fillna('(vacant)')

    if not smd_id_list:
        # List all SMDs by default
        smd_id_list = sorted(dcp['smd_id'].to_list())

    district_list = '<ul>'

    for idx, district_row in dcp[dcp['smd_id'].isin(smd_id_list)].iterrows():

        smd_id = district_row['smd_id']
        smd_display = smd_id.replace('smd_','')
        smd_display_lower = smd_display.lower()

        if district_row['full_name'] == '(vacant)':
            commmissioner_name = '(vacant)'
        else:
            commmissioner_name = 'Commissioner ' + district_row['full_name']

        if level == 0:
            link_path = 'ancs/districts/'
        elif level == 1:
            link_path = 'districts/'
        elif level == 2:
            link_path = ''

        district_list += f'<li><a href="{link_path}{smd_display_lower}.html">{smd_display}: {commmissioner_name}</a></li>'


    district_list += '</ul>'

    return district_list



def build_data_table(row, fields_to_try):
        """
        Create HTML table for one row of data

        If no fields are valid, returns empty string
        """

        field_names = pd.read_csv('data/field_names.csv')
            
        output_table = """
            <table border="1">
              <tbody>
              """

        fields_written = 0

        for field_name in fields_to_try:

            if field_name in row:

                field_value = row[field_name]

                if pd.notna(field_value):

                    display_name = field_names.loc[field_names['field_name'] == field_name, 'display_name'].values[0]
                    if pd.isnull(display_name):
                        display_name = field_name

                    output_table += f"""
                        <tr>
                        <th>{display_name}</th>
                        """

                    if '_link' in field_name:
                        output_table += f'<td><a href="{field_value}">{field_value}</a></td>'
                    elif '_email' in field_name:
                        output_table += f'<td><a href="mailto:{field_value}">{field_value}</a></td>'
                    else:
                        output_table += f'<td>{field_value}</td>'
                    
                    output_table += '</tr>'

                    fields_written += 1

        output_table += """
                </tbody>
            </table>
        """

        # or could use: if any([(f in row.index) for f in fields_to_try]):
        if fields_written == 0:
            output_table = ''
        
        return output_table



def calculate_zoom(area):

    slope = -0.0000004570057419
    intercept = 15.0255174

    zoom_level = (slope * area) + intercept

    return zoom_level



def current_time():
    """
    Return current time in DC
    """

    tz = pytz.timezone('America/New_York')
    dc_now = datetime.now(tz)
    dc_timestamp = dc_now.strftime("%B %-d, %Y") # Hour of day: %-I:%M %p

    return dc_timestamp



def add_footer(input_html, level=0):
    """
    Return HTML with footer included

    level for relative links: 
        0: same dir as homepage, index.html
        1: one directory down, like ancs/
        2: two directories down, like ancs/districts/
    """

    with open('templates/footer.html', 'r') as f:
        footer_html = f.read()


    if level == 0:
        link_path = ''
    elif level == 1:
        link_path = '../'
    elif level == 2:
        link_path = '../../'

    footer_html = footer_html.replace('REPLACE_WITH_LINK_PATH___', link_path)

    footer_html = footer_html.replace('REPLACE_WITH_EDIT_LINK', edit_form_link('Submit edits'))
    footer_html = footer_html.replace('REPLACE_WITH_UPDATED_AT', current_time())

    output_html = input_html.replace('<!-- replace with footer -->', footer_html)

    return output_html

