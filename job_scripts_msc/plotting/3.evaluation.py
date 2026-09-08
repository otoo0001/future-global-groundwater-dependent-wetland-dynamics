#!/usr/bin/env python3
"""
regional_bubbles_plus_dumbbell_large_text.py

Complete figure:

a. Regional bubble validation map
   Circle colour = precision, TP / (TP + FP)
   Circle size   = total validation area, TP + FP + FN

b. Dumbbell area comparison
   Grey   = total GLWDv2 wetlands in drylands
   Blue   = Rhodes ∩ GLWDv2 wetlands in drylands
   Orange = simulated wetlands in drylands
"""

from pathlib import Path
import csv
import numpy as np
import rasterio
import rasterio.features
from rasterio.warp import reproject
from rasterio.enums import Resampling
from rasterio.transform import xy
from rasterio.windows import Window
from rasterio.windows import transform as window_transform

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.io.shapereader as shpreader

from scipy.ndimage import distance_transform_edt


# =============================================================================
# INPUTS
# =============================================================================
INTERSECTION_TIF = Path(
    "/path/to/scratch/from_projects/validation/input_files/rhodes_2024_gde/Rhodes/"
    "glwd_rhodes_intersection_for_validation/"
    "glwd_rhodes_intersection_binary_no_open.tif"
)

PERSISTENCE_TIF = Path(
    "/path/to/scratch/paper_2/revisions/shapefiles_from/"
    "wetgde_max_presence_mask_2015_2019.tif"
)

DRYLAND_MASK_TIF = Path(
    "/path/to/scratch/from_projects/validation/input_files/koppen_geiger/1991_2020/"
    "koppen_geiger_0p5.tif"
)

GLWD_CLASS_TIF = Path(
    "/path/to/scratch/from_projects/validation/input_files/glwd/"
    "GLWD_v2_delta_combined_classes/GLWD_v2_delta_main_class.tif"
)

OUTDIR = Path(
     "/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/plots/figures_uncertainty_reviewer_final/"
)
OUTDIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# SETTINGS
# =============================================================================
PERSISTENCE_NODATA = -1
GLWD_NODATA = 0

INTERSECTION_POSITIVE = 1
OPEN_WATER_VALUE = 2

COMBINED_CLASSES = [1, 2, 3]
DRYLAND_CLASSES = {4, 5, 6, 7, 8, 9, 10}

PAD = 200
TOLERANCE_KM = 10.0
TILE_SIZE = 1200


# =============================================================================
# HELPERS
# =============================================================================
def load_raster(path):
    with rasterio.open(path) as src:
        arr = src.read(1)
        profile = src.profile.copy()
        transform = src.transform
        crs = src.crs
        nodata = src.nodata

    return arr, profile, transform, crs, nodata


def align_to_grid(
    src_arr,
    src_transform,
    src_crs,
    src_nodata,
    dst_shape,
    dst_transform,
    dst_crs,
    dst_nodata,
    resampling=Resampling.nearest,
):
    out = np.full(dst_shape, dst_nodata, dtype=np.float32)

    reproject(
        source=src_arr,
        destination=out,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=src_nodata,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        dst_nodata=dst_nodata,
        dst_width=dst_shape[1],
        dst_height=dst_shape[0],
        resampling=resampling,
    )

    return out


def write_metrics_txt(path, metrics):
    with open(path, "w") as f:
        for k, v in metrics.items():
            f.write(f"{k}: {v}\n")


def write_area_table_csv(path, records):
    header = [
        "continent",
        "glwd_area_km2",
        "rhodes_glwd_intersection_area_km2",
        "simulated_classes123_area_km2",
        "intersection_over_glwd",
        "simulated_over_glwd",
        "simulated_over_intersection",
    ]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(records)


def get_bbox_from_mask(mask, pad=0):
    rows, cols = np.where(mask)

    if rows.size == 0 or cols.size == 0:
        raise RuntimeError("No positive pixels found.")

    r0 = max(0, rows.min() - pad)
    r1 = min(mask.shape[0], rows.max() + pad + 1)
    c0 = max(0, cols.min() - pad)
    c1 = min(mask.shape[1], cols.max() + pad + 1)

    return r0, r1, c0, c1


