#!/usr/bin/env python3
"""
wtd_sat_sensitivity_validation_monthly_gswp3w5e5_2015_2019.py

Monthly-first GDW sensitivity validation.

This version:
1. Uses GSWP3-W5E5 historical forcing.
2. Uses 2015-2019.
3. Applies WTD and satAreaFrac thresholds per month.
4. Aggregates monthly GDW to temporal presence using any(time).
5. Validates against Rhodes ∩ GLWD dryland reference with 10 km tolerance.
"""

from pathlib import Path
import tempfile
import gc

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import reproject
from rasterio.enums import Resampling
from rasterio.transform import xy
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from scipy.ndimage import distance_transform_edt
import xarray as xr
from numba import njit

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib as mpl

mpl.rcParams["font.family"] = "sans-serif"
mpl.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans"]


# =============================================================================
# PATHS
# =============================================================================
SAT_FILE = Path(
    "/projects/prjs1222/globgm_input/_data/cmip6_input/gswp3-w5e5/"
    "historical/sat_area_fraction_monthly.nc"
)

WTD_ZARR = Path(
    "/projects/prjs1222/globgm_output/historical_reference/"
    "monthly/gswp3-w5e5.zarr"
)

INTERSECTION_TIF = Path(
    "/path/to/scratch/from_projects/validation/input_files/"
    "rhodes_2024_gde/Rhodes/glwd_rhodes_intersection_for_validation/"
    "glwd_rhodes_intersection_binary_no_open.tif"
)

DRYLAND_MASK_TIF = Path(
    "/path/to/scratch/from_projects/validation/input_files/"
    "koppen_geiger/1991_2020/koppen_geiger_0p5.tif"
)

GLWD_CLASS_TIF = Path(
    "/path/to/scratch/from_projects/validation/input_files/"
    "glwd/GLWD_v2_delta_combined_classes/GLWD_v2_delta_main_class.tif"
)

OUTDIR = Path(
    "/path/to/scratch/paper_3/new_outputs/"
    "sensitivity/plots/wtd_sat_sensitivity_validation_monthly_2km_tolerance"
)
OUTDIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# SETTINGS
# =============================================================================
WTD_THRESHOLDS = [0.1, 1.0, 2.0, 3.0, 4.0, 5.0,6.0,7.0,8.0]
SAT_THRESHOLDS = [0.25, 0.50, 0.75]

WTD_FRAC_THRESHOLD = 0.5
MIN_VALID_FINE = 5

WTD_VAR = "wtd"
WTD_LAYER1 = 1
WTD_LAYER2 = 2
SAT_VAR_CANDIDATES = ["satAreaFrac", "sat_area_fraction", "satAreaFraction", "sat"]

ANALYSIS_PERIOD = ("2015-01", "2019-12")

TOLERANCE_KM = 2.0
DRYLAND_CLASSES = {4, 5, 6, 7, 8, 9, 10}
INTERSECTION_POSITIVE = 1
PAD = 200
TILE_SIZE = 1200


def log(msg):
    print(f"[{pd.Timestamp.now():%H:%M:%S}] {msg}", flush=True)


def find_coord_name(ds, candidates):
    for name in candidates:
        if name in ds.coords or name in ds.variables:
            return name
    raise KeyError(f"None of these coordinate names found: {candidates}")


def find_sat_var(ds):
    for name in SAT_VAR_CANDIDATES:
        if name in ds.data_vars:
            return name
    if len(ds.data_vars) == 1:
        return list(ds.data_vars)[0]
    raise KeyError(f"Could not infer SAT variable. Available variables: {list(ds.data_vars)}")


# =============================================================================
# LOAD MODEL DATA
# =============================================================================
def open_sat_dataset():
    log(f"Opening SAT monthly file: {SAT_FILE}")
    ds = xr.open_dataset(SAT_FILE, decode_times=True, mask_and_scale=True)

    sat_var = find_sat_var(ds)
    lat_name = find_coord_name(ds, ["lat", "latitude", "y"])
    lon_name = find_coord_name(ds, ["lon", "longitude", "x"])

    sat = ds[sat_var].sel(time=slice(*ANALYSIS_PERIOD))

    if lat_name != "lat" or lon_name != "lon":
        sat = sat.rename({lat_name: "lat", lon_name: "lon"})
        ds = ds.rename({lat_name: "lat", lon_name: "lon"})

    if sat["lat"].values[0] < sat["lat"].values[-1]:
        sat = sat.sortby("lat", ascending=False)

    if sat["lon"].values[0] > sat["lon"].values[-1]:
        sat = sat.sortby("lon")

    return ds, sat


