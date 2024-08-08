# Read PDF list of candidates from DCBOE using Tabula then save to Excel file.


import tabula
import pandas as pd
from pathlib import Path

input_pdf = Path('~/Dropbox/OpenANC/DCBOE candidate lists 2024/General-24-ANC-Candidates-08072024.pdf')
output_xlsx = Path('data/dcboe/excel-clean/dcboe-ballot-2024-08-07.xlsx')

print(f'input: {input_pdf.name}')

dfs = tabula.read_pdf(input_pdf, pages='all')

df = pd.concat(dfs)

print(f'Number of candidates: {df.Name.notnull().sum()}')

columns_to_excel = ['ANC-SMD', 'Name', 'Date of Pick-up', 'Date Filed']

df[columns_to_excel].to_excel(output_xlsx, index=False)
# df.to_excel(output_xlsx, index=False)

print(f'output: {output_xlsx.name}')