def crop_extent(transform, r0, r1, c0, c1):
    west, north = xy(transform, r0, c0, offset="ul")
    east, south = xy(transform, r1 - 1, c1 - 1, offset="lr")
    return [west, east, south, north]


def add_map_base(ax):
    ax.set_global()
    ax.add_feature(
        cfeature.COASTLINE.with_scale("110m"),
        linewidth=0.6,
        edgecolor="0.45",
    )
    ax.set_axis_off()
    ax.set_frame_on(False)


def get_pixel_sizes_km(transform, extent):
    lon_res_deg = abs(transform.a)
    lat_res_deg = abs(transform.e)

    center_lat = 0.5 * (extent[2] + extent[3])

    row_km = lat_res_deg * 111.32
    col_km = lon_res_deg * 111.32 * max(np.cos(np.deg2rad(center_lat)), 1e-6)

    return row_km, col_km, center_lat


def get_tolerance_pad_pixels(transform, extent, tolerance_km):
    row_km, col_km, _ = get_pixel_sizes_km(transform, extent)

    pad_rows = int(np.ceil(tolerance_km / row_km)) + 2
    pad_cols = int(np.ceil(tolerance_km / col_km)) + 2

    return pad_rows, pad_cols, row_km, col_km


def iter_tiles(nrows, ncols, tile_size):
    for rr0 in range(0, nrows, tile_size):
        rr1 = min(nrows, rr0 + tile_size)

        for cc0 in range(0, ncols, tile_size):
            cc1 = min(ncols, cc0 + tile_size)
            yield rr0, rr1, cc0, cc1


# =============================================================================
# CONTINENT AND AREA
# =============================================================================
def build_continent_raster(dst_shape, dst_transform):
    continent_names = [
        "Africa",
        "Asia",
        "Europe",
        "North America",
        "South America",
        "Oceania",
        "Antarctica",
    ]

    continent_to_code = {
        name: i + 1
        for i, name in enumerate(continent_names)
    }

    code_to_continent = {
        v: k
        for k, v in continent_to_code.items()
    }

    shp = shpreader.natural_earth(
        resolution="110m",
        category="cultural",
        name="admin_0_countries",
    )

    shapes = []

    for rec in shpreader.Reader(shp).records():
        cont = rec.attributes["CONTINENT"]

        if cont in continent_to_code:
            shapes.append((rec.geometry, continent_to_code[cont]))

    continent_raster = rasterio.features.rasterize(
        shapes,
        out_shape=dst_shape,
        transform=dst_transform,
        fill=0,
        dtype="uint8",
    )

    return continent_raster, code_to_continent


def get_row_area_km2(transform, nrows):
    lat_res_deg = abs(transform.e)
    lon_res_deg = abs(transform.a)

    row_areas = np.zeros(nrows, dtype=np.float64)

    for r in range(nrows):
        _, lat_center = xy(transform, r, 0, offset="center")

        pixel_height_km = lat_res_deg * 111.32
        pixel_width_km = lon_res_deg * 111.32 * max(
            np.cos(np.deg2rad(lat_center)),
            1e-12,
        )

        row_areas[r] = pixel_height_km * pixel_width_km

    return row_areas


def area_by_continent_km2(mask, continent_arr, row_areas_km2, code_to_continent):
    out = {}

    valid_conts = sorted(
        np.unique(continent_arr[continent_arr > 0]).astype(int)
    )

    for cont_code in valid_conts:
        cont_name = code_to_continent.get(cont_code, f"Continent_{cont_code}")

        if cont_name == "Antarctica":
            continue

        cont_mask = mask & (continent_arr == cont_code)

        if not cont_mask.any():
            out[cont_name] = 0.0
            continue

        row_counts = cont_mask.sum(axis=1).astype(np.float64)
        out[cont_name] = float(np.sum(row_counts * row_areas_km2))

    return out


