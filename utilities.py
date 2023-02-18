"""
Utility functions for process_input
"""

import openpyxl
import os

"""
read in PyPSA input file (either csv or excel[xlsx or xls]) into a list of lists
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
read in csv file into a list of lists
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
read in first sheet of an excel file into a list of lists using openpyxl
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

"strip string of leading and trailing single and double quotes, if present"
def strip_quotes(string):
    if string is None:
        return None
    if string.startswith('"') and string.endswith('"'):
        return string[1:-1]
    if string.startswith("'") and string.endswith("'"):
        return string[1:-1]
    return string

"""
eliminate all lists in a list of lists that are empty or contain only empty strings
"""
def remove_empty_rows(list_of_lists):
    return [row for row in list_of_lists if not all(x is None for x in row)]

"""
return as integer the index of first list in list of lists that has a keyword in the first element, 
checking in a case insensitive manner
"""

def find_first_row_with_keyword(list_of_lists, keyword):
    for i in range(len(list_of_lists)):
        if not ( keyword is None or list_of_lists[i][0] is None):
            if keyword.lower() in list_of_lists[i][0].lower():
                return i
    return -1

"""
read first column of a csv file into a list, ignoring the first row
"""
def read_csv_file_to_list_of_attributes(file_name):
    with open(file_name, 'r') as f:
        csv_list = []
        for line in f:
            csv_list.append(strip_quotes(line.split(',')[0]))
    return csv_list[1:]

"""
create dictionary of allowable attributes for each component type
"""
def create_component_attribute_dict(path_to_component_attributes, component_dict):
    component_attribute_dict = {}
    for component_type in component_dict:
        component_attribute_file_name = component_dict[component_type] 
        component_attribute_dict[component_type] = read_csv_file_to_list_of_attributes(
            path_to_component_attributes + component_attribute_file_name + '.csv')
        if component_type in ['load','generator']:
            component_attribute_dict[component_type].append('series_file')
            component_attribute_dict[component_type].append('normalization')
    return component_attribute_dict

"""
list files in a directory, stripping out hidden files and eliminating file extension
"""
def list_files_in_directory(directory):
    return [f.split('.')[0] for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and not f.startswith('.')]

"""
return true if all elements of a list are in any of the lists in a dictionary of lists or are empty strings or all spaces, else return the elements that are not in any of the lists in the dictionary
"""
def check_if_all_elements_in_list_are_in_any_list_in_dict_of_lists_or_empty(element_list, dict_of_lists):
    print (dict_of_lists)
    for element in element_list:
        if element != None:
            if not any(element in dict_of_lists[key] for key in dict_of_lists):
                return False, element
    return True, None

"""
concatenate list of strings into a single string separated by spaces
"""
def concatenate_list_of_strings(list_of_strings):
    if type(list_of_strings) is list:
        return ' '.join(list_of_strings)
    else:
        return list_of_strings

""""
code to read in an excel file, create a dictionary from the 'case_data' section, 
and a list of dictionaries from the 'tech_data' section
"""
def read_excel_file_to_dict(file_name):
    # create dictionary of allowable attributes for each component type
    component_directory = "./PyPSA/pypsa/component_attrs/"
    component_dict = {"load":"loads","generator":"generators","line":"lines","transformer":"transformers","bus":"buses","store":"stores",
                    "carrier":"carriers","link":"links","global_constraint":"global_constraints","network":"networks","shunt_impedance":"shunt_impedances",
                    "storage_unit":"storage_units","transformer_type":"transformer_types","sub_network":"sub_networks"}
    # make a list of component file names (plural of component type)

    component_attribute_dict_list = create_component_attribute_dict(component_directory, component_dict)

    # read in excel file describing case and technology data
    worksheet = read_pypsa_input_file(file_name) # worksheet is a list of lists
    print(worksheet)
    worksheet = remove_empty_rows(worksheet)
    start_case_row = find_first_row_with_keyword(worksheet, 'case_data')
    end_case_row = find_first_row_with_keyword(worksheet, 'end_case_data')
    case_data = worksheet[start_case_row+1: end_case_row]
    start_tech_row = find_first_row_with_keyword(worksheet, 'tech_data')
    end_tech_row = find_first_row_with_keyword(worksheet, 'end_tech_data')
    tech_data = worksheet[start_tech_row+1: end_tech_row]
    # create dictionary of case data
    case_data_dict = {}
    for row in case_data:
        case_data_dict[row[0]] = row[1]
    # create list of dictionaries of technology data
    attributes = tech_data[0] 

    if(attributes[0].lower() != 'component'):
        raise Exception('First column of tech_data must be "component_class"')
    good,bad_list = check_if_all_elements_in_list_are_in_any_list_in_dict_of_lists_or_empty(attributes[1:], component_attribute_dict_list)
    if(good == False):
        raise Exception('Attributes in tech_data must be in the list of allowable attributes for the component type. Failed = '+concatenate_list_of_strings(bad_list))
    tech_data_list = []
    for row in tech_data[1:]:
        tech_data_dict = {}
        component = row[0]
        if(component not in component_dict):
            raise Exception('Component type in tech_data must be in the list of allowable component types. Failed = '+component)
        tech_data_dict['component'] = component
        for i in range(1,len(row)):
            val = row[i]
            if(val != None and attributes[i] != None): # only add attribute to dictionary if it is not empty or attribute is not empty
                if(attributes[i] in component_attribute_dict_list[component]):
                    tech_data_dict[attributes[i]] = val
        tech_data_list.append(tech_data_dict)
    return case_data_dict, tech_data_list



case_dict,tech_list = read_excel_file_to_dict('test_case.csv')

print('case_dict')
print(case_dict)
print('tech_list')
print(tech_list)

