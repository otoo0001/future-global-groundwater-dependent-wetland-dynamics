# #!/usr/bin/env python3
# """
# subgrid_wtd_distribution_actual.py

# Sub-grid groundwater depth distribution within GDW pixels at threshold = 5m.

# Formula:
#     gwd_90m(p) = z_90(p) - (Z_mean - 5.0)
#                = dzRel_p - dzRel_mean + 5.0

# where:
#     z_90(p)    = dem_minimum + dzRel_p   (elevation of sub-pixel at percentile p)
#     Z_mean     = dem_average             (mean elevation of ~100 sub-pixels in cell)
#     dzRel_mean = dem_average - dem_minimum

# Key fix: each topo file is reprojected to the persistence mask grid
# before extraction — the topo files are 21600 rows (global) while the
# persistence mask is 16707 rows (83N to 77S). Without alignment the
# row indices are completely wrong.

# Outputs:
#     subgrid_wtd_histogram.png
#     subgrid_wtd_cdf.png
#     subgrid_wtd_summary.txt
# """

# from pathlib import Path
# import gc
# import numpy as np
# import pandas as pd
# import xarray as xr
# import rasterio
# from rasterio.warp import reproject as rio_reproject
# from rasterio.enums import Resampling
# import rasterio.transform as rio_tf_mod

# import matplotlib
# matplotlib.use("Agg")
# import matplotlib.pyplot as plt
# import matplotlib as mpl
# mpl.rcParams["font.family"] = "sans-serif"
# mpl.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans"]

# # =============================================================================
# # PATHS
# # =============================================================================
# TOPO_DIR = Path(
#     "/projects/prjs1222/globgm_input/_data/globgm_input/"
#     "topography_30sec_03sec")

# PERSISTENCE_TIF = Path(
#     "/path/to/scratch/paper_2/revisions/shapefiles_from/"
#     "wetgde_max_presence_mask_2015_2019.tif")

# OUT = Path(
#     "/path/to/scratch/paper_3/new_outputs/"
#     "sensitivity/subgrid_wtd_actual")
# OUT.mkdir(parents=True, exist_ok=True)

# # =============================================================================
# # SETTINGS
# # =============================================================================
# DZREL_PCTS    = [0, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
# DZREL_TAG     = {p: f"{p:04d}" for p in DZREL_PCTS}
# TOPO_SUFFIX   = ("topography_parameters_30sec_february_2021"
#                  "_global_covered_with_zero.nc")

# GDW_CLASSES   = [1, 2, 3]
# WTD_THRESHOLD = 5.0          # coarse WTD threshold (m)
# THRESHOLDS    = [0, 0.5, 1.0, 2.0, 3.0, 5.0]

# THR_COLORS = {
#     0:   "#053061",
#     0.5: "#2166AC",
#     1.0: "#4DAC26",
#     2.0: "#F1B300",
#     3.0: "#D73027",
#     5.0: "#67001F",
# }

# def log(msg):
#     print(f"[{pd.Timestamp.now():%H:%M:%S}] {msg}", flush=True)

# def topo_path(name):
#     return TOPO_DIR / f"{name}_{TOPO_SUFFIX}"

# def dzrel_path(pct):
#     return TOPO_DIR / f"dzRel{DZREL_TAG[pct]}_{TOPO_SUFFIX}"

# # =============================================================================
# # LOAD GDW MASK
# # =============================================================================
# def load_gdw_mask():
#     log("Loading GDW persistence mask ...")
#     with rasterio.open(PERSISTENCE_TIF) as src:
#         arr          = src.read(1)
#         mask_tf      = src.transform
#         mask_crs     = src.crs
#         mask_shape   = arr.shape

#     gdw_mask = np.isin(arr, GDW_CLASSES)
#     log(f"  shape={mask_shape}  GDW pixels={gdw_mask.sum():,}")
#     return gdw_mask, mask_tf, mask_crs, mask_shape

# # =============================================================================
# # REPROJECT TOPO FILE TO PERSISTENCE MASK GRID
# # =============================================================================
# def load_topo_aligned(nc_path, var_name, mask_shape, mask_tf, mask_crs):
#     """
#     Load one topo NC file (21600 x 43200, global) and reproject
#     to the persistence mask grid (16707 x 43200, 83N–77S).
#     Returns aligned float32 array on the mask grid.
#     """
#     ds  = xr.open_dataset(nc_path)
#     arr = ds[var_name].values.astype("float32")
#     lat = ds["lat"].values.astype("float64")
#     lon = ds["lon"].values.astype("float64")
#     ds.close()

#     res    = abs(lat[1] - lat[0])
#     src_tf = rio_tf_mod.from_origin(
#         lon[0] - res/2, lat[0] + res/2, res, res)
#     src_crs = rasterio.crs.CRS.from_epsg(4326)

#     aligned = np.full(mask_shape, np.nan, dtype="float32")
#     rio_reproject(
#         source=arr,
#         destination=aligned,
#         src_transform=src_tf,
#         src_crs=src_crs,
#         src_nodata=np.nan,
#         dst_transform=mask_tf,
#         dst_crs=mask_crs,
#         dst_nodata=np.nan,
#         dst_width=mask_shape[1],
#         dst_height=mask_shape[0],
#         resampling=Resampling.nearest)

#     del arr; gc.collect()
#     return aligned

