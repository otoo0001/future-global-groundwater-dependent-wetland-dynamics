import numpy as np
import pandas as pd
from pathlib import Path
import os

BASE = Path(os.environ.get("WETGDE_OUTPUT_DIR", "./outputs/WetGDEs_fgdw_v3"))

GCMS = [
    "gfdl-esm4",
    "ipsl-cm6a-lr",
    "mpi-esm1-2-hr",
    "mri-esm2-0",
    "ukesm1-0-ll",
]

SCENARIOS = ["historical", "ssp126", "ssp370", "ssp585"]

for gcm in GCMS:
    for sc in SCENARIOS:
        pq = BASE / "gcms" / gcm / sc / "parquet" / f"wetGDE_area_{gcm}_{sc}.parquet"

        if not pq.exists():
            print(f"❌ MISSING: {gcm} {sc}")
            continue

        df = pd.read_parquet(pq)
        df["time"] = pd.to_datetime(df["time"])

        totals = df.groupby("time")["area_gdw_km2"].sum()

        print(f"\n{gcm:15s} {sc:10s}")
        print(f"  Months : {len(totals)}")
        print(f"  Groups : {df['BIOME_ID_REALM'].nunique()}")
        print(f"  First  : {totals.iloc[0]:,.0f} km²")
        print(f"  Mean   : {totals.mean():,.0f} km²")
        print(f"  Last   : {totals.iloc[-1]:,.0f} km²")

        if (df["area_gdw_km2"] < 0).any():
            print("  ❌ Negative areas found")
        else:
            print("  ✓ No negative areas")

print("\nFinished.")
