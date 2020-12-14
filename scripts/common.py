
import sys
import pytz
import hashlib
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

    ancs = pd.read_csv('data/ancs.csv')

    anc_upper = 'ANC' + anc_id
    anc_lower = anc_upper.lower()

    anc_neighborhoods = ancs[ancs['anc_id'] == anc_id]['neighborhoods'].values[0]

    return anc_upper, anc_lower, anc_neighborhoods



def assemble_divo():
    """
    Return DataFrame with one row per SMD and various stats about each SMD's ranking

    divo = district-votes
    """

    results = pd.read_csv('data/results.csv')
    districts = pd.read_csv('data/districts.csv')

    votes_per_smd = pd.DataFrame(results.groupby('smd_id').votes.sum()).reset_index()

    # Calculate number of SMDs in each Ward and ANC
    smds_per_ward = pd.DataFrame(districts.groupby('ward').size(), columns=['smds_in_ward']).reset_index()
    smds_per_anc = pd.DataFrame(districts.groupby('anc_id').size(), columns=['smds_in_anc']).reset_index()

    divo = pd.merge(districts, votes_per_smd, how='inner', on='smd_id')
    divo = pd.merge(divo, smds_per_ward, how='inner', on='ward')
    divo = pd.merge(divo, smds_per_anc, how='inner', on='anc_id')
    divo['smds_in_dc'] = len(districts)

    # Rank each SMD by the number of votes recorded for ANC races within that SMD
    # method = min: assigns the lowest rank when multiple rows are tied
    divo['rank_dc'] = divo['votes'].rank(method='min', ascending=False)
    divo['rank_ward'] = divo.groupby('ward').votes.rank(method='min', ascending=False)
    divo['rank_anc'] = divo.groupby('anc_id').votes.rank(method='min', ascending=False)

    # Create strings showing the ranking of each SMD within its ANC, Ward, and DC-wide
    divo['string_dc'] = divo.apply(
        lambda row: f"{make_ordinal(row['rank_dc'])} out of {row['smds_in_dc']} SMDs", axis=1)

    divo['string_ward'] = divo.apply(
        lambda row: f"{make_ordinal(row['rank_ward'])} out of {row['smds_in_ward']} SMDs", axis=1)

    divo['string_anc'] = divo.apply(
        lambda row: f"{make_ordinal(row['rank_anc'])} out of {row['smds_in_anc']} SMDs", axis=1)


    average_votes_in_dc = divo.votes.mean()
    average_votes_by_ward = divo.groupby('ward').votes.mean()
    average_votes_by_anc = divo.groupby('anc_id').votes.mean()

    return divo



def list_commissioners(status=None, date_point=None):
    """
    Return dataframe with list of commissioners by status

    Options:
    status=None (all statuses returned) -- default
    status='former'
    status='current'
    status='future'

    date_point=None -- all statuses calculated from current DC time (default)
    date_point=(some other datetime) -- all statuses calculated from that datetime
    """

    commissioners = pd.read_csv('data/commissioners.csv')

    if not date_point:
        tz = pytz.timezone('America/New_York')
        dc_now = datetime.now(tz)
        date_point = dc_now

    commissioners['start_date'] = pd.to_datetime(commissioners['start_date']).dt.tz_localize(tz='America/New_York')
    commissioners['end_date'] = pd.to_datetime(commissioners['end_date']).dt.tz_localize(tz='America/New_York')

    # Create combined field with start and end dates, showing ambiguity
    commissioners['start_date_str'] = commissioners['start_date'].dt.strftime('%B %-d, %Y')
    commissioners['end_date_str'] = commissioners['end_date'].dt.strftime('%B %-d, %Y')

    # We don't have exact dates when these commissioners started, so show "circa 2019"
    commissioners.loc[commissioners['start_date_str'] == 'January 2, 2019', 'start_date_str'] = '~2019'

    # Combine start and end dates into one field
    commissioners['term_in_office'] = commissioners['start_date_str'] + ' to ' + commissioners['end_date_str']

    commissioners['is_former'] = commissioners.end_date < date_point
    commissioners['is_current'] = (commissioners.start_date < date_point) & (date_point < commissioners.end_date)
    commissioners['is_future'] = date_point < commissioners.start_date

    # Test here that there is, at most, one "Current" and one "Future" commissioner per SMD. 
    # Multiple "Former" commissioners is allowed
    smd_count = commissioners.groupby('smd_id')[['is_former', 'is_current', 'is_future']].sum().astype(int)
    # smd_count.to_csv('smd_commissioner_count.csv')
    
    if smd_count['is_current'].max() > 1 or smd_count['is_future'].max() > 1:
        raise Exception('Too many commissioners per SMD')

    if status:
        commissioner_output = commissioners[commissioners['is_' + status]].copy()
    else:
        commissioner_output = commissioners.copy()

    return commissioner_output



