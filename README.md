# Future global groundwater-dependent wetland dynamics

This repository contains the modelling and analysis code used to assess historical and future changes in groundwater-dependent wetlands (WetGDEs).

The workflow combines groundwater-table depth, saturated-area fractions and land-use information to estimate groundwater-dependent wetland fractions and evaluate changes in their extent, groundwater dependency and associated uncertainty under historical and future climate conditions.

---

## Repository structure

```text
future-global-groundwater-dependent-wetland-dynamics/
├── environment.yml
├── README.md
├── docs/
├── scripts/
│   ├── run_combined.py
│   ├── run_process_model.py
│   ├── run_wetgde_paper3.py
│   └── validate_all_runs.py
├── sensitivity/
│   └── scripts/
├── slurm/
│   ├── job_scripts_msc/
│   ├── submit_combined.example.sh
│   ├── submit_gcms.example.sh
│   ├── submit_mask.example.sh
│   └── submit_process_model.example.sh
├── wetgde_mask/
│   ├── config.example.py
│   ├── grid_utils.py
│   ├── __init__.py
│   ├── io.py
│   ├── pipeline.py
│   └── writer.py
└── wetgde_model/
    ├── area.py
    ├── config.example.py
    ├── dependency.py
    ├── feedback.py
    ├── __init__.py
    ├── io_utils.py
    ├── loss.py
    ├── lu_utils.py
    ├── mask.py
    ├── pcr_io.py
    ├── pipeline.py
    ├── qa_utils.py
    ├── run.py
    ├── uncertainty.py
    └── writers.py
```

### `wetgde_mask/`

Contains the workflow used to derive groundwater-dependent wetland fractions from groundwater-table depth and saturated-area information.

The directory name reflects an earlier mask-based implementation. The current workflow retains saturated-area information fractionally in the WetGDE calculation.

### `wetgde_model/`

Contains the main analysis routines used to quantify WetGDE extent and change, groundwater dependency, losses and uncertainty.

### `scripts/`

Contains the main executable Python scripts:

* `run_wetgde_paper3.py` — runs the WetGDE fraction workflow.
* `run_process_model.py` — runs the groundwater-dependency, loss and uncertainty analyses.
* `run_combined.py` — runs the combined workflow.
* `validate_all_runs.py` — checks completed model outputs.

### `sensitivity/`

Contains scripts used to evaluate the sensitivity of WetGDE estimates to methodological assumptions and parameter choices.

### `slurm/`

Contains public templates of the SLURM submission scripts used to run the analyses on the Snellius national supercomputer.

Additional processing, evaluation and plotting scripts are retained under `slurm/job_scripts_msc/`.

Machine-specific submission scripts are excluded from version control.

---

# WetGDE calculation

WetGDE extent is represented as a fractional quantity at 5 arcmin resolution.

The calculation combines saturated-area fraction with groundwater-table depth information. Shallow-groundwater conditions are evaluated using the fraction of the underlying high-resolution groundwater cells satisfying the groundwater-table-depth criterion.

The main WetGDE fraction is calculated as:

```text
f_gdw = satAreaFrac × is_gdw × (1 - f_conv)
```

where:

* `satAreaFrac` is the saturated-area fraction;
* `is_gdw` identifies grid cells satisfying the groundwater-dependence criteria;
* `f_conv` is the fraction affected by land-use conversion.

In the current implementation, `is_gdw` requires:

```text
satAreaFrac > 0.5
```

and:

```text
wtd_shallow_frac >= 0.5
```

where `wtd_shallow_frac` represents the fraction of the underlying groundwater-model cells with groundwater-table depth ≤ 5 m.

Open-water and non-GDW pixels are excluded from the WetGDE fraction.

The resulting `f_gdw` ranges from 0 to 1 and represents the estimated groundwater-dependent wetland fraction of a grid cell after land-use exclusion.

---

# Historical and future simulations

The analysis includes a historical simulation and future projections under three scenarios:

* SSP1-2.6 (`ssp126`)
* SSP3-7.0 (`ssp370`)
* SSP5-8.5 (`ssp585`)