def open_wtd_dataset():
    log(f"Opening monthly WTD zarr: {WTD_ZARR}")
    ds = xr.open_zarr(str(WTD_ZARR), consolidated=False)
    da = ds[WTD_VAR]

    if "time" not in da.dims:
        raise ValueError(
            "WTD_ZARR has no time dimension. Use the monthly WTD zarr, not average_ensemble.zarr."
        )

    da = da.sel(time=slice(*ANALYSIS_PERIOD))

    wtd_l1 = da.sel(layer=WTD_LAYER1, drop=True)
    wtd_l2 = da.sel(layer=WTD_LAYER2, drop=True)
    wtd = xr.where(np.isfinite(wtd_l1), wtd_l1, wtd_l2)

    if "model" in wtd.dims:
        wtd = wtd.squeeze("model", drop=True)

    lat_name = find_coord_name(ds, ["latitude", "lat", "y"])
    lon_name = find_coord_name(ds, ["longitude", "lon", "x"])

    if lat_name != "latitude" or lon_name != "longitude":
        wtd = wtd.rename({lat_name: "latitude", lon_name: "longitude"})
        ds = ds.rename({lat_name: "latitude", lon_name: "longitude"})

    if wtd["latitude"].values[0] < wtd["latitude"].values[-1]:
        wtd = wtd.sortby("latitude", ascending=False)

    if wtd["longitude"].values[0] > wtd["longitude"].values[-1]:
        wtd = wtd.sortby("longitude")

    return ds, wtd


# =============================================================================
# AGGREGATE FINE WTD TO COARSE GRID
# =============================================================================
@njit(cache=True)
def _agg_threshold_fracs(
    wtd_flat,
    lat_idx_flat,
    lon_idx_flat,
    n_lat,
    n_lon,
    thresholds,
    min_valid,
):
    n_t = len(thresholds)
    valid = np.zeros((n_lat, n_lon), dtype=np.int32)
    frac_cnt = np.zeros((n_t, n_lat, n_lon), dtype=np.int32)

    for k in range(len(wtd_flat)):
        v = wtd_flat[k]
        if np.isnan(v):
            continue

        i = lat_idx_flat[k]
        j = lon_idx_flat[k]

        valid[i, j] += 1

        for t in range(n_t):
            if v <= thresholds[t]:
                frac_cnt[t, i, j] += 1

    wtd_fracs = np.full((n_t, n_lat, n_lon), np.nan, dtype=np.float32)

    for i in range(n_lat):
        for j in range(n_lon):
            if valid[i, j] >= min_valid:
                for t in range(n_t):
                    wtd_fracs[t, i, j] = frac_cnt[t, i, j] / valid[i, j]

    return wtd_fracs


def prepare_index_maps(lat_f, lon_f, lat_c, lon_c, fine_shape):
    n_lat = len(lat_c)
    n_lon = len(lon_c)

    lat_c_asc = lat_c[::-1].copy()
    lat_f_asc = lat_f[::-1].copy()

    lat_idx = np.clip(
        np.searchsorted(lat_c_asc, lat_f_asc, side="right") - 1,
        0,
        n_lat - 1,
    ).astype(np.int32)

    lon_idx = np.clip(
        np.searchsorted(lon_c, lon_f, side="right") - 1,
        0,
        n_lon - 1,
    ).astype(np.int32)

    lat_idx_2d = np.broadcast_to(lat_idx[:, None], fine_shape).ravel().astype(np.int32)
    lon_idx_2d = np.broadcast_to(lon_idx[None, :], fine_shape).ravel().astype(np.int32)

    return lat_idx_2d, lon_idx_2d


def aggregate_wtd_month(wtd_np, lat_idx_2d, lon_idx_2d, n_lat, n_lon):
    wtd_asc = wtd_np[::-1, :].copy()

    wtd_fracs_asc = _agg_threshold_fracs(
        wtd_asc.ravel(),
        lat_idx_2d,
        lon_idx_2d,
        n_lat,
        n_lon,
        np.array(WTD_THRESHOLDS, dtype=np.float32),
        MIN_VALID_FINE,
    )

    return wtd_fracs_asc[:, ::-1, :]


