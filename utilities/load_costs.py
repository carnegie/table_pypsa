# Modified from: https://github.com/PyPSA/pypsa-eur/blob/master/scripts/add_electricity.py

import pandas as pd
import yaml

def calculate_annuity(n, r):
    """
    Calculate the annuity factor for an asset with lifetime n years and.

    discount rate of r, e.g. annuity(20, 0.05) * 20 = 1.6
    """
    if isinstance(r, pd.Series):
        return pd.Series(1 / n, index=r.index).where(
            r == 0, r / (1.0 - 1.0 / (1.0 + r) ** n)
        )
    elif r > 0:
        return r / (1.0 - 1.0 / (1.0 + r) ** n)
    else:
        return 1 / n

def load_costs(tech_costs, config, Nyears=1.0):
    """
    Create and return a costs dataframe loaded from the tech_costs file
    config: a yaml file
    """
    
    # Read in costs from csv file
    costs = pd.read_csv(tech_costs, index_col=[0, 1]).sort_index()

    # Load config files
    import os
    print('32: config:', config)
    print('33: /home/runner/work contents:', os.listdir('/home/runner/work'))
    print('34: /home/runner/work/clab_pypsa contents:', os.listdir('/home/runner/work/clab_pypsa'))
    print('35: /home/runner/work/clab_pypsa/clab_pypsa contents:', os.listdir('/home/runner/work/clab_pypsa/clab_pypsa'))
    print()
    print('36: utilities dir:', os.listdir('/home/runner/work/clab_pypsa/utilities'))
    try:  # TEMP 9may23 debug why doesn't find .yaml file
        with open(config, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print("40: EXC", e)
        print('  config:', config)
        print('37: cwd:', os.getcwd())
        print('-- cwd files --')
        for fname in os.listdir():
            print('  ', fname)
        print('-----------------')
        import sys
        sys.exit()

    # correct units to MW
    costs.loc[costs.unit.str.contains("/kW"), "value"] *= 1e3
    costs.unit = costs.unit.str.replace("/kW", "/MW")

    fill_values = config["fill_values"]
    costs = costs.value.unstack().fillna(fill_values)

    costs["capital_cost"] = (
        (
            calculate_annuity(costs["lifetime"], costs["discount rate"])
            + costs["FOM"] / 100.0
        )
        * costs["investment"]
        * Nyears
    )

    costs.at["OCGT", "fuel"] = costs.at["gas", "fuel"]
    costs.at["CCGT", "fuel"] = costs.at["gas", "fuel"]

    costs["marginal_cost"] = costs["VOM"] + costs["fuel"] / costs["efficiency"]

    costs = costs.rename(columns={"CO2 intensity": "co2_emissions"})

    costs.at["OCGT", "co2_emissions"] = costs.at["gas", "co2_emissions"]
    costs.at["CCGT", "co2_emissions"] = costs.at["gas", "co2_emissions"]

    costs.at["solar", "capital_cost"] = (
        config["rooftop_share"] * costs.at["solar-rooftop", "capital_cost"]
        + (1 - config["rooftop_share"]) * costs.at["solar-utility", "capital_cost"]
    )

    def costs_for_storage(store, link1, link2=None, max_hours=1.0):
        capital_cost = link1["capital_cost"] + max_hours * store["capital_cost"]
        if link2 is not None:
            capital_cost += link2["capital_cost"]
        return pd.Series(
            dict(capital_cost=capital_cost, marginal_cost=0.0, co2_emissions=0.0)
        )

    max_hours = config["max_hours"]
    costs.loc["battery"] = costs_for_storage(
        costs.loc["battery storage"],
        costs.loc["battery inverter"],
        max_hours=max_hours["battery"],
    )
    costs.loc["H2"] = costs_for_storage(
        costs.loc["hydrogen storage underground"],
        costs.loc["fuel cell"],
        costs.loc["electrolysis"],
        max_hours=max_hours["H2"],
    )

    for attr in ("marginal_cost", "capital_cost"):
        overwrites = config.get(attr)
        if overwrites is not None:
            overwrites = pd.Series(overwrites)
            costs.loc[overwrites.index, attr] = overwrites

    return costs
