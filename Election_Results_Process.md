# Election Results Process

Download main election results file from: https://electionresults.dcboe.org/election_results/2024-General-Election

Results Category: Citywide, Download Summary Reports, Results in CSV format. Save CSV to data/dcboe/election_results

This file contains the votes of the named candidates on the ballot, as well as the total of write-ins. The format of the file has been consistent across elections. 

Download the Write-In Candidates PDF from the same page. Copy the winners to a text CSV file.

    What does this mean? "There is a write-in nominee with more votes than this write-in candidate. As such, there is no winner for this contest."

Run

    python build_site.py -e

Resolve any SMD errors in the source files. Fix any SMD formatting issues. 

In config.py, increment current_election_year to the next election year. In 2025, set it to "2026"

Run

     python build_site.py --all

## External IDs

