# matching_spec.py


from scripts.match_people import MatchPeople


mp = MatchPeople(
    input_csv_path='~/Desktop/candidates_test.csv'
    , source_name='candidates_dcboe'
    , name_column='candidate_name'
    )

result = mp.match_to_openanc()

# print(result)
# result.to_clipboard()