def monthly_gdw_presence(wtd, sat):
    lat_c = sat["lat"].values.astype("float64")
    lon_c = sat["lon"].values.astype("float64")
    lat_f = wtd["latitude"].values.astype("float64")
    lon_f = wtd["longitude"].values.astype("float64")

    if not np.array_equal(wtd["time"].values, sat["time"].values):
        common_time = np.intersect1d(wtd["time"].values, sat["time"].values)
        if len(common_time) == 0:
            raise ValueError("No overlapping monthly time steps between WTD and SAT.")

        log(f"Aligning WTD and SAT to {len(common_time)} common monthly time steps")
        wtd = wtd.sel(time=common_time)
        sat = sat.sel(time=common_time)

    n_wtd = len(WTD_THRESHOLDS)
    n_sat = len(SAT_THRESHOLDS)
    n_lat = len(lat_c)
    n_lon = len(lon_c)

    gdw_presence = np.zeros((n_sat, n_wtd, n_lat, n_lon), dtype=bool)

    fine_shape = (len(lat_f), len(lon_f))
    lat_idx_2d, lon_idx_2d = prepare_index_maps(
        lat_f,
        lon_f,
        lat_c,
        lon_c,
        fine_shape,
    )

    times = wtd["time"].values

    for tt, t in enumerate(times, start=1):
        log(f"Monthly GDW detection {tt}/{len(times)}: {pd.Timestamp(t).strftime('%Y-%m')}")

        wtd_np = wtd.sel(time=t).compute().values.astype("float32")
        sat_np = sat.sel(time=t).compute().values.astype("float32")

        wtd_fracs = aggregate_wtd_month(
            wtd_np,
            lat_idx_2d,
            lon_idx_2d,
            n_lat,
            n_lon,
        )

        for s_idx, sat_threshold in enumerate(SAT_THRESHOLDS):
            sat_ok = np.isfinite(sat_np) & (sat_np > sat_threshold)

            for w_idx in range(n_wtd):
                wtd_ok = (
                    np.isfinite(wtd_fracs[w_idx])
                    & (wtd_fracs[w_idx] >= WTD_FRAC_THRESHOLD)
                )

                gdw_presence[s_idx, w_idx] |= wtd_ok & sat_ok

        del wtd_np, sat_np, wtd_fracs
        gc.collect()

    return gdw_presence, lat_c, lon_c


# =============================================================================
# RASTER HELPERS
# =============================================================================
def write_gdw_tif(gdw_mask, lat_c, lon_c, out_path):
    dlat = abs(lat_c[1] - lat_c[0])
    dlon = abs(lon_c[1] - lon_c[0])

    west = lon_c[0] - dlon / 2
    north = lat_c[0] + dlat / 2

    transform = rasterio.transform.from_origin(west, north, dlon, dlat)

    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "width": len(lon_c),
        "height": len(lat_c),
        "count": 1,
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": 255,
        "compress": "lzw",
    }

    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(gdw_mask.astype(np.uint8), 1)


def load_raster(path):
    with rasterio.open(path) as src:
        arr = src.read(1)
        profile = src.profile.copy()
        transform = src.transform
        crs = src.crs
        nodata = src.nodata

    return arr, profile, transform, crs, nodata


def align_to_grid(
    src_arr,
    src_transform,
    src_crs,
    src_nodata,
    dst_shape,
    dst_transform,
    dst_crs,
    dst_nodata,
    resampling=Resampling.nearest,
):
    out = np.full(dst_shape, dst_nodata, dtype=np.float32)

    reproject(
        source=src_arr.astype(np.float32),
        destination=out,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=float(src_nodata) if src_nodata is not None else np.nan,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        dst_nodata=float(dst_nodata),
        dst_width=dst_shape[1],
        dst_height=dst_shape[0],
        resampling=resampling,
    )

    return out


def get_bbox_from_mask(mask, pad=0):
    rows, cols = np.where(mask)

    r0 = max(0, rows.min() - pad)
    r1 = min(mask.shape[0], rows.max() + pad + 1)
    c0 = max(0, cols.min() - pad)
    c1 = min(mask.shape[1], cols.max() + pad + 1)

    return r0, r1, c0, c1


