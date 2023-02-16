import os, csv, pickle
import argparse, logging
import pypsa
import pandas as pd
from datetime import datetime
from Preprocess_Input import preprocess_input

pd.set_option('display.max_columns', None)
pd.set_option("display.precision", 8)
logging.basicConfig(level=logging.INFO)

# Parse the input file as command line argument
parser = argparse.ArgumentParser()
parser.add_argument('-f', '--filename', help="Input csv case file", required=True)
args = parser.parse_args()
input_file = args.filename


# Helper functions
##################################
def skip_until_begin_data(filename):
    with open(filename) as fin:
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


##################################
def replace_24th_hour(hour, day, month, year):
    if hour != 24:
        return hour, day, month, year
    else:
        new_hour = 0
        if day != 31:
            new_day = int(day) + 1
        else:
            new_day = 1
            if month != 12:
                new_month = month + 1
            else:
                new_month = 1
                new_year = year + 1
        return new_hour, new_day, new_month, new_year


##################################


def main():
    # Read in MEM case input file and translate to dictionaries
    case_dict, tech_list = preprocess_input(input_file)
    print(case_dict)
    print(tech_list)

    # Scale all float in tech_list by a numerics_scaling excluding decay rate, efficiency and charging time
    for tech_dict in tech_list:
        print(tech_dict)
        for key, value in tech_dict.items():
            if type(value) == float:
                if key != "decay_rate" and key != "charging_time" and key != "efficiency":
                    print(key, value)
                    tech_dict[key] = value * case_dict["numerics_scaling"]

    # Define PyPSA network
    n = pypsa.Network()

    for tech_dict in tech_list:

        # Read in time
        if tech_dict["tech_type"] != 'curtailment':
            start_date_time = "{0}-{1}-{2} {3}:00".format(case_dict["year_start"], case_dict["month_start"],
                                                          case_dict["day_start"], case_dict["hour_start"])
            hour_end, day_end, month_end, year_end = replace_24th_hour(case_dict["hour_end"], case_dict["day_end"],
                                                                       case_dict["month_end"], case_dict["year_end"])
            end_date_time = "{0}-{1}-{2} {3}:00".format(year_end, month_end, day_end, hour_end)

            # Read and format time series file
            if "series_file" in tech_dict.keys():
                ts_file = os.path.join(case_dict["data_path"], tech_dict["series_file"])
                skiprows = skip_until_begin_data(ts_file)
                ts = pd.read_csv(ts_file, parse_dates=False, sep=",", skiprows=skiprows)
                ts.columns = [x.lower() for x in ts.columns]
                ts['date'] = pd.to_datetime(ts[['day', 'month', 'year', 'hour']])
                ts = ts.set_index(['date'])
                ts.drop(columns=['day', 'month', 'year', 'hour'], inplace=True)

                # Get time range
                ts = ts.loc[start_date_time: end_date_time]
                n.snapshots = ts.index
                if ts.empty:
                    logging.warning("Time series was not properly read in and dataframe is empty! Returning now.")
                    return

            # Define busses (==nodes in MEM)
            bus_name = tech_dict["tech_name"].split("_")[0] + "_" + tech_dict["tech_name"].split("_")[1]
            if not bus_name in list(n.buses.index.values):
                n.add("Bus", bus_name)

            # Define generator(s)
            if "generator" in tech_dict["tech_type"] or "lost_load" in tech_dict["tech_type"]:

                n.add(
                    "Generator",
                    tech_dict["tech_name"],
                    bus=bus_name,
                    carrier=tech_dict["tech_name"],
                    p_max_pu=ts.iloc[:, 0] if "series_file" in tech_dict.keys() else 1.,
                    efficiency=tech_dict["efficiency"] if "efficiency" in tech_dict.keys() else 1.,
                    capital_cost=case_dict["num_time_periods"] * tech_dict[
                        "fixed_cost"] if "fixed_cost" in tech_dict.keys() else 0.,  # €/MW/a
                    marginal_cost=tech_dict["var_cost"] if "var_cost" in tech_dict.keys() else 0.,  # €/MWh_e
                    p_nom_extendable=True,
                )

            # Define demand(s)
            elif "demand" in tech_dict["tech_type"]:
                n.add(
                    "Load",
                    tech_dict["tech_name"],
                    bus=bus_name,
                    carrier=tech_dict["tech_name"],
                    p_set=ts.iloc[:, 0],
                )

            # Define transmission(s) and/or transfer(s)
            elif "transmission" in tech_dict["tech_type"] or "transfer" in tech_dict["tech_type"]:
                n.add("Link",
                      tech_dict["tech_name"],
                      bus0=tech_dict["node_from"],
                      bus1=tech_dict["node_to"],
                      carrier=tech_dict["tech_name"],
                      p_nom_extendable=True,
                      efficiency=tech_dict["efficiency"] if "efficiency" in tech_dict.keys() else 1.,
                      capital_cost=case_dict["num_time_periods"] * tech_dict[
                          "fixed_cost"] if "fixed_cost" in tech_dict.keys() else 0.,  # €/MW/a
                      marginal_cost=tech_dict["var_cost"] if "var_cost" in tech_dict.keys() else 0.,  # €/MWh_e
                      p_min_pu=-1 if "transmission" in tech_dict["tech_type"] else 0.,
                      )

            # Define storage(s)
            elif "storage" in tech_dict["tech_type"]:
                print("Standing loss from file: ", tech_dict["decay_rate"])
                n.add(
                    "StorageUnit",
                    tech_dict["tech_name"],
                    bus=bus_name,
                    carrier=tech_dict["tech_name"],
                    capital_cost=tech_dict["charging_time"] * case_dict["num_time_periods"] * tech_dict[
                        "fixed_cost"] if "fixed_cost" in tech_dict.keys() else 0.,  # €/MW/a
                    p_nom_extendable=True,
                    efficiency_store=tech_dict["efficiency"],
                    cyclic_state_of_charge=True,  # cyclic state of charge
                    max_hours=tech_dict["charging_time"],
                    standing_loss=tech_dict["decay_rate"],
                )

            else:
                print("\nThis technology is not included: ", tech_dict["tech_name"])

        # Curtailment is computed as difference of production - demand


    print("Storage in network", n.storage_units)
    print(n.generators)


    # Solve the linear optimization power flow with Gurobi
    n.lopf(solver_name='gurobi')  # , solver_options={'seed': 42})

    # Collect output in dataframes
    time_inputs_df = n.generators_t["p_max_pu"]
    time_inputs_df = time_inputs_df.rename(columns=dict(zip(n.generators_t["p_max_pu"].columns.to_list(),
                                                            [name + " series" for name in
                                                             n.generators_t["p_max_pu"].columns.to_list()])))
    time_inputs_df = pd.concat([time_inputs_df, n.loads_t["p_set"].rename(columns=dict(
        zip(n.loads_t["p_set"].columns.to_list(), [name + " load" for name in n.loads_t["p_set"].columns.to_list()])))],
                               axis=1)

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
            [name + " dispatch" for name in n.storage_units_t["p_dispatch"].columns.to_list()])))], axis=1)
    time_results_df = pd.concat([time_results_df, n.storage_units_t["state_of_charge"].rename(columns=dict(
        zip(n.storage_units_t["state_of_charge"].columns.to_list(),
            [name + " state of charge" for name in n.storage_units_t["state_of_charge"].columns.to_list()])))], axis=1)
    time_results_df.insert(0, "time index", time_results_df.reset_index().index)

    system_cost = n.statistics()["Capital Expenditure"].sum() / case_dict["num_time_periods"] + n.statistics()[
        "Operational Expenditure"].sum()
    case_results_df = pd.DataFrame([[n.objective, system_cost]], columns=['objective [$]', 'system cost [$/h]'])

    # Write output
    output_name = "output_" + case_dict["case_name"].replace("inter","")
    output_folder = os.path.join("output_data/", output_name)
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    df_dict = {'time inputs': time_inputs_df, 'case results': case_results_df, 'tech results': n.statistics(),
               'time results': time_results_df}
    print(df_dict['tech results'])
    # Divide all dataframes in df_dict values by numerics_scaling if dataframe column has "cost", "$" or "Expenditure" in name
    for results in df_dict:
        for col in df_dict[results].columns:
            if "cost" in col or "$" in col or "Expenditure" in col or "Revenue" in col:
                df_dict[results][col] = df_dict[results][col] / case_dict["numerics_scaling"]
    print(df_dict['tech results'])

    excel_writer = pd.ExcelWriter(os.path.join(output_folder, output_name + ".xlsx"), engine='xlsxwriter')
    for results in df_dict:
        df_dict[results].to_excel(excel_writer, sheet_name=results)
    excel_writer.save()
    with open(os.path.join(output_folder, output_name + ".pickle"), 'wb') as f:
        pickle.dump(df_dict, f)


if __name__ == "__main__":
    main()
