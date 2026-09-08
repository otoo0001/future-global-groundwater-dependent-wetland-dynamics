"""
pipeline.py  --  Paper 3 wetGDE f_gdw computation at 5 arcmin  (v3).

Computes per cell for 5 variants:
  full        varying WTD + varying LU
  nonlu       varying WTD + no LU exclusion  (f_conv = 0)
  freeze_lu   varying WTD + frozen historical LU
  freeze_wtd  frozen historical WTD climatology + varying LU
  freeze_both frozen historical WTD + frozen historical LU

NC output variables (8 total):
  f_gdw               fraction 0-1
  f_gdw_nonlu         fraction 0-1
  f_gdw_freeze_lu     fraction 0-1
  f_gdw_freeze_wtd    fraction 0-1
  area_gdw_km2
  area_gdw_nonlu_km2
  area_gdw_freeze_lu_km2
  area_gdw_freeze_wtd_km2

QA mask NOT applied here. Open water mask IS applied here.
"""

import os
import gc
import numpy as np
import xarray as xr
import pandas as pd
from netCDF4 import Dataset, date2num

from . import config as cfg
from .grid_utils import lon_range, unify_longitudes, align_time


START_YEAR = int(os.environ.get("START_YEAR", "1969"))
END_YEAR   = int(os.environ.get("END_YEAR",   "2050"))


try:
    from numba import njit

    @njit(cache=True)
    def _aggregate_numba(flat, labels, n_coarse, wtd_min, wtd_max):
        valid_count   = np.zeros(n_coarse, dtype=np.int32)
        shallow_count = np.zeros(n_coarse, dtype=np.int32)
        wtd_sum       = np.zeros(n_coarse, dtype=np.float32)
        for i in range(len(flat)):
            v = flat[i]
            if not np.isnan(v):
                lbl = labels[i]
                valid_count[lbl]   += 1
                wtd_sum[lbl]       += v
                if wtd_min <= v <= wtd_max:
                    shallow_count[lbl] += 1
        return valid_count, shallow_count, wtd_sum

    _USE_NUMBA = True
    print("[pipeline] numba JIT enabled")

except ImportError:
    _USE_NUMBA = False
    print("[pipeline] numba not available, falling back to numpy bincount")


def _aggregate_numpy(flat, labels, n_coarse, wtd_min, wtd_max):
    valid   = np.isfinite(flat)
    shallow = valid & (flat >= wtd_min) & (flat <= wtd_max)
    vc = np.bincount(labels[valid],   minlength=n_coarse).astype(np.int32)
    sc = np.bincount(labels[shallow], minlength=n_coarse).astype(np.int32)
    ws = np.bincount(labels[valid], weights=flat[valid],
                     minlength=n_coarse).astype(np.float32)
    return vc, sc, ws


def _aggregate_one(flat, labels, n_coarse):
    if _USE_NUMBA:
        return _aggregate_numba(flat, labels, n_coarse,
                                np.float32(cfg.WTD_MIN), np.float32(cfg.WTD_MAX))
    return _aggregate_numpy(flat, labels, n_coarse, cfg.WTD_MIN, cfg.WTD_MAX)


def _build_labels(wtd: xr.DataArray, sat: xr.DataArray) -> np.ndarray:
    sat_lat_s = np.sort(sat["lat"].values.astype(np.float64))
    sat_lon_s = np.sort(sat["lon"].values.astype(np.float64))
    wtd_lat   = wtd["lat"].values.astype(np.float64)
    wtd_lon   = wtd["lon"].values.astype(np.float64)
    n_lon_c   = len(sat["lon"])

    def _nearest(src, tgt):
        idx = np.searchsorted(src, tgt)
        idx = np.clip(idx, 1, len(src) - 1)
        use_l = (tgt - src[idx-1]) <= (src[idx] - tgt)
        return (idx - use_l.astype(np.int32)).astype(np.int32)

    lat_p = _nearest(sat_lat_s, wtd_lat)
    lon_p = _nearest(sat_lon_s, wtd_lon)
    lat_p = np.argsort(np.argsort(sat["lat"].values.astype(np.float64)))[lat_p]
    lon_p = np.argsort(np.argsort(sat["lon"].values.astype(np.float64)))[lon_p]

    lat_2d = np.repeat(lat_p[:, None], len(lon_p), axis=1)
    lon_2d = np.tile(lon_p[None, :], (len(lat_p), 1))
    return (lat_2d * n_lon_c + lon_2d).ravel().astype(np.int32)


