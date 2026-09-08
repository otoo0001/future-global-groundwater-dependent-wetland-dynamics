#!/usr/bin/env python3
"""
run.py  --  entry point for the wetGDE per-member pipeline.

Set any combination of run flags:

    RUN_ENSEMBLE=1                              ensemble only
    RUN_GCMS=1                                  all 5 GCMs only
    RUN_SENSITIVITY=1                           threshold sensitivity only
    RUN_ENSEMBLE=1 RUN_GCMS=1                  ensemble + all GCMs
    RUN_ENSEMBLE=1 RUN_SENSITIVITY=1           ensemble + sensitivity
    RUN_ENSEMBLE=1 RUN_GCMS=1 RUN_SENSITIVITY=1  everything

Filter to one scenario or GCM:
    RUN_GCMS=1 GCM=gfdl-esm4 SCENARIO=ssp370 python run.py

Custom sensitivity thresholds and window:
    RUN_SENSITIVITY=1 SAT_THRESHOLDS=0.25,0.5,0.75 WTD_THRESHOLDS=3.0,5.0 python run.py
    RUN_SENSITIVITY=1 SENS_AGG_YEARS=10 SENS_HIST_END_YEAR=2014 SENS_FUT_END_YEAR=2050 python run.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wetgde_model.config import get_config
from wetgde_model.pipeline import run_all

if __name__ == "__main__":
    cfg = get_config()
    run_all(cfg)