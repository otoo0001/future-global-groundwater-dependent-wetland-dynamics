# """
# pipeline.py  --  orchestration for v3 multi-variant runs.

# GCM jobs only (RUN_GCMS=1).
# Each job writes one NC with 8 variables + one parquet with 4 area columns.

# Variants computed in a single pass:
#   full        dynamic WTD + dynamic LU
#   nonlu       dynamic WTD + no LU
#   freeze_lu   dynamic WTD + frozen historical LU
#   freeze_wtd  frozen WTD climatology + dynamic LU

# Output folder: WetGDEs_fgdw_v3
# """
# from __future__ import annotations

# import logging
# import time
# from pathlib import Path
# from typing import Dict, List, Optional

# import numpy as np
# import pandas as pd
# import xarray as xr

# from .area import (
#     aggregate_tile_fgdw,
#     build_biome_realm_raster,
#     build_pixel_area,
#     build_realm_raster,
#     load_pixel_area,
# )
# from .config import Config, ENSEMBLE_MEMBER
# from .io_utils import (
#     align_times,
#     build_regrid_indices,
#     build_wtd_climatology,
#     open_sat,
#     open_wtd,
#     read_tile,
# )
# from .lu_utils import PcrLazy
# from .qa_utils import build_open_water_mask, build_qa_mask
# from .writers import write_area_parquet_v3, write_sensitivity_parquet, AREA_COLS

# logger = logging.getLogger(__name__)

# FGDW_FILL = np.float32(-9999.0)

# # NC variables that map to parquet area columns
# NC_TO_AREA = {
#     "area_gdw_km2":            "area_gdw_km2",
#     "area_gdw_nonlu_km2":      "area_gdw_nonlu_km2",
#     "area_gdw_freeze_lu_km2":  "area_gdw_freeze_lu_km2",
#     "area_gdw_freeze_wtd_km2": "area_gdw_freeze_wtd_km2",
# }


# # ── helpers ───────────────────────────────────────────────────────────────────

# def _standard_jobs(members, cfg):
#     jobs = [(m, s) for m in members for s in cfg.scenarios]
#     if cfg.only_member:   jobs = [(m,s) for m,s in jobs if m == cfg.only_member]
#     if cfg.only_scenario: jobs = [(m,s) for m,s in jobs if s == cfg.only_scenario]
#     return jobs


# def _remap_open_water(open_water_qa, qa_lat, qa_lon, sat_lat, sat_lon):
#     r_lat, r_lon = build_regrid_indices(qa_lat, qa_lon, sat_lat, sat_lon)
#     return open_water_qa[np.ix_(r_lat, r_lon)]


# # ── mask writing ──────────────────────────────────────────────────────────────

# def _write_fgdw_mask_v3(
#     member: str, scenario: str, cfg: Config,
#     nc_out: str,
#     lu,               # PcrLazy dynamic
#     lu_frozen,        # PcrLazy frozen historical LU
#     wtd_clim,         # (12, ny, nx) or None
#     open_water_sat,
#     pixel_area_sat,
# ) -> None:
#     """Write all 8-variable NC via wetgde_mask.pipeline."""
#     from wetgde_mask.pipeline import run_pipeline as mask_run
#     from wetgde_mask.writer  import build_encoding, build_global_attrs, build_var_attrs

#     sat_path = (cfg.sat_path(scenario)
#                 if member == ENSEMBLE_MEMBER
#                 else cfg.gcm_sat_path(member, scenario))
#     sat = open_sat(sat_path)
#     wtd = open_wtd(cfg.wtd_path(member, scenario))

#     enc         = build_encoding(sat)
#     global_attr = build_global_attrs(scenario)
#     var_attr    = build_var_attrs(scenario)

#     logger.info("Writing v3 NC: %s", nc_out)
#     mask_run(
#         sat=sat, wtd=wtd,
#         lu=lu,
#         lu_frozen=lu_frozen,
#         wtd_clim=wtd_clim,
#         open_water_2d=open_water_sat,
#         pixel_area_2d=pixel_area_sat,
#         scen=scenario,
#         out_path=nc_out,
#         enc=enc,
#         global_attrs=global_attr,
#         var_attrs=var_attr,
#     )
#     logger.info("v3 NC written: %s", nc_out)


