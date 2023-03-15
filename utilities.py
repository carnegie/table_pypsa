"""
Utility functions for process_input
"""

import numpy as np
import openpyxl
import os, logging
import pypsa

"""
Read in PyPSA input file (either csv or excel[xlsx or xls]) into a list of lists
"""
def read_pypsa_input_file(file_name):
    if file_name.endswith('.csv'):
        return read_csv_file(file_name)
    elif file_name.endswith('.xlsx') or file_name.endswith('.xls'):
        return read_excel_file(file_name)
    else:
        print ('file name must end with .csv, .xlsx, or .xls')
        return None

"""
Read in csv file into a list of lists
"""
def read_csv_file(file_name):
    with open(file_name, 'r') as f:
        csv_list = []
        for line in f:
            csv_list.append(line.split(','))
    # replace empty strings with None
    for i in range(len(csv_list)):
        for j in range(len(csv_list[i])):
            if csv_list[i][j] == '' or csv_list[i][j] == '\n':
                csv_list[i][j] = None
    return csv_list

"""
Read in first sheet of an excel file into a list of lists using openpyxl
"""
def read_excel_file(file_name):
    workbook = openpyxl.load_workbook(file_name, data_only=True)
    worksheet = workbook.active
    list_of_lists = []
    for row in worksheet.iter_rows():
        row_list = []
        for cell in row:
            row_list.append(cell.value)
        list_of_lists.append(row_list)
    return list_of_lists

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
Create dictionary of allowable attributes for each component type
"""
def update_component_attribute_dict(attributes_from_file):
    component_attribute_dict = pypsa.descriptors.Dict({k: v.copy() for k, v in pypsa.components.component_attrs.items()})

    bus_numbers = [int(bus.replace("bus","")) for bus in attributes_from_file if bus is not None and bus.startswith('bus') and bus != 'bus']
    # Add attributes for components that are not in default PyPSA

    for ibus in bus_numbers:
        # Bus0 and bus1 are default in PyPSA, so don't add them
        if ibus>=2:
            component_attribute_dict["Link"].loc["bus{0}".format(ibus)] = ["string", np.nan, np.nan, "bus {0}".format(ibus), "Input (optional)"]
            component_attribute_dict["Link"].loc["efficiency{0}".format(ibus)] = ["static or series", "per unit", 1.0, "bus {0} efficiency".format(ibus), "Input (optional)"]
            component_attribute_dict["Link"].loc["p{0}".format(ibus)] = ["series", "MW", 0.0, "bus {0} output".format(ibus), "Output", ]

    for component_type in ['Load','Generator']:
        component_attribute_dict[component_type].loc["time_series_file"] = ["string", np.nan, np.nan, "time series file", "Input (optional)"]
        component_attribute_dict[component_type].loc["normalization"] = ["string", np.nan, np.nan, "normalization", "Input (optional)"]
    return component_attribute_dict

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

""""
Code to read in an excel file, create a dictionary from the 'case_data' section, 
and a list of dictionaries from the 'component_data' section
"""
def read_excel_file_to_dict(file_name):
    # read in excel file describing case and component data
    worksheet = read_pypsa_input_file(file_name) # worksheet is a list of lists
    worksheet = remove_empty_rows(worksheet)
    start_case_row = find_first_row_with_keyword(worksheet, 'case_data')
    end_case_row = find_first_row_with_keyword(worksheet, 'end_case_data')
    case_data = worksheet[start_case_row+1: end_case_row]
    start_component_row = find_first_row_with_keyword(worksheet, 'component_data')
    end_component_row = find_first_row_with_keyword(worksheet, 'end_component_data')
    component_data = worksheet[start_component_row+1: end_component_row]

    # create dictionary of case data
    case_data_dict = {}
    for row in case_data:
        case_data_dict[row[0]] = row[1]

    # Set logging level
    logging.basicConfig(level=case_data_dict["logging_level"].upper())

    # create list of dictionaries of component data
    attributes = component_data[0] 

    if(attributes[0].lower() != 'component'):
        logging.error('First column of component_data must be "component"')
        logging.error('Failed = '+attributes[0])

    # check that attributes are in the list of allowable attributes for the component type
    component_attribute_dictionary = update_component_attribute_dict(attributes[1:])
    good,bad_list = check_attributes(attributes[1:], component_attribute_dictionary)
    if(good == False):
        logging.error('Attributes in component_data must be in the list of allowable attributes for the component type. Failed = '+concatenate_list_of_strings(bad_list))
        return None
    component_data_list = []
    for row in component_data[1:]:
        component_data_dict = {}
        component = row[0]
        if(component not in pypsa.components.component_attrs.keys()):
            if component[0] == '#':
                logging.info('Skipping commented out component: '+component)
                continue
            logging.error('Component type in component_data must be in the list of allowable component types. Failed = '+component)
        component_data_dict['component'] = component
        # for link replace 'bus' with 'bus0'
        if component == 'Link':
            use_attributes = list(attributes)
            use_attributes[attributes.index('bus')] = 'bus0'
        # for storage unit replace 'efficiency' with 'efficiency_store'
        elif component == 'StorageUnit':
            use_attributes = list(attributes)
            use_attributes[attributes.index('efficiency')] = 'efficiency_store'
        elif component == 'Store':
            use_attributes = list(attributes)
            use_attributes[attributes.index('p_min_pu')] = 'e_min_pu'
            use_attributes[attributes.index('p_nom')] = 'e_nom'
        else:
            use_attributes = attributes
        for i in range(1,len(row)):
            attribute = use_attributes[i]
            val = row[i]
            # only add attribute to dictionary if it is not empty or attribute is not empty
            if(val != None and attribute != None):
                component_data_dict[attribute] = val
        component_data_list.append(component_data_dict)
    return case_data_dict, component_data_list, component_attribute_dictionary
