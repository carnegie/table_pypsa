import os, csv
import pandas as pd

def check_directory(directory):
    """
    Check if directory exists, if not create it
    """
    if not os.path.exists(directory):
        os.makedirs(directory)


def strip_quotes(string):
    """
    Strip string of leading and trailing single and double quotes, if present
    """
    if string is None:
        return None
    if string.startswith('"') and string.endswith('"'):
        return string[1:-1]
    if string.startswith("'") and string.endswith("'"):
        return string[1:-1]
    return string



def remove_empty_rows(list_of_lists):
    """
    Eliminate all lists in a list of lists that are empty or contain only empty strings
    """
    return [row for row in list_of_lists if not all(x is None for x in row)]


def find_first_row_with_keyword(list_of_lists, keyword):
    """
    Return as integer the index of first list in list of lists that only has a keyword in the first element, 
    checking in a case insensitive manner
    """
    for i in range(len(list_of_lists)):
        if not ( keyword is None or list_of_lists[i][0] is None):
            if keyword.lower() == list_of_lists[i][0].lower():
                return i
    return -1

"""
List files in a directory, stripping out hidden files and eliminating file extension

def list_files_in_directory(directory):
    return [f.split('.')[0] for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and not f.startswith('.')]
"""


def check_attributes(element_list, dict_of_lists):
    """
    Return true if all elements of a list are in any of the lists in a dictionary of lists or are empty strings or all spaces, else return the elements that are not in any of the lists in the dictionary
    """
    for element in element_list:
        if element != None:
            if not any(element in dict_of_lists[key].index for key in dict_of_lists):
                return False, element
    return True, None


def concatenate_list_of_strings(list_of_strings):
    """
    Concatenate list of strings into a single string separated by spaces
    """
    if type(list_of_strings) is list:
        return ' '.join(list_of_strings)
    else:
        return list_of_strings


def is_number(s):
    """
    Check if a string is a number
    """
    try:
        float(s)
        return True
    except ValueError:
        return False


def skip_until_keyword(ts_file, keyword):
    """
    Number of rows to skip until beginning of data in time series csv file
    """
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

def get_output_filename(case_input_dict):
    """
    return generated output file pathname
    """
    check_directory(case_input_dict["output_path"])
    check_directory(os.path.join(case_input_dict["output_path"], case_input_dict["case_name"]))
    outfile = os.path.join(case_input_dict["output_path"], case_input_dict["case_name"], case_input_dict["filename_prefix"])
    return outfile

def stats_add_units(n_stats, case_input_dict):
    """
    return statistics dataframe with units added to column names
    """
    stats = n_stats().copy()
    for col in stats.columns:
        if "Capital Expenditure" in col or "Revenue" in col:
            unit = " [{}]".format(case_input_dict["currency"])
        elif "Operational Expenditure" in col:
            unit = " [{}/{}]".format(case_input_dict["currency"], case_input_dict["time_unit"])
        elif not "Factor" in col :
            unit = " [{}]".format(case_input_dict["power_unit"])  
        elif "Curtailment" in col:
            unit = " [{}{}]".format(case_input_dict["power_unit"], case_input_dict["time_unit"])          
        else:
            unit = ""
        stats.rename(columns={col: col+unit}, inplace=True)
    return stats
