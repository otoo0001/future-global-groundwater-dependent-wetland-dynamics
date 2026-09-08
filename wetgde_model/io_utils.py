"""
io_utils.py  --  lazy input opening, regrid index construction, tile reads.

Nothing here loads a full global array. All spatial reads are tile-scoped.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)


# ---- coordinate normalisation ----

def _std_coords(obj):
    """Rename latitude/longitude/y/x -> lat/lon wherever needed."""
    ren = {}
    for old, new in [("latitude", "lat"), ("longitude", "lon"),
                     ("y", "lat"), ("x", "lon")]:
        if old in obj.dims and new not in obj.dims:
            ren[old] = new
    return obj.rename(ren) if ren else obj


def _sort_latlon(da: xr.DataArray) -> xr.DataArray:
    for dim in ("lat", "lon"):
        if dim in da.dims and np.any(np.diff(da[dim].values) < 0):
            da = da.sortby(dim)
    return da


# ---- open functions ----

def open_sat(path: str, chunks: Optional[dict] = None) -> xr.DataArray:
    """
    Open satAreaFrac NetCDF lazily.
    Returns float32 DataArray, lat/lon ascending.
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"satAreaFrac not found: {path}")
    ds = xr.open_dataset(str(path), decode_times=True, chunks=chunks or {})
    ds = _std_coords(ds)
    var = "satAreaFrac" if "satAreaFrac" in ds.data_vars else list(ds.data_vars)[0]
    da = _sort_latlon(ds[var].astype("float32"))
    logger.debug("Opened sat %s  shape=%s", Path(path).name, dict(da.sizes))
    return da


def open_wtd(path: str) -> xr.DataArray:
    """
    Open GLOBGM WTD zarr.
    Merges layer 1 (primary) and layer 2 (fallback).
    Returns float32 DataArray, lat/lon ascending.
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"WTD zarr not found: {path}")

    ds = None
    for kw in ({"consolidated": True}, {"consolidated": False}, {"zarr_version": 3}):
        try:
            ds = xr.open_zarr(str(path), **kw)
            break
        except Exception:
            continue
    if ds is None:
        raise RuntimeError(f"Could not open zarr with any strategy: {path}")

    ds = _std_coords(ds)

    if "layer" not in ds.dims:
        raise KeyError(f"Expected 'layer' dim in {path}, got dims: {list(ds.dims)}")
    if "wtd" not in ds.data_vars:
        raise KeyError(f"Expected 'wtd' variable in {path}, got: {list(ds.data_vars)}")

    raw = ds["wtd"]
    # drop model dimension if present
    if "model" in raw.dims:
        raw = raw.isel(model=0, drop=True)
    l1 = raw.sel(layer=1, drop=True)
    l2 = raw.sel(layer=2, drop=True)
    wtd = xr.where(l1.isnull(), l2, l1).astype("float32")
    wtd = _sort_latlon(wtd)

    logger.debug("Opened WTD %s  shape=%s", Path(path).name, dict(wtd.sizes))
    return wtd


# ---- regridding ----

def _nn_indices(src: np.ndarray, tgt: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(src, tgt)
    idx = np.clip(idx, 1, len(src) - 1)
    left, right = src[idx - 1], src[idx]
    use_left = (tgt - left) <= (right - tgt)
    return (idx - use_left.astype(np.int32)).astype(np.int32)


def _match_lon_convention(src_lon: np.ndarray, tgt_lon: np.ndarray) -> np.ndarray:
    src_max = float(np.nanmax(src_lon))
    tgt = np.array(tgt_lon, copy=True, dtype=np.float64)
    if src_max > 180.0 and float(np.nanmin(tgt)) < 0.0:
        tgt = np.mod(tgt, 360.0)
    elif src_max <= 180.0 and float(np.nanmax(tgt)) > 180.0:
        tgt = ((tgt + 180.0) % 360.0) - 180.0
    return tgt


def build_regrid_indices(
    src_lat: np.ndarray,
    src_lon: np.ndarray,
    tgt_lat: np.ndarray,
    tgt_lon: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Nearest-neighbour index arrays: src_data[lat_idx[i], lon_idx[j]] -> tgt[i, j].
    Handles descending source latitudes and lon convention mismatches.
    """
    if src_lat[0] > src_lat[-1]:
        lat_idx = _nn_indices(src_lat[::-1], tgt_lat)
        lat_idx = (len(src_lat) - 1) - lat_idx
    else:
        lat_idx = _nn_indices(src_lat, tgt_lat)

    lon_idx = _nn_indices(src_lon, _match_lon_convention(src_lon, tgt_lon))
    return lat_idx.astype(np.int32), lon_idx.astype(np.int32)