# # =============================================================================
# # LOAD TOPOGRAPHY AT GDW PIXELS
# # =============================================================================
# def load_topography_at_gdw(gdw_mask, mask_tf, mask_crs, mask_shape):
#     """
#     For each topo file:
#       1. Load and reproject to persistence mask grid
#       2. Extract values at GDW pixel locations only
#     Returns pct_matrix (n_gdw, 13) and dz_mean_gdw (n_gdw,).
#     """
#     gdw_rows, gdw_cols = np.where(gdw_mask)
#     n_gdw = len(gdw_rows)
#     log(f"Extracting topography at {n_gdw:,} GDW pixels ...")

#     # dzRel_mean = dem_average - dem_minimum
#     log("  dem_average (Z_mean) ...")
#     dem_avg = load_topo_aligned(
#         topo_path("dem_average"), "dem_average",
#         mask_shape, mask_tf, mask_crs)
#     z_mean_gdw = dem_avg[gdw_rows, gdw_cols].copy()
#     del dem_avg; gc.collect()

#     log("  dem_minimum ...")
#     dem_min = load_topo_aligned(
#         topo_path("dem_minimum"), "dem_minimum",
#         mask_shape, mask_tf, mask_crs)
#     z_min_gdw = dem_min[gdw_rows, gdw_cols].copy()
#     del dem_min; gc.collect()

#     dz_mean_gdw = np.maximum(z_mean_gdw - z_min_gdw, 0).astype("float32")
#     del z_min_gdw, z_mean_gdw; gc.collect()

#     log(f"  dzRel_mean: median={np.nanmedian(dz_mean_gdw):.2f}m  "
#         f"p90={np.nanpercentile(dz_mean_gdw, 90):.2f}m")

#     # dzRel percentiles
#     pct_matrix = np.full((n_gdw, len(DZREL_PCTS)), np.nan, dtype="float32")
#     for i, pct in enumerate(DZREL_PCTS):
#         log(f"  dzRel{pct:3d} ...")
#         var  = f"dzRel{DZREL_TAG[pct]}"
#         aln  = load_topo_aligned(
#             dzrel_path(pct), var,
#             mask_shape, mask_tf, mask_crs)
#         pct_matrix[:, i] = aln[gdw_rows, gdw_cols]
#         del aln; gc.collect()

#     log(f"  pct_matrix shape: {pct_matrix.shape}")
#     return pct_matrix, dz_mean_gdw

# # =============================================================================
# # COMPUTE SUB-GRID GWD
# # =============================================================================
# def compute_subgrid_gwd(pct_matrix, dz_mean_gdw):
#     """
#     gwd_90m(p) = dzRel_p - dzRel_mean + WTD_THRESHOLD
#                = z_90(p) - (Z_mean - WTD_THRESHOLD)
#     """
#     log(f"Computing sub-grid GWD (threshold={WTD_THRESHOLD}m) ...")

#     valid  = (np.isfinite(dz_mean_gdw) &
#               np.all(np.isfinite(pct_matrix), axis=1))
#     log(f"  valid pixels: {valid.sum():,}")

#     dzm_v  = dz_mean_gdw[valid]
#     pct_v  = pct_matrix[valid]
#     gwd    = pct_v - dzm_v[:, None] + WTD_THRESHOLD   # (n_valid, 13)

#     flat = gwd.ravel()
#     flat = flat[np.isfinite(flat)]

#     log(f"  n sub-pixel values: {len(flat):,}")
#     log(f"  median = {np.median(flat):.2f} m")
#     log(f"  p05    = {np.percentile(flat,  5):.2f} m")
#     log(f"  p95    = {np.percentile(flat, 95):.2f} m")
#     for thr in THRESHOLDS:
#         log(f"  fraction ≤ {thr} m: {np.mean(flat<=thr)*100:.2f}%")

#     return flat

# # =============================================================================
# # PLOT — HISTOGRAM
# # =============================================================================
# def plot_histogram(flat):
#     log("Plotting histogram ...")
#     fig, ax = plt.subplots(figsize=(8, 5), dpi=300)

#     ax.hist(flat, bins=150, range=(-10, 20),
#             density=True, color="#2166AC", alpha=0.70, edgecolor="none")

#     for thr in THRESHOLDS:
#         frac = np.mean(flat <= thr) * 100
#         ax.axvline(thr, color=THR_COLORS[thr], lw=1.5, ls="--",
#                    label=f"\u2264{thr} m: {frac:.1f}%")

#     ax.axvline(np.median(flat), color="#333333", lw=2.0, ls="-",
#                label=f"Median: {np.median(flat):.2f} m")

#     ax.set_xlabel("Groundwater depth at 90 m sub-pixel scale (m)", fontsize=12)
#     ax.set_ylabel("Density", fontsize=12)
#     ax.tick_params(labelsize=10)
#     ax.grid(alpha=0.22, linewidth=0.7)
#     ax.legend(frameon=False, fontsize=10)
#     for sp in ("top", "right"):
#         ax.spines[sp].set_visible(False)

#     fig.tight_layout()
#     out = OUT / "subgrid_wtd_histogram.png"
#     fig.savefig(out, dpi=300, bbox_inches="tight")
#     plt.show()
#     plt.close(fig)
#     log(f"Saved: {out}")

# # =============================================================================
# # PLOT — CDF
# # =============================================================================
# def plot_cdf(flat):
#     log("Plotting CDF ...")
#     sorted_v = np.sort(flat)
#     cdf      = np.arange(1, len(sorted_v)+1) / len(sorted_v) * 100

#     fig, ax = plt.subplots(figsize=(8, 5), dpi=300)

#     ax.plot(sorted_v, cdf, color="#2166AC", lw=2.5)
#     ax.fill_between(sorted_v, 0, cdf, color="#2166AC", alpha=0.08)

