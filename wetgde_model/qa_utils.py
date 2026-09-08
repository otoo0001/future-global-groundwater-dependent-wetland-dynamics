"""
qa_utils.py  --  QA mask and open water mask construction.

build_qa_mask         merges QA NC files, excludes mountains/karst/permafrost/spinup
build_open_water_mask reprojects GLWD open-water GeoTIFF onto QA grid
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Tuple

import numpy as np
import rasterio
import rasterio.windows
import xarray as xr

logger = logging.getLogger(__name__)


def _std(ds):
    ren = {}
    if "latitude" in ds.coords:
        ren["latitude"] = "lat"
    if "longitude" in ds.coords:
        ren["longitude"] = "lon"
    return ds.rename(ren) if ren else ds


def _open_qa_merged(qa_paths) -> xr.Dataset:
    base = _std(xr.open_dataset(qa_paths[0], decode_times=False, mask_and_scale=False))
    qa_lat = base["lat"].values
    qa_lon = base["lon"].values
    ny0, nx0 = qa_lat.size, qa_lon.size
    qa_vars = {}

    for p in qa_paths:
        ds = _std(xr.open_dataset(p, decode_times=False, mask_and_scale=False))
        if (
            ds.sizes.get("lat") != ny0
            or ds.sizes.get("lon") != nx0
            or not np.array_equal(ds["lat"].values, qa_lat)
            or not np.array_equal(ds["lon"].values, qa_lon)
        ):
            ds = ds.interp(lat=qa_lat, lon=qa_lon, method="nearest")
        for v in ds.data_vars:
            dv = ds[v]
            if "time" in dv.dims:
                dv = dv.isel(time=0, drop=True)
            qa_vars[v] = dv
        ds.close()

    base.close()
    return xr.Dataset(qa_vars, coords={"lat": qa_lat, "lon": qa_lon})


def build_qa_mask(qa_dir: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Load and merge QA NC files, build boolean exclusion mask.

    Returns
    -------
    qa_lat  : float64 (ny,)
    qa_lon  : float64 (nx,)
    qa_mask : bool    (ny, nx)  True = valid pixel
    """
    qa_paths = sorted(
        [os.path.join(qa_dir, f) for f in os.listdir(qa_dir) if f.endswith(".nc")]
    )
    if not qa_paths:
        raise FileNotFoundError(f"No .nc files in QA_DIR: {qa_dir}")

    qa = _open_qa_merged(qa_paths)
    qa_lat = qa["lat"].values
    qa_lon = qa["lon"].values
    ny, nx = qa_lat.size, qa_lon.size

    def _get(var):
        return qa[var].values if var in qa.data_vars else None

    mount = _get("mountains_qa")
    karst = _get("karst_qa")
    perma = _get("permafrost_qa")
    spin  = _get("spinup_qa")

    static_ok = np.ones((ny, nx), dtype=bool)
    if mount is not None:
        static_ok &= mount == 0
    if karst is not None:
        static_ok &= karst == 0
    if perma is not None:
        static_ok &= perma == 0

    spin_ok = np.ones((ny, nx), dtype=bool)
    if spin is not None:
        spin_ok = ~np.isin(spin, [4, 6])

    qa_mask = (static_ok & spin_ok).astype(bool)
    logger.info(
        "QA mask: grid=(%d,%d)  valid=%.2f%%  "
        "mountains=%s karst=%s permafrost=%s spinup=%s",
        ny, nx, 100.0 * qa_mask.mean(),
        mount is not None, karst is not None, perma is not None, spin is not None,
    )

    try:
        qa.close()
    except Exception:
        pass

    return qa_lat, qa_lon, qa_mask


def build_open_water_mask(
    mask_tif: str,
    qa_lat: np.ndarray,
    qa_lon: np.ndarray,
) -> np.ndarray:
    """
    Read GLWD open-water GeoTIFF via GDAL (bypasses rasterio read issues on HPC).
    Returns bool (ny, nx): True = open water (to be excluded).
    """
    if not Path(mask_tif).exists():
        raise FileNotFoundError(f"Open-water mask not found: {mask_tif}")

    try:
        from osgeo import gdal
        gdal.UseExceptions()
        ds   = gdal.Open(mask_tif, gdal.GA_ReadOnly)
        band = ds.GetRasterBand(1)
        arr  = band.ReadAsArray().astype(np.uint8)
        gt   = ds.GetGeoTransform()
        nodata = band.GetNoDataValue()
        ds = None
        t_c, t_a, t_f, t_e = gt[0], gt[1], gt[3], gt[5]
    except Exception as gdal_err:
        raise RuntimeError(
            f"Could not read open-water mask with GDAL: {mask_tif}\n{gdal_err}"
        )

    src_ny, src_nx = arr.shape
    src_lon = t_c + (np.arange(src_nx) + 0.5) * t_a
    src_lat = t_f + (np.arange(src_ny) + 0.5) * t_e

    if src_lat[0] > src_lat[-1]:
        src_lat_asc = src_lat[::-1]
        lat_rev = True
    else:
        src_lat_asc = src_lat
        lat_rev = False

    src_lon_max = float(src_lon.max())
    tgt_lon = np.array(qa_lon, copy=True, dtype=np.float64)
    if src_lon_max > 180.0 and tgt_lon.min() < 0.0:
        tgt_lon = np.mod(tgt_lon, 360.0)
    elif src_lon_max <= 180.0 and tgt_lon.max() > 180.0:
        tgt_lon = ((tgt_lon + 180.0) % 360.0) - 180.0

    def _nn(src, tgt):
        idx = np.searchsorted(src, tgt)
        idx = np.clip(idx, 1, len(src) - 1)
        left, right = src[idx - 1], src[idx]
        use_left = (tgt - left) <= (right - tgt)
        return (idx - use_left.astype(np.int32)).astype(np.int32)

    lat_idx = _nn(src_lat_asc, qa_lat)
    if lat_rev:
        lat_idx = (src_ny - 1) - lat_idx
    lon_idx = _nn(src_lon, tgt_lon)

    remapped = arr[np.ix_(lat_idx, lon_idx)]
    open_water = (remapped > 0) if nodata is None else ((remapped > 0) & (remapped != nodata))

    logger.info("Open-water mask: excluded=%.2f%% of grid", 100.0 * open_water.mean())
    return open_water.astype(bool)

