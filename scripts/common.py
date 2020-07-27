
import pytz
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
    

def dc_coordinates():
    """Return coordinates for a DC-wide map"""

    dc_longitude = -77.016243706276569
    dc_latitude = 38.894858329321485
    dc_zoom_level = 10.3

    return dc_longitude, dc_latitude, dc_zoom_level


def list_of_smds_without_candidates():
    """Return a list of SMDs that don't currently have a candidate"""

    districts = pd.read_csv('data/districts.csv')
    candidates = pd.read_csv('data/candidates.csv')

    district_candidates = pd.merge(districts, candidates, how='left', on='smd_id')

    no_candidate_districts = district_candidates[district_candidates['candidate_id'].isnull()]['smd_id'].unique().tolist()
    districts_with_candidates = district_candidates[district_candidates['candidate_id'].notnull()]['smd_id'].unique().tolist()

    return no_candidate_districts


def anc_names(anc_id):
    """
    Return formatted ANC names
    """

    anc_upper = 'ANC' + anc_id
    anc_lower = anc_upper.lower()

    return anc_upper, anc_lower


def build_anc_html_table(anc_id, level=0):
    """
    Return an HTML table with one row per district in an ANC

    Contains current commissioner and all candidates by status
    """

    anc_upper, anc_lower = anc_names(anc_id)

    ancs = pd.read_csv('data/ancs.csv')
    districts = pd.read_csv('data/districts.csv')
    commissioners = pd.read_csv('data/commissioners.csv')
    people = pd.read_csv('data/people.csv')
    candidates = pd.read_csv('data/candidates.csv')
    candidate_statuses = pd.read_csv('data/candidate_statuses.csv')

    dc = pd.merge(districts, commissioners, how='left', on='smd_id')
    dcp = pd.merge(dc, people, how='left', on='person_id')

    cp = pd.merge(candidates, people, how='inner', on='person_id')
    cpd = pd.merge(cp, districts, how='inner', on='smd_id')

    dcp['Current Commissioner'] = dcp['full_name'].fillna('(vacant)')

    anc_df = dcp[dcp['anc_id'] == anc_id].copy()

    # Construct link to SMD page
    if level == 0:
        link_path = 'ancs/districts/'
    elif level == 1:
        link_path = 'districts/'
    elif level == 2:
        link_path = ''

    anc_df['SMD'] = (
        f'<a href="{link_path}' + anc_df['smd_id'].str.replace('smd_','') + '.html">' 
        + anc_df['smd_id'].str.replace('smd_','') + '</a>'
        )

    columns_to_html = ['SMD', 'Current Commissioner']


    cpd['order_status'] = cpd['display_order'].astype(str) + ';' + cpd['candidate_status']

    candidates_in_anc = cpd[cpd['anc_id'] == anc_id].copy()
    statuses_in_anc = sorted(candidates_in_anc['order_status'].unique())
    
    for status in statuses_in_anc:

        status_name = status[status.find(';')+1:]
        columns_to_html += [status_name]
        
        cs_df = candidates_in_anc[candidates_in_anc['order_status'] == status][['smd_id', 'full_name']].copy()
        cs_smd = cs_df.groupby('smd_id').agg({'full_name': list}).reset_index()
        cs_smd[status_name] = cs_smd['full_name'].apply(lambda row: ', '.join(row))
        
        anc_df = pd.merge(anc_df, cs_smd, how='left', on='smd_id')            

    html = anc_df[columns_to_html].to_html(index=False, na_rep='', justify='left', escape=False)

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
    commissioners = pd.read_csv('data/commissioners.csv')
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

        district_list += f'<li><a href="{link_path}{smd_display}.html">{smd_display}: {commmissioner_name}</a></li>'


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


def build_footer():

    with open('templates/footer.html', 'r') as f:
        footer_html = f.read()

    footer_html = footer_html.replace('REPLACE_WITH_EDIT_LINK', edit_form_link('Submit edits'))
    footer_html = footer_html.replace('REPLACE_WITH_UPDATED_AT', current_time())

    return footer_html
