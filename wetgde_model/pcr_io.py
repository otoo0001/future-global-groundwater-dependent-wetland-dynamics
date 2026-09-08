"""
pcr_io.py  --  open PCR-GLOBWB ISIMIP3 variables needed for GDI.

Only opens precipitation (for dry/wet season classification).
satAreaFrac is read directly from the v3 GCM NCs.

File naming convention:
  {PCR_ROOT}/{gcm}/{scenario}/
  pcrglobwb_cmip6-isimip3-{gcm}_image-aqueduct_{scenario}_{variable}_
  global_monthly-{agg}_{start}_{end}_basetier1.nc

On-disk chunks: (1, 15, 4320) — very fine.
We rechunk to (12, 2160, 4320) on open to avoid dask graph explosion.
"""
from __future__ import annotations

import glob
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

PCR_ROOT = os.environ.get(
    "PCR_ISIMIP_ROOT",
    "/projects/2/managed_datasets/hypflowsci6_v1.0/output",
)

# on-disk chunk is (1, 15, 4320) — rechunk to full spatial on open
_CHUNKS = {"time": 12, "lat": 2160, "lon": 4320}

_AGG = {
    "precipitation":    "monthly-total",
    "actualET":         "monthly-total",
    "gwRecharge":       "monthly-total",
    "totalRunoff":      "monthly-total",
    "directRunoff":     "monthly-total",
    "storGroundwater":  "monthly-average",
    "storUppTotal":     "monthly-average",
    "storLowTotal":     "monthly-average",
    "satDegUpp":        "monthly-average",
    "satDegLow":        "monthly-average",
    "topWaterLayer":    "monthly-average",
}


# ── path resolution ───────────────────────────────────────────────────────────

def pcr_path(gcm: str, scenario: str, variable: str, root: str = PCR_ROOT) -> str:
    agg  = _AGG.get(variable, "monthly-*")
    base = Path(root) / gcm / scenario
    pattern = (
        f"pcrglobwb_cmip6-isimip3-{gcm}_image-aqueduct_"
        f"{scenario}_{variable}_global_{agg}_*_basetier1.nc"
    )
    matches = sorted(glob.glob(str(base / pattern)))
    if not matches:
        raise FileNotFoundError(
            f"No PCR file: variable={variable} gcm={gcm} scenario={scenario}\n"
            f"  searched: {base / pattern}"
        )
    if len(matches) > 1:
        logger.warning("Multiple matches for %s/%s/%s; using first", gcm, scenario, variable)
    return matches[0]


# ── generic opener ────────────────────────────────────────────────────────────

def open_pcr_var(
    gcm: str,
    scenario: str,
    variable: str,
    root: str = PCR_ROOT,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> xr.DataArray:
    """
    Open one PCR-GLOBWB variable as float32 DataArray (time, lat, lon).
    Rechunked to (12, 2160, 4320) to avoid dask graph explosion from
    on-disk (1, 15, 4320) chunks.
    """
    path = pcr_path(gcm, scenario, variable, root)
    ds   = xr.open_dataset(path, decode_times=True, chunks=_CHUNKS)

    # standardise coord names
    ren = {}
    for old, new in [("latitude","lat"),("longitude","lon")]:
        if old in ds.dims: ren[old] = new
    if ren: ds = ds.rename(ren)

    var = variable if variable in ds.data_vars else list(ds.data_vars)[0]
    da  = ds[var].astype("float32")

    # ensure lat ascending
    if "lat" in da.dims and float(da["lat"].values[0]) > float(da["lat"].values[-1]):
        da = da.sortby("lat")

    if start_year is not None:
        da = da.sel(time=da["time"].dt.year >= start_year)
    if end_year is not None:
        da = da.sel(time=da["time"].dt.year <= end_year)

    logger.debug("open_pcr_var: %s/%s/%s  shape=%s", gcm, scenario, variable, dict(da.sizes))
    return da


# ── named convenience openers ─────────────────────────────────────────────────

def open_precipitation(gcm: str, scenario: str, **kwargs) -> xr.DataArray:
    """precipitation [m/month, monthly-total]."""
    da = open_pcr_var(gcm, scenario, "precipitation", **kwargs)
    da.attrs.update({"long_name": "Precipitation", "units": "m/month"})
    return da


def open_actual_et(gcm: str, scenario: str, **kwargs) -> xr.DataArray:
    """actualET [m/month, monthly-total]."""
    da = open_pcr_var(gcm, scenario, "actualET", **kwargs)
    da.attrs.update({"long_name": "Actual evapotranspiration", "units": "m/month"})
    return da


def open_gw_recharge(gcm: str, scenario: str, **kwargs) -> xr.DataArray:
    """gwRecharge [m/month, monthly-total]. Always positive in PCR-GLOBWB."""
    da = open_pcr_var(gcm, scenario, "gwRecharge", **kwargs)
    da.attrs.update({"long_name": "Groundwater recharge", "units": "m/month"})
    return da


def open_stor_groundwater(gcm: str, scenario: str, **kwargs) -> xr.DataArray:
    """storGroundwater [m, monthly-average]."""
    da = open_pcr_var(gcm, scenario, "storGroundwater", **kwargs)
    da.attrs.update({"long_name": "Groundwater storage", "units": "m"})
    return da