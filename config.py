
"""
current_election_year: This is the year when the current election is happening.

When you set this to a future election, it has the effect of hiding candidates from the lists
of SMDs (like on openanc.org/index.html). So if it's the year 2023 and this value is set to 2024,
no candidates are displayed on these lists because no candidates yet exist in the candidates.csv
table for the 2024 election.
""" 
current_election_year = 2022


# This is the year when the current map was made
current_redistricting_year = 2022

site_timezone = 'America/New_York'