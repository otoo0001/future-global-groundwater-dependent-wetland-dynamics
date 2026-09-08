#!/usr/bin/env python3
from pathlib import Path
import math
import numpy as np
import pandas as pd
import xarray as xr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm, SymLogNorm, ListedColormap, BoundaryNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import geopandas as gpd
import cartopy.crs as ccrs
import cartopy.feature as cfeature

try:
    import cmocean
    # curl gives the desired convention here: negative = red/brown, positive = blue.
    CMAP_DIVERGING = cmocean.cm.curl
except ImportError:
    CMAP_DIVERGING = plt.get_cmap("RdBu")

# =============================================================================
# PATHS
# =============================================================================

BASE = Path("/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3")
ENSEMBLE = BASE / "ensemble"
GCMS_BASE = BASE / "gcms"
OUT = BASE / "plots" / "manuscript_figures"
WWF_SHAPE = "/path/to/scratch/paper_3/inputs/biomes/biomes/wwf_terr_ecos.shp"

OUT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# SETTINGS
# =============================================================================

GCMS = ["gfdl-esm4", "ipsl-cm6a-lr", "mpi-esm1-2-hr", "mri-esm2-0", "ukesm1-0-ll"]
SCENARIOS = ["historical", "ssp126", "ssp370", "ssp585"]
FUTURE_S = ["ssp126", "ssp370", "ssp585"]

COL_TOTAL = "area_gdw_km2"
COL_NONLU = "area_gdw_nonlu_km2"
COL_GW_ONLY = "area_gdw_freeze_lu_km2"
COL_LU_ONLY = "area_gdw_freeze_wtd_km2"

PCR_COLS = {
    "Groundwater Impact Only": COL_NONLU,
    "Land-use Impact Only": COL_LU_ONLY,
    "Groundwater + Land-use Impact": COL_TOTAL,
}
PCR_COLS_NORM = PCR_COLS.copy()

TS_VAR = COL_TOTAL
TS_AREA_VAR = COL_NONLU
PIXEL_VAR = COL_TOTAL

HIST_BASE = (1995, 2004)
HIST_LAST = (2005, 2014)
FUT_LAST = (2041, 2050)

JOIN_YEAR = 2015
SMOOTH_YEARS = 5
BASELINE_MIN = 0.01

PCR_VLIM = 15
ABS_PERCENTILE = 95

SCEN_COLOR = {
    "historical": "#333333",
    "ssp126": "#1a9850",
    "ssp370": "#fdae61",
    "ssp585": "#d73027",
}

SCEN_LABEL = {
    "historical": "Historical",
    "ssp126": "SSP1-2.6",
    "ssp370": "SSP3-7.0",
    "ssp585": "SSP5-8.5",
}

MERGE_TO = {"AA", "OC"}
MERGED_CODE = "AO"

REALM_NAME = {
    "AT": "Afrotropical",
    "IM": "Indo-Malayan",
    "NA": "Nearctic",
    "NT": "Neotropical",
    "PA": "Palearctic",
    MERGED_CODE: "Australasian & Oceanian",
}

REALM_ORDER = [
    "Nearctic",
    "Neotropical",
    "Afrotropical",
    "Palearctic",
    "Indo-Malayan",
    "Australasian & Oceanian",
]

PERSISTENCE_COLORS = {
    1: "#FFD92F",
    2: "#66BD3A",
    3: "#0571B0",
}

GAINLOSS_COLORS = {
    -2: "#5E2A84",
    -1: "#B28AC7",
    0: "#F0F0F0",
    1: "#66BD3A",
    2: "#1B7837",
}

TRANSITION_COLORS = {
    11: "#F7F7F7",
    12: "#FFE066",
    13: "#1ABC9C",
    21: "#F4A261",
    22: "#F7F7F7",
    23: "#2A9D8F",
    31: "#D7191C",
    32: "#92C5DE",
    33: "#F7F7F7",
}

# =============================================================================
# HELPERS
# =============================================================================

def log(msg):
    print(f"[{pd.Timestamp.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def smooth(s):
    return s.rolling(
        SMOOTH_YEARS,
        center=True,
        min_periods=max(1, SMOOTH_YEARS // 2),
    ).mean()


def normalize_realm_codes(s):
    x = s.astype(str).replace({r: MERGED_CODE for r in MERGE_TO})
    return x.map(REALM_NAME).fillna(x)


def period_for_scenario(scenario):
    return HIST_LAST if scenario == "historical" else FUT_LAST


def parquet_path(gcm, scenario):
    return GCMS_BASE / gcm / scenario / "parquet" / f"wetGDE_area_{gcm}_{scenario}.parquet"


def timmean_path(scenario):
    y1, y2 = period_for_scenario(scenario)
    return ENSEMBLE / scenario / "nc" / f"wetGDE_ensemble_timmean_{scenario}_{y1}-{y2}.nc"


def monthly_clim_path(scenario):
    y1, y2 = period_for_scenario(scenario)
    return ENSEMBLE / scenario / "nc" / f"wetGDE_ensemble_monthly_climatology_{scenario}_{y1}-{y2}.nc"


def add_map_background(ax):
    ax.set_global()
    ax.set_extent([-180, 180, -58, 90], crs=ccrs.PlateCarree())
    ax.add_feature(
        cfeature.LAND.with_scale("110m"),
        facecolor="#f5f5f2",
        edgecolor="none",
        zorder=0,
    )
    ax.coastlines(linewidth=0.25, color="0.45", zorder=3)
    ax.axis("off")


def classify_active_months(months):
    out = xr.full_like(months, np.nan, dtype="float32")
    out = out.where(~((months >= 1) & (months <= 3)), 1)
    out = out.where(~((months >= 4) & (months <= 6)), 2)
    out = out.where(~(months >= 7), 3)
    return out


def discrete_cmap_norm(value_color_map):
    values = sorted(value_color_map)
    colors = [value_color_map[v] for v in values]
    cmap = ListedColormap(colors)
    bounds = [values[0] - 0.5]
    bounds += [(values[i] + values[i + 1]) / 2 for i in range(len(values) - 1)]
    bounds += [values[-1] + 0.5]
    norm = BoundaryNorm(bounds, cmap.N)
    return cmap, norm


def format_plain_tick(x):
    if not np.isfinite(x):
        return ""
    x = float(x)
    if abs(x) >= 1:
        return f"{x:.1f}".rstrip("0").rstrip(".")
    return f"{x:.2f}".rstrip("0").rstrip(".")

# =============================================================================
# PARQUET
# =============================================================================

def extract_realm(df):
    d = df.copy()

    if "BIOME_ID_REALM" in d.columns:
        code = d["BIOME_ID_REALM"].astype(str).str.split("_", n=1).str[-1]
        d["realm"] = normalize_realm_codes(code)
    elif "realm" in d.columns:
        d["realm"] = normalize_realm_codes(d["realm"].astype(str))
    else:
        raise KeyError("No BIOME_ID_REALM or realm column found")

    return d[~d["realm"].isin(["AN", "Antarctica", "Antarctic"])].copy()


def load_parquet_all(cols):
    frames = []

    for gcm in GCMS:
        for sc in SCENARIOS:
            p = parquet_path(gcm, sc)
            if not p.exists():
                log(f"[missing parquet] {p}")
                continue

            df = pd.read_parquet(p)
            keep = [c for c in ["time", "BIOME_ID_REALM", "realm", "member"] + cols if c in df.columns]
            df = df[keep].copy()
            df["time"] = pd.to_datetime(df["time"])
            df["source"] = gcm
            df["scenario"] = sc
            df = extract_realm(df)

            if "member" not in df.columns:
                df["member"] = "member_0"

            missing = [col for col in cols if col not in df.columns]
            if missing:
                raise KeyError(f"Missing columns in {p}: {missing}")

            frames.append(df)

    if not frames:
        raise FileNotFoundError("No parquet files loaded")

    return pd.concat(frames, ignore_index=True)


def annual_realm_from_parquet(cols, keep_gcm=False):
    df = load_parquet_all(cols)

    if "BIOME_ID_REALM" not in df.columns:
        raise KeyError("BIOME_ID_REALM is needed to aggregate biome-realms correctly")

    area_cols = [c for c in cols if c.startswith("area_")]
    frac_cols = [c for c in cols if c.startswith("f_")]
    value_cols = area_cols + frac_cols

    monthly_biome = (
        df.groupby(["source", "scenario", "realm", "BIOME_ID_REALM", "time"], as_index=False)[value_cols]
        .mean()
    )

    parts = []
    if area_cols:
        parts.append(
            monthly_biome.groupby(["source", "scenario", "realm", "time"], as_index=False)[area_cols]
            .sum()
        )
    if frac_cols:
        parts.append(
            monthly_biome.groupby(["source", "scenario", "realm", "time"], as_index=False)[frac_cols]
            .mean()
        )

    if not parts:
        raise ValueError("No valid columns to aggregate")

    monthly = parts[0]
    for p in parts[1:]:
        monthly = monthly.merge(p, on=["source", "scenario", "realm", "time"], how="outer")

    monthly["year"] = monthly["time"].dt.year

    annual_gcm = (
        monthly.groupby(["source", "scenario", "realm", "year"], as_index=False)[value_cols]
        .mean()
    )

    if keep_gcm:
        return annual_gcm

    return annual_gcm.groupby(["scenario", "realm", "year"], as_index=False)[value_cols].mean()


def annual_biome_realm_from_parquet(cols):
    df = load_parquet_all(cols)

    if "BIOME_ID_REALM" not in df.columns:
        raise KeyError("BIOME_ID_REALM is needed for biome-realm map")

    parts = df["BIOME_ID_REALM"].astype(str).str.split("_", n=1, expand=True)
    df["biome_realm"] = parts[0] + "_" + parts[1].replace({r: MERGED_CODE for r in MERGE_TO})

    monthly_member_mean = (
        df.groupby(["source", "scenario", "biome_realm", "time"], as_index=False)[cols]
        .mean()
    )
    monthly_member_mean["year"] = monthly_member_mean["time"].dt.year

    annual_gcm = (
        monthly_member_mean.groupby(["source", "scenario", "biome_realm", "year"], as_index=False)[cols]
        .mean()
    )

    return annual_gcm.groupby(["scenario", "biome_realm", "year"], as_index=False)[cols].mean()

# =============================================================================
# SHAPEFILES
# =============================================================================

def load_biome_realm_gdf():
    gdf = gpd.read_file(WWF_SHAPE).to_crs("EPSG:4326")
    gdf = gdf[~gdf["REALM"].isin(["AN"])].copy()
    gdf["realm_code"] = gdf["REALM"].astype(str).replace({r: MERGED_CODE for r in MERGE_TO})
    gdf["biome_realm"] = gdf["BIOME"].astype(int).astype(str) + "_" + gdf["realm_code"]
    return gdf.dissolve(by="biome_realm", as_index=False, aggfunc="first")[["biome_realm", "geometry"]]

# =============================================================================
# REALM TIME SERIES
# =============================================================================

def plot_realm_ts_core(var, out_name, ylabel, transform=None):
    log(f"Loading yearly realm data for TS: {var}")
    df = annual_realm_from_parquet([var], keep_gcm=True)
    df["value_plot"] = df[var] if transform is None else transform(df[var])

    realms = [r for r in REALM_ORDER if r in set(df["realm"])]
    ncols = 3
    nrows = math.ceil(len(realms) / ncols)

    fig, axes = plt.subplots(nrows, ncols, figsize=(17, 8.5), dpi=300, sharex=True)
    axes = np.array(axes).reshape(nrows, ncols)

    for i, realm in enumerate(realms):
        log(f"Plotting TS realm: {realm}, var={var}")
        ax = axes[i // ncols, i % ncols]
        hist = df[(df["scenario"] == "historical") & (df["realm"] == realm) & (df["year"] <= 2014)].copy()
        hist_piv = hist.pivot_table(index="year", columns="source", values="value_plot", aggfunc="mean").sort_index()
        hist_mean = smooth(hist_piv.mean(axis=1))
        hist_low = smooth(hist_piv.min(axis=1))
        hist_high = smooth(hist_piv.max(axis=1))

        ax.fill_between(hist_mean.index, hist_low.values, hist_high.values, color=SCEN_COLOR["historical"], alpha=0.18, linewidth=0)
        ax.plot(hist_mean.index, hist_mean.values, color=SCEN_COLOR["historical"], lw=2.5)

        hist_clean = hist_mean.dropna()
        if hist_clean.empty:
            continue

        last_hist_year = int(hist_clean.index.max())
        last_hist_value = float(hist_clean.iloc[-1])

        for sc in FUTURE_S:
            d = df[(df["scenario"] == sc) & (df["realm"] == realm) & (df["year"] >= JOIN_YEAR)].copy()
            if d.empty:
                continue

            piv = d.pivot_table(index="year", columns="source", values="value_plot", aggfunc="mean").sort_index()
            mean_raw = piv.mean(axis=1)
            low_raw = piv.min(axis=1)
            high_raw = piv.max(axis=1)
            mean_raw_clean = mean_raw.dropna()
            if mean_raw_clean.empty:
                continue

            shift = last_hist_value - float(mean_raw_clean.iloc[0])
            mean = smooth(mean_raw + shift)
            low = smooth(low_raw + shift)
            high = smooth(high_raw + shift)

            low0 = float(hist_low.dropna().iloc[-1])
            high0 = float(hist_high.dropna().iloc[-1])
            shade_x = np.concatenate([[last_hist_year], mean.index.values])
            shade_low = np.concatenate([[low0], low.values])
            shade_high = np.concatenate([[high0], high.values])

            ax.fill_between(shade_x, shade_low, shade_high, color=SCEN_COLOR[sc], alpha=0.18, linewidth=0)
            mean_clean = mean.dropna()
            first_future_year = int(mean_clean.index.min())
            first_future_value = float(mean_clean.iloc[0])
            ax.plot([last_hist_year, first_future_year], [last_hist_value, first_future_value], color=SCEN_COLOR[sc], lw=2.5)
            ax.plot(mean.index, mean.values, color=SCEN_COLOR[sc], lw=2.5)

        ax.axvline(JOIN_YEAR, color="0.65", lw=1.2, ls=":")
        ax.set_title(realm, fontweight="bold")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)

    for j in range(len(realms), nrows * ncols):
        axes[j // ncols, j % ncols].set_visible(False)

    handles = [Line2D([0], [0], color=SCEN_COLOR[s], lw=3, label=SCEN_LABEL[s]) for s in SCENARIOS]
    fig.legend(handles=handles, frameon=False, ncol=4, loc="lower center")
    fig.tight_layout(rect=[0.02, 0.07, 0.98, 0.98])
    out = OUT / out_name
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log(f"Saved: {out}")


def plot_realm_ts():
    plot_realm_ts_core(TS_VAR, "realm_ts_area_gdw_gcm_shading.png", "Area(M km²)", transform=lambda s: s / 1e8)


def plot_realm_ts_nonlu_area():
    plot_realm_ts_core(TS_AREA_VAR, "realm_ts_no_land_use_area_gcm_shading.png", "Area(M km²)", transform=lambda s: s / 1e8)

# =============================================================================
# LOLLIPOP
# =============================================================================

def slope_km2_per_year(years, values):
    x = np.asarray(years, float)
    y = np.asarray(values, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 2:
        return np.nan
    m, _ = np.polyfit(x[ok], y[ok], 1)
    return float(m)


def plot_lollipop():
    log("Loading data for lollipop")
    df = annual_realm_from_parquet([COL_TOTAL, COL_NONLU], keep_gcm=False)
    rows = []
    for (sc, realm), g in df.groupby(["scenario", "realm"]):
        lo, hi = HIST_LAST if sc == "historical" else FUT_LAST
        d = g[(g["year"] >= lo) & (g["year"] <= hi)]
        rows.append({
            "scenario": sc,
            "realm": realm,
            "slope_total": slope_km2_per_year(d["year"], d[COL_TOTAL]),
            "slope_nonlu": slope_km2_per_year(d["year"], d[COL_NONLU]),
        })

    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "lollipop_total_vs_nonlu_slopes.csv", index=False)

    realms = [r for r in REALM_ORDER if r in set(tab["realm"])]
    y_base = np.arange(len(realms))[::-1]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), dpi=300)
    axes = axes.ravel()

    for ax, sc in zip(axes, SCENARIOS):
        d = tab[tab["scenario"] == sc].set_index("realm").reindex(realms)
        ax.axvline(0, color="0.65", lw=1)
        for yi, val in zip(y_base + 0.16, d["slope_total"] / 1000):
            if np.isfinite(val):
                c = "#2166ac" if val >= 0 else "#b2182b"
                ax.plot([0, val], [yi, yi], color=c, lw=2)
                ax.plot(val, yi, "o", color=c)
        for yi, val in zip(y_base - 0.16, d["slope_nonlu"] / 1000):
            if np.isfinite(val):
                c = "#2166ac" if val >= 0 else "#b2182b"
                ax.plot([0, val], [yi, yi], color=c, lw=2, ls="--")
                ax.plot(val, yi, "s", mfc="white", mec=c)
        ax.set_yticks(y_base)
        ax.set_yticklabels(realms)
        ax.set_title(SCEN_LABEL[sc], fontweight="bold")
        ax.set_xlabel("Trend (thousand km² yr⁻¹)")
        ax.grid(axis="x", alpha=0.25)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)

    fig.legend(handles=[
        Line2D([0], [0], color="0.3", marker="o", lw=2, label="GDW area with landuse change impact"),
        Line2D([0], [0], color="0.3", marker="s", mfc="white", lw=2, ls="--", label="GDW area without landuse change impact"),
        Line2D([0], [0], color="#2166ac", lw=2, label="Increasing"),
        Line2D([0], [0], color="#b2182b", lw=2, label="Declining"),
    ], frameon=False, ncol=4, loc="lower center")
    fig.tight_layout(rect=[0.02, 0.08, 0.98, 0.98])
    out = OUT / "lollipop_total_vs_nonlu_slopes.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log(f"Saved: {out}")

