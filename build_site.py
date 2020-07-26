"""
All steps necessary to build OpenANC pages
"""

from scripts.refresh_data import RefreshData
from scripts.build_index import BuildIndex
from scripts.build_districts import BuildDistricts
from scripts.build_ancs import BuildANCs

# r = RefreshData()
# r.run()

# bi = BuildIndex()
# bi.run()

# ba = BuildANCs()
# ba.run()

bd = BuildDistricts()
bd.run()