def crop_extent(transform, r0, r1, c0, c1):
    west, north = xy(transform, r0, c0, offset="ul")
    east, south = xy(transform, r1 - 1, c1 - 1, offset="lr")
    return [west, east, south, north]


def get_pixel_sizes_km(transform, extent):
    lon_res_deg = abs(transform.a)
    lat_res_deg = abs(transform.e)
    center_lat = 0.5 * (extent[2] + extent[3])

    row_km = lat_res_deg * 111.32
    col_km = lon_res_deg * 111.32 * max(np.cos(np.deg2rad(center_lat)), 1e-6)

    return row_km, col_km, center_lat


def get_row_area_km2(transform, nrows):
    lat_res_deg = abs(transform.e)
    lon_res_deg = abs(transform.a)
    row_areas = np.zeros(nrows, dtype=np.float64)

    for r in range(nrows):
        _, lat_c = xy(transform, r, 0, offset="center")
        h_km = lat_res_deg * 111.32
        w_km = lon_res_deg * 111.32 * max(np.cos(np.deg2rad(lat_c)), 1e-12)
        row_areas[r] = h_km * w_km

    return row_areas


def iter_tiles(nrows, ncols, tile_size):
    for rr0 in range(0, nrows, tile_size):
        rr1 = min(nrows, rr0 + tile_size)

        for cc0 in range(0, ncols, tile_size):
            cc1 = min(ncols, cc0 + tile_size)
            yield rr0, rr1, cc0, cc1


def pixel_areas_km2(lat, lon):
    dlat = abs(np.diff(lat).mean())
    dlon = abs(np.diff(lon).mean())
    radius_km = 6371.0

    area_1d = (
        (np.pi / 180) ** 2
        * radius_km**2
        * np.abs(np.cos(np.deg2rad(lat)))
        * dlat
        * dlon
    )

    return np.tile(area_1d[:, None], (1, len(lon))).astype("float32")


def area_from_mask_km2(mask, row_areas):
    return float(np.sum(mask.sum(axis=1) * row_areas))


# =============================================================================
# VALIDATION
# =============================================================================
def tolerance_evaluate(pred, ref, inter_transform, extent_crop, crop_r0, crop_c0):
    row_km, col_km, _ = get_pixel_sizes_km(inter_transform, extent_crop)

    pad_rows = int(np.ceil(TOLERANCE_KM / row_km)) + 2
    pad_cols = int(np.ceil(TOLERANCE_KM / col_km)) + 2

    n_ref = int(ref.sum())
    n_pred = int(pred.sum())

    if n_pred == 0 or n_ref == 0:
        return {
            "precision": np.nan,
            "recall": 0.0 if n_ref > 0 else np.nan,
            "f1": np.nan,
            "n_ref": n_ref,
            "n_pred": n_pred,
            "tp_pred": 0,
            "fp": n_pred,
            "fn": n_ref,
            "ref_hits": 0,
        }

    dist_to_ref = distance_transform_edt(~ref, sampling=(row_km, col_km))
    tp_pred = pred & (dist_to_ref <= TOLERANCE_KM)
    fp = pred & (dist_to_ref > TOLERANCE_KM)

    hit_ref = np.zeros(ref.shape, dtype=bool)
    nrows, ncols = pred.shape

    for tr0, tr1, tc0, tc1 in iter_tiles(nrows, ncols, TILE_SIZE):
        hr0 = max(0, tr0 - pad_rows)
        hr1 = min(nrows, tr1 + pad_rows)
        hc0 = max(0, tc0 - pad_cols)
        hc1 = min(ncols, tc1 + pad_cols)

        pred_h = pred[hr0:hr1, hc0:hc1]

        if not pred_h.any():
            continue

        ref_h = ref[hr0:hr1, hc0:hc1]

        halo_extent = crop_extent(
            inter_transform,
            crop_r0 + hr0,
            crop_r0 + hr1,
            crop_c0 + hc0,
            crop_c0 + hc1,
        )

        r_km, c_km, _ = get_pixel_sizes_km(inter_transform, halo_extent)
        d2pred = distance_transform_edt(~pred_h, sampling=(r_km, c_km))

        cr0 = tr0 - hr0
        cr1 = cr0 + (tr1 - tr0)
        cc0 = tc0 - hc0
        cc1 = cc0 + (tc1 - tc0)

        hit_ref[tr0:tr1, tc0:tc1] |= (
            ref_h[cr0:cr1, cc0:cc1]
            & (d2pred[cr0:cr1, cc0:cc1] <= TOLERANCE_KM)
        )

        del pred_h, ref_h, d2pred

    n_tp = int(tp_pred.sum())
    n_fp = int(fp.sum())
    n_hits = int(hit_ref.sum())
    n_fn = n_ref - n_hits

    precision = n_tp / n_pred if n_pred > 0 else np.nan
    recall = n_hits / n_ref if n_ref > 0 else np.nan

    f1 = (
        2 * precision * recall / (precision + recall)
        if np.isfinite(precision)
        and np.isfinite(recall)
        and (precision + recall) > 0
        else np.nan
    )

    del dist_to_ref, tp_pred, fp, hit_ref

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "n_ref": n_ref,
        "n_pred": n_pred,
        "tp_pred": n_tp,
        "fp": n_fp,
        "fn": n_fn,
        "ref_hits": n_hits,
    }


