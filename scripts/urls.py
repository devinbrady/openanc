

def district_link(smd_id, smd_name, link_source='root', show_redistricting_cycle=False, redistricting_cycle=None):
    """Return an HTML link for one district page"""

    if show_redistricting_cycle:
        redistricting_string = f'[{redistricting_cycle} Cycle] '
    else:
        redistricting_string = ''

    link_body = f'{redistricting_string}{smd_name}'

    link_text = f'<a href="{district_url(smd_id, link_source=link_source)}">{link_body}</a>'

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



def district_url(smd_id, link_source='root'):
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

    link_prefix = relative_link_prefix(
        source=link_source
        , destination='district'
        , redistricting_year=redistricting_year
        )

    # if level == -3:
    #     link_path = f'../../../map_{redistricting_year}/ancs/districts/'
    # elif level == -2:
    #     link_path = f'../../map_{redistricting_year}/ancs/districts/'
    # elif level == -1:
    #     link_path = f'../map_{redistricting_year}/ancs/districts/'
    # elif level == 0:
    #     link_path = f'map_{redistricting_year}/ancs/districts/'
    # elif level == 1:
    #     link_path = 'districts/'
    # elif level == 2:
    #     link_path = ''
    # elif level == 9:
    #     link_path = '../ancs/districts/'
    # else:
    #     raise ValueError(f'Link level {level} is not implemented yet')

    return f'{link_prefix}{district_slug(smd_id)}.html' 



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