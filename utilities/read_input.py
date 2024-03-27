"""
Utility functions for process_input
"""
import numpy as np
import logging
import pypsa
from utilities.load_costs import load_costs
from utilities.utilities import is_number, remove_empty_rows, find_first_row_with_keyword, check_attributes, concatenate_list_of_strings
from datetime import datetime
from pathlib import Path
import pandas as pd
from sys import exit


def read_pypsa_input_file(file_name):
    """ file_name: str, case file path 
        return a list of lists of data from the PyPSA case .csv or .xlsx
    """
    if file_name.endswith('.csv'):
        return read_csv_file(file_name)
    elif file_name.endswith('.xlsx') or file_name.endswith('.xls'):
        return read_excel_file(file_name)
    else:
        print ('file name must end with .csv, .xlsx, or .xls')
        return None


def read_csv_file(file_name):
    """ Read csv case file into a list of lists of cell values
        Convert numbers to int or float, booleans to True or False, blanks to None
    """
    df = pd.read_csv(file_name, header=None)
    csv_list_with_nan = df.values.tolist()
    # convert np.nan to None
    csv_list = []
    for row in csv_list_with_nan:
        new_list = []
        for value in row:
            if value in [np.nan,'','\n']:
                new_list.append(None)
            elif value.lower() == 'true':
                new_list.append(True)
            elif value.lower() == 'false':
                new_list.append(False)
            else:
                # try converting to int or float
                try:
                    new_list.append(int(value))
                except Exception:
                    try:
                        new_list.append(float(value))
                    except Exception:
                        new_list.append(value)  # leave value as is
        csv_list.append(new_list)
    return csv_list


def read_excel_file(file_name):
    """
    Read in first sheet of an excel file into a list of lists using Pandas
    """
    df_worksheet = pd.read_excel(file_name, header=None)
    list_of_lists_with_nan = df_worksheet.values.tolist()
    # convert np.nan to None
    list_of_lists = []
    for row in list_of_lists_with_nan:
        new_list = []  # with None instead of np.nan
        for value in row:
            new_list.append(None if value is np.nan else value)
        list_of_lists.append(new_list)
    return list_of_lists


def update_component_attribute_dict(attributes_from_file):
    """
    Create dictionary of allowable attributes for each component type
    """
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


def define_special_attributes(comp, attr):
    """ return optionally updated attr based on component data """
    # for link replace 'bus' with 'bus0'
    if comp == 'Link':
        use_attr = list(attr)
        use_attr[attr.index('bus')] = 'bus0'
    # for storage unit replace 'efficiency' with 'efficiency_store'
    elif comp == 'StorageUnit':
        use_attr = list(attr)
        if 'efficiency' in attr:
            use_attr[attr.index('efficiency')] = 'efficiency_store'
    elif comp == 'Store':
        use_attr = list(attr)
        if 'p_min_pu' in attr:
            use_attr[attr.index('p_min_pu')] = 'e_min_pu'
        if 'p_max_pu' in attr:
            use_attr[attr.index('p_max_pu')] = 'e_max_pu'
        if 'p_nom' in attr:
            use_attr[attr.index('p_nom')] = 'e_nom'
        if 'cyclic_state_of_charge' in attr:
            use_attr[attr.index('cyclic_state_of_charge')] = 'e_cyclic'
    else:
        use_attr = attr
    return use_attr


