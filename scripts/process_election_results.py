"""
Read in election results files from DCBOE, perform calculations, and match to database
"""

import pandas as pd
from tqdm import tqdm

from scripts.data_transformations import (
    list_candidates
    )

from scripts.common import (
    hash_dataframe
    , match_names
    , validate_smd_ids
)



class ProcessElectionResults():

    def __init__(self):
        
        self.results_files = {
            2020: 'November_3_2020_General_Election_Certified_Results.csv'
            , 2022: 'November_8_2022_General_Election_Certified_Results.csv'
            , 2024: 'November_5_2024_General_Election_Certified_Results.csv'
        }

        self.write_in_files = {
            2020: 'write_in_winners_2020.csv'
            , 2022: 'write_in_winners_2022.csv'
            , 2024: 'write_in_winners_2024.csv'
        }



    def read_election_results_csv(self, election_year):
        """
        Read and preprocess data from DCBOE election CSV. Return a cleaned DataFrame
        """
    
        df = pd.read_csv(f'data/dcboe/election_results/{self.results_files[election_year]}')

        df = df.rename(columns={
            'Candidate': 'candidate_name'
            , 'ContestName': 'contest_name'
            , 'ContestNumber': 'contest_number'
            , 'Votes': 'votes'
        })

        if election_year == 2024:
            anc = df[df['contest_name'].str.contains('ANC-')].copy()
        else:
            anc = df[df['contest_name'].str.contains('SINGLE MEMBER DISTRICT')].copy()

        smd_id_prefix = 'smd_'
        if election_year >= 2022:
            smd_id_prefix += '2022_'

        if election_year == 2024:
            # Stop extraction at space, for district entered as "ANC-6/8F01 6/8F01"
            anc['smd_id'] = smd_id_prefix + anc['contest_name'].str.extract('(?<=ANC-)(\S*)')
            anc['smd_id'] = anc['smd_id'].str.replace('6/8F', '8F')
        else:
            anc['smd_id'] = smd_id_prefix + anc['contest_name'].str.extract('(?<=ANC - )(.*)(?=SINGLE MEMBER)')

        anc['smd_id'] = anc['smd_id'].str.strip()
        validate_smd_ids(anc)

        candidates_results = (
            anc
            [~anc.candidate_name.isin(['OVER VOTES', 'UNDER VOTES'])]
            .groupby(['smd_id', 'contest_number', 'candidate_name'])
            .votes.sum()
            .reset_index()
        )

        # external_id is a hash of the uppercase candidate name and the smd_id they were running in
        candidates_results['candidate_name_upper'] = candidates_results['candidate_name'].str.upper()
        candidates_results['external_id'] = hash_dataframe(candidates_results, ['smd_id', 'candidate_name_upper'])
        candidates_results.loc[candidates_results.candidate_name_upper == 'WRITE-IN', 'external_id'] = pd.NA

        candidates_results['ranking'] = candidates_results.groupby('smd_id').votes.rank(method='first', ascending=False)
        candidates_results['winner'] = candidates_results['ranking'] == 1

        candidates_results['write_in_winner'] = (
            candidates_results['winner'] & (candidates_results['candidate_name'] == 'Write-in')
        )

        # Sort candidates by the number of votes they got within SMD, making the winner first
        candidates_results = candidates_results.sort_values(by=['smd_id', 'votes'], ascending=[True, False])



        # Calculate the total votes cast in each SMD

        total_votes = candidates_results.groupby('smd_id').votes.sum()
        total_votes.name = 'total_votes'
        candidates_results = pd.merge(candidates_results, total_votes, how='inner', on='smd_id')
        candidates_results['vote_share'] = candidates_results['votes'] / candidates_results['total_votes']



        # Create columns showing the number of votes the winner in each SMD received.
        # This will be used to calculate the "margin of defeat" for all other candidates.

        winning_votes = candidates_results.groupby('smd_id').agg(
            winning_votes=('votes', max)
            , winning_vote_percentage=('vote_share', max)
        )

        candidates_results = pd.merge(candidates_results, winning_votes, how='inner', on='smd_id')



        # Create columns showing the number of votes for the next candidate in the DataFrame.
        # For the first place candidate in an SMD, these _shifted columns will have the votes
        # of the second-place candidate.

        shift_one = candidates_results[['smd_id', 'votes', 'vote_share']].shift(-1)
        shift_one = shift_one.rename(columns={
            'smd_id': 'smd_id_shifted'
            , 'votes': 'votes_shifted'
            , 'vote_share': 'vote_share_shifted'
        })

        candidates_results = pd.concat([candidates_results, shift_one], axis=1)



        # Calculate the margin of victory - positive for winners, negative for losers
        candidates_results['margin_of_victory'] = None
        candidates_results['margin_of_victory_percentage'] = None

        contested_winners = (
            (candidates_results['smd_id'] == candidates_results['smd_id_shifted']) & (candidates_results['winner'])
        )

        # For winners, the margin of victory is their votes minus the second-place votes
        candidates_results.loc[contested_winners, 'margin_of_victory'] = (
            candidates_results['votes'] - candidates_results['votes_shifted']
        )
        candidates_results.loc[contested_winners, 'margin_of_victory_percentage'] = (
            candidates_results['vote_share'] - candidates_results['vote_share_shifted']
        )

        # For losers, the margin of defeat is the their votes minus the first-place votes
        candidates_results.loc[~contested_winners, 'margin_of_victory'] = (
            candidates_results['votes'] - candidates_results['winning_votes']
        )

        candidates_results.loc[~contested_winners, 'margin_of_victory_percentage'] = (
            candidates_results['vote_share'] - candidates_results['winning_vote_percentage']
        )



        # Count the number of candidates who received votes. This lumps all write-ins as one candidate.
        # num_candidates is not currently used by the frontend, just for humans checking the data.

        num_candidates = candidates_results.groupby('smd_id').candidate_name.count()
        num_candidates.name = 'num_candidates'
        candidates_results = pd.merge(candidates_results, num_candidates, how='inner', on='smd_id')

        print(f'Election results processed for year: {election_year}. Number of candidates: {candidates_results.external_id.nunique()}. Total votes: {candidates_results.votes.sum():,}')

        return candidates_results



    def read_write_in_winners(self, election_year):

        write_in_df = pd.read_csv(f'data/dcboe/election_results/{self.write_in_files[election_year]}')

        write_in_df = write_in_df.rename(
            columns={
            'Office': 'smd'
            , 'ANC/SMD': 'smd'
            , 'Write-in Candidate Name': 'official_name'
            , "Candidate's Name": 'official_name'
            })

        smd_id_prefix = 'smd_'
        if election_year >= 2022:
            smd_id_prefix += '2022_'

        write_in_df['smd_id'] = smd_id_prefix + write_in_df['smd']
        validate_smd_ids(write_in_df)

        write_in_df['candidate_name'] = write_in_df['official_name']
        write_in_df['candidate_name_upper'] = write_in_df['official_name'].str.upper()

        write_in_df['external_id'] = hash_dataframe(write_in_df, ['smd_id', 'candidate_name_upper'])

        print(f'Write-in results processed for year: {election_year}. Number of write-in winners: {len(write_in_df)}')

        return write_in_df



    def run(self):

        results_dict = {}

        for election_year in self.results_files:
            results_dict[election_year] = self.read_election_results_csv(election_year)

        results_all_years = pd.concat(results_dict, names=['election_year']).reset_index()

        results_all_years[[
            'election_year'
            , 'smd_id'
            , 'external_id'
            , 'candidate_name'
            , 'votes'
            , 'vote_share'
            , 'ranking'
            , 'winner'
            , 'write_in_winner'
            , 'margin_of_victory'
            , 'margin_of_victory_percentage'
            , 'num_candidates'
            , 'total_votes'
        ]].to_csv('data/dcboe/candidate_votes.csv', index=False)


        write_in_dict = {}
        for election_year in self.write_in_files:
            write_in_dict[election_year] = self.read_write_in_winners(election_year)

        write_in_all_years = pd.concat(write_in_dict, names=['election_year']).reset_index()

        write_in_all_years[[
            'election_year'
            , 'external_id'
            , 'smd_id'
            , 'candidate_name'
        ]].to_csv('data/dcboe/write_in_winners.csv', index=False)