def build_global_record(records):
    global_rec = {
        "continent": "Global",
        "glwd_area_km2": float(sum(r["glwd_area_km2"] for r in records)),
        "rhodes_glwd_intersection_area_km2": float(
            sum(r["rhodes_glwd_intersection_area_km2"] for r in records)
        ),
        "simulated_classes123_area_km2": float(
            sum(r["simulated_classes123_area_km2"] for r in records)
        ),
    }

    g = global_rec["glwd_area_km2"]
    r = global_rec["rhodes_glwd_intersection_area_km2"]
    s = global_rec["simulated_classes123_area_km2"]

    global_rec["intersection_over_glwd"] = r / g if g > 0 else np.nan
    global_rec["simulated_over_glwd"] = s / g if g > 0 else np.nan
    global_rec["simulated_over_intersection"] = s / r if r > 0 else np.nan

    return global_rec


# =============================================================================
# VALIDATION
# =============================================================================
def evaluate_combined_tiled(
    pred,
    ref,
    inter_transform,
    extent_crop,
    crop_row_offset,
    crop_col_offset,
    tolerance_km,
):
    reference_positive_count = int(ref.sum())
    predicted_positive_count = int(pred.sum())

    crop_row_km, crop_col_km, crop_center_lat = get_pixel_sizes_km(
        inter_transform,
        extent_crop,
    )

    pad_rows_tol, pad_cols_tol, _, _ = get_tolerance_pad_pixels(
        inter_transform,
        extent_crop,
        tolerance_km,
    )

    if predicted_positive_count == 0:
        tp_pred_mask = np.zeros(ref.shape, dtype=bool)
        fp_mask = np.zeros(ref.shape, dtype=bool)
        hit_ref_mask = np.zeros(ref.shape, dtype=bool)

        metrics = {
            "allowable_distance_km": float(tolerance_km),
            "reference_positive_pixels": int(reference_positive_count),
            "predicted_positive_pixels": 0,
            "tolerant_true_positive_pred_pixels": 0,
            "tolerant_false_alarm_pixels": 0,
            "tolerant_reference_hits": 0,
            "tolerant_reference_misses": int(reference_positive_count),
            "precision": np.nan,
            "recall": 0.0 if reference_positive_count > 0 else np.nan,
            "f1": np.nan,
        }

        return metrics, tp_pred_mask, fp_mask, hit_ref_mask

    dist_to_ref = distance_transform_edt(
        ~ref,
        sampling=(crop_row_km, crop_col_km),
    )

    tp_pred_mask = pred & (dist_to_ref <= tolerance_km)
    fp_mask = pred & (dist_to_ref > tolerance_km)

    tp_pred_count = int(tp_pred_mask.sum())
    fp_count = int(fp_mask.sum())

    hit_ref_mask = np.zeros(ref.shape, dtype=bool)

    nrows, ncols = pred.shape

    for tr0, tr1, tc0, tc1 in iter_tiles(nrows, ncols, TILE_SIZE):
        hr0 = max(0, tr0 - pad_rows_tol)
        hr1 = min(nrows, tr1 + pad_rows_tol)
        hc0 = max(0, tc0 - pad_cols_tol)
        hc1 = min(ncols, tc1 + pad_cols_tol)

        pred_halo = pred[hr0:hr1, hc0:hc1]

        if not pred_halo.any():
            continue

        ref_halo = ref[hr0:hr1, hc0:hc1]

        halo_extent = crop_extent(
            inter_transform,
            crop_row_offset + hr0,
            crop_row_offset + hr1,
            crop_col_offset + hc0,
            crop_col_offset + hc1,
        )

        row_km_h, col_km_h, _ = get_pixel_sizes_km(
            inter_transform,
            halo_extent,
        )

        dist_to_pred_halo = distance_transform_edt(
            ~pred_halo,
            sampling=(row_km_h, col_km_h),
        )

        core_r0 = tr0 - hr0
        core_r1 = core_r0 + (tr1 - tr0)
        core_c0 = tc0 - hc0
        core_c1 = core_c0 + (tc1 - tc0)

        hit_core = (
            ref_halo[core_r0:core_r1, core_c0:core_c1]
            & (
                dist_to_pred_halo[
                    core_r0:core_r1,
                    core_c0:core_c1,
                ]
                <= tolerance_km
            )
        )

        hit_ref_mask[tr0:tr1, tc0:tc1] |= hit_core

    hit_ref_count = int(hit_ref_mask.sum())
    fn_count = int(reference_positive_count - hit_ref_count)

    precision = tp_pred_count / predicted_positive_count
    recall = hit_ref_count / reference_positive_count if reference_positive_count > 0 else np.nan

    f1 = (
        2 * precision * recall / (precision + recall)
        if np.isfinite(precision)
        and np.isfinite(recall)
        and (precision + recall) > 0
        else np.nan
    )

    metrics = {
        "predicted_label": "classes_1_to_3_combined",
        "allowable_distance_km": float(tolerance_km),
        "reference_positive_pixels": int(reference_positive_count),
        "predicted_positive_pixels": int(predicted_positive_count),
        "tolerant_true_positive_pred_pixels": int(tp_pred_count),
        "tolerant_false_alarm_pixels": int(fp_count),
        "tolerant_reference_hits": int(hit_ref_count),
        "tolerant_reference_misses": int(fn_count),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "approx_row_pixel_size_km": float(crop_row_km),
        "approx_col_pixel_size_km": float(crop_col_km),
        "crop_center_latitude": float(crop_center_lat),
        "tile_size": int(TILE_SIZE),
        "pad_rows_tolerance": int(pad_rows_tol),
        "pad_cols_tolerance": int(pad_cols_tol),
    }

    return metrics, tp_pred_mask, fp_mask, hit_ref_mask


