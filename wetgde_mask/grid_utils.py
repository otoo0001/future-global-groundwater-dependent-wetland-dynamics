"""
grid_utils.py  --  coordinate standardisation, longitude unification,
                   regional subsetting, chunking, and attribute helpers.
"""

import numpy as np
import xarray as xr
from . import config as cfg


def ascii(s) -> str:
    return str(s).encode("ascii", "ignore").decode("ascii")


def standardize_coords(da) -> xr.DataArray:
    rename = {}
    if "latitude"  in da.dims: rename["latitude"]  = "lat"
    if "longitude" in da.dims: rename["longitude"] = "lon"
    if "y" in da.dims and "lat" not in da.dims: rename["y"] = "lat"
    if "x" in da.dims and "lon" not in da.dims: rename["x"] = "lon"
    return da.rename(rename) if rename else da


def sort_coords(da: xr.DataArray) -> xr.DataArray:
    for d in ("lat", "lon"):
        if d in da.dims and np.any(np.diff(da[d].values) < 0):
            da = da.sortby(d)
    return da


def lon_range(da: xr.DataArray) -> str:
    if "lon" not in da.dims:
        return "m180_180"
    vmin = float(da["lon"].min())
    vmax = float(da["lon"].max())
    return "0_360" if vmin >= -1e-6 and vmax <= 360.0 + 1e-6 else "m180_180"


def unify_longitudes(da: xr.DataArray, target: str) -> xr.DataArray:
    if "lon" not in da.dims:
        return da
    lon  = da["lon"]
    vmin = float(lon.min())
    vmax = float(lon.max())
    if target == "0_360":
        if vmin < 0 or vmax > 360:
            da = da.assign_coords(
                lon=xr.where(lon < 0, lon + 360.0, lon)
            ).sortby("lon")
    else:
        if vmin < -180 or vmax > 180:
            da = da.assign_coords(
                lon=((lon + 180.0) % 360.0) - 180.0
            ).sortby("lon")
    return da


def subset_region(da: xr.DataArray, region_name: str) -> xr.DataArray:
    region = cfg.REGIONS.get(region_name, cfg.REGIONS["great_plains"])
    lat_lo, lat_hi = region["lat"]
    lon_lo, lon_hi = region["lon"]
    da = sort_coords(da)
    if "lon" in da.dims and lon_range(da) == "0_360":
        lon_lo = lon_lo if lon_lo >= 0 else lon_lo + 360.0
        lon_hi = lon_hi if lon_hi >= 0 else lon_hi + 360.0
        if lon_lo <= lon_hi:
            return da.sel(lat=slice(lat_lo, lat_hi), lon=slice(lon_lo, lon_hi))
        left  = da.sel(lat=slice(lat_lo, lat_hi), lon=slice(lon_lo, 360.0))
        right = da.sel(lat=slice(lat_lo, lat_hi), lon=slice(0.0,    lon_hi))
        return xr.concat([left, right], dim="lon").sortby("lon")
    return da.sel(lat=slice(lat_lo, lat_hi), lon=slice(lon_lo, lon_hi))


def chunk_map(da: xr.DataArray, targets: dict) -> dict:
    out = {}
    for d in da.dims:
        size   = int(da.sizes[d])
        target = int(targets.get(d, size))
        out[d] = max(1, min(target, size))
    return out


def align_time(a: xr.DataArray, b: xr.DataArray):
    if "time" not in a.dims or "time" not in b.dims:
        return a, b
    common = np.intersect1d(a["time"].values, b["time"].values)
    if common.size == 0:
        raise ValueError("No overlapping time steps between SAT and WTD")
    return a.sel(time=common), b.sel(time=common)


def sanitize_dataset_attrs(ds: xr.Dataset) -> xr.Dataset:
    ds.attrs = {k: ascii(v) for k, v in ds.attrs.items()}
    ds.attrs.setdefault("institution", cfg.INSTITUTION)
    if "history" in ds.attrs:
        ds.attrs["history"] = ascii(ds.attrs["history"])
    if "time" in ds.coords:
        ds["time"].attrs["standard_name"] = "time"
        ds["time"].attrs.setdefault("long_name", "time")
    if "lat" in ds.coords:
        ds["lat"].attrs.update({
            "standard_name": "latitude",
            "units":         "degrees_north",
            "long_name":     "latitude",
        })
    if "lon" in ds.coords:
        ds["lon"].attrs.update({
            "standard_name": "longitude",
            "units":         "degrees_east",
            "long_name":     "longitude",
        })
    return ds