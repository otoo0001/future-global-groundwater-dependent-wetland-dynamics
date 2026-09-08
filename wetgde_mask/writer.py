"""
writer.py  --  metadata, encoding, and output setup for Paper 3 wetGDE f_gdw output.

NC variables:
  f_gdw        (float32)  fraction 0-1, NaN = not GDW / open water / outside domain
  area_gdw_km2 (float32)  = f_gdw * pixel_area_km2, NaN where f_gdw is NaN
  No history attribute written.
"""

import os
import numpy as np
import xarray as xr
from datetime import datetime

from . import config as cfg
from .grid_utils import chunk_map
from .io import sat_source_path

FGDW_FILL = np.float32(-9999.0)


def build_global_attrs(scen: str) -> dict:
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return {
        "Conventions":           cfg.CONVENTIONS,
        "product_version":       cfg.PRODUCT_VERSION,
        "license":               cfg.LICENSE,
        "doi":                   cfg.DOI,
        "creator_name":          cfg.AUTHOR,
        "creator_email":         cfg.EMAIL,
        "creator_institution":   cfg.INSTITUTION,
        "supervisor":            cfg.SUPERVISOR,
        "supervisor_email":      cfg.SUPERVISOR_EMAIL,
        "project":               cfg.PROJECT,
        "references":            cfg.REFERENCES,
        "model_sat":             cfg.MODEL_SAT,
        "model_wtd":             cfg.MODEL_WTD,
        "forcing":               cfg.FORCING,
        "date_created":          now,
        "featureType":           "grid",
        "spatial_resolution":    "5 arcmin (~9 km); native PCR-GLOBWB resolution",
        "source_sat_resolution": "5 arcmin",
        "source_wtd_resolution": "~30 arcsec (1/120 deg, GLOBGM)",
        "sat_threshold":         str(cfg.SAT_THRESHOLD),
        "wtd_frac_threshold":    str(cfg.WTD_FRAC_THRESHOLD),
        "min_valid_fine_cells":  str(cfg.MIN_VALID_FINE_CELLS),
        "frequency":             "monthly",
        "scenario":              scen,
        # no history
    }


def build_var_attrs(scen: str) -> dict:
    src     = sat_source_path(scen)
    wtd_src = f"{cfg.WTD_ROOT}/{scen}/ensemble.zarr"
    formula = (
        "satAreaFrac * is_gdw * (1 - f_conv); "
        f"is_gdw: satAreaFrac>{cfg.SAT_THRESHOLD} AND "
        f"wtd_shallow_frac>={cfg.WTD_FRAC_THRESHOLD}; "
        "open-water and non-GDW pixels = NaN"
    )
    return {
        "f_gdw": {
            "long_name":    "GDW fraction after land-use exclusion",
            "units":        "1",
            "valid_range":  "0.0, 1.0",
            "formula":      formula,
            "scenario":     scen,
            "source_sat":   os.path.basename(src),
            "source_wtd":   wtd_src,
            "grid_mapping": "crs",
        },
        "area_gdw_km2": {
            "long_name":    "GDW area after land-use exclusion",
            "units":        "km2",
            "formula":      "f_gdw * pixel_area_km2",
            "scenario":     scen,
            "source_sat":   os.path.basename(src),
            "source_wtd":   wtd_src,
            "grid_mapping": "crs",
            "note":         "pixel area from cellsize05min.nc (m2 / 1e6 → km2)",
        },
        "lat": {
            "standard_name": "latitude",
            "units":         "degrees_north",
            "axis":          "Y",
            "long_name":     "latitude",
        },
        "lon": {
            "standard_name": "longitude",
            "units":         "degrees_east",
            "axis":          "X",
            "long_name":     "longitude",
        },
        "time": {
            "standard_name": "time",
            "axis":          "T",
            "long_name":     "time",
        },
    }


def build_encoding(sat_ref: xr.DataArray) -> dict:
    cm     = chunk_map(sat_ref, cfg.CHUNK_COARSE)
    chunks = tuple(max(1, cm.get(d, 1)) for d in ("time", "lat", "lon"))
    base   = {
        "zlib":       True,
        "complevel":  cfg.COMPLEVEL,
        "chunksizes": chunks,
        "dtype":      "f4",
        "_FillValue":  FGDW_FILL,
    }
    return {
        "f_gdw":        dict(base),
        "area_gdw_km2": dict(base),
        "time": {"zlib": True, "complevel": 1},
        "lat":  {"zlib": True, "complevel": 1},
        "lon":  {"zlib": True, "complevel": 1},
    }


def write_scenario(
    sat: xr.DataArray,
    wtd: xr.DataArray,
    lu,
    open_water_2d,
    pixel_area_2d,
    scen: str,
    out_path: str = None,
) -> None:
    """
    Top-level convenience function.
    Writes f_gdw and area_gdw_km2 NC for one scenario.
    """
    from .pipeline import run_pipeline

    os.makedirs(cfg.OUT_DIR, exist_ok=True)
    if out_path is None:
        out_path = os.path.join(cfg.OUT_DIR, f"wetGDE_paper3_{scen}_5arcmin_fgdw.nc")

    enc         = build_encoding(sat)
    global_attr = build_global_attrs(scen)
    var_attr    = build_var_attrs(scen)

    print(f"  [write] f_gdw + area_gdw_km2 → {out_path}")
    run_pipeline(
        sat=sat, wtd=wtd,
        lu=lu,
        open_water_2d=open_water_2d,
        pixel_area_2d=pixel_area_2d,
        scen=scen,
        out_path=out_path,
        enc=enc,
        global_attrs=global_attr,
        var_attrs=var_attr,
    )