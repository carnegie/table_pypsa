import os, csv

"""
Check if directory exists, if not create it
"""
def check_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

"""
Strip string of leading and trailing single and double quotes, if present
"""
def strip_quotes(string):
    if string is None:
        return None
    if string.startswith('"') and string.endswith('"'):
        return string[1:-1]
    if string.startswith("'") and string.endswith("'"):
        return string[1:-1]
    return string

"""
Eliminate all lists in a list of lists that are empty or contain only empty strings
"""
def remove_empty_rows(list_of_lists):
    return [row for row in list_of_lists if not all(x is None for x in row)]

"""
Return as integer the index of first list in list of lists that only has a keyword in the first element, 
checking in a case insensitive manner
"""

def find_first_row_with_keyword(list_of_lists, keyword):
    for i in range(len(list_of_lists)):
        if not ( keyword is None or list_of_lists[i][0] is None):
            if keyword.lower() == list_of_lists[i][0].lower():
                return i
    return -1

"""
List files in a directory, stripping out hidden files and eliminating file extension
"""
def list_files_in_directory(directory):
    return [f.split('.')[0] for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and not f.startswith('.')]

"""
Return true if all elements of a list are in any of the lists in a dictionary of lists or are empty strings or all spaces, else return the elements that are not in any of the lists in the dictionary
"""
def check_attributes(element_list, dict_of_lists):
    for element in element_list:
        if element != None:
            if not any(element in dict_of_lists[key].index for key in dict_of_lists):
                return False, element
    return True, None

"""
Concatenate list of strings into a single string separated by spaces
"""
def concatenate_list_of_strings(list_of_strings):
    if type(list_of_strings) is list:
        return ' '.join(list_of_strings)
    else:
        return list_of_strings

"""
Check if a string is a number
"""
def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

"""
Number of rows to skip until beginning of data in time series csv file
"""
def skip_until_keyword(ts_file, keyword):
    with open(ts_file) as fin:
        # read to keyword and then one more line (header line)
        data_reader = csv.reader(fin)
        line_index = 1
        while True:
            line = next(data_reader)
            if line[0] == keyword:
                return line_index
            else:
                line_index += 1