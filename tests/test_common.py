
from scripts.common import *



def test_smd_geojson():
    """Confirm that SMD geojson contains all of the districts"""

    gdf = smd_geojson()
    assert len(gdf) == 641



def test_anc_geojson():
    """Confirm that ANC geojson contains all of the ANCs"""

    gdf = anc_geojson()
    assert len(gdf) == 86



def test_ward_geojson():
    """Confirm that Ward geojson contains all of the wards"""

    gdf = ward_geojson()
    assert len(gdf) == 16



# def test_mapbox_slugs():

#     ms = mapbox_slugs()
#     print(ms.keys())

#     assert True