# # ── area aggregation from v3 NC ───────────────────────────────────────────────

# def _area_loop_v3(
#     member, scenario, cfg, nc_path,
#     codes_arr, pixel_area, qa_mask,
#     code_to_label, n_codes,
#     group_col,
#     qa_lat=None, qa_lon=None,
# ):
#     """
#     Read all 4 area variables from v3 NC tile-by-tile.
#     Writes single parquet with 4 area columns.
#     """
#     ds     = xr.open_dataset(nc_path, decode_times=True, engine="netcdf4",
#                               mask_and_scale=True)
#     times  = pd.DatetimeIndex(ds["time"].values)
#     n_times = len(times)
#     ny = ds.sizes["lat"]
#     nx = ds.sizes["lon"]

#     # remap grids
#     if qa_lat is not None and qa_lon is not None:
#         nc_lat = ds["lat"].values
#         nc_lon = ds["lon"].values
#         r_lat, r_lon = build_regrid_indices(qa_lat, qa_lon, nc_lat, nc_lon)
#         codes_arr  = codes_arr[np.ix_(r_lat, r_lon)].astype(np.int32)
#         pixel_area = pixel_area[np.ix_(r_lat, r_lon)].astype(np.float32)
#         qa_mask    = qa_mask[np.ix_(r_lat, r_lon)]
#         logger.info("_area_loop_v3: remapped qa->nc grid (%d,%d)", nc_lat.size, nc_lon.size)

#     pq_out      = cfg.parquet_out_path(member, scenario)
#     accumulated = None

#     for t0i in range(0, n_times, cfg.time_batch):
#         t1i         = min(t0i + cfg.time_batch, n_times)
#         times_batch = times[t0i:t1i]
#         B           = len(times_batch)

#         # sums dict: area_col -> (B, n_codes+1)
#         sums = {col: np.zeros((B, n_codes + 1), dtype=np.float64) for col in AREA_COLS}

#         for y0 in range(0, ny, cfg.tile_y):
#             y1 = min(y0 + cfg.tile_y, ny)
#             for x0 in range(0, nx, cfg.tile_x):
#                 x1 = min(x0 + cfg.tile_x, nx)

#                 codes_tile = codes_arr[y0:y1, x0:x1]
#                 if codes_tile.max() == 0:
#                     continue

#                 area_tile = pixel_area[y0:y1, x0:x1]
#                 qa_tile   = qa_mask[y0:y1, x0:x1]

#                 for nc_var, area_col in NC_TO_AREA.items():
#                     if nc_var not in ds:
#                         continue
#                     batch = (ds[nc_var]
#                              .isel(time=slice(t0i, t1i),
#                                    lat=slice(y0, y1),
#                                    lon=slice(x0, x1))
#                              .values.astype(np.float32))  # (B, ty, tx)

#                     for k in range(B):
#                         aggregate_tile_fgdw(
#                             batch[k], codes_tile, area_tile, qa_tile,
#                             n_codes, sums[area_col][k],
#                         )

#         accumulated = write_area_parquet_v3(
#             sums, times_batch, code_to_label, n_codes,
#             member, scenario, group_col, pq_out, cfg.parquet_codec, accumulated,
#         )
#         logger.info("area v3 batch %d/%d  member=%s scenario=%s",
#                     t1i, n_times, member, scenario)

#     ds.close()


# # ── GCM job ───────────────────────────────────────────────────────────────────

# def _run_gcm_job_v3(
#     member, scenario, cfg,
#     codes_arr, pixel_area, qa_mask,
#     code_to_label, n_codes,
#     open_water_sat,
#     sat_lat_ref, sat_lon_ref,
#     qa_lat=None, qa_lon=None,
# ):
#     t0 = time.time()
#     logger.info("===START GCM v3=== member=%s scenario=%s", member, scenario)

