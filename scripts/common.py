
import pytz
import hashlib
import numpy as np
import pandas as pd
import geopandas as gpd
from datetime import datetime

from fuzzywuzzy import fuzz
from fuzzywuzzy import process


from scripts.data_transformations import (
    list_commissioners
    , list_candidates
    , people_dataframe
    , districts_candidates_commissioners
    )

from scripts.urls import (
    generate_link
    , relative_link_prefix
    )

CURRENT_ELECTION_YEAR = 2022
CURRENT_REDISTRICTING_YEAR = 2022

def smd_geojson():
    """Return a GeoDataFrame with SMDs from all redistricting cycles"""

    map_2012 = gpd.read_file('maps/smd-2012-preprocessed.geojson')
    map_2022 = gpd.read_file('maps/smd-2022-preprocessed.geojson')

    # Turn the 2012 MultiPolygons into Polygons to match 2022
    map_2012['geometry'] = map_2012.geometry.apply(lambda x: x.geoms[0])

    return gpd.GeoDataFrame(pd.concat([map_2012, map_2022]), crs=map_2012.crs)



def anc_geojson():
    """Return a GeoDataFrame with SMDs from all redistricting cycles"""

    map_2012 = gpd.read_file('maps/anc-2012.geojson')
    map_2022 = gpd.read_file('maps/anc-2022.geojson')

    # Turn the 2012 MultiPolygons into Polygons to match 2022
    map_2012['geometry'] = map_2012.geometry.apply(lambda x: x.geoms[0])

    return gpd.GeoDataFrame(pd.concat([map_2012, map_2022]), crs=map_2012.crs)



def ward_geojson():
    """Return a GeoDataFrame with wards from all redistricting cycles"""

    map_2012 = gpd.read_file('maps/ward-from-smd-2012.geojson')
    map_2022 = gpd.read_file('maps/ward-from-smd-2022.geojson')

    map_2012['geometry'] = map_2012.geometry.apply(lambda x: x.geoms[0])
    map_2022['geometry'] = map_2022.geometry.apply(lambda x: x.geoms[0])

    return gpd.GeoDataFrame(pd.concat([map_2012, map_2022]), crs=map_2012.crs)



