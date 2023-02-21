import os, csv, pickle
import argparse, logging
import pypsa
import pandas as pd
from utilities import read_excel_file_to_dict

# Parse the input file as command line argument
parser = argparse.ArgumentParser()
parser.add_argument('-f', '--filename', help="Input csv case file", required=True)
args = parser.parse_args()
input_file = args.filename

"""
Scale all float in tech_list by a numerics_scaling excluding decay rate, efficiency and charging time
"""
def scale_by_numeric_factor(scale_factor, tech_list):
    for tech_dict in tech_list:
        for key, value in tech_dict.items():
            if type(value) == float:
                if key != "decay_rate" and key != "charging_time" and key != "efficiency":
                    tech_dict[key] = value * scale_factor

"""
Divide all dataframes in df_dict values by numerics_scaling if dataframe column has "cost", "$" or "Expenditure" in name
"""
def divide_results_by_numeric_factor(df_dict, scaling_factor):
    for results in df_dict:
        for col in df_dict[results].columns:
            if "cost" in col or "$" in col or "Expenditure" in col or "Revenue" in col:
                df_dict[results][col] = df_dict[results][col] / scaling_factor
    return df_dict

"""
Number of rows to skip until beginning of data in time series csv file
"""
def skip_until_begin_data(ts_file):
    with open(ts_file) as fin:
        # read to keyword 'BEGIN_DATA' and then one more line (header line)
        data_reader = csv.reader(fin)
        # Throw away all lines up to and include the line that has 'BEGIN_GLOBAL_DATA' in the first cell of the line
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
    ts['date'] = pd.to_datetime(ts[['day', 'month', 'year', 'hour']])
    ts = ts.set_index(['date'])
    ts.drop(columns=['day', 'month', 'year', 'hour'], inplace=True)
    ts = ts.loc[date_time_start: date_time_end]

    if ts.empty:
        logging.warning("Time series was not properly read in and dataframe is empty! Returning now.")
        return
    return ts

def add_buses_to_network(n, tech_list):
    # Add buses to network based on 'bus' in tech_list
    for tech_dict in tech_list:
        if "bus" in tech_dict:
            if tech_dict["bus"] not in n.buses.index:
                n.add("Bus", tech_dict["bus"])
    return n

"""
Define PyPSA network and add components based on input dictionaries
"""
def dicts_to_pypsa(case_dict, tech_list):
    # Set logging level
    logging.basicConfig(level=case_dict["logging_level"].upper())

    # Define PyPSA network
    n = pypsa.Network()

    # Add buses to network based on 'bus' in tech_list
    n = add_buses_to_network(n, tech_list)

    for tech_dict in tech_list:
        # for generators and loads, add time series to components
        if tech_dict["component"] == "Generator" or tech_dict["component"] == "Load":
            # Add time series to components
            if "time_series_file" in tech_dict:
                input_file = os.path.join(case_dict["input_path"],tech_dict["time_series_file"])
                ts = process_time_series_file(input_file, case_dict["datetime_start"], case_dict["datetime_end"])
                if ts is not None:
                    n.snapshots = ts.index
                    if tech_dict["component"] == "Generator":
                        tech_dict["p_max_pu"] = ts.iloc[:, 0]
                    elif tech_dict["component"] == "Load":
                        tech_dict["p_set"] = ts.iloc[:, 0]
                    tech_dict.pop("time_series_file")
                else:
                    logging.warning("Time series file not found for " + tech_dict["name"] + ". Skipping component.")
                    continue
        print("\nTech dict")
        print(tech_dict)

        # Add components to network based on tech_dict as attributes for network add function, excluding "component" and "name"
        n.add(tech_dict["component"], tech_dict["name"], **{k: v for k, v in tech_dict.items() if k != "component" and k != "name"})
    return n

"""
Write results to excel file and pickle file
"""
def write_results_to_file(case_dict, df_dict, n, scaling_factor):
    # Divide results by scaling factor
    df_dict = divide_results_by_numeric_factor(df_dict, scaling_factor)

    # Write results to excel file
    with pd.ExcelWriter(case_dict["output_file"]+".xlsx") as writer:
        for results in df_dict:
            df_dict[results].to_excel(writer, sheet_name=results)

    # Write results to pickle file
    with open(case_dict["output_file"]+".pickle", 'wb') as f:
        pickle.dump([case_dict, df_dict, n], f)

    # Logging info
    logging.info("Results written to file: " + case_dict["output_file"] + ".xlsx")
    logging.info("Results written to file: " + case_dict["output_file"] + ".pickle")

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
    system_cost = n.statistics()["Capital Expenditure"].sum() / case_dict["num_time_periods"] + n.statistics()[
        "Operational Expenditure"].sum()
    case_results_df = pd.DataFrame([[n.objective, system_cost]], columns=['objective [$]', 'system cost [$/h]'])

    # Collect results in one dictionary
    df_dict = {'time inputs': time_inputs_df, 'case results': case_results_df, 'tech results': n.statistics(),
               'time results': time_results_df}

    return df_dict


def main():
    # Read in xlsx case input file and translate to dictionaries
    case_dict, tech_list = read_excel_file_to_dict(input_file)

    print (case_dict)
    print ("\n", tech_list)

    # # Scale by numerics_scaling, this avoids rounding otherwise done in Gurobi for small numbers
    # scale_by_numeric_factor(case_dict["numerics_scaling"], tech_list)
    #
    # Define PyPSA network
    network = dicts_to_pypsa(case_dict, tech_list)
    pd.set_option('display.max_columns', None)
    print(network.generators)
    print(network.loads)

    # Solve the linear optimization power flow with Gurobi
    network.lopf(solver_name='gurobi')

    # # Postprocess results and write to excel, pickle
    # postprocess_results(network, case_dict)
    #
    # # Write results to excel file
    # write_results_to_file(case_dict, df_dict, network)


if __name__ == "__main__":
    main()