def read_component_data(comp_dict, attr, val, technology, costs_df):
    """
    Read in one row of component data and update the comp_dict
    """
    factor = 1
    # if value is a number or name, read that.
    # if it's empty or a cost name, use read_attr to get the value from the costs dataframe.
    if attr != None:
        read_attr = None
        # if "name", "bus", or "time_series_file" is in attr or value can be converted to a float, use that
        if (val != None and (any(x in attr for x in ['name', 'bus', 'carrier']) or is_number(val) or '=' in val)):
            comp_dict[attr] = val
        # if otherwise value is a string, use database value if the string is just 'db'
        # if first two letters are db use the rest of the string as the attribute name
        # if there is a '*' in the string, use the value before the '*' as a factor to multiply the database value
        elif type(val) is str:
            if 'db' in val:
                if val == 'db':
                    read_attr = attr
                elif '*' in val:
                    factor = float(val.split('*')[0])
                    val = val.split('*')[1].replace('db_','')
                    read_attr = val
                else:
                    val = val.replace('db_','')
                    read_attr = val
            elif val.endswith('.csv'):
                comp_dict[attr] = val
            else:
                logging.error('Failed to read in '+val + ' for attribute ' + attr + ' for component ' + comp_dict["component"] + ' ' + comp_dict["name"])
                logging.error('Exiting now.')
                exit()

        # if read_attr is defined, use it to get the value from the costs dataframe
        if read_attr != None:
            if (technology in costs_df.index and read_attr in costs_df.columns):
                comp_dict[attr] = costs_df.loc[technology, read_attr] * factor
                logging.info('Using technology database value for ' + comp_dict["component"] + ' "' + comp_dict["name"] + '" for ' + attr
                                + ' = ' + str(comp_dict[attr]) + ' for technology ' + technology)   
            elif (technology not in costs_df.index and read_attr in costs_df.columns):
                logging.error('Technology ' + technology + ' not in database. Trying to use database value for ' + read_attr + '.')
                logging.error('Terminal error. Exiting.')
                exit() 
            elif (technology in costs_df.index and read_attr not in costs_df.columns):
                logging.error('Attribute ' + read_attr + ' does not have a database value for technology ' + technology + '.')
                logging.error('Terminal error. Exiting.')
                exit()
            else:
                logging.error('Technology ' + technology + ' not in database and attribute ' + read_attr + ' does not have a database value for technology ' + technology + '.')
                logging.error('Terminal error. Exiting.')
                exit()

    return comp_dict


def convert_slash_to_dash_dates(s):
    """ s: 'mm/dd/yyyy 0:00:00'  from csv case file
        return 'yyyy-mm-dd <time>:00'
    """
    parts = s.split()
    # convert date
    if '/' in parts[0]:
        old = parts[0]
        mm,dd,yyyy = old.split('/')
        if len(mm)==1:
            mm = '0' + mm
        if len(dd)==1:
            dd = '0' + dd
        parts[0] = '-'.join([yyyy,mm,dd])
    
    # convert time
    time = parts[1]
    if time.count(':')==1:
        parts[1] = time + ':00'  # add seconds
        
    return ' '.join(parts)


def read_input_file_to_dict(file_name):
    """"
    file_name:  str, case file 
    Code to read in an excel or csv case file
    return a dictionary from the CASE_DATA section: 
        case_data_dict: keys: col A, values: col B
    return a list of dictionaries (one per row) from the COMPONENT_DATA section: 
        component_attribute_dictionary: keys: col names from first row, values: cell values
    return component_attribute_dictionary: a pypsa.descriptors dict
    """
    
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
    # convert date format if necessary
    if '/' in case_data_dict['datetime_end']:
        case_data_dict['datetime_end'] = convert_slash_to_dash_dates(case_data_dict['datetime_end'])
    if '/' in case_data_dict['datetime_start']:
        case_data_dict['datetime_start'] = convert_slash_to_dash_dates(case_data_dict['datetime_start'])
    nyears = (datetime.strptime(case_data_dict["datetime_end"], "%Y-%m-%d %H:%M:%S") - datetime.strptime(
        case_data_dict["datetime_start"], "%Y-%m-%d %H:%M:%S")).days // 365
    case_data_dict['nyears'] = nyears
    
    # Config file path
    cwd = Path.cwd()
    if cwd.parts[-1] == 'table_pypsa':
        config_file_path = str(cwd / 'utilities' / 'cost_config.yaml')  # for local or Github action
        # note in GitHub action the cwd is /home/runner/work/table_pypsa/table_pypsa
    elif (cwd / 'table_pypsa').is_dir():  # we're above the table_pypsa dir
        config_file_path = str(cwd / 'table_pypsa' / 'utilities' / 'cost_config.yaml')
    elif 'table_pypsa' in cwd.parts:  # in case we're running an executable in table_pypsa/dist/run_pypsa via PyInstaller exe
        table_pypsa_index = cwd.parts.index('table_pypsa')
        path_to_table_pypsa = Path(*cwd.parts[:table_pypsa_index+1])
        config_file_path = str(path_to_table_pypsa / 'utilities' / 'cost_config.yaml')
    else:
        logging.error('Current directory is not table_pypsa and table_pypsa directory is not in current directory.')

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
            if attribute in component_attribute_dictionary[component].index:
                component_data_dict = read_component_data(component_data_dict, attribute, value, tech_name, costs)

        component_data_list.append(component_data_dict)
    return case_data_dict, component_data_list, component_attribute_dictionary
