import os, csv, pickle
import argparse, logging
import pypsa
import pandas as pd
from utilities import read_excel_file_to_dict
import sys, platform

# Parse the input file as command line argument
"""  bh 5mar23
parser = argparse.ArgumentParser()
parser.add_argument('-f', '--filename', help="Input csv case file", required=True)
args = parser.parse_args()
input_file = args.filename
"""
input_file = "test_case.xlsx"  # BH replace above

"""
Check if directory exists, if not create it
"""
def check_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

"""
Scale all float in component_list by a numerics_scaling excluding decay rate, efficiency and charging time
"""
def scale_normalize_time_series(scale_factor, component_dict):
    # Scale all pandas series in component_list by numerics_scaling and normalize by normalization factor
    for key in component_dict:
        if type(component_dict[key]) is pd.Series or "cost" in key:
            normalization = component_dict['normalization'] / component_dict[key].mean() if 'normalization' in component_dict else 1.
            component_dict[key] = component_dict[key] * scale_factor * normalization
    return component_dict

"""
Divide all dataframes in df_dict values by numerics_scaling if dataframe column has "cost", "$" or "Expenditure" in name
"""
def divide_results_by_numeric_factor(df_dict, scaling_factor):
    for results in df_dict:
        for col in df_dict[results].columns:
            if not "capacity factor" in col.lower():
                df_dict[results][col] = df_dict[results][col] / scaling_factor
    return df_dict

"""
Number of rows to skip until beginning of data in time series csv file
"""
def skip_until_begin_data(ts_file):
    with open(ts_file) as fin:
        # read to keyword 'BEGIN_DATA' and then one more line (header line)
        data_reader = csv.reader(fin)
        line_index = 1
        while True:
            line = next(data_reader)
            if line[0] == 'BEGIN_DATA':
                return line_index
            else:
                line_index += 1

"""
Read in time series file and format as pandas dataframe and return dataframe if not empty.
"""
def process_time_series_file(ts_file, date_time_start, date_time_end):
    skiprows = skip_until_begin_data(ts_file)
    ts = pd.read_csv(ts_file, parse_dates=False, sep=",", skiprows=skiprows)
    ts.columns = [x.lower() for x in ts.columns]    
    
    ts['hour'] = ts['hour'] - 1 # convert MEM 1..24 to Py 0..23
    
    ts['date'] = pd.to_datetime(ts[['day', 'month', 'year', 'hour']])    
    ts = ts.set_index(['date'])
    ts.drop(columns=['day', 'month', 'year', 'hour'], inplace=True)
    ts = ts.loc[date_time_start: date_time_end]

    if ts.empty:
        logging.warning("Time series was not properly read in and dataframe is empty! Returning now.")
        return
    return ts

def add_buses_to_network(n, component_list):
    # Add buses to network based on 'bus' in component_list
    for component_dict in component_list:
        if "bus" in component_dict:
            if component_dict["bus"] not in n.buses.index:
                n.add("Bus", component_dict["bus"])
    return n

"""
Define PyPSA network and add components based on input dictionaries
"""
def dicts_to_pypsa(case_dict, component_list):
    # Define PyPSA network
    n = pypsa.Network()

    # Add buses to network based on 'bus' in component_list
    n = add_buses_to_network(n, component_list)

    for component_dict in component_list:
        # for generators and loads, add time series to components
        if component_dict["component"] == "Generator" or component_dict["component"] == "Load":
            # Add time series to components
            if "time_series_file" in component_dict:
                #BH input_file = os.path.join(case_dict["input_path"],component_dict["time_series_file"])
                input_file = "solar.csv"
                ts = process_time_series_file(input_file, case_dict["datetime_start"], case_dict["datetime_end"])
                if ts is not None:
                    # Include time series as snapshots taking every delta_t value
                    n.snapshots = ts.iloc[::case_dict['delta_t'], :].index if case_dict['delta_t'] else ts.index
                    # Add time series to component
                    if component_dict["component"] == "Generator":
                        component_dict["p_max_pu"] = ts.iloc[:, 0]
                    elif component_dict["component"] == "Load":
                        component_dict["p_set"] = ts.iloc[:, 0]
                    # Remove time_series_file from component_dict
                    component_dict.pop("time_series_file")
                    # Scale by numerics_scaling, this avoids rounding otherwise done in Gurobi for small numbers and normalize time series
                    component_dict = scale_normalize_time_series(case_dict["numerics_scaling"], component_dict)
                else:
                    logging.warning("Time series file not found for " + component_dict["name"] + ". Skipping component.")
                    continue

        # Add p_nom_extendable attribute to generators, storages and links if p_nom is not defined
        if component_dict["component"] == "Generator" or component_dict["component"] == "StorageUnit" or component_dict["component"] == "Link":
            if "p_nom" not in component_dict:
                component_dict["p_nom_extendable"] = True

        # Add components to network based on component_dict as attributes for network add function, excluding "component" and "name"
        n.add(component_dict["component"], component_dict["name"], **{k: v for k, v in component_dict.items() if k != "component" and k != "name"})
    return n

