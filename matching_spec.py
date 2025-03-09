# matching_spec.py


from scripts.match_people import MatchPeople


# mp = MatchPeople(
#     input_csv_path='~/Desktop/candidates_test.csv'
#     , source_name='candidates_dcboe'
#     , name_column='candidate_name'
#     )

# mp = MatchPeople(
#     input_csv_path='data/dcboe/write_in_winners.csv'
#     , source_name='write_in_winners'
#     , name_column='candidate_name'
#     )

mp = MatchPeople(
    input_csv_path='data/dcboe/candidate_votes.csv'
    , source_name='candidate_votes'
    , name_column='candidate_name'
    )

result = mp.match_to_openanc()

# print(result)
# result.to_clipboard()