def plot_lollipop_decadal_change():
    log("Plotting decadal-change lollipop")

    df = annual_realm_from_parquet([COL_TOTAL, COL_NONLU], keep_gcm=False)
    rows = []

    for sc in SCENARIOS:
        if sc == "historical":
            base_lo, base_hi = HIST_BASE
            fut_lo, fut_hi = HIST_LAST
        else:
            base_lo, base_hi = HIST_LAST
            fut_lo, fut_hi = FUT_LAST

        d_base = df[
            df["scenario"].eq("historical")
            & df["year"].between(base_lo, base_hi)
        ]

        d_fut = df[
            df["scenario"].eq(sc)
            & df["year"].between(fut_lo, fut_hi)
        ]

        base = (
            d_base.groupby("realm", as_index=False)[[COL_TOTAL, COL_NONLU]]
            .mean()
        )

        fut = (
            d_fut.groupby("realm", as_index=False)[[COL_TOTAL, COL_NONLU]]
            .mean()
        )

        m = base.merge(
            fut,
            on="realm",
            suffixes=("_base", "_future"),
            how="outer",
        )

        m["scenario"] = sc
        m["base_period"] = f"{base_lo}-{base_hi}"
        m["future_period"] = f"{fut_lo}-{fut_hi}"

        m["delta_total_1000km2"] = (
            m[f"{COL_TOTAL}_future"] - m[f"{COL_TOTAL}_base"]
        ) / 1e5

        m["delta_nonlu_1000km2"] = (
            m[f"{COL_NONLU}_future"] - m[f"{COL_NONLU}_base"]
        ) / 1e5

        rows.append(m)

    tab = pd.concat(rows, ignore_index=True)

    tab.to_csv(
        OUT / "lollipop_total_vs_nonlu_decadal_change.csv",
        index=False,
    )

    realms = [r for r in REALM_ORDER if r in set(tab["realm"])]
    y_base = np.arange(len(realms))[::-1]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), dpi=300)
    axes = axes.ravel()

    for ax, sc in zip(axes, SCENARIOS):
        d = (
            tab[tab["scenario"] == sc]
            .set_index("realm")
            .reindex(realms)
        )

        ax.axvline(0, color="0.65", lw=1)

        for yi, v_total, v_nonlu in zip(
            y_base,
            d["delta_total_1000km2"],
            d["delta_nonlu_1000km2"],
        ):

            if np.isfinite(v_total):
                c_total = "#2166ac" if v_total >= 0 else "#b2182b"

                ax.plot(
                    [0, v_total],
                    [yi + 0.08, yi + 0.08],
                    color=c_total,
                    lw=2,
                    zorder=1,
                )

                ax.plot(
                    v_total,
                    yi + 0.08,
                    "o",
                    color=c_total,
                    zorder=2,
                )

            if np.isfinite(v_nonlu):
                c_nonlu = "#2166ac" if v_nonlu >= 0 else "#b2182b"

                ax.plot(
                    [0, v_nonlu],
                    [yi - 0.08, yi - 0.08],
                    color=c_nonlu,
                    lw=2,
                    ls="--",
                    zorder=1,
                )

                ax.plot(
                    v_nonlu,
                    yi - 0.08,
                    "s",
                    mfc="white",
                    mec=c_nonlu,
                    zorder=2,
                )

        ax.set_yticks(y_base)
        ax.set_yticklabels(realms)

        ax.set_title(SCEN_LABEL[sc], fontweight="bold")
        ax.set_xlabel("Change in GDW area (thousand km²)")
        ax.grid(axis="x", alpha=0.25)

        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)

    fig.legend(
        handles=[
            Line2D(
                [0], [0],
                color="0.3",
                marker="o",
                lw=2,
                label="Total GDW",
            ),
            Line2D(
                [0], [0],
                color="0.3",
                marker="s",
                mfc="white",
                lw=2,
                ls="--",
                label="GDW without land-use change impact",
            ),
            Line2D(
                [0], [0],
                color="#2166ac",
                lw=2,
                label="Gain",
            ),
            Line2D(
                [0], [0],
                color="#b2182b",
                lw=2,
                label="Loss",
            ),
        ],
        frameon=False,
        ncol=4,
        loc="lower center",
    )

    fig.tight_layout(rect=[0.02, 0.08, 0.98, 0.98])

    out = OUT / "lollipop_total_vs_nonlu_decadal_change.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)

    log(f"Saved: {out}")