#     for thr in THRESHOLDS:
#         frac = np.mean(flat <= thr) * 100
#         ax.axvline(thr, color=THR_COLORS[thr], lw=1.5, ls="--",
#                    label=f"\u2264{thr} m: {frac:.1f}%")
#         ax.plot(thr, frac, "o", color=THR_COLORS[thr], ms=6, zorder=4)

#     ax.axhline(50, color="#CCCCCC", lw=0.8, ls=":", alpha=0.7)
#     ax.fill_betweenx([0, 100], sorted_v.min(), 0,
#                      color="#D6EAF8", alpha=0.25,
#                      label="Inundated (<0 m)")

#     ax.set_xlim(-10, 20)
#     ax.set_ylim(0, 100)
#     ax.set_xlabel("Groundwater depth at 90 m sub-pixel scale (m)", fontsize=12)
#     ax.set_ylabel("Cumulative % of sub-pixels", fontsize=12)
#     ax.tick_params(labelsize=10)
#     ax.grid(alpha=0.22, linewidth=0.7)
#     ax.legend(frameon=False, fontsize=10, loc="lower right")
#     for sp in ("top", "right"):
#         ax.spines[sp].set_visible(False)

#     fig.tight_layout()
#     out = OUT / "subgrid_wtd_cdf.png"
#     fig.savefig(out, dpi=300, bbox_inches="tight")
#     plt.show()
#     plt.close(fig)
#     log(f"Saved: {out}")

# # =============================================================================
# # SAVE SUMMARY
# # =============================================================================
# def save_summary(flat):
#     lines = [
#         f"Formula: gwd_90m(p) = dzRel_p - dzRel_mean + {WTD_THRESHOLD}",
#         f"       = z_90(p) - (Z_mean - {WTD_THRESHOLD})",
#         f"GDW mask: {PERSISTENCE_TIF.name}  (classes {GDW_CLASSES})",
#         f"Fix: topo files reprojected to mask grid before extraction",
#         f"n sub-pixel values: {len(flat):,}",
#         "",
#         f"median: {np.median(flat):.3f} m",
#         f"p05:    {np.percentile(flat,  5):.3f} m",
#         f"p25:    {np.percentile(flat, 25):.3f} m",
#         f"p75:    {np.percentile(flat, 75):.3f} m",
#         f"p95:    {np.percentile(flat, 95):.3f} m",
#         "",
#     ]
#     for thr in THRESHOLDS:
#         lines.append(f"fraction \u2264 {thr:4.1f} m: {np.mean(flat<=thr)*100:.2f}%")

#     out = OUT / "subgrid_wtd_summary.txt"
#     with open(out, "w") as f:
#         f.write("\n".join(lines) + "\n")
#     log(f"Saved: {out}")
#     for line in lines:
#         log(f"  {line}")

# # =============================================================================
# # MAIN
# # =============================================================================
# if __name__ == "__main__":

#     gdw_mask, mask_tf, mask_crs, mask_shape = load_gdw_mask()

#     pct_matrix, dz_mean_gdw = load_topography_at_gdw(
#         gdw_mask, mask_tf, mask_crs, mask_shape)

#     flat = compute_subgrid_gwd(pct_matrix, dz_mean_gdw)

#     plot_histogram(flat)
#     plot_cdf(flat)
#     save_summary(flat)

#     log("Done.")



# #!/usr/bin/env python3
# """
# subgrid_wtd_distribution_actual.py

# Sub-grid groundwater depth distribution within GDW pixels using
# the ACTUAL per-pixel WTD from GLOBGM (GSWP3-W5E5 historical average).

# Formula:
#     gwd_90m(p) = z_90(p) - (Z_mean - WTD_actual)
#                = dzRel_p - dzRel_mean + WTD_actual

# where:
#     WTD_actual = GLOBGM ensemble average WTD for each 30-arcsec pixel
#     Z_mean     = dem_average (mean elevation of ~100 sub-pixels in cell)
#     dzRel_mean = dem_average - dem_minimum
#     dzRel_p    = sub-pixel elevation above minimum at percentile p

# All topo files reprojected to the persistence mask grid (16707 x 43200)
# before extraction to avoid the row-index mismatch bug.

# Outputs:
#     subgrid_wtd_histogram.png
#     subgrid_wtd_cdf.png
#     subgrid_wtd_summary.txt
# """

# from pathlib import Path
# import gc
# import numpy as np
# import pandas as pd
# import xarray as xr
# import rasterio
# from rasterio.warp import reproject as rio_reproject
# from rasterio.enums import Resampling
# import rasterio.transform as rio_tf_mod

# import matplotlib
# matplotlib.use("Agg")
# import matplotlib.pyplot as plt
# import matplotlib as mpl
# mpl.rcParams["font.family"] = "sans-serif"
# mpl.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans"]

# # =============================================================================
# # PATHS
# # =============================================================================
# TOPO_DIR = Path(
#     "/projects/prjs1222/globgm_input/_data/globgm_input/"
#     "topography_30sec_03sec")

# WTD_ZARR = Path(
#     "/projects/prjs1222/globgm_output/historical_reference/average/"
#     "average_gswp3-w5e5.zarr")

# PERSISTENCE_TIF = Path(
#     "/path/to/scratch/paper_2/revisions/shapefiles_from/"
#     "wetgde_max_presence_mask_2015_2019.tif")

# OUT = Path(
#     "/path/to/scratch/paper_3/new_outputs/"
#     "sensitivity/subgrid_wtd_actual")
# OUT.mkdir(parents=True, exist_ok=True)

