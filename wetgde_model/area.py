# """
# area.py  --  raster construction and tile-based area aggregation.

# Two raster types:
#   build_biome_realm_raster   for ensemble: BIOME_ID_REALM grouping, QA + open water mask
#   build_realm_raster         for GCMs/sensitivity: REALM grouping, QA + open water mask

# Both return (codes_arr, code_to_label, label_to_code).
# Area aggregation is the same function for both: aggregate_tile_two_col.
# """
# from __future__ import annotations

# import logging
# from typing import Dict, Optional, Tuple

# import geopandas as gpd
# import numpy as np
# import rasterio.features
# from affine import Affine

# logger = logging.getLogger(__name__)

# R_EARTH: float = 6_371_000.0  # m


# def build_pixel_area(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
#     """Pixel area in km2. Returns float32 (ny, nx). Analytical fallback."""
#     lat_res = float(abs(lat[1] - lat[0]))
#     lon_res = float(abs(lon[1] - lon[0]))
#     dlam = lon_res / 360.0
#     band = (
#         np.sin(np.deg2rad(lat + lat_res / 2.0))
#         - np.sin(np.deg2rad(lat - lat_res / 2.0))
#     )
#     row_area = (2.0 * np.pi * R_EARTH**2 * band * dlam / 1e6).astype("float32")
#     return np.repeat(row_area[:, None], lon.size, axis=1)


# def load_pixel_area(
#     cell_area_path: str,
#     cell_area_var: str,
#     cell_area_units: str,
#     tgt_lat: np.ndarray,
#     tgt_lon: np.ndarray,
# ) -> np.ndarray:
#     """
#     Load pixel area from NetCDF file and remap to target grid.
#     Returns float32 (ny, nx) in km2.
#     Falls back to analytical computation if file not found.
#     """
#     import xarray as xr
#     from pathlib import Path

#     if not Path(cell_area_path).exists():
#         logger.warning(
#             "Cell area file not found: %s  falling back to analytical", cell_area_path
#         )
#         return build_pixel_area(tgt_lat, tgt_lon)

#     ds = xr.open_dataset(cell_area_path, decode_times=False)

#     # standardise coords
#     ren = {}
#     if "latitude" in ds.coords:  ren["latitude"]  = "lat"
#     if "longitude" in ds.coords: ren["longitude"] = "lon"
#     if ren:
#         ds = ds.rename(ren)

#     var = cell_area_var if cell_area_var in ds else list(ds.data_vars)[0]
#     arr = ds[var].values.astype(np.float32)
#     src_lat = ds["lat"].values.astype(np.float64)
#     src_lon = ds["lon"].values.astype(np.float64)
#     ds.close()

#     # convert to km2
#     if cell_area_units.lower() == "m2":
#         arr = arr / 1e6
#     elif cell_area_units.lower() == "ha":
#         arr = arr / 100.0

#     # sort src lat ascending
#     if src_lat[0] > src_lat[-1]:
#         src_lat = src_lat[::-1]
#         arr = arr[::-1, :]

#     # nearest-neighbour remap to target grid
#     def _nn(src, tgt):
#         idx = np.searchsorted(src, tgt)
#         idx = np.clip(idx, 1, len(src) - 1)
#         left, right = src[idx - 1], src[idx]
#         use_left = (tgt - left) <= (right - tgt)
#         return (idx - use_left.astype(np.int32)).astype(np.int32)

#     # normalise lon convention
#     src_lon_max = float(src_lon.max())
#     tgt_lon2 = np.array(tgt_lon, copy=True, dtype=np.float64)
#     if src_lon_max > 180.0 and tgt_lon2.min() < 0.0:
#         tgt_lon2 = np.mod(tgt_lon2, 360.0)
#     elif src_lon_max <= 180.0 and tgt_lon2.max() > 180.0:
#         tgt_lon2 = ((tgt_lon2 + 180.0) % 360.0) - 180.0

#     lat_idx = _nn(src_lat, tgt_lat)
#     lon_idx = _nn(src_lon, tgt_lon2)

#     remapped = arr[np.ix_(lat_idx, lon_idx)].astype(np.float32)
#     logger.info(
#         "Cell area loaded from %s  mean=%.4f km2  grid=(%d x %d)",
#         cell_area_path, float(remapped.mean()), tgt_lat.size, tgt_lon.size,
#     )
#     return remapped


