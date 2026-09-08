#!/usr/bin/env python3
"""
run_process_model.py  --  entry point for process-based GDW model (Modules 2, 3, 5).

Runs dependency, loss, and uncertainty for each GCM x SSP combination
using PCR-GLOBWB ISIMIP3 diagnostic outputs.

Flow per GCM x SSP
------------------
  Module 2  dependency    GDI from Qcr (= -gwRecharge.clip(0)), actualET, precipitation
  Module 3  loss          structural + functional + recharge loss vs historical baseline

Final step (all GCMs x SSPs combined)
--------------------------------------
  Module 5  uncertainty   variance decomposition + stippling on GDI_use ensemble

Outputs written to:
  {OUT_NC_DIR}/process_model/{gcm}/{scenario}/
    gdi_{gcm}_{scenario}.nc            gdi_use, gdi_input, dry_season_gdi, gdi_trend
    loss_{gcm}_{scenario}.nc           structural, functional, recharge_loss_mm_yr
  {OUT_NC_DIR}/process_model/
    uncertainty_ensemble.nc            f_gcm, f_ssp, f_threshold, f_residual,
                                       robust_mask, time_of_emergence (optional)

Usage
-----
  # all GCMs x SSPs
  RUN_PROCESS_MODEL=1 python run_process_model.py

  # one GCM
  RUN_PROCESS_MODEL=1 GCM=gfdl-esm4 python run_process_model.py

  # one GCM x scenario
  RUN_PROCESS_MODEL=1 GCM=gfdl-esm4 SCENARIO=ssp370 python run_process_model.py

  # GDI only (skip loss and uncertainty)
  RUN_PROCESS_MODEL=1 RUN_GDI_ONLY=1 GCM=gfdl-esm4 SCENARIO=ssp370 python run_process_model.py

  # skip existing outputs
  RUN_PROCESS_MODEL=1 SKIP_EXISTING=1 python run_process_model.py

Environment variables
---------------------
  PCR_ISIMIP_ROOT   root of ISIMIP3 PCR outputs
                    default: /projects/2/managed_datasets/hypflowsci6_v1.0/output
  BASELINE_START    first year of historical baseline (default: 1995)
  BASELINE_END      last year of historical baseline  (default: 2014)
  GCM               filter to one GCM
  SCENARIO          filter to one scenario (ssp126/ssp370/ssp585 only;
                    historical is always loaded as the baseline)
  SKIP_EXISTING     skip jobs where output NC already exists (default: 1)
  WTD_THRESHOLD     WTD threshold [m] (default: 5.0)
  SAT_THRESHOLD     satAreaFrac threshold (default: 0.5)
  RUN_GDI_ONLY      run Module 2 only; skip loss and uncertainty (default: 0)
"""
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import dask
import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["RUN_PROCESS_MODEL"] = "1"
os.environ.setdefault("SKIP_EXISTING", "1")

# limit dask threads to cpus-per-task to avoid oversubscription on Snellius
dask.config.set({"num_workers": int(os.environ.get("SLURM_CPUS_PER_TASK", 4))})

GDI_ONLY = os.environ.get("RUN_GDI_ONLY", "0").strip() in ("1", "true", "yes")

from wetgde_model.config import get_config, Config
from wetgde_model.pcr_io import (
    open_all_gdi_inputs,
    open_gw_recharge,
)
from wetgde_model.dependency import ETA_MIN, INPUT_MIN, DRY_PERCENTILE
from wetgde_model.loss import detect_loss
from wetgde_model.uncertainty import run_uncertainty
from wetgde_model.io_utils import open_sat, open_wtd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# SSP scenarios only; historical is always used as baseline
SSP_SCENARIOS = ["ssp126", "ssp370", "ssp585"]


