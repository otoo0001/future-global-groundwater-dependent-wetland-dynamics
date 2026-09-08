"""
lu_utils.py  --  LU total fraction reader using aggregated lu_total files.

Follows 2_future_gdes_area.py exactly:
  Historical: lu_total_hist_ssp2_1970-2014_clamp01.nc
  SSP future: lu_total_{ssp_key}_2015-2100_clamp01.nc

Seam handled via delta-change bridge for full family (SSP scenarios only):
  LU_adj(t) = clip( LU_hist(2014) + (LU_fut(t) - LU_fut(2015)), 0, 1 )

Variable name inside files: controlled by LU_VAR (default "lu").
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)

LU_HIST_END   = 2014
LU_SCEN_START = 2015

_SSP_KEY = {
    "historical": None,
    "ssp126":     "ssp1",
    "ssp370":     "ssp3",
    "ssp585":     "ssp5",
}


def _std(ds):
    ren = {}
    if "latitude" in ds.coords: ren["latitude"] = "lat"
    if "longitude" in ds.coords: ren["longitude"] = "lon"
    return ds.rename(ren) if ren else ds


def _nn(src: np.ndarray, tgt: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(src, tgt)
    idx = np.clip(idx, 1, len(src) - 1)
    left, right = src[idx - 1], src[idx]
    use_left = (tgt - left) <= (right - tgt)
    return (idx - use_left.astype(np.int32)).astype(np.int32)


def _build_regrid_indices(src_lat, src_lon, tgt_lat, tgt_lon):
    if src_lat[0] > src_lat[-1]:
        lat_idx = _nn(src_lat[::-1], tgt_lat)
        lat_idx = (len(src_lat) - 1) - lat_idx
    else:
        lat_idx = _nn(src_lat, tgt_lat)
    src_lon_max = float(np.nanmax(src_lon))
    tgt_lon2 = np.array(tgt_lon, copy=True)
    if src_lon_max > 180.0 and tgt_lon2.min() < 0.0:
        tgt_lon2 = np.mod(tgt_lon2, 360.0)
    elif src_lon_max <= 180.0 and tgt_lon2.max() > 180.0:
        tgt_lon2 = ((tgt_lon2 + 180.0) % 360.0) - 180.0
    lon_idx = _nn(src_lon, tgt_lon2)
    return lat_idx.astype(np.int32), lon_idx.astype(np.int32)


class PcrLazy:
    """
    LU total fraction reader using aggregated lu_total files.
    Mirrors LuReader from 2_future_gdes_area.py.
    """

    def __init__(
        self,
        scenario: str,
        pcr_files: Dict[str, Path],   # {"hist": path, "fut": path}
        qa_lat: np.ndarray,
        qa_lon: np.ndarray,
        lu_vars=None,                 # unused, kept for API compatibility
    ):
        self.scenario = scenario
        self._qa_lat = qa_lat
        self._qa_lon = qa_lon
        self._files = []
        self._idx_cache: Dict = {}
        self._freeze_cache: Dict = {}
        self._delta_cache: Dict = {}

        hist_path = pcr_files.get("hist")
        fut_path  = pcr_files.get("fut")

        if hist_path is None or not Path(str(hist_path)).exists():
            raise FileNotFoundError(f"LU hist file missing: {hist_path}")

        hist_ds = _std(xr.open_dataset(str(hist_path), decode_times=True,
                                        engine="netcdf4", mask_and_scale=False))
        lu_var = [v for v in hist_ds.data_vars][0]
        hist_years = pd.DatetimeIndex(hist_ds["time"].values).year.values.astype(np.int32)
        hist_lat_idx, hist_lon_idx = _build_regrid_indices(
            hist_ds["lat"].values, hist_ds["lon"].values, qa_lat, qa_lon
        )
        self._files.append(dict(
            tag="hist", path=hist_path, ds=hist_ds, var=lu_var,
            years=hist_years, lat_idx=hist_lat_idx, lon_idx=hist_lon_idx,
        ))

        if fut_path is not None and Path(str(fut_path)).exists():
            fut_ds = _std(xr.open_dataset(str(fut_path), decode_times=True,
                                           engine="netcdf4", mask_and_scale=False))
            lu_var_f = [v for v in fut_ds.data_vars][0]
            fut_years = pd.DatetimeIndex(fut_ds["time"].values).year.values.astype(np.int32)
            fut_lat_idx, fut_lon_idx = _build_regrid_indices(
                fut_ds["lat"].values, fut_ds["lon"].values, qa_lat, qa_lon
            )
            self._files.append(dict(
                tag="fut", path=fut_path, ds=fut_ds, var=lu_var_f,
                years=fut_years, lat_idx=fut_lat_idx, lon_idx=fut_lon_idx,
            ))
        elif scenario != "historical" and fut_path is not None:
            raise FileNotFoundError(f"LU fut file missing: {fut_path}")

        logger.info("PcrLazy: scenario=%s files=%s", scenario,
                    [str(f["path"]) for f in self._files])

    def _select_file(self, year: int) -> dict:
        if self.scenario == "historical" or year <= LU_HIST_END:
            return self._files[0]
        return self._files[1]

    def _read_tile_year(self, f: dict, year: int, y0, y1, x0, x1) -> np.ndarray:
        years = f["years"]
        tidx  = int(np.argmin(np.abs(years - year)))
        src_lat = f["lat_idx"][y0:y1]
        src_lon = f["lon_idx"][x0:x1]
        lat_lo, lat_hi = int(src_lat.min()), int(src_lat.max())
        lon_lo, lon_hi = int(src_lon.min()), int(src_lon.max())
        box = f["ds"][f["var"]].isel(
            time=tidx,
            lat=slice(lat_lo, lat_hi + 1),
            lon=slice(lon_lo, lon_hi + 1),
        ).values.astype(np.float32)
        slab = box[np.ix_(src_lat - lat_lo, src_lon - lon_lo)]
        return np.where((slab >= 0.0) & (slab <= 1.0), slab, 0.0).astype(np.float32)

    def _delta_tile(self, y0, y1, x0, x1) -> np.ndarray:
        """LU delta at seam: LU_hist(2014) - LU_fut(2015) for bridge correction."""
        cache_key = ("delta", y0, y1, x0, x1)
        if cache_key in self._delta_cache:
            return self._delta_cache[cache_key]
        hist_2014 = self._read_tile_year(self._files[0], LU_HIST_END,  y0, y1, x0, x1)
        fut_2015  = self._read_tile_year(self._files[1], LU_SCEN_START, y0, y1, x0, x1)
        delta = (hist_2014 - fut_2015).astype(np.float32)
        self._delta_cache[cache_key] = delta
        return delta

    def get_dynamic_tile(self, year: int, y0, y1, x0, x1) -> np.ndarray:
        """
        Dynamic LU for one year with delta-change bridge at seam.
        Matches 2_future_gdes_area.py LU_BRIDGE_FULL logic.
        """
        f = self._select_file(year)
        slab = self._read_tile_year(f, year, y0, y1, x0, x1)
        if self.scenario != "historical" and year >= LU_SCEN_START:
            delta = self._delta_tile(y0, y1, x0, x1)
            slab = np.clip(slab + delta, 0.0, 1.0).astype(np.float32)
        return slab

    def get_frozen_tile(
        self,
        y0, y1, x0, x1,
        freeze_mode: str,
        freeze_start: int,
        freeze_end: int,
        fix_year: int,
    ) -> np.ndarray:
        cache_key = (y0, y1, x0, x1, freeze_mode, freeze_start, freeze_end, fix_year)
        if cache_key in self._freeze_cache:
            return self._freeze_cache[cache_key]

        if freeze_mode == "year":
            s = self._read_tile_year(self._select_file(fix_year), fix_year, y0, y1, x0, x1)
        else:
            years = np.arange(freeze_start, freeze_end + 1, dtype=np.int32)
            acc = np.zeros((y1 - y0, x1 - x0), dtype=np.float32)
            for yr in years:
                acc += self._read_tile_year(self._select_file(int(yr)), int(yr), y0, y1, x0, x1)
            s = np.clip(acc / max(1, len(years)), 0.0, 1.0).astype(np.float32)

        self._freeze_cache[cache_key] = s
        return s