#     pq_out = cfg.parquet_out_path(member, scenario)
#     if Path(pq_out).exists() and cfg.skip_existing:
#         logger.info("Parquet exists, skipping: %s", pq_out)
#         return

#     # load WTD climatology from cache or build from GCM historical zarr
#     import os as _os
#     _cache_dir = _os.environ.get("WTD_CLIM_CACHE_DIR", "")
#     _cache_path = Path(_cache_dir) / f"wtd_clim_{member}.npy" if _cache_dir else None
#     if _cache_path and _cache_path.exists():
#         wtd_clim = np.load(str(_cache_path))
#         logger.info("Loaded cached WTD clim: %s  shape=%s", _cache_path, wtd_clim.shape)
#     else:
#         logger.info("Building WTD climatology for %s: window=%s", member, cfg.wtd_clim_window)
#         wtd_clim = build_wtd_climatology(
#             cfg.wtd_clim_zarr_path(member), cfg.wtd_clim_window,
#             target_lat=sat_lat_ref, target_lon=sat_lon_ref)
#         logger.info("WTD climatology built: shape=%s", wtd_clim.shape)
#         if _cache_path:
#             np.save(str(_cache_path), wtd_clim)
#             logger.info("Cached WTD clim: %s", _cache_path)

#     sat_ref = open_sat(cfg.gcm_sat_path(member, scenario))
#     sat_lat = sat_ref["lat"].values
#     sat_lon = sat_ref["lon"].values

#     # dynamic LU
#     lu = (PcrLazy(scenario, cfg.pcr_files[scenario], sat_lat, sat_lon, cfg.lu_vars)
#           if cfg.apply_lu_mask else None)

#     # frozen historical LU
#     if cfg.apply_lu_mask:
#         class _FrozenLU:
#             def __init__(self, b): self._b = b
#             def get_dynamic_tile(self, yr, y0, y1, x0, x1):
#                 return self._b.get_frozen_tile(
#                     y0, y1, x0, x1,
#                     cfg.lu_freeze_mode,
#                     cfg.lu_freeze_start, cfg.lu_freeze_end, cfg.fix_lu_year)
#         lu_frozen = _FrozenLU(lu)
#     else:
#         lu_frozen = None

#     # remap pixel_area to sat grid
#     if qa_lat is not None and qa_lon is not None:
#         r_lat, r_lon   = build_regrid_indices(qa_lat, qa_lon, sat_lat, sat_lon)
#         pixel_area_sat = pixel_area[np.ix_(r_lat, r_lon)].astype(np.float32)
#     else:
#         pixel_area_sat = pixel_area.astype(np.float32)

#     nc_out = cfg.nc_out_path(member, scenario)

#     if Path(nc_out).exists() and cfg.skip_existing:
#         logger.info("NC exists, skipping mask: %s", nc_out)
#     else:
#         _write_fgdw_mask_v3(
#             member, scenario, cfg, nc_out,
#             lu, lu_frozen, wtd_clim,
#             open_water_sat, pixel_area_sat,
#         )

#     _area_loop_v3(
#         member, scenario, cfg, nc_out,
#         codes_arr, pixel_area, qa_mask,
#         code_to_label, n_codes,
#         group_col="BIOME_ID_REALM",
#         qa_lat=qa_lat, qa_lon=qa_lon,
#     )

#     logger.info("===DONE GCM v3=== member=%s scenario=%s  wall=%.1f s",
#                 member, scenario, time.time()-t0)


# # ── run_all ───────────────────────────────────────────────────────────────────

# def run_all(cfg: Config) -> None:
#     import logging as _logging

#     cfg.validate()
#     for d in (cfg.out_nc_dir, cfg.out_parquet_dir, cfg.log_dir):
#         Path(d).mkdir(parents=True, exist_ok=True)

#     fmt  = _logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
#     root = _logging.getLogger()
#     root.setLevel(_logging.INFO)
#     if not any(isinstance(h, _logging.StreamHandler) for h in root.handlers):
#         sh = _logging.StreamHandler(); sh.setFormatter(fmt); root.addHandler(sh)
#     fh = _logging.FileHandler(f"{cfg.log_dir}/wetgde_pipeline_v3.log")
#     fh.setFormatter(fmt); root.addHandler(fh)

