# bhayes 21mar23
# extract table from output file and expected output file and compare them

expected_filename = "solar output Py format.txt"
output_filename = "run_output.txt"

def get_expected(expected_filename):
    """ extract table as list of lists from expected output file"""
    expected_table = []
    with open(expected_filename, 'r') as f:
        found_table = False
        for line in f:
            line = line.strip()
            column_values = line.split()
            print(column_values)
            if not found_table:
                if column_values == ['Objective', 'Residual']:
                    found_table = True
                    continue
            
            # process table rows
            if found_table:
                if column_values == []:
                    break
                expected_table.append(column_values[:-1])  # drop Time header and time value last column

    print('-- Table --')
    for line in expected_table:
        print(line)

                
        