# def _rasterize(
#     gdf: "gpd.GeoDataFrame",
#     label_col: str,
#     lat: np.ndarray,
#     lon: np.ndarray,
#     exclusion_mask: np.ndarray,  # bool (ny, nx): True = excluded
# ) -> Tuple[np.ndarray, Dict[int, str], Dict[str, int]]:
#     """Shared rasterization logic for any label column."""
#     labels = sorted(gdf[label_col].unique())
#     label_to_code: Dict[str, int] = {l: i + 1 for i, l in enumerate(labels)}
#     code_to_label: Dict[int, str] = {v: k for k, v in label_to_code.items()}

#     ny, nx = lat.size, lon.size
#     lat_res = float(abs(lat[1] - lat[0]))
#     lon_res = float(abs(lon[1] - lon[0]))
#     transform = Affine(
#         lon_res, 0.0, lon.min() - lon_res / 2.0,
#         0.0, -lat_res, lat.max() + lat_res / 2.0,
#     )
#     shapes = (
#         (geom, label_to_code[lbl])
#         for geom, lbl in zip(gdf.geometry, gdf[label_col])
#     )
#     codes_arr = rasterio.features.rasterize(
#         shapes, out_shape=(ny, nx), transform=transform, fill=0, dtype="int32"
#     )
#     codes_arr = np.where(~exclusion_mask, codes_arr, 0).astype(np.int32)

#     n_active = int((codes_arr > 0).sum())
#     logger.info(
#         "Raster '%s': %d labels, %d active pixels (%.2f%%)",
#         label_col, len(labels), n_active, 100.0 * n_active / codes_arr.size,
#     )
#     return codes_arr, code_to_label, label_to_code


# def _load_wwf(shp_path: str) -> "gpd.GeoDataFrame":
#     gdf = gpd.read_file(shp_path).set_crs("EPSG:4326", allow_override=True)
#     if "BIOME" not in gdf.columns or "REALM" not in gdf.columns:
#         raise RuntimeError(f"Shapefile must contain BIOME and REALM fields: {shp_path}")
#     gdf = gdf.loc[gdf["BIOME"].between(1, 14), ["BIOME", "REALM", "geometry"]].copy()
#     gdf = gdf.dropna(subset=["REALM", "geometry"])
#     return gdf


# def build_biome_realm_raster(
#     shp_path: str,
#     lat: np.ndarray,
#     lon: np.ndarray,
#     qa_mask: np.ndarray,
#     open_water_mask: np.ndarray,
# ) -> Tuple[np.ndarray, Dict[int, str], Dict[str, int]]:
#     """
#     Biome x Realm raster for ensemble runs.
#     Exclusion: QA mask + open water mask.
#     Group column: BIOME_ID_REALM  e.g. '1_PA'
#     """
#     gdf = _load_wwf(shp_path)
#     gdf["BIOME_ID_REALM"] = (
#         gdf["BIOME"].astype(int).astype(str) + "_" + gdf["REALM"].astype(str)
#     )
#     exclusion = (~qa_mask) | open_water_mask
#     return _rasterize(gdf, "BIOME_ID_REALM", lat, lon, exclusion)


# def build_realm_raster(
#     shp_path: str,
#     lat: np.ndarray,
#     lon: np.ndarray,
#     qa_mask: np.ndarray,              # True = valid
#     open_water_mask: np.ndarray,      # True = open water (exclude)
# ) -> Tuple[np.ndarray, Dict[int, str], Dict[str, int]]:
#     """
#     Realm-only raster for GCM and sensitivity runs.
#     Exclusion: QA mask + open water mask.
#     Group column: REALM  e.g. 'PA'
#     """
#     gdf = _load_wwf(shp_path)
#     gdf["REALM"] = gdf["REALM"].astype(str).str.strip()
#     gdf = gdf[gdf["REALM"] != ""]
#     exclusion = (~qa_mask) | open_water_mask
#     return _rasterize(gdf, "REALM", lat, lon, exclusion)


