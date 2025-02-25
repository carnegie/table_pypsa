import pypsa
import pickle
import argparse,logging
from pathlib import Path
import os, sys
import pandas as pd

# note in GitHub action the cwd is /home/runner/work/table_pypsa/table_pypsa

# if running as .exe from the dist/run_pypsa dir cd to the table_pypsa dir
cwd = Path.cwd()
if cwd.parts[-1] == 'run_pypsa':
    os.chdir('../..')  # move up to table_pypsa
    
# import always relative to the current file
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# if not in table_pypsa directory add it to the sys.path
cwd = Path.cwd()
if not cwd.parts[-1]=='table_pypsa' and 'table_pypsa' in os.listdir():
    # add path to table_pypsa to sys.path
    sys.path.append(str(cwd / 'table_pypsa'))
    
from utilities.read_input import read_input_file_to_dict
from utilities.utilities import skip_until_keyword, get_output_filename, stats_add_units, add_carrier_info


def scale_normalize_time_series(component_dict, scaling_factor=1.):
    """
    Scale all float in component_list by a numerics_scaling excluding decay rate, efficiency and charging time
    """
    # Scale all pandas series in component_list by numerics_scaling and normalize by normalization factor
    for key in component_dict:
        if key == "p_set" or key == "p_max_pu":
            # Normalize time series by normalization factor if defined
            if type(component_dict[key]) is pd.Series:
                normalization = component_dict['normalization'] / component_dict[key].mean() if 'normalization' in component_dict else 1.
                component_dict[key] *= normalization 
            # Scale by numerics_scaling, this avoids rounding otherwise done in Gurobi for small numbers
            if type(component_dict[key]) is pd.Series or "capital_cost" in key:
                component_dict[key] *= scaling_factor
    return component_dict


def divide_results_by_numeric_factor(df_dict, scaling_factor):
    """
    Divide time series and costs in result dataframes in df_dict by scaling_factor
    """
    for results in df_dict:
        if "time" in results or "results" in results:
            result = df_dict[results]
            for col in result.columns:
                if "carrier" in col:
                    continue
                if "Capacity Factor" in col or "Optimal Capacity" in col or "Curtailment" in col:
                    if "Optimal Capacity" in col:
                        result[col] /= scaling_factor
                    # Scale capacity factor only when carrier is also in time inputs
                    for carr in result.index.get_level_values(1).unique():
                        if carr+" series" in df_dict["time inputs"].columns:
                            if not "Optimal Capacity" in col:
                                # Divide by scaling factor
                                result.loc[result.index.get_level_values(1) == carr, col] /= scaling_factor
                            else:
                                # Unscale if has time series
                                result.loc[result.index.get_level_values(1) == carr, col] *= scaling_factor
                else:
                    result[col] /= scaling_factor        
    return df_dict


def process_time_series_file(ts_file, date_time_start, date_time_end):
    """
    Read in time series file and format as pandas dataframe and return dataframe if not empty.
    """
    skiprows = skip_until_keyword(ts_file, 'BEGIN_DATA')

    ts = pd.read_csv(ts_file, parse_dates=False, sep=",", skiprows=skiprows)
    ts.columns = [x.lower() for x in ts.columns]
    
    # Assume first column is datetime unless 'hour' is present
    if not 'hour' in ts.columns:
        ts['date'] = pd.to_datetime(ts[ts.columns[0]])
        ts.drop(columns=[ts.columns[0]], inplace=True)
        # Drop raw demand if present
        if 'raw demand (mw)' in ts.columns:
            ts.drop(columns=['raw demand (mw)'], inplace=True)
    else:
        # Date as 'day', 'month', 'year' and 'hour' columns
        # This corresponds to the format of the time series files from MEM (developed by CLab)
        ts['hour'] = ts['hour'] - 1  # convert MEM 1..24 to py 0..23
        ts['date'] = pd.to_datetime(ts[['day', 'month', 'year', 'hour']])
        ts.drop(columns=['day', 'month', 'year', 'hour'], inplace=True)


    ts.set_index('date', inplace=True)

    # Check if time series exists and covers the whole time period
    if ts.empty:
        logging.warning("Time series was not properly read in and dataframe is empty! Returning now.")
        return
    # Add warning when time series doesn't cover the whole time period
    elif date_time_start not in ts.index or date_time_end not in ts.index:
        logging.warning("Time series doesn't cover the whole time period. Returning now.")
        return
    else:
        ts = ts.loc[date_time_start: date_time_end]

    return ts

def add_buses_to_network(n, component_list):
    # Add buses to network based on 'bus' and 'bus1' in component_list
    for component_dict in component_list:
        for bus_key in ["bus", "bus1"]:
            bus_value = component_dict.get(bus_key)
            if bus_value and bus_value not in n.buses.index:
                n.add("Bus", bus_value, carrier=bus_value)
            if bus_value and bus_value not in n.carriers.index:
                n.add("Carrier", bus_value)
    return n


