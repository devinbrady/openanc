# Process for Updating Candidate Lists during Election Season

Download from https://dcboe.org/elections/2024-elections

Open tabula

Load this PDF

Close tabula, try something else

Open in adobe acrobat. 

Open new excel workbook. Make first column format text only

Copy, paste into Excel, match destination formatting

Delete all columns except for: ANC/SMD	Name	Date of Pick-up	Date Filed

Make sure there is not bad unicode in these column headers



## Restart

Make the process_candidates script ok with not having a write-in candidates list as a separate CSV thus far in 2024. 

Make the validate_smd_ids() function raise an Exception to see the stack trace

Rename the SMDs for 6/8F to be 8F

Clear all cells in the "dcboe" sheet in Source

Remove write-in winners for this election

Then do I delete the match_file? 1_candidates_dcboe_match.csv? Yes. Also I need to start including the election_year in the hash for external_id in candidates because with just candidate name and district, the hash can be the same in 2 different election years

Still no candidates on the List page

Person pages - yes


candidate_statuses - Pulled Papers for Ballot - This should be True in the pre-deadline period of an election year, and False after the deadline. 

Changed this: display_df['Election Year'] = config.current_election_year

Had to add "Candidates" to columns_to_html

List page - yes

ANC page - yes
Ward page - yes

Undo the comments on Counts

Uncomment add_candidates on the district pages

Districts - yes