def write_gdi_incremental(
    inputs: dict,
    gdw_mask: xr.DataArray,
    out_path: str,
) -> None:
    """
    Compute and write GDI year by year to avoid OOM.

    Strategy:
      Pass 1: iterate over years, compute gdi_use and gdi_input for each year,
              write to NC immediately in append mode. Memory: ~1 GB peak per year.
      Pass 2: re-read gdi_use from the written file to compute diagnostics
              (dry_season_gdi and gdi_trend via OLS). Append to same file.

    Parameters
    ----------
    inputs   : dict from open_all_gdi_inputs (qcr, eta, p_net, gw_recharge)
    gdw_mask : bool DataArray (lat, lon)  historical GDW pixels
    out_path : str  output NC path
    """
    qcr   = inputs["qcr"]
    eta   = inputs["eta"]
    p_net = inputs["p_net"]

    times   = pd.DatetimeIndex(qcr["time"].values)
    years   = sorted(set(times.year))
    n_years = len(years)

    logger.info(
        "  write_gdi_incremental: %d years (%d-%d)  out=%s",
        n_years, years[0], years[-1], Path(out_path).name,
    )

    # ── Pass 1: gdi_use + gdi_input + qcr, one year at a time ────────────
    logger.info("  Pass 1: computing and writing %d years", n_years)
    t_pass1 = time.time()

    for i, year in enumerate(years):
        t_year = time.time()
        mask_y = qcr["time"].dt.year == year
        n_steps = int(mask_y.sum())

        logger.info(
            "  [%d/%d] year=%d  loading %d timesteps...",
            i + 1, n_years, year, n_steps,
        )

        # load one year eagerly
        t_load = time.time()
        qcr_y = qcr.sel(time=mask_y).load()
        eta_y = eta.sel(time=mask_y).load()
        p_y   = p_net.sel(time=mask_y).load()
        logger.info("    load done  %.1f s", time.time() - t_load)

        qcr_pos = qcr_y.clip(min=0.0)
        eta_pos = eta_y.clip(min=0.0)
        p_pos   = p_y.clip(min=0.0)

        gdi_use_y = xr.where(
            eta_pos > ETA_MIN,
            (qcr_pos / eta_pos.where(eta_pos > ETA_MIN, other=np.float32(1.0))).clip(0.0, 1.0),
            np.float32(0.0),
        ).astype("float32")
        gdi_use_y.name = "gdi_use"

        gdi_input_y = xr.where(
            (qcr_pos + p_pos) > INPUT_MIN,
            (qcr_pos / (qcr_pos + p_pos).where(
                (qcr_pos + p_pos) > INPUT_MIN, other=np.float32(1.0)
            )).clip(0.0, 1.0),
            np.float32(0.0),
        ).astype("float32")
        gdi_input_y.name = "gdi_input"

        qcr_y.name = "qcr"
        qcr_y.attrs = {
            "long_name": "Capillary rise (water balance residual)",
            "units":     "m/month",
        }

        logger.info(
            "    qcr  mean=%.6f  nonzero=%.3f",
            float(qcr_pos.mean()), float((qcr_pos > 0).mean()),
        )
        logger.info(
            "    gdi_use  mean=%.4f  gdi_input  mean=%.4f",
            float(gdi_use_y.mean()), float(gdi_input_y.mean()),
        )

        ds_y = xr.Dataset({
            "gdi_use":   gdi_use_y,
            "gdi_input": gdi_input_y,
            "qcr":       qcr_y,
        })

        t_write = time.time()
        mode = "w" if i == 0 else "a"
        ds_y.to_netcdf(out_path, mode=mode, unlimited_dims=["time"])
        logger.info(
            "    write done  %.1f s  (mode=%s)",
            time.time() - t_write, mode,
        )

        logger.info(
            "  [%d/%d] year=%d DONE  total=%.1f s",
            i + 1, n_years, year, time.time() - t_year,
        )

    logger.info("  Pass 1 complete  total=%.1f s", time.time() - t_pass1)

    # ── Pass 2: diagnostics from full gdi_use ─────────────────────────────
    logger.info("  Pass 2: computing dry_season_gdi and gdi_trend")
    t_pass2 = time.time()

    gdi_written  = xr.open_dataset(out_path, chunks={"time": 12, "lat": 180, "lon": 360})
    gdi_use_full = gdi_written["gdi_use"]
    logger.info(
        "  re-opened %s  shape=%s",
        Path(out_path).name, dict(gdi_use_full.sizes),
    )

    # dry-season GDI
    logger.info("  computing p_thresh (10th percentile)...")
    t_dry = time.time()
    p_thresh   = p_net.quantile(DRY_PERCENTILE / 100.0, dim="time").load()
    is_dry     = p_net < p_thresh
    dry_season = gdi_use_full.where(is_dry).mean("time").load().astype("float32")
    if gdw_mask is not None:
        dry_season = dry_season.where(gdw_mask)
    dry_season.name = "dry_season_gdi"
    dry_season.attrs = {
        "long_name": f"Mean GDI_use when P < {DRY_PERCENTILE}th percentile",
        "units":     "1",
    }
    logger.info(
        "  dry_season_gdi done  mean=%.4f  %.1f s",
        float(dry_season.mean(skipna=True)), time.time() - t_dry,
    )

    # OLS trend on annual-mean GDI
    logger.info("  computing OLS trend on annual-mean GDI...")
    t_trend    = time.time()
    gdi_annual = gdi_use_full.resample(time="1YE").mean()
    logger.info("  annual means computed: %d years", int(gdi_annual.sizes["time"]))
    trend = (
        gdi_annual.polyfit(dim="time", deg=1, skipna=True)
                  .sel(degree=1)["polyfit_coefficients"]
                  .astype("float32")
    ).load()
    trend.name = "gdi_trend"
    trend.attrs = {
        "long_name": "OLS slope of annual-mean GDI_use",
        "units":     "GDI/year",
        "note":      "Negative = groundwater subsidy declining.",
    }
    logger.info(
        "  gdi_trend done  negative_frac=%.3f  %.1f s",
        float((trend < 0).mean(skipna=True)), time.time() - t_trend,
    )

    gdi_written.close()

    # append 2D diagnostics
    xr.Dataset({"dry_season_gdi": dry_season, "gdi_trend": trend}).to_netcdf(
        out_path, mode="a"
    )
    logger.info(
        "  Pass 2 complete  diagnostics appended  %.1f s",
        time.time() - t_pass2,
    )


