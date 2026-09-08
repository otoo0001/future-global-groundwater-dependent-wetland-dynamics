#!/usr/bin/env python3
"""
Standalone diagnostic for the S10/S10b area inflation bug.
No dependency on the main plotting script at all -- everything needed
(paths, constants, aggregation logic) is inlined here. Safe to run from
any directory.

Run:
    python debug_s10_area_inflation_standalone.py
"""
from pathlib import Path
import pandas as pd

# =============================================================================
# PATHS AND CONSTANTS (copied from the main plotting script's config)
# =============================================================================

BASE      = Path("/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3")
GCMS_BASE = BASE / "gcms"

GCMS      = ["gfdl-esm4", "ipsl-cm6a-lr", "mpi-esm1-2-hr", "mri-esm2-0", "ukesm1-0-ll"]

COL_TOTAL = "area_gdw_km2"
COL_NONLU = "area_gdw_nonlu_km2"

MERGE_TO    = {"AA", "OC"}
MERGED_CODE = "AO"

# Which GCM/scenario to diagnose -- change these if you want to check others.
GCM = "gfdl-esm4"
SC  = "historical"


def parquet_path(gcm, sc):
    return GCMS_BASE / gcm / sc / "parquet" / f"wetGDE_area_{gcm}_{sc}.parquet"


# =============================================================================
# STEP 0: raw parquet
# =============================================================================

print("=" * 70)
print(f"STEP 0: raw parquet file for {GCM} / {SC}")
print("=" * 70)

p = parquet_path(GCM, SC)
print(f"Path: {p}")
print(f"Exists: {p.exists()}")

if not p.exists():
    print("File not found -- check GCM/scenario/path above and adjust if needed.")
    raise SystemExit(1)

raw = pd.read_parquet(p)
print(f"Raw shape: {raw.shape}")
print(f"Columns: {list(raw.columns)}")

has_bir  = "BIOME_ID_REALM" in raw.columns
has_time = "time" in raw.columns

print(f"Unique BIOME_ID_REALM: {raw['BIOME_ID_REALM'].nunique() if has_bir else 'N/A -- column missing'}")
print(f"Unique time values: {raw['time'].nunique() if has_time else 'N/A -- column missing'}")

if has_bir and has_time:
    print()
    print("Rows per (BIOME_ID_REALM, time) -- should be exactly 1 if no duplication:")
    dup_check = raw.groupby(["BIOME_ID_REALM", "time"]).size()
    print(dup_check.describe())
    print(f"Max rows for a single (BIOME_ID_REALM, time) pair: {dup_check.max()}")
    if dup_check.max() > 1:
        worst = dup_check.idxmax()
        print(f"[FLAG] Worst offender: BIOME_ID_REALM={worst[0]}, time={worst[1]} "
              f"has {dup_check.max()} duplicate rows")
        dup_rows = raw[(raw["BIOME_ID_REALM"] == worst[0]) & (raw["time"] == worst[1])]
        print(dup_rows[[COL_TOTAL]].describe())

# =============================================================================
# STEP 1: sum at a single timestamp, across all BIOME_ID_REALM
# =============================================================================

print()
print("=" * 70)
print(f"STEP 1: sum of {COL_TOTAL} at a single timestamp, across all BIOME_ID_REALM")
print("=" * 70)

if has_time:
    one_time = raw["time"].iloc[0]
    snap = raw[raw["time"] == one_time]
    print(f"Timestamp: {one_time}")
    print(f"Rows at this timestamp: {len(snap)}")
    print(f"Sum of {COL_TOTAL} at this timestamp "
          f"(should be roughly the global total GDW area, ~2,000,000 km2): "
          f"{snap[COL_TOTAL].sum():,.0f}")
    print(f"Mean of {COL_TOTAL} at this timestamp (per-row average): {snap[COL_TOTAL].mean():,.1f}")
else:
    print("No 'time' column -- cannot do a single-timestamp snapshot.")
    snap = raw

# =============================================================================
# STEP 2: biome_realm code collapsing (the AA/OC -> AO merge)
# =============================================================================

print()
print("=" * 70)
print("STEP 2: biome_realm code collapsing (AA/OC -> AO merge)")
print("=" * 70)

df = raw.copy()
if has_bir:
    parts = df["BIOME_ID_REALM"].astype(str).str.split("_", n=1, expand=True)
    df["biome_realm"] = parts[0] + "_" + parts[1].replace({r: MERGED_CODE for r in MERGE_TO})

    print(f"Unique biome_realm codes after merge: {df['biome_realm'].nunique()}")
    print(f"Unique original BIOME_ID_REALM codes: {df['BIOME_ID_REALM'].nunique()}")

    mapping = df.groupby("biome_realm")["BIOME_ID_REALM"].nunique().sort_values(ascending=False)
    multi = mapping[mapping > 1]
    print()
    print("biome_realm codes with >1 original BIOME_ID_REALM mapped to them")
    print("(these are the only candidates for double counting via the AA/OC merge):")
    if multi.empty:
        print("  (none -- the AA/OC merge is not the source of inflation)")
    else:
        print(multi)

    if has_time:
        snap2 = df[df["time"] == one_time]
        print()
        print(f"Sum of {COL_TOTAL} at this timestamp after biome_realm relabeling: "
              f"{snap2[COL_TOTAL].sum():,.0f}")
        print(f"(should match STEP 1's sum: {snap[COL_TOTAL].sum():,.0f})")
else:
    print("No 'BIOME_ID_REALM' column -- cannot check merge behavior.")

# =============================================================================
# STEP 3: the actual groupby(...).mean() aggregation used in the pipeline
# =============================================================================

print()
print("=" * 70)
print("STEP 3: through groupby(['biome_realm','time']).mean() (as used in")
print("        annual_biome_realm_from_parquet)")
print("=" * 70)

if has_bir and has_time:
    mmm = df.groupby(["biome_realm", "time"], as_index=False)[[COL_TOTAL]].mean()
    snap3 = mmm[mmm["time"] == one_time]
    print(f"Sum of {COL_TOTAL} after groupby+mean (by biome_realm,time): {snap3[COL_TOTAL].sum():,.0f}")
    print(f"Number of biome_realm rows at this timestamp: {len(snap3)} "
          f"(should equal unique biome_realm count: {df['biome_realm'].nunique()})")

    print()
    print("Per-biome_realm breakdown at this timestamp, sorted by area (largest first):")
    print(snap3.sort_values(COL_TOTAL, ascending=False).to_string(index=False))
else:
    print("Skipped -- missing required columns.")

print()
print("=" * 70)
print("INTERPRETATION")
print("=" * 70)
print("If STEP 1's sum is already far above ~2,000,000 km2, the raw parquet")
print("itself contains inflated/duplicated data (upstream of this script).")
print()
print("If STEP 1 looks reasonable but STEP 3 is inflated, the bug is in the")
print("biome_realm groupby+mean step: multiple original BIOME_ID_REALM rows")
print("are being averaged instead of summed, silently discarding area.")
print()
print("If a single biome_realm dominates the STEP 3 breakdown with an")
print("implausibly large value (tens of millions of km2), check whether that")
print("code corresponds to a merged AA/OC catch-all bucket, or whether many")
print("BIOME_ID_REALM sub-codes were folded into it.")