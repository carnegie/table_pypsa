
## Clone this repository 

with --recursive (this clones PyPSA as a submodule ), for example

```git clone https://github.com/carnegie/clab_pypsa --recursive```

#
## Install dependencies in the environment

When you're running for the first time, create a new environment with

```conda env create -f env.yaml```

Then activate the environment with

```conda activate pypsa_table```

every time you want to run pypsa_table.

#
## Install a solver

For Gurobi, follow [installation instructions](https://www.gurobi.com/documentation/10.0/quickstart_windows/cs_python_installation_opt.html) to install Gurobi. Free licenses for academics are available.

For other solvers, see the instructions in the [PyPSA documentation](https://pypsa.readthedocs.io/en/latest/installation.html).

#
## Run PyPSA

To run PyPSA, you need to have a case input file and data input files.

pyPSA is run with the command

```python run_pypsa.py -f input_file.xlsx```

where `input_file.xlsx` is the case input file.
(See for example the `test_case.xlsx` file in `test/ .`)

#
#
## Create a new project based on clab_pypsa

In a new repository add clab_pypsa as a submodule with (this will follow the main branch of clab_pypsa)

```git submodule add -b main https://github.com/carnegie/clab_pypsa```

Make sure to update the submodule regularly by doing

```git submodule update --remote --recursive```

#
To run PyPSA in that repository, then run

```python clab_pypsa/run_pypsa.py -f <path_to_your_case_file>```