# ── per-GCM x SSP job ────────────────────────────────────────────────────────

def run_gcm_scenario(
    gcm: str,
    scenario: str,
    cfg: Config,
    sat_hist: xr.DataArray,
    wtd_hist: xr.DataArray,
    gw_recharge_hist: xr.DataArray,
) -> Optional[xr.DataArray]:
    """
    Run Modules 2-3 for one GCM x SSP pair.

    Parameters
    ----------
    gcm, scenario    : str
    cfg              : Config
    sat_hist         : historical satAreaFrac (already loaded by caller)
    wtd_hist         : historical WTD (already loaded by caller)
    gw_recharge_hist : historical gwRecharge (already loaded by caller)

    Returns
    -------
    gdi_use DataArray (time, lat, lon) for stacking into uncertainty ensemble,
    or None if job was skipped.
    """
    out_dir = Path(cfg.process_model_out_dir(gcm, scenario))
    skip    = cfg.skip_existing

    gdi_nc  = out_dir / f"gdi_{gcm}_{scenario}.nc"
    loss_nc = out_dir / f"loss_{gcm}_{scenario}.nc"

    if skip and gdi_nc.exists() and (GDI_ONLY or loss_nc.exists()):
        logger.info("SKIP (outputs exist): gcm=%s scenario=%s", gcm, scenario)
        return xr.open_dataset(str(gdi_nc))["gdi_use"]

    logger.info("=== START gcm=%s scenario=%s  GDI_ONLY=%s ===", gcm, scenario, GDI_ONLY)
    t0 = time.time()

    # ── load sat and WTD futures ───────────────────────────────────────────
    sat_fut = open_sat(cfg.gcm_sat_path(gcm, scenario))
    wtd_fut = open_wtd(cfg.wtd_path(gcm, scenario))

    # precompute WTD mean once to avoid recomputing per open_all_gdi_inputs call
    logger.info("  computing WTD mean: gcm=%s scenario=%s", gcm, scenario)
    wtd_fut_mean = wtd_fut.mean("time")
    logger.info("  WTD mean ready (lazy)")

    # inputs_fut only needed for Module 3 recharge loss
    inputs_fut = None
    if not GDI_ONLY:
        inputs_fut = open_all_gdi_inputs(
            gcm, scenario, root=cfg.pcr_isimip_root,
            start_year=2015, end_year=cfg.end_year,
            wtd_mean=wtd_fut_mean,
            wtd_thresh=cfg.wtd_threshold,
        )

    # ── Module 2: GDI ─────────────────────────────────────────────────────
    if not (skip and gdi_nc.exists()):
        logger.info("Module 2: GDI  gcm=%s scenario=%s", gcm, scenario)

        inputs_all = open_all_gdi_inputs(
            gcm, scenario,
            root=cfg.pcr_isimip_root,
            wtd_mean=wtd_fut_mean,
            wtd_thresh=cfg.wtd_threshold,
        )
        hist_gdw_mask = (
            (sat_hist.mean("time") > cfg.sat_threshold) &
            (wtd_hist.mean("time") <= cfg.wtd_threshold)
        )
        write_gdi_incremental(
            inputs=inputs_all,
            gdw_mask=hist_gdw_mask,
            out_path=str(gdi_nc),
        )
        logger.info("  written: %s", gdi_nc.name)
    else:
        logger.info("  SKIP GDI (exists)")

    # always read gdi_use from file for loss module
    gdi_ds = xr.open_dataset(str(gdi_nc))

    # ── Module 3: loss ────────────────────────────────────────────────────
    if not GDI_ONLY:
        if not (skip and loss_nc.exists()):
            logger.info("Module 3: loss  gcm=%s scenario=%s", gcm, scenario)

            wtd_hist_base = wtd_hist.sel(
                time=slice(str(cfg.baseline_start), str(cfg.baseline_end))
            ).mean("time")
            sat_hist_base = sat_hist.sel(
                time=slice(str(cfg.baseline_start), str(cfg.baseline_end))
            ).mean("time")

            fut_end      = cfg.end_year
            wtd_fut_end  = wtd_fut.sel(
                time=wtd_fut["time"].dt.year >= fut_end - 9
            ).mean("time")
            sat_fut_mean = sat_fut.sel(
                time=sat_fut["time"].dt.year >= fut_end - 9
            ).mean("time")

            gw_recharge_combined = xr.concat(
                [gw_recharge_hist, inputs_fut["gw_recharge"]], dim="time"
            )

            loss_ds = detect_loss(
                wtd_hist=wtd_hist_base,
                wtd_fut=wtd_fut_end,
                sat_hist=sat_hist_base,
                sat_fut=sat_fut_mean,
                gdi=gdi_ds["gdi_use"],
                gw_recharge=gw_recharge_combined,
                sat_thresh=cfg.sat_threshold,
                wtd_thresh=cfg.wtd_threshold,
            )
            loss_ds.to_netcdf(str(loss_nc))
            logger.info("  written: %s", loss_nc.name)
        else:
            logger.info("  SKIP loss (exists)")
    else:
        logger.info("  SKIP Module 3 (GDI_ONLY=1)")

    logger.info(
        "=== DONE gcm=%s scenario=%s  wall=%.1f s ===",
        gcm, scenario, time.time() - t0,
    )
    return gdi_ds["gdi_use"]