def compute_continent_validation_records(
    tp_pred_mask,
    fp_mask,
    ref,
    hit_ref_mask,
    continent_crop,
    row_areas_km2,
    code_to_continent,
):
    fn_mask = ref & (~hit_ref_mask)

    records = []

    cont_codes = sorted(
        np.unique(continent_crop[continent_crop > 0]).astype(int)
    )

    for cont_code in cont_codes:
        cont = code_to_continent.get(cont_code, f"Continent_{cont_code}")

        if cont == "Antarctica":
            continue

        cmask = continent_crop == cont_code

        tp_rows = (tp_pred_mask & cmask).sum(axis=1).astype(float)
        fp_rows = (fp_mask & cmask).sum(axis=1).astype(float)
        fn_rows = (fn_mask & cmask).sum(axis=1).astype(float)

        tp_area = float(np.sum(tp_rows * row_areas_km2))
        fp_area = float(np.sum(fp_rows * row_areas_km2))
        fn_area = float(np.sum(fn_rows * row_areas_km2))

        precision = (
            tp_area / (tp_area + fp_area)
            if (tp_area + fp_area) > 0
            else np.nan
        )

        recall = (
            tp_area / (tp_area + fn_area)
            if (tp_area + fn_area) > 0
            else np.nan
        )

        records.append(
            {
                "continent": cont,
                "tp_area_km2": tp_area,
                "fp_area_km2": fp_area,
                "fn_area_km2": fn_area,
                "precision": precision,
                "recall": recall,
                "total_validation_area_km2": tp_area + fp_area + fn_area,
            }
        )

    return records


def get_continent_centroids():
    return {
        "Africa": (20, 2),
        "Asia": (80, 35),
        "Europe": (15, 52),
        "North America": (-105, 45),
        "South America": (-60, -18),
        "Oceania": (135, -25),
    }


