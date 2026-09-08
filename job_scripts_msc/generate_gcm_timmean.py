#!/usr/bin/env python3
"""
Per-GCM equivalent of the ensemble timmean/monthly-climatology builder.

Same logic as the ensemble script (create_base_file / write_array /
compute_outputs_for_scenario), but looped once per GCM instead of run once
on the pre-averaged ensemble monthly file. Produces the files that
open_timmean_da_gcm() in the figures script expects, enabling:
  - S5 (per-pixel GCM standard deviation map)
  - Fig 1b error bars (if switched to pixel-derived gain/loss)
  - any other per-GCM spatial product

ASSUMPTION TO VERIFY: this script assumes a per-GCM monthly NetCDF exists
at GCMS_BASE/<gcm>/<scenario>/nc/wetGDE_<gcm>_<scenario>.nc, e.g.
wetGDE_gfdl-esm4_historical.nc -- confirmed present on Snellius via
`ls .../gcms/gfdl-esm4/historical/nc/`. If other GCMs use a different
naming pattern, only MONTHLY_PATH_GCM below needs to change.

If a per-GCM monthly file is missing for some GCM/scenario pair, that
pair is skipped and logged rather than aborting the whole run, so
whatever GCMs are available get processed and the uncertainty figures
degrade gracefully (S5 requires only >=2 GCMs).
"""

import os
os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"
os.environ["HDF5_DISABLE_VERSION_CHECK"] = "2"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import xarray as xr
import netCDF4 as nc


GCMS_BASE = Path("/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/gcms")

GCMS = ["gfdl-esm4", "ipsl-cm6a-lr", "mpi-esm1-2-hr", "mri-esm2-0", "ukesm1-0-ll"]

SCENARIOS = {
    "historical": (2005, 2014),
    "ssp126": (2041, 2050),
    "ssp370": (2041, 2050),
    "ssp585": (2041, 2050),
}

VARS = [
    "area_gdw_km2",
    "area_gdw_nonlu_km2",
]

FILL_VALUE = np.float32(-9999.0)


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def monthly_path_gcm(gcm, scenario):
    # Confirmed on Snellius: e.g. wetGDE_gfdl-esm4_historical.nc
    # (no "_monthly_" in the name, unlike the ensemble file naming).
    return GCMS_BASE / gcm / scenario / "nc" / f"wetGDE_{gcm}_{scenario}.nc"


def out_time_mean_path_gcm(gcm, scenario, y1, y2):
    # Must match timmean_path_gcm() in the figures script.
    return GCMS_BASE / gcm / scenario / "nc" / f"wetGDE_{gcm}_timmean_{scenario}_{y1}-{y2}.nc"


def out_monthly_clim_path_gcm(gcm, scenario, y1, y2):
    return GCMS_BASE / gcm / scenario / "nc" / f"wetGDE_{gcm}_monthly_climatology_{scenario}_{y1}-{y2}.nc"


def days_since_1900(timestamp):
    return float((pd.Timestamp(timestamp) - pd.Timestamp("1900-01-01")).days)


def create_base_file(outfile, lat, lon, mode, scenario, y1, y2, gcm):
    if outfile.exists():
        outfile.unlink()

    ds = nc.Dataset(outfile, mode="w", format="NETCDF4")

    if mode == "time_mean":
        ds.createDimension("time", 1)
    elif mode == "monthly_climatology":
        ds.createDimension("month", 12)
    else:
        raise ValueError(mode)

    ds.createDimension("lat", len(lat))
    ds.createDimension("lon", len(lon))

    if mode == "time_mean":
        t = ds.createVariable("time", "f8", ("time",))
        mid_year = int(round((y1 + y2) / 2))
        t[:] = [days_since_1900(f"{mid_year}-07-01")]
        t.units = "days since 1900-01-01 00:00:00"
        t.calendar = "standard"
        t.long_name = "time"
        t.axis = "T"

    if mode == "monthly_climatology":
        m = ds.createVariable("month", "i4", ("month",))
        m[:] = np.arange(1, 13, dtype="int32")
        m.long_name = "calendar month"
        m.units = "1"

    la = ds.createVariable("lat", "f4", ("lat",))
    la[:] = lat.astype("float32")
    la.units = "degrees_north"
    la.standard_name = "latitude"
    la.long_name = "latitude"
    la.axis = "Y"

    lo = ds.createVariable("lon", "f4", ("lon",))
    lo[:] = lon.astype("float32")
    lo.units = "degrees_east"
    lo.standard_name = "longitude"
    lo.long_name = "longitude"
    lo.axis = "X"

    dims = ("time", "lat", "lon") if mode == "time_mean" else ("month", "lat", "lon")

    for var in VARS:
        v = ds.createVariable(
            var,
            "f4",
            dims,
            zlib=True,
            complevel=1,
            fill_value=FILL_VALUE,
            chunksizes=(1, 180, 360),
        )
        v.units = "km2"
        if mode == "time_mean":
            v.long_name = f"{y1}-{y2} time mean of {var}, {gcm}"
        else:
            v.long_name = f"{y1}-{y2} monthly climatology of {var}, {gcm}"
        v.missing_value = FILL_VALUE

    ds.title = f"wetGDE {gcm} {mode}, {scenario}, {y1}-{y2}"
    ds.gcm = gcm
    ds.scenario = scenario
    ds.period = f"{y1}-{y2}"
    ds.Conventions = "CF-1.8"
    ds.created = datetime.now().isoformat(timespec="seconds")

    return ds


