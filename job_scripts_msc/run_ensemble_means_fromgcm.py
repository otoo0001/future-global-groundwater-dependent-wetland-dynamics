# #!/usr/bin/env python3
# COMPUTE MONTHLY ENSEMBLE MEANS OF GDWS        

# # Must be set before any HDF5/netCDF4 import
# import os
# os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"
# os.environ["HDF5_DISABLE_VERSION_CHECK"] = "2"
# os.environ["OMP_NUM_THREADS"] = "1"
# os.environ["OPENBLAS_NUM_THREADS"] = "1"
# os.environ["MKL_NUM_THREADS"] = "1"

# from pathlib import Path
# from datetime import datetime

# import numpy as np
# import pandas as pd
# import xarray as xr
# import netCDF4 as nc


# SCENARIO = os.environ.get("SCENARIO", "historical")

# BASE = Path("/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/gcms")
# OUT = Path("/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/ensemble")

# GCMS = [
#     "gfdl-esm4",
#     "ipsl-cm6a-lr",
#     "mpi-esm1-2-hr",
#     "mri-esm2-0",
#     "ukesm1-0-ll",
# ]

# VARS = [
#     "area_gdw_km2",
#     "area_gdw_nonlu_km2",
# ]

# FILL_VALUE = np.float32(-9999.0)


# def log(msg):
#     print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# def src_path(gcm):
#     return BASE / gcm / SCENARIO / "nc" / f"wetGDE_{gcm}_{SCENARIO}.nc"


# def get_template():
#     for gcm in GCMS:
#         p = src_path(gcm)
#         if p.exists():
#             ds = xr.open_dataset(p, decode_times=True, mask_and_scale=True)
#             lat = ds["lat"].values.astype("float32")
#             lon = ds["lon"].values.astype("float32")
#             times = pd.to_datetime(ds["time"].values)
#             ds.close()
#             return lat, lon, times
#     raise FileNotFoundError("No valid GCM files found")


# def time_to_days(t):
#     return float((pd.Timestamp(t) - pd.Timestamp("1900-01-01")).days)


# def compute_time_var(ti, time_value, var):
#     total = None
#     count = None
#     used = []

#     for gcm in GCMS:
#         p = src_path(gcm)

#         if not p.exists():
#             log(f"  [missing] {gcm}: {p}")
#             continue

#         ds = xr.open_dataset(p, decode_times=True, mask_and_scale=True)

#         if var not in ds:
#             log(f"  [skip] {gcm}: variable '{var}' not found")
#             ds.close()
#             continue

#         if ti >= ds.sizes["time"]:
#             log(f"  [skip] {gcm}: no timestep index {ti}")
#             ds.close()
#             continue

#         arr = ds[var].isel(time=ti).values.astype("float32")
#         ds.close()

#         valid = np.isfinite(arr)

#         if total is None:
#             total = np.zeros(arr.shape, dtype="float64")
#             count = np.zeros(arr.shape, dtype="uint16")

#         total[valid] += arr[valid].astype("float64")
#         count[valid] += 1
#         used.append(gcm)

#     if total is None or len(used) < 2:
#         raise RuntimeError(
#             f"Not enough valid GCMs for time index={ti}, time={time_value}, var={var}. "
#             f"Found: {used}"
#         )

#     out = np.full(total.shape, np.nan, dtype="float32")
#     ok = count > 0
#     out[ok] = (total[ok] / count[ok]).astype("float32")

#     log(f"  [done] ti={ti}, time={time_value.date()}, var={var}, n_members={len(used)}")
#     return out


# def create_output_file(outfile, lat, lon):
#     log(f"[create] {outfile}")

#     ds = nc.Dataset(outfile, mode="w", format="NETCDF4")

#     ds.createDimension("time", None)
#     ds.createDimension("lat", len(lat))
#     ds.createDimension("lon", len(lon))

#     t = ds.createVariable("time", "f8", ("time",))
#     t.units = "days since 1900-01-01 00:00:00"
#     t.calendar = "standard"
#     t.long_name = "time"
#     t.axis = "T"

#     la = ds.createVariable("lat", "f4", ("lat",))
#     la.units = "degrees_north"
#     la.standard_name = "latitude"
#     la.long_name = "latitude"
#     la.axis = "Y"
#     la[:] = lat

#     lo = ds.createVariable("lon", "f4", ("lon",))
#     lo.units = "degrees_east"
#     lo.standard_name = "longitude"
#     lo.long_name = "longitude"
#     lo.axis = "X"
#     lo[:] = lon

#     for var in VARS:
#         v = ds.createVariable(
#             var,
#             "f4",
#             ("time", "lat", "lon"),
#             zlib=True,
#             complevel=1,
#             fill_value=FILL_VALUE,
#             chunksizes=(1, 180, 360),
#         )
#         v.units = "km2"
#         v.long_name = f"monthly ensemble mean of {var}"
#         v.missing_value = FILL_VALUE