# ── uncertainty (all GCMs x SSPs combined) ───────────────────────────────────

def run_uncertainty_ensemble(
    gdi_collection: dict,
    cfg: Config,
    sat_thresholds: List[float],
    wtd_thresholds: List[float],
) -> None:
    """
    Stack GDI_use across GCMs x SSPs x thresholds and run Module 5.

    gdi_collection : dict  {(gcm, scenario): gdi_use DataArray}
    """
    out_path = Path(cfg.out_nc_dir) / "process_model" / "uncertainty_ensemble.nc"
    if cfg.skip_existing and out_path.exists():
        logger.info("SKIP uncertainty (exists): %s", out_path)
        return

    logger.info("Module 5: uncertainty  n_members=%d", len(gdi_collection))

    gcms  = sorted({k[0] for k in gdi_collection})
    ssps  = sorted({k[1] for k in gdi_collection})

    # build (gcm, ssp, time, lat, lon) DataArray from collected GDI
    gcm_arrays = []
    for gcm in gcms:
        ssp_arrays = []
        for ssp in ssps:
            if (gcm, ssp) not in gdi_collection:
                logger.warning("  missing GDI for gcm=%s ssp=%s; skipping", gcm, ssp)
                continue
            ssp_arrays.append(
                gdi_collection[(gcm, ssp)].expand_dims(ssp=[ssp])
            )
        if ssp_arrays:
            gcm_arrays.append(
                xr.concat(ssp_arrays, dim="ssp").expand_dims(gcm=[gcm])
            )

    if not gcm_arrays:
        logger.error("uncertainty: no GDI arrays collected; aborting")
        return

    da_base = xr.concat(gcm_arrays, dim="gcm")

    # expand threshold dimension using existing sensitivity thresholds
    thresh_arrays = []
    for i, (st, wt) in enumerate(
        [(st, wt) for st in sat_thresholds for wt in wtd_thresholds]
    ):
        thresh_arrays.append(da_base.expand_dims(threshold=[i]))
    da_full = xr.concat(thresh_arrays, dim="threshold")

    logger.info(
        "uncertainty: da shape = %s", dict(da_full.sizes)
    )

    unc_ds = run_uncertainty(
        da_full,
        baseline_period=cfg.baseline_period,
        spatial_decomp=False,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    unc_ds.to_netcdf(str(out_path))
    logger.info("uncertainty written: %s", out_path)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    cfg = get_config()
    cfg.validate()

    Path(cfg.log_dir).mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(
        Path(cfg.log_dir) / "process_model.log"
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    ))
    logging.getLogger().addHandler(fh)

    logger.info(
        "[%sZ] START run_process_model",
        datetime.utcnow().isoformat(timespec="seconds"),
    )
    logger.info(
        "  pcr_isimip_root : %s", cfg.pcr_isimip_root
    )
    logger.info(
        "  baseline        : %d-%d", cfg.baseline_start, cfg.baseline_end
    )

    # build job list
    gcms = [cfg.only_member] if cfg.only_member else cfg.gcms
    ssps = [cfg.only_scenario] if cfg.only_scenario else SSP_SCENARIOS

    # historical is always loaded as baseline; never run as a projection scenario
    if "historical" in ssps:
        logger.warning(
            "SCENARIO=historical is not a valid projection scenario and will be skipped. "
            "Historical data is loaded automatically as the baseline. "
            "Use SCENARIO=ssp126, ssp370, or ssp585."
        )
        ssps = [s for s in ssps if s != "historical"]
    if not ssps:
        logger.error("No valid SSP scenarios to run. Exiting.")
        return

    logger.info("  GCMs      : %s", gcms)
    logger.info("  scenarios : %s", ssps)

    gdi_collection = {}
    t_total = time.time()

    for gcm in gcms:
        # load historical inputs once per GCM (shared across all SSPs)
        logger.info("Loading historical inputs: gcm=%s", gcm)
        try:
            sat_hist = open_sat(cfg.gcm_sat_path(gcm, "historical"))
            sat_hist = sat_hist.sel(
                time=slice(str(cfg.baseline_start), str(cfg.baseline_end))
            )
            wtd_hist = open_wtd(cfg.wtd_path(gcm, "historical"))
            wtd_hist = wtd_hist.sel(
                time=slice(str(cfg.baseline_start), str(cfg.baseline_end))
            )
            gw_recharge_hist = (
                None if GDI_ONLY else
                open_gw_recharge(
                    gcm, "historical", root=cfg.pcr_isimip_root,
                    start_year=cfg.baseline_start, end_year=cfg.baseline_end,
                )
            )
        except Exception as e:
            logger.error("Failed to load historical inputs gcm=%s: %s", gcm, e)
            continue

        for ssp in ssps:
            try:
                gdi_use = run_gcm_scenario(
                    gcm=gcm,
                    scenario=ssp,
                    cfg=cfg,
                    sat_hist=sat_hist,
                    wtd_hist=wtd_hist,
                    gw_recharge_hist=gw_recharge_hist,
                )
                if gdi_use is not None:
                    gdi_collection[(gcm, ssp)] = gdi_use
            except Exception as e:
                logger.error(
                    "FAILED gcm=%s scenario=%s: %s", gcm, ssp, e, exc_info=True
                )

    # Module 5: uncertainty across full ensemble
    if GDI_ONLY:
        logger.info("Uncertainty skipped (GDI_ONLY=1)")
    elif len(gdi_collection) >= 2:
        try:
            run_uncertainty_ensemble(
                gdi_collection=gdi_collection,
                cfg=cfg,
                sat_thresholds=cfg.sensitivity_sat_thresholds,
                wtd_thresholds=cfg.sensitivity_wtd_thresholds,
            )
        except Exception as e:
            logger.error("uncertainty failed: %s", e, exc_info=True)
    else:
        logger.warning(
            "Uncertainty skipped: need >= 2 GCM x SSP results, got %d",
            len(gdi_collection),
        )

    logger.info(
        "[%sZ] DONE  wall=%.1f s",
        datetime.utcnow().isoformat(timespec="seconds"),
        time.time() - t_total,
    )


if __name__ == "__main__":
    main()