def plot_lollipop_groundwater_vs_total_longterm_change():
    log("Plotting long-term groundwater-only vs total wetGDE change lollipop")

    table = compute_biome_realm_pcr_table()

    parts = table[
        table["component"].isin([
            "Groundwater Impact Only",
            "Groundwater + Land-use Impact",
        ])
    ].copy()

    parts["realm_code"] = (
        parts["biome_realm"]
        .astype(str)
        .str.split("_", n=1)
        .str[-1]
    )

    parts["realm"] = normalize_realm_codes(parts["realm_code"])

    tab = (
        parts.groupby(
            ["scenario", "realm", "component"],
            as_index=False
        )["abs_change_km2"]
        .sum()
    )

    wide = tab.pivot_table(
        index=["scenario", "realm"],
        columns="component",
        values="abs_change_km2",
        aggfunc="sum",
    ).reset_index()

    wide["delta_gw_1000km2"] = (
        wide["Groundwater Impact Only"] / 1000
    )

    wide["delta_total_1000km2"] = (
        wide["Groundwater + Land-use Impact"] / 1000
    )

    wide.to_csv(
        OUT / "lollipop_groundwater_vs_total_longterm_change.csv",
        index=False,
    )

    realms = [r for r in REALM_ORDER if r in set(wide["realm"])]
    y_base = np.arange(len(realms))[::-1]

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(12, 8),
        dpi=300,
    )

    axes = axes.ravel()

    for ax, sc in zip(axes, SCENARIOS):

        d = (
            wide[wide["scenario"] == sc]
            .set_index("realm")
            .reindex(realms)
        )

        ax.axvline(0, color="0.65", lw=1)

        for yi, v_gw, v_total in zip(
            y_base,
            d["delta_gw_1000km2"],
            d["delta_total_1000km2"],
        ):

            if np.isfinite(v_gw):

                c_gw = (
                    "#2166ac"
                    if v_gw >= 0
                    else "#b2182b"
                )

                ax.plot(
                    [0, v_gw],
                    [yi + 0.08, yi + 0.08],
                    color=c_gw,
                    lw=2,
                    zorder=1,
                )

                ax.plot(
                    v_gw,
                    yi + 0.08,
                    "o",
                    color=c_gw,
                    zorder=2,
                )

            if np.isfinite(v_total):

                c_total = (
                    "#2166ac"
                    if v_total >= 0
                    else "#b2182b"
                )

                ax.plot(
                    [0, v_total],
                    [yi - 0.08, yi - 0.08],
                    color=c_total,
                    lw=2,
                    ls="--",
                    zorder=1,
                )

                ax.plot(
                    v_total,
                    yi - 0.08,
                    "s",
                    mfc="white",
                    mec=c_total,
                    zorder=2,
                )

        ax.set_yticks(y_base)
        ax.set_yticklabels(realms)

        ax.set_title(
            SCEN_LABEL[sc],
            fontweight="bold"
        )

        ax.set_xlabel(
            "Change in GDW area (thousand km²)",    
        )

        ax.grid(axis="x", alpha=0.25)


        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)

    fig.legend(
        handles=[
            Line2D(
                [0], [0],
                color="0.3",
                marker="o",
                lw=2,
                label="Groundwater impact only",
            ),
            Line2D(
                [0], [0],
                color="0.3",
                marker="s",
                mfc="white",
                lw=2,
                ls="--",
                label="Groundwater + land-use impact",
            ),
            Line2D(
                [0], [0],
                color="#2166ac",
                lw=2,
                label="Gain",
            ),
            Line2D(
                [0], [0],
                color="#b2182b",
                lw=2,
                label="Loss",
            ),
        ],
        frameon=False,
        ncol=4,
        loc="lower center",
    )

    fig.tight_layout(rect=[0.02, 0.08, 0.98, 0.98])

    out = OUT / "lollipop_groundwater_vs_total_longterm_change.png"

    fig.savefig(
        out,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(fig)

    log(f"Saved: {out}")

# =============================================================================
# BIOME-REALM TABLES AND MAPS
# =============================================================================

def compute_biome_realm_pcr_table():
    log("Computing biome-realm PCR table")

    # Biome-realm polygon areas used for area-normalized change.
    gdf_area = load_biome_realm_gdf()
    gdf_area_eq = gdf_area.to_crs("ESRI:54009")
    gdf_area["biome_area_km2"] = gdf_area_eq.geometry.area / 1e6
    gdf_lookup = dict(zip(gdf_area["biome_realm"], gdf_area["biome_area_km2"]))

    cols = list(dict.fromkeys(list(PCR_COLS.values()) + [COL_TOTAL]))
    df = annual_biome_realm_from_parquet(cols)
    records = []
    base_hist = df[(df["scenario"] == "historical") & df["year"].between(*HIST_LAST)]
    base_old = df[(df["scenario"] == "historical") & df["year"].between(*HIST_BASE)]

    for sc in SCENARIOS:
        if sc == "historical":
            base_all = base_old
            fut_all = base_hist
        else:
            base_all = base_hist
            fut_all = df[(df["scenario"] == sc) & df["year"].between(*FUT_LAST)]

        for label, col in PCR_COLS.items():
            if col == COL_TOTAL:
                b = base_all.groupby("biome_realm", as_index=False)[COL_TOTAL].mean().rename(columns={COL_TOTAL: "base"})
                f = fut_all.groupby("biome_realm", as_index=False)[COL_TOTAL].mean().rename(columns={COL_TOTAL: "future"})
            else:
                b = base_all.groupby("biome_realm", as_index=False)[col].mean().rename(columns={col: "base"})
                f = fut_all.groupby("biome_realm", as_index=False)[col].mean().rename(columns={col: "future"})

            m = b.merge(f, on="biome_realm", how="outer")
            m["abs_change_km2"] = m["future"] - m["base"]
            # Normalize by biome-realm land area to make differently sized biome-realms comparable.
            biome_area = gdf_lookup.get(m["biome_realm"].iloc[0], np.nan)
            m["pct_change"] = np.where(
                biome_area > 0,
                m["abs_change_km2"] / biome_area * 100,
                np.nan,
            )

            # Keep self-normalized relative change as a separate metric.
            m["normalized_change_pct"] = np.where(
                m["base"] >= BASELINE_MIN,
                m["abs_change_km2"] / m["base"] * 100,
                np.nan,
            )
            m["scenario"] = sc
            m["component"] = label
            records.append(m)

    out = pd.concat(records, ignore_index=True)
    out.to_csv(OUT / "biome_realm_percent_change_gw_lu_both.csv", index=False)
    out.to_csv(OUT / "biome_realm_self_normalized_component_change_gw_lu_both.csv", index=False)
    return out


def load_biome_realm_gdf_checked(table):
    gdf = load_biome_realm_gdf()
    missing = sorted(set(gdf["biome_realm"]) - set(table["biome_realm"]))
    extra = sorted(set(table["biome_realm"]) - set(gdf["biome_realm"]))
    log(f"Missing in table: {missing[:20]} n={len(missing)}")
    log(f"Extra in table: {extra[:20]} n={len(extra)}")
    return gdf


def plot_biome_realm_map(table, value_col, out_png, colorbar_label, vlim, components=None):
    gdf = load_biome_realm_gdf_checked(table)
    scenarios = SCENARIOS
    if components is None:
        components = list(table["component"].dropna().unique())

    fig, axes = plt.subplots(
        len(scenarios),
        len(components),
        figsize=(5.8 * len(components), 11),
        dpi=300,
        subplot_kw={"projection": ccrs.Robinson()},
        gridspec_kw={"hspace": 0.04, "wspace": 0.02},
    )
    axes = np.array(axes).reshape(len(scenarios), len(components))
    norm = TwoSlopeNorm(vcenter=0, vmin=-vlim, vmax=vlim)

    for r, sc in enumerate(scenarios):
        for c, comp in enumerate(components):
            ax = axes[r, c]
            add_map_background(ax)
            d = table[(table["scenario"] == sc) & (table["component"] == comp)][["biome_realm", value_col]]
            plot_gdf = gdf.merge(d, on="biome_realm", how="left")
            plot_gdf.plot(
                column=value_col,
                ax=ax,
                transform=ccrs.PlateCarree(),
                cmap=CMAP_DIVERGING,
                norm=norm,
                linewidth=0.0,
                missing_kwds={"color": "white"},
                zorder=2,
            )
            if r == 0:
                ax.set_title(comp, fontsize=14, fontweight="bold")
            if c == 0:
                ax.text(-0.08, 0.5, SCEN_LABEL[sc], transform=ax.transAxes, rotation=90, va="center", ha="right", fontsize=14)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=CMAP_DIVERGING)
    cax = fig.add_axes([0.91, 0.18, 0.018, 0.65])
    cb = fig.colorbar(sm, cax=cax)
    cb.set_label(colorbar_label, fontsize=12)
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log(f"Saved: {out_png}")


def plot_biome_realm_pcr_maps():
    log("Plotting biome-realm PCR maps")
    table = compute_biome_realm_pcr_table()

    plot_biome_realm_map(
        table=table,
        value_col="pct_change",
        out_png=OUT / "biome_realm_percent_change_gw_lu_both_map.png",
        colorbar_label="% change ",
        vlim=PCR_VLIM,
        components=list(PCR_COLS.keys()),
    )

    norm_components = list(PCR_COLS_NORM.keys())
    plot_biome_realm_map(
        table=table[table["component"].isin(norm_components)].copy(),
        value_col="normalized_change_pct",
        out_png=OUT / "biome_realm_self_normalized_component_change_gw_lu_both_map.png",
        colorbar_label="% change",
        vlim=PCR_VLIM,
        components=norm_components,
    )

# =============================================================================
# REALM AREA CSV AND FRACTION PLOT
# =============================================================================

def save_realm_area_table():
    log("Saving realm GDW area table")
    df = annual_realm_from_parquet([COL_TOTAL, COL_NONLU], keep_gcm=False)
    rows = []
    for sc in SCENARIOS:
        lo, hi = HIST_LAST if sc == "historical" else FUT_LAST
        d = df[df["scenario"].eq(sc) & df["year"].between(lo, hi)]
        m = d.groupby("realm", as_index=False)[[COL_TOTAL, COL_NONLU]].mean()
        m["scenario"] = sc
        m["period"] = f"{lo}-{hi}"
        m["total_gdw_mkm2"] = m[COL_TOTAL] / 1e8
        m["no_land_use_gdw_mkm2"] = m[COL_NONLU] / 1e8
        m["land_use_difference_mkm2"] = (m[COL_TOTAL] - m[COL_NONLU]) / 1e8
        m["no_land_use_fraction_pct"] = np.where(m[COL_TOTAL] > 0, m[COL_NONLU] / m[COL_TOTAL] * 100, np.nan)
        rows.append(m[["scenario", "period", "realm", "total_gdw_mkm2", "no_land_use_gdw_mkm2", "land_use_difference_mkm2", "no_land_use_fraction_pct"]])
    out = pd.concat(rows, ignore_index=True)
    out["realm"] = pd.Categorical(out["realm"], categories=REALM_ORDER, ordered=True)
    out = out.sort_values(["scenario", "realm"])
    csv = OUT / "realm_gdw_area_total_vs_no_land_use.csv"
    out.to_csv(csv, index=False)
    log(f"Saved: {csv}")


# def plot_realm_nonlu_fraction():
#     log("Plotting no-land-use fraction")
#     tab = pd.read_csv(OUT / "realm_gdw_area_total_vs_no_land_use.csv")
#     fig, ax = plt.subplots(figsize=(11, 5.8), dpi=300)
#     x = np.arange(len(REALM_ORDER))
#     width = 0.2
#     for i, sc in enumerate(SCENARIOS):
#         dd = tab[tab["scenario"] == sc].set_index("realm").reindex(REALM_ORDER)
#         ax.bar(x + (i - 1.5) * width, dd["no_land_use_fraction_pct"], width=width, color=SCEN_COLOR[sc], label=SCEN_LABEL[sc])
#     ax.set_ylabel("No-land-use GDW as % of total GDW")
#     ax.set_xticks(x)
#     ax.set_xticklabels(REALM_ORDER, rotation=35, ha="right")
#     ax.set_ylim(0, 105)
#     ax.grid(axis="y", alpha=0.25)
#     ax.legend(frameon=False, ncol=4, loc="upper center")
#     for sp in ("top", "right"):
#         ax.spines[sp].set_visible(False)
#     fig.tight_layout()
#     out_png = OUT / "realm_no_land_use_fraction_of_total_gdw.png"
#     fig.savefig(out_png, dpi=300, bbox_inches="tight")
#     plt.close(fig)
#     log(f"Saved: {out_png}")

# =============================================================================
# PIXEL CHANGE MAPS
# =============================================================================

def open_timmean_da(scenario, var):
    path = timmean_path(scenario)
    if not path.exists():
        raise FileNotFoundError(path)
    ds = xr.open_dataset(path, decode_times=True, mask_and_scale=True)
    if var not in ds:
        raise KeyError(f"{var} missing in {path}")
    da = ds[var]
    if "time" in da.dims:
        da = da.isel(time=0)
    return da


def open_monthly_clim_da(scenario, var):
    path = monthly_clim_path(scenario)
    if not path.exists():
        raise FileNotFoundError(path)
    ds = xr.open_dataset(path, decode_times=True, mask_and_scale=True)
    if var not in ds:
        raise KeyError(f"{var} missing in {path}")
    return ds[var]