def read_tile(
    da: xr.DataArray,
    t_idx: int,
    lat_idx: np.ndarray,
    lon_idx: np.ndarray,
    y0: int, y1: int,
    x0: int, x1: int,
) -> np.ndarray:
    """
    Read one time slice of da regridded to target grid, for tile [y0:y1, x0:x1].
    Only fetches the bounding box of source pixels needed.
    Returns float32 (y1-y0, x1-x0).
    """
    src_lat = lat_idx[y0:y1]
    src_lon = lon_idx[x0:x1]
    lat_lo, lat_hi = int(src_lat.min()), int(src_lat.max())
    lon_lo, lon_hi = int(src_lon.min()), int(src_lon.max())
    box = (
        da.isel(
            time=t_idx,
            lat=slice(lat_lo, lat_hi + 1),
            lon=slice(lon_lo, lon_hi + 1),
        ).values.astype(np.float32)
    )
    return box[np.ix_(src_lat - lat_lo, src_lon - lon_lo)]


# ---- time alignment ----

def align_times(
    sat_times: np.ndarray,
    wtd_times: np.ndarray,
) -> Tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """
    Year-month intersection of two time axes.
    Returns (common_times, sat_indices, wtd_indices).
    Uses period matching so minor timestamp differences do not break alignment.
    """
    sat_p = pd.DatetimeIndex(sat_times).to_period("M")
    wtd_p = pd.DatetimeIndex(wtd_times).to_period("M")
    sat_s = pd.Series(np.arange(len(sat_p)), index=sat_p)
    wtd_s = pd.Series(np.arange(len(wtd_p)), index=wtd_p)
    common = sat_s.index.intersection(wtd_s.index)
    if len(common) == 0:
        raise ValueError("No overlapping time steps between satAreaFrac and WTD")
    sat_idx = sat_s.loc[common].values.astype(int)
    wtd_idx = wtd_s.loc[common].values.astype(int)
    common_times = pd.DatetimeIndex(sat_times)[sat_idx]
    logger.debug(
        "Aligned %d time steps  %s .. %s",
        len(common_times), str(common_times[0].date()), str(common_times[-1].date()),
    )
    return common_times, sat_idx, wtd_idx


# ---- WTD monthly climatology ----
def build_wtd_climatology(
    zarr_path,
    clim_window,
    target_lat=None,
    target_lon=None,
):
    """
    Build monthly WTD climatology.

    Parameters
    ----------
    zarr_path : str
        Path to WTD zarr.
    clim_window : str
        "YYYY-MM-DD,YYYY-MM-DD"
    target_lat, target_lon : np.ndarray or None
        Optional target grid.

    Returns
    -------
    np.ndarray
        Monthly climatology with shape (12, ny, nx)
    """
    import numpy as np
    import pandas as pd
    import xarray as xr

    start, end = [x.strip() for x in clim_window.split(",")]

    ds = xr.open_zarr(zarr_path, consolidated=False)

    # detect WTD variable
    if "wtd" in ds.data_vars:
        var = "wtd"
    else:
        var = list(ds.data_vars)[0]

    da = ds[var].sel(time=slice(start, end))

    # coordinate names
    lat_name = "lat" if "lat" in da.dims else "latitude"
    lon_name = "lon" if "lon" in da.dims else "longitude"

    # optional interpolation
    # build climatology on native grid first (fast), then remap to target
    times = pd.DatetimeIndex(da["time"].values)
    ny_nat = da.sizes[lat_name]
    nx_nat = da.sizes[lon_name]

    sums   = np.zeros((12, ny_nat, nx_nat), dtype=np.float64)
    counts = np.zeros((12, ny_nat, nx_nat), dtype=np.int32)

    for i, ts in enumerate(times):
        m    = ts.month - 1
        slab = da.isel(time=i)
        for dim in ("model", "layer"):
            if dim in slab.dims:
                slab = slab.isel({dim: 0})
        slab  = slab.values.astype(np.float32)
        valid = np.isfinite(slab)
        sums[m][valid]   += slab[valid]
        counts[m][valid] += 1

    clim_nat = np.full((12, ny_nat, nx_nat), np.nan, dtype=np.float32)
    valid = counts > 0
    clim_nat[valid] = (sums[valid] / counts[valid]).astype(np.float32)
    ds.close()

    # remap native climatology to target grid if needed
    if target_lat is not None and target_lon is not None:
        from .io_utils import build_regrid_indices as _bri
        nat_lat = da[lat_name].values
        nat_lon = da[lon_name].values
        r_lat, r_lon = _bri(nat_lat, nat_lon, target_lat, target_lon)
        clim_nat = clim_nat[:, r_lat, :][:, :, r_lon]

    return clim_nat
