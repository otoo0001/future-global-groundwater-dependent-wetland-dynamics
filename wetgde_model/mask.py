"""
mask.py  --  binary wetGDE computation.

Rule:
  wetGDE = 1    satAreaFrac > sat_threshold  AND  WTD <= wtd_threshold
  wetGDE = 0    valid pixels that do not meet the rule
  wetGDE = 127  missing (either input NaN)
"""
from __future__ import annotations

import numpy as np
import xarray as xr

FILL: np.int8 = np.int8(127)


def wetgde_tile(
    sat: np.ndarray,
    wtd: np.ndarray,
    sat_threshold: float,
    wtd_threshold: float,
) -> np.ndarray:
    """
    Compute wetGDE for one numpy tile.
    Both arrays must already be on the same grid.
    Returns int8, same shape as inputs.
    """
    valid = np.isfinite(sat) & np.isfinite(wtd)
    return np.where(
        valid,
        ((sat > sat_threshold) & (wtd <= wtd_threshold)).astype(np.int8),
        FILL,
    ).astype(np.int8)


def build_wetgde_lazy(
    sat: xr.DataArray,
    wtd_on_sat: xr.DataArray,
    sat_threshold: float,
    wtd_threshold: float,
) -> xr.DataArray:
    """
    Build wetGDE lazily via xarray/dask.
    sat and wtd_on_sat must share the same grid and time axis.
    Returns chunked int8 DataArray named 'wetGDE'.
    """
    valid = sat.notnull() & wtd_on_sat.notnull()
    wet = xr.where(
        valid,
        ((sat > sat_threshold) & (wtd_on_sat <= wtd_threshold)).astype("int8"),
        int(FILL),
    ).astype("int8")
    wet.name = "wetGDE"
    return wet