# =============================================================================
# MAIN LOOP
# =============================================================================
def run():
    sat_ds, sat = open_sat_dataset()
    wtd_ds, wtd = open_wtd_dataset()

    gdw_presence, lat_c, lon_c = monthly_gdw_presence(wtd, sat)

    sat_ds.close()
    wtd_ds.close()

    del sat, wtd
    gc.collect()

    parea = pixel_areas_km2(lat_c, lon_c)

    log("Loading validation reference rasters ...")
    inter, _, inter_tf, inter_crs, _ = load_raster(INTERSECTION_TIF)
    dryland, _, dry_tf, dry_crs, dry_nd = load_raster(DRYLAND_MASK_TIF)
    glwd, _, glwd_tf, glwd_crs, glwd_nd = load_raster(GLWD_CLASS_TIF)

    log("Aligning dryland mask ...")
    dry_aln = align_to_grid(
        dryland.astype(np.float32),
        dry_tf,
        dry_crs,
        float(dry_nd) if dry_nd is not None else np.nan,
        inter.shape,
        inter_tf,
        inter_crs,
        np.nan,
    )

    dry_int = np.where(np.isfinite(dry_aln), dry_aln, -9999).astype(np.int16)
    dry_mask = np.isfinite(dry_aln) & np.isin(dry_int, list(DRYLAND_CLASSES))

    del dryland, dry_aln, dry_int
    gc.collect()

    log("Aligning GLWD ...")
    glwd_aln = align_to_grid(
        glwd.astype(np.float32),
        glwd_tf,
        glwd_crs,
        float(glwd_nd) if glwd_nd is not None else 0.0,
        inter.shape,
        inter_tf,
        inter_crs,
        0.0,
    ).astype(np.int16)

    del glwd
    gc.collect()

    glwd_wetland_full = (glwd_aln != 0) & dry_mask
    ref_full = (inter == INTERSECTION_POSITIVE) & dry_mask

    r0, r1, c0, c1 = get_bbox_from_mask(ref_full, pad=PAD)
    ext_crop = crop_extent(inter_tf, r0, r1, c0, c1)
    crop_tf = window_transform(Window(c0, r0, c1 - c0, r1 - r0), inter_tf)
    row_areas = get_row_area_km2(crop_tf, r1 - r0)

    ref_crop = ref_full[r0:r1, c0:c1]
    dry_crop = dry_mask[r0:r1, c0:c1]
    glwd_crop = glwd_wetland_full[r0:r1, c0:c1]

    reference_area_km2 = area_from_mask_km2(ref_crop, row_areas)
    reference_area_1000km2 = reference_area_km2 / 1e3
    reference_pixels = int(ref_crop.sum())

    glwd_reference_area_km2 = area_from_mask_km2(glwd_crop, row_areas)
    glwd_reference_area_1000km2 = glwd_reference_area_km2 / 1e3
    glwd_reference_pixels = int(glwd_crop.sum())

    dryland_validation_area_km2 = area_from_mask_km2(dry_crop, row_areas)
    dryland_validation_area_1000km2 = dryland_validation_area_km2 / 1e3
    dryland_validation_pixels = int(dry_crop.sum())

    log(f"Rhodes ∩ GLWD reference area = {reference_area_1000km2:.1f} thousand km²")
    log(f"GLWD dryland reference area = {glwd_reference_area_1000km2:.1f} thousand km²")

    records = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_tif = Path(tmpdir) / "gdw_threshold.tif"

        for s_idx, sat_threshold in enumerate(SAT_THRESHOLDS):
            log(f"\nSAT threshold = {sat_threshold}")

            for w_idx, wtd_threshold in enumerate(WTD_THRESHOLDS):
                log(f"  WTD threshold = {wtd_threshold} m")

                gdw_mask = gdw_presence[s_idx, w_idx]

                gdw_area_global_km2 = float(np.nansum(parea[gdw_mask]))
                gdw_area_global_1000km2 = gdw_area_global_km2 / 1e3

                write_gdw_tif(gdw_mask, lat_c, lon_c, tmp_tif)

                with rasterio.open(tmp_tif) as src:
                    gdw_aln = align_to_grid(
                        src.read(1).astype(np.float32),
                        src.transform,
                        src.crs,
                        255.0,
                        inter.shape,
                        inter_tf,
                        inter_crs,
                        0.0,
                        resampling=Resampling.nearest,
                    )

                pred_crop = (gdw_aln[r0:r1, c0:c1] == 1) & dry_crop

                gdw_area_drylands_km2 = area_from_mask_km2(pred_crop, row_areas)
                gdw_area_drylands_1000km2 = gdw_area_drylands_km2 / 1e3

                val = tolerance_evaluate(
                    pred=pred_crop,
                    ref=ref_crop,
                    inter_transform=inter_tf,
                    extent_crop=ext_crop,
                    crop_r0=r0,
                    crop_c0=c0,
                )

                records.append(
                    {
                        "sat_threshold": sat_threshold,
                        "wtd_threshold_m": wtd_threshold,
                        "wtd_frac_threshold": WTD_FRAC_THRESHOLD,
                        "temporal_aggregation": "monthly_gdw_any_2015_2019",
                        "forcing": "gswp3-w5e5_historical",

                        "gdw_area_global_km2": gdw_area_global_km2,
                        "gdw_area_global_1000km2": gdw_area_global_1000km2,
                        "gdw_area_drylands_km2": gdw_area_drylands_km2,
                        "gdw_area_drylands_1000km2": gdw_area_drylands_1000km2,

                        "reference_area_km2": reference_area_km2,
                        "reference_area_1000km2": reference_area_1000km2,
                        "reference_pixels": reference_pixels,

                        "glwd_reference_area_km2": glwd_reference_area_km2,
                        "glwd_reference_area_1000km2": glwd_reference_area_1000km2,
                        "glwd_reference_pixels": glwd_reference_pixels,

                        "dryland_validation_area_km2": dryland_validation_area_km2,
                        "dryland_validation_area_1000km2": dryland_validation_area_1000km2,
                        "dryland_validation_pixels": dryland_validation_pixels,

                        "precision": round(float(val["precision"]), 4)
                        if np.isfinite(val["precision"])
                        else np.nan,
                        "recall": round(float(val["recall"]), 4)
                        if np.isfinite(val["recall"])
                        else np.nan,
                        "f1": round(float(val["f1"]), 4)
                        if np.isfinite(val["f1"])
                        else np.nan,

                        "n_ref": val["n_ref"],
                        "n_pred": val["n_pred"],
                        "tp_pred": val["tp_pred"],
                        "fp": val["fp"],
                        "fn": val["fn"],
                        "ref_hits": val["ref_hits"],
                    }
                )

                log(
                    f"    global area={gdw_area_global_1000km2:.1f} thousand km², "
                    f"dryland area={gdw_area_drylands_1000km2:.1f} thousand km², "
                    f"precision={val['precision']:.3f}, "
                    f"recall={val['recall']:.3f}, "
                    f"f1={val['f1']:.3f}"
                )

                del gdw_aln, pred_crop
                gc.collect()

    df = pd.DataFrame(records)

    out_csv = OUTDIR / "wtd_sat_sensitivity_metrics_monthly_gswp3w5e5_2015_2019.csv"
    df.to_csv(out_csv, index=False)

    log(f"Saved: {out_csv}")
    print(df.to_string(index=False))

    return df, glwd_reference_area_km2, reference_area_km2