Future conditions are evaluated for:

**2041–2050**

The period:

**1995–2014**

is used as the historical reference period for future comparisons where applicable.

---

# Climate-model ensemble

Future projections are evaluated using five CMIP6 global climate models:

* GFDL-ESM4
* IPSL-CM6A-LR
* MPI-ESM1-2-HR
* MRI-ESM2-0
* UKESM1-0-LL

Individual GCM simulations are retained throughout the workflow to quantify inter-model variation, model agreement and uncertainty.

---

# Input data and external code

Large input datasets are not distributed directly with this repository.

## GLOBGM groundwater simulations

Groundwater-table depth and associated groundwater variables are obtained from the GLOBGM simulations described by van Jaarsveld et al. (2026), *Global hyper-resolution modeling of historical and future groundwater dynamics*.

GLOBGM is a MODFLOW-based global groundwater model operating at approximately 30 arcsec spatial resolution.

### GLOBGM model repository

https://github.com/UU-Hydro/GLOBGM

### Model code used for the historical and future simulations

https://doi.org/10.5281/zenodo.17065147

### van Jaarsveld et al. (2026)

https://doi.org/10.5194/esd-17-1201-2026

---

## GLOBGM simulation outputs

### Historical reference simulation — GSWP3-W5E5

https://doi.org/10.24416/UU01-AKSHOX

### CMIP6 monthly outputs

https://doi.org/10.24416/UU01-1BXLPD

### CMIP6 annual outputs

https://doi.org/10.24416/UU01-V6B9YS

### CMIP6 long-term-average outputs

https://doi.org/10.24416/UU01-SLRFI7

### Quality-assurance and supporting data

https://doi.org/10.24416/UU01-16EJ3Y

### GLOBGM CMIP6 data catalogue and access instructions

https://vanjaarsveldbarry.github.io/globgm_cmip6/

The historical reference simulation covers 1960–2019. The CMIP6 archive contains historical and future GCM-forced groundwater simulations.

The WetGDE analysis in this repository evaluates future conditions for 2041–2050.

---

## Saturated-area fraction

Saturated-area fractions are derived using the `pgb_sat_area_frac` workflow:

https://github.com/edwinkost/pgb_sat_area_frac

The resulting saturated-area fractions are combined with groundwater-table depth information in the WetGDE calculations.

---

## Land use

Land-use information is used to account for conversion of potential groundwater-dependent wetland area.

The workflow also contains counterfactual calculations in which land use or groundwater conditions are held fixed. These calculations are used to separate the contributions of changing groundwater conditions and land-use change to changes in WetGDE extent.

---

## Open water

Open-water information is used to exclude permanent open-water areas from the WetGDE estimates.

---

# Software environment

The software environment required for the workflow is defined in:

```text
environment.yml
```

Create the environment using:

```bash
conda env create -f environment.yml
```

Activate it using:

```bash
conda activate wetgde
```

The environment includes the principal scientific and geospatial Python packages required by the workflow, including:

* NumPy
* pandas
* SciPy
* xarray
* Dask
* Numba
* NetCDF4
* h5netcdf
* Zarr
* PyArrow
* Rasterio
* GeoPandas
* Shapely
* PyProj
* Matplotlib
* Cartopy

---

# Configuration

Machine-specific configuration files are not distributed with this repository.

Public configuration templates are provided as:

```text
wetgde_mask/config.example.py
wetgde_model/config.example.py
```

After cloning the repository, create local configuration files:

```bash
cp wetgde_mask/config.example.py wetgde_mask/config.py
cp wetgde_model/config.example.py wetgde_model/config.py
```

Edit the resulting `config.py` files to provide the locations of the required input datasets and output directories on the local system.

The local files:

```text
wetgde_mask/config.py
wetgde_model/config.py
```

are excluded from version control.

This allows machine-specific paths and local settings to remain separate from the public repository.

The scientific settings in the example configuration files should be checked against the requirements of the analysis before running the workflow.

---

# Running the workflow

Commands should be executed from the repository root.

## 1. Run the WetGDE workflow