def _compute_is_gdw(sat_2d, frac, vc2, open_water_2d):
    """Shared GDW mask from saturation fraction."""
    has_wtd   = vc2 > 0
    enough    = vc2 >= cfg.MIN_VALID_FINE_CELLS
    valid_sat = np.isfinite(sat_2d)
    return (
        valid_sat & has_wtd & enough &
        (sat_2d > cfg.SAT_THRESHOLD) &
        (frac >= cfg.WTD_FRAC_THRESHOLD) &
        (~open_water_2d)
    )


def _compute_is_gdw_frozen_wtd(sat_2d, wtd_clim_month, open_water_2d):
    """GDW mask using frozen WTD climatology (scalar threshold, not fraction)."""
    valid_sat = np.isfinite(sat_2d)
    valid_wtd = np.isfinite(wtd_clim_month)
    return (
        valid_sat & valid_wtd &
        (sat_2d > cfg.SAT_THRESHOLD) &
        (wtd_clim_month >= cfg.WTD_MIN) &
        (wtd_clim_month <= cfg.WTD_MAX) &
        (~open_water_2d)
    )


def _process_year(wtd_np, sat_np, lu_np, lu_frozen_np,
                  wtd_clim,          # (12, n_lat_c, n_lon_c) or None
                  open_water_2d,
                  pixel_area_2d,
                  labels, n_lat_c, n_lon_c,
                  months=None):
    """
    Compute all 4 f_gdw variants for one year.

    Returns dict of float32 arrays (n_t, n_lat_c, n_lon_c):
      f_gdw, f_gdw_nonlu, f_gdw_freeze_lu, f_gdw_freeze_wtd
      area_gdw_km2, area_gdw_nonlu_km2,
      area_gdw_freeze_lu_km2, area_gdw_freeze_wtd_km2
    """
    n_coarse = n_lat_c * n_lon_c
    n_t      = wtd_np.shape[0]

    out = {}
    for name in ("f_gdw", "f_gdw_nonlu", "f_gdw_freeze_lu", "f_gdw_freeze_wtd",
                 "area_gdw_km2", "area_gdw_nonlu_km2",
                 "area_gdw_freeze_lu_km2", "area_gdw_freeze_wtd_km2"):
        out[name] = np.full((n_t, n_lat_c, n_lon_c), np.nan, dtype=np.float32)

    for ti in range(n_t):
        flat = wtd_np[ti].ravel()
        vc, sc, _ = _aggregate_one(flat, labels, n_coarse)

        vc2  = vc.reshape(n_lat_c, n_lon_c)
        sc2  = sc.reshape(n_lat_c, n_lon_c)
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = np.where(vc2 > 0, sc2 / vc2.astype(np.float32), np.nan).astype(np.float32)

        sat_2d  = sat_np[ti]
        is_gdw  = _compute_is_gdw(sat_2d, frac, vc2, open_water_2d)

        # ── LU arrays ───────────────────────────────────────────────────────
        lu_dyn = (np.clip(np.nan_to_num(lu_np[ti], nan=0.0), 0.0, 1.0)
                  if lu_np is not None
                  else np.zeros((n_lat_c, n_lon_c), dtype=np.float32))

        lu_frz = (np.clip(np.nan_to_num(lu_frozen_np[ti], nan=0.0), 0.0, 1.0)
                  if lu_frozen_np is not None
                  else lu_dyn)

        # ── full ─────────────────────────────────────────────────────────────
        fgdw = np.where(is_gdw,
                        sat_2d.astype(np.float32) * (1.0 - lu_dyn),
                        np.nan).astype(np.float32)
        out["f_gdw"][ti]       = fgdw
        out["area_gdw_km2"][ti] = np.where(np.isfinite(fgdw),
                                            fgdw * pixel_area_2d, np.nan).astype(np.float32)

        # ── nonlu ────────────────────────────────────────────────────────────
        fgdw_nl = np.where(is_gdw, sat_2d.astype(np.float32), np.nan).astype(np.float32)
        out["f_gdw_nonlu"][ti]       = fgdw_nl
        out["area_gdw_nonlu_km2"][ti] = np.where(np.isfinite(fgdw_nl),
                                                   fgdw_nl * pixel_area_2d, np.nan).astype(np.float32)

        # ── freeze_lu ────────────────────────────────────────────────────────
        fgdw_fl = np.where(is_gdw,
                           sat_2d.astype(np.float32) * (1.0 - lu_frz),
                           np.nan).astype(np.float32)
        out["f_gdw_freeze_lu"][ti]       = fgdw_fl
        out["area_gdw_freeze_lu_km2"][ti] = np.where(np.isfinite(fgdw_fl),
                                                       fgdw_fl * pixel_area_2d, np.nan).astype(np.float32)

        # ── freeze_wtd ───────────────────────────────────────────────────────
        if wtd_clim is not None and months is not None:
            mo         = int(months[ti]) - 1  # 0-indexed
            wtd_frozen = wtd_clim[mo]
            is_gdw_fw  = _compute_is_gdw_frozen_wtd(sat_2d, wtd_frozen, open_water_2d)
            fgdw_fw    = np.where(is_gdw_fw,
                                   sat_2d.astype(np.float32) * (1.0 - lu_dyn),
                                   np.nan).astype(np.float32)
        else:
            fgdw_fw = np.full((n_lat_c, n_lon_c), np.nan, dtype=np.float32)

        out["f_gdw_freeze_wtd"][ti]       = fgdw_fw
        out["area_gdw_freeze_wtd_km2"][ti] = np.where(np.isfinite(fgdw_fw),
                                                        fgdw_fw * pixel_area_2d, np.nan).astype(np.float32)

    return out


