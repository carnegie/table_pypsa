# Scripts to run PyPSA with input tables

## Install PyPSA

[Install PyPSA](https://pypsa.readthedocs.io/en/latest/installation.html) with

```conda install -c conda-forge pypsa```

or 

```pip install pypsa```

## Install Gurobi

Follow [installation instructions](https://www.gurobi.com/documentation/10.0/quickstart_windows/cs_python_installation_opt.html) to install Gurobi. Free licenses for academics are available.


## Clone this repository 

with --recursive (this clones PyPSA as a submodule ), for example

```git clone https://github.com/carnegie/clab_pypsa --recursive```


## Data input files

The data input files are in the [Carnegie storage](https://carnegiescience.freshservice.com/support/solutions/articles/3000028580-data-storage-strategy) `data`. 
The files can for example be accessed through

```ssh username@dtn.dge.carnegiescience.edu```

The data files are in the format of csv files. The data directory is:

```/carnegie/data/Shared/Labs/Caldeira Lab/Everyone/energy_demand_capacity_data/test_case_solar_wind_demand```


## Run PyPSA

To run PyPSA, you need to have a case input file and data input files.

pyPSA is run with the command

```python run_pypsa.py -f test_case.xlsx```

where `test_case.xlsx` is the case input file.

