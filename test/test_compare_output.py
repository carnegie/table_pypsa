""" run run_pypsa, compare tables from test_prefix.xlsx to expected_output.txt """
import pandas as pd
import os
from pathlib import Path

print('cur dir:', os.getcwd())

# find output_data path
cur_dir = Path(os.getcwd())
output_test_case_dir = str(cur_dir.joinpath('output_data', 'test_case'))
output_xlsx_path = str(cur_dir.joinpath('output_data', 'test_case', 'test_prefix.xlsx'))

# check 3 'results' sheets
was_error = False
for sheet_name in ['case results', 'component results', 'time results']:
    output_df = pd.read_excel(output_xlsx_path, sheet_name=sheet_name)
    expected_df = pd.read_excel('test/test_prefix_expected.xlsx', sheet_name=sheet_name)

    # compare pypsa output to expected output
    comparison_df = output_df.compare(expected_df)
    print('='*40)
    if comparison_df.shape == (0,0):
        print(f'OK, {sheet_name} sheet: output == expected')
        print('='*40)
    else:
        print(f'ERROR: {sheet_name} sheet: output does not match expected')
        print('  output df shape:  ', output_df.shape)
        print('  expected df shape:', expected_df.shape)
        print('Here are the differences:')
        print(comparison_df)
        print('='*40)
        was_error = True

if was_error:
    raise Exception('output_data/test_case/test_prefix.xlsx does not match expected')

