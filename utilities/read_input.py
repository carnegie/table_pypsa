"""
Utility functions for process_input
"""

import numpy as np
import openpyxl
import logging
import pypsa
from utilities.load_costs import load_costs
from utilities.utilities import *
from datetime import datetime

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

    # Add attributes for components that are not in default PyPSA
    for component_type in ['Load','Generator']:
        component_attribute_dict[component_type].loc["time_series_file"] = ["string", np.nan, np.nan, "time series file", "Input (optional)"]
        component_attribute_dict[component_type].loc["normalization"] = ["string", np.nan, np.nan, "normalization", "Input (optional)"]

    return component_attribute_dict

"""
Define special attributes for some components
"""
def define_special_attributes(comp, attr):
    # for link replace 'bus' with 'bus0'
    if comp == 'Link':
        use_attr = list(attr)
        use_attr[attr.index('bus')] = 'bus0'
    # for storage unit replace 'efficiency' with 'efficiency_store'
    elif comp == 'StorageUnit':
        use_attr = list(attr)
        use_attr[attr.index('efficiency')] = 'efficiency_store'
    elif comp == 'Store':
        use_attr = list(attr)
        use_attr[attr.index('p_min_pu')] = 'e_min_pu'
        use_attr[attr.index('p_nom')] = 'e_nom'
    else:
        use_attr = attr
    return use_attr

"""
Read in component data
"""
def read_component_data(comp_dict, attr, val, technology, costs_df):
    factor = 1
    # if value is a number or name, read that.
    # if it's empty or a cost name, use read_attr to get the value from the costs dataframe.
    if attr != None:
        # if "name", "bus", or "time_series_file" is in attr or value can be converted to a float, use that
        if (val != None and (any(x in attr for x in ['name', 'bus', 'carrier', 'time_series_file']) or is_number(val))):
            comp_dict[attr] = val
            read_attr = None
        # if otherwise value is a string, use that as read attr
        elif type(val) is str:
            if '*' in val:
                factor = float(val.split('*')[0])
                val = val.split('*')[1]
            read_attr = val
        # if value is empty, use attr as read attr
        else:
            read_attr = attr
        # if read_attr is defined, use it to get the value from the costs dataframe
        if (read_attr != None and read_attr in costs_df.columns and technology in costs_df.index):
            comp_dict[attr] = costs_df.loc[technology, read_attr] * factor
            logging.info('Using default value for ' + comp_dict["component"] + ' "' + comp_dict["name"] + '" for ' + attr
                         + ' = ' + str(comp_dict[attr]))
    return comp_dict

""""
Code to read in an excel or csv file, create a dictionary from the 'case_data' section, 
and a list of dictionaries from the 'component_data' section
"""
def read_input_file_to_dict(file_name):
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

    # Number of full years between two datetimes given as strings
    nyears = (datetime.strptime(case_data_dict["datetime_end"], "%Y-%m-%d %H:%M:%S") - datetime.strptime(
        case_data_dict["datetime_start"], "%Y-%m-%d %H:%M:%S")).days // 365
    # Config file path
    if '/' in os.getcwd() and os.getcwd().split('/')[-1] == 'clab_pypsa':  # if unix path
        config_file_path = os.getcwd() + '/utilities/cost_config.yaml'
    elif '\\' in os.getcwd() and os.getcwd().split('\\')[-1] == 'clab_pypsa':  # allow for windows path
        config_file_path = os.getcwd() + '\\utilities\\cost_config.yaml'
    elif os.path.isdir(os.getcwd() + '/clab_pypsa'):
        config_file_path = os.getcwd() + '/clab_pypsa/utilities/cost_config.yaml'
    else:
        logging.error('Current directory is not clab_pypsa and clab directory is not in current directory.')
    # Load PyPSA costs
    costs = load_costs(tech_costs=case_data_dict["costs_path"], config=config_file_path, Nyears=nyears)

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
        component_data_dict['name'] = row[1]
        # Read in technology name before additional specifications following % and remove space at end
        tech_name = row[1].split('%')[0].strip()

        # Determine special attributes for component
        use_attributes = define_special_attributes(component, attributes)

        for i in range(2,len(row)):
            attribute = use_attributes[i]
            value = row[i]
            component_data_dict = read_component_data(component_data_dict, attribute, value, tech_name, costs)

        component_data_list.append(component_data_dict)
    return case_data_dict, component_data_list, component_attribute_dictionary
