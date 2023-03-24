""" run run_pypsa, compare tables from test_prefix.xlsx to expected_output.txt """
import pandas as pd
import os
from pathlib import Path

print('cur dir:', os.getcwd())

# find output_data path
cur_dir = Path(os.getcwd())
output_dir = str(cur_dir.joinpath('output_data'))

output_test_case_dir = str(cur_dir.joinpath('output_data', 'test_case'))

output_xlsx_path = str(cur_dir.joinpath('output_data', 'test_case', 'test_prefix.xlsx'))

output_df = pd.read_excel(output_xlsx_path)
expected_df = pd.read_excel('test/test_prefix.xlsx')

print('output xlsx shape:  ', output_df.shape)
print('expected xlsx shape:', expected_df.shape)

# compare pypsa output to expected output
comparison_df = output_df.compare(expected_df)
print('='*40)
if comparison_df.shape == (0,0):
    print('OK, output == expected')
    print('='*40)
else:
    print('ERROR: actual output does not match expected output')
    print('here are the differences:')
    print(comparison_df)
    print('='*40)
    raise Exception('output_data/test_case/test_prefix.xlsx does not match expected')