def _create_variable(nc, name, dtype, dims, spec, fill_value):
    spec   = spec or {}
    kwargs = {"fill_value": fill_value}
    for k in ("zlib", "complevel", "shuffle", "fletcher32", "chunksizes"):
        if k in spec:
            kwargs[k] = spec[k]
    return nc.createVariable(name, dtype, dims, **kwargs)


def _set_attrs(obj, attrs: dict):
    for k, v in (attrs or {}).items():
        if k != "_FillValue":
            obj.setncattr(k, v)


def _init_output_netcdf(out_path, sat_template, enc, global_attrs, var_attrs):
    if os.path.exists(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass

    n_lat    = sat_template.sizes["lat"]
    n_lon    = sat_template.sizes["lon"]
    lat_vals = sat_template["lat"].values.astype(np.float32)
    lon_vals = sat_template["lon"].values.astype(np.float32)

    nc = Dataset(out_path, "w", format=cfg.NC_FORMAT)
    _set_attrs(nc, global_attrs)

    nc.createDimension("time", None)
    nc.createDimension("lat",  n_lat)
    nc.createDimension("lon",  n_lon)

    time_var = nc.createVariable("time", "f8", ("time",))
    lat_var  = nc.createVariable("lat",  "f4", ("lat",))
    lon_var  = nc.createVariable("lon",  "f4", ("lon",))

    lat_var[:] = lat_vals
    lon_var[:] = lon_vals

    time_var.units    = "days since 1900-01-01 00:00:00"
    time_var.calendar = "standard"
    _set_attrs(time_var, var_attrs.get("time", {}))
    _set_attrs(lat_var,  var_attrs.get("lat",  {}))
    _set_attrs(lon_var,  var_attrs.get("lon",  {}))

    FILL = np.float32(-9999.0)

    # 8 output variables
    nc_vars = [
        ("f_gdw",                "GDW saturation fraction (dynamic WTD, dynamic LU)"),
        ("f_gdw_nonlu",          "GDW saturation fraction (dynamic WTD, no LU exclusion)"),
        ("f_gdw_freeze_lu",      "GDW saturation fraction (dynamic WTD, frozen historical LU)"),
        ("f_gdw_freeze_wtd",     "GDW saturation fraction (frozen WTD climatology, dynamic LU)"),
        ("area_gdw_km2",         "GDW area km2 (dynamic WTD, dynamic LU)"),
        ("area_gdw_nonlu_km2",   "GDW area km2 (dynamic WTD, no LU exclusion)"),
        ("area_gdw_freeze_lu_km2",  "GDW area km2 (dynamic WTD, frozen historical LU)"),
        ("area_gdw_freeze_wtd_km2", "GDW area km2 (frozen WTD climatology, dynamic LU)"),
    ]
    for vname, long_name in nc_vars:
        v = _create_variable(nc, vname, "f4", ("time", "lat", "lon"),
                             enc.get(vname, {}), FILL)
        v.long_name = long_name
        v.units     = "1" if vname.startswith("f_") else "km2"
        _set_attrs(v, var_attrs.get(vname, {}))

    nc.close()


def _append_year(out_path, year_arrays, t_yr):
    nc      = Dataset(out_path, "a")
    n_exist = nc.dimensions["time"].size
    n_new   = len(t_yr)
    sl      = slice(n_exist, n_exist + n_new)

    tvar = nc.variables["time"]
    nums = date2num(
        pd.to_datetime(t_yr).to_pydatetime(),
        units=tvar.units,
        calendar=getattr(tvar, "calendar", "standard"),
    )
    tvar[sl] = nums

    for vname, arr in year_arrays.items():
        nc.variables[vname][sl] = arr

    nc.close()


def run_pipeline(
    sat: xr.DataArray,
    wtd: xr.DataArray,
    lu,
    lu_frozen,              # PcrLazy with frozen LU, or None
    wtd_clim,               # np.ndarray (12, ny, nx) monthly climatology or None
    open_water_2d: np.ndarray,
    pixel_area_2d: np.ndarray,
    scen: str,
    out_path: str,
    enc: dict,
    global_attrs: dict,
    var_attrs: dict,
    on_year_arrays=None,
) -> None:
    """
    Compute and write all 8 f_gdw / area variables year by year.

    Parameters
    ----------
    sat            : satAreaFrac DataArray (5 arcmin)
    wtd            : WTD DataArray (~30 arcsec)
    lu             : PcrLazy instance (dynamic LU) or None
    lu_frozen      : PcrLazy instance (frozen historical LU) or None
    wtd_clim       : (12, ny_sat, nx_sat) monthly WTD climatology or None
    open_water_2d  : bool (ny_sat, nx_sat)
    pixel_area_2d  : float32 (ny_sat, nx_sat) km2
    scen           : scenario name
    out_path       : output NC path
    enc            : encoding dict
    global_attrs   : global NC attributes
    var_attrs      : per-variable NC attributes
    on_year_arrays : optional callback(year_arrays, t_yr)
    """
    target = lon_range(wtd)
    sat    = unify_longitudes(sat, target)
    wtd    = unify_longitudes(wtd, target)
    sat, wtd = align_time(sat, wtd)

    sat = sat.astype("float32")
    wtd = wtd.astype("float32")
    sat = sat.sel(time=(sat["time"].dt.year >= START_YEAR) & (sat["time"].dt.year <= END_YEAR))
    wtd = wtd.sel(time=(wtd["time"].dt.year >= START_YEAR) & (wtd["time"].dt.year <= END_YEAR))

    n_lat_c = sat.sizes["lat"]
    n_lon_c = sat.sizes["lon"]

    print(f"  [setup] scenario: {scen}")
    print(f"  [setup] WTD: {wtd.sizes['lat']} x {wtd.sizes['lon']}")
    print(f"  [setup] SAT: {n_lat_c} x {n_lon_c}")
    print(f"  [setup] wtd_clim available: {wtd_clim is not None}")
    print(f"  [setup] lu_frozen available: {lu_frozen is not None}")
    print(f"  [setup] open_water excluded pixels: {open_water_2d.sum():,}")
    print(f"  [setup] pixel_area mean: {pixel_area_2d.mean():.2f} km2")
    print(f"  [setup] building int32 labels array ...")
    labels = _build_labels(wtd, sat)

    # remap wtd_clim from QA/input grid to sat grid if needed
    if wtd_clim is not None:
        clim_shape = wtd_clim.shape  # (12, ny_clim, nx_clim)
        ny_sat, nx_sat = sat.sizes["lat"], sat.sizes["lon"]
        if clim_shape[1] != ny_sat or clim_shape[2] != nx_sat:
            print(f"  [setup] remapping wtd_clim {clim_shape} -> sat grid ({ny_sat},{nx_sat}) ...")
            import scipy.ndimage as _nd
            zoom_y = ny_sat / clim_shape[1]
            zoom_x = nx_sat / clim_shape[2]
            wtd_clim = np.stack([
                _nd.zoom(wtd_clim[m], (zoom_y, zoom_x), order=1).astype(np.float32)
                for m in range(12)
            ], axis=0)
            print(f"  [setup] wtd_clim remapped to {wtd_clim.shape}")

    if _USE_NUMBA:
        _dummy = np.zeros(100, dtype=np.float32)
        _dlbl  = np.zeros(100, dtype=np.int32)
        _aggregate_numba(_dummy, _dlbl, 10,
                         np.float32(cfg.WTD_MIN), np.float32(cfg.WTD_MAX))
        print("  [setup] numba warmed up")

    times = pd.DatetimeIndex(wtd["time"].values)
    years = sorted(set(times.year))
    n_yrs = len(years)

    if n_yrs == 0:
        raise ValueError(f"No years available after START_YEAR={START_YEAR}")

    print(f"  [setup] {n_yrs} years ({years[0]}-{years[-1]}) -> {out_path}")
    _init_output_netcdf(out_path, sat, enc, global_attrs, var_attrs)

    for yi, yr in enumerate(years):
        mask  = times.year == yr
        t_yr  = wtd["time"].values[mask]
        tidxs = np.where(mask)[0]
        months_yr = times[mask].month.values

        print(f"  [year {yi+1:3d}/{n_yrs}] {yr}  loading WTD ...")
        wtd_np = wtd.isel(time=tidxs).values.astype(np.float32)

        print(f"  [year {yi+1:3d}/{n_yrs}] {yr}  loading SAT ...")
        sat_np = sat.isel(time=tidxs).values.astype(np.float32)

        n_t = len(tidxs)

        # dynamic LU
        if lu is not None:
            lu_np = np.stack([
                lu.get_dynamic_tile(int(pd.Timestamp(t_yr[k]).year),
                                    0, n_lat_c, 0, n_lon_c)
                for k in range(n_t)
            ], axis=0).astype(np.float32)
        else:
            lu_np = None

        # frozen LU
        if lu_frozen is not None:
            lu_frozen_np = np.stack([
                lu_frozen.get_dynamic_tile(int(pd.Timestamp(t_yr[k]).year),
                                           0, n_lat_c, 0, n_lon_c)
                for k in range(n_t)
            ], axis=0).astype(np.float32)
        else:
            lu_frozen_np = None

        print(f"  [year {yi+1:3d}/{n_yrs}] {yr}  computing all variants ...")
        year_arrays = _process_year(
            wtd_np, sat_np, lu_np, lu_frozen_np,
            wtd_clim, open_water_2d,
            pixel_area_2d, labels, n_lat_c, n_lon_c,
            months=months_yr,
        )

        del wtd_np, sat_np, lu_np, lu_frozen_np
        gc.collect()

        print(f"  [year {yi+1:3d}/{n_yrs}] {yr}  appending to NC ...")
        _append_year(out_path, year_arrays, t_yr)

        if on_year_arrays is not None:
            on_year_arrays(year_arrays, t_yr)

        del year_arrays
        gc.collect()
        print(f"  [year {yi+1:3d}/{n_yrs}] {yr}  done")

    try:
        size = os.path.getsize(out_path)
        print(f"  [done] {out_path}  {size:,} bytes")
    except Exception:
        print(f"  [done] {out_path}")