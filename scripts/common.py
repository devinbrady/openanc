
import sys
import pytz
import hashlib
import numpy as np
import pandas as pd
import geopandas as gpd
from datetime import datetime

from fuzzywuzzy import fuzz
from fuzzywuzzy import process


# The redistricting cycle of the current serving commissioners
# CURRENT_REDISTRICTING_CYCLE = '2012'


def smd_geojson():
    """Return a GeoDataFrame with SMDs from all redistricting cycles"""

    map_2012 = gpd.read_file('maps/smd-2012-preprocessed.geojson')
    map_2022 = gpd.read_file('maps/smd-2022-preprocessed.geojson')

    # Turn the 2012 MultiPolygons into Polygons to match 2022
    map_2012['geometry'] = map_2012.geometry.apply(lambda x: x[0])

    return gpd.GeoDataFrame(pd.concat([map_2012, map_2022]), crs=map_2012.crs)



def anc_geojson():
    """Return a GeoDataFrame with SMDs from all redistricting cycles"""

    map_2012 = gpd.read_file('maps/anc-2012.geojson')
    map_2022 = gpd.read_file('maps/anc-2022.geojson')

    # Turn the 2012 MultiPolygons into Polygons to match 2022
    map_2012['geometry'] = map_2012.geometry.apply(lambda x: x[0])

    return gpd.GeoDataFrame(pd.concat([map_2012, map_2022]), crs=map_2012.crs)



def people_dataframe():
    """Return dataframe of people.csv with the name URLs added."""

    people = pd.read_csv('data/people.csv')
    people['name_url'] = people.full_name.apply(lambda x: format_name_for_url(x))

    return people



def format_name_for_url(name):
    """
    Strip out the non-ASCII characters from a person's full name to use as the URL.
    This is somewhat like Wikipedia's URL formatting but not exactly.

    Spaces become underscores, numbers and letters with accents are preserved as they are.
    """

    name_formatted = name.replace(' ', '_')

    characters_to_strip = ['"' , '(' , ')' , '.' , '-' , ',' , '\'']
    for c in characters_to_strip:
        name_formatted = name_formatted.replace(c, '')

    return name_formatted



def mapbox_slugs():
    """
    Return dict containing mapping of mapbox style id -> url slug
    """

    mb_styles = pd.read_csv('data/mapbox_styles.csv')
    mb_style_slugs = {}
    for idx, row in mb_styles.iterrows():
        mb_style_slugs[row['id']] = row['mapbox_link'][row['mapbox_link'].rfind('/')+1 :]

    return mb_style_slugs



def district_url(smd_id, level=0):
    """
    Generate a complete url for a smd_id

    link level, relative to where the source page is on the directory tree:
        -2: two levels up from the source page (like, from a district to a previous redistricting map)
        0: html root
        1: ANC page
        2: SMD page
    """

    if '2022' in smd_id:
        redistricting_year = '2022'
    else:
        redistricting_year = '2012'

    if level == -3:
        link_path = f'../../../map_{redistricting_year}/ancs/districts/'
    elif level == -2:
        link_path = f'../../map_{redistricting_year}/ancs/districts/'
    elif level == -1:
        link_path = f'../map_{redistricting_year}/ancs/districts/'
    elif level == 0:
        link_path = f'map_{redistricting_year}/ancs/districts/'
    elif level == 1:
        link_path = 'districts/'
    elif level == 2:
        link_path = ''
    elif level == 9:
        link_path = '../ancs/districts/'
    else:
        raise ValueError(f'Link level {level} is not implemented yet')

    return f'{link_path}{district_slug(smd_id)}.html' 



def anc_url(anc_id, level=0):
    """
    Generate a complete url for an anc_id

    link level, relative to where the source page is on the directory tree:
        -2: two levels up from the source page (like, from a district to a previous redistricting map)
        0: html root
        1: ANC page
        2: SMD page
    """

    if '2022' in anc_id:
        redistricting_year = '2022'
    else:
        redistricting_year = '2012'

    if level == -1:
        link_path = f'../ancs/'
    elif level == 0:
        link_path = f'map_{redistricting_year}/ancs/'
    else:
        raise ValueError(f'Link level {level} is not implemented yet')

    return f'{link_path}{district_slug(anc_id)}.html' 



