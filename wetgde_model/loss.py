"""
loss.py  --  wetland loss detection across three mechanisms.

Three loss types:

  structural   Binary threshold crossing.
               Pixels classified as GDW historically that no longer meet
               the satAreaFrac + WTD thresholds in the future period.

  functional   GDI decline within currently mapped GDW pixels.
               Negative Theil-Sen slope on GDI_use, even before the
               structural threshold is crossed. The wetland is losing its
               groundwater subsidy before disappearing from the mask.

  recharge     Decline in gwRecharge flux from recharge-type pixels.
               gwRecharge [m/month, monthly-total] is annualised to mm/yr.
               Loss = historical_mean - future_mean, clipped to >= 0.
               Feeds into feedback.py for downstream WTD propagation.

Paper 3 narrative:
  Under SSP3-7.0 and SSP5-8.5, X% of current GDW area faces committed
  structural loss by 2050. An additional Y% faces functional degradation
  without yet crossing the structural threshold: at-risk wetlands invisible
  to extent-based metrics, where loss of groundwater subsidy precedes
  structural disappearance potentially by decades.

Usage
-----
    from wetgde_model.loss import detect_loss
    from wetgde_model.pcr_io import open_gw_recharge

    gw_recharge = open_gw_recharge(gcm, scenario)
    loss_ds = detect_loss(
        wtd_hist, wtd_fut, sat_hist, sat_fut,
        gdi=gdi_ds.gdi_use,
        gw_recharge=gw_recharge,
    )
    # loss_ds.structural, loss_ds.functional, loss_ds.recharge_loss_mm_yr
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

# Theil-Sen slope below which a pixel is functionally degrading [GDI/yr]
FUNCTIONAL_SLOPE_THRESHOLD = -0.002


def detect_loss(
    wtd_hist: xr.DataArray,
    wtd_fut: xr.DataArray,
    sat_hist: xr.DataArray,
    sat_fut: xr.DataArray,
    gdi: Optional[xr.DataArray] = None,
    gw_recharge: Optional[xr.DataArray] = None,
    sat_thresh: float = 0.5,
    wtd_thresh: float = 5.0,
    functional_slope_thresh: float = FUNCTIONAL_SLOPE_THRESHOLD,
) -> xr.Dataset:
    """
    Detect structural, functional, and recharge loss.

    Parameters
    ----------
    wtd_hist, wtd_fut    : DataArray (time, lat, lon) or (lat, lon)
                           If 3D, period mean is used for masking.
    sat_hist, sat_fut    : DataArray matching wtd shapes.
    gdi                  : DataArray (time, lat, lon) monthly GDI_use.
                           Output of dependency.compute_gdi. Required for
                           functional loss. If None, functional = all False.
    gw_recharge          : DataArray (time, lat, lon) gwRecharge [m/month].
                           From pcr_io.open_gw_recharge. Required for
                           recharge loss. If None, recharge_loss = 0.
    sat_thresh           : float
    wtd_thresh           : float
    functional_slope_thresh : float  Theil-Sen threshold [GDI/yr]

    Returns
    -------
    xr.Dataset with:
      historical_mask   bool    (lat, lon)
      structural        bool    (lat, lon)
      functional        bool    (lat, lon)
      recharge_loss_mm_yr float32 (lat, lon)
      combined_at_risk  bool    (lat, lon)  structural OR functional
    """
    logger.info(
        "detect_loss: sat_thresh=%.2f  wtd_thresh=%.1f  "
        "func_slope_thresh=%.4f",
        sat_thresh, wtd_thresh, functional_slope_thresh,
    )

    wtd_h = _tmean(wtd_hist)
    wtd_f = _tmean(wtd_fut)
    sat_h = _tmean(sat_hist)
    sat_f = _tmean(sat_fut)

    hist_mask = _gdw_mask(sat_h, wtd_h, sat_thresh, wtd_thresh)
    fut_mask  = _gdw_mask(sat_f, wtd_f, sat_thresh, wtd_thresh)

    # structural
    structural = (hist_mask & ~fut_mask).astype(bool)
    structural.name = "structural"
    structural.attrs = {
        "long_name":  "Structural wetland loss",
        "definition": (
            f"GDW in historical (satAreaFrac>{sat_thresh}, WTD<{wtd_thresh}m) "
            "that no longer meets thresholds in future period."
        ),
    }

    # functional
    if gdi is not None:
        functional = _functional_loss(
            gdi, hist_mask, structural, functional_slope_thresh
        )
    else:
        logger.warning(
            "detect_loss: gdi not provided; functional loss = all False. "
            "Pass dependency.compute_gdi output to enable."
        )
        functional = xr.zeros_like(structural)
    functional.name = "functional"
    functional.attrs = {
        "long_name":  "Functional wetland loss (GDI declining)",
        "definition": (
            "Current GDW pixel with Theil-Sen GDI_use slope < "
            f"{functional_slope_thresh:.4f} GDI/yr; not yet structurally lost."
        ),
    }

    # recharge
    if gw_recharge is not None:
        recharge_loss = _recharge_loss(gw_recharge, sat_h, sat_thresh)
    else:
        logger.warning(
            "detect_loss: gw_recharge not provided; recharge_loss = 0. "
            "Pass pcr_io.open_gw_recharge output to enable."
        )
        recharge_loss = xr.zeros_like(sat_h, dtype="float32")
    recharge_loss.name = "recharge_loss_mm_yr"
    recharge_loss.attrs = {
        "long_name": "Recharge flux loss from recharge-type wetland pixels",
        "units":     "mm/yr",
        "definition": (
            "Decline in mean annual downward gwRecharge flux between "
            "historical and future periods for recharge-type pixels. "
            "Positive = loss of recharge. Feeds into feedback.py."
        ),
    }

    combined = (structural | functional).astype(bool)
    combined.name = "combined_at_risk"
    combined.attrs = {"long_name": "Combined at-risk pixels (structural OR functional)"}

    n_hist = int(hist_mask.sum())
    logger.info(
        "detect_loss done: hist_GDW=%d  structural=%d (%.1f%%)  "
        "functional=%d (%.1f%%)  combined=%d (%.1f%%)",
        n_hist,
        int(structural.sum()), 100.0 * int(structural.sum()) / max(n_hist, 1),
        int(functional.sum()), 100.0 * int(functional.sum()) / max(n_hist, 1),
        int(combined.sum()),   100.0 * int(combined.sum())   / max(n_hist, 1),
    )

    return xr.Dataset({
        "historical_mask":     hist_mask,
        "structural":          structural,
        "functional":          functional,
        "recharge_loss_mm_yr": recharge_loss,
        "combined_at_risk":    combined,
    })


def detect_loss_sensitivity(
    wtd_hist: xr.DataArray,
    wtd_fut: xr.DataArray,
    sat_hist: xr.DataArray,
    sat_fut: xr.DataArray,
    sat_thresholds: list,
    wtd_thresholds: list,
    gdi: Optional[xr.DataArray] = None,
    gw_recharge: Optional[xr.DataArray] = None,
) -> xr.Dataset:
    """
    Run detect_loss across the 25-combination threshold grid.
    Returns Dataset with dims (sat_thresh, wtd_thresh, lat, lon).
    """
    results = []
    for st in sat_thresholds:
        for wt in wtd_thresholds:
            ds = detect_loss(
                wtd_hist, wtd_fut, sat_hist, sat_fut,
                gdi=gdi, gw_recharge=gw_recharge,
                sat_thresh=st, wtd_thresh=wt,
            )
            results.append(ds.expand_dims(sat_thresh=[st], wtd_thresh=[wt]))
    return xr.combine_by_coords(results)


def _tmean(da: xr.DataArray) -> xr.DataArray:
    return da.mean("time") if "time" in da.dims else da


def _gdw_mask(
    sat: xr.DataArray,
    wtd: xr.DataArray,
    sat_thresh: float,
    wtd_thresh: float,
) -> xr.DataArray:
    valid = sat.notnull() & wtd.notnull()
    return (valid & (sat > sat_thresh) & (wtd <= wtd_thresh)).astype(bool)


def _functional_loss(
    gdi: xr.DataArray,
    hist_mask: xr.DataArray,
    structural: xr.DataArray,
    slope_thresh: float,
) -> xr.DataArray:
    from .dependency import _theil_sen_slope
    slope = _theil_sen_slope(gdi.resample(time="1YE").mean(), dim="time")
    return (
        hist_mask & ~structural & slope.notnull() & (slope < slope_thresh)
    ).astype(bool)


def _recharge_loss(
    gw_recharge: xr.DataArray,
    sat: xr.DataArray,
    sat_thresh: float,
) -> xr.DataArray:
    """
    Decline in downward gwRecharge flux for recharge-type pixels.
    gwRecharge is monthly-total [m/month]; annualise to mm/yr.
    Recharge pixels = wet AND gwRecharge > 0 in the long-term mean.
    """
    # recharge-type pixels: wet and net downward flux in historical mean
    is_recharge = (sat > sat_thresh) & (gw_recharge.mean("time") > 0)

    n     = int(gw_recharge.sizes["time"])
    mid   = n // 2
    hist  = gw_recharge.isel(time=slice(None, mid)).mean("time")
    fut   = gw_recharge.isel(time=slice(mid, None)).mean("time")

    # m/month -> mm/yr: * 1000 mm/m * 12 months/yr
    loss_mm_yr = ((hist - fut) * 12.0 * 1000.0).clip(min=0.0).astype("float32")
    return loss_mm_yr.where(is_recharge, other=np.float32(0.0))