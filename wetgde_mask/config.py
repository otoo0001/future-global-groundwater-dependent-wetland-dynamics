"""
config.py  --  all tunable parameters and paths for the Paper 3 wetGDE pipeline.

Physical basis
--------------
Paper 3 maps wetGDE at 5 arcmin to maintain consistency with the land use
input, which is also at 5 arcmin resolution (PCR-GLOBWB resolution).

WTD source: GLOBGM zarr at 1/120 deg (~30 arcsec), 19200 x 43200
            /projects/prjs1222/globgm_output/cmip6/monthly/{scenario}/ensemble.zarr
            variable: wtd, dims: (model, layer, time, latitude, longitude)
            layer 1 = primary, layer 2 = fallback

SAT source: PCR-GLOBWB NetCDF at ~1/12 deg (~5 arcmin), 2160 x 4320

The WTD and SAT grids do NOT nest exactly (lat ratio = 8.889, lon ratio = 10).
WTD cells are assigned to parent SAT cells by coordinate lookup (searchsorted).
Aggregation uses numpy bincount via numba JIT for speed.

PS: Edit this file only. No other module hardcodes paths or thresholds.
"""

import os

# ---------------- Directories ----------------
SAT_DIR  = "/projects/prjs1578/sat_future"
WTD_ROOT = "/projects/prjs1222/globgm_output/cmip6/monthly"
OUT_DIR  = "/path/to/scratch/paper_3/new_outputs/WetGDEs/ensemble"

# WTD zarr config
WTD_MODEL  = "ensemble"
WTD_VAR    = "wtd"
WTD_LAYER1 = 1
WTD_LAYER2 = 2

# Native zarr chunk shape: (model=1, layer=1, time=2, lat=1280, lon=1200)
# Read in 2-timestep batches aligned to zarr chunks for fast IO
WTD_TIME_CHUNK = 2
WTD_LAT_CHUNK  = 1280
WTD_LON_CHUNK  = 1200

# ---------------- Scenarios ----------------
SCENARIOS = ["historical", "ssp126", "ssp370", "ssp585"]

# ---------------- Variable names ----------------
SAT_VAR = "satAreaFrac"

# ---------------- Thresholds ----------------
SAT_THRESHOLD        = 0.5
WTD_MIN              = -10.0   # metres; negative = surface inundation, included up to -10m
WTD_MAX              = 5.0   # metres
WTD_FRAC_THRESHOLD   = 0.5   # at least 50% of valid fine cells must be shallow
MIN_VALID_FINE_CELLS = 5     # minimum valid fine cells to classify a coarse cell

# ---------------- Chunking (coarse grid only, fine grid uses zarr native) ----
SZ           = int(os.environ.get("SPATIAL_CHUNK", "512"))
CHUNK_COARSE = {"time": 1, "lat": SZ, "lon": SZ}

# ---------------- NetCDF write options ----------------
ENGINE    = "netcdf4"
NC_FORMAT = "NETCDF4_CLASSIC"
COMPLEVEL = 4

# ---------------- Metadata ----------------
AUTHOR           = "Nicole Gyakowah Otoo"
EMAIL            = "n.g.otoo@uu.nl, REMOVED"
INSTITUTION      = "Department of Physical Geography, Utrecht University"
SUPERVISOR       = "Edwin H. Sutanudjaja"
SUPERVISOR_EMAIL = "E.H.Sutanudjaja@uu.nl"
PROJECT          = ""
REFERENCES       = (
    "Otoo et al. (2025) HESS 29(8) 2153-2165; "
    "Sutanudjaja et al. (2018) GMD PCR-GLOBWB 2; "
    "de Graaf et al. (2015) GLOBGM"
)
LICENSE          = "CC BY 4.0"
CONVENTIONS      = "CF-1.8"
PRODUCT_VERSION  = "1.0"
DOI              = ""    # fill after data deposition
MODEL_SAT        = "PCR-GLOBWB 2"
MODEL_WTD        = "GLOBGM"
FORCING          = "CMIP6 ensemble mean"

# ---------------- Runtime flags ----------------
TEST        = os.environ.get("TEST",        "false").lower() in ("true","1","yes","y")
SMALL_TEST  = os.environ.get("SMALL_TEST",  "false").lower() in ("true","1","yes","y")
REGION_NAME = os.environ.get("REGION",      "great_plains").strip().lower()
ONLY_SCEN   = os.environ.get("SCENARIO",    "").strip() or None
PROGRESS_LOG= os.environ.get("PROGRESS_LOG","").strip() or None

# ---------------- Test regions ----------------
REGIONS = {
    "great_plains": dict(lat=(25.0,  50.0),  lon=(-106.0, -94.0)),
    "sahel":        dict(lat=(10.0,  20.0),  lon=(-20.0,   30.0)),
    "amazon":       dict(lat=(-15.0,  5.0),  lon=(-75.0,  -50.0)),
    "europe":       dict(lat=(36.0,  60.0),  lon=(-10.0,   30.0)),
    "australia_se": dict(lat=(-40.0,-25.0),  lon=(140.0,  155.0)),
}