# def aggregate_tile_two_col(
#     wet_tile: np.ndarray,       # int8    (B, ty, tx)   1=wet, 0=dry, 127=missing
#     codes_tile: np.ndarray,     # int32   (ty, tx)
#     area_tile: np.ndarray,      # float32 (ty, tx)   km2
#     lu_tile: np.ndarray,        # float32 (ty, tx)   LU fraction [0,1]
#     n_codes: int,
#     apply_lu_mask: bool,
#     sums_none: np.ndarray,      # float64 (B, n_codes+1)  in place
#     sums_lu: np.ndarray,        # float64 (B, n_codes+1)  in place
#     f_gdw_tile: np.ndarray = None,  # float32 (B, ty, tx) wtd_shallow_frac; if None use binary
# ) -> None:
#     """
#     Accumulate area sums for one tile across a time batch.

#     Formula (Schipper et al.):
#       A_gdw,i = f_gdw,i * (1 - f_conv,i) * A_i

#     sums_none += f_gdw * A              (no LU exclusion)
#     sums_lu   += f_gdw * (1-lu) * A    (with LU exclusion)

#     If f_gdw_tile is None, falls back to binary (f_gdw = 1 where wetGDE=1).
#     """
#     B = wet_tile.shape[0]
#     codes_flat = codes_tile.ravel()
#     area_flat  = area_tile.ravel().astype(np.float64)
#     lu_flat    = np.nan_to_num(lu_tile.ravel(), nan=0.0).clip(0.0, 1.0).astype(np.float64)

#     for k in range(B):
#         wet_flat = wet_tile[k].ravel()
#         mask = (wet_flat == np.int8(1)) & (codes_flat > 0)
#         if not mask.any():
#             continue

#         if f_gdw_tile is not None:
#             fgdw_flat = np.nan_to_num(f_gdw_tile[k].ravel(), nan=0.0).clip(0.0, 1.0).astype(np.float64)
#         else:
#             fgdw_flat = np.ones(len(wet_flat), dtype=np.float64)

#         w_none = fgdw_flat[mask] * area_flat[mask]
#         w_lu   = fgdw_flat[mask] * (1.0 - lu_flat[mask]) * area_flat[mask] if apply_lu_mask else w_none

#         sums_none[k] += np.bincount(codes_flat[mask], weights=w_none, minlength=n_codes + 1)
#         sums_lu[k]   += np.bincount(codes_flat[mask], weights=w_lu,   minlength=n_codes + 1)

# def aggregate_tile_fgdw(
#     fgdw_tile: np.ndarray,   # float32 (ty, tx)  f_gdw values, NaN = not GDW
#     codes_tile: np.ndarray,  # int32   (ty, tx)
#     area_tile:  np.ndarray,  # float32 (ty, tx)  km2
#     qa_tile:    np.ndarray,  # bool    (ty, tx)  True = valid (QA mask)
#     n_codes:    int,
#     sums:       np.ndarray,  # float64 (n_codes+1,)  in place
# ) -> None:
#     """
#     Accumulate area for one tile.
#     A_gdw,i = f_gdw,i * A_i   (LU already baked into f_gdw)
#     QA mask applied here.
#     NaN f_gdw pixels skipped automatically.
#     """
#     codes_flat = codes_tile.ravel()
#     area_flat  = area_tile.ravel().astype(np.float64)
#     fgdw_flat  = fgdw_tile.ravel().astype(np.float64)
#     qa_flat    = qa_tile.ravel()

#     mask = (np.isfinite(fgdw_flat)) & (fgdw_flat > 0) & (codes_flat > 0) & qa_flat
#     if not mask.any():
#         return

#     weights = fgdw_flat[mask] * area_flat[mask]
#     sums += np.bincount(codes_flat[mask], weights=weights, minlength=n_codes + 1)

