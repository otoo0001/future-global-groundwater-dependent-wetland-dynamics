#!/usr/bin/env python3
"""
dem_based_subgrid_groundwater_depth.py

Creates two PNGs:

1. global_dem_based_subgrid_groundwater_depth.png
2. dem_based_subgrid_groundwater_depth_cdf.png

Uses DEM percentiles to reconstruct sub-grid groundwater depth:

    WTD_sub(p) = WTD_coarse + dzRel_p - dzRel_mean

where:

    dzRel_mean = DEM_average - DEM_minimum
"""

import os
import numpy as np
import xarray as xr
import rasterio
from rasterio.warp import reproject, Resampling

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    HAS_CARTOPY = True
except Exception:
    HAS_CARTOPY = False


WTD_ZARR = "/projects/prjs1222/globgm_output/historical_reference/monthly/gswp3-w5e5.zarr"
PERS_MASK = os.environ.get("WETGDE_PERSISTENCE_MASK", "/path/to/wetgde_max_presence_mask_2015_2019.tif")

TOPO_DIR = "/projects/prjs1222/globgm_input/_data/globgm_input/topography_30sec_03sec"
TOPO_TPL = TOPO_DIR + "/dzRel{p}_topography_parameters_30sec_february_2021_global_covered_with_zero.nc"
DEM_TPL = TOPO_DIR + "/dem_{v}_topography_parameters_30sec_february_2021_global_covered_with_zero.nc"

PCTS = [
    "0000", "0001", "0005", "0010", "0020", "0030", "0040",
    "0050", "0060", "0070", "0080", "0090", "0100"
]

YEARS = slice("2015", "2019")
OUTLIER_PERCENTILE = 98

OUT_DIR = os.environ.get("WETGDE_SENSITIVITY_OUT", "./sensitivity/outputs")
os.makedirs(OUT_DIR, exist_ok=True)

OUT_MAP = f"{OUT_DIR}/global_dem_based_subgrid_groundwater_depth.png"
OUT_CDF = f"{OUT_DIR}/dem_based_subgrid_groundwater_depth_cdf.png"


def log(msg):
    print(msg, flush=True)


def load_mask():
    with rasterio.open(PERS_MASK) as src:
        mask = src.read(1)
        tf = src.transform
        crs = src.crs
        h = src.height
        w = src.width

    gdw = mask >= 1
    return gdw, tf, crs, h, w


def reproject_raster_band_to_mask(src, tf, crs, h, w):
    dst = np.full((h, w), np.nan, dtype=np.float32)

    reproject(
        rasterio.band(src, 1),
        dst,
        dst_transform=tf,
        dst_crs=crs,
        resampling=Resampling.nearest,
    )

    return dst


def topo_stack_at_gdw(gdw, tf, crs, h, w):
    idx = np.where(gdw.ravel())[0]
    stack = np.empty((len(PCTS), idx.size), dtype=np.float32)

    for i, p in enumerate(PCTS):
        fpath = TOPO_TPL.format(p=p)

        with rasterio.open(f"netcdf:{fpath}:dzRel{p}") as src:
            dst = reproject_raster_band_to_mask(src, tf, crs, h, w)

        stack[i, :] = dst.ravel()[idx]
        log(f"Extracted dzRel{p}")

    def grab_dem(var):
        fpath = DEM_TPL.format(v=var)

        with rasterio.open(f"netcdf:{fpath}:dem_{var}") as src:
            dst = reproject_raster_band_to_mask(src, tf, crs, h, w)

        return dst.ravel()[idx]

    dem_average = grab_dem("average")
    dem_minimum = grab_dem("minimum")
    dzrel_mean = dem_average - dem_minimum

    return stack, dzrel_mean, idx


