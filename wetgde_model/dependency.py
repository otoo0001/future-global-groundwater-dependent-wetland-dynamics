"""
dependency.py  --  Groundwater Dependency Index (GDI) computation.

Approach: dry-season saturation persistence ratio.

    GDI = mean(satAreaFrac | P < P_q25) / mean(satAreaFrac | P > P_q75)

Rationale:
  - A pixel sustained by groundwater stays saturated even when rain stops.
  - A precipitation-driven pixel loses saturation during dry months.
  - GDI close to 1 → saturation independent of rain → groundwater-sustained.
  - GDI close to 0 → saturation collapses without rain → precipitation-driven.

This is more robust than correlation-based approaches because:
  - No lag ambiguity (dry/wet classification is threshold-based not lagged)
  - No seasonal confounding (we explicitly contrast dry vs wet season)
  - No WTD resolution mismatch (only uses satAreaFrac and P)
  - Interpretable: directly measures ecological GW dependency

Additional diagnostics:
  gdi_anomaly_corr  : 1 - corr(deseasonalised SAT anomaly, P anomaly)
                      Robust check: GDW pixels should show low anomaly correlation.
  gdi_trend         : OLS slope of annual-mean GDI [GDI/yr]
                      Negative = groundwater subsidy declining = functional loss signal.

All inputs are monthly (time, lat, lon) float32 DataArrays.
satAreaFrac is read from v3 GCM NCs (already computed in pipeline).
precipitation is read from PCR-GLOBWB via pcr_io.open_precipitation.

Usage
-----
    from wetgde_model.dependency import compute_gdi
    from wetgde_model.io_utils import open_sat
    from wetgde_model.pcr_io import open_precipitation

    sat = open_sat(cfg.gcm_sat_path(gcm, scenario))
    p   = open_precipitation(gcm, scenario)
    gdi_ds = compute_gdi(sat, p, gdw_mask=historical_mask)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

DRY_QUANTILE = 0.25   # bottom 25% precip months = dry
WET_QUANTILE = 0.75   # top 25% precip months = wet
SAT_MIN      = 1e-6   # guard for division


def compute_gdi(
    sat: xr.DataArray,
    p_net: xr.DataArray,
    gdw_mask: Optional[xr.DataArray] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> xr.Dataset:
    """
    Compute GDI and diagnostics from monthly satAreaFrac and precipitation.

    Parameters
    ----------
    sat      : DataArray (time, lat, lon)  satAreaFrac [0-1]
    p_net    : DataArray (time, lat, lon)  precipitation [m/month]
    gdw_mask : DataArray (lat, lon) bool   optional; restrict to GDW pixels
    start_year, end_year : int  optional year filter

    Returns
    -------
    xr.Dataset with:
      gdi            float32 (lat, lon)  dry-season persistence ratio
      gdi_dry        float32 (lat, lon)  mean sat in dry months
      gdi_wet        float32 (lat, lon)  mean sat in wet months
      gdi_anomaly    float32 (lat, lon)  1 - corr(SAT_anom, P_anom)
      gdi_trend      float32 (lat, lon)  OLS slope of annual GDI [GDI/yr]
    """
    # ── year filter ───────────────────────────────────────────────────────
    if start_year is not None:
        sat   = sat.sel(time=sat["time"].dt.year >= start_year)
        p_net = p_net.sel(time=p_net["time"].dt.year >= start_year)
    if end_year is not None:
        sat   = sat.sel(time=sat["time"].dt.year <= end_year)
        p_net = p_net.sel(time=p_net["time"].dt.year <= end_year)

    logger.info(
        "compute_gdi: n_timesteps=%d  start=%s  end=%s",
        int(sat.sizes.get("time", 0)),
        str(sat["time"].values[0])[:7] if sat.sizes.get("time",0)>0 else "?",
        str(sat["time"].values[-1])[:7] if sat.sizes.get("time",0)>0 else "?",
    )

    # ── align grids if needed ─────────────────────────────────────────────
    # sat is on 5-arcmin GCM grid; p_net is also 5-arcmin PCR grid
    # but may differ slightly in lat/lon — snap to sat grid
    if not (
        np.allclose(sat["lat"].values, p_net["lat"].values, atol=0.01) and
        np.allclose(sat["lon"].values, p_net["lon"].values, atol=0.01)
    ):
        logger.info("  regridding p_net to sat grid (nearest neighbour)")
        p_net = p_net.interp(lat=sat["lat"], lon=sat["lon"], method="nearest")

    # align time axis to intersection
    sat_times = set(sat["time"].values.tolist())
    p_times   = set(p_net["time"].values.tolist())
    common    = sorted(sat_times & p_times)
    if len(common) < len(sat["time"]):
        logger.warning(
            "  time mismatch: sat=%d  p=%d  common=%d — using intersection",
            sat.sizes["time"], p_net.sizes["time"], len(common),
        )
        sat   = sat.sel(time=common)
        p_net = p_net.sel(time=common)

    # ── dry / wet season thresholds ───────────────────────────────────────
    # compute per-pixel thresholds from climatology
    logger.info("  computing P quantile thresholds ...")
    p_q25 = p_net.quantile(DRY_QUANTILE, dim="time").compute()
    p_q75 = p_net.quantile(WET_QUANTILE, dim="time").compute()

    is_dry = p_net < p_q25   # bool (time, lat, lon)
    is_wet = p_net > p_q75

    # ── GDI: dry-season persistence ratio ────────────────────────────────
    logger.info("  computing dry-season mean SAT ...")
    gdi_dry = sat.where(is_dry).mean("time").compute().astype("float32")

    logger.info("  computing wet-season mean SAT ...")
    gdi_wet = sat.where(is_wet).mean("time").compute().astype("float32")

    # ratio: how much of wet-season saturation is preserved in dry season
    gdi = xr.where(
        gdi_wet > SAT_MIN,
        (gdi_dry / gdi_wet.where(gdi_wet > SAT_MIN, other=np.float32(1.0))).clip(0.0, 1.0),
        np.float32(0.0),
    ).astype("float32")

    if gdw_mask is not None:
        gdi     = gdi.where(gdw_mask)
        gdi_dry = gdi_dry.where(gdw_mask)
        gdi_wet = gdi_wet.where(gdw_mask)

    gdi.name = "gdi"
    gdi.attrs = {
        "long_name":   "Groundwater Dependency Index (dry-season persistence)",
        "formula":     "mean(SAT|P<P_q25) / mean(SAT|P>P_q75)",
        "units":       "1",
        "valid_range": "0.0, 1.0",
        "note": (
            "GDI=1: saturation fully maintained in dry season (groundwater-sustained). "
            "GDI=0: saturation collapses in dry season (precipitation-driven)."
        ),
    }
    gdi_dry.name = "gdi_dry"
    gdi_dry.attrs = {
        "long_name": "Mean satAreaFrac during dry months (P < 25th percentile)",
        "units": "1",
    }
    gdi_wet.name = "gdi_wet"
    gdi_wet.attrs = {
        "long_name": "Mean satAreaFrac during wet months (P > 75th percentile)",
        "units": "1",
    }

    # ── anomaly correlation (robustness check) ────────────────────────────
    logger.info("  computing anomaly correlation ...")
    gdi_anomaly = _anomaly_corr(sat, p_net, gdw_mask)

    # ── OLS trend on annual-mean GDI ─────────────────────────────────────
    logger.info("  computing GDI trend ...")
    gdi_trend = _gdi_trend(sat, p_net, gdw_mask)

    logger.info(
        "compute_gdi done: gdi_mean=%.4f  gdi_dry=%.4f  gdi_wet=%.4f",
        float(gdi.mean(skipna=True)),
        float(gdi_dry.mean(skipna=True)),
        float(gdi_wet.mean(skipna=True)),
    )

    return xr.Dataset({
        "gdi":        gdi,
        "gdi_dry":    gdi_dry,
        "gdi_wet":    gdi_wet,
        "gdi_anomaly": gdi_anomaly,
        "gdi_trend":  gdi_trend,
    })


def _anomaly_corr(
    sat: xr.DataArray,
    p_net: xr.DataArray,
    gdw_mask: Optional[xr.DataArray] = None,
) -> xr.DataArray:
    """
    1 - corr(deseasonalised SAT anomaly, P anomaly) per pixel.

    High value (→1) = SAT decoupled from P = groundwater-sustained.
    Low value (→0)  = SAT follows P = precipitation-driven.

    Deseasonalisation: subtract monthly climatology to remove seasonal cycle
    before correlating, avoiding seasonal confounding.
    """
    # monthly climatology
    sat_clim = sat.groupby("time.month").mean("time")
    p_clim   = p_net.groupby("time.month").mean("time")

    sat_anom = (sat.groupby("time.month") - sat_clim).astype("float32")
    p_anom   = (p_net.groupby("time.month") - p_clim).astype("float32")

    # pearson correlation per pixel
    n    = sat_anom.sizes["time"]
    mean_s = sat_anom.mean("time")
    mean_p = p_anom.mean("time")
    cov    = ((sat_anom - mean_s) * (p_anom - mean_p)).mean("time")
    std_s  = sat_anom.std("time")
    std_p  = p_anom.std("time")
    corr   = (cov / (std_s * std_p + 1e-9)).clip(-1.0, 1.0)

    # GDI anomaly: high = decoupled from P = GW-sustained
    out = (1.0 - corr).clip(0.0, 1.0).astype("float32").compute()

    if gdw_mask is not None:
        out = out.where(gdw_mask)

    out.name = "gdi_anomaly"
    out.attrs = {
        "long_name": "1 - corr(deseasonalised SAT anomaly, P anomaly)",
        "units":     "1",
        "note": (
            "Robustness check for GDI. High = SAT decoupled from P = GW-sustained. "
            "Low = SAT tracks P = precipitation-driven."
        ),
    }
    return out


def _gdi_trend(
    sat: xr.DataArray,
    p_net: xr.DataArray,
    gdw_mask: Optional[xr.DataArray] = None,
) -> xr.DataArray:
    """
    OLS slope of annual-mean GDI [GDI/yr].
    Computed year by year to avoid loading all data at once.
    Negative slope = groundwater subsidy declining = functional loss signal.
    """
    # compute annual GDI by year
    years = sorted(set(int(y) for y in sat["time"].dt.year.values))

    p_q25 = p_net.quantile(DRY_QUANTILE, dim="time").compute()
    p_q75 = p_net.quantile(WET_QUANTILE, dim="time").compute()

    annual_gdis = []
    for yr in years:
        sat_y = sat.sel(time=sat["time"].dt.year == yr).compute()
        p_y   = p_net.sel(time=p_net["time"].dt.year == yr).compute()
        dry_y = sat_y.where(p_y < p_q25).mean("time")
        wet_y = sat_y.where(p_y > p_q75).mean("time")
        gdi_y = xr.where(wet_y > SAT_MIN,
                         (dry_y / wet_y.where(wet_y > SAT_MIN, other=np.float32(1.0))).clip(0,1),
                         np.float32(0.0)).astype("float32")
        annual_gdis.append(gdi_y.expand_dims(year=[yr]))

    gdi_ann = xr.concat(annual_gdis, dim="year").astype("float32")

    trend = (
        gdi_ann.polyfit(dim="year", deg=1, skipna=True)
               .sel(degree=1)["polyfit_coefficients"]
               .astype("float32")
               .compute()
    )

    if gdw_mask is not None:
        trend = trend.where(gdw_mask)

    trend.name = "gdi_trend"
    trend.attrs = {
        "long_name": "OLS slope of annual-mean GDI [GDI/yr]",
        "units":     "GDI/year",
        "note":      "Negative = groundwater subsidy declining = functional loss.",
    }
    return trend


def compute_gdi_incremental(
    sat: xr.DataArray,
    p_net: xr.DataArray,
    out_path: str,
    gdw_mask: Optional[xr.DataArray] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> None:
    """
    Compute GDI and write to NC incrementally (year by year).
    Avoids loading full time series into memory.

    Writes:
      Pass 1: annual GDI per year → NC
      Pass 2: diagnostics (gdi_dry, gdi_wet, gdi_anomaly, gdi_trend) → NC
    """
    import time as _time
    from pathlib import Path

    if start_year is not None:
        sat   = sat.sel(time=sat["time"].dt.year >= start_year)
        p_net = p_net.sel(time=p_net["time"].dt.year >= start_year)
    if end_year is not None:
        sat   = sat.sel(time=sat["time"].dt.year <= end_year)
        p_net = p_net.sel(time=p_net["time"].dt.year <= end_year)

    # align grids
    if not (
        np.allclose(sat["lat"].values, p_net["lat"].values, atol=0.01) and
        np.allclose(sat["lon"].values, p_net["lon"].values, atol=0.01)
    ):
        logger.info("  regridding p_net to sat grid")
        p_net = p_net.interp(lat=sat["lat"], lon=sat["lon"], method="nearest")

    # compute P thresholds once from full period
    logger.info("  computing P quantile thresholds (full period) ...")
    t0 = _time.time()
    p_q25 = p_net.quantile(DRY_QUANTILE, dim="time").compute()
    p_q75 = p_net.quantile(WET_QUANTILE, dim="time").compute()
    logger.info("  P thresholds done  %.1f s", _time.time()-t0)

    years = sorted(set(int(y) for y in sat["time"].dt.year.values))
    n_yrs = len(years)
    logger.info("  Pass 1: annual GDI for %d years", n_yrs)

    annual_gdis = []
    for i, yr in enumerate(years):
        t_yr = _time.time()
        sat_y = sat.sel(time=sat["time"].dt.year==yr).compute()
        p_y   = p_net.sel(time=p_net["time"].dt.year==yr).compute()

        dry_y = sat_y.where(p_y < p_q25).mean("time").astype("float32")
        wet_y = sat_y.where(p_y > p_q75).mean("time").astype("float32")
        gdi_y = xr.where(wet_y > SAT_MIN,
                         (dry_y/wet_y.where(wet_y>SAT_MIN,other=np.float32(1.0))).clip(0,1),
                         np.float32(0.0)).astype("float32")
        gdi_y.name = "gdi"

        if gdw_mask is not None:
            gdi_y   = gdi_y.where(gdw_mask)
            dry_y   = dry_y.where(gdw_mask)
            wet_y   = wet_y.where(gdw_mask)

        annual_gdis.append(gdi_y.assign_coords(year=yr).expand_dims("year"))

        ds_y = xr.Dataset({
            "gdi":     gdi_y.expand_dims(year=[yr]),
            "gdi_dry": dry_y.expand_dims(year=[yr]),
            "gdi_wet": wet_y.expand_dims(year=[yr]),
        })
        mode = "w" if i==0 else "a"
        ds_y.to_netcdf(out_path, mode=mode, unlimited_dims=["year"])

        logger.info(
            "  [%d/%d] year=%d  gdi_mean=%.4f  %.1f s",
            i+1, n_yrs, yr, float(gdi_y.mean(skipna=True)), _time.time()-t_yr,
        )

    logger.info("  Pass 1 complete")

    # Pass 2: diagnostics
    logger.info("  Pass 2: diagnostics")

    # re-open annual GDI for trend
    gdi_ann = xr.concat(annual_gdis, dim="year")
    trend = (
        gdi_ann.polyfit(dim="year", deg=1, skipna=True)
               .sel(degree=1)["polyfit_coefficients"]
               .astype("float32").compute()
    )
    if gdw_mask is not None: trend = trend.where(gdw_mask)
    trend.name = "gdi_trend"
    trend.attrs = {"long_name":"OLS slope annual GDI","units":"GDI/year",
                   "note":"Negative = groundwater subsidy declining."}

    # anomaly correlation
    gdi_anomaly = _anomaly_corr(sat, p_net, gdw_mask)

    # period-mean GDI
    is_dry = p_net < p_q25
    is_wet = p_net > p_q75
    gdi_dry_all = sat.where(is_dry).mean("time").compute().astype("float32")
    gdi_wet_all = sat.where(is_wet).mean("time").compute().astype("float32")
    gdi_all = xr.where(gdi_wet_all>SAT_MIN,
                       (gdi_dry_all/gdi_wet_all.where(gdi_wet_all>SAT_MIN,
                        other=np.float32(1.0))).clip(0,1),
                       np.float32(0.0)).astype("float32")
    if gdw_mask is not None:
        gdi_all     = gdi_all.where(gdw_mask)
        gdi_dry_all = gdi_dry_all.where(gdw_mask)
        gdi_wet_all = gdi_wet_all.where(gdw_mask)

    gdi_all.name     = "gdi_period"
    gdi_dry_all.name = "gdi_dry_period"
    gdi_wet_all.name = "gdi_wet_period"

    xr.Dataset({
        "gdi_period":     gdi_all,
        "gdi_dry_period": gdi_dry_all,
        "gdi_wet_period": gdi_wet_all,
        "gdi_anomaly":    gdi_anomaly,
        "gdi_trend":      trend,
    }).to_netcdf(out_path, mode="a")

    logger.info("  Pass 2 complete  written: %s", Path(out_path).name)