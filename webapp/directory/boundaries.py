"""Loads the whole-district/whole-ward/whole-ANC boundary geometries used on the detail page
maps, from the GeoJSON files in geo_data/ (sourced from ../maps/ in the main repo)."""
import json
from pathlib import Path

GEO_DIR = Path(__file__).resolve().parent / 'geo_data'

_FILES = {
    ('anc', 2012): 'anc-2012.geojson',
    ('anc', 2022): 'anc-2022.geojson',
    ('ward', 2012): 'ward-2012.geojson',
    ('ward', 2022): 'ward-2022.geojson',
    ('district', 2012): 'smd-2012-preprocessed.geojson',
    ('district', 2022): 'smd-2022-preprocessed.geojson',
}

# The id property in each file's features isn't always named after our model ('district' is
# called 'smd' in the source data).
_ID_PREFIX = {'anc': 'anc', 'ward': 'ward', 'district': 'smd'}

_cache = {}


def _load(kind, year):
    key = (kind, year)
    if key not in _cache:
        filename = _FILES.get(key)
        if filename is None:
            _cache[key] = {}
        else:
            with (GEO_DIR / filename).open() as f:
                data = json.load(f)
            if kind == 'ward':
                # The official ward files key features by their WARD number, not a ward_id.
                _cache[key] = {str(feature['properties']['WARD']): feature['geometry'] for feature in data['features']}
            else:
                id_field = f'{_ID_PREFIX[kind]}_id'
                _cache[key] = {feature['properties'].get(id_field): feature['geometry'] for feature in data['features']}
    return _cache[key]


def boundary_geometry(kind, designator, year):
    """kind is 'anc', 'ward', or 'district'; designator is the ANC/district designator (e.g.
    '1A', '1A01') or ward number (e.g. 6). Returns a GeoJSON geometry dict, or None if this
    boundary isn't available."""
    designator = str(designator)
    if year == 2012:
        # One known naming quirk in the 2012 source files: the ward-3/4-spanning ANC and its
        # districts are called "3G"/"3G01".."3G07" instead of "3/4G"/"3/4G01" etc.
        designator = designator.replace('3/4G', '3G')
    if kind == 'district' and year == 2022:
        # The 2022 SMD geometry file drops the "6/" ward prefix for the ward-6/8-spanning
        # districts (smd_id "smd_2022_8F01", not "smd_2022_6/8F01") -- a data quirk specific
        # to this file, distinct from the similar smd_id truncation in the Mapbox tileset.
        designator = designator.replace('6/8F', '8F')
    if kind == 'ward':
        return _load(kind, year).get(designator)
    prefix = _ID_PREFIX[kind]
    if year == 2012:
        feature_id = f'{prefix}_{designator}'
    elif kind == 'district':
        # Unlike anc_id/ward_id (designator, then year), smd_id puts the year first.
        feature_id = f'{prefix}_{year}_{designator}'
    else:
        feature_id = f'{prefix}_{designator}_{year}'
    return _load(kind, year).get(feature_id)
