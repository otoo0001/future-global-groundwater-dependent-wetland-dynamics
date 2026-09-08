"""
io.py  --  open satAreaFrac (PCR-GLOBWB, 5 arcmin) and WTD (GLOBGM zarr, ~30 arcsec).

Optimisations
-------------
1. WTD is clipped to the SAT domain before loading to reduce memory.
2. WTD zarr is opened with chunks matching native zarr chunk shape
   (time=2, lat=1280, lon=1200) so reads are chunk-aligned and fast.
3. Layer combination is done lazily before any data is loaded.
"""

import os
import numpy as np
import xarray as xr

from . import config as cfg
from .grid_utils import standardize_coords, sort_coords, subset_region


def open_sat(scen: str) -> xr.DataArray:
    """
    Load satAreaFrac at native 5 arcmin (PCR-GLOBWB).
    Loaded eagerly as it is small (2160 x 4320 x n_time x 4 bytes ~ 500 MB).
    """
    path = os.path.join(cfg.SAT_DIR, f"satAreaFrac_monthly_ensemble_mean_{scen}.nc")
    if not os.path.exists(path):
        raise FileNotFoundError(f"SAT file not found: {path}")

    ds = xr.open_dataset(path, decode_times=True, chunks=None)
    da = ds[cfg.SAT_VAR] if cfg.SAT_VAR in ds else ds[list(ds.data_vars)[0]]
    da = standardize_coords(da)
    da = sort_coords(da)

    if cfg.SMALL_TEST:
        da = subset_region(da, cfg.REGION_NAME)

    if int(da.sizes.get("lat", 0)) == 0 or int(da.sizes.get("lon", 0)) == 0:
        raise ValueError(f"SAT for {scen} has empty spatial dims")

    return da.astype("float32")


def open_wtd(scen: str, sat: xr.DataArray) -> xr.DataArray:
    """
    Load WTD from GLOBGM zarr, clipped to the SAT domain.

    Optimisations:
    - Clips WTD to SAT lat/lon extent before any data is read,
      reducing memory by up to 30% at polar edges.
    - Opens with chunks matching the native zarr chunk shape
      (time=2, lat=1280, lon=1200) so IO is chunk-aligned.
    - Layer combination is lazy (no data read until .values is called).

    Parameters
    ----------
    scen : scenario name
    sat  : satAreaFrac DataArray, used to determine clipping domain
    """
    zpath = os.path.join(cfg.WTD_ROOT, scen, "ensemble.zarr")
    if not os.path.isdir(zpath):
        raise FileNotFoundError(f"WTD zarr not found: {zpath}")

    # open with zarr-native chunk shape for aligned reads
    ds = xr.open_zarr(
        zpath,
        zarr_format=3,
        chunks={
            "model":     1,
            "layer":     1,
            "time":      cfg.WTD_TIME_CHUNK,
            "latitude":  cfg.WTD_LAT_CHUNK,
            "longitude": cfg.WTD_LON_CHUNK,
        },
    )

    if cfg.WTD_VAR not in ds:
        raise KeyError(f"'{cfg.WTD_VAR}' not in {zpath}. Has: {list(ds.data_vars)}")

    # select ensemble model (lazy)
    wtd_raw = ds[cfg.WTD_VAR].sel(model=cfg.WTD_MODEL)

    # combine layers lazily: layer 1 primary, layer 2 fallback
    l1  = wtd_raw.sel(layer=cfg.WTD_LAYER1)
    l2  = wtd_raw.sel(layer=cfg.WTD_LAYER2)
    wtd = xr.where(l1.notnull(), l1, l2)

    # standardize coordinate names
    wtd = standardize_coords(wtd)
    wtd = sort_coords(wtd)

    # clip to SAT domain to reduce memory
    # add a small buffer (2 fine cells) to avoid clipping valid edge cells
    sat_lat = sat["lat"].values
    sat_lon = sat["lon"].values
    lat_res = float(abs(sat_lat[1] - sat_lat[0]))
    lon_res = float(abs(sat_lon[1] - sat_lon[0]))

    lat_min = float(sat_lat.min()) - 2 * lat_res
    lat_max = float(sat_lat.max()) + 2 * lat_res
    lon_min = float(sat_lon.min()) - 2 * lon_res
    lon_max = float(sat_lon.max()) + 2 * lon_res

    wtd = wtd.sel(
        lat=slice(lat_min, lat_max) if wtd["lat"].values[0] < wtd["lat"].values[-1]
            else slice(lat_max, lat_min),
        lon=slice(lon_min, lon_max),
    )

    if cfg.SMALL_TEST:
        wtd = subset_region(wtd, cfg.REGION_NAME)

    if int(wtd.sizes.get("lat", 0)) == 0 or int(wtd.sizes.get("lon", 0)) == 0:
        raise ValueError(f"WTD for {scen} has empty spatial dims after clipping")

    # restrict to start year
    wtd = wtd.sel(time=wtd.time.dt.year >= 1969)
    return wtd.astype("float32")


def sat_source_path(scen: str) -> str:
    return os.path.join(cfg.SAT_DIR, f"satAreaFrac_monthly_ensemble_mean_{scen}.nc")