After creating and configuring `wetgde_mask/config.py`, run:

```bash
python scripts/run_wetgde_paper3.py
```

A scenario can be specified through the corresponding environment variable.

For example:

```bash
SCENARIO=ssp370 python scripts/run_wetgde_paper3.py
```

---

## 2. Run the process-based analyses

After creating and configuring `wetgde_model/config.py`, run:

```bash
RUN_PROCESS_MODEL=1 python scripts/run_process_model.py
```

A specific GCM and scenario can be selected.

For example:

```bash
RUN_PROCESS_MODEL=1 \
GCM=gfdl-esm4 \
SCENARIO=ssp370 \
python scripts/run_process_model.py
```

The process workflow contains analyses of groundwater dependency, WetGDE loss and uncertainty.

---

## 3. Run the combined workflow

Run the combined workflow using:

```bash
python scripts/run_combined.py
```

---

## 4. Validate completed simulations

Completed model runs can be checked using:

```bash
python scripts/validate_all_runs.py
```

The output directory used by the validation script can be configured for the local system.

---

# Running on Snellius

The simulations used in this study were executed on the Snellius national supercomputer.

Public templates of the principal SLURM submission scripts are provided:

```text
slurm/
├── submit_mask.example.sh
├── submit_gcms.example.sh
├── submit_combined.example.sh
├── submit_process_model.example.sh
└── job_scripts_msc/
```

Additional SLURM templates are provided under `slurm/job_scripts_msc/` and `sensitivity/scripts/`.

The `.example.sh` files contain public versions of the submission scripts. Machine-specific paths and local settings used for the original simulations are excluded from version control.

Before using a submission script, copy the required template to a local `.sh` file.

For example:

```bash
cp slurm/submit_gcms.example.sh slurm/submit_gcms.sh
```

Then adapt the local script for the target system, including:

* input and output paths;
* Python or Conda environment;
* SLURM partition and account settings;
* memory and CPU requirements;
* log locations; and
* other machine-specific settings.

After configuration, submit the job using:

```bash
sbatch slurm/submit_gcms.sh
```

The same procedure can be used for the other `.example.sh` submission scripts.

---

# Outputs

A generic representation of the main output directory is:

```text
/path/to/WetGDEs_fgdw_v3/
```

Individual GCM results are organised by climate model and scenario.

For example:

```text
WetGDEs_fgdw_v3/
└── gcms/
    ├── gfdl-esm4/
    │   ├── historical/
    │   ├── ssp126/
    │   ├── ssp370/
    │   └── ssp585/
    ├── ipsl-cm6a-lr/
    │   ├── historical/
    │   ├── ssp126/
    │   ├── ssp370/
    │   └── ssp585/
    ├── mpi-esm1-2-hr/
    │   ├── historical/
    │   ├── ssp126/
    │   ├── ssp370/
    │   └── ssp585/
    ├── mri-esm2-0/
    │   ├── historical/
    │   ├── ssp126/
    │   ├── ssp370/
    │   └── ssp585/
    └── ukesm1-0-ll/
        ├── historical/
        ├── ssp126/
        ├── ssp370/
        └── ssp585/
```

Each GCM–scenario run contains spatial NetCDF outputs and aggregated Parquet outputs.

For example:

```text
gcms/
└── ipsl-cm6a-lr/
    └── historical/
        ├── nc/
        │   └── wetGDE_ipsl-cm6a-lr_historical.nc
        └── parquet/
            └── wetGDE_area_ipsl-cm6a-lr_historical.parquet
```

---

# NetCDF outputs

The main NetCDF files contain monthly spatial WetGDE fractions and corresponding areas on the 5 arcmin analysis grid.

The principal fraction variables are:

```text
f_gdw
f_gdw_nonlu
f_gdw_freeze_lu
f_gdw_freeze_wtd
```

## `f_gdw`

Main WetGDE fraction after land-use exclusion.

The calculation is:

```text
f_gdw = satAreaFrac × is_gdw × (1 - f_conv)
```

Units:

```text
1
```

Valid range:

```text
0–1
```

## `f_gdw_nonlu`

WetGDE saturation fraction calculated using dynamic groundwater conditions without land-use exclusion.

## `f_gdw_freeze_lu`

WetGDE fraction calculated using dynamic groundwater conditions while land use is held at historical conditions.

## `f_gdw_freeze_wtd`

WetGDE fraction calculated using a frozen historical groundwater-table-depth climatology while land use varies dynamically.

The counterfactual calculations allow groundwater-related and land-use-related contributions to changes in WetGDE extent to be evaluated separately.

---

## WetGDE area variables

Corresponding area variables are provided in km²:

```text
area_gdw_km2
area_gdw_nonlu_km2
area_gdw_freeze_lu_km2
area_gdw_freeze_wtd_km2
```

The main WetGDE area is calculated as:

```text
area_gdw_km2 = f_gdw × pixel_area_km2
```

The principal NetCDF dimensions are:

```text
time
lat
lon
```

The global 5 arcmin grid contains:

```text
lat = 2160
lon = 4320
```

The generated files use CF-1.8 metadata conventions.

---

# Parquet outputs

The Parquet outputs contain spatially aggregated WetGDE area time series.

The main columns are:

```text
time
BIOME_ID_REALM
member
scenario
area_gdw_km2
area_gdw_nonlu_km2
area_gdw_freeze_lu_km2
area_gdw_freeze_wtd_km2
```

### `time`

Monthly simulation time step.

### `BIOME_ID_REALM`

Biome–biogeographic-realm combination used for spatial aggregation.

### `member`

GCM associated with the simulation.

### `scenario`

Simulation scenario:

```text
historical
ssp126
ssp370
ssp585
```

### Area columns

The four area variables correspond to the main and counterfactual WetGDE calculations contained in the NetCDF outputs.

The Parquet products provide compact regional time series for temporal analyses, GCM and scenario comparisons, regional aggregation and preparation of figures.

---

# Inspecting outputs

The generated NetCDF and Parquet files can be inspected directly from the command line before further analysis.

First define the local output directory:

```bash
BASE="/path/to/WetGDEs_fgdw_v3"
```

## List available outputs

List NetCDF outputs:

```bash
find "$BASE" -type f -name "*.nc" | head -10
```

List Parquet outputs:

```bash
find "$BASE" -type f -name "*.parquet" | head -10
```

---

## Example: inspect a NetCDF output

Select an example historical simulation:

```bash
NC="$BASE/gcms/ipsl-cm6a-lr/historical/nc/wetGDE_ipsl-cm6a-lr_historical.nc"
```

Inspect its dimensions, variables and metadata:

```bash
ncdump -h "$NC"
```

A more compact inspection can be performed using xarray:

```bash
python - "$NC" <<'PY'
import sys
import xarray as xr

path = sys.argv[1]

with xr.open_dataset(path) as ds:
    print("\nDataset:")
    print(ds)

    print("\nDimensions:")
    for name, size in ds.sizes.items():
        print(f"  {name}: {size}")

    print("\nData variables:")
    for name, da in ds.data_vars.items():
        print(
            f"  {name}: "
            f"dims={da.dims}, "
            f"shape={da.shape}, "
            f"dtype={da.dtype}"
        )

    print("\nGlobal attributes:")
    for key, value in ds.attrs.items():
        print(f"  {key}: {value}")
PY
```

---

## Example: inspect WetGDE values

Basic statistics for the principal WetGDE fraction variables can be calculated using:

```bash
python - "$NC" <<'PY'
import sys
import xarray as xr

path = sys.argv[1]

variables = [
    "f_gdw",
    "f_gdw_nonlu",
    "f_gdw_freeze_lu",
    "f_gdw_freeze_wtd",
]

with xr.open_dataset(path) as ds:
    for name in variables:
        if name not in ds:
            continue

        da = ds[name]

        print("\n" + "=" * 60)
        print(name)
        print("=" * 60)
        print("Minimum :", float(da.min(skipna=True).compute()))
        print("Maximum :", float(da.max(skipna=True).compute()))
        print("Mean    :", float(da.mean(skipna=True).compute()))
        print("Units   :", da.attrs.get("units", ""))
        print("Name    :", da.attrs.get("long_name", ""))
PY
```

