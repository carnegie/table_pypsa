def get_expected(filename):
    """ extract table as list of lists from expected output file"""
    expected_table = []
    with open(filename, 'r') as f:
        found_table = False
        for line in f:
            line = line.strip()
            column_values = line.split()
            if not found_table:
                if column_values == ['Objective', 'Residual']:
                    found_table = True
                    continue
            
            # process table rows
            if found_table:
                if column_values == []:
                    break
                expected_table.append(column_values[:-1])  # drop Time header and time value last column
    return expected_table

expected_filename = "solar output Py format.txt"
output_filename = "lopf_output.txt"

expected_table = get_expected(expected_filename)
lopf_table = get_expected(output_filename)
print('Table are equal:', expected_table == lopf_table)