def ward_url(ward_id, level=0):
    """
    Generate a complete url for an ward_id

    link level, relative to where the source page is on the directory tree:
        -2: two levels up from the source page (like, from a district to a previous redistricting map)
        0: html root
        1: ANC page
        2: SMD page
    """

    if '2022' in ward_id:
        redistricting_year = '2022'
    else:
        redistricting_year = '2012'

    if level == -1:
        link_path = f'../map_{redistricting_year}/wards/'
    elif level == 0:
        link_path = f'map_{redistricting_year}/wards/'
    else:
        raise ValueError(f'Link level {level} is not implemented yet')

    return f'{link_path}{district_slug(ward_id)}.html' 



def district_slug(smd_id):
    """
    Generate the final part of a district URL, that will go before the '.html'
    """

    items_to_strip_out = ['2022', 'smd', '_', '/']

    district_slug = smd_id
    for i in items_to_strip_out:
        district_slug = district_slug.replace(i, '')

    return district_slug



def edit_form_link(link_text='Submit edits'):
    """Return HTML for link to form for edits"""

    return f'<a href="https://docs.google.com/forms/d/e/1FAIpQLScw8EUGIOtUj994IYEM1W7PfBGV0anXjEmz_YKiKJc4fm-tTg/viewform">{link_text}</a>'



def candidate_form_link(link_text='Candidate Declaration Form', smd_id=None):
    """
    Link to form for candidates to declare themselves, can optionally also pre-fill the smd_id
    """

    link_destination = 'https://docs.google.com/forms/d/e/1FAIpQLSdt0eG_GnVSM5vqL4OHDFEMn6d2g_La8nj94pUswzt_uY1K-A/viewform'

    if smd_id:

        smd_id_form = smd_id.replace('smd_', '').replace('2022_', '')

        link_destination += f'?usp=pp_url&entry.1452324632=SMD+{smd_id_form}'


    return f'<a href="{link_destination}">{link_text}</a>'






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

    todo: this should be just a 4 value bounding box, easier to deal with and faster pages
    """
    
    shape_row = shape_gdf[shape_gdf[field_name] == field_value].copy()

    geo_bounds = shape_row.geometry.boundary.iloc[0].xy


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



def assemble_divo():
    """
    Return DataFrame with one row per SMD and various stats about each SMD's ranking

    divo = district-votes
    """

    results = pd.read_csv('data/results.csv')
    districts = pd.read_csv('data/districts.csv')

    votes_per_smd = pd.DataFrame(results.groupby('smd_id').votes.sum()).reset_index()

    # Calculate number of SMDs in each Ward and ANC
    smds_per_ward = pd.DataFrame(districts.groupby('ward_id').size(), columns=['smds_in_ward']).reset_index()
    smds_per_anc = pd.DataFrame(districts.groupby('anc_id').size(), columns=['smds_in_anc']).reset_index()

    divo = pd.merge(districts, votes_per_smd, how='inner', on='smd_id')
    divo = pd.merge(divo, smds_per_ward, how='inner', on='ward_id')
    divo = pd.merge(divo, smds_per_anc, how='inner', on='anc_id')
    divo['smds_in_dc'] = len(districts)

    # Rank each SMD by the number of votes recorded for ANC races within that SMD
    # method = min: assigns the lowest rank when multiple rows are tied
    divo['rank_dc'] = divo['votes'].rank(method='min', ascending=False)
    divo['rank_ward'] = divo.groupby('ward_id').votes.rank(method='min', ascending=False)
    divo['rank_anc'] = divo.groupby('anc_id').votes.rank(method='min', ascending=False)

    # Create strings showing the ranking of each SMD within its ANC, Ward, and DC-wide
    divo['string_dc'] = divo.apply(
        lambda row: f"{make_ordinal(row['rank_dc'])} out of {row['smds_in_dc']} SMDs", axis=1)

    divo['string_ward'] = divo.apply(
        lambda row: f"{make_ordinal(row['rank_ward'])} out of {row['smds_in_ward']} SMDs", axis=1)

    divo['string_anc'] = divo.apply(
        lambda row: f"{make_ordinal(row['rank_anc'])} out of {row['smds_in_anc']} SMDs", axis=1)


    average_votes_in_dc = divo.votes.mean()
    average_votes_by_ward = divo.groupby('ward_id').votes.mean()
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
        date_point = datetime.now(tz)

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



def build_smd_html_table(list_of_smds, level=0):
    """
    Return an HTML table with one row per district for a given list of SMDs

    Contains current commissioner and all candidates
    """

    district_comm_commelect = build_district_comm_commelect()
    
    display_df = district_comm_commelect[district_comm_commelect['smd_id'].isin(list_of_smds)].copy()

    display_df['SMD'] = display_df.apply(lambda x: 
        f'<a href="{district_url(x.smd_id, level=level)}">{x.smd_name}</a>'
        , axis=1
        )

    display_df['Current Commissioner'] = display_df['current_commissioner']

    columns_to_html = ['SMD', 'Current Commissioner']

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
            subset=['Current Commissioner']
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



def build_district_list(smd_id_list=None, level=0, show_redistricting_cycle=False):
    """
    Bulleted list of districts and current commmissioners

    If smd_id_list is None, all districts are returned
    If smd_id_list is a list, those SMDs are returned

    link level:
        0: html root
        1: ANC page
        2: SMD page

    If show_redistricting_cycle is True, then the year of the cycle will be displayed.
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

        if district_row['full_name'] == '(vacant)':
            if district_row['redistricting_year'] == 2022:
                commissioner_name = ''
            else:
                commissioner_name = ': (vacant)'
        else:
            commissioner_name = ': Commissioner ' + district_row['full_name']


        if show_redistricting_cycle:
            redistricting_string = f'[{district_row.redistricting_cycle} Cycle] '
        else:
            redistricting_string = ''


        link_body = f'{redistricting_string}{district_row.smd_name}{commissioner_name}'

        district_list += f'<li><a href="{district_url(smd_id, level)}">{link_body}</a></li>'


    district_list += '</ul>'

    return district_list



