# Read PDF list of candidates from DCBOE using Tabula then save to Excel file.


import tabula
import pandas as pd
from pathlib import Path

input_pdf = Path('~/Dropbox/OpenANC/DCBOE candidate lists 2024/General-24-ANC-Candidates-09122024.pdf')
output_xlsx = Path('data/dcboe/excel-clean/dcboe-ballot-2024-09-12.xlsx')

print(f'input: {input_pdf.name}')

dfs = tabula.read_pdf(input_pdf, pages='all')

df = pd.concat(dfs)

print(f'Number of ballot candidates: {df.Name.notnull().sum()}')

df['Date of Withdrawal'] = df.Name.str.extract("\(withdrew(.*)\)")
df['Name'] = df.Name.str.replace("\(withdrew(.*)\)", '', regex=True, case=False).str.strip()

df['Challenge Notes'] = 'Challenge' + df.Name.str.extract("\(Challenge(.*)\)")
df['Name'] = df.Name.str.replace("\(Challenge(.*)\)", '', regex=True, case=False).str.strip()

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



wu_input_pdf = Path('~/Dropbox/OpenANC/DCBOE candidate lists 2024/General-24-Write-in-Candidates-09122024.pdf')
wu_output_xlsx = Path('data/dcboe/excel-clean/dcboe-write-in-2024-09-12.xlsx')

print(f'\ninput: {wu_input_pdf.name}')

wu_dfs = tabula.read_pdf(wu_input_pdf, pages='all')

wu_df = pd.concat(wu_dfs)

wu_df = wu_df[wu_df.Office.str.contains('Advisory')].copy()
wu_df.rename(columns={"Write-in Candidate's Name": 'Name'}, inplace=True)

print(f'Number of write-in candidates: {wu_df.Name.notnull().sum()}')

wu_df['Office'] = wu_df['Office'].str.replace('Advisory Neighborhood Commissioner', '').str.strip()
wu_df['Name'] = wu_df['Name'].str.replace('*', '', regex=False).str.strip()

columns_to_excel = ['Office', 'Name']
wu_df[columns_to_excel].to_excel(wu_output_xlsx, index=False)
print(f'output: {wu_output_xlsx.name}')