def plot_ssp370_pixel_pct_change():
    log("Plotting SSP370 pixel percent change")

    hist = open_timmean_da("historical", PIXEL_VAR)
    fut = open_timmean_da("ssp370", PIXEL_VAR)

    pct = xr.where(hist >= BASELINE_MIN, (fut - hist) / hist * 100, np.nan)
    pct = pct.where(np.abs(pct) >= 5)

    pct_np = pct.compute().values.astype("float32")
    lat = pct["lat"].values
    lon = pct["lon"].values

    pct.name = f"pct_change_{PIXEL_VAR}"
    pct.attrs["units"] = "%"

    pct.to_netcdf(
        OUT / f"ssp370_{PIXEL_VAR}_pixel_pct_change_2041-2050_vs_2005-2014.nc"
    )

    vals = np.abs(pct_np[np.isfinite(pct_np)])
    vlim = float(np.nanpercentile(vals, 95)) if vals.size else 100
    vlim = max(10, min(vlim, 100))

    norm = SymLogNorm(
        linthresh=5,
        linscale=1,
        vmin=-vlim,
        vmax=vlim,
        base=10,
    )

    fig = plt.figure(figsize=(15, 8.5), dpi=300)
    ax = plt.axes(projection=ccrs.Robinson())
    ax.set_axis_off()
    add_map_background(ax)

    try:
        ax.outline_patch.set_visible(False)
    except Exception:
        pass

    pm = ax.pcolormesh(
        lon,
        lat,
        np.ma.masked_invalid(pct_np),
        transform=ccrs.PlateCarree(),
        cmap=CMAP_DIVERGING,
        norm=norm,
        shading="auto",
        rasterized=False,
    )

    cb = fig.colorbar(
        pm,
        ax=ax,
        orientation="horizontal",
        pad=0.035,
        shrink=0.72,
    )

    ticks = np.array([-100, -50, -20, -10, 0, 10, 20, 50, 100])
    ticks = ticks[(ticks >= -vlim) & (ticks <= vlim)]

    if ticks.size == 0:
        ticks = np.array([-10, -5, 0, 5, 10])

    cb.set_ticks(ticks)
    cb.set_ticklabels([str(int(t)) for t in ticks])
    cb.ax.tick_params(labelsize=11)
    cb.set_label("% change in GDW area per pixel", fontsize=13)

    out_png = OUT / f"ssp370_{PIXEL_VAR}_pixel_pct_change_map.png"

    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)

    log(f"Saved: {out_png}")

def plot_ssp370_pixel_absolute_change():
    log("Plotting SSP370 pixel absolute change")

    hist = open_timmean_da("historical", PIXEL_VAR)
    fut = open_timmean_da("ssp370", PIXEL_VAR)

    diff = (fut - hist).where(hist >= BASELINE_MIN)
    diff_np = diff.compute().values.astype("float32")

    lat = diff["lat"].values
    lon = diff["lon"].values

    diff.name = f"absolute_change_{PIXEL_VAR}"
    diff.attrs["units"] = "km2 per pixel"

    nc_out = OUT / f"ssp370_{PIXEL_VAR}_pixel_absolute_change_2041-2050_vs_2005-2014.nc"
    diff.to_netcdf(nc_out)
    log(f"Saved: {nc_out}")

    vals = np.abs(diff_np[np.isfinite(diff_np)])

    if vals.size:
        vlim = float(np.nanpercentile(vals, ABS_PERCENTILE))
    else:
        vlim = 1.0

    if not np.isfinite(vlim) or vlim <= 0:
        vlim = 1.0

    vlim = float(np.ceil(vlim))

    plot_arr = np.where(np.isfinite(diff_np), diff_np, np.nan)

    norm = TwoSlopeNorm(
        vcenter=0,
        vmin=-vlim,
        vmax=vlim,
    )

    fig = plt.figure(figsize=(15, 8.5), dpi=300)
    ax = plt.axes(projection=ccrs.Robinson())
    ax.set_axis_off()
    add_map_background(ax)

    try:
        ax.outline_patch.set_visible(False)
    except Exception:
        pass

    pm = ax.pcolormesh(
        lon,
        lat,
        np.ma.masked_invalid(plot_arr),
        transform=ccrs.PlateCarree(),
        cmap=CMAP_DIVERGING,
        norm=norm,
        shading="auto",
        rasterized=False,
    )

    cb = fig.colorbar(
        pm,
        ax=ax,
        orientation="horizontal",
        pad=0.035,
        shrink=0.72,
    )

    tick_lim = int(vlim)

    if tick_lim <= 5:
        ticks = np.arange(-tick_lim, tick_lim + 1, 1)
    else:
        step = max(1, int(np.ceil(tick_lim / 4)))
        ticks = np.arange(-tick_lim, tick_lim + 1, step)

    if 0 not in ticks:
        ticks = np.sort(np.append(ticks, 0))

    cb.set_ticks(ticks)
    cb.set_ticklabels([str(int(t)) for t in ticks])
    cb.ax.tick_params(labelsize=11)
    cb.set_label("Change in GDW area per pixel (km²)", fontsize=13)

    out_png = OUT / f"ssp370_{PIXEL_VAR}_pixel_absolute_change_map.png"

    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)

    log(f"Saved: {out_png}")
# =============================================================================
# PERSISTENCE MAPS
# =============================================================================

def plot_ssp370_future_persistence_class():
    log("Plotting SSP370 future persistence class")
    fut_clim = open_monthly_clim_da("ssp370", PIXEL_VAR)
    fut_months = (fut_clim >= BASELINE_MIN).sum("month")
    persistence = classify_active_months(fut_months)
    persistence.name = "future_persistence_class"
    persistence.attrs["classes"] = "1=episodic_1_3_months, 2=seasonal_4_6_months, 3=perennial_7_12_months"
    nc_out = OUT / "ssp370_future_persistence_class_per_pixel.nc"
    persistence.to_netcdf(nc_out)
    log(f"Saved: {nc_out}")

    pers_np = persistence.compute().values.astype("float32")
    lat = persistence["lat"].values
    lon = persistence["lon"].values
    cmap, norm = discrete_cmap_norm(PERSISTENCE_COLORS)

    fig = plt.figure(figsize=(14, 7.5), dpi=300)
    ax = plt.axes(projection=ccrs.Robinson())
    ax.set_axis_off()
    add_map_background(ax)
    try:
        ax.outline_patch.set_visible(False)
    except Exception:
        pass
    ax.pcolormesh(lon, lat, np.ma.masked_invalid(pers_np), transform=ccrs.PlateCarree(), cmap=cmap, norm=norm, shading="auto", rasterized=False)
    # ax.set_title("Future no-land-use wetGDE persistence class, SSP3-7.0\nBased on 2041-2050 monthly climatology", fontsize=15, fontweight="bold")
    handles = [
        Patch(facecolor=PERSISTENCE_COLORS[1], edgecolor="0.4", label="Episodic\n1-3 months"),
        Patch(facecolor=PERSISTENCE_COLORS[2], edgecolor="0.4", label="Seasonal\n4-6 months"),
        Patch(facecolor=PERSISTENCE_COLORS[3], edgecolor="0.4", label="Perennial\n7-12 months")
    ]
    ax.legend(handles=handles, title="Persistence class)", frameon=False, loc="center left", bbox_to_anchor=(0.99, 0.5), fontsize=15, title_fontsize=10)
    #fig.text(0.5, 0.045, f"A GDW-active month is defined as no-land-use wetGDE area ≥ {BASELINE_MIN:g} km² per pixel.", ha="center", fontsize=9, color="0.25")
    out_png = OUT / "ssp370_future_persistence_class_map.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log(f"Saved: {out_png}")


def plot_ssp370_change_in_gdw_months():
    log("Plotting SSP370 change in GDW-active months")
    hist_clim = open_monthly_clim_da("historical", PIXEL_VAR)
    fut_clim = open_monthly_clim_da("ssp370", PIXEL_VAR)
    hist_months = (hist_clim >= BASELINE_MIN).sum("month")
    fut_months = (fut_clim >= BASELINE_MIN).sum("month")
    month_change = fut_months - hist_months
    month_change.name = "change_in_gdw_active_months"
    month_change.attrs["units"] = "months"
    nc_out = OUT / "ssp370_change_in_gdw_active_months_per_pixel.nc"
    month_change.to_netcdf(nc_out)
    log(f"Saved: {nc_out}")

    change_np = month_change.compute().values.astype("float32")
    lat = month_change["lat"].values
    lon = month_change["lon"].values
    norm = TwoSlopeNorm(vcenter=0, vmin=-6, vmax=6)

    fig = plt.figure(figsize=(14, 7.5), dpi=300)
    ax = plt.axes(projection=ccrs.Robinson())
    ax.set_axis_off()
    add_map_background(ax)
    try:
        ax.outline_patch.set_visible(False)
    except Exception:
        pass
    pm = ax.pcolormesh(lon, lat, np.ma.masked_invalid(change_np), transform=ccrs.PlateCarree(), cmap=CMAP_DIVERGING, norm=norm, shading="auto", rasterized=False)
    cb = plt.colorbar(pm, ax=ax, orientation="horizontal", pad=0.035, shrink=0.76)
    ticks = np.arange(-6, 7, 2)
    cb.set_ticks(ticks)
    cb.set_ticklabels([str(int(t)) for t in ticks])
    cb.ax.tick_params(labelsize=11)
    cb.set_label("Change in average number of months", fontsize=13)
    # ax.set_title("Change in no-land-use GDW-active months, SSP3-7.0 minus historical\n2041-2050 relative to 2005-2014", fontsize=15, fontweight="bold")
    #fig.text(0.5, 0.045, f"Positive values mean more months with no-land-use wetGDE area ≥ {BASELINE_MIN:g} km² per pixel.", ha="center", fontsize=9, color="0.25")
    out_png = OUT / "ssp370_change_in_gdw_active_months_map.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log(f"Saved: {out_png}")


def plot_single_persistence_panel(data_np, lon, lat, cmap, norm, title, out_png, legend_handles=None, colorbar_label=None, colorbar_ticks=None):
    fig = plt.figure(figsize=(14, 7.5), dpi=300)
    ax = plt.axes(projection=ccrs.Robinson())
    ax.set_axis_off()
    add_map_background(ax)
    try:
        ax.outline_patch.set_visible(False)
    except Exception:
        pass
    pm = ax.pcolormesh(lon, lat, np.ma.masked_invalid(data_np), transform=ccrs.PlateCarree(), cmap=cmap, norm=norm, shading="auto", rasterized=False, zorder=2)
    ax.set_title(title, fontsize=15, fontweight="bold")

    if colorbar_label is not None:
        cb = fig.colorbar(pm, ax=ax, orientation="horizontal", pad=0.035, shrink=0.76)
        cb.set_label(colorbar_label)
        if colorbar_ticks is not None:
            cb.set_ticks(colorbar_ticks)
            cb.set_ticklabels([str(int(t)) for t in colorbar_ticks])

    if legend_handles is not None:
        ax.legend(handles=legend_handles, loc="lower center", bbox_to_anchor=(0.5, -0.10), ncol=3, frameon=False, fontsize=9)

    #fig.text(0.5, 0.045, f"A GDW-active month is defined as no-land-use wetGDE area ≥ {BASELINE_MIN:g} km² per pixel. Only pixels active in at least one month in both periods are shown.", ha="center", fontsize=9, color="0.25")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log(f"Saved: {out_png}")