"""
Write results to excel file and pickle file
"""
def write_results_to_file(case_dict, df_dict, n):

    # Write results to excel file
    check_directory(case_dict["output_path"])
    check_directory(os.path.join(case_dict["output_path"], case_dict["case_name"]))
    output_file = os.path.join(case_dict["output_path"], case_dict["case_name"], case_dict["filename_prefix"])

    with pd.ExcelWriter(output_file+".xlsx") as writer:
        for results in df_dict:
            df_dict[results].to_excel(writer, sheet_name=results)

    # Write results to pickle file
    with open(output_file+".pickle", 'wb') as f:
        pickle.dump(df_dict, f)

    # Logging info
    logging.info("Results written to file: " + output_file + ".xlsx")
    logging.info("Results written to file: " + output_file + ".pickle")

"""
Postprocess results and collect in dataframes
"""
def postprocess_results(n, case_dict):
    # Collect generators_t["p_max_pu"] and loads_t["p_set"] in one input dataframe, renaming columns to include "series" or "load"
    time_inputs_df = n.generators_t["p_max_pu"]
    time_inputs_df = time_inputs_df.rename(columns=dict(zip(n.generators_t["p_max_pu"].columns.to_list(),
                                                            [name + " series" for name in
                                                             n.generators_t["p_max_pu"].columns.to_list()])))
    time_inputs_df = pd.concat([time_inputs_df, n.loads_t["p_set"].rename(columns=dict(
        zip(n.loads_t["p_set"].columns.to_list(), [name + " load" for name in n.loads_t["p_set"].columns.to_list()])))], axis=1)

    # Collect generator dispatch, load, storage charged, storage dispatch and storage state of charge in one output dataframe
    time_results_df = n.generators_t["p"]
    time_results_df = time_results_df.rename(columns=dict(zip(n.generators_t["p"].columns.to_list(),
                                                             [name + " dispatch" for name in
                                                              n.generators_t["p"].columns.to_list()])))
    time_results_df = pd.concat([time_results_df, n.loads_t["p"].rename(columns=dict(
        zip(n.loads_t["p"].columns.to_list(), [name + " load" for name in n.loads_t["p"].columns.to_list()])))], axis=1)
    time_results_df = pd.concat([time_results_df, n.storage_units_t["p_store"].rename(columns=dict(
        zip(n.storage_units_t["p_store"].columns.to_list(),
            [name + " charged" for name in n.storage_units_t["p_store"].columns.to_list()])))], axis=1)
    time_results_df = pd.concat([time_results_df, n.storage_units_t["p_dispatch"].rename(columns=dict(
        zip(n.storage_units_t["p_dispatch"].columns.to_list(),
            [name + " discharged" for name in n.storage_units_t["p_dispatch"].columns.to_list()])))], axis=1)
    time_results_df = pd.concat([time_results_df, n.storage_units_t["state_of_charge"].rename(columns=dict(
        zip(n.storage_units_t["state_of_charge"].columns.to_list(),
            [name + " state of charge" for name in n.storage_units_t["state_of_charge"].columns.to_list()])))], axis=1)

    # Collect objective and system cost in one dataframe
    system_cost = n.statistics()["Capital Expenditure"].sum() / case_dict["total_hours"] + n.statistics()[
        "Operational Expenditure"].sum()
    case_results_df = pd.DataFrame([[n.objective, system_cost]], columns=['objective [$]', 'system cost [$/h]'])

    # Collect results in one dictionary
    df_dict = {'time inputs': time_inputs_df, 'case results': case_results_df, 'component results': n.statistics(),
               'time results': time_results_df}

    # Divide results by scaling factor
    df_dict = divide_results_by_numeric_factor(df_dict, case_dict["numerics_scaling"])

    return df_dict


def main():
    # Read in xlsx case input file and translate to dictionaries
    #BH 15mar causes unpack error:  case_dict, component_list = read_excel_file_to_dict(input_file)
    case_dict, component_list, *the_rest = read_excel_file_to_dict(input_file)

    # Define PyPSA network
    network = dicts_to_pypsa(case_dict, component_list)

    # Solve the linear optimization power flow with Gurobi
    print("Running network.lopf(solver_name='gurobi')")
    # Capture output to lopf_output.txt
    if platform.system() == 'Windows':
        stdout_copy = sys.stdout
        with open('lopf_output.txt', 'w') as sys.stdout:
            network.lopf(solver_name='gurobi')
        sys.stdout = stdout_copy  # restore stdout
    else:  # Linux
        network.lopf(solver_name='gurobi') > 'lopf_output.txt'
    print('Wrote to lopf_output.txt')
    
    # Postprocess results and write to excel, pickle
    output_df_dict = postprocess_results(network, case_dict)

    # Write results to excel file
    write_results_to_file(case_dict, output_df_dict, network)


def get_expected_table(filename):
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


if __name__ == "__main__":
    main()
    # Compare output to expected output
    expected_filename = "solar output Py format.txt"
    output_filename = "lopf_output.txt"
    
    expected_table = get_expected_table(expected_filename)
    lopf_table = get_expected_table(output_filename)
    same = expected_table == lopf_table
    print('='*30)
    if same:
        print('OK: output matches expected', )
    else:
        print('ERROR: output does not match expected')
        print('Non-matching lines:')
        for exp, actual in zip(expected_table, lopf_table):
            if exp != actual:
                print('SB ', exp)
                print('WAS', actual)
                print()
    print('='*30)