# # =============================================================================
# # SETTINGS
# # =============================================================================
# DZREL_PCTS  = [0, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
# DZREL_TAG   = {p: f"{p:04d}" for p in DZREL_PCTS}
# TOPO_SUFFIX = ("topography_parameters_30sec_february_2021"
#                "_global_covered_with_zero.nc")

# WTD_VAR    = "wtd"
# WTD_LAYER1 = 1
# WTD_LAYER2 = 2

# GDW_CLASSES = [1, 2, 3]
# THRESHOLDS  = [0, 0.5, 1.0, 2.0, 3.0, 5.0]

# THR_COLORS = {
#     0:   "#053061",
#     0.5: "#2166AC",
#     1.0: "#4DAC26",
#     2.0: "#F1B300",
#     3.0: "#D73027",
#     5.0: "#67001F",
# }

# def log(msg):
#     print(f"[{pd.Timestamp.now():%H:%M:%S}] {msg}", flush=True)

# def topo_path(name):
#     return TOPO_DIR / f"{name}_{TOPO_SUFFIX}"

# def dzrel_path(pct):
#     return TOPO_DIR / f"dzRel{DZREL_TAG[pct]}_{TOPO_SUFFIX}"

# # =============================================================================
# # LOAD GDW MASK
# # =============================================================================
# def load_gdw_mask():
#     log("Loading GDW persistence mask ...")
#     with rasterio.open(PERSISTENCE_TIF) as src:
#         arr        = src.read(1)
#         mask_tf    = src.transform
#         mask_crs   = src.crs
#         mask_shape = arr.shape

#     gdw_mask = np.isin(arr, GDW_CLASSES)
#     log(f"  shape={mask_shape}  GDW pixels={gdw_mask.sum():,}")
#     return gdw_mask, mask_tf, mask_crs, mask_shape

# # =============================================================================
# # REPROJECT TO PERSISTENCE MASK GRID
# # =============================================================================
# def align_to_mask(arr_global, lat_global, lon_global,
#                    mask_shape, mask_tf, mask_crs):
#     """
#     Reproject a global 2D array (21600 x 43200) to the
#     persistence mask grid (16707 x 43200, 83N-77S).
#     """
#     res    = abs(lat_global[1] - lat_global[0])
#     src_tf = rio_tf_mod.from_origin(
#         lon_global[0] - res/2,
#         lat_global[0] + res/2,
#         res, res)
#     src_crs = rasterio.crs.CRS.from_epsg(4326)

#     aligned = np.full(mask_shape, np.nan, dtype="float32")
#     rio_reproject(
#         source=arr_global,
#         destination=aligned,
#         src_transform=src_tf,
#         src_crs=src_crs,
#         src_nodata=np.nan,
#         dst_transform=mask_tf,
#         dst_crs=mask_crs,
#         dst_nodata=np.nan,
#         dst_width=mask_shape[1],
#         dst_height=mask_shape[0],
#         resampling=Resampling.nearest)
#     return aligned

# # =============================================================================
# # LOAD ACTUAL WTD AT GDW PIXELS
# # =============================================================================
# def load_wtd_at_gdw(gdw_mask, mask_shape, mask_tf, mask_crs):
#     """
#     Load GLOBGM GSWP3-W5E5 average WTD, reproject to mask grid,
#     extract values at GDW pixel locations.
#     """
#     log("Loading actual GLOBGM WTD (GSWP3-W5E5 average) ...")
#     ds     = xr.open_zarr(str(WTD_ZARR), consolidated=False)
#     da     = ds[WTD_VAR]
#     wtd_l1 = da.sel(layer=WTD_LAYER1, drop=True)
#     wtd_l2 = da.sel(layer=WTD_LAYER2, drop=True)
#     wtd    = xr.where(np.isfinite(wtd_l1), wtd_l1, wtd_l2)
#     if "model" in wtd.dims:
#         wtd = wtd.squeeze("model")
#     wtd_np = wtd.compute().values.astype("float32")
#     lat_z  = ds["latitude"].values.astype("float64")
#     lon_z  = ds["longitude"].values.astype("float64")
#     ds.close()

#     log(f"  WTD source shape={wtd_np.shape}  "
#         f"lat[0]={lat_z[0]:.3f}  lat[-1]={lat_z[-1]:.3f}")

#     # Reproject WTD to mask grid
#     wtd_aligned = align_to_mask(wtd_np, lat_z, lon_z,
#                                  mask_shape, mask_tf, mask_crs)
#     del wtd_np; gc.collect()

#     gdw_rows, gdw_cols = np.where(gdw_mask)
#     wtd_gdw = wtd_aligned[gdw_rows, gdw_cols].copy()
#     del wtd_aligned; gc.collect()

#     valid = np.isfinite(wtd_gdw) & (wtd_gdw >= 0)
#     log(f"  valid WTD at GDW pixels: {valid.sum():,} / {len(wtd_gdw):,}")
#     log(f"  WTD median={np.nanmedian(wtd_gdw[valid]):.2f}m  "
#         f"p10={np.nanpercentile(wtd_gdw[valid],10):.2f}m  "
#         f"p90={np.nanpercentile(wtd_gdw[valid],90):.2f}m")
#     return wtd_gdw

# # =============================================================================
# # LOAD TOPOGRAPHY AT GDW PIXELS
# # =============================================================================
# def load_topography_at_gdw(gdw_mask, mask_shape, mask_tf, mask_crs):
#     """
#     Load each topo file, reproject to mask grid, extract GDW pixel values.
#     Processes one file at a time to keep peak memory ~4 GB.
#     """
#     gdw_rows, gdw_cols = np.where(gdw_mask)
#     n_gdw = len(gdw_rows)
#     log(f"Extracting topography at {n_gdw:,} GDW pixels ...")