def plot_ssp370_persistence_change_maps():
    log("Plotting SSP370 persistence change maps")
    hist_clim = open_monthly_clim_da("historical", PIXEL_VAR)
    fut_clim = open_monthly_clim_da("ssp370", PIXEL_VAR)

    hist_months = (hist_clim >= BASELINE_MIN).sum("month")
    fut_months = (fut_clim >= BASELINE_MIN).sum("month")
    month_change = fut_months - hist_months
    hist_class = classify_active_months(hist_months)
    fut_class = classify_active_months(fut_months)
    class_change = fut_class - hist_class
    transition = hist_class * 10 + fut_class

    valid = np.isfinite(hist_class) & np.isfinite(fut_class)
    month_change = month_change.where(valid)
    class_change = class_change.where(valid)
    transition = transition.where(valid)

    month_change.name = "change_in_gdw_active_months"
    class_change.name = "persistence_class_change"
    transition.name = "persistence_transition"
    month_change.to_netcdf(OUT / "ssp370_change_in_gdw_active_months_per_pixel.nc")
    class_change.to_netcdf(OUT / "ssp370_persistence_class_change_per_pixel.nc")
    transition.to_netcdf(OUT / "ssp370_persistence_transition_per_pixel.nc")

    lat = month_change["lat"].values
    lon = month_change["lon"].values
    month_np = month_change.compute().values.astype("float32")
    class_np = class_change.compute().values.astype("float32")
    trans_np = transition.compute().values.astype("float32")

    norm_month = TwoSlopeNorm(vcenter=0, vmin=-6, vmax=6)
    gainloss_cmap, gainloss_norm = discrete_cmap_norm(GAINLOSS_COLORS)
    trans_cmap, trans_norm = discrete_cmap_norm(TRANSITION_COLORS)

    handles_gain = [
        Patch(facecolor=GAINLOSS_COLORS[-2], edgecolor="0.4", label="Loss of 2 classes"),
        Patch(facecolor=GAINLOSS_COLORS[-1], edgecolor="0.4", label="Loss of 1 class"),
        Patch(facecolor=GAINLOSS_COLORS[0], edgecolor="0.4", label="No change"),
        Patch(facecolor=GAINLOSS_COLORS[1], edgecolor="0.4", label="Gain of 1 class"),
        Patch(facecolor=GAINLOSS_COLORS[2], edgecolor="0.4", label="Gain of 2 classes"),
    ]
    handles_trans = [
        Patch(facecolor=TRANSITION_COLORS[12], edgecolor="0.4", label="Episodic → Seasonal"),
        Patch(facecolor=TRANSITION_COLORS[13], edgecolor="0.4", label="Episodic → Perennial"),
        Patch(facecolor=TRANSITION_COLORS[21], edgecolor="0.4", label="Seasonal → Episodic"),
        Patch(facecolor=TRANSITION_COLORS[23], edgecolor="0.4", label="Seasonal → Perennial"),
        Patch(facecolor=TRANSITION_COLORS[31], edgecolor="0.4", label="Perennial → Episodic"),
        Patch(facecolor=TRANSITION_COLORS[32], edgecolor="0.4", label="Perennial → Seasonal"),
        Patch(facecolor=TRANSITION_COLORS[11], edgecolor="0.4", label="No class change"),
    ]

    plot_single_persistence_panel(
        month_np,
        lon,
        lat,
        CMAP_DIVERGING,
        norm_month,
        "",
        OUT / "ssp370_persistence_change_active_months_map.png",
        colorbar_label="Number of months",
        colorbar_ticks=[-6, -4, -2, 0, 2, 4, 6],
    )
    plot_single_persistence_panel(
        class_np,
        lon,
        lat,
        gainloss_cmap,
        gainloss_norm,
        "",
        OUT / "ssp370_persistence_class_gain_loss_map.png",
        legend_handles=handles_gain,
    )
    plot_single_persistence_panel(
        trans_np,
        lon,
        lat,
        trans_cmap,
        trans_norm,
        "",
        OUT / "ssp370_persistence_transition_map.png",
        legend_handles=handles_trans,
    )

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.8), dpi=300, subplot_kw={"projection": ccrs.Robinson()}, gridspec_kw={"wspace": 0.03})
    for ax in axes:
        add_map_background(ax)

    pm = axes[0].pcolormesh(lon, lat, np.ma.masked_invalid(month_np), transform=ccrs.PlateCarree(), cmap=CMAP_DIVERGING, norm=norm_month, shading="auto", rasterized=False)
    axes[0].set_title("a) Number of months", fontsize=11, fontweight="bold")
    cb = fig.colorbar(pm, ax=axes[0], orientation="horizontal", pad=0.04, shrink=0.82)
    cb.set_label("Months")
    ticks = [-6, -4, -2, 0, 2, 4, 6]
    cb.set_ticks(ticks)
    cb.set_ticklabels([str(int(t)) for t in ticks])

    axes[1].pcolormesh(lon, lat, np.ma.masked_invalid(class_np), transform=ccrs.PlateCarree(), cmap=gainloss_cmap, norm=gainloss_norm, shading="auto", rasterized=False)
    axes[1].set_title("b) Persistence class gain or loss", fontsize=11, fontweight="bold")
    axes[1].legend(handles=handles_gain, frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(0.5, -0.35), fontsize=8)

    axes[2].pcolormesh(lon, lat, np.ma.masked_invalid(trans_np), transform=ccrs.PlateCarree(), cmap=trans_cmap, norm=trans_norm, shading="auto", rasterized=False)
    axes[2].set_title("c) Transition map, historical → future", fontsize=11, fontweight="bold")
    axes[2].legend(handles=handles_trans, frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(0.5, -0.35), fontsize=8)

    # fig.suptitle("Change in no-land-use wetGDE persistence, SSP3-7.0 minus historical\n2041-2050 relative to 2005-2014", fontsize=15, fontweight="bold", y=1.02)
    #fig.text(0.5, -0.03, f"A GDW-active month is defined as no-land-use wetGDE area ≥ {BASELINE_MIN:g} km² per pixel. Only pixels active in at least one month in both periods are shown.", ha="center", fontsize=9, color="0.25")
    out_png = OUT / "ssp370_persistence_change_maps.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log(f"Saved: {out_png}")

# =============================================================================
# MONTHLY CLIMATOLOGY PERCENT CHANGE AND TIME OF MAX CHANGE
# =============================================================================

# def plot_ssp370_monthly_climatology_pct_change():
#     log("Plotting SSP370 monthly climatology percent change")
#     hist = open_monthly_clim_da("historical", PIXEL_VAR)
#     fut = open_monthly_clim_da("ssp370", PIXEL_VAR)
#     pct = xr.where(hist >= BASELINE_MIN, (fut - hist) / hist * 100, np.nan)
#     pct_np_all = pct.compute().values.astype("float32")
#     vals = np.abs(pct_np_all[np.isfinite(pct_np_all)])
#     vlim = float(np.nanpercentile(vals, 98)) if vals.size else 100
#     vlim = max(10, min(vlim, 100))
#     norm = TwoSlopeNorm(vcenter=0, vmin=-vlim, vmax=vlim)
#     lat = pct["lat"].values
#     lon = pct["lon"].values
#     month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

#     fig, axes = plt.subplots(3, 4, figsize=(16, 8.8), dpi=300, subplot_kw={"projection": ccrs.Robinson()})
#     axes = axes.ravel()
#     for i, month in enumerate(range(1, 13)):
#         ax = axes[i]
#         arr = pct.sel(month=month).values.astype("float32")
#         add_map_background(ax)
#         pm = ax.pcolormesh(lon, lat, np.ma.masked_invalid(arr), transform=ccrs.PlateCarree(), cmap=CMAP_DIVERGING, norm=norm, shading="auto", rasterized=False)
#         ax.set_title(month_names[i], fontsize=11, fontweight="bold")
#     cax = fig.add_axes([0.25, 0.07, 0.5, 0.025])
#     cb = fig.colorbar(pm, cax=cax, orientation="horizontal")
#     cb.set_label("Monthly climatology change in no-land-use wetGDE area, %")
#     fig.suptitle("Monthly climatology percent change, SSP3-7.0 minus historical\n2041-2050 relative to 2005-2014", fontsize=15, fontweight="bold", y=0.98)
#     out_png = OUT / "ssp370_area_gdw_nonlu_km2_monthly_climatology_pct_change.png"
#     fig.savefig(out_png, dpi=300, bbox_inches="tight")
#     plt.close(fig)
#     log(f"Saved: {out_png}")

#     log("Plotting month of maximum absolute area change")
#     change = (fut - hist).where(hist >= BASELINE_MIN)
#     abs_change = np.abs(change)
#     max_change = abs_change.max("month")
#     threshold = float(np.nanpercentile(max_change.compute().values, 50))
#     month_max = abs_change.idxmax("month").where(max_change >= threshold)
#     month_max_np = month_max.compute().values.astype("float32")
#     cmap_month = plt.get_cmap("twilight", 12)
#     norm_month = BoundaryNorm(np.arange(0.5, 13.5, 1), cmap_month.N)

#     fig = plt.figure(figsize=(14, 7.5), dpi=300)
#     ax = plt.axes(projection=ccrs.Robinson())
#     add_map_background(ax)
#     pm = ax.pcolormesh(lon, lat, np.ma.masked_invalid(month_max_np), transform=ccrs.PlateCarree(), cmap=cmap_month, norm=norm_month, shading="auto", rasterized=False)
#     cb = plt.colorbar(pm, ax=ax, orientation="horizontal", pad=0.035, shrink=0.76, ticks=np.arange(1, 13))
#     cb.ax.set_xticklabels(month_names)
#     cb.set_label("Month of maximum absolute area change")
#     ax.set_title("Timing of maximum monthly no-land-use wetGDE area change\nSSP3-7.0 2041-2050 relative to historical 2005-2014", fontsize=15, fontweight="bold")
#     #fig.text(0.5, 0.045, f"Computed from absolute km² change, not percent change. Pixels with maximum monthly change below the median signal ({threshold:.3g} km²) are masked.", ha="center", fontsize=9, color="0.25")
#     out_png = OUT / "ssp370_area_gdw_nonlu_km2_month_of_max_absolute_change.png"
#     fig.savefig(out_png, dpi=300, bbox_inches="tight")
#     plt.close(fig)
#     log(f"Saved: {out_png}")

#     month_max.name = "month_of_max_abs_area_change"
#     month_max.to_netcdf(OUT / "ssp370_area_gdw_nonlu_km2_month_of_max_absolute_change.nc")

# =============================================================================
# PIXEL DOMINANT DRIVER MAP AND DONUT SUMMARY
# =============================================================================