def build_results_candidate_people():
    """
    Return DataFrame containing results, candidates, and people joined
    """

    people = pd.read_csv('data/people.csv')
    candidates = pd.read_csv('data/candidates.csv')
    results = pd.read_csv('data/results.csv')

    results_candidates = pd.merge(
        results #[['candidate_id', 'person_id', 'smd_id']]
        , candidates #[['candidate_id']]
        , how='left'
        , on=['candidate_id', 'smd_id']
        )
    rcp = pd.merge(results_candidates, people, how='left', on='person_id') # results-candidates-people

    # Determine who were incumbent candidates at the time of the election
    election_date = datetime(2020, 11, 3, tzinfo=pytz.timezone('America/New_York'))
    commissioners = list_commissioners(status=None)
    incumbents = commissioners[(commissioners.start_date < election_date) & (election_date < commissioners.end_date)]
    incumbent_candidates = pd.merge(incumbents, candidates, how='inner', on='person_id')
    incumbent_candidates['is_incumbent'] = True

    rcp = pd.merge(rcp, incumbent_candidates[['candidate_id', 'is_incumbent']], how='left', on='candidate_id')
    rcp['is_incumbent'] = rcp['is_incumbent'].fillna(False)

    # Sort by SMD ascenting, Votes descending
    rcp = rcp.sort_values(by=['smd_id', 'votes'], ascending=[True, False])

    # Placeholder name for all write-in candidates. 
    # We do not know the combination of name and vote count for write-in candidates
    # We only know the name of the write-in winners
    rcp['full_name'] = rcp['full_name'].fillna('Write-ins combined')
    rcp['write_in_winner_int'] = rcp['write_in_winner'].astype(int)

    return rcp



def build_district_comm_commelect():
    """
    Build DataFrame showing commissioner and commissioner-elect for every district
    """

    districts = pd.read_csv('data/districts.csv')
    commissioners = list_commissioners(status=None)
    people = pd.read_csv('data/people.csv')

    cp = pd.merge(commissioners, people, how='inner', on='person_id')
    
    # left join to both current commissioners and commissioners-elect
    cp_current = pd.merge(districts, cp.loc[cp['is_current'], ['smd_id', 'person_id', 'full_name']], how='left', on='smd_id')
    cp_current = cp_current.rename(columns={'full_name': 'current_commissioner', 'person_id': 'current_person_id'})

    cp_current_future = pd.merge(cp_current, cp.loc[cp['is_future'], ['smd_id', 'person_id', 'full_name']], how='left', on='smd_id')
    cp_current_future = cp_current_future.rename(columns={'full_name': 'commissioner_elect', 'person_id': 'future_person_id'})

    # If there is not a current commissioner for the SMD, mark the row as "vacant"
    cp_current_future['current_commissioner'] = cp_current_future['current_commissioner'].fillna('(vacant)')

    return cp_current_future



def build_smd_html_table(list_of_smds, link_path=''):
    """
    Return an HTML table with one row per district for a given list of SMDs

    Contains current commissioner and all candidates with number of votes
    """

    rcp = build_results_candidate_people()

    # Bold the winners in this text field
    # results_field = 'Candidates and Results (Winner in Bold)'
    # rcp[results_field] = rcp.apply(
    #     lambda row:
    #         '<strong>{} ({:,.0f} votes)</strong>'.format(row['full_name'], row['votes'])
    #         if row['winner']
    #         else '{} ({:,.0f} votes)'.format(row['full_name'], row['votes'])
    #     , axis=1
    #     )

    results_field = 'Candidates and Results'
    rcp[results_field] = rcp.apply(
        lambda row: '{} ({:,.0f} votes)'.format(row['full_name'], row['votes'])
        , axis=1
        )

    # Aggregate results by SMD
    district_results = rcp.groupby('smd_id').agg({
        'votes': sum
        , results_field: lambda x: ', '.join(x)
        , 'write_in_winner_int': sum
        })

    total_votes_display_name = 'ANC Votes'
    district_results[total_votes_display_name] = district_results['votes']
    max_votes_for_bar_chart = district_results[total_votes_display_name].max()

    district_comm_commelect = build_district_comm_commelect()
    dcp_results = pd.merge(district_comm_commelect, district_results, how='left', on='smd_id')
    
    display_df = dcp_results[dcp_results['smd_id'].isin(list_of_smds)].copy()

    display_df['SMD'] = (
        f'<a href="{link_path}' + display_df['smd_id'].str.replace('smd_','').str.lower() + '.html">' 
        + display_df['smd_id'].str.replace('smd_','') + '</a>'
        )

    display_df['Current Commissioner'] = display_df['current_commissioner']
    display_df['Commissioner-Elect'] = display_df['commissioner_elect']

    # Append "write-in" to Commissioners-Elect who were write-in candidates
    display_df.loc[display_df['write_in_winner_int'] == 1, 'Commissioner-Elect'] = display_df.loc[display_df['write_in_winner_int'] == 1, 'Commissioner-Elect'] + ' (write-in)'

    columns_to_html = ['SMD', 'Current Commissioner', 'Commissioner-Elect'] #, total_votes_display_name, results_field]

    css_uuid = hashlib.sha224(display_df[columns_to_html].to_string().encode()).hexdigest() + '_'

    html = (
        display_df[columns_to_html]
        .fillna('')
        .style
        # .set_properties(
        #     subset=[results_field]
        #     , **{
        #         'text-align': 'left'
        #         , 'width': '700px'
        #         , 'height': '45px'
        #         }
        #     )
        # .set_properties(
        #     subset=[total_votes_display_name]
        #     , **{'text-align': 'left'}
        #     )
        .set_properties(
            subset=['Current Commissioner', 'Commissioner-Elect']
            , **{'width': '230px', 'text-align': 'left'} # 230px fits the longest commissioner name on one row
            ) # why is the width in pixels so different between these columns? 
        # .format({total_votes_display_name: '{:,.0f}'})
        # .bar(
        #     subset=[total_votes_display_name]
        #     , color='#cab2d6' # light purple
        #     , vmin=0
        #     , vmax=3116
        #     )
        .set_uuid(css_uuid)
        .hide_index()
        .render()
        )

    return html