#     def load_nc_aligned(var_name, nc_path):
#         ds  = xr.open_dataset(nc_path)
#         arr = ds[var_name].values.astype("float32")
#         lat = ds["lat"].values.astype("float64")
#         lon = ds["lon"].values.astype("float64")
#         ds.close()
#         aln = align_to_mask(arr, lat, lon, mask_shape, mask_tf, mask_crs)
#         del arr; gc.collect()
#         return aln

#     log("  dem_average ...")
#     dem_avg    = load_nc_aligned("dem_average", topo_path("dem_average"))
#     z_mean_gdw = dem_avg[gdw_rows, gdw_cols].copy()
#     del dem_avg; gc.collect()

#     log("  dem_minimum ...")
#     dem_min    = load_nc_aligned("dem_minimum", topo_path("dem_minimum"))
#     z_min_gdw  = dem_min[gdw_rows, gdw_cols].copy()
#     del dem_min; gc.collect()

#     dz_mean_gdw = np.maximum(z_mean_gdw - z_min_gdw, 0).astype("float32")
#     del z_mean_gdw, z_min_gdw; gc.collect()

#     log(f"  dzRel_mean: median={np.nanmedian(dz_mean_gdw):.2f}m  "
#         f"p90={np.nanpercentile(dz_mean_gdw, 90):.2f}m")

#     pct_matrix = np.full((n_gdw, len(DZREL_PCTS)), np.nan, dtype="float32")
#     for i, pct in enumerate(DZREL_PCTS):
#         log(f"  dzRel{pct:3d} ...")
#         var = f"dzRel{DZREL_TAG[pct]}"
#         aln = load_nc_aligned(var, dzrel_path(pct))
#         pct_matrix[:, i] = aln[gdw_rows, gdw_cols]
#         del aln; gc.collect()

#     log(f"  pct_matrix shape: {pct_matrix.shape}")
#     return pct_matrix, dz_mean_gdw

# # =============================================================================
# # COMPUTE SUB-GRID GWD USING ACTUAL WTD
# # =============================================================================
# def compute_subgrid_gwd(pct_matrix, dz_mean_gdw, wtd_gdw):
#     """
#     gwd_90m(p) = dzRel_p - dzRel_mean + WTD_actual

#     Uses the actual per-pixel GLOBGM WTD rather than a fixed threshold.
#     """
#     log("Computing sub-grid GWD using actual WTD ...")

#     valid = (np.isfinite(wtd_gdw)   & (wtd_gdw >= 0) &
#              np.isfinite(dz_mean_gdw) &
#              np.all(np.isfinite(pct_matrix), axis=1))
#     log(f"  valid pixels: {valid.sum():,}")

#     wtd_v  = wtd_gdw[valid]
#     dzm_v  = dz_mean_gdw[valid]
#     pct_v  = pct_matrix[valid]

#     # Shape: (n_valid, 13) — actual WTD varies per pixel
#     gwd = pct_v - dzm_v[:, None] + wtd_v[:, None]

#     flat = gwd.ravel()
#     flat = flat[np.isfinite(flat)]

#     log(f"  n sub-pixel values: {len(flat):,}")
#     log(f"  median = {np.median(flat):.2f} m")
#     log(f"  p05    = {np.percentile(flat,  5):.2f} m")
#     log(f"  p95    = {np.percentile(flat, 95):.2f} m")
#     for thr in THRESHOLDS:
#         log(f"  fraction \u2264 {thr} m: {np.mean(flat<=thr)*100:.2f}%")

#     return flat

# # =============================================================================
# # PLOT — HISTOGRAM
# # =============================================================================
# def plot_histogram(flat):
#     log("Plotting histogram ...")
#     fig, ax = plt.subplots(figsize=(8, 5), dpi=300)

#     ax.hist(flat, bins=150, range=(-10, 20),
#             density=True, color="#2166AC", alpha=0.70, edgecolor="none")

#     for thr in THRESHOLDS:
#         frac = np.mean(flat <= thr) * 100
#         ax.axvline(thr, color=THR_COLORS[thr], lw=1.5, ls="--",
#                    label=f"\u2264{thr} m: {frac:.1f}%")

#     ax.axvline(np.median(flat), color="#333333", lw=2.0, ls="-",
#                label=f"Median: {np.median(flat):.2f} m")

#     ax.set_xlabel("Groundwater depth at 90 m sub-pixel scale (m)", fontsize=12)
#     ax.set_ylabel("Density", fontsize=12)
#     ax.tick_params(labelsize=10)
#     ax.grid(alpha=0.22, linewidth=0.7)
#     ax.legend(frameon=False, fontsize=10)
#     for sp in ("top", "right"):
#         ax.spines[sp].set_visible(False)

#     fig.tight_layout()
#     out = OUT / "subgrid_wtd_histogram.png"
#     fig.savefig(out, dpi=300, bbox_inches="tight")
#     plt.show()
#     plt.close(fig)
#     log(f"Saved: {out}")

# # =============================================================================
# # PLOT — CDF
# # =============================================================================
# def plot_cdf(flat):
#     log("Plotting CDF ...")
#     sorted_v = np.sort(flat)
#     cdf      = np.arange(1, len(sorted_v)+1) / len(sorted_v) * 100

#     fig, ax = plt.subplots(figsize=(8, 5), dpi=300)

#     ax.plot(sorted_v, cdf, color="#2166AC", lw=2.5)
#     ax.fill_between(sorted_v, 0, cdf, color="#2166AC", alpha=0.08)

