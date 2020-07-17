
import pandas as pd


def build_district_list(smd_id_list=None):
    """
    Bulleted list of districts and current commmissioners

    If smd_id_list is None, all districts are returned
    If smd_id_list is a list, those SMDs are returned
    """

    districts = pd.read_csv('data/districts.csv')
    commissioners = pd.read_csv('data/commissioners.csv')
    people = pd.read_csv('data/people.csv')

    dc = pd.merge(districts, commissioners, how='left', on='smd')
    dcp = pd.merge(dc, people, how='left', on='person_id')

    dcp['full_name'] = dcp['full_name'].fillna('(vacant)')

    if not smd_id_list:
        # List all SMDs by default
        smd_id_list = sorted(dcp['smd'].to_list())

    district_list = '<ul>'

    for idx, district_row in dcp[dcp['smd'].isin(smd_id_list)].iterrows():

        smd_id = district_row['smd']
        smd_display = smd_id.replace('smd_','')

        if district_row['full_name'] == '(vacant)':
            commmissioner_name = '(vacant)'            
        else:
            commmissioner_name = 'Commissioner ' + district_row['full_name']

        district_list += f'<li><a href="districts/{smd_display}.html">{smd_display}: {commmissioner_name}</a></li>'


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