
import pytz
import pandas as pd
from datetime import datetime


def build_district_list(smd_id_list=None, level=0):
    """
    Bulleted list of districts and current commmissioners

    If smd_id_list is None, all districts are returned
    If smd_id_list is a list, those SMDs are returned

    level: 
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
        """
            
        output_table = """
            <table border="1">
              <tbody>
              """

        for field_name in fields_to_try:

            if field_name in row:

                field_value = row[field_name]

                output_table += f"""
                    <tr>
                    <th>{field_name}</th>
                    """

                if '_link' in field_name:
                    output_table += f'<td><a href="{field_value}">{field_value}</a></td>'
                else:
                    output_table += f'<td>{field_value}</td>'
                
                output_table += '</tr>'


        output_table += """
                </tbody>
            </table>
        """
        
        return output_table



def current_time():
    """
    Return current time in DC
    """

    tz = pytz.timezone('America/New_York')
    dc_now = datetime.now(tz)
    dc_timestamp = dc_now.strftime("%B %-d, %Y %-I:%M %p")

    return dc_timestamp


def build_footer():

    with open('templates/footer.html', 'r') as f:
        footer_html = f.read()

    footer_html = footer_html.replace('REPLACE_WITH_UPDATED_AT', current_time())

    return footer_html
