"""
writers.py  --  disk output for wetgde_model  (v3).

write_area_parquet_v3      atomic parquet with 4 area columns:
                             area_gdw_km2
                             area_gdw_nonlu_km2
                             area_gdw_freeze_lu_km2
                             area_gdw_freeze_wtd_km2
write_sensitivity_parquet  mean-area parquet for sensitivity runs
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

AREA_COLS = [
    "area_gdw_km2",
    "area_gdw_nonlu_km2",
    "area_gdw_freeze_lu_km2",
    "area_gdw_freeze_wtd_km2",
]


def _atomic_write(df: pd.DataFrame, out_path: str, codec: str) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(out) + ".tmp")
    if tmp.exists():
        try: tmp.unlink()
        except OSError: pass
    pq.write_table(
        pa.Table.from_pandas(df, preserve_index=False),
        str(tmp), compression=codec, use_dictionary=True,
    )
    os.replace(str(tmp), str(out))
    logger.info("Written parquet: %s  rows=%d  (%.2f MB)",
                out_path, len(df), out.stat().st_size / 1e6)


def write_area_parquet_v3(
    sums: Dict[str, np.ndarray],
    times_batch: pd.DatetimeIndex,
    code_to_label: Dict[int, str],
    n_codes: int,
    member: str,
    scenario: str,
    group_col: str,
    out_path: str,
    codec: str = "snappy",
    existing_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Write multi-column area parquet (v3).

    Parameters
    ----------
    sums : dict  key = area column name, value = np.ndarray (B, n_codes+1)
    """
    records = []
    for k, ts in enumerate(times_batch):
        for code in range(1, n_codes + 1):
            row = {
                "time":     ts,
                group_col:  code_to_label[code],
                "member":   member,
                "scenario": scenario,
            }
            any_nonzero = False
            for col in AREA_COLS:
                v = float(sums[col][k, code]) if col in sums else 0.0
                row[col] = v
                if v > 0.0:
                    any_nonzero = True
            if any_nonzero:
                records.append(row)

    if not records:
        return existing_df if existing_df is not None else pd.DataFrame()

    df = pd.DataFrame(records)
    df["time"] = pd.to_datetime(df["time"])
    for col in AREA_COLS:
        if col in df.columns:
            df[col] = df[col].astype("float64")
        else:
            df[col] = 0.0

    col_order = ["time", group_col, "member", "scenario"] + AREA_COLS
    df = df[[c for c in col_order if c in df.columns]]

    combined = (pd.concat([existing_df, df], ignore_index=True)
                if existing_df is not None else df)
    combined = combined.sort_values(["time", group_col]).reset_index(drop=True)
    _atomic_write(combined, out_path, codec)
    return combined


def write_sensitivity_parquet(
    records: List[dict],
    out_path: str,
    codec: str = "snappy",
) -> None:
    if not records:
        return
    df = pd.DataFrame(records)
    df["mean_area_km2"] = df["mean_area_km2"].astype("float64")
    df = df.sort_values(
        ["scenario", "sat_threshold", "wtd_threshold", "realm"]
    ).reset_index(drop=True)
    _atomic_write(df, out_path, codec)