"""
area.py -- raster construction and tile-based area aggregation.

Key correction
--------------
Cell area is an extensive quantity and must not be nearest-neighbour
resampled from a coarser grid to a finer grid. This module computes pixel
area directly on the target latitude-longitude grid.

All areas returned and aggregated by this module are in km².
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import geopandas as gpd
import numpy as np
import rasterio.features
from affine import Affine

logger = logging.getLogger(__name__)

R_EARTH_M: float = 6_371_000.0
EARTH_SURFACE_AREA_KM2: float = 4.0 * np.pi * (R_EARTH_M / 1000.0) ** 2


# =============================================================================
# GRID AND AREA HELPERS
# =============================================================================

def _validate_1d_regular_coord(
    values: np.ndarray,
    name: str,
    *,
    rtol: float = 3e-3,
    atol: float = 1e-8,
) -> float:
    """
    Validate an approximately regular one-dimensional coordinate.

    Small deviations caused by float32 coordinate storage are allowed.

    Returns
    -------
    float
        Median absolute grid spacing.
    """
    arr = np.asarray(values, dtype=np.float64)

    if arr.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional; got shape {arr.shape}.")
    if arr.size < 2:
        raise ValueError(f"{name} must contain at least two values.")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains non-finite values.")

    diffs = np.diff(arr)

    if np.any(diffs == 0):
        raise ValueError(f"{name} contains duplicate coordinate values.")

    if not (np.all(diffs > 0) or np.all(diffs < 0)):
        raise ValueError(f"{name} must be strictly monotonic.")

    abs_diffs = np.abs(diffs)
    step = float(np.median(abs_diffs))
    max_rel_dev = float(np.max(np.abs(abs_diffs - step)) / step)

    if max_rel_dev > rtol and not np.allclose(
        abs_diffs, step, rtol=rtol, atol=atol
    ):
        raise ValueError(
            f"{name} is not approximately regularly spaced. "
            f"Median step={step}, min step={abs_diffs.min()}, "
            f"max step={abs_diffs.max()}, "
            f"maximum relative deviation={max_rel_dev:.6f}."
        )

    logger.info(
        "%s spacing accepted: median=%.12f°, min=%.12f°, "
        "max=%.12f°, max relative deviation=%.6f",
        name,
        step,
        float(abs_diffs.min()),
        float(abs_diffs.max()),
        max_rel_dev,
    )

    return step


def _validate_lat_lon(
    lat: np.ndarray,
    lon: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, float, float]:
    """Validate target-grid latitude and longitude coordinates."""
    lat_arr = np.asarray(lat, dtype=np.float64)
    lon_arr = np.asarray(lon, dtype=np.float64)

    lat_res = _validate_1d_regular_coord(lat_arr, "lat")
    lon_res = _validate_1d_regular_coord(lon_arr, "lon")

    if np.nanmin(lat_arr) < -90.0 - 1e-6 or np.nanmax(lat_arr) > 90.0 + 1e-6:
        raise ValueError(
            f"Latitude range must be within [-90, 90]; got "
            f"[{lat_arr.min()}, {lat_arr.max()}]."
        )

    if lon_res <= 0.0 or lon_res > 360.0:
        raise ValueError(f"Invalid longitude resolution: {lon_res} degrees.")

    return lat_arr, lon_arr, lat_res, lon_res


def build_pixel_area(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """
    Calculate pixel area in km² for an approximately regular lat-lon grid.

    Parameters
    ----------
    lat, lon
        One-dimensional arrays of cell-centre coordinates.

    Returns
    -------
    np.ndarray
        Float32 array with shape (lat.size, lon.size), in km².
    """
    lat_arr, lon_arr, lat_res, lon_res = _validate_lat_lon(lat, lon)

    # For a global longitude grid, use the exact nominal spacing inferred
    # from the number of columns when it matches the observed spacing.
    nominal_lon_res = 360.0 / lon_arr.size
    if np.isclose(lon_res, nominal_lon_res, rtol=3e-3, atol=1e-8):
        lon_res = nominal_lon_res

    south = np.clip(lat_arr - lat_res / 2.0, -90.0, 90.0)
    north = np.clip(lat_arr + lat_res / 2.0, -90.0, 90.0)
    dlon_rad = np.deg2rad(lon_res)

    row_area_km2 = (
        (R_EARTH_M ** 2)
        * dlon_rad
        * (
            np.sin(np.deg2rad(north))
            - np.sin(np.deg2rad(south))
        )
        / 1e6
    )

    row_area_km2 = np.maximum(row_area_km2, 0.0)

    area = np.repeat(
        row_area_km2.astype(np.float32)[:, None],
        lon_arr.size,
        axis=1,
    )

    if not np.all(np.isfinite(area)):
        raise ValueError("Calculated pixel-area array contains non-finite values.")
    if np.any(area < 0):
        raise ValueError("Calculated pixel-area array contains negative values.")

    return area


def _grid_is_global(lon: np.ndarray, lon_res: float) -> bool:
    """Return True when longitude coverage is approximately global."""
    lon_arr = np.asarray(lon, dtype=np.float64)
    coverage = lon_arr.size * lon_res
    return np.isclose(
        coverage,
        360.0,
        rtol=0.0,
        atol=max(1e-6, lon_res * 0.1),
    )


def validate_pixel_area(
    area_km2: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    *,
    global_tolerance_fraction: float = 0.02,
) -> None:
    """
    Validate physical plausibility of a target-grid pixel-area array.
    """
    area = np.asarray(area_km2, dtype=np.float64)
    lat_arr, lon_arr, _, lon_res = _validate_lat_lon(lat, lon)

    expected_shape = (lat_arr.size, lon_arr.size)
    if area.shape != expected_shape:
        raise ValueError(
            f"Pixel-area shape mismatch: got {area.shape}, "
            f"expected {expected_shape}."
        )

    if not np.all(np.isfinite(area)):
        raise ValueError("Pixel-area array contains non-finite values.")
    if np.any(area < 0):
        raise ValueError("Pixel-area array contains negative values.")
    if not np.any(area > 0):
        raise ValueError("Pixel-area array contains no positive values.")

    total_km2 = float(area.sum())

    if total_km2 > EARTH_SURFACE_AREA_KM2 * 1.02:
        raise ValueError(
            "Pixel-area sum exceeds Earth's surface area: "
            f"{total_km2 / 1e6:.3f} million km²."
        )

    if _grid_is_global(lon_arr, lon_res):
        lower = EARTH_SURFACE_AREA_KM2 * (1.0 - global_tolerance_fraction)
        upper = EARTH_SURFACE_AREA_KM2 * (1.0 + global_tolerance_fraction)

        if not (lower <= total_km2 <= upper):
            logger.warning(
                "Global grid area differs from spherical Earth area: "
                "calculated=%.3f million km², expected≈%.3f million km². "
                "This may be valid if the latitude domain is cropped.",
                total_km2 / 1e6,
                EARTH_SURFACE_AREA_KM2 / 1e6,
            )

    logger.info(
        "Pixel-area validation passed: shape=%s, min=%.6f km², "
        "mean=%.6f km², max=%.6f km², total=%.3f million km²",
        area.shape,
        float(area.min()),
        float(area.mean()),
        float(area.max()),
        total_km2 / 1e6,
    )


def load_pixel_area(
    cell_area_path: str,
    cell_area_var: str,
    cell_area_units: str,
    tgt_lat: np.ndarray,
    tgt_lon: np.ndarray,
) -> np.ndarray:
    """
    Return pixel area on the target grid in km².

    The source cell-area raster is intentionally not nearest-neighbour
    resampled. Cell area is extensive, so that would duplicate coarse-cell
    area into multiple fine cells and inflate totals.

    File-related arguments are retained for compatibility with the existing
    pipeline.
    """
    path = Path(cell_area_path)

    if path.exists():
        logger.info(
            "Cell-area source exists at %s (variable=%s, declared units=%s), "
            "but values are not resampled because cell area is extensive. "
            "Computing area directly on the target grid.",
            path,
            cell_area_var,
            cell_area_units,
        )
    else:
        logger.warning(
            "Cell-area file not found at %s. Computing area directly on the "
            "target grid.",
            path,
        )

    area = build_pixel_area(tgt_lat, tgt_lon)
    validate_pixel_area(area, tgt_lat, tgt_lon)
    return area


# =============================================================================
# RASTERIZATION
# =============================================================================

def _rasterize(
    gdf: gpd.GeoDataFrame,
    label_col: str,
    lat: np.ndarray,
    lon: np.ndarray,
    exclusion_mask: np.ndarray,
) -> Tuple[np.ndarray, Dict[int, str], Dict[str, int]]:
    """Shared rasterization logic for any label column."""
    lat_arr, lon_arr, lat_res, lon_res = _validate_lat_lon(lat, lon)

    expected_shape = (lat_arr.size, lon_arr.size)
    if exclusion_mask.shape != expected_shape:
        raise ValueError(
            f"exclusion_mask shape {exclusion_mask.shape} does not match "
            f"{expected_shape}."
        )

    if label_col not in gdf.columns:
        raise KeyError(f"Missing label column '{label_col}'.")

    gdf_valid = gdf.dropna(subset=[label_col, "geometry"]).copy()
    gdf_valid[label_col] = gdf_valid[label_col].astype(str)

    labels = sorted(gdf_valid[label_col].unique())
    if not labels:
        raise ValueError(f"No valid labels found in column '{label_col}'.")

    label_to_code: Dict[str, int] = {
        label: i + 1 for i, label in enumerate(labels)
    }
    code_to_label: Dict[int, str] = {
        code: label for label, code in label_to_code.items()
    }

    lat_descending = lat_arr[0] > lat_arr[-1]
    lat_for_transform = lat_arr if lat_descending else lat_arr[::-1]
    exclusion_for_raster = (
        exclusion_mask if lat_descending else exclusion_mask[::-1, :]
    )

    transform = Affine(
        lon_res,
        0.0,
        float(lon_arr.min() - lon_res / 2.0),
        0.0,
        -lat_res,
        float(lat_for_transform.max() + lat_res / 2.0),
    )

    shapes = (
        (geometry, label_to_code[label])
        for geometry, label in zip(
            gdf_valid.geometry,
            gdf_valid[label_col],
        )
    )

    codes_arr = rasterio.features.rasterize(
        shapes=shapes,
        out_shape=expected_shape,
        transform=transform,
        fill=0,
        dtype="int32",
    )

    codes_arr = np.where(
        ~exclusion_for_raster,
        codes_arr,
        0,
    ).astype(np.int32)

    if not lat_descending:
        codes_arr = codes_arr[::-1, :]

    n_active = int(np.count_nonzero(codes_arr > 0))
    logger.info(
        "Raster '%s': %d labels, %d active pixels (%.2f%%)",
        label_col,
        len(labels),
        n_active,
        100.0 * n_active / codes_arr.size,
    )

    return codes_arr, code_to_label, label_to_code


def _load_wwf(shp_path: str) -> gpd.GeoDataFrame:
    """Load and validate the WWF terrestrial ecoregions shapefile."""
    path = Path(shp_path)
    if not path.exists():
        raise FileNotFoundError(f"WWF shapefile not found: {path}")

    gdf = gpd.read_file(path)

    if gdf.crs is None:
        logger.warning("WWF shapefile has no CRS. Assuming EPSG:4326.")
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    required = {"BIOME", "REALM", "geometry"}
    missing = required.difference(gdf.columns)
    if missing:
        raise RuntimeError(
            f"Shapefile must contain BIOME and REALM fields. Missing: {missing}"
        )

    gdf = gdf.loc[
        gdf["BIOME"].between(1, 14),
        ["BIOME", "REALM", "geometry"],
    ].copy()

    gdf = gdf.dropna(subset=["REALM", "geometry"])
    gdf["REALM"] = gdf["REALM"].astype(str).str.strip()
    gdf = gdf[gdf["REALM"] != ""]

    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        logger.warning(
            "Repairing %d invalid WWF geometries with buffer(0).",
            int(invalid.sum()),
        )
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)

    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()

    if gdf.empty:
        raise ValueError("WWF shapefile contains no valid biome-realm features.")

    return gdf


def build_biome_realm_raster(
    shp_path: str,
    lat: np.ndarray,
    lon: np.ndarray,
    qa_mask: np.ndarray,
    open_water_mask: np.ndarray,
) -> Tuple[np.ndarray, Dict[int, str], Dict[str, int]]:
    """
    Build biome-realm raster for ensemble runs.

    Exclusion: failed QA or open water.
    Group column: BIOME_ID_REALM, e.g. '1_PA'.
    """
    expected_shape = (np.asarray(lat).size, np.asarray(lon).size)

    if qa_mask.shape != expected_shape:
        raise ValueError(
            f"qa_mask shape {qa_mask.shape} does not match {expected_shape}."
        )
    if open_water_mask.shape != expected_shape:
        raise ValueError(
            f"open_water_mask shape {open_water_mask.shape} does not match "
            f"{expected_shape}."
        )

    gdf = _load_wwf(shp_path)
    gdf["BIOME_ID_REALM"] = (
        gdf["BIOME"].astype(int).astype(str)
        + "_"
        + gdf["REALM"].astype(str)
    )

    exclusion = (~qa_mask.astype(bool)) | open_water_mask.astype(bool)

    return _rasterize(
        gdf,
        "BIOME_ID_REALM",
        lat,
        lon,
        exclusion,
    )


def build_realm_raster(
    shp_path: str,
    lat: np.ndarray,
    lon: np.ndarray,
    qa_mask: np.ndarray,
    open_water_mask: np.ndarray,
) -> Tuple[np.ndarray, Dict[int, str], Dict[str, int]]:
    """
    Build realm-only raster for GCM and sensitivity runs.

    Exclusion: failed QA or open water.
    Group column: REALM, e.g. 'PA'.
    """
    expected_shape = (np.asarray(lat).size, np.asarray(lon).size)

    if qa_mask.shape != expected_shape:
        raise ValueError(
            f"qa_mask shape {qa_mask.shape} does not match {expected_shape}."
        )
    if open_water_mask.shape != expected_shape:
        raise ValueError(
            f"open_water_mask shape {open_water_mask.shape} does not match "
            f"{expected_shape}."
        )

    gdf = _load_wwf(shp_path)
    exclusion = (~qa_mask.astype(bool)) | open_water_mask.astype(bool)

    return _rasterize(
        gdf,
        "REALM",
        lat,
        lon,
        exclusion,
    )


# =============================================================================
# TILE AGGREGATION
# =============================================================================

def _validate_tile_shapes(
    wet_tile: np.ndarray,
    codes_tile: np.ndarray,
    area_tile: np.ndarray,
    lu_tile: np.ndarray,
    f_gdw_tile: Optional[np.ndarray],
) -> None:
    """Validate shapes for batch tile aggregation."""
    if wet_tile.ndim != 3:
        raise ValueError(
            f"wet_tile must have shape (B, ty, tx); got {wet_tile.shape}."
        )

    _, ty, tx = wet_tile.shape
    expected_2d = (ty, tx)

    if codes_tile.shape != expected_2d:
        raise ValueError(
            f"codes_tile shape {codes_tile.shape} does not match {expected_2d}."
        )
    if area_tile.shape != expected_2d:
        raise ValueError(
            f"area_tile shape {area_tile.shape} does not match {expected_2d}."
        )
    if lu_tile.shape != expected_2d:
        raise ValueError(
            f"lu_tile shape {lu_tile.shape} does not match {expected_2d}."
        )
    if f_gdw_tile is not None and f_gdw_tile.shape != wet_tile.shape:
        raise ValueError(
            f"f_gdw_tile shape {f_gdw_tile.shape} does not match "
            f"wet_tile shape {wet_tile.shape}."
        )

    if not np.all(np.isfinite(area_tile)):
        raise ValueError("area_tile contains non-finite values.")
    if np.any(area_tile < 0):
        raise ValueError("area_tile contains negative values.")


def aggregate_tile_two_col(
    wet_tile: np.ndarray,
    codes_tile: np.ndarray,
    area_tile: np.ndarray,
    lu_tile: np.ndarray,
    n_codes: int,
    apply_lu_mask: bool,
    sums_none: np.ndarray,
    sums_lu: np.ndarray,
    f_gdw_tile: Optional[np.ndarray] = None,
) -> None:
    """
    Accumulate area sums for one tile across a time batch.

    sums_none += f_gdw * A
    sums_lu   += f_gdw * (1 - f_conv) * A

    All area values are in km².
    """
    _validate_tile_shapes(
        wet_tile,
        codes_tile,
        area_tile,
        lu_tile,
        f_gdw_tile,
    )

    batch_size = wet_tile.shape[0]
    expected_shape = (batch_size, n_codes + 1)

    if sums_none.shape != expected_shape:
        raise ValueError(
            f"sums_none shape {sums_none.shape} does not match {expected_shape}."
        )
    if sums_lu.shape != expected_shape:
        raise ValueError(
            f"sums_lu shape {sums_lu.shape} does not match {expected_shape}."
        )

    codes_flat = np.asarray(codes_tile, dtype=np.int32).ravel()
    area_flat = np.asarray(area_tile, dtype=np.float64).ravel()

    if np.any(codes_flat < 0) or np.any(codes_flat > n_codes):
        raise ValueError("codes_tile contains invalid zone codes.")

    lu_flat = np.nan_to_num(
        np.asarray(lu_tile, dtype=np.float64).ravel(),
        nan=0.0,
        posinf=1.0,
        neginf=0.0,
    )
    lu_flat = np.clip(lu_flat, 0.0, 1.0)

    for k in range(batch_size):
        wet_flat = np.asarray(wet_tile[k]).ravel()

        mask = (
            (wet_flat == np.int8(1))
            & (codes_flat > 0)
            & np.isfinite(area_flat)
            & (area_flat > 0)
        )

        if not np.any(mask):
            continue

        if f_gdw_tile is None:
            fgdw_flat = np.ones(wet_flat.size, dtype=np.float64)
        else:
            fgdw_flat = np.nan_to_num(
                np.asarray(f_gdw_tile[k], dtype=np.float64).ravel(),
                nan=0.0,
                posinf=1.0,
                neginf=0.0,
            )
            fgdw_flat = np.clip(fgdw_flat, 0.0, 1.0)

        w_none = fgdw_flat[mask] * area_flat[mask]

        if apply_lu_mask:
            w_lu = (
                fgdw_flat[mask]
                * (1.0 - lu_flat[mask])
                * area_flat[mask]
            )
        else:
            w_lu = w_none

        sums_none[k] += np.bincount(
            codes_flat[mask],
            weights=w_none,
            minlength=n_codes + 1,
        )
        sums_lu[k] += np.bincount(
            codes_flat[mask],
            weights=w_lu,
            minlength=n_codes + 1,
        )


def aggregate_tile_fgdw(
    fgdw_tile: np.ndarray,
    codes_tile: np.ndarray,
    area_tile: np.ndarray,
    qa_tile: np.ndarray,
    n_codes: int,
    sums: np.ndarray,
) -> None:
    """
    Accumulate area from a continuous f_gdw tile.

    A_gdw = f_gdw * A_pixel

    Land-use effects are assumed to already be included in f_gdw_tile.
    """
    if fgdw_tile.ndim != 2:
        raise ValueError(
            f"fgdw_tile must be two-dimensional; got {fgdw_tile.shape}."
        )

    expected_shape = fgdw_tile.shape

    if codes_tile.shape != expected_shape:
        raise ValueError(
            f"codes_tile shape {codes_tile.shape} does not match {expected_shape}."
        )
    if area_tile.shape != expected_shape:
        raise ValueError(
            f"area_tile shape {area_tile.shape} does not match {expected_shape}."
        )
    if qa_tile.shape != expected_shape:
        raise ValueError(
            f"qa_tile shape {qa_tile.shape} does not match {expected_shape}."
        )
    if sums.shape != (n_codes + 1,):
        raise ValueError(
            f"sums shape {sums.shape} does not match {(n_codes + 1,)}."
        )

    codes_flat = np.asarray(codes_tile, dtype=np.int32).ravel()
    area_flat = np.asarray(area_tile, dtype=np.float64).ravel()
    fgdw_flat = np.asarray(fgdw_tile, dtype=np.float64).ravel()
    qa_flat = np.asarray(qa_tile, dtype=bool).ravel()

    if np.any(codes_flat < 0) or np.any(codes_flat > n_codes):
        raise ValueError("codes_tile contains invalid zone codes.")
    if not np.all(np.isfinite(area_flat)):
        raise ValueError("area_tile contains non-finite values.")
    if np.any(area_flat < 0):
        raise ValueError("area_tile contains negative values.")

    mask = (
        np.isfinite(fgdw_flat)
        & (fgdw_flat > 0.0)
        & (codes_flat > 0)
        & qa_flat
        & (area_flat > 0.0)
    )

    if not np.any(mask):
        return

    weights = np.clip(fgdw_flat[mask], 0.0, 1.0) * area_flat[mask]

    sums += np.bincount(
        codes_flat[mask],
        weights=weights,
        minlength=n_codes + 1,
    )