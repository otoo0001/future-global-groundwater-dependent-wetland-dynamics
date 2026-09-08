"""
uncertainty.py  --  projection uncertainty quantification.

Two components required for Nature Water submission:

1. Variance decomposition  (Hawkins & Sutton 2009, BAMS 90:1095)
   Partitions total projection variance into fractional contributions:
     f_gcm        GCM structural uncertainty     (5 members)
     f_ssp        Scenario uncertainty           (ssp126, ssp370, ssp585)
     f_threshold  Threshold sensitivity          (25 combinations)
     f_residual   Residual (internal variability proxy)

   Run as a time series so the dominant uncertainty source at each lead
   time is visible: GCM + residual dominate early, SSP dominates after ~2040.

2. Spatial robustness / stippling  (IPCC AR6 convention)
   Pixels where >= 80% of GCMs agree on the sign of change are robust.
   Remaining pixels are stippled on projection maps.

Input DataArray expected dimensions:
  gcm        GCM name (5 values)
  ssp        scenario string
  threshold  threshold combination index (0-24)
  time       annual or monthly timesteps
  lat, lon   spatial (optional for global decomposition)

Usage
-----
    from wetgde_model.uncertainty import decompose_variance, compute_stippling
    from wetgde_model.uncertainty import time_of_emergence, run_uncertainty

    # global decomposition (fast, for time-series figure)
    vd = decompose_variance(da, spatial=False)

    # spatial stippling per SSP
    stipple = compute_stippling(da.median("threshold"), reference=da_baseline)

    # time of emergence
    toe = time_of_emergence(da.median(["ssp","threshold"]), ("1995","2014"))

    # all in one
    ds = run_uncertainty(da, baseline_period=("1995","2014"))
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

AGREEMENT_THRESHOLD = 0.8   # fraction of GCMs for "robust" designation

DIM_GCM   = "gcm"
DIM_SSP   = "ssp"
DIM_THRESH = "threshold"
DIM_TIME  = "time"


def decompose_variance(
    da: xr.DataArray,
    spatial: bool = False,
    gcm_dim: str = DIM_GCM,
    ssp_dim: str = DIM_SSP,
    thresh_dim: str = DIM_THRESH,
) -> xr.Dataset:
    """
    Hawkins-Sutton variance decomposition.

    Parameters
    ----------
    da         : DataArray with dims (gcm, ssp, threshold, time, [lat, lon])
                 Values should already be anomalies relative to a baseline,
                 or raw projected values if baseline is removed elsewhere.
    spatial    : bool
                 False (default): spatially average first, then decompose.
                                  Fast; produces (time,) output for figures.
                 True:            decompose per pixel. Slow; for spatial maps.
    gcm_dim, ssp_dim, thresh_dim : str  dimension names

    Returns
    -------
    xr.Dataset with:
      f_gcm        float32 (time, [lat, lon])
      f_ssp        float32 (time, [lat, lon])
      f_threshold  float32 (time, [lat, lon])
      f_residual   float32 (time, [lat, lon])
      var_total    float32 (time, [lat, lon])
    """
    logger.info("decompose_variance: spatial=%s", spatial)

    if not spatial and "lat" in da.dims and "lon" in da.dims:
        da = da.mean(["lat", "lon"])

    var_gcm    = da.var(dim=gcm_dim).mean([ssp_dim, thresh_dim])
    var_ssp    = da.var(dim=ssp_dim).mean([gcm_dim, thresh_dim])
    var_thresh = da.var(dim=thresh_dim).mean([gcm_dim, ssp_dim])
    var_total  = da.var(dim=[gcm_dim, ssp_dim, thresh_dim])

    var_residual = (var_total - var_gcm - var_ssp - var_thresh).clip(min=0.0)
    safe_total   = var_total.where(var_total > 0)

    f_gcm    = (var_gcm    / safe_total).clip(0.0, 1.0).astype("float32")
    f_ssp    = (var_ssp    / safe_total).clip(0.0, 1.0).astype("float32")
    f_thresh = (var_thresh / safe_total).clip(0.0, 1.0).astype("float32")
    f_resid  = (var_residual / safe_total).clip(0.0, 1.0).astype("float32")

    # normalise to sum exactly to 1
    total_f = (f_gcm + f_ssp + f_thresh + f_resid).where(lambda x: x > 0, other=1.0)
    f_gcm    = (f_gcm    / total_f).astype("float32")
    f_ssp    = (f_ssp    / total_f).astype("float32")
    f_thresh = (f_thresh / total_f).astype("float32")
    f_resid  = (f_resid  / total_f).astype("float32")

    try:
        last = {DIM_TIME: -1} if DIM_TIME in f_gcm.dims else {}
        logger.info(
            "decompose_variance (last timestep): "
            "GCM=%.2f  SSP=%.2f  threshold=%.2f  residual=%.2f",
            float(f_gcm.isel(**last).mean()),
            float(f_ssp.isel(**last).mean()),
            float(f_thresh.isel(**last).mean()),
            float(f_resid.isel(**last).mean()),
        )
    except Exception:
        pass

    attrs_base = {"units": "1", "reference": "Hawkins & Sutton (2009) BAMS 90:1095"}
    f_gcm.name    = "f_gcm";    f_gcm.attrs    = {**attrs_base, "long_name": "Fractional GCM variance"}
    f_ssp.name    = "f_ssp";    f_ssp.attrs    = {**attrs_base, "long_name": "Fractional SSP variance"}
    f_thresh.name = "f_threshold"; f_thresh.attrs = {**attrs_base, "long_name": "Fractional threshold variance"}
    f_resid.name  = "f_residual";  f_resid.attrs  = {**attrs_base, "long_name": "Fractional residual variance (internal variability proxy)"}

    return xr.Dataset({
        "f_gcm":       f_gcm,
        "f_ssp":       f_ssp,
        "f_threshold": f_thresh,
        "f_residual":  f_resid,
        "var_total":   var_total.astype("float32"),
    })


def compute_stippling(
    da: xr.DataArray,
    reference: Optional[xr.DataArray] = None,
    agreement_threshold: float = AGREEMENT_THRESHOLD,
    gcm_dim: str = DIM_GCM,
) -> xr.DataArray:
    """
    IPCC AR6 stippling: fraction of GCMs agreeing on sign of change.

    Parameters
    ----------
    da                  : DataArray (gcm, [time], lat, lon)
                          Future-period values or already the change signal.
    reference           : DataArray ([time], lat, lon) optional baseline.
                          Change = da.mean(time) - reference.mean(time).
    agreement_threshold : float  default 0.8

    Returns
    -------
    bool DataArray (lat, lon):
      True  = robust (stipple NOT needed on map)
      False = uncertain (stipple on map)
    """
    signal = da.mean("time") if "time" in da.dims else da
    if reference is not None:
        ref    = reference.mean("time") if "time" in reference.dims else reference
        signal = signal - ref

    sign       = xr.where(signal > 0, 1, xr.where(signal < 0, -1, 0))
    med_sign   = sign.median(dim=gcm_dim)
    agree      = sign == xr.where(med_sign >= 0, 1, -1)
    frac_agree = agree.mean(dim=gcm_dim).astype("float32")

    robust = (frac_agree >= agreement_threshold).astype(bool)
    robust.name = "robust_mask"
    robust.attrs = {
        "long_name":            "Spatial robustness mask",
        "convention":           "IPCC AR6",
        "agreement_threshold":  agreement_threshold,
        "definition": (
            f"True where >= {int(agreement_threshold*100)}% of GCMs agree on "
            "sign of change. False pixels should be stippled on projection maps."
        ),
    }
    logger.info(
        "compute_stippling: robust=%.1f%%  agreement_threshold=%.2f",
        100.0 * float(robust.mean()), agreement_threshold,
    )
    return robust


def time_of_emergence(
    da: xr.DataArray,
    baseline_period: Tuple[str, str],
    snr_threshold: float = 2.0,
    gcm_dim: str = DIM_GCM,
) -> xr.DataArray:
    """
    Year when ensemble-mean anomaly first exceeds snr_threshold * baseline sigma.

    Parameters
    ----------
    da               : DataArray (gcm, time, [lat, lon])
    baseline_period  : ("YYYY", "YYYY") inclusive year strings
    snr_threshold    : float  default 2.0

    Returns
    -------
    float32 DataArray (lat, lon): year of emergence. NaN = never emerges.
    """
    base_slice = da.sel(time=slice(*baseline_period))
    baseline   = base_slice.mean([gcm_dim, "time"])
    noise      = base_slice.std([gcm_dim, "time"])

    signal  = da.mean(gcm_dim) - baseline
    emerged = signal.abs() / noise.where(noise > 0) >= snr_threshold

    years = np.array(
        [int(str(t)[:4]) for t in da["time"].values], dtype=np.float32
    )

    def _first(e: np.ndarray) -> float:
        idx = np.argmax(e)
        return float(years[idx]) if e[idx] else np.nan

    toe = xr.apply_ufunc(
        _first, emerged,
        input_core_dims=[["time"]],
        vectorize=True,
        dask="parallelized",
        output_dtypes=["float32"],
    ).astype("float32")

    toe.name = "time_of_emergence"
    toe.attrs = {
        "long_name":     "Time of emergence (year)",
        "units":         "year",
        "snr_threshold": snr_threshold,
        "baseline":      f"{baseline_period[0]}-{baseline_period[1]}",
        "note":          "NaN where signal does not emerge within projection period.",
    }
    logger.info(
        "time_of_emergence: median=%.0f  fraction_emerged=%.2f",
        float(toe.median(skipna=True)), float(toe.notnull().mean()),
    )
    return toe


def run_uncertainty(
    da: xr.DataArray,
    baseline_period: Optional[Tuple[str, str]] = None,
    agreement_threshold: float = AGREEMENT_THRESHOLD,
    spatial_decomp: bool = False,
) -> xr.Dataset:
    """
    Run variance decomposition, stippling, and optionally ToE.

    Parameters
    ----------
    da               : DataArray (gcm, ssp, threshold, time, lat, lon)
    baseline_period  : optional ("YYYY","YYYY") for ToE
    agreement_threshold : float
    spatial_decomp   : bool

    Returns
    -------
    xr.Dataset with f_gcm, f_ssp, f_threshold, f_residual, var_total,
    robust_mask per SSP, and optionally time_of_emergence.
    """
    ds = decompose_variance(da, spatial=spatial_decomp)

    # stippling: collapse threshold dim, then per SSP
    da_no_thresh = da.median(dim=DIM_THRESH)
    stipple_list = []
    for ssp in da_no_thresh[DIM_SSP].values:
        mask = compute_stippling(
            da_no_thresh.sel(**{DIM_SSP: ssp}),
            agreement_threshold=agreement_threshold,
        ).expand_dims(**{DIM_SSP: [ssp]})
        stipple_list.append(mask.to_dataset(name="robust_mask"))
    ds = xr.merge([ds] + stipple_list)

    if baseline_period is not None:
        toe = time_of_emergence(
            da.median([DIM_SSP, DIM_THRESH]), baseline_period
        )
        ds["time_of_emergence"] = toe

    return ds