def wtd_at_gdw(gdw, tf, crs, h, w):
    wtd = (
        xr.open_zarr(WTD_ZARR)["wtd"]
        .isel(model=0, layer=0)
        .sel(time=YEARS)
        .mean("time")
    )

    src_arr = wtd.values.astype(np.float32)

    lat = wtd["latitude"].values if "latitude" in wtd.dims else wtd["lat"].values
    lon = wtd["longitude"].values if "longitude" in wtd.dims else wtd["lon"].values

    src_tf = rasterio.transform.from_bounds(
        lon.min(),
        lat.min(),
        lon.max(),
        lat.max(),
        src_arr.shape[1],
        src_arr.shape[0],
    )

    dst = np.full((h, w), np.nan, dtype=np.float32)

    reproject(
        src_arr,
        dst,
        src_transform=src_tf,
        src_crs=crs,
        dst_transform=tf,
        dst_crs=crs,
        resampling=Resampling.nearest,
    )

    idx = np.where(gdw.ravel())[0]
    return dst.ravel()[idx]


def compute_subgrid_wtd(stack, dzrel_mean, wtd_coarse):
    return wtd_coarse[None, :] + stack - dzrel_mean[None, :]


def remove_map_outliers(cell_mean_wtd, percentile=98):
    values = cell_mean_wtd[np.isfinite(cell_mean_wtd)]

    if values.size == 0:
        raise RuntimeError("No valid values found before map filtering.")

    cutoff = np.nanpercentile(values, percentile)

    filtered = cell_mean_wtd.copy()
    filtered[filtered > cutoff] = np.nan

    values_filtered = filtered[np.isfinite(filtered)]

    log(f"Map outlier cutoff P{percentile}: {cutoff:.3f} m")
    log(f"Map pixels before filtering: {values.size}")
    log(f"Map pixels after filtering: {values_filtered.size}")
    log(f"Map pixels removed: {values.size - values_filtered.size}")

    return filtered, cutoff


def plot_global_map(arr, tf, out_png):
    data = np.ma.masked_invalid(arr)

    left = tf.c
    top = tf.f
    right = left + tf.a * arr.shape[1]
    bottom = top + tf.e * arr.shape[0]
    extent = [left, right, bottom, top]

    vmax = np.nanpercentile(arr, 98)
    vmax = max(vmax, 0.1)

    if HAS_CARTOPY:
        fig = plt.figure(figsize=(11, 5.8))
        ax = plt.axes(projection=ccrs.Robinson())
        ax.set_global()

        im = ax.imshow(
            data,
            origin="upper",
            extent=extent,
            transform=ccrs.PlateCarree(),
            cmap="viridis",
            vmin=0,
            vmax=vmax,
            interpolation="nearest",
        )

        ax.coastlines(linewidth=0.4)
        ax.add_feature(cfeature.BORDERS, linewidth=0.15, alpha=0.3)
        ax.axis("off")

    else:
        fig, ax = plt.subplots(figsize=(11, 5.8))

        im = ax.imshow(
            data,
            origin="upper",
            extent=extent,
            cmap="viridis",
            vmin=0,
            vmax=vmax,
            interpolation="nearest",
        )

        ax.axis("off")

    cbar = fig.colorbar(
        im,
        ax=ax,
        orientation="horizontal",
        fraction=0.045,
        pad=0.04,
    )

    cbar.set_label("Sub-grid groundwater depth (m)")

    fig.savefig(out_png, dpi=300, bbox_inches="tight", transparent=True)
    plt.close(fig)


