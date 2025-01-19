# Read PDF list of candidates from DCBOE using Tabula then save to Excel file.


import tabula
import pandas as pd
from pathlib import Path


def candidate_list_ballot():
    """
    Save PDF to XLSX for the list of candidates who are trying to get on the ballot.
    """

    input_pdf = Path('~/Dropbox/OpenANC/DCBOE candidate lists 2024/General-24-ANC-Candidates-09242024.pdf')
    output_xlsx = Path('data/dcboe/excel-clean/dcboe-ballot-2024-09-24.xlsx')

    print(f'input: {input_pdf.name}')

    dfs = tabula.read_pdf(input_pdf, pages='all')

    df = pd.concat(dfs)

    print(f'Number of ballot candidates: {df.Name.notnull().sum()}')

    df['Date of Withdrawal'] = df.Name.str.extract("\(withdrew(.*)\)")
    df['Name'] = df.Name.str.replace("\(withdrew(.*)\)", '', regex=True, case=False).str.strip()

    df['Challenge Notes'] = 'Challenge' + df.Name.str.extract("\(Challenge(.*)\)")
    df['Name'] = df.Name.str.replace("\(Challenge(.*)\)", '', regex=True, case=False).str.strip()

    # Remove the rows where the candidate is "Write-In, If Any"
    df = df.loc[df['Name'].str.lower() != 'write-in, if any'].copy()

    columns_to_excel = [
        'ANC-SMD'
        , 'Name'
        , 'Date of Pick-up'
        , 'Date Filed'
        , 'Date of Withdrawal'
        , 'Challenge Notes'
        ]

    df[columns_to_excel].to_excel(output_xlsx, index=False)

    print(f'output: {output_xlsx.name}')


def candidate_list_write_in():
    """
    Save PDF to XLSX for the list of candidates who filed to run as write-ins.
    """

    wu_input_pdf = Path('~/Dropbox/OpenANC/DCBOE candidate lists 2024/General-24-Write-in-Candidates-11072024.pdf')
    wu_output_xlsx = Path('data/dcboe/excel-clean/dcboe-write-in-2024-11-07.xlsx')

    print(f'\ninput: {wu_input_pdf.name}')

    wu_dfs = tabula.read_pdf(wu_input_pdf, pages='all')

    for idx, _ in enumerate(wu_dfs):
        if idx > 0:
            wu_dfs[idx].loc[len(wu_dfs[idx])+1] = wu_dfs[idx].columns
            wu_dfs[idx].columns = ["Write-in Candidate's Name", "Office", "Party", "Date Form Filed"]

    wu_df = pd.concat(wu_dfs)

    wu_df = wu_df[wu_df.Office.str.contains('Advisory')].copy()
    wu_df.rename(columns={"Write-in Candidate's Name": 'Name'}, inplace=True)

    print(f'Number of write-in candidates: {wu_df.Name.notnull().sum()}')


    spelling_variations = [
        'Advisory Neighborhood Commissioner'
        , 'Advisory Neighbohood Commissioner'
        , 'Advisory Neighborhhod Commissioner'
        , 'Advisory Neighborhood Commisioner'
        , 'Advisory Neighborhood commissioner'
    ]

    for sp in spelling_variations:
        wu_df['Office'] = wu_df['Office'].str.replace(sp, '').str.strip()


    wu_df['Name'] = wu_df['Name'].str.replace('*', '', regex=False).str.strip()

    columns_to_excel = ['Office', 'Name']
    wu_df[columns_to_excel].to_excel(wu_output_xlsx, index=False)
    print(f'output: {wu_output_xlsx.name}')



def election_results_write_in():
    """I couldn't get this PDF to format correctly, instead copied and pasted manually"""

    input_pdf = Path('~/Dropbox/OpenANC/DCBOE candidate lists 2024/November_5_2024_General_Election_Write-In.pdf')
    output_csv = Path('data/dcboe/election_results/write_in_winners_2024.csv')

    print(f'input: {input_pdf.name}')

    dfs = tabula.read_pdf(input_pdf, pages='all')

    df = pd.concat(dfs)
    df.to_clipboard()





if __name__ == '__main__':

    # candidate_list_ballot()
    # candidate_list_write_in()

    election_results_write_in()
