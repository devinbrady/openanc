"""
Scripts for handling URLs within the OpenANC project
"""


def generate_url(district_id, link_source='root'):
    """
    Return a relative link to a given smd_id, anc_id, or ward_id's page from a source page
    """

    if 'smd_' in district_id:
        destination = 'district'
    elif 'anc_' in district_id:
        destination = 'anc'
    elif 'ward_' in district_id:
        destination = 'ward'
    else: # person_id
        destination = 'person'

    if '2022' in district_id:
        redistricting_year = 2022
    else:
        redistricting_year = 2012

    if destination == 'person':
        link_slug = format_name_for_url_from_person_id(district_id)
    else:
        link_slug = district_slug(district_id)

    return (
        relative_link_prefix(source=link_source, destination=destination, redistricting_year=redistricting_year)
        + link_slug
        + '.html'
        )


# should be generate_link, make it work for all destinations
def district_link(smd_id, smd_name, link_source='root', show_redistricting_cycle=False, redistricting_cycle=None):
    """Return an HTML link for one district page"""

    if show_redistricting_cycle:
        redistricting_string = f'[{redistricting_cycle} Cycle] '
    else:
        redistricting_string = ''

    link_body = f'{redistricting_string}{smd_name}'

    link_text = f'<a href="{generate_url(smd_id, link_source=link_source)}">{link_body}</a>'

    return link_text



def relative_link_prefix(source, destination, redistricting_year='xxxx'):
    """
    Returns the first part of the URL

    For instance:
    relative_link_prefix()['anc']['person'] : use this when linking to a person page from an ANC page
    relative_link_prefix()['person']['district'] : use this when linking to a district page from a person page
    """

    link_prefix = 'xxxx'

    if source == 'root':
        if destination == 'root':
            link_prefix = ''
        elif destination == 'anc':
            link_prefix = f'map_{redistricting_year}/ancs/'
        elif destination == 'ward':
            link_prefix = f'map_{redistricting_year}/wards/'
        elif destination == 'district':
            link_prefix = f'map_{redistricting_year}/ancs/districts/'
        elif destination == 'person':
            link_prefix = 'people/'

    elif source == 'anc':
        if destination == 'root':
            link_prefix = '../../'
        elif destination == 'district':
            link_prefix = f'../../map_{redistricting_year}/ancs/districts/'
        elif destination == 'person':
            link_prefix = '../../people/'

    elif source == 'ward':
        if destination == 'root':
            link_prefix = '../../'
        elif destination == 'district':
            link_prefix = f'../../map_{redistricting_year}/ancs/districts/'
        elif destination == 'person':
            link_prefix = '../../people/'

    elif source == 'district':
        if destination == 'root':
            link_prefix = '../../../'
        elif destination == 'ward':
            link_prefix = f'../map_{redistricting_year}/wards/'
        elif destination == 'anc':
            link_prefix = f'../../map_{redistricting_year}/ancs/'
        elif destination == 'district':
            link_prefix = f'../../../map_{redistricting_year}/ancs/districts/'
        elif destination == 'person':
            link_prefix = '../../../people/'

    elif source == 'person':
        if destination == 'root':
            link_prefix = '../'
        elif destination == 'district':
            link_prefix = f'../map_{redistricting_year}/ancs/districts/'
        elif destination == 'person':
            link_prefix = ''

    elif source == 'absolute':
        if destination == 'root':
            link_prefix = 'https://openanc.org/'
        elif destination == 'district':
            link_prefix = f'https://openanc.org/map_{redistricting_year}/ancs/districts/'
        elif destination == 'person':
            link_prefix = 'https://openanc.org/people/'


    """
    If 'xxxx' is in the link_prefix, this means that the source-destination combination has not been defined yet,
    or that a redistricting_year needed to be supplied but was not. 
    """
    if 'xxxx' in link_prefix:
        raise ValueError(
            'Link prefix not yet implemented for this combination. '
            + f'source: {source}, destination: {destination}, redistricting_year: {redistricting_year}'
            )

    return link_prefix



def district_slug(smd_id):
    """
    Generate the final part of a district URL, that will go before the '.html'
    """

    items_to_strip_out = ['2022', 'smd', 'anc', 'ward', '_', '/']

    district_slug = smd_id
    for i in items_to_strip_out:
        district_slug = district_slug.replace(i, '')

    return district_slug



def format_name_for_url_from_person_id(person_id):

    people = pd.read_csv('data/people.csv')

    person_name = people[people.person_id == person_id].full_name.iloc[0]

    return format_name_for_url(person_name)


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

