"""
-----------------------
Config File Instuctions
-----------------------

This file contains configuration variables for the entire OpenANC project. 

Any script can use these variables by calling `import config` then
referencing the variable, such as `config.current_redistricting_year`
"""


"""
current_election_year: This is the year when the current election is happening.

When you set this to a future election, it has the effect of hiding candidates from the lists
of SMDs (like on openanc.org/list.html). So if it's the year 2023 and this value is set to 2024,
no candidates are displayed on these lists because no candidates yet exist in the candidates.csv
table for the 2024 election.
"""
current_election_year = 2026


# This is the year when the current map was made
current_redistricting_year = 2022


# This is the local timezone for all time-related functions.
site_timezone = 'America/New_York'


"""
This is the current version of Mapbox GL JS the project uses.

In general, we want to use a really recent version, and we haven't seen any changes
to OpenANC functionality from changing versions,

For most recent version, see: https://docs.mapbox.com/mapbox-gl-js/guides/
"""
mapbox_gl_js_version = 'v2.15.0'