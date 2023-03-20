import pickle
import argparse,logging
import pypsa
import pandas as pd
from utilities.read_input import read_input_file_to_dict
from utilities.utilities import *

# Parse the input file as command line argument
parser = argparse.ArgumentParser()
parser.add_argument('-f', '--filename', help="Input case file (xlsx or csv)", required=True)
args = parser.parse_args()
input_file = args.filename


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
Read in time series file and format as pandas dataframe and return dataframe if not empty.
"""
def process_time_series_file(ts_file, date_time_start, date_time_end):
    skiprows = skip_until_keyword(ts_file, 'BEGIN_DATA')
    ts = pd.read_csv(ts_file, parse_dates=False, sep=",", skiprows=skiprows)
    ts.columns = [x.lower() for x in ts.columns]
    ts['date'] = pd.to_datetime(ts[['day', 'month', 'year', 'hour']])
    ts = ts.set_index(['date'])
    ts.drop(columns=['day', 'month', 'year', 'hour'], inplace=True)
    ts = ts.loc[date_time_start: date_time_end]

    # Check dtype of time series
    if ts.dtypes[0] != 'float64':
        ts = ts.astype(float)

    if ts.empty:
        logging.warning("Time series was not properly read in and dataframe is empty! Returning now.")
        return
    return ts

def add_buses_to_network(n, component_list):
    # Add buses to network based on 'bus' and 'bus1' in component_list
    for component_dict in component_list:
        if "bus" in component_dict:
            if component_dict["bus"] not in n.buses.index:
                n.add("Bus", component_dict["bus"])
        if "bus1" in component_dict:
            if component_dict["bus1"] not in n.buses.index:
                n.add("Bus", component_dict["bus1"])
    return n

"""
Define PyPSA network and add components based on input dictionaries
"""
def dicts_to_pypsa(case_dict, component_list, component_attr):
    # Define PyPSA network
    n = pypsa.Network(override_component_attrs=component_attr)

    # Add buses to network based on 'bus' in component_list
    n = add_buses_to_network(n, component_list)

    for component_dict in component_list:
        # for generators and loads, add time series to components
        if component_dict["component"] == "Generator" or component_dict["component"] == "Load":
            # Add time series to components
            if "time_series_file" in component_dict:
                input_file = os.path.join(case_dict["input_path"],component_dict["time_series_file"])
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
        if component_dict["component"] in ["Generator", "StorageUnit", "Link"]:
            if "p_nom" not in component_dict:
                component_dict["p_nom_extendable"] = True
        elif component_dict["component"] == "Store":
                if "e_nom" not in component_dict:
                    component_dict["e_nom_extendable"] = True

        # Default carrier to component name if not defined
        if "carrier" not in component_dict:
            component_dict["carrier"] = component_dict["name"]

        # Add components to network based on component_dict as attributes for network add function, excluding "component" and "name"
        n.add(component_dict["component"], component_dict["name"], **{k: v for k, v in component_dict.items() if k != "component" and k != "name"})
    return n

"""
Write results to excel file and pickle file
"""
def write_results_to_file(case_dict, df_dict):

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
    time_results_df = pd.concat([time_results_df, n.stores_t["e"].rename(columns=dict(
        zip(n.stores_t["e"].columns.to_list(),
            [name + " state of charge" for name in n.stores_t["e"].columns.to_list()])))], axis=1)
    time_results_df = pd.concat([time_results_df, n.links_t["p0"].rename(columns=dict(
        zip(n.links_t["p0"].columns.to_list(),
            [name + " dispatch" for name in n.links_t["p0"].columns.to_list()])))], axis=1)

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
    # Read in case input file and translate to dictionaries
    case_dict, component_list, component_attributes = read_input_file_to_dict(input_file)

    # Define PyPSA network
    network = dicts_to_pypsa(case_dict, component_list, component_attributes)

    # Solve the linear optimization power flow with Gurobi
    network.lopf(solver_name='gurobi')

    # Postprocess results and write to excel, pickle
    output_df_dict = postprocess_results(network, case_dict)

    # Write results to excel file
    write_results_to_file(case_dict, output_df_dict)

if __name__ == "__main__":
    main()