def plot_pixel_driver_direction_all_scenarios():
    log("Plotting pixel level driver dominance with loss and gain direction")

    all_counts = []

    class_colors = {
        1: "#08306B",
        2: "#6BAED6",
        3: "#7F2704",
        4: "#FDAE6B",
        5: "#A1D99B",
        6: "#238B45",
    }

    class_labels = {
        1: "Groundwater driven loss",
        2: "Groundwater driven gain",
        3: "Land use driven loss",
        4: "Land use driven gain",
        5: "Mixed loss",
        6: "Mixed gain",
    }

    for sc in FUTURE_S:
        log(f"Processing driver direction: {sc}")

        hist_total = open_timmean_da("historical", COL_TOTAL)
        fut_total = open_timmean_da(sc, COL_TOTAL)

        hist_nonlu = open_timmean_da("historical", COL_NONLU)
        fut_nonlu = open_timmean_da(sc, COL_NONLU)

        hist_lu_effect = hist_total - hist_nonlu
        fut_lu_effect = fut_total - fut_nonlu

        dgw = np.abs(fut_nonlu - hist_nonlu)
        dlu = np.abs(fut_lu_effect - hist_lu_effect)

        total_signal = dgw + dlu
        dtotal_signed = fut_total - hist_total

        signal_values = total_signal.compute().values
        finite_signal = signal_values[np.isfinite(signal_values)]

        threshold = (
            float(np.nanpercentile(finite_signal, 50))
            if finite_signal.size
            else 0.0
        )

        valid = total_signal >= threshold

        dominance_dir = xr.full_like(
            total_signal,
            np.nan,
            dtype="float32",
        )

        dominance_dir = dominance_dir.where(
            ~(valid & (dgw > dlu) & (dtotal_signed < 0)),
            1,
        )

        dominance_dir = dominance_dir.where(
            ~(valid & (dgw > dlu) & (dtotal_signed > 0)),
            2,
        )

        dominance_dir = dominance_dir.where(
            ~(valid & (dlu > dgw) & (dtotal_signed < 0)),
            3,
        )

        dominance_dir = dominance_dir.where(
            ~(valid & (dlu > dgw) & (dtotal_signed > 0)),
            4,
        )

        dominance_dir = dominance_dir.where(
            ~(valid & np.isclose(dgw, dlu) & (dtotal_signed < 0)),
            5,
        )

        dominance_dir = dominance_dir.where(
            ~(valid & np.isclose(dgw, dlu) & (dtotal_signed > 0)),
            6,
        )

        dominance_dir.name = "dominant_driver_with_direction"

        dominance_dir.attrs["classes"] = (
            "1=groundwater driven loss, "
            "2=groundwater driven gain, "
            "3=land use driven loss, "
            "4=land use driven gain, "
            "5=mixed loss, "
            "6=mixed gain"
        )

        dominance_dir.attrs["method"] = (
            "Dominant driver is assigned by comparing absolute changes in "
            "|delta no land use wetGDE| and |delta land use effect|. "
            "Direction is assigned from signed total wetGDE change, "
            "future total wetGDE minus historical total wetGDE. "
            "Pixels below the median total driver signal are masked."
        )

        dominance_dir.attrs["scenario"] = sc
        dominance_dir.attrs["threshold_total_signal_km2"] = threshold

        dgw.name = "absolute_groundwater_change_km2"
        dlu.name = "absolute_landuse_change_km2"
        dtotal_signed.name = "signed_total_wetgde_change_km2"
        total_signal.name = "total_driver_signal_km2"

        dgw.attrs["description"] = (
            "absolute future no land use wetGDE minus historical no land use wetGDE"
        )

        dlu.attrs["description"] = (
            "absolute future land use effect minus historical land use effect, "
            "where land use effect equals total wetGDE minus no land use wetGDE"
        )

        dtotal_signed.attrs["description"] = (
            "future total wetGDE minus historical total wetGDE"
        )

        total_signal.attrs["description"] = (
            "absolute groundwater change plus absolute land use change"
        )

        for da in [dgw, dlu, dtotal_signed, total_signal]:
            da.attrs["scenario"] = sc

        dominance_dir.to_netcdf(
            OUT / f"{sc}_pixel_dominant_driver_with_direction.nc"
        )

        dgw.to_netcdf(
            OUT / f"{sc}_absolute_groundwater_change_driver.nc"
        )

        dlu.to_netcdf(
            OUT / f"{sc}_absolute_landuse_change_driver.nc"
        )

        dtotal_signed.to_netcdf(
            OUT / f"{sc}_signed_total_wetgde_change.nc"
        )

        total_signal.to_netcdf(
            OUT / f"{sc}_total_driver_signal.nc"
        )

        dom_np = dominance_dir.compute().values.astype("float32")
        lat = dominance_dir["lat"].values
        lon = dominance_dir["lon"].values

        valid_pixels = int(np.isfinite(dom_np).sum())

        for cls, label in class_labels.items():
            n_pixels = int(np.nansum(dom_np == cls))

            all_counts.append({
                "scenario": sc,
                "class": cls,
                "label": label,
                "n_pixels": n_pixels,
                "valid_pixels": valid_pixels,
                "fraction_pct": (
                    n_pixels / valid_pixels * 100
                    if valid_pixels > 0
                    else np.nan
                ),
                "threshold_total_signal_km2": threshold,
            })

        cmap, norm = discrete_cmap_norm(class_colors)

        fig = plt.figure(figsize=(15, 8), dpi=300)
        ax = plt.axes(projection=ccrs.Robinson())
        ax.set_axis_off()

        add_map_background(ax)

        try:
            ax.outline_patch.set_visible(False)
        except Exception:
            pass

        ax.pcolormesh(
            lon,
            lat,
            np.ma.masked_invalid(dom_np),
            transform=ccrs.PlateCarree(),
            cmap=cmap,
            norm=norm,
            shading="auto",
            rasterized=False,
            zorder=2,
        )

        handles = [
            Patch(facecolor=class_colors[i], edgecolor="0.4", label=class_labels[i])
            for i in range(1, 7)
        ]

        ax.legend(
            handles=handles,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.10),
            ncol=3,
            frameon=False,
            fontsize=10,
        )

        out_png = OUT / f"{sc}_pixel_dominant_driver_with_direction_map.png"

        fig.savefig(
            out_png,
            dpi=300,
            bbox_inches="tight",
        )

        plt.close(fig)

        log(f"Saved: {out_png}")

    count_tab = pd.DataFrame(all_counts)

    count_tab.to_csv(
        OUT / "pixel_driver_direction_counts_all_scenarios.csv",
        index=False,
    )

    log(f"Saved: {OUT / 'pixel_driver_direction_counts_all_scenarios.csv'}")


