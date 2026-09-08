#!/usr/bin/env python3
"""
run_wetgde_paper3.py  --  entry point for Paper 3 wetGDE mask pipeline.

Runs one or all scenarios. Each scenario writes one NetCDF file year by year:
  {OUT_DIR}/wetGDE_paper3_{scenario}_5arcmin.nc

Usage
-----
# all scenarios
python scripts/run_wetgde_paper3.py

# one scenario
SCENARIO=ssp370 python scripts/run_wetgde_paper3.py

# small regional test
SMALL_TEST=1 REGION=amazon SCENARIO=historical python scripts/run_wetgde_paper3.py

# start from a specific year (skip earlier timesteps)
START_YEAR=2015 SCENARIO=ssp370 python scripts/run_wetgde_paper3.py
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wetgde_mask import config as cfg
from wetgde_mask.io import open_sat, open_wtd
from wetgde_mask.writer import write_scenario


def main():
    scens = [cfg.ONLY_SCEN] if cfg.ONLY_SCEN else cfg.SCENARIOS

    print(f"[{datetime.utcnow().isoformat(timespec='seconds')}Z] START")
    print(f"  scenarios : {scens}")
    print(f"  OUT_DIR   : {cfg.OUT_DIR}")
    print(f"  SMALL_TEST: {cfg.SMALL_TEST}  REGION: {cfg.REGION_NAME if cfg.SMALL_TEST else 'full_global'}")

    t0 = time.time()

    for scen in scens:
        print(f"\n[{datetime.utcnow().isoformat(timespec='seconds')}Z] === {scen} ===")
        try:
            sat = open_sat(scen)
            wtd = open_wtd(scen, sat)
            write_scenario(sat, wtd, scen)
        except Exception as e:
            print(f"[ERROR] {scen}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n[{datetime.utcnow().isoformat(timespec='seconds')}Z] DONE  wall={time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