# =============================================================================
# PLOTTING
# =============================================================================
def plot_panel_b_dumbbell(ax, records):
    records_plot = [
        r for r in records
        if r["continent"] != "Antarctica"
    ]

    records_plot.append(build_global_record(records_plot))

    continents = [r["continent"] for r in records_plot]

    glwd = np.array(
        [r["glwd_area_km2"] for r in records_plot],
        dtype=float,
    ) / 1_000_000

    ref_area = np.array(
        [r["rhodes_glwd_intersection_area_km2"] for r in records_plot],
        dtype=float,
    ) / 1_000_000

    sim = np.array(
        [r["simulated_classes123_area_km2"] for r in records_plot],
        dtype=float,
    ) / 1_000_000

    y = np.arange(len(continents))

    ax.hlines(
        y,
        0,
        glwd,
        color="0.86",
        linewidth=11,
        zorder=1,
    )

    ax.hlines(
        y,
        ref_area,
        sim,
        color="0.25",
        linewidth=1.7,
        zorder=3,
    )
    ax.scatter(
        sim,
        y,
        s=85,
        color="#e67e22",
        label="Simulated",
        zorder=5,
    )
    ax.scatter(
        glwd,
        y,
        s=65,
        color="0.65",
        label="Total GLWDv2",
        zorder=2,
    )

    ax.scatter(
        ref_area,
        y,
        s=85,
        color="#1f4e79",
        label="Rhodes ∩ GLWDv2",
        zorder=4,
    )



    ax.set_yticks(y)
    ax.set_yticklabels(continents, fontsize=15)
    ax.invert_yaxis()

    ax.set_xlabel("Wetland area (million km²)", fontsize=17)

    ax.grid(
        axis="x",
        color="0.90",
        linewidth=0.8,
    )

    ax.set_axisbelow(True)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.tick_params(
        axis="both",
        labelsize=15,
        width=1.2,
        length=5,
    )

    ax.legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.25),
        ncol=3,
        fontsize=14,
        handletextpad=0.8,
        columnspacing=1.8,
    )


def plot_regional_bubbles_plus_dumbbell(
    paths,
    validation_records,
    area_records,
):
    centroids = get_continent_centroids()

    fig = plt.figure(figsize=(12.5, 12.5))

    gs = fig.add_gridspec(
        2,
        1,
        height_ratios=[3.2, 1.35],
        hspace=0.16,
)

    ax_map = fig.add_subplot(
        gs[0],
        projection=ccrs.Robinson(),
    )

    add_map_base(ax_map)

    max_area = max(
        r["total_validation_area_km2"]
        for r in validation_records
    )

    sc = None

    for rec in validation_records:
        cont = rec["continent"]

        if cont not in centroids:
            continue

        lon, lat = centroids[cont]

        size = 120 + 1650 * rec["total_validation_area_km2"] / max_area

        sc = ax_map.scatter(
            lon,
            lat,
            s=size,
            c=rec["precision"],
            cmap="viridis",
            vmin=0,
            vmax=1,
            transform=ccrs.PlateCarree(),
            edgecolor="black",
            linewidth=0.8,
            zorder=4,
        )

        ax_map.text(
            lon,
            lat - 8,
            cont,
            transform=ccrs.PlateCarree(),
            ha="center",
            va="top",
            fontsize=14,
            fontweight="medium",
            zorder=5,
        )

    cbar = plt.colorbar(
        sc,
        ax=ax_map,
        orientation="horizontal",
        fraction=0.055,
        pad=0.025,
    )

    cbar.set_label(
        "Precision, TP / (TP + FP)",
        fontsize=16,
    )

    cbar.ax.tick_params(labelsize=14)

    ax_map.text(
        -0.08,
        1.03,
        "(a)",
        transform=ax_map.transAxes,
        fontsize=22,
        fontweight="bold",
        va="top",
        ha="left",
    )

    ax_bar = fig.add_subplot(gs[1])

    plot_panel_b_dumbbell(
        ax_bar,
        area_records,
    )

    ax_bar.text(
        -0.08,
        1.10,
        "(b)",
        transform=ax_bar.transAxes,
        fontsize=22,
        fontweight="bold",
        va="top",
        ha="left",
    )

    for path in paths:
        suffix = Path(path).suffix.lower()

        if suffix == ".svg":
            plt.savefig(
                path,
                format="svg",
                bbox_inches="tight",
                pad_inches=0.08,
                facecolor="white",
                transparent=False,
            )
        elif suffix == ".pdf":
            plt.savefig(
                path,
                bbox_inches="tight",
                pad_inches=0.08,
            )
        else:
            plt.savefig(
                path,
                dpi=600,
                bbox_inches="tight",
                pad_inches=0.08,
            )

    plt.close(fig)