def plot_driver_direction_donut():
    log("Plotting driver direction donut charts")

    csv = OUT / "pixel_driver_direction_counts_all_scenarios.csv"
    df = pd.read_csv(csv)

    scenario_order = [
        "ssp126",
        "ssp370",
        "ssp585",
    ]

    scenario_labels = {
        "ssp126": "SSP1 2.6",
        "ssp370": "SSP3 7.0",
        "ssp585": "SSP5 8.5",
    }

    class_order = [
        "Groundwater driven loss",
        "Groundwater driven gain",
        "Land use driven loss",
        "Land use driven gain",
        "Mixed loss",
        "Mixed gain",
    ]

    colors = {
        "Groundwater driven loss": "#08306B",
        "Groundwater driven gain": "#6BAED6",
        "Land use driven loss": "#7F2704",
        "Land use driven gain": "#FDAE6B",
        "Mixed gain": "#238B45",
        "Mixed loss": "#A1D99B",
        
    }

    df["label"] = (
        df["label"]
        .astype(str)
        .str.replace("-", " ", regex=False)
    )

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(15, 5.8),
        dpi=300,
    )

    for ax, sc in zip(axes, scenario_order):

        d = df[df["scenario"] == sc].copy()

        vals = [
            float(
                d.loc[
                    d["label"] == cls,
                    "fraction_pct",
                ].sum()
            )
            for cls in class_order
        ]

        cols = [colors[cls] for cls in class_order]

        ax.pie(
            vals,
            colors=cols,
            startangle=90,
            counterclock=False,
            wedgeprops=dict(
                width=0.42,
                edgecolor="white",
                linewidth=1.6,
            ),
            autopct=lambda p:
                f"{p:.0f}%"
                if p >= 3
                else "",
            pctdistance=0.86,
            textprops=dict(
                fontsize=15,
                fontweight="bold",
                color="black",
            ),
        )

        centre_circle = plt.Circle(
            (0, 0),
            0.47,
            fc="white",
        )

        ax.add_artist(centre_circle)

        loss_pct = float(
            d.loc[
                d["label"].str.contains(
                    "loss",
                    case=False,
                    na=False,
                ),
                "fraction_pct",
            ].sum()
        )

        gain_pct = float(
            d.loc[
                d["label"].str.contains(
                    "gain",
                    case=False,
                    na=False,
                ),
                "fraction_pct",
            ].sum()
        )

        ax.text(
            0,
            0.12,
            f"{loss_pct:.0f}%",
            ha="center",
            va="center",
            fontsize=22,
            fontweight="bold",
            color="#7F2704",
        )

        ax.text(
            0,
            -0.05,
            "Loss",
            ha="center",
            va="center",
            fontsize=13,
            color="0.30",
        )

        ax.text(
            0,
            -0.23,
            f"Gain {gain_pct:.0f}%",
            ha="center",
            va="center",
            fontsize=12,
            color="0.45",
        )

        ax.set_title(
            scenario_labels[sc],
            fontsize=17,
            fontweight="bold",
            pad=20,
        )

        ax.set_aspect("equal")

    handles = [
        Patch(
            facecolor=colors[cls],
            edgecolor="none",
            label=cls,
        )
        for cls in class_order
    ]

    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.04),
        ncol=3,
        frameon=False,
        fontsize=13,
    )

    fig.tight_layout(
        rect=[0, 0.09, 1, 1],
    )

    out = OUT / "driver_direction_donut_summary.png"

    fig.savefig(
        out,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(fig)

    log(f"Saved: {out}")
    

##For figure 1 

from matplotlib.colors import LinearSegmentedColormap
import matplotlib as mpl

mpl.rcParams["font.family"] = "sans-serif"
mpl.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Helvetica", "Liberation Sans"]

_RDGREY_BU = LinearSegmentedColormap.from_list(
    "rdgrey_bu",
    [
        "#67001F", "#B2182B", "#D6604D", "#F4A582", "#FDDBC7",
        "#AAAAAA",
        "#D1E5F0", "#92C5DE", "#4393C3", "#2166AC", "#053061",
    ],
    N=512,
)
_RDGREY_BU.set_bad(color="white")


def _add_map_background_white(ax):
    ax.set_global()
    ax.set_extent([-180, 180, -58, 90], crs=ccrs.PlateCarree())
    ax.add_feature(
        cfeature.LAND.with_scale("110m"),
        facecolor="white", edgecolor="none", zorder=0,
    )
    ax.coastlines(linewidth=0.35, color="0.55", zorder=3)
    ax.axis("off")

def plot_figure1_four_panel():
    log("Building four-panel Figure 1")

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    hist_da = open_timmean_da("historical", PIXEL_VAR)
    lat = hist_da["lat"].values
    lon = hist_da["lon"].values

    diff_np = (
        (open_timmean_da("ssp370", PIXEL_VAR) - hist_da)
        .where(hist_da >= BASELINE_MIN)
        .compute()
        .values.astype("float32")
    )

    SCEN_ORDER = ["ssp126", "ssp370", "ssp585"]

    SCEN_LABELS = {
        "ssp126": "SSP1–2.6",
        "ssp370": "SSP3–7.0",
        "ssp585": "SSP5–8.5",
    }

    loss_vals = {"ssp126": 245, "ssp370": 432, "ssp585": 341}
    gain_vals = {"ssp126": 194, "ssp370": 102, "ssp585": 300}

    driver_nc = OUT / "ssp370_pixel_dominant_driver_with_direction.nc"

    if not driver_nc.exists():
        plot_pixel_driver_direction_all_scenarios()

    with xr.open_dataset(driver_nc) as ds_drv:
        dom_np = ds_drv["dominant_driver_with_direction"].values.astype("float32")

    csv_path = OUT / "pixel_driver_direction_counts_all_scenarios.csv"

    if not csv_path.exists():
        plot_pixel_driver_direction_all_scenarios()

    df_counts = pd.read_csv(csv_path)
    df_counts["label"] = df_counts["label"].str.replace("-", " ", regex=False)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    fig = plt.figure(figsize=(72, 52), dpi=300, constrained_layout=False)

    top_b, top_h = 0.56, 0.39
    cb_b, cb_h = 0.515, 0.018
    bot_b, bot_h = 0.10, 0.34

    left_edge = 0.035
    map_w = 0.62
    gap = 0.035
    side_w = 0.29

    map_l = left_edge
    side_l = map_l + map_w + gap

    ax_a = fig.add_axes(
        [map_l, top_b, map_w, top_h],
        projection=ccrs.Robinson(),
    )

    ax_bbar = fig.add_axes(
        [side_l, top_b, side_w, top_h],
    )

    ax_cb = fig.add_axes(
        [map_l + 0.15 * map_w, cb_b, map_w * 0.70, cb_h],
    )

    ax_cmap = fig.add_axes(
        [map_l, bot_b, map_w, bot_h],
        projection=ccrs.Robinson(),
    )

    ax_d = fig.add_axes(
        [side_l, bot_b, side_w, bot_h],
    )

    # ------------------------------------------------------------------
    # MASSIVE FONT SCALING
    # ------------------------------------------------------------------
    PANEL_LABEL_SIZE = 100
    AXIS_LABEL_SIZE = 68
    TICK_SIZE = 60
    VALUE_SIZE = 64
    LEGEND_SIZE = 56
    PERCENT_SIZE = 60
    SMALL_TEXT = 52

    LABEL_KW = dict(
        fontsize=PANEL_LABEL_SIZE,
        fontweight="bold",
        va="top",
        ha="left",
        fontfamily="sans-serif",
    )

    # ------------------------------------------------------------------
    # Panel a
    # ------------------------------------------------------------------
    _add_map_background_white(ax_a)

    norm_a = TwoSlopeNorm(vcenter=0, vmin=-8, vmax=8)

    pm_a = ax_a.pcolormesh(
        lon,
        lat,
        np.ma.masked_invalid(diff_np),
        transform=ccrs.PlateCarree(),
        cmap=_RDGREY_BU,
        norm=norm_a,
        shading="auto",
        rasterized=True,
        zorder=2,
    )

    ax_a.text(
        -0.04,
        1.03,
        "a",
        transform=ax_a.transAxes,
        **LABEL_KW,
    )

    # ------------------------------------------------------------------
    # Colorbar
    # ------------------------------------------------------------------
    cb = fig.colorbar(
        pm_a,
        cax=ax_cb,
        orientation="horizontal",
        ticks=[-8, -4, 0, 4, 8],
        extend="both",
    )

    cb.set_label(
        "Change in GDW area per pixel (km²)",
        fontsize=AXIS_LABEL_SIZE,
        fontfamily="sans-serif",
        fontweight="bold",
    )

    cb.ax.tick_params(
        labelsize=TICK_SIZE,
        length=12,
        width=2.0,
    )

    cb.outline.set_linewidth(2.0)
    cb.outline.set_edgecolor("0.35")

    ax_cb.axhline(
        0.72,
        color="white",
        alpha=0.18,
        linewidth=14,
        zorder=5,
    )

    # ------------------------------------------------------------------
    # Panel b
    # ------------------------------------------------------------------
    x_ins = np.arange(len(SCEN_ORDER))
    bar_w_ = 0.34

    LOSS_COL = "#B2182B"
    GAIN_COL = "#2166AC"

    loss_arr = np.array([loss_vals[sc] for sc in SCEN_ORDER])
    gain_arr = np.array([gain_vals[sc] for sc in SCEN_ORDER])

    b_loss = ax_bbar.bar(
        x_ins - bar_w_ / 2,
        -loss_arr,
        width=bar_w_,
        color=LOSS_COL,
        edgecolor="white",
        linewidth=2.0,
        label="Loss",
    )

    b_gain = ax_bbar.bar(
        x_ins + bar_w_ / 2,
        gain_arr,
        width=bar_w_,
        color=GAIN_COL,
        edgecolor="white",
        linewidth=2.0,
        label="Gain",
    )

    for bar, val in zip(b_loss, loss_arr):
        ax_bbar.text(
            bar.get_x() + bar.get_width() / 2,
            -val - 20,
            f"{val:,}",
            ha="center",
            va="top",
            fontsize=VALUE_SIZE,
            color=LOSS_COL,
            fontweight="bold",
            fontfamily="sans-serif",
        )

    for bar, val in zip(b_gain, gain_arr):
        ax_bbar.text(
            bar.get_x() + bar.get_width() / 2,
            val + 20,
            f"{val:,}",
            ha="center",
            va="bottom",
            fontsize=VALUE_SIZE,
            color=GAIN_COL,
            fontweight="bold",
            fontfamily="sans-serif",
        )

    ax_bbar.text(
        -0.18,
        1.03,
        "b",
        transform=ax_bbar.transAxes,
        **LABEL_KW,
    )

    ax_bbar.axhline(0, color="0.30", lw=2.2, zorder=3)

    ax_bbar.set_ylim(-520, 340)

    ax_bbar.set_xticks(x_ins)

    ax_bbar.set_xticklabels(
        [SCEN_LABELS[s] for s in SCEN_ORDER],
        fontsize=TICK_SIZE,
        rotation=0,
        ha="center",
        fontfamily="sans-serif",
        fontweight="bold",
    )

    ax_bbar.set_ylabel(
        "Area change (thousand km²)",
        fontsize=AXIS_LABEL_SIZE,
        fontfamily="sans-serif",
        fontweight="bold",
    )

    ax_bbar.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda y, _: str(abs(int(y))))
    )

    ax_bbar.tick_params(axis="y", labelsize=TICK_SIZE)
    ax_bbar.tick_params(axis="x", labelsize=TICK_SIZE, pad=12)

    ax_bbar.grid(
        axis="y",
        alpha=0.20,
        linewidth=1.8,
    )

    ax_bbar.legend(
        frameon=False,
        loc="lower left",
        handlelength=1.5,
        handleheight=1.2,
        prop={
            "family": "sans-serif",
            "size": LEGEND_SIZE,
            "weight": "bold",
        },
    )

    for sp in ("top", "right"):
        ax_bbar.spines[sp].set_visible(False)

    for sp in ("left", "bottom"):
        ax_bbar.spines[sp].set_linewidth(2.0)

    # ------------------------------------------------------------------
    # Panel c
    # ------------------------------------------------------------------
    CLASS_COLORS = {
        1: "#08306B",
        2: "#6BAED6",
        3: "#7F2704",
        4: "#FDAE6B",
        5: "#A1D99B",
        6: "#238B45",
    }

    CLASS_LABELS_MAP = {
        1: "Groundwater loss",
        2: "Groundwater gain",
        3: "Land use loss",
        4: "Land use gain",
        5: "Mixed loss",
        6: "Mixed gain",
    }

    cmap_b, norm_b = discrete_cmap_norm(CLASS_COLORS)

    try:
        cmap_b.set_bad(color="white")
    except Exception:
        pass

    _add_map_background_white(ax_cmap)

    ax_cmap.pcolormesh(
        lon,
        lat,
        np.ma.masked_invalid(dom_np),
        transform=ccrs.PlateCarree(),
        cmap=cmap_b,
        norm=norm_b,
        shading="auto",
        rasterized=True,
        zorder=2,
    )

    ax_cmap.text(
        -0.04,
        1.03,
        "c",
        transform=ax_cmap.transAxes,
        **LABEL_KW,
    )

    # ------------------------------------------------------------------
    # Panel d
    # ------------------------------------------------------------------
    LOSS_CLASSES = [
        "Groundwater driven loss",
        "Land use driven loss",
        "Mixed loss",
    ]

    GAIN_CLASSES = [
        "Groundwater driven gain",
        "Land use driven gain",
        "Mixed gain",
    ]
    LOSS_COLORS = ["#08306B", "#7F2704", "#238B45"]
    GAIN_COLORS = ["#6BAED6", "#FDAE6B", "#A1D99B"]
  

    y_pos = np.arange(len(SCEN_ORDER))
    bar_height = 0.50

    for i, sc in enumerate(SCEN_ORDER):

        d = df_counts[df_counts["scenario"] == sc].set_index("label")

        left_loss = 0.0

        for cls, col in zip(LOSS_CLASSES, LOSS_COLORS):

            val = (
                float(d.loc[cls, "fraction_pct"])
                if cls in d.index else 0.0
            )

            ax_d.barh(
                y_pos[i],
                -val,
                left=-left_loss,
                height=bar_height,
                color=col,
                edgecolor="white",
                linewidth=1.4,
            )

            if val >= 5:
                ax_d.text(
                    -left_loss - val / 2,
                    y_pos[i],
                    f"{val:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=PERCENT_SIZE,
                    color="white",
                    fontweight="bold",
                    fontfamily="sans-serif",
                )

            left_loss += val

        left_gain = 0.0

        for cls, col in zip(GAIN_CLASSES, GAIN_COLORS):

            val = (
                float(d.loc[cls, "fraction_pct"])
                if cls in d.index else 0.0
            )

            ax_d.barh(
                y_pos[i],
                val,
                left=left_gain,
                height=bar_height,
                color=col,
                edgecolor="white",
                linewidth=1.4,
            )

            if val >= 5:
                ax_d.text(
                    left_gain + val / 2,
                    y_pos[i],
                    f"{val:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=PERCENT_SIZE,
                    color="white",
                    fontweight="bold",
                    fontfamily="sans-serif",
                )

            left_gain += val

    ax_d.text(
        -0.18,
        1.03,
        "d",
        transform=ax_d.transAxes,
        **LABEL_KW,
    )

    ax_d.axvline(
        0,
        color="0.25",
        lw=2.2,
        zorder=3,
    )

    ax_d.set_yticks(y_pos)

    ax_d.set_yticklabels(
        [SCEN_LABELS[s] for s in SCEN_ORDER],
        fontsize=TICK_SIZE,
        fontfamily="sans-serif",
        fontweight="bold",
    )

    ax_d.set_xlabel(
        "Fraction of pixels (%)",
        fontsize=AXIS_LABEL_SIZE,
        fontfamily="sans-serif",
        fontweight="bold",
    )

    ax_d.grid(
        axis="x",
        alpha=0.22,
        linewidth=1.8,
    )

    ax_d.xaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda x, _: str(abs(int(x))))
    )

    ax_d.tick_params(axis="x", labelsize=TICK_SIZE)
    ax_d.tick_params(axis="y", labelsize=TICK_SIZE)

    ax_d.text(
        0.25,
        -0.12,
        "← Loss",
        transform=ax_d.transAxes,
        ha="center",
        va="top",
        fontsize=SMALL_TEXT,
        color="0.35",
        fontfamily="sans-serif",
    )

    ax_d.text(
        0.75,
        -0.12,
        "Gain →",
        transform=ax_d.transAxes,
        ha="center",
        va="top",
        fontsize=SMALL_TEXT,
        color="0.35",
        fontfamily="sans-serif",
    )

    for sp in ("top", "right"):
        ax_d.spines[sp].set_visible(False)

    for sp in ("left", "bottom"):
        ax_d.spines[sp].set_linewidth(2.0)

    # ------------------------------------------------------------------
    # Shared legend
    # ------------------------------------------------------------------
    shared_handles = [
        Patch(
            facecolor=CLASS_COLORS[i],
            edgecolor="0.5",
            label=CLASS_LABELS_MAP[i],
            linewidth=1.0,
        )
        for i in range(1, 7)
    ]

    fig.legend(
        handles=shared_handles,
        ncol=6,
        loc="lower center",
        bbox_to_anchor=(0.50, 0.02),
        frameon=False,
        handlelength=1.6,
        handleheight=1.3,
        columnspacing=2.2,
        prop={
            "family": "sans-serif",
            "size": LEGEND_SIZE,
        },
    )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    out_png = OUT / "figure1_four_panel.png"

    fig.savefig(
        out_png,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(fig)

    log(f"Saved: {out_png}")

"""
Drop-in addition to manuscript_figures.py
Add plot_realm_ts_only() and call it from main().

Layout: 2x3 grid of realm time series only, no global panel, no dotted line.
Saved as realm_ts_only.png
"""

import matplotlib as mpl
mpl.rcParams["font.family"] = "sans-serif"
mpl.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Helvetica", "Liberation Sans"]


def plot_realm_ts_only():
    log("Building realm-only time series figure")

    df = annual_realm_from_parquet([TS_VAR], keep_gcm=True)
    df["value_plot"] = df[TS_VAR] / 1e8

    realms = [r for r in REALM_ORDER if r in set(df["realm"])]

    fig = plt.figure(figsize=(22, 12), dpi=300, constrained_layout=False)

    ncols, nrows = 3, 2
    left0 = 0.07
    bot0  = 0.10
    pw    = (0.90 - (ncols - 1) * 0.03) / ncols
    ph    = (0.82 - (nrows - 1) * 0.06) / nrows
    hgap  = 0.03
    vgap  = 0.08

    realm_axes = []
    for row in range(nrows):
        for col in range(ncols):
            l = left0 + col * (pw + hgap)
            b = bot0  + (nrows - 1 - row) * (ph + vgap)
            realm_axes.append(fig.add_axes([l, b, pw, ph]))

    def _plot_ts_panel(ax, source_df, title, ylabel):
        hist = source_df[
            (source_df["scenario"] == "historical") &
            (source_df["year"] <= 2014)
        ].copy()
        hist_piv  = hist.pivot_table(
            index="year", columns="source",
            values="value_plot", aggfunc="mean",
        ).sort_index()
        hist_mean = smooth(hist_piv.mean(axis=1))
        hist_low  = smooth(hist_piv.min(axis=1))
        hist_high = smooth(hist_piv.max(axis=1))

        ax.fill_between(
            hist_mean.index, hist_low.values, hist_high.values,
            color=SCEN_COLOR["historical"], alpha=0.18, linewidth=0,
        )
        ax.plot(hist_mean.index, hist_mean.values,
                color=SCEN_COLOR["historical"], lw=2.0)

        hist_clean = hist_mean.dropna()
        if hist_clean.empty:
            return

        last_yr  = int(hist_clean.index.max())
        last_val = float(hist_clean.iloc[-1])

        for sc in FUTURE_S:
            d = source_df[
                (source_df["scenario"] == sc) &
                (source_df["year"] >= JOIN_YEAR)
            ].copy()
            if d.empty:
                continue
            piv = d.pivot_table(
                index="year", columns="source",
                values="value_plot", aggfunc="mean",
            ).sort_index()
            mean_raw       = piv.mean(axis=1)
            low_raw        = piv.min(axis=1)
            high_raw       = piv.max(axis=1)
            mean_raw_clean = mean_raw.dropna()
            if mean_raw_clean.empty:
                continue

            shift = last_val - float(mean_raw_clean.iloc[0])
            mean  = smooth(mean_raw  + shift)
            low   = smooth(low_raw   + shift)
            high  = smooth(high_raw  + shift)

            low0   = float(hist_low.dropna().iloc[-1])
            high0  = float(hist_high.dropna().iloc[-1])
            shade_x   = np.concatenate([[last_yr], mean.index.values])
            shade_low = np.concatenate([[low0],    low.values])
            shade_hi  = np.concatenate([[high0],   high.values])

            ax.fill_between(shade_x, shade_low, shade_hi,
                            color=SCEN_COLOR[sc], alpha=0.18, linewidth=0)
            mean_clean = mean.dropna()
            ax.plot(
                [last_yr, int(mean_clean.index.min())],
                [last_val, float(mean_clean.iloc[0])],
                color=SCEN_COLOR[sc], lw=2.0,
            )
            ax.plot(mean.index, mean.values, color=SCEN_COLOR[sc], lw=2.0)

        ax.set_title(title, fontsize=11, fontweight="bold",
                     fontfamily="sans-serif")
        ax.set_ylabel(ylabel, fontsize=11, fontfamily="sans-serif")
        ax.tick_params(labelsize=10)
        ax.grid(axis="y", alpha=0.25)
        ax.yaxis.set_major_locator(
            matplotlib.ticker.MaxNLocator(nbins=5, prune="both")
        )
        ax.yaxis.set_major_formatter(
            matplotlib.ticker.FormatStrFormatter("%.2f")
        )
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)

    for i, (realm, ax) in enumerate(zip(realms, realm_axes)):
        _plot_ts_panel(ax, df[df["realm"] == realm].copy(),
                       title=realm, ylabel="Area (M km²)")

    for j in range(len(realms), len(realm_axes)):
        realm_axes[j].set_visible(False)

    handles = [
        Line2D([0], [0], color=SCEN_COLOR[s], lw=2.5, label=SCEN_LABEL[s])
        for s in SCENARIOS
    ]
    fig.legend(handles=handles, frameon=False, ncol=4,
               fontsize=11, loc="lower center",
               bbox_to_anchor=(0.5, 0.01),
               prop={"family": "sans-serif", "size": 11})

    out_png = OUT / "realm_ts_only.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log(f"Saved: {out_png}")