def dicts_to_pypsa(case_dict, component_list, component_attr):
    """
    Define PyPSA network and add components based on input dictionaries
    """
    # Define PyPSA network
    n = pypsa.Network(override_component_attrs=component_attr)

    # Add buses to network based on 'bus' in component_list
    n = add_buses_to_network(n, component_list)

    for component_dict in component_list:
        # for generators and loads, add time series to components
        for attr in component_dict:
            # Add time series to components
            if isinstance(component_dict[attr], str) and ".csv" in component_dict[attr]:
                logging.info("Reading time series file for {0} of {1}.".format(attr, component_dict["name"]))
                factor = component_dict[attr].split("*")[0] if "*" in component_dict[attr] else 1
                component_dict[attr] = component_dict[attr].split("*")[1] if "*" in component_dict[attr] else component_dict[attr]
                ts_file = os.path.join(case_dict["input_path"],component_dict[attr])
                if not os.path.exists(ts_file):
                    logging.error("Time series file not found for {0} in path {1}. Exiting now.".format(component_dict[attr], ts_file))
                    sys.exit(1)
                try:
                    ts = process_time_series_file(ts_file, case_dict["datetime_start"], case_dict["datetime_end"])
                except Exception: 
                    logging.error("Didn't process time series file {0} accurately. Exiting now.".format(component_dict[attr]))
                    sys.exit(1)
                if ts is not None:
                    # Include time series as snapshots taking every delta_t value
                    n.snapshots = ts.iloc[::case_dict['delta_t'], :].index if case_dict['delta_t'] else ts.index
                    # Add time series to component
                    component_dict[attr] = ts.iloc[:, 0] * float(factor)

                    # Scale by numerics_scaling, this avoids rounding otherwise done in Gurobi for small numbers and normalize time series if needed
                    component_dict = scale_normalize_time_series(component_dict, case_dict["numerics_scaling"])                 
                else:
                    logging.warning("Time series is None. Exiting now.")
                    sys.exit(1)

        # Without time series file, set snaphsots to number of time steps defined in the input file
        if len(n.snapshots) == 1 and case_dict["no_time_steps"] is not None:
            n.set_snapshots(range(int(round(case_dict["no_time_steps"]))))

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
        # Add carrier to network if not already in network
        if component_dict["carrier"] not in n.carriers.index:
            n.add("Carrier", component_dict["carrier"])

        # Add components to network based on component_dict as attributes for network add function, excluding "component" and "name"
        n.add(component_dict["component"], component_dict["name"], **{k: v for k, v in component_dict.items() if k != "component" and k != "name"})
    return n


def write_results_to_file(infile, outfile, component_input_list, df_dict):
    """
    Write results to excel file and pickle file
    """
    # Write results to excel file
    # If input was read from output, change name
    if infile == outfile+".xlsx":
        outfile = outfile + "_rerun"
    with pd.ExcelWriter(outfile+".xlsx") as writer:
        # Copy infile to first sheet of output file
        if infile.endswith('.xlsx'):
            input_df = pd.read_excel(infile, sheet_name=0)
        else:  # csv
            input_df = pd.read_csv(infile)
        # Column names
        headers = ["PyPSA case input file"] + (len(input_df.columns)-1) * [""]
        input_df.to_excel(writer, sheet_name="input file", index=False, header=headers)
        # Write component list to excel file which includes the cost values
        pd.DataFrame(component_input_list).to_excel(writer, index=False, sheet_name="component inputs")
        # Write results to excel file
        for results in df_dict:
            if results == "case results":
                df_dict[results].to_excel(writer, sheet_name=results, index=False)
            else:
                df_dict[results].to_excel(writer, sheet_name=results)

    # Write results to pickle file
    with open(outfile+".pickle", 'wb') as f:
        pickle.dump(df_dict, f)

    # Logging info
    logging.info("Results written to file: " + outfile + ".xlsx")
    logging.info("Results written to file: " + outfile + ".pickle")
    