#     logger.info("v3 pipeline: RUN_GCMS=%s  APPLY_LU_MASK=%s",
#                 cfg.run_gcms, cfg.apply_lu_mask)

#     # ── static grids ─────────────────────────────────────────────────────────
#     logger.info("Loading QA mask")
#     qa_lat, qa_lon, qa_mask = build_qa_mask(cfg.qa_dir)

#     logger.info("Loading open-water mask")
#     open_water_qa = build_open_water_mask(cfg.open_water_mask_tif, qa_lat, qa_lon)

#     pixel_area = load_pixel_area(
#         cfg.cell_area_path, cfg.cell_area_var, cfg.cell_area_units, qa_lat, qa_lon,
#     )

#     _ref_sc     = cfg.only_scenario or ("historical" if "historical" in cfg.scenarios else cfg.scenarios[0])
#     _ref_member = cfg.only_member or cfg.gcms[0]
#     _sat_ref    = open_sat(cfg.gcm_sat_path(_ref_member, _ref_sc))
#     sat_lat_ref = _sat_ref["lat"].values
#     sat_lon_ref = _sat_ref["lon"].values

#     logger.info("Remapping open-water mask to sat grid (%d x %d)",
#                 sat_lat_ref.size, sat_lon_ref.size)
#     open_water_sat = _remap_open_water(open_water_qa, qa_lat, qa_lon,
#                                        sat_lat_ref, sat_lon_ref)

#     # ── realm raster ─────────────────────────────────────────────────────────
#     logger.info("Building BIOME_ID_REALM raster")
#     gcm_codes, gcm_labels, _ = build_biome_realm_raster(
#         cfg.biome_shp, qa_lat, qa_lon, qa_mask, open_water_qa)
#     gcm_n = len(gcm_labels)
#     logger.info("BIOME_ID_REALM: %d codes", gcm_n)

#     # ── GCM jobs ─────────────────────────────────────────────────────────────
#     if not cfg.run_gcms:
#         raise ValueError("v3 pipeline: set RUN_GCMS=1")

#     jobs = _standard_jobs(cfg.gcms, cfg)
#     logger.info("GCM v3 jobs: %d", len(jobs))

#     for member, scenario in jobs:
#         try:
#             _run_gcm_job_v3(
#                 member, scenario, cfg,
#                 gcm_codes, pixel_area, qa_mask,
#                 gcm_labels, gcm_n,
#                 open_water_sat,
#                 sat_lat_ref, sat_lon_ref,
#                 qa_lat=qa_lat, qa_lon=qa_lon,
#             )
#         except Exception as exc:
#             logger.error("FAILED gcm member=%s scenario=%s: %s",
#                          member, scenario, exc, exc_info=True)



