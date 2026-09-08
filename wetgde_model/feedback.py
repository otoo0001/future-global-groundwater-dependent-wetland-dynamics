"""
feedback.py  --  recharge wetland loss to downstream WTD feedback.

Propagates recharge wetland loss (from loss.py) to downstream WTD deepening
and flags GDW pixels at elevated risk as a consequence.

Feedback pathway:
  1. Recharge wetland dries under SSP forcing
  2. Downward gwRecharge flux to aquifer declines
  3. Catchment-aggregated recharge deficit accumulates over projection window
  4. WTD deepens: delta_WTD [m] = cumulative_deficit_m / specific_yield
  5. GDW pixels where WTD_current + delta_WTD > WTD_threshold are flagged

Aquifer storage coefficient:
  The preferred source is GLOBGM specific yield output. If unavailable,
  storGroundwater from PCR-GLOBWB can be used to estimate specific yield
  as delta_S / delta_WTD over the historical period. Falls back to
  DEFAULT_STORAGE_COEFF = 0.1 if neither is possible.

  Request GLOBGM specific yield from Edwin before finalising Module 4.

Caveat: delta_WTD is a linear first-order estimate. Full propagation requires
transient GLOBGM re-runs with modified recharge boundary conditions.
State this explicitly as a limitation in Paper 3.

Usage
-----
    from wetgde_model.feedback import compute_feedback, estimate_storage_coeff
    from wetgde_model.pcr_io import open_stor_groundwater

    # optional: estimate S_y from storGroundwater + WTD
    stor_gw = open_stor_groundwater(gcm, "historical")
    s_y = estimate_storage_coeff(stor_gw, wtd_hist)

    fb = compute_feedback(
        recharge_loss=loss_ds.recharge_loss_mm_yr,
        wtd_current=wtd_fut_mean,
        catchment_mask=catchment_raster,
        storage_coeff=s_y,
        wtd_thresh=5.0,
        projection_years=35,
    )
    # fb.delta_wtd_m, fb.at_risk_gdw, fb.catchment_deficit_mm
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_COEFF = 0.1    # dimensionless; conservative unconfined aquifer
MIN_DEFICIT_MM_YR     = 1.0    # below this, delta_WTD is negligible


def compute_feedback(
    recharge_loss: xr.DataArray,
    wtd_current: xr.DataArray,
    catchment_mask: xr.DataArray,
    storage_coeff: Optional[xr.DataArray] = None,
    wtd_thresh: float = 5.0,
    projection_years: int = 35,
) -> xr.Dataset:
    """
    Compute first-order WTD deepening from upstream recharge wetland loss.

    Parameters
    ----------
    recharge_loss    : DataArray (lat, lon)  recharge flux loss [mm/yr]
                       From loss.detect_loss output (recharge_loss_mm_yr).
    wtd_current      : DataArray (lat, lon)  current WTD [m]
    catchment_mask   : DataArray (lat, lon)  integer catchment ID per pixel.
                       Use HydroBASINS level 5-7 rasterised to 5 arcmin.
    storage_coeff    : DataArray (lat, lon)  specific yield [-], optional.
                       Use estimate_storage_coeff or GLOBGM output.
                       If None, uses DEFAULT_STORAGE_COEFF uniformly.
    wtd_thresh       : float  WTD threshold [m]
    projection_years : int    years of deficit accumulation; default 35 (2015-2050)

    Returns
    -------
    xr.Dataset with:
      delta_wtd_m          float32 (lat, lon)  WTD deepening [m]
      at_risk_gdw          bool    (lat, lon)  pixels crossing threshold
      catchment_deficit_mm float32 (lat, lon)  upstream deficit [mm]
    """
    logger.info(
        "compute_feedback: projection_years=%d  wtd_thresh=%.1f",
        projection_years, wtd_thresh,
    )

    if storage_coeff is None:
        logger.warning(
            "compute_feedback: storage_coeff not provided. "
            "Using DEFAULT_STORAGE_COEFF=%.2f. "
            "Preferred: GLOBGM specific yield (request from Edwin) "
            "or estimate_storage_coeff(storGroundwater, wtd).",
            DEFAULT_STORAGE_COEFF,
        )
        sy = xr.full_like(recharge_loss, DEFAULT_STORAGE_COEFF, dtype="float32")
    else:
        sy = storage_coeff.clip(min=1e-4).astype("float32")

    # aggregate recharge loss per catchment
    catchment_deficit = _aggregate_per_catchment(recharge_loss, catchment_mask)

    # accumulated deficit over projection window [mm]
    total_deficit_mm = (
        catchment_deficit.where(catchment_deficit > MIN_DEFICIT_MM_YR, other=0.0)
        * projection_years
    ).astype("float32")
    total_deficit_mm.name = "catchment_deficit_mm"
    total_deficit_mm.attrs = {
        "long_name": (
            f"Cumulative upstream recharge deficit over {projection_years} years"
        ),
        "units": "mm",
    }

    # WTD deepening: deficit_m / specific_yield
    delta_wtd = (total_deficit_mm / 1000.0 / sy).astype("float32")
    delta_wtd.name = "delta_wtd_m"
    delta_wtd.attrs = {
        "long_name": "First-order WTD deepening from upstream recharge loss",
        "units":     "m",
        "formula":   "cumulative_recharge_deficit_m / specific_yield",
        "caveat": (
            "Linear first-order estimate. Full propagation requires transient "
            "GLOBGM re-runs with modified recharge boundary conditions."
        ),
    }

    # at-risk GDW pixels
    wtd_projected = wtd_current + delta_wtd
    at_risk = (
        wtd_current.notnull() &
        (wtd_current <= wtd_thresh) &
        (wtd_projected > wtd_thresh)
    ).astype(bool)
    at_risk.name = "at_risk_gdw"
    at_risk.attrs = {
        "long_name": "GDW pixels at risk from upstream recharge loss",
        "definition": (
            f"Current WTD <= {wtd_thresh}m but "
            f"WTD + delta_WTD > {wtd_thresh}m."
        ),
    }

    logger.info(
        "compute_feedback done: delta_wtd mean=%.3f m  at_risk pixels=%d",
        float(delta_wtd.mean()), int(at_risk.sum()),
    )

    return xr.Dataset({
        "delta_wtd_m":          delta_wtd,
        "at_risk_gdw":          at_risk,
        "catchment_deficit_mm": total_deficit_mm,
    })


def estimate_storage_coeff(
    stor_groundwater: xr.DataArray,
    wtd: xr.DataArray,
    min_sy: float = 0.01,
    max_sy: float = 0.4,
) -> xr.DataArray:
    """
    Estimate specific yield from PCR-GLOBWB storGroundwater and GLOBGM WTD.

    S_y = delta_S / delta_h

    Uses inter-annual variance: regresses storage change against WTD change
    over the historical period. Both inputs must cover the same time window.

    Parameters
    ----------
    stor_groundwater : DataArray (time, lat, lon)  storGroundwater [m, monthly-average]
                       From pcr_io.open_stor_groundwater.
    wtd              : DataArray (time, lat, lon)  WTD [m, monthly]
    min_sy, max_sy   : float  plausible range for clipping

    Returns
    -------
    float32 DataArray (lat, lon)  estimated specific yield [-]
    """
    delta_s = stor_groundwater.diff("time")
    delta_h = wtd.diff("time")

    # pixel-wise regression: S_y = cov(delta_s, delta_h) / var(delta_h)
    cov = (
        (delta_s - delta_s.mean("time")) * (delta_h - delta_h.mean("time"))
    ).mean("time")
    var_h = delta_h.var("time")

    sy = xr.where(var_h > 1e-8, (cov / var_h).clip(min_sy, max_sy), DEFAULT_STORAGE_COEFF)
    sy = sy.astype("float32")
    sy.name = "specific_yield"
    sy.attrs = {
        "long_name": "Estimated specific yield",
        "units":     "1",
        "formula":   "cov(delta_storGW, delta_WTD) / var(delta_WTD)",
        "note":      (
            "First-order proxy. Preferred source is GLOBGM specific yield output. "
            f"Clipped to [{min_sy}, {max_sy}]."
        ),
    }
    logger.info(
        "estimate_storage_coeff: mean=%.3f  range=[%.3f, %.3f]",
        float(sy.mean()), float(sy.min()), float(sy.max()),
    )
    return sy


def _aggregate_per_catchment(
    recharge_loss: xr.DataArray,
    catchment_mask: xr.DataArray,
) -> xr.DataArray:
    """
    Sum recharge_loss over all pixels sharing the same catchment ID
    and assign the catchment total back to every pixel in that catchment.
    """
    loss_np  = recharge_loss.values.astype(np.float64)
    catch_np = catchment_mask.values.astype(np.int32)

    valid    = np.isfinite(loss_np) & (catch_np > 0)
    cat_ids  = catch_np[valid]
    loss_vals = loss_np[valid]

    n_cats  = int(cat_ids.max()) + 1 if len(cat_ids) > 0 else 1
    cat_sum = np.bincount(cat_ids, weights=loss_vals, minlength=n_cats)

    out = np.zeros_like(loss_np, dtype=np.float32)
    out[valid] = cat_sum[cat_ids].astype(np.float32)

    return xr.DataArray(out, coords=recharge_loss.coords, dims=recharge_loss.dims)