def postprocess_results(n, case_dict):
    """
    Postprocess results and collect in dataframes
    """
    # Collect generators_t["p_max_pu"] and loads_t["p_set"] in one input dataframe, renaming columns to include "series" or "load"
    time_inputs_df = n.generators_t["p_max_pu"]
    time_inputs_df = time_inputs_df.rename(columns=dict(zip(n.generators_t["p_max_pu"].columns.to_list(),
                                                            [name + " series" for name in
                                                             n.generators_t["p_max_pu"].columns.to_list()])))
    time_inputs_df = pd.concat([time_inputs_df, n.loads_t["p_set"].rename(columns=dict(
        zip(n.loads_t["p_set"].columns.to_list(), [name + " load" for name in n.loads_t["p_set"].columns.to_list()])))], axis=1)
    time_inputs_df = pd.concat([time_inputs_df, n.generators_t["marginal_cost"].rename(columns=dict(
        zip(n.generators_t["marginal_cost"].columns.to_list(),
            [name + " marginal cost" for name in n.generators_t["marginal_cost"].columns.to_list()])))], axis=1)
    time_inputs_df = pd.concat([time_inputs_df, n.links_t["marginal_cost"].rename(columns=dict(
        zip(n.links_t["marginal_cost"].columns.to_list(),
            [name + " marginal cost" for name in n.links_t["marginal_cost"].columns.to_list()])))], axis=1)

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
            [name + " e" for name in n.stores_t["e"].columns.to_list()])))], axis=1)
    time_results_df = pd.concat([time_results_df, n.links_t["p0"].rename(columns=dict(
        zip(n.links_t["p0"].columns.to_list(),
            [name + " dispatch" for name in n.links_t["p0"].columns.to_list()])))], axis=1)
    time_results_df = pd.concat([time_results_df, n.buses_t["marginal_price"].rename(columns=dict(
        zip(n.buses_t["marginal_price"].columns.to_list(),
            [name + " marginal cost" for name in n.buses_t["marginal_price"].columns.to_list()])))], axis=1)

    # Collect objective and system cost in one dataframe
    system_cost = (n.statistics()["Capital Expenditure"].sum() + n.statistics()[
        "Operational Expenditure"].sum()) / case_dict["total_hours"]
    case_results_df = pd.DataFrame([[n.objective, system_cost]], columns=['objective [{0}]'.format(case_dict["currency"]), 'system cost [{0}/{1}]'.format(case_dict["currency"], case_dict["time_unit"])])

    # Include component statistics also if 0 after optimization
    n.statistics.set_parameters(drop_zero=False)
    # Add units
    statistics_df = stats_add_units(n.statistics, case_dict)
    # Add column with carrier to statistics_df
    statistics_df = add_carrier_info(n, statistics_df)

    # Collect results in one dictionary
    df_dict = {'time inputs': time_inputs_df, 'case results': case_results_df, 'component results': statistics_df,
               'time results': time_results_df}

    # Divide results by scaling factor
    df_dict = divide_results_by_numeric_factor(df_dict, case_dict["numerics_scaling"])

    return df_dict


def add_bicharger_constraint(m, n):
    """
    Add constraint requiring the same sizing for charging and discharging power
    """
    # Add bi-directional charging constraint if bicharger in name of component

    # Filter links with 'bicharger' in their name
    bicharger_links = [link for link in n.links.index if 'bicharger' in link]

    # Create a dictionary to store matching charger-discharger pairs
    bicharger_pairs = {}

    # Search for matching charger-discharger pairs based on the prefix before '-bicharger'
    for link in bicharger_links:
        # Extract the prefix, assuming the format is '*-bicharger'
        prefix = link.split('-bicharger')[0]
        possible_matches = [l for l in bicharger_links if l.startswith(prefix) and l != link]
    
        # If a matching pair is found, store it
        if possible_matches and not prefix in bicharger_pairs:
            bicharger_pairs[prefix] = (link, possible_matches[0]) 

    # Add constraints for each matching pair
    for prefix, (charger_link, discharger_link) in bicharger_pairs.items():
        # Get the power and efficiency values for the charger and discharger
        logging.info(f"Found bi-directional charging pair for {prefix}: {charger_link} and {discharger_link}")
        p_charger = m.variables['Link-p_nom'].at[charger_link]
        p_discharger = m.variables['Link-p_nom'].at[discharger_link]
        efficiency = n.links.at[discharger_link, 'efficiency']
        logging.info(f"Charger power: {p_charger}, discharger power: {p_discharger}, Efficiency: {efficiency}")

        # Define the symbolic expression for the constraint (without evaluation)
        constraint_expression = p_charger - p_discharger * efficiency
        # Add the constraint
        m.add_constraints(lhs=constraint_expression, sign="=", rhs=0, name="bicharger_constraint_" + prefix)

    return m

def build_network(infile):
    """ infile: string path for .xlsx or .csv case file """
    
    # Read in case input file and translate to dictionaries
    case_dict, component_list, component_attributes = read_input_file_to_dict(infile)

    # Define PyPSA network
    network = dicts_to_pypsa(case_dict, component_list, component_attributes)

    return network, case_dict, component_list, component_attributes


def run_pypsa(network, case_dict):

    # Solve the linear optimization power flow with Gurobi
    model = network.optimize.create_model()
    model = add_bicharger_constraint(model, network)
    network.optimize.solve_model(solver_name=case_dict['solver'])

    # Check if optimization was successful
    if not hasattr(network, 'objective'):
        logging.warning("Optimization was not successful! Returning now.")
        return


def write_result(network, case_dict, component_list, infile, outfile_suffix=""):

    # Postprocess results and write to excel, pickle
    output_df_dict = postprocess_results(network, case_dict)

    # Get output path and filename
    output_file = get_output_filename(case_dict) + outfile_suffix
    # Write results to file
    write_results_to_file(infile, output_file, component_list, output_df_dict)

    # Save network to .nc file
    # network.export_to_netcdf(output_file + ".nc")


if __name__ == "__main__":
    # Parse the input file as command line argument
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--filename', help="Input case file (xlsx or csv)", required=True)
    args = parser.parse_args()
    input_file = args.filename
    
    # Run PyPSA
    n, c_dict, comp_list, comp_attrs = build_network(input_file)
    run_pypsa(n, c_dict)
    write_result(n, c_dict, comp_list, input_file)