def build_smd_html_table_candidates(list_of_smds, link_path=''):
    """
    Return an HTML table with one row per district for a given list of SMDs

    Contains current commissioner and all candidates by status
    """

    districts = pd.read_csv('data/districts.csv')
    commissioners = list_commissioners(status='current')
    people = pd.read_csv('data/people.csv')
    candidates = pd.read_csv('data/candidates.csv')
    candidate_statuses = pd.read_csv('data/candidate_statuses.csv')

    dc = pd.merge(districts, commissioners, how='left', on='smd_id')
    dcp = pd.merge(dc, people, how='left', on='person_id')

    cp = pd.merge(candidates, people, how='inner', on='person_id')
    cpd = pd.merge(cp, districts, how='inner', on='smd_id')
    cpds = pd.merge(cpd, candidate_statuses, how='inner', on='candidate_status')

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



    cpds['order_status'] = cpds['display_order'].astype(str) + ';' + cpds['candidate_status']

    candidates_in_smds = cpds[cpds['smd_id'].isin(list_of_smds)].copy()
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
        .set_uuid('smd_')
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
    commissioners = list_commissioners(status='current')
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

        th_class = 'attribute_heading'
        td_class = 'attribute_value'

        field_names = pd.read_csv('data/field_names.csv')
            
        output_table = """
            <table>
              <tbody>
              """

        fields_written = 0

        for field_name in fields_to_try:

            if field_name in row:

                field_value = row[field_name]

                # Convert timestamp to human-readable string
                if isinstance(field_value, datetime):
                    field_value = field_value.strftime('%B %-d, %Y')

                if pd.notna(field_value) and len(field_value) > 0:

                    # If no display_name has been defined for the field_name, use the field_name as the display_name
                    if sum(field_names['field_name'] == field_name) == 0:
                        display_name = field_name
                    else:
                        display_name = field_names.loc[field_names['field_name'] == field_name, 'display_name'].values[0]

                    output_table += f"""
                        <tr>
                        <th class="{th_class}">{display_name}</th>
                        """

                    if '_link' in field_name:
                        output_table += f'<td class="{td_class}"><a href="{field_value}">{field_value}</a></td>'
                    elif '_email' in field_name:
                        output_table += f'<td class="{td_class}"><a href="mailto:{field_value}">{field_value}</a></td>'
                    else:
                        output_table += f'<td class="{td_class}">{field_value}</td>'
                    
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



def build_link_block(row, fields_to_try):
    """
    Create HTML links in one block, intended to be one field within build_data_table()
    """

    field_names = pd.read_csv('data/field_names.csv')

    link_block = ''

    for field_name in fields_to_try:

        if pd.notnull(row[field_name]):

            if len(link_block) > 0:
                link_block += ' | '

            display_name = field_names.loc[field_names['field_name'] == field_name, 'display_name'].values[0]
            link_block += '<a href="{}">{}</a>'.format(row[field_name], display_name)


    return link_block



def calculate_zoom(area):
    # todo: remove this

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
    dc_timestamp = dc_now.strftime('%B %-d, %Y') # Hour of day: %-I:%M %p

    return dc_timestamp



def make_ordinal(n):
    """
    Convert an integer into its ordinal representation::

        make_ordinal(0)   => '0th'
        make_ordinal(3)   => '3rd'
        make_ordinal(122) => '122nd'
        make_ordinal(213) => '213th'

    Source: https://stackoverflow.com/a/50992575/3443926
    """

    n = int(n)
    suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    return str(n) + suffix



def add_footer(input_html, level=0, updated_at=None):
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

    if not updated_at:
        updated_at = current_time()

    footer_html = footer_html.replace('REPLACE_WITH_LINK_PATH___', link_path)

    footer_html = footer_html.replace('REPLACE_WITH_EDIT_LINK', edit_form_link('Submit edits'))
    footer_html = footer_html.replace('REPLACE_WITH_UPDATED_AT', updated_at)

    output_html = input_html.replace('<!-- replace with footer -->', footer_html)

    return output_html