#     for thr in THRESHOLDS:
#         frac = np.mean(flat <= thr) * 100
#         ax.axvline(thr, color=THR_COLORS[thr], lw=1.5, ls="--",
#                    label=f"\u2264{thr} m: {frac:.1f}%")
#         ax.plot(thr, frac, "o", color=THR_COLORS[thr], ms=6, zorder=4)

#     ax.axhline(50, color="#CCCCCC", lw=0.8, ls=":", alpha=0.7)
#     ax.fill_betweenx([0, 100], sorted_v.min(), 0,
#                      color="#D6EAF8", alpha=0.25,
#                      label="Inundated (<0 m)")

#     ax.set_xlim(-5, 15)
#     ax.set_ylim(0, 100)
#     ax.set_xlabel("Groundwater depth at 90 m sub-pixel scale (m)", fontsize=12)
#     ax.set_ylabel("Cumulative % of sub-pixels", fontsize=12)
#     ax.tick_params(labelsize=10)
#     ax.grid(alpha=0.22, linewidth=0.7)
#     ax.legend(frameon=False, fontsize=10, loc="lower right")
#     for sp in ("top", "right"):
#         ax.spines[sp].set_visible(False)

#     fig.tight_layout()
#     out = OUT / "subgrid_wtd_cdf.png"
#     fig.savefig(out, dpi=300, bbox_inches="tight")
#     plt.show()
#     plt.close(fig)
#     log(f"Saved: {out}")

# # =============================================================================
# # SAVE SUMMARY
# # =============================================================================
# def save_summary(flat):
#     lines = [
#         "Formula: gwd_90m(p) = dzRel_p - dzRel_mean + WTD_actual",
#         "         Uses actual per-pixel GLOBGM WTD (GSWP3-W5E5 average)",
#         f"GDW mask: {PERSISTENCE_TIF.name}  (classes {GDW_CLASSES})",
#         f"n sub-pixel values: {len(flat):,}",
#         "",
#         f"median: {np.median(flat):.3f} m",
#         f"p05:    {np.percentile(flat,  5):.3f} m",
#         f"p25:    {np.percentile(flat, 25):.3f} m",
#         f"p75:    {np.percentile(flat, 75):.3f} m",
#         f"p95:    {np.percentile(flat, 95):.3f} m",
#         "",
#     ]
#     for thr in THRESHOLDS:
#         lines.append(
#             f"fraction \u2264 {thr:4.1f} m: {np.mean(flat<=thr)*100:.2f}%")

#     out = OUT / "subgrid_wtd_summary.txt"
#     with open(out, "w") as f:
#         f.write("\n".join(lines) + "\n")
#     log(f"Saved: {out}")
#     for line in lines:
#         log(f"  {line}")

# # =============================================================================
# # MAIN
# # =============================================================================
# if __name__ == "__main__":

#     gdw_mask, mask_tf, mask_crs, mask_shape = load_gdw_mask()

#     wtd_gdw = load_wtd_at_gdw(gdw_mask, mask_shape, mask_tf, mask_crs)

#     pct_matrix, dz_mean_gdw = load_topography_at_gdw(
#         gdw_mask, mask_shape, mask_tf, mask_crs)

#     flat = compute_subgrid_gwd(pct_matrix, dz_mean_gdw, wtd_gdw)

#     plot_histogram(flat)
#     plot_cdf(flat)
#     save_summary(flat)

#     log("Done.")





#!/usr/bin/env python3
"""
subgrid_wtd_distribution_actual.py
"""

from pathlib import Path
import gc
import numpy as np
import pandas as pd
import xarray as xr
import rasterio
from rasterio.warp import reproject as rio_reproject
from rasterio.enums import Resampling
import rasterio.transform as rio_tf_mod

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib as mpl

mpl.rcParams["font.family"] = "sans-serif"
mpl.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans"]
mpl.rcParams["agg.path.chunksize"] = 10000

TOPO_DIR = Path(
    "/projects/prjs1222/globgm_input/_data/globgm_input/"
    "topography_30sec_03sec"
)

WTD_ZARR = Path(
    "/projects/prjs1222/globgm_output/historical_reference/average/"
    "average_gswp3-w5e5.zarr"
)

PERSISTENCE_TIF = Path(
    "/path/to/scratch/paper_2/revisions/shapefiles_from/"
    "wetgde_max_presence_mask_2015_2019.tif"
)

OUT = Path(
    "/path/to/scratch/paper_3/new_outputs/"
    "sensitivity/subgrid_wtd_actual"
)
OUT.mkdir(parents=True, exist_ok=True)