# =============================================================================
# FIGURES
# =============================================================================
def _pivot(df, value_col):
    return df.pivot(
        index="sat_threshold",
        columns="wtd_threshold_m",
        values=value_col,
    ).sort_index(ascending=False)


def _annotate_heatmap(ax, data, fmt):
    values = data.values

    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            v = values[i, j]
            if np.isfinite(v):
                ax.text(j, i, format(v, fmt), ha="center", va="center", fontsize=8)


def plot_heatmaps(df):
    metrics = [
        ("precision", "Precision", ".2f"),
        ("recall", "Recall", ".2f"),
        ("f1", "F1", ".2f"),
        ("gdw_area_global_1000km2", "Global GDW area\n(thousand km²)", ".0f"),
        ("gdw_area_drylands_1000km2", "Dryland GDW area\n(thousand km²)", ".0f"),
    ]

    fig, axes = plt.subplots(1, len(metrics), figsize=(21, 4.8), dpi=300)

    for ax, (col, title, fmt) in zip(axes, metrics):
        data = _pivot(df, col)

        im = ax.imshow(data.values, aspect="auto")
        _annotate_heatmap(ax, data, fmt)

        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xlabel("WTD threshold (m)", fontsize=10)
        ax.set_ylabel("satAreaFrac threshold", fontsize=10)

        ax.set_xticks(np.arange(len(data.columns)))
        ax.set_xticklabels([f"{v:g}" for v in data.columns], fontsize=9)

        ax.set_yticks(np.arange(len(data.index)))
        ax.set_yticklabels([f"{v:g}" for v in data.index], fontsize=9)

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(labelsize=8)

    fig.suptitle(
        "GDW sensitivity to WTD and saturation thresholds, monthly GDW presence 2015-2019",
        fontsize=13,
        fontweight="bold",
        y=1.03,
    )

    fig.tight_layout()

    out_png = OUTDIR / "wtd_sat_sensitivity_heatmaps_monthly_gswp3w5e5_2015_2019.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)

    log(f"Saved figure: {out_png}")


