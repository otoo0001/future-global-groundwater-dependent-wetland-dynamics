#!/usr/bin/env python3
"""
run_combined.py  --  ensemble run entry point.

Delegates entirely to wetgde_model.pipeline.run_all with RUN_ENSEMBLE=1.

Flow:
  1. wetgde_mask.pipeline.run_pipeline  writes f_gdw NC per scenario
       f_gdw = satAreaFrac * is_gdw * (1 - f_conv)
       open-water → NaN  (on sat grid)
  2. _area_loop_from_nc  reads f_gdw NC, applies QA mask
       A_gdw,i = f_gdw,i * A_i
       parquet column: area_gdw_km2

Environment variables (same as wetgde_model/run.py):
  SCENARIO        filter to one scenario (default: all)
  FREEZE_LU       freeze LU at historical mean (default: 0)
  APPLY_LU_MASK   apply LU exclusion (default: 1)
  START_YEAR      first year to process (default: 1979)
  END_YEAR        last year to process (default: 2050)
  SKIP_EXISTING   skip existing NC/parquet (default: 1)
  WRITE_NC        write f_gdw NC (default: 1)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# force ensemble mode
os.environ["RUN_ENSEMBLE"] = "1"
os.environ["RUN_GCMS"]     = "0"
os.environ.setdefault("WRITE_NC",       "1")
os.environ.setdefault("SKIP_EXISTING",  "1")
os.environ.setdefault("APPLY_LU_MASK",  "1")
os.environ.setdefault("START_YEAR",     "1979")
os.environ.setdefault("END_YEAR",       "2050")

from wetgde_model.config import get_config
from wetgde_model.pipeline import run_all

if __name__ == "__main__":
    cfg = get_config()
    run_all(cfg)