"""
pipeline.py -- orchestration for v3 multi-variant runs.

GCM jobs only (RUN_GCMS=1).
Each job writes one NetCDF with 8 variables and one parquet with 4 area columns.

Variants computed in a single pass
----------------------------------
full
    Dynamic WTD + dynamic LU.
nonlu
    Dynamic WTD + no LU.
freeze_lu
    Dynamic WTD + frozen historical LU.
freeze_wtd
    Frozen WTD climatology + dynamic LU.

Important area-aggregation rule
-------------------------------
The NetCDF variables named ``area_gdw_*_km2`` already contain pixel-level
areas in km². They must be summed directly by biome-realm. They must not be
passed to ``aggregate_tile_fgdw()``, because that function multiplies its
input by pixel area and would therefore produce km⁴.

Output folder: WetGDEs_fgdw_v3
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .area import (
    build_biome_realm_raster,
    load_pixel_area,
)
from .config import Config, ENSEMBLE_MEMBER
from .io_utils import (
    build_regrid_indices,
    build_wtd_climatology,
    open_sat,
    open_wtd,
)
from .lu_utils import PcrLazy
from .qa_utils import build_open_water_mask, build_qa_mask
from .writers import write_area_parquet_v3, AREA_COLS

logger = logging.getLogger(__name__)

FGDW_FILL = np.float32(-9999.0)

# NetCDF variables that map directly to parquet area columns.
# Each variable already has units of km² per pixel.
NC_TO_AREA = {
    "area_gdw_km2": "area_gdw_km2",
    "area_gdw_nonlu_km2": "area_gdw_nonlu_km2",
    "area_gdw_freeze_lu_km2": "area_gdw_freeze_lu_km2",
    "area_gdw_freeze_wtd_km2": "area_gdw_freeze_wtd_km2",
}


# =============================================================================
# HELPERS
# =============================================================================

def _standard_jobs(members, cfg):
    """Build the filtered member-scenario job list."""
    jobs = [(member, scenario) for member in members for scenario in cfg.scenarios]

    if cfg.only_member:
        jobs = [
            (member, scenario)
            for member, scenario in jobs
            if member == cfg.only_member
        ]

    if cfg.only_scenario:
        jobs = [
            (member, scenario)
            for member, scenario in jobs
            if scenario == cfg.only_scenario
        ]

    return jobs


def _remap_open_water(
    open_water_qa,
    qa_lat,
    qa_lon,
    sat_lat,
    sat_lon,
):
    """Nearest-neighbour remap of the categorical open-water mask."""
    r_lat, r_lon = build_regrid_indices(
        qa_lat,
        qa_lon,
        sat_lat,
        sat_lon,
    )
    return open_water_qa[np.ix_(r_lat, r_lon)]


def _sum_area_values_by_code(
    area_values_2d: np.ndarray,
    codes_tile: np.ndarray,
    qa_tile: np.ndarray,
    n_codes: int,
    out_sums: np.ndarray,
) -> None:
    """
    Sum an already-area-valued raster directly by zone code.

    Parameters
    ----------
    area_values_2d
        Pixel-level area values in km².
    codes_tile
        Integer biome-realm code per pixel.
    qa_tile
        Boolean QA mask; True means valid.
    n_codes
        Highest valid zone code.
    out_sums
        Float64 array with shape ``(n_codes + 1,)`` modified in place.

    Notes
    -----
    No multiplication by pixel area is done here. ``area_values_2d`` already
    contains km² per pixel.
    """
    values = np.asarray(area_values_2d, dtype=np.float64).ravel()
    codes = np.asarray(codes_tile, dtype=np.int32).ravel()
    qa = np.asarray(qa_tile, dtype=bool).ravel()

    if values.size != codes.size or values.size != qa.size:
        raise ValueError(
            "Area values, code raster, and QA mask must contain the same "
            "number of pixels."
        )

    if np.any(codes < 0):
        raise ValueError("codes_tile contains negative zone codes.")
    if np.any(codes > n_codes):
        raise ValueError(
            f"codes_tile contains a code greater than n_codes={n_codes}."
        )

    valid = (
        np.isfinite(values)
        & (values > 0.0)
        & (codes > 0)
        & qa
    )

    if not np.any(valid):
        return

    out_sums += np.bincount(
        codes[valid],
        weights=values[valid],
        minlength=n_codes + 1,
    )


# =============================================================================
# MASK WRITING
# =============================================================================

def _write_fgdw_mask_v3(
    member: str,
    scenario: str,
    cfg: Config,
    nc_out: str,
    lu,
    lu_frozen,
    wtd_clim,
    open_water_sat,
    pixel_area_sat,
) -> None:
    """Write all eight v3 NetCDF variables via wetgde_mask.pipeline."""
    from wetgde_mask.pipeline import run_pipeline as mask_run
    from wetgde_mask.writer import (
        build_encoding,
        build_global_attrs,
        build_var_attrs,
    )

    sat_path = (
        cfg.sat_path(scenario)
        if member == ENSEMBLE_MEMBER
        else cfg.gcm_sat_path(member, scenario)
    )

    sat = open_sat(sat_path)
    wtd = open_wtd(cfg.wtd_path(member, scenario))

    encoding = build_encoding(sat)
    global_attrs = build_global_attrs(scenario)
    variable_attrs = build_var_attrs(scenario)

    logger.info("Writing v3 NC: %s", nc_out)

    mask_run(
        sat=sat,
        wtd=wtd,
        lu=lu,
        lu_frozen=lu_frozen,
        wtd_clim=wtd_clim,
        open_water_2d=open_water_sat,
        pixel_area_2d=pixel_area_sat,
        scen=scenario,
        out_path=nc_out,
        enc=encoding,
        global_attrs=global_attrs,
        var_attrs=variable_attrs,
    )

    logger.info("v3 NC written: %s", nc_out)


# =============================================================================
# AREA AGGREGATION FROM V3 NETCDF
# =============================================================================

def _area_loop_v3(
    member,
    scenario,
    cfg,
    nc_path,
    codes_arr,
    pixel_area,
    qa_mask,
    code_to_label,
    n_codes,
    group_col,
    qa_lat=None,
    qa_lon=None,
):
    """
    Read all four area variables from the v3 NetCDF tile by tile.

    The ``area_gdw_*_km2`` variables already contain km² per pixel, so they
    are summed directly by biome-realm and written to one parquet file.
    """
    del pixel_area  # intentionally unused in direct area summation

    ds = xr.open_dataset(
        nc_path,
        decode_times=True,
        engine="netcdf4",
        mask_and_scale=True,
    )

    try:
        times = pd.DatetimeIndex(ds["time"].values)
        n_times = len(times)
        ny = ds.sizes["lat"]
        nx = ds.sizes["lon"]

        # Remap categorical masks/codes from QA grid to NetCDF grid.
        if qa_lat is not None and qa_lon is not None:
            nc_lat = ds["lat"].values
            nc_lon = ds["lon"].values

            r_lat, r_lon = build_regrid_indices(
                qa_lat,
                qa_lon,
                nc_lat,
                nc_lon,
            )

            codes_arr = codes_arr[np.ix_(r_lat, r_lon)].astype(np.int32)
            qa_mask = qa_mask[np.ix_(r_lat, r_lon)].astype(bool)

            logger.info(
                "_area_loop_v3: remapped QA/code grids to NC grid (%d, %d)",
                nc_lat.size,
                nc_lon.size,
            )

        expected_shape = (ny, nx)

        if codes_arr.shape != expected_shape:
            raise ValueError(
                f"codes_arr shape {codes_arr.shape} does not match "
                f"NetCDF grid {expected_shape}."
            )

        if qa_mask.shape != expected_shape:
            raise ValueError(
                f"qa_mask shape {qa_mask.shape} does not match "
                f"NetCDF grid {expected_shape}."
            )

        missing_vars = [
            nc_var
            for nc_var in NC_TO_AREA
            if nc_var not in ds
        ]
        if missing_vars:
            logger.warning(
                "NetCDF is missing expected area variables: %s",
                missing_vars,
            )

        pq_out = cfg.parquet_out_path(member, scenario)
        accumulated = None

        for t0i in range(0, n_times, cfg.time_batch):
            t1i = min(t0i + cfg.time_batch, n_times)
            times_batch = times[t0i:t1i]
            batch_size = len(times_batch)

            sums = {
                col: np.zeros(
                    (batch_size, n_codes + 1),
                    dtype=np.float64,
                )
                for col in AREA_COLS
            }

            for y0 in range(0, ny, cfg.tile_y):
                y1 = min(y0 + cfg.tile_y, ny)

                for x0 in range(0, nx, cfg.tile_x):
                    x1 = min(x0 + cfg.tile_x, nx)

                    codes_tile = codes_arr[y0:y1, x0:x1]

                    if not np.any(codes_tile > 0):
                        continue

                    qa_tile = qa_mask[y0:y1, x0:x1]

                    if not np.any(qa_tile):
                        continue

                    for nc_var, area_col in NC_TO_AREA.items():
                        if nc_var not in ds:
                            continue

                        batch = (
                            ds[nc_var]
                            .isel(
                                time=slice(t0i, t1i),
                                lat=slice(y0, y1),
                                lon=slice(x0, x1),
                            )
                            .values.astype(np.float32)
                        )

                        for k in range(batch_size):
                            _sum_area_values_by_code(
                                area_values_2d=batch[k],
                                codes_tile=codes_tile,
                                qa_tile=qa_tile,
                                n_codes=n_codes,
                                out_sums=sums[area_col][k],
                            )

            accumulated = write_area_parquet_v3(
                sums,
                times_batch,
                code_to_label,
                n_codes,
                member,
                scenario,
                group_col,
                pq_out,
                cfg.parquet_codec,
                accumulated,
            )

            logger.info(
                "area v3 batch %d/%d member=%s scenario=%s",
                t1i,
                n_times,
                member,
                scenario,
            )

    finally:
        ds.close()


# =============================================================================
# GCM JOB
# =============================================================================

def _run_gcm_job_v3(
    member,
    scenario,
    cfg,
    codes_arr,
    pixel_area,
    qa_mask,
    code_to_label,
    n_codes,
    open_water_sat,
    sat_lat_ref,
    sat_lon_ref,
    qa_lat=None,
    qa_lon=None,
):
    """Run one GCM-scenario v3 job."""
    start_time = time.time()

    logger.info(
        "===START GCM v3=== member=%s scenario=%s",
        member,
        scenario,
    )

    pq_out = cfg.parquet_out_path(member, scenario)

    if Path(pq_out).exists() and cfg.skip_existing:
        logger.info("Parquet exists, skipping: %s", pq_out)
        return

    import os as _os

    cache_dir = _os.environ.get("WTD_CLIM_CACHE_DIR", "")
    cache_path = (
        Path(cache_dir) / f"wtd_clim_{member}.npy"
        if cache_dir
        else None
    )

    if cache_path and cache_path.exists():
        wtd_clim = np.load(str(cache_path))
        logger.info(
            "Loaded cached WTD climatology: %s shape=%s",
            cache_path,
            wtd_clim.shape,
        )
    else:
        logger.info(
            "Building WTD climatology for %s: window=%s",
            member,
            cfg.wtd_clim_window,
        )

        wtd_clim = build_wtd_climatology(
            cfg.wtd_clim_zarr_path(member),
            cfg.wtd_clim_window,
            target_lat=sat_lat_ref,
            target_lon=sat_lon_ref,
        )

        logger.info(
            "WTD climatology built: shape=%s",
            wtd_clim.shape,
        )

        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(str(cache_path), wtd_clim)
            logger.info("Cached WTD climatology: %s", cache_path)

    sat_ref = open_sat(cfg.gcm_sat_path(member, scenario))
    sat_lat = sat_ref["lat"].values
    sat_lon = sat_ref["lon"].values

    lu = (
        PcrLazy(
            scenario,
            cfg.pcr_files[scenario],
            sat_lat,
            sat_lon,
            cfg.lu_vars,
        )
        if cfg.apply_lu_mask
        else None
    )

    if cfg.apply_lu_mask:

        class _FrozenLU:
            def __init__(self, base):
                self._base = base

            def get_dynamic_tile(self, year, y0, y1, x0, x1):
                return self._base.get_frozen_tile(
                    y0,
                    y1,
                    x0,
                    x1,
                    cfg.lu_freeze_mode,
                    cfg.lu_freeze_start,
                    cfg.lu_freeze_end,
                    cfg.fix_lu_year,
                )

        lu_frozen = _FrozenLU(lu)

    else:
        lu_frozen = None

    # Pixel area is needed only when writing/rebuilding the NetCDF area fields.
    if qa_lat is not None and qa_lon is not None:
        r_lat, r_lon = build_regrid_indices(
            qa_lat,
            qa_lon,
            sat_lat,
            sat_lon,
        )
        pixel_area_sat = pixel_area[np.ix_(r_lat, r_lon)].astype(np.float32)
    else:
        pixel_area_sat = pixel_area.astype(np.float32)

    nc_out = cfg.nc_out_path(member, scenario)

    if Path(nc_out).exists() and cfg.skip_existing:
        logger.info("NC exists, skipping mask: %s", nc_out)
    else:
        _write_fgdw_mask_v3(
            member,
            scenario,
            cfg,
            nc_out,
            lu,
            lu_frozen,
            wtd_clim,
            open_water_sat,
            pixel_area_sat,
        )

    _area_loop_v3(
        member,
        scenario,
        cfg,
        nc_out,
        codes_arr,
        pixel_area,
        qa_mask,
        code_to_label,
        n_codes,
        group_col="BIOME_ID_REALM",
        qa_lat=qa_lat,
        qa_lon=qa_lon,
    )

    logger.info(
        "===DONE GCM v3=== member=%s scenario=%s wall=%.1f s",
        member,
        scenario,
        time.time() - start_time,
    )


# =============================================================================
# RUN ALL
# =============================================================================

def run_all(cfg: Config) -> None:
    """Run all configured v3 GCM jobs."""
    import logging as _logging

    cfg.validate()

    for directory in (
        cfg.out_nc_dir,
        cfg.out_parquet_dir,
        cfg.log_dir,
    ):
        Path(directory).mkdir(parents=True, exist_ok=True)

    formatter = _logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    root = _logging.getLogger()
    root.setLevel(_logging.INFO)

    if not any(
        isinstance(handler, _logging.StreamHandler)
        for handler in root.handlers
    ):
        stream_handler = _logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    file_handler = _logging.FileHandler(
        f"{cfg.log_dir}/wetgde_pipeline_v3.log"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logger.info(
        "v3 pipeline: RUN_GCMS=%s APPLY_LU_MASK=%s",
        cfg.run_gcms,
        cfg.apply_lu_mask,
    )

    logger.info("Loading QA mask")
    qa_lat, qa_lon, qa_mask = build_qa_mask(cfg.qa_dir)

    logger.info("Loading open-water mask")
    open_water_qa = build_open_water_mask(
        cfg.open_water_mask_tif,
        qa_lat,
        qa_lon,
    )

    pixel_area = load_pixel_area(
        cfg.cell_area_path,
        cfg.cell_area_var,
        cfg.cell_area_units,
        qa_lat,
        qa_lon,
    )

    reference_scenario = (
        cfg.only_scenario
        or (
            "historical"
            if "historical" in cfg.scenarios
            else cfg.scenarios[0]
        )
    )

    reference_member = cfg.only_member or cfg.gcms[0]

    sat_reference = open_sat(
        cfg.gcm_sat_path(
            reference_member,
            reference_scenario,
        )
    )

    sat_lat_ref = sat_reference["lat"].values
    sat_lon_ref = sat_reference["lon"].values

    logger.info(
        "Remapping open-water mask to sat grid (%d x %d)",
        sat_lat_ref.size,
        sat_lon_ref.size,
    )

    open_water_sat = _remap_open_water(
        open_water_qa,
        qa_lat,
        qa_lon,
        sat_lat_ref,
        sat_lon_ref,
    )

    logger.info("Building BIOME_ID_REALM raster")

    gcm_codes, gcm_labels, _ = build_biome_realm_raster(
        cfg.biome_shp,
        qa_lat,
        qa_lon,
        qa_mask,
        open_water_qa,
    )

    gcm_n = len(gcm_labels)

    logger.info(
        "BIOME_ID_REALM: %d codes",
        gcm_n,
    )

    if not cfg.run_gcms:
        raise ValueError("v3 pipeline: set RUN_GCMS=1")

    jobs = _standard_jobs(cfg.gcms, cfg)

    logger.info("GCM v3 jobs: %d", len(jobs))

    for member, scenario in jobs:
        try:
            _run_gcm_job_v3(
                member,
                scenario,
                cfg,
                gcm_codes,
                pixel_area,
                qa_mask,
                gcm_labels,
                gcm_n,
                open_water_sat,
                sat_lat_ref,
                sat_lon_ref,
                qa_lat=qa_lat,
                qa_lon=qa_lon,
            )
        except Exception as exc:
            logger.error(
                "FAILED gcm member=%s scenario=%s: %s",
                member,
                scenario,
                exc,
                exc_info=True,
            )