def district_link(smd_id, smd_name, redistricting_year, level=0, show_redistricting_cycle=False, redistricting_cycle=None):
    """Return an HTML link for one district page"""

    if show_redistricting_cycle:
        redistricting_string = f'[{redistricting_cycle} Cycle] '
    else:
        redistricting_string = ''

    link_body = f'{redistricting_string}{smd_name}'

    link_text = f'<a href="{district_url(smd_id, level)}">{link_body}</a>'

    return link_text




def build_data_table(row, fields_to_try, people_level=0):
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

                if field_name == 'full_name':
                    # Write link to person page for full name
                    if people_level == -3:
                        prefix = '../../../'
                    
                    field_value = f'<a href="{prefix}people/{row.name_url}.html">{row.full_name}</a>'
                else:
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
    Return current time in DC, formatted as a string for human readability
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
        1: one directory down, like ancs/map_2012/
        2: two directories down, like ancs/map_2012/districts/
    """

    with open('templates/footer.html', 'r') as f:
        footer_html = f.read()

    if level == 0:
        link_path = ''
    elif level == 1:
        link_path = '../'
    elif level == 2:
        link_path = '../../'
    elif level == 3:
        link_path = '../../../'

    if not updated_at:
        updated_at = current_time()

    footer_html = footer_html.replace('REPLACE_WITH_LINK_PATH___', link_path)

    footer_html = footer_html.replace('<!-- replace with edit items -->', edit_item_list())
    footer_html = footer_html.replace('REPLACE_WITH_UPDATED_AT', updated_at)

    output_html = input_html.replace('<!-- replace with footer -->', footer_html)

    return output_html


def edit_item_list():

    edit_items = f'<li>{candidate_form_link()}</li>'

    return edit_items


def hash_dataframe(df, columns_to_hash):
    """
    Given a DataFrame, hash certain columns

    df = pandas DataFrame
    columns_to_hash = a list containing the column names that should be hashed
    """

    hash_of_data = []

    for idx, row in df.iterrows():
        list_to_hash = row[columns_to_hash]
        string_to_hash = ','.join(list_to_hash)
        hash_of_data += [hashlib.sha224(string_to_hash.encode()).hexdigest()]

    return hash_of_data



def match_names(source_value, list_to_search, list_of_ids):
    """
    Take one name, compare to list of names, return the best match and the match score
    """

    matches = process.extract(source_value, list_to_search, scorer=fuzz.ratio, limit=1)

    best_id = list_of_ids[matches[0][2]]
    best_score = matches[0][1]

    return best_id, best_score