def mapbox_slugs():
    """
    Return dict containing mapping of mapbox style id -> url slug
    """

    mb_styles = pd.read_csv('data/mapbox_styles.csv')
    mb_style_slugs = {}
    for idx, row in mb_styles.iterrows():
        mb_style_slugs[row['id']] = row['mapbox_link'][row['mapbox_link'].rfind('/')+1 :]

    return mb_style_slugs



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
    Add a GeoJSON feature as a Javascript variable to an HTML string. This variable will be used to calculate the bounds of the map.

    The shape is reduced to a 4-value bounding box to reduce the size of the HTML file. 
    """
    
    shape_row = shape_gdf[shape_gdf[field_name] == field_value].copy()

    # Calculate the bounds of this shape, which will determine the view window on this district's page
    bounds_df = shape_row.geometry.bounds.squeeze()
    geo_bounds = [[bounds_df.minx, bounds_df.maxx], [bounds_df.miny, bounds_df.maxy]]

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



def build_smd_html_table(list_of_smds, link_source=None, district_comm_commelect=pd.DataFrame(), candidate_statuses=pd.DataFrame()):
    """
    Return an HTML table with one row per district for a given list of SMDs

    Contains current commissioner and all candidates

    To speed up load times, the district_coom_commelection argument allows you to only load that DataFrame once,
    and pass it to this function multiple times. But if it isn't passed as an argument, this function will
    generate it.
    """

    if len(district_comm_commelect) == 0:
        district_comm_commelect = districts_candidates_commissioners(link_source=link_source)

    if len(candidate_statuses) == 0:
        candidate_statuses = pd.read_csv('data/candidate_statuses.csv')
    
    candidate_statuses = candidate_statuses.set_index('display_order').copy()
    
    display_df = district_comm_commelect[district_comm_commelect['smd_id'].isin(list_of_smds)].copy()

    display_df['SMD'] = display_df.apply(lambda x: generate_link(x.smd_id, link_source=link_source, link_body=x.smd_name), axis=1)

    status_columns = [c for c in display_df.columns if c.startswith('list_of_candidates_status_')]
    candidate_status_name_list = []
    for c in status_columns:
        status_id = int(c.replace('list_of_candidates_status_', ''))
        status_name = candidate_statuses.loc[status_id, 'candidate_status']
        candidate_status_name_list += [status_name]

        display_df[status_name] = display_df[c]


    display_df['Current Commissioner'] = display_df['current_commissioner']
    display_df['Candidates'] = display_df['list_of_candidate_links']
    display_df['Commissioner-Elect'] = display_df['commissioner_elect']

    columns_to_html = ['SMD', 'Election Year']

    display_df['Election Year'] = '2022'
    display_df.loc[display_df.redistricting_year == 2012, 'Election Year'] = '2020'

    # Display these columns if they are valid in this list of SMDs
    if any(display_df.redistricting_year == 2012):
        columns_to_html += ['Current Commissioner']

    if any(display_df.redistricting_year == 2022):
        columns_to_html += candidate_status_name_list

    if any(display_df.commissioner_elect.notnull()):
        columns_to_html += ['Commissioner-Elect']

    # Hash the first column and all column names. Used a CSS id for the resulting table.
    # First column + column names should change less frequently than the table contents.
    first_column_plus_column_names = ';'.join(list(display_df[columns_to_html[0]]) + columns_to_html)
    css_uuid = hashlib.sha224(first_column_plus_column_names.encode()).hexdigest() + '_'

    # The non-SMD columns should be formatted with left alignment
    subset_columns = [c for c in columns_to_html if c not in ('SMD', 'Election Year')]

    html = (
        display_df[columns_to_html]
        .fillna('')
        .style
        .set_properties(
            subset=subset_columns
            , **{'width': '230px', 'text-align': 'left'} # 230px fits the longest commissioner name on one row
            ) # why is the width in pixels so different between these columns? 
        .set_uuid(css_uuid)
        .hide(axis='index')
        .to_html()
        )

    return html



def build_district_list(smd_id_list=None, link_source='root', show_redistricting_cycle=False):
    """
    Bulleted list of districts and current commmissioners

    If smd_id_list is None, all districts are returned
    If smd_id_list is a list, those SMDs are returned

    If show_redistricting_cycle is True, then the year of the cycle will be displayed.
    """

    districts = pd.read_csv('data/districts.csv')
    commissioners = list_commissioners(status='current')
    people = people_dataframe()

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

        district_list += f'<li>{generate_link(smd_id, link_source=link_source, link_body=link_body)}</li>'


    district_list += '</ul>'

    return district_list




def build_data_table(row, fields_to_try, link_source='root'):
    """
    Create HTML table for one row of data

    If no fields are valid, returns empty string

    todo: rename this to be clearer
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

            if field_name in ['full_name', 'Name']:
                # Write link to person page for full name
                field_value = generate_link(row.person_name_id, link_source=link_source, link_body=row.full_name)
            else:
                field_value = row[field_name]


            # Convert timestamp to human-readable string
            if isinstance(field_value, datetime):
                field_value = field_value.strftime('%B %-d, %Y')

            if field_name[-3:] == '_at':
                field_value = pd.to_datetime(field_value).strftime('%B %-d, %Y')

            if pd.notna(field_value) and len(str(field_value)) > 0:

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



def current_timestamp():
    """Return current timestamp in DC, in datetime format"""

    tz = pytz.timezone('America/New_York')
    return datetime.now(tz)



def current_date_str():
    """Return current date in DC, formatted as a string for human readability"""

    return current_timestamp().strftime('%B %-d, %Y') # Hour of day: %-I:%M %p



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



def add_footer(input_html, link_source='root', updated_at=None):
    """
    Return HTML with footer included
    """

    with open('templates/footer.html', 'r') as f:
        footer_html = f.read()

    link_path = relative_link_prefix(source=link_source, destination='root')

    if not updated_at:
        updated_at = current_date_str()

    footer_html = footer_html.replace('REPLACE_WITH_LINK_PATH___', link_path)

    # footer_html = footer_html.replace('<!-- replace with edit items -->', edit_item_list())
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