def plot_cdf(values, out_png):
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]

    v = v[(v >= -5) & (v <= 15)]

    x = np.sort(v)
    y = np.arange(1, x.size + 1) / x.size * 100.0

    thresholds = [0, 0.5, 1, 2, 3, 5]

    colors = {
        0: "#08306B",
        0.5: "#2166AC",
        1: "#33A02C",
        2: "#F2A900",
        3: "#DE2D26",
        5: "#67001F",
    }

    fig, ax = plt.subplots(figsize=(8.5, 5.2))

    ax.axvspan(
        -5,
        0,
        color="#DCEAF7",
        alpha=0.45,
        label="<0 m",
    )

    ax.plot(
        x,
        y,
        color="#2166AC",
        linewidth=2.8,
    )

    for t in thresholds:
        pct = np.mean(v <= t) * 100.0

        ax.axvline(
            t,
            color=colors[t],
            linestyle="--",
            linewidth=1.5,
        )

        ax.scatter(
            t,
            pct,
            s=55,
            color=colors[t],
            zorder=5,
        )

        ax.text(
            t + 0.12,
            pct + 1.5,
            f"{pct:.1f}%",
            color=colors[t],
            fontsize=10,
            fontweight="bold",
        )

    legend_handles = [
        Line2D([0], [0], color=colors[0], linestyle="--", lw=1.5, label="≤0 m"),
        Line2D([0], [0], color=colors[0.5], linestyle="--", lw=1.5, label="≤0.5 m"),
        Line2D([0], [0], color=colors[1], linestyle="--", lw=1.5, label="≤1 m"),
        Line2D([0], [0], color=colors[2], linestyle="--", lw=1.5, label="≤2 m"),
        Line2D([0], [0], color=colors[3], linestyle="--", lw=1.5, label="≤3 m"),
        Line2D([0], [0], color=colors[5], linestyle="--", lw=1.5, label="≤5 m"),
        Patch(
            facecolor="#DCEAF7",
            edgecolor="#DCEAF7",
            alpha=0.45,
            label="<0 m",
        ),
    ]

    ax.legend(
        handles=legend_handles,
        frameon=False,
        loc="lower right",
        fontsize=10,
    )

    ax.axhline(
        50,
        color="0.65",
        linestyle=":",
        linewidth=1.0,
    )

    ax.set_xlabel("Sub-grid groundwater depth (m)")
    ax.set_ylabel("Cumulative % of sub-pixels")

    ax.set_xlim(-5, 15)
    ax.set_ylim(0, 100)

    ax.grid(True, linewidth=0.4, alpha=0.35)

    fig.tight_layout()
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main():
    log("Loading GDW mask")
    gdw, tf, crs, h, w = load_mask()

    log(f"GDW pixels: {int(gdw.sum())}")

    log("Loading DEM percentile stack")
    stack, dzrel_mean, idx = topo_stack_at_gdw(gdw, tf, crs, h, w)

    log("Loading WTD")
    wtd_coarse = wtd_at_gdw(gdw, tf, crs, h, w)

    valid = (
        np.isfinite(wtd_coarse)
        & np.isfinite(dzrel_mean)
        & np.all(np.isfinite(stack), axis=0)
    )

    log(f"Valid GDW pixels: {int(valid.sum())}")

    wtd_sub = compute_subgrid_wtd(
        stack[:, valid],
        dzrel_mean[valid],
        wtd_coarse[valid],
    )

    cdf_values = wtd_sub.ravel()
    cdf_values = cdf_values[np.isfinite(cdf_values)]

    log(f"Sub-grid WTD values for CDF: {cdf_values.size}")
    log(f"Fraction ≤0 m: {np.mean(cdf_values <= 0) * 100:.2f}%")
    log(f"Fraction ≤0.5 m: {np.mean(cdf_values <= 0.5) * 100:.2f}%")
    log(f"Fraction ≤1 m: {np.mean(cdf_values <= 1) * 100:.2f}%")
    log(f"Fraction ≤2 m: {np.mean(cdf_values <= 2) * 100:.2f}%")
    log(f"Fraction ≤3 m: {np.mean(cdf_values <= 3) * 100:.2f}%")
    log(f"Fraction ≤5 m: {np.mean(cdf_values <= 5) * 100:.2f}%")

    cell_mean_wtd_valid = np.nanmean(wtd_sub, axis=0).astype(np.float32)

    cell_mean_wtd = np.full(wtd_coarse.size, np.nan, dtype=np.float32)
    cell_mean_wtd[valid] = cell_mean_wtd_valid

    cell_mean_wtd_filtered, cutoff = remove_map_outliers(
        cell_mean_wtd,
        percentile=OUTLIER_PERCENTILE,
    )

    out_flat = np.full(h * w, np.nan, dtype=np.float32)
    out_flat[idx] = cell_mean_wtd_filtered
    out_map = out_flat.reshape(h, w)

    log("Plotting global map")
    plot_global_map(out_map, tf, OUT_MAP)

    log("Plotting CDF")
    plot_cdf(cdf_values, OUT_CDF)

    log(f"Saved: {OUT_MAP}")
    log(f"Saved: {OUT_CDF}")


if __name__ == "__main__":
    main()