This provides a basic check of the generated WetGDE fractions and the counterfactual calculations.

---

## Example: inspect a Parquet output

Select an example historical Parquet output:

```bash
PQ="$BASE/gcms/ipsl-cm6a-lr/historical/parquet/wetGDE_area_ipsl-cm6a-lr_historical.parquet"
```

Inspect the file using pandas:

```bash
python - "$PQ" <<'PY'
import sys
import pandas as pd

path = sys.argv[1]

df = pd.read_parquet(path)

print("\nShape:")
print(df.shape)

print("\nColumns:")
for column in df.columns:
    print(f"  {column}")

print("\nData types:")
print(df.dtypes)

print("\nFirst 10 rows:")
print(df.head(10).to_string(index=False))

print("\nSummary:")
print(df.describe(include="all").transpose().to_string())
PY
```

This displays the dimensions of the table, column names, data types, example records and summary statistics.

---

## Quick inspection of one NetCDF and one Parquet file

The following example automatically selects the first NetCDF and Parquet files found in the output directory:

```bash
BASE="/path/to/WetGDEs_fgdw_v3"

NC=$(find "$BASE" -type f -name "*.nc" | head -1)
PQ=$(find "$BASE" -type f -name "*.parquet" | head -1)

echo "============================================================"
echo "NETCDF"
echo "============================================================"
echo "$NC"
ncdump -h "$NC"

echo

echo "============================================================"
echo "PARQUET"
echo "============================================================"
echo "$PQ"

python - "$PQ" <<'PY'
import sys
import pandas as pd

path = sys.argv[1]

df = pd.read_parquet(path)

print("\nShape:", df.shape)

print("\nColumns:")
for column in df.columns:
    print(f"  {column}")

print("\nFirst 10 rows:")
print(df.head(10).to_string(index=False))
PY
```

---

## Check the number of generated files

Count all NetCDF outputs:

```bash
find "$BASE" -type f -name "*.nc" | wc -l
```

Count all Parquet outputs:

```bash
find "$BASE" -type f -name "*.parquet" | wc -l
```

---

## Check output coverage by GCM and scenario

List all GCM NetCDF and Parquet outputs:

```bash
find "$BASE/gcms" -type f \
\( -name "*.nc" -o -name "*.parquet" \) \
| sort
```

This provides a quick check that the required historical and SSP simulations have produced outputs before subsequent ensemble processing, analysis or figure generation.

---

# Output validation

The repository contains an output-validation script:

```text
scripts/validate_all_runs.py
```

Run:

```bash
python scripts/validate_all_runs.py
```

The validation stage is intended to identify missing or incomplete model outputs before downstream analyses are performed.

The output location can be configured for the local computing environment.

---

# Data availability

Large model inputs and outputs are not stored directly in this GitHub repository.

The GLOBGM groundwater simulations used by the workflow are available from the external repositories and data archives listed above.

Saturated-area fractions are derived using the external `pgb_sat_area_frac` workflow referenced above.

Processed WetGDE outputs associated with this study will be archived and published through the Utrecht University Yoda research data infrastructure.

**Processed WetGDE outputs:**

DOI/link to be added after publication.

The data archive will contain the processed outputs required to reproduce the principal analyses and figures associated with the study.

The GitHub repository contains the corresponding modelling, processing, sensitivity, evaluation and plotting code.

---

# Reproducibility

This repository provides:

* the WetGDE modelling code;
* process-based analysis code;
* sensitivity-analysis scripts;
* GCM and ensemble-processing workflows;
* output-validation scripts;
* public templates of the SLURM scripts used for the HPC calculations; and
* the Conda environment specification.

Full reproduction requires access to the corresponding GLOBGM simulations, saturated-area fractions, land-use information and other external input datasets described above.

Machine-specific configuration and submission files are excluded from version control. Public templates are provided and must be adapted to the local computing environment before use.