def write_array(ds_out, mode, var, index, arr):
    data = arr.astype("float32").copy()
    data[~np.isfinite(data)] = FILL_VALUE

    if mode == "time_mean":
        ds_out[var][0, :, :] = data
    else:
        ds_out[var][index, :, :] = data


def compute_outputs_for_gcm_scenario(gcm, scenario, y1, y2):
    src = monthly_path_gcm(gcm, scenario)

    if not src.exists():
        log(f"[missing, skipping] {src}")
        return False

    log("")
    log("=" * 70)
    log(f"GCM     : {gcm}")
    log(f"Scenario: {scenario}")
    log(f"Period  : {y1}-{y2}")
    log(f"Input   : {src}")
    log("=" * 70)

    ds = xr.open_dataset(src, decode_times=True, mask_and_scale=True)

    lat = ds["lat"].values.astype("float32")
    lon = ds["lon"].values.astype("float32")

    yy = ds["time"].dt.year
    ds_period = ds.sel(time=(yy >= y1) & (yy <= y2))

    if ds_period.sizes.get("time", 0) == 0:
        ds.close()
        log(f"[warn] no timesteps found for {gcm} {scenario} {y1}-{y2}, skipping")
        return False

    out_tm = out_time_mean_path_gcm(gcm, scenario, y1, y2)
    out_mc = out_monthly_clim_path_gcm(gcm, scenario, y1, y2)
    out_tm.parent.mkdir(parents=True, exist_ok=True)
    out_mc.parent.mkdir(parents=True, exist_ok=True)

    log(f"[create time mean] {out_tm}")
    ds_tm = create_base_file(out_tm, lat, lon, "time_mean", scenario, y1, y2, gcm)

    log(f"[create monthly climatology] {out_mc}")
    ds_mc = create_base_file(out_mc, lat, lon, "monthly_climatology", scenario, y1, y2, gcm)

    for var in VARS:
        if var not in ds_period:
            log(f"[skip] {var}, missing")
            continue

        log(f"[time mean] {var}")
        arr_tm = ds_period[var].mean("time", skipna=True).values
        write_array(ds_tm, "time_mean", var, 0, arr_tm)
        ds_tm.sync()

        log(f"[monthly climatology] {var}")
        for month in range(1, 13):
            da_m = ds_period[var].sel(time=(ds_period["time"].dt.month == month))
            if da_m.sizes.get("time", 0) == 0:
                arr = np.full((len(lat), len(lon)), np.nan, dtype="float32")
            else:
                arr = da_m.mean("time", skipna=True).values
            write_array(ds_mc, "monthly_climatology", var, month - 1, arr)
            ds_mc.sync()

    ds_tm.close()
    ds_mc.close()
    ds.close()

    log(f"[done time mean] {out_tm}")
    log(f"[done monthly climatology] {out_mc}")
    return True


def main():
    n_done, n_skipped = 0, 0
    for gcm in GCMS:
        for scenario, (y1, y2) in SCENARIOS.items():
            ok = compute_outputs_for_gcm_scenario(gcm, scenario, y1, y2)
            if ok:
                n_done += 1
            else:
                n_skipped += 1

    log("")
    log(f"All GCM outputs complete. Done: {n_done}, skipped (missing input): {n_skipped}")
    if n_skipped > 0:
        log("If most/all pairs were skipped, verify monthly_path_gcm() naming "
            "against the actual files under GCMS_BASE/<gcm>/<scenario>/nc/.")


if __name__ == "__main__":
    main()