DZREL_PCTS = [0, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
DZREL_TAG = {p: f"{p:04d}" for p in DZREL_PCTS}

TOPO_SUFFIX = (
    "topography_parameters_30sec_february_2021"
    "_global_covered_with_zero.nc"
)

WTD_VAR = "wtd"
WTD_LAYER1 = 1
WTD_LAYER2 = 2

GDW_CLASSES = [1, 2, 3]
THRESHOLDS = [0, 0.5, 1.0, 2.0, 3.0, 5.0]

THR_COLORS = {
    0: "#053061",
    0.5: "#2166AC",
    1.0: "#4DAC26",
    2.0: "#F1B300",
    3.0: "#D73027",
    5.0: "#67001F",
}


def log(msg):
    print(f"[{pd.Timestamp.now():%H:%M:%S}] {msg}", flush=True)


def topo_path(name):
    return TOPO_DIR / f"{name}_{TOPO_SUFFIX}"


def dzrel_path(pct):
    return TOPO_DIR / f"dzRel{DZREL_TAG[pct]}_{TOPO_SUFFIX}"


def load_gdw_mask():
    log("Loading GDW persistence mask ...")

    with rasterio.open(PERSISTENCE_TIF) as src:
        arr = src.read(1)
        mask_tf = src.transform
        mask_crs = src.crs
        mask_shape = arr.shape

    gdw_mask = np.isin(arr, GDW_CLASSES)

    log(f"  shape={mask_shape}")
    log(f"  GDW pixels={gdw_mask.sum():,}")

    return gdw_mask, mask_tf, mask_crs, mask_shape


def align_to_mask(arr_global, lat_global, lon_global,
                  mask_shape, mask_tf, mask_crs):

    res = abs(lat_global[1] - lat_global[0])

    src_tf = rio_tf_mod.from_origin(
        lon_global[0] - res / 2,
        lat_global[0] + res / 2,
        res,
        res
    )

    src_crs = rasterio.crs.CRS.from_epsg(4326)

    aligned = np.full(mask_shape, np.nan, dtype="float32")

    rio_reproject(
        source=arr_global,
        destination=aligned,
        src_transform=src_tf,
        src_crs=src_crs,
        src_nodata=np.nan,
        dst_transform=mask_tf,
        dst_crs=mask_crs,
        dst_nodata=np.nan,
        dst_width=mask_shape[1],
        dst_height=mask_shape[0],
        resampling=Resampling.nearest
    )

    return aligned


def load_wtd_at_gdw(gdw_mask, mask_shape, mask_tf, mask_crs):
    log("Loading actual GLOBGM WTD ...")

    ds = xr.open_zarr(str(WTD_ZARR), consolidated=False)

    da = ds[WTD_VAR]

    wtd_l1 = da.sel(layer=WTD_LAYER1, drop=True)
    wtd_l2 = da.sel(layer=WTD_LAYER2, drop=True)

    wtd = xr.where(np.isfinite(wtd_l1), wtd_l1, wtd_l2)

    if "model" in wtd.dims:
        wtd = wtd.squeeze("model")

    wtd_np = wtd.compute().values.astype("float32")
    lat_z = ds["latitude"].values.astype("float64")
    lon_z = ds["longitude"].values.astype("float64")

    ds.close()

    log(f"  WTD source shape={wtd_np.shape}")

    wtd_aligned = align_to_mask(
        wtd_np,
        lat_z,
        lon_z,
        mask_shape,
        mask_tf,
        mask_crs
    )

    del wtd_np
    gc.collect()

    gdw_rows, gdw_cols = np.where(gdw_mask)
    wtd_gdw = wtd_aligned[gdw_rows, gdw_cols].copy()

    del wtd_aligned
    gc.collect()

    valid = np.isfinite(wtd_gdw) & (wtd_gdw >= 0)

    log(f"  valid WTD at GDW pixels: {valid.sum():,} / {len(wtd_gdw):,}")
    log(f"  WTD median={np.nanmedian(wtd_gdw[valid]):.2f} m")
    log(f"  WTD p10={np.nanpercentile(wtd_gdw[valid], 10):.2f} m")
    log(f"  WTD p90={np.nanpercentile(wtd_gdw[valid], 90):.2f} m")

    return wtd_gdw


def load_topography_at_gdw(gdw_mask, mask_shape, mask_tf, mask_crs):
    gdw_rows, gdw_cols = np.where(gdw_mask)
    n_gdw = len(gdw_rows)

    log(f"Extracting topography at {n_gdw:,} GDW pixels ...")

    def load_nc_aligned(var_name, nc_path):
        ds = xr.open_dataset(nc_path)
        arr = ds[var_name].values.astype("float32")
        lat = ds["lat"].values.astype("float64")
        lon = ds["lon"].values.astype("float64")
        ds.close()

        aligned = align_to_mask(
            arr,
            lat,
            lon,
            mask_shape,
            mask_tf,
            mask_crs
        )

        del arr
        gc.collect()

        return aligned

    log("  dem_average ...")
    dem_avg = load_nc_aligned("dem_average", topo_path("dem_average"))
    z_mean_gdw = dem_avg[gdw_rows, gdw_cols].copy()

    del dem_avg
    gc.collect()

    log("  dem_minimum ...")
    dem_min = load_nc_aligned("dem_minimum", topo_path("dem_minimum"))
    z_min_gdw = dem_min[gdw_rows, gdw_cols].copy()

    del dem_min
    gc.collect()

    dz_mean_gdw = np.maximum(z_mean_gdw - z_min_gdw, 0).astype("float32")

    del z_mean_gdw, z_min_gdw
    gc.collect()

    log(f"  dzRel_mean median={np.nanmedian(dz_mean_gdw):.2f} m")
    log(f"  dzRel_mean p90={np.nanpercentile(dz_mean_gdw, 90):.2f} m")

    pct_matrix = np.full(
        (n_gdw, len(DZREL_PCTS)),
        np.nan,
        dtype="float32"
    )

    for i, pct in enumerate(DZREL_PCTS):
        log(f"  dzRel{pct:3d} ...")

        var_name = f"dzRel{DZREL_TAG[pct]}"
        nc_path = dzrel_path(pct)

        aligned = load_nc_aligned(var_name, nc_path)
        pct_matrix[:, i] = aligned[gdw_rows, gdw_cols]

        del aligned
        gc.collect()

    log(f"  pct_matrix shape={pct_matrix.shape}")

    return pct_matrix, dz_mean_gdw


def compute_subgrid_gwd(pct_matrix, dz_mean_gdw, wtd_gdw):
    log("Computing sub-grid GWD using actual WTD ...")

    valid = (
        np.isfinite(wtd_gdw)
        & (wtd_gdw >= 0)
        & np.isfinite(dz_mean_gdw)
        & np.all(np.isfinite(pct_matrix), axis=1)
    )

    log(f"  valid pixels={valid.sum():,}")

    wtd_v = wtd_gdw[valid]
    dzm_v = dz_mean_gdw[valid]
    pct_v = pct_matrix[valid]

    gwd = pct_v - dzm_v[:, None] + wtd_v[:, None]

    flat = gwd.ravel()
    flat = flat[np.isfinite(flat)].astype("float32")

    log(f"  n sub-pixel values={len(flat):,}")
    log(f"  median = {np.median(flat):.2f} m")
    log(f"  p05    = {np.percentile(flat, 5):.2f} m")
    log(f"  p95    = {np.percentile(flat, 95):.2f} m")

    for thr in THRESHOLDS:
        log(f"  fraction ≤ {thr} m: {np.mean(flat <= thr) * 100:.2f}%")

    return flat


def plot_histogram(flat):
    log("Plotting histogram ...")

    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)

    ax.hist(
        flat,
        bins=150,
        range=(-10, 20),
        density=True,
        color="#2166AC",
        alpha=0.70,
        edgecolor="none"
    )

    for thr in THRESHOLDS:
        frac = np.mean(flat <= thr) * 100
        ax.axvline(
            thr,
            color=THR_COLORS[thr],
            lw=1.5,
            ls="--",
            label=f"≤{thr} m: {frac:.1f}%"
        )

    med = np.median(flat)

    ax.axvline(
        med,
        color="#333333",
        lw=2.0,
        ls="-",
        label=f"Median: {med:.2f} m"
    )

    ax.set_xlabel("Groundwater depth at 90 m sub-pixel scale (m)", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.tick_params(labelsize=10)
    ax.grid(alpha=0.22, linewidth=0.7)
    ax.legend(frameon=False, fontsize=10)

    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

    fig.tight_layout()

    out = OUT / "subgrid_wtd_histogram.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)

    log(f"Saved: {out}")


def plot_cdf(flat):
    log("Plotting CDF ...")

    flat_sorted = np.sort(flat)

    x = np.linspace(-5, 15, 5000, dtype="float32")
    y = np.searchsorted(flat_sorted, x, side="right")
    y = y / len(flat_sorted) * 100

    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)

    ax.plot(x, y, color="#2166AC", lw=2.5)

    for thr in THRESHOLDS:
        frac = np.mean(flat <= thr) * 100

        ax.axvline(
            thr,
            color=THR_COLORS[thr],
            lw=1.5,
            ls="--",
            label=f"≤{thr} m: {frac:.1f}%"
        )

        ax.plot(
            thr,
            frac,
            "o",
            color=THR_COLORS[thr],
            ms=6,
            zorder=4
        )

    ax.axhline(
        50,
        color="#CCCCCC",
        lw=0.8,
        ls=":",
        alpha=0.7
    )

    ax.axvspan(
        -5,
        0,
        color="#D6EAF8",
        alpha=0.25,
        label="<0 m"
    )

    ax.set_xlim(-5, 15)
    ax.set_ylim(0, 100)

    ax.set_xlabel("Groundwater depth at 90 m sub-pixel scale (m)", fontsize=12)
    ax.set_ylabel("Cumulative % of sub-pixels", fontsize=12)
    ax.tick_params(labelsize=10)
    ax.grid(alpha=0.22, linewidth=0.7)
    ax.legend(frameon=False, fontsize=10, loc="lower right")

    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

    fig.tight_layout()

    out = OUT / "subgrid_wtd_cdf.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)

    log(f"Saved: {out}")