# =============================================================================
# MAIN
# =============================================================================
def main():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 15,
            "axes.labelsize": 17,
            "axes.titlesize": 17,
            "xtick.labelsize": 15,
            "ytick.labelsize": 15,
            "legend.fontsize": 14,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.dpi": 600,
        }
    )

    print("=" * 70)
    print("Creating regional bubble map plus dumbbell area comparison")
    print("=" * 70)

    print("[1/10] Loading rasters")

    intersection, _, inter_transform, inter_crs, _ = load_raster(
        INTERSECTION_TIF
    )

    persistence, _, pers_transform, pers_crs, pers_nodata = load_raster(
        PERSISTENCE_TIF
    )

    dryland, _, dry_transform, dry_crs, dry_nodata = load_raster(
        DRYLAND_MASK_TIF
    )

    glwd_class, _, glwd_transform, glwd_crs, glwd_nodata = load_raster(
        GLWD_CLASS_TIF
    )

    print("[2/10] Aligning persistence raster")

    persistence_aligned = align_to_grid(
        src_arr=persistence.astype(np.float32),
        src_transform=pers_transform,
        src_crs=pers_crs,
        src_nodata=(
            float(pers_nodata)
            if pers_nodata is not None
            else float(PERSISTENCE_NODATA)
        ),
        dst_shape=intersection.shape,
        dst_transform=inter_transform,
        dst_crs=inter_crs,
        dst_nodata=float(PERSISTENCE_NODATA),
        resampling=Resampling.nearest,
    ).astype(np.int16)

    print("[3/10] Aligning dryland raster")

    dryland_aligned = align_to_grid(
        src_arr=dryland.astype(np.float32),
        src_transform=dry_transform,
        src_crs=dry_crs,
        src_nodata=(
            float(dry_nodata)
            if dry_nodata is not None
            else np.nan
        ),
        dst_shape=intersection.shape,
        dst_transform=inter_transform,
        dst_crs=inter_crs,
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )

    dryland_safe_int = np.where(
        np.isfinite(dryland_aligned),
        dryland_aligned,
        -9999,
    ).astype(np.int16)

    dryland_mask = (
        np.isfinite(dryland_aligned)
        & np.isin(dryland_safe_int, list(DRYLAND_CLASSES))
    )

    print("[4/10] Aligning GLWD raster")

    glwd_aligned = align_to_grid(
        src_arr=glwd_class.astype(np.float32),
        src_transform=glwd_transform,
        src_crs=glwd_crs,
        src_nodata=(
            float(glwd_nodata)
            if glwd_nodata is not None
            else float(GLWD_NODATA)
        ),
        dst_shape=intersection.shape,
        dst_transform=inter_transform,
        dst_crs=inter_crs,
        dst_nodata=float(GLWD_NODATA),
        resampling=Resampling.nearest,
    ).astype(np.int16)

    print("[5/10] Building continent raster")

    continent_raster, code_to_continent = build_continent_raster(
        dst_shape=intersection.shape,
        dst_transform=inter_transform,
    )

    print("[6/10] Cropping comparison domain")

    comparison_domain = (
        ((intersection == INTERSECTION_POSITIVE) & dryland_mask)
        | (
            np.isin(persistence_aligned, COMBINED_CLASSES)
            & dryland_mask
        )
    )

    r0, r1, c0, c1 = get_bbox_from_mask(
        comparison_domain,
        pad=PAD,
    )

    intersection_crop = intersection[r0:r1, c0:c1]
    persistence_crop = persistence_aligned[r0:r1, c0:c1]
    dryland_crop = dryland_mask[r0:r1, c0:c1]
    glwd_crop = glwd_aligned[r0:r1, c0:c1]
    continent_crop = continent_raster[r0:r1, c0:c1]

    extent_crop = crop_extent(
        inter_transform,
        r0,
        r1,
        c0,
        c1,
    )

    print("[7/10] Preparing validation masks")

    valid = (
        np.isfinite(persistence_crop)
        & (persistence_crop != PERSISTENCE_NODATA)
        & dryland_crop
    )

    ref = (
        (intersection_crop == INTERSECTION_POSITIVE)
        & dryland_crop
        & valid
    ).astype(bool)

    pred_combined = (
        np.isin(persistence_crop, COMBINED_CLASSES)
        & dryland_crop
        & valid
    ).astype(bool)

    glwd_wetland = (
        (glwd_crop != GLWD_NODATA)
        & dryland_crop
        & valid
    ).astype(bool)

    print(f"    valid pixels: {int(valid.sum()):,}")
    print(f"    reference pixels: {int(ref.sum()):,}")
    print(f"    simulated pixels: {int(pred_combined.sum()):,}")
    print(f"    GLWD wetland pixels: {int(glwd_wetland.sum()):,}")

    print("[8/10] Computing 10 km tolerance validation")

    metrics, tp_pred_mask, fp_mask, hit_ref_mask = evaluate_combined_tiled(
        pred=pred_combined,
        ref=ref,
        inter_transform=inter_transform,
        extent_crop=extent_crop,
        crop_row_offset=r0,
        crop_col_offset=c0,
        tolerance_km=TOLERANCE_KM,
    )

    print(f"    precision: {metrics['precision']}")
    print(f"    recall: {metrics['recall']}")
    print(f"    f1: {metrics['f1']}")

    print("[9/10] Computing area summaries")

    crop_transform = window_transform(
        Window(c0, r0, c1 - c0, r1 - r0),
        inter_transform,
    )

    row_areas_km2 = get_row_area_km2(
        crop_transform,
        intersection_crop.shape[0],
    )

    glwd_area = area_by_continent_km2(
        glwd_wetland,
        continent_crop,
        row_areas_km2,
        code_to_continent,
    )

    ref_area = area_by_continent_km2(
        ref,
        continent_crop,
        row_areas_km2,
        code_to_continent,
    )

    sim_area = area_by_continent_km2(
        pred_combined,
        continent_crop,
        row_areas_km2,
        code_to_continent,
    )

    continents_out = sorted(
        set(glwd_area.keys())
        | set(ref_area.keys())
        | set(sim_area.keys()),
        key=lambda c: glwd_area.get(c, 0.0),
        reverse=True,
    )

    area_records = []

    for cont in continents_out:
        g = float(glwd_area.get(cont, 0.0))
        r = float(ref_area.get(cont, 0.0))
        s = float(sim_area.get(cont, 0.0))

        area_records.append(
            {
                "continent": cont,
                "glwd_area_km2": g,
                "rhodes_glwd_intersection_area_km2": r,
                "simulated_classes123_area_km2": s,
                "intersection_over_glwd": r / g if g > 0 else np.nan,
                "simulated_over_glwd": s / g if g > 0 else np.nan,
                "simulated_over_intersection": s / r if r > 0 else np.nan,
            }
        )

    validation_records = compute_continent_validation_records(
        tp_pred_mask=tp_pred_mask,
        fp_mask=fp_mask,
        ref=ref,
        hit_ref_mask=hit_ref_mask,
        continent_crop=continent_crop,
        row_areas_km2=row_areas_km2,
        code_to_continent=code_to_continent,
    )

    print("[10/10] Writing outputs")

    write_metrics_txt(
        OUTDIR / "regional_bubbles_validation_metrics.txt",
        metrics,
    )

    write_area_table_csv(
        OUTDIR / "regional_bubbles_area_records.csv",
        area_records,
    )

    plot_regional_bubbles_plus_dumbbell(
        paths=[
            OUTDIR / "evaluation_glwd_rohdes.png",
            OUTDIR / "evaluation_glwd_rohdes.pdf",
            OUTDIR / "evaluation_glwd_rohdes.svg",
        ],
        validation_records=validation_records,
        area_records=area_records,
    )

    print("Wrote:")
    print(OUTDIR / "evaluation_glwd_rohdes.png")
    print(OUTDIR / "evaluation_glwd_rohdes.pdf")
    print(OUTDIR / "evaluation_glwd_rohdes.svg")
    print("Done.")


if __name__ == "__main__":
    main()