def plot_area_bars(df, glwd_reference_area_km2, reference_area_km2):
    sat_thresholds = sorted(df["sat_threshold"].unique())
    wtd_thresholds = sorted(df["wtd_threshold_m"].unique())

    fig, axes = plt.subplots(
        1,
        len(sat_thresholds),
        figsize=(6.5 * len(sat_thresholds), 5.3),
        dpi=300,
        sharey=True,
    )

    if len(sat_thresholds) == 1:
        axes = [axes]

    for ax, sat_threshold in zip(axes, sat_thresholds):
        sub = df[df["sat_threshold"] == sat_threshold].sort_values("wtd_threshold_m")

        x = np.arange(len(wtd_thresholds))
        bw = 0.25

        ax.bar(
            x - bw,
            [glwd_reference_area_km2 / 1e3] * len(wtd_thresholds),
            width=bw * 0.9,
            label="Total GLWDv2, drylands",
        )

        ax.bar(
            x,
            [reference_area_km2 / 1e3] * len(wtd_thresholds),
            width=bw * 0.9,
            label="Rhodes ∩ GLWD reference",
        )

        ax.bar(
            x + bw,
            sub["gdw_area_drylands_1000km2"].values,
            width=bw * 0.9,
            label="Simulated GDW, drylands",
        )

        ax.set_title(f"satAreaFrac > {sat_threshold:g}", fontsize=11, fontweight="bold")
        ax.set_xlabel("WTD threshold (m)", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{v:g}" for v in wtd_thresholds], fontsize=9)
        ax.grid(axis="y", alpha=0.25)

        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)

    axes[0].set_ylabel("Wetland area (thousand km²)", fontsize=11)
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")

    fig.suptitle(
        "Dryland wetland area comparison across WTD and saturation thresholds, monthly GDW presence 2015-2019",
        fontsize=13,
        fontweight="bold",
        y=1.03,
    )

    fig.tight_layout()

    out_png = OUTDIR / "wtd_sat_sensitivity_area_bars_monthly_gswp3w5e5_2015_2019.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)

    log(f"Saved figure: {out_png}")


def plot_results(df, glwd_reference_area_km2, reference_area_km2):
    plot_heatmaps(df)
    plot_area_bars(df, glwd_reference_area_km2, reference_area_km2)


if __name__ == "__main__":
    df, glwd_reference_area, reference_area = run()
    plot_results(df, glwd_reference_area, reference_area)
    log("Done.")