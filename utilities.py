"""
Utility functions for process_input
"""

import xlrd

"""
read in first sheet of an excel file into an xlrd worksheet object
"""
def read_excel_file(file_name):
    workbook = xlrd.open_workbook(file_name)
    worksheet = workbook.sheet_by_index(0)
    return worksheet

"""
eliminate all emptry rows from an xlrd worksheet object
"""
def remove_empty_rows(worksheet):
    for row in range(worksheet.nrows):
        if worksheet.cell_value(row, 0) == '':
            worksheet._cell_values.pop(row)
            worksheet._cell_types.pop(row)
            worksheet._row_len.pop(row)
    return worksheet

""""
find first row of data in an xlrd worksheet that has a keyword in the first column, checking in a case insensitive manner
""""
def find_first_row_with_keyword(worksheet, keyword):
    for row in range(worksheet.nrows):
        if keyword.lower() in worksheet.cell_value(row, 0).lower():
            return row
    return -1

"""
return all rows of data in an xlrd worksheet between two rows
"""
def get_rows_between(worksheet, start_row, end_row):
    return worksheet.get_rows()[start_row:end_row]

"""
read first column of a csv file into a list, ignoring the first row
"""
def read_csv_file_to_list_of_attributes(file_name):
    with open(file_name, 'r') as f:
        csv_list = []
        for line in f:
            csv_list.append(line.split(',')[0])
    return csv_list[1:]

"""
create dictionary of allowable attributes for each component type
"""
def create_component_attribute_dict(path_to_component_attributes, component_types):
    component_attribute_dict = {}
    for component_type in :
        component_attribute_dict[component_type] = read_csv_file_to_list_of_attributes(path_to_component_attributes + component_type + '.csv')

"""
list files in a directory, stripping out hidden files and eliminating file extension
"""
def list_files_in_directory(directory):
    return [f.split('.')[0] for f in listdir(directory) if isfile(join(directory, f)) and not f.startswith('.')]

"""
return true if all elements of a list are in any of the lists in a dictionary of lists, else return the elements that are not in any of the lists in the dictionary
"""
def check_if_all_elements_in_list_are_in_any_list_in_dict_of_lists(element_list, dict_of_lists):
    for element in element_list:
        if not any(element in dict_of_lists[key] for key in dict_of_lists):
            return False, element
    return True, None

"""
concatenate list of strings into a single string separated by spaces
"""
def concatenate_list_of_strings(list_of_strings):
    return ' '.join(list_of_strings)

""""
code to read in an excel file, create a dictionary from the 'case_data' section, 
and a list of dictionaries from the 'tech_data' section
"""
def read_excel_file_to_dict(file_name):
    # create dictionary of allowable attributes for each component type
    component_directory = "../PyPSA/component_attributes/"
    component_types = list_files_in_directory(component_directory)
    component_attribute_dict_list = create_component_attribute_dict(component_directory)
    # read in excel file describing case and technology data
    worksheet = read_excel_file(file_name)
    worksheet = remove_empty_rows(worksheet)
    start_case_row = find_first_row_with_keyword(worksheet, 'case_data')
    end_case_row = find_first_row_with_keyword(worksheet, 'end_case_data')
    case_data = get_rows_between(worksheet, start_case_row+1, end_case_row-1)
    start_tech_row = find_first_row_with_keyword(worksheet, 'tech_data')
    end_tech_row = find_first_row_with_keyword(worksheet, 'end_tech_data')
    tech_data = get_rows_between(worksheet, start_tech_row+1, end_tech_row-1)
    # create dictionary of case data
    case_data_dict = {}
    for row in case_data:
        case_data_dict[row[0].value] = row[1].value
    # create list of dictionaries of technology data
    attributes = tech_data.row_values(0)
    if(attributes[0].lower() != 'component'):
        raise Exception('First column of tech_data must be "component"')
    good,bad_list = check_if_all_elements_in_list_are_in_any_list_in_dict_of_lists(attributes[1:], component_attribute_dict_list)
    if(good == False):
        raise Exception('Attributes in tech_data must be in the list of allowable attributes for the component type. Failed = '+concatenate_list_of_strings(bad_list))
    tech_data_list = []
    for row in tech_data:
        tech_data_dict = {}
        component = row[0].value
        if(component not in component_types):
            raise Exception('Component type in tech_data must be in the list of allowable component types. Failed = '+component)
        for i in range(1,len(row)):
            val = row[i].value
            if(val != ''): # only add attribute to dictionary if it is not empty
                if(attributes[i] in component_attribute_dict_list[component]):
                    tech_data_dict[attributes[i]] = val
        tech_data_list.append(tech_data_dict)
    return case_data_dict, tech_data_list