#     ds.title = f"wetGDE monthly ensemble mean, {SCENARIO}"
#     ds.scenario = SCENARIO
#     ds.ensemble_members = ", ".join(GCMS)
#     ds.Conventions = "CF-1.8"
#     ds.created = datetime.now().isoformat(timespec="seconds")

#     ds.close()
#     log(f"[created] {outfile}")


# def append_time(outfile, ti, time_value, arrays):
#     ds = nc.Dataset(outfile, mode="a")

#     ds["time"][ti] = time_to_days(time_value)

#     for var, arr in arrays.items():
#         data = arr.copy()
#         data[~np.isfinite(data)] = FILL_VALUE
#         ds[var][ti, :, :] = data

#     ds.sync()
#     ds.close()


# def get_resume_index(outfile, n_times):
#     if not outfile.exists():
#         return 0

#     try:
#         ds = nc.Dataset(outfile, mode="r")
#         n_written = ds.dimensions["time"].size
#         ds.close()

#         if n_written >= n_times:
#             log(f"[complete] output already has all {n_written} timesteps, nothing to do")
#             return n_times

#         log(f"[resume] found {n_written} timesteps already written")
#         return n_written

#     except Exception as e:
#         log(f"[warn] could not read existing file ({e}), recreating")
#         outfile.unlink()
#         return 0


# def main():
#     log("=" * 60)
#     log(f"Scenario : {SCENARIO}")
#     log(f"GCMs     : {', '.join(GCMS)}")
#     log(f"Variables: {', '.join(VARS)}")
#     log("=" * 60)

#     lat, lon, times = get_template()

#     log(f"Grid      : {len(lat)} lat x {len(lon)} lon")
#     log(f"Timesteps : {times[0].date()} to {times[-1].date()} ({len(times)} total)")

#     outdir = OUT / SCENARIO / "nc"
#     outdir.mkdir(parents=True, exist_ok=True)

#     outfile = outdir / f"wetGDE_ensemble_monthly_{SCENARIO}.nc"

#     start_ti = get_resume_index(outfile, len(times))

#     if start_ti >= len(times):
#         return

#     if not outfile.exists():
#         create_output_file(outfile, lat, lon)

#     for ti, time_value in enumerate(times):
#         if ti < start_ti:
#             log(f"[skip] time index {ti}, {time_value.date()} already written")
#             continue

#         log("")
#         log(f"----- timestep {ti + 1}/{len(times)}: {time_value.date()} -----")

#         arrays = {}
#         for var in VARS:
#             arrays[var] = compute_time_var(ti, time_value, var)

#         append_time(outfile, ti, time_value, arrays)
#         log(f"[appended] {time_value.date()} → time index {ti}")

#     log("")
#     log(f"[complete] {outfile}")
#     log("Open with:")
#     log(f"  xr.open_dataset('{outfile}')")
#     log(f"  ncview {outfile}")


# if __name__ == "__main__":
#     main()



#!/usr/bin/env python3

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


BASE = Path("/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/ensemble")

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


def monthly_path(scenario):
    return BASE / scenario / "nc" / f"wetGDE_ensemble_monthly_{scenario}.nc"


def out_time_mean_path(scenario, y1, y2):
    return BASE / scenario / "nc" / f"wetGDE_ensemble_timmean_{scenario}_{y1}-{y2}.nc"


def out_monthly_clim_path(scenario, y1, y2):
    return BASE / scenario / "nc" / f"wetGDE_ensemble_monthly_climatology_{scenario}_{y1}-{y2}.nc"


def days_since_1900(timestamp):
    return float((pd.Timestamp(timestamp) - pd.Timestamp("1900-01-01")).days)


def create_base_file(outfile, lat, lon, mode, scenario, y1, y2):
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
            v.long_name = f"{y1}-{y2} time mean of {var}"
        else:
            v.long_name = f"{y1}-{y2} monthly climatology of {var}"
        v.missing_value = FILL_VALUE

    ds.title = f"wetGDE ensemble {mode}, {scenario}, {y1}-{y2}"
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


def compute_outputs_for_scenario(scenario, y1, y2):
    src = monthly_path(scenario)

    if not src.exists():
        log(f"[missing] {src}")
        return

    log("")
    log("=" * 70)
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
        raise RuntimeError(f"No timesteps found for {scenario}, {y1}-{y2}")

    out_tm = out_time_mean_path(scenario, y1, y2)
    out_mc = out_monthly_clim_path(scenario, y1, y2)

    log(f"[create time mean] {out_tm}")
    ds_tm = create_base_file(out_tm, lat, lon, "time_mean", scenario, y1, y2)

    log(f"[create monthly climatology] {out_mc}")
    ds_mc = create_base_file(out_mc, lat, lon, "monthly_climatology", scenario, y1, y2)

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
            log(f"  month {month:02d}")
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


def main():
    for scenario, (y1, y2) in SCENARIOS.items():
        compute_outputs_for_scenario(scenario, y1, y2)

    log("")
    log("All outputs complete.")


if __name__ == "__main__":
    main()