"""
Drop-in addition to manuscript_figures.py
Two functions:
  plot_figure3_lollipop()   – decadal change lollipop, all four scenarios (Figure 3)
  plot_figure4_biome_map()  – biome-realm component map, future scenarios (Figure 4)

Add both to main().
"""

import matplotlib as mpl
mpl.rcParams["font.family"] = "sans-serif"
mpl.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Helvetica", "Liberation Sans"]

"""
Drop-in addition to manuscript_figures.py
Two functions:
  plot_figure3_lollipop()   – decadal change lollipop, all four scenarios (Figure 3)
  plot_figure4_biome_map()  – biome-realm component map, all four scenarios (Figure 4)

Add both to main().
"""

import matplotlib as mpl
mpl.rcParams["font.family"] = "sans-serif"
mpl.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Helvetica", "Liberation Sans"]


# =============================================================================
# FIGURE 3 – Decadal change lollipop
# =============================================================================

def plot_figure3_lollipop():
    log("Plotting Figure 3: decadal-change lollipop")

    df = annual_realm_from_parquet([COL_TOTAL, COL_NONLU], keep_gcm=False)
    rows = []

    for sc in SCENARIOS:
        if sc == "historical":
            base_lo, base_hi = HIST_BASE
            fut_lo,  fut_hi  = HIST_LAST
        else:
            base_lo, base_hi = HIST_LAST
            fut_lo,  fut_hi  = FUT_LAST

        d_base = df[df["scenario"].eq("historical") & df["year"].between(base_lo, base_hi)]
        d_fut  = df[df["scenario"].eq(sc)           & df["year"].between(fut_lo,  fut_hi)]

        base = d_base.groupby("realm", as_index=False)[[COL_TOTAL, COL_NONLU]].mean()
        fut  = d_fut.groupby( "realm", as_index=False)[[COL_TOTAL, COL_NONLU]].mean()

        m = base.merge(fut, on="realm", suffixes=("_base", "_future"), how="outer")
        m["delta_total"] = (m[f"{COL_TOTAL}_future"] - m[f"{COL_TOTAL}_base"]) / 1e5
        m["delta_nonlu"] = (m[f"{COL_NONLU}_future"] - m[f"{COL_NONLU}_base"]) / 1e5
        m["scenario"] = sc
        rows.append(m)

    tab    = pd.concat(rows, ignore_index=True)
    realms = [r for r in REALM_ORDER if r in set(tab["realm"])]
    y_pos  = np.arange(len(realms))[::-1]

    panel_scenarios = SCENARIOS

    fig, axes = plt.subplots(
        1, len(panel_scenarios),
        figsize=(24, 7), dpi=300,
    )

    for ax, sc in zip(axes, panel_scenarios):
        d = tab[tab["scenario"] == sc].set_index("realm").reindex(realms)

        ax.axvline(0, color="0.60", lw=1.0, zorder=0)

        for yi, v_total, v_nonlu in zip(y_pos, d["delta_total"], d["delta_nonlu"]):

            if np.isfinite(v_total):
                c = "#2166AC" if v_total >= 0 else "#B2182B"
                ax.plot([0, v_total], [yi + 0.10, yi + 0.10],
                        color=c, lw=2.2, zorder=1, solid_capstyle="round")
                ax.plot(v_total, yi + 0.10, "o", color=c, ms=7, zorder=2)

            if np.isfinite(v_nonlu):
                c = "#2166AC" if v_nonlu >= 0 else "#B2182B"
                ax.plot([0, v_nonlu], [yi - 0.10, yi - 0.10],
                        color=c, lw=2.2, ls="--", zorder=1, solid_capstyle="round")
                ax.plot(v_nonlu, yi - 0.10, "s",
                        mfc="white", mec=c, ms=7, zorder=2, mew=1.8)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(realms, fontsize=10.5)
        ax.set_title(SCEN_LABEL[sc], fontsize=12, fontweight="bold")
        ax.set_xlabel("Change in GDW area\n(thousand km²)", fontsize=10.5)
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=5, prune="both"))
        ax.grid(axis="x", alpha=0.22, linewidth=0.7)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)

    leg_handles = [
        Line2D([0], [0], color="0.3", marker="o", lw=2.2, ms=7,
               label="Total GDW"),
        Line2D([0], [0], color="0.3", marker="s", mfc="white", mew=1.8,
               lw=2.2, ls="--", ms=7,
               label="GDW without land-use impact"),
        Line2D([0], [0], color="#2166AC", lw=2.2, label="Gain"),
        Line2D([0], [0], color="#B2182B", lw=2.2, label="Loss"),
    ]
    fig.legend(
        handles=leg_handles,
        ncol=4,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.00),
        frameon=False,
        fontsize=10.5,
        handlelength=1.8,
        columnspacing=1.6,
        prop={"family": "sans-serif", "size": 10.5},
    )

    fig.tight_layout(rect=[0.0, 0.10, 1.0, 1.0])
    out = OUT / "figure3_lollipop_decadal_change.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log(f"Saved: {out}")


# =============================================================================
# FIGURE 4 – Biome-realm component maps, all four scenarios
# =============================================================================

def plot_figure4_biome_map():
    log("Plotting Figure 4: biome-realm component maps")

    table = compute_biome_realm_pcr_table()
    gdf   = load_biome_realm_gdf_checked(table)

    value_col  = "normalized_change_pct"
    components = list(PCR_COLS_NORM.keys())
    scenarios  = SCENARIOS

    COMP_LABELS = {
        "Groundwater Impact Only":       "Groundwater-only",
        "Land-use Impact Only":          "Land-use-only",
        "Groundwater + Land-use Impact": "Combined",
    }

    nrows = len(scenarios)
    ncols = len(components)

    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(5.5 * ncols, 3.8 * nrows),
        dpi=300,
        subplot_kw={"projection": ccrs.Robinson()},
        gridspec_kw={"hspace": 0.05, "wspace": 0.03},
    )
    axes = np.array(axes).reshape(nrows, ncols)

    norm = TwoSlopeNorm(vcenter=0, vmin=-PCR_VLIM, vmax=PCR_VLIM)

    for r, sc in enumerate(scenarios):
        for c, comp in enumerate(components):
            ax = axes[r, c]

            ax.set_global()
            ax.set_extent([-180, 180, -58, 90], crs=ccrs.PlateCarree())
            ax.add_feature(
                cfeature.LAND.with_scale("110m"),
                facecolor="white", edgecolor="none", zorder=0,
            )
            ax.coastlines(linewidth=0.22, color="0.55", zorder=3)
            ax.axis("off")

            d = table[
                (table["scenario"] == sc) &
                (table["component"] == comp)
            ][["biome_realm", value_col]]

            plot_gdf = gdf.merge(d, on="biome_realm", how="left")

            plot_gdf.plot(
                column=value_col,
                ax=ax,
                transform=ccrs.PlateCarree(),
                cmap=CMAP_DIVERGING,
                norm=norm,
                linewidth=0.0,
                missing_kwds={"color": "white"},
                zorder=2,
            )

            if r == 0:
                ax.set_title(
                    COMP_LABELS.get(comp, comp),
                    fontsize=13, fontweight="bold",
                    fontfamily="sans-serif", pad=6,
                )

            if c == 0:
                ax.text(
                    -0.06, 0.5, SCEN_LABEL[sc],
                    transform=ax.transAxes,
                    rotation=90, va="center", ha="right",
                    fontsize=12, fontfamily="sans-serif",
                    fontweight="bold",
                )

    cax = fig.add_axes([0.20, 0.03, 0.60, 0.014])
    sm  = plt.cm.ScalarMappable(norm=norm, cmap=CMAP_DIVERGING)
    sm.set_array([])
    cb  = fig.colorbar(sm, cax=cax, orientation="horizontal",
                       ticks=[-15, -10, -5, 0, 5, 10, 15], extend="both")
    cb.set_label(
        "Change in GDW area relative to baseline (%)",
        fontsize=12, fontfamily="sans-serif",
    )
    cb.ax.tick_params(labelsize=10.5)
    cb.outline.set_linewidth(0.7)

    out = OUT / "figure4_biome_realm_component_maps.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log(f"Saved: {out}")
# MAIN
# =============================================================================

def main():
    log(f"Saving outputs to: {OUT}")
    # plot_realm_ts()
    # plot_realm_ts_nonlu_area()
    # plot_lollipop()
    # plot_lollipop_decadal_change()
    # plot_lollipop_groundwater_vs_total_longterm_change()
    # plot_biome_realm_pcr_maps()
    # save_realm_area_table()
    # # plot_realm_nonlu_fraction()
    # plot_ssp370_pixel_pct_change()
    # plot_ssp370_pixel_absolute_change()
    # plot_ssp370_future_persistence_class()
    # plot_ssp370_change_in_gdw_months()
    # plot_ssp370_persistence_change_maps()
    # # plot_ssp370_monthly_climatology_pct_change()
    # plot_pixel_driver_direction_all_scenarios()
    # plot_driver_direction_donut()
    plot_figure1_four_panel()
    plot_figure3_lollipop()
    plot_figure4_biome_map()
    plot_realm_ts_only()
    log("Done.")


if __name__ == "__main__":
    main()