def save_summary(flat):
    log("Saving summary ...")

    lines = [
        "Formula: gwd_90m(p) = dzRel_p - dzRel_mean + WTD_actual",
        "Uses actual per-pixel GLOBGM WTD, GSWP3-W5E5 historical average",
        f"GDW mask: {PERSISTENCE_TIF.name}",
        f"GDW classes: {GDW_CLASSES}",
        f"n sub-pixel values: {len(flat):,}",
        "",
        f"median: {np.median(flat):.3f} m",
        f"p05:    {np.percentile(flat, 5):.3f} m",
        f"p25:    {np.percentile(flat, 25):.3f} m",
        f"p75:    {np.percentile(flat, 75):.3f} m",
        f"p95:    {np.percentile(flat, 95):.3f} m",
        "",
    ]

    for thr in THRESHOLDS:
        lines.append(
            f"fraction ≤ {thr:4.1f} m: {np.mean(flat <= thr) * 100:.2f}%"
        )

    out = OUT / "subgrid_wtd_summary.txt"

    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")

    log(f"Saved: {out}")

    for line in lines:
        log(f"  {line}")


if __name__ == "__main__":

    gdw_mask, mask_tf, mask_crs, mask_shape = load_gdw_mask()

    wtd_gdw = load_wtd_at_gdw(
        gdw_mask,
        mask_shape,
        mask_tf,
        mask_crs
    )

    pct_matrix, dz_mean_gdw = load_topography_at_gdw(
        gdw_mask,
        mask_shape,
        mask_tf,
        mask_crs
    )

    flat = compute_subgrid_gwd(
        pct_matrix,
        dz_mean_gdw,
        wtd_gdw
    )

    plot_histogram(flat)
    plot_cdf(flat)
    save_summary(flat)

    log("Done.")