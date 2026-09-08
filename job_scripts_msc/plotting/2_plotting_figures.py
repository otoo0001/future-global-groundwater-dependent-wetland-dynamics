# #!/usr/bin/env python3
# from pathlib import Path
# import numpy as np
# import pandas as pd
# import xarray as xr

# import matplotlib
# matplotlib.use("Agg")
# import matplotlib.pyplot as plt
# import matplotlib.ticker
# from matplotlib.colors import (
#     TwoSlopeNorm, ListedColormap,
#     BoundaryNorm, LinearSegmentedColormap,
# )
# from matplotlib.lines import Line2D
# from matplotlib.patches import Patch

# import geopandas as gpd
# import cartopy.crs as ccrs
# import cartopy.feature as cfeature

# import matplotlib as mpl
# mpl.rcParams["font.family"] = "sans-serif"
# mpl.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Helvetica", "Liberation Sans"]

# try:
#     import cmocean
#     CMAP_DIVERGING = cmocean.cm.curl
# except ImportError:
#     CMAP_DIVERGING = plt.get_cmap("RdBu")

# # =============================================================================
# # PATHS
# # =============================================================================

# BASE      = Path("/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3")
# ENSEMBLE  = BASE / "ensemble"
# GCMS_BASE = BASE / "gcms"
# OUT       = BASE / "plots" / "figures_v2806"
# WWF_SHAPE = "/path/to/scratch/paper_3/inputs/biomes/biomes/wwf_terr_ecos.shp"
# OUT.mkdir(parents=True, exist_ok=True)

# # =============================================================================
# # SETTINGS
# # =============================================================================

# GCMS      = ["gfdl-esm4", "ipsl-cm6a-lr", "mpi-esm1-2-hr", "mri-esm2-0", "ukesm1-0-ll"]
# SCENARIOS = ["historical", "ssp126", "ssp370", "ssp585"]
# FUTURE_S  = ["ssp126", "ssp370", "ssp585"]

# COL_TOTAL   = "area_gdw_km2"
# COL_NONLU   = "area_gdw_nonlu_km2"
# COL_GW_ONLY = "area_gdw_freeze_lu_km2"
# COL_LU_ONLY = "area_gdw_freeze_wtd_km2"

# PCR_COLS = {
#     "Groundwater Impact Only":       COL_NONLU,
#     "Land-use Impact Only":          COL_LU_ONLY,
#     "Groundwater + Land-use Impact": COL_TOTAL,
# }
# PCR_COLS_NORM = PCR_COLS.copy()

# TS_VAR         = COL_TOTAL
# PIXEL_VAR      = COL_TOTAL
# HIST_BASE      = (1995, 2004)
# HIST_LAST      = (2005, 2014)
# FUT_LAST       = (2041, 2050)
# JOIN_YEAR      = 2015
# SMOOTH_YEARS   = 5
# BASELINE_MIN   = 0.01
# PCR_VLIM       = 15
# ABS_PERCENTILE = 95

# SCEN_COLOR = {
#     "historical": "#333333",
#     "ssp126":     "#1a9850",
#     "ssp370":     "#fdae61",
#     "ssp585":     "#d73027",
# }
# SCEN_LABEL = {
#     "historical": "Historical",
#     "ssp126":     "SSP1-2.6",
#     "ssp370":     "SSP3-7.0",
#     "ssp585":     "SSP5-8.5",
# }

# MERGE_TO    = {"AA", "OC"}
# MERGED_CODE = "AO"
# REALM_NAME  = {
#     "AT": "Afrotropical", "IM": "Indo-Malayan",
#     "NA": "Nearctic",     "NT": "Neotropical",
#     "PA": "Palearctic",   MERGED_CODE: "Australasian & Oceanian",
# }
# REALM_ORDER = [
#     "Nearctic", "Neotropical", "Afrotropical",
#     "Palearctic", "Indo-Malayan", "Australasian & Oceanian",
# ]

# FS = {
#     "panel":  22,
#     "title":  20,
#     "axis":   18,
#     "tick":   16,
#     "legend": 16,
#     "value":  16,
#     "small":  14,
# }
# S = 4.5

# _RDGREY_BU = LinearSegmentedColormap.from_list(
#     "rdgrey_bu",
#     ["#67001F","#B2182B","#D6604D","#F4A582","#FDDBC7",
#      "#AAAAAA",
#      "#D1E5F0","#92C5DE","#4393C3","#2166AC","#053061"],
#     N=512,
# )
# _RDGREY_BU.set_bad(color="white")

# # =============================================================================
# # HELPERS
# # =============================================================================

# def log(msg):
#     print(f"[{pd.Timestamp.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

# def smooth(s):
#     return s.rolling(SMOOTH_YEARS, center=True,
#                      min_periods=max(1, SMOOTH_YEARS // 2)).mean()

# def normalize_realm_codes(s):
#     x = s.astype(str).replace({r: MERGED_CODE for r in MERGE_TO})
#     return x.map(REALM_NAME).fillna(x)

# def period_for_scenario(sc):
#     return HIST_LAST if sc == "historical" else FUT_LAST

# def parquet_path(gcm, sc):
#     return GCMS_BASE / gcm / sc / "parquet" / f"wetGDE_area_{gcm}_{sc}.parquet"

# def timmean_path(sc):
#     y1, y2 = period_for_scenario(sc)
#     return ENSEMBLE / sc / "nc" / f"wetGDE_ensemble_timmean_{sc}_{y1}-{y2}.nc"

# def monthly_clim_path(sc):
#     y1, y2 = period_for_scenario(sc)
#     return ENSEMBLE / sc / "nc" / f"wetGDE_ensemble_monthly_climatology_{sc}_{y1}-{y2}.nc"

# def add_map_background(ax, white=False):
#     ax.set_global()
#     ax.set_extent([-180, 180, -58, 90], crs=ccrs.PlateCarree())
#     ax.add_feature(cfeature.LAND.with_scale("110m"),
#                    facecolor="white" if white else "#f5f5f2",
#                    edgecolor="none", zorder=0)
#     ax.coastlines(linewidth=0.7, color="0.50", zorder=3)
#     ax.axis("off")

# def discrete_cmap_norm(vcm):
#     vals   = sorted(vcm)
#     cmap   = ListedColormap([vcm[v] for v in vals])
#     bounds = [vals[0]-0.5] + [(vals[i]+vals[i+1])/2 for i in range(len(vals)-1)] + [vals[-1]+0.5]
#     return cmap, BoundaryNorm(bounds, cmap.N)

# def open_timmean_da(sc, var):
#     path = timmean_path(sc)
#     if not path.exists(): raise FileNotFoundError(path)
#     ds = xr.open_dataset(path, decode_times=True, mask_and_scale=True)
#     if var not in ds: raise KeyError(f"{var} missing in {path}")
#     da = ds[var]
#     return da.isel(time=0) if "time" in da.dims else da
# def open_monthly_clim_da(sc, var):
#     path = monthly_clim_path(sc)

#     if not path.exists():
#         raise FileNotFoundError(path)

#     ds = xr.open_dataset(
#         path,
#         decode_times=True,
#         mask_and_scale=True,
#     )

#     if var not in ds:
#         raise KeyError(f"{var} missing in {path}")

#     da = ds[var]

#     if "time" in da.dims and "month" not in da.dims:
#         da = da.assign_coords(month=da["time"].dt.month).swap_dims({"time": "month"})
#         da = da.drop_vars("time")

#     return da

# # =============================================================================
# # PARQUET LOADERS
# # =============================================================================

# def extract_realm(df):
#     d = df.copy()
#     if "BIOME_ID_REALM" in d.columns:
#         code = d["BIOME_ID_REALM"].astype(str).str.split("_", n=1).str[-1]
#         d["realm"] = normalize_realm_codes(code)
#     elif "realm" in d.columns:
#         d["realm"] = normalize_realm_codes(d["realm"].astype(str))
#     else:
#         raise KeyError("No BIOME_ID_REALM or realm column found")
#     return d[~d["realm"].isin(["AN","Antarctica","Antarctic"])].copy()

# def load_parquet_all(cols):
#     frames = []
#     for gcm in GCMS:
#         for sc in SCENARIOS:
#             p = parquet_path(gcm, sc)
#             if not p.exists(): log(f"[missing] {p}"); continue
#             df   = pd.read_parquet(p)
#             keep = [c for c in ["time","BIOME_ID_REALM","realm","member"]+cols if c in df.columns]
#             df   = df[keep].copy()
#             df["time"]     = pd.to_datetime(df["time"])
#             df["source"]   = gcm
#             df["scenario"] = sc
#             df = extract_realm(df)
#             if "member" not in df.columns: df["member"] = "member_0"
#             missing = [c for c in cols if c not in df.columns]
#             if missing: raise KeyError(f"Missing cols in {p}: {missing}")
#             frames.append(df)
#     if not frames: raise FileNotFoundError("No parquet files loaded")
#     return pd.concat(frames, ignore_index=True)

# def annual_realm_from_parquet(cols, keep_gcm=False):
#     df         = load_parquet_all(cols)
#     area_cols  = [c for c in cols if c.startswith("area_")]
#     frac_cols  = [c for c in cols if c.startswith("f_")]
#     value_cols = area_cols + frac_cols
#     mb = df.groupby(["source","scenario","realm","BIOME_ID_REALM","time"],
#                     as_index=False)[value_cols].mean()
#     parts = []
#     if area_cols: parts.append(mb.groupby(["source","scenario","realm","time"], as_index=False)[area_cols].sum())
#     if frac_cols: parts.append(mb.groupby(["source","scenario","realm","time"], as_index=False)[frac_cols].mean())
#     monthly = parts[0]
#     for p in parts[1:]: monthly = monthly.merge(p, on=["source","scenario","realm","time"], how="outer")
#     monthly["year"] = monthly["time"].dt.year
#     ag = monthly.groupby(["source","scenario","realm","year"], as_index=False)[value_cols].mean()
#     return ag if keep_gcm else ag.groupby(["scenario","realm","year"], as_index=False)[value_cols].mean()

# def annual_biome_realm_from_parquet(cols):
#     df    = load_parquet_all(cols)
#     parts = df["BIOME_ID_REALM"].astype(str).str.split("_", n=1, expand=True)
#     df["biome_realm"] = parts[0] + "_" + parts[1].replace({r: MERGED_CODE for r in MERGE_TO})
#     mmm   = df.groupby(["source","scenario","biome_realm","time"], as_index=False)[cols].mean()
#     mmm["year"] = mmm["time"].dt.year
#     ag    = mmm.groupby(["source","scenario","biome_realm","year"], as_index=False)[cols].mean()
#     return ag.groupby(["scenario","biome_realm","year"], as_index=False)[cols].mean()

# # =============================================================================
# # SHAPEFILES
# # =============================================================================

# def load_biome_realm_gdf():
#     gdf = gpd.read_file(WWF_SHAPE).to_crs("EPSG:4326")
#     gdf = gdf[~gdf["REALM"].isin(["AN"])].copy()
#     gdf["realm_code"]  = gdf["REALM"].astype(str).replace({r: MERGED_CODE for r in MERGE_TO})
#     gdf["biome_realm"] = gdf["BIOME"].astype(int).astype(str) + "_" + gdf["realm_code"]
#     return gdf.dissolve(by="biome_realm", as_index=False, aggfunc="first")[["biome_realm","geometry"]]

# def load_biome_realm_gdf_checked(table):
#     gdf = load_biome_realm_gdf()
#     log(f"Missing in table: {sorted(set(gdf['biome_realm'])-set(table['biome_realm']))[:20]}")
#     log(f"Extra in table:   {sorted(set(table['biome_realm'])-set(gdf['biome_realm']))[:20]}")
#     return gdf

# # =============================================================================
# # BIOME-REALM TABLE
# # =============================================================================

# def compute_biome_realm_pcr_table():
#     log("Computing biome-realm PCR table")
#     gdf_area    = load_biome_realm_gdf()
#     gdf_area["biome_area_km2"] = gdf_area.to_crs("ESRI:54009").geometry.area / 1e6
#     gdf_lookup  = dict(zip(gdf_area["biome_realm"], gdf_area["biome_area_km2"]))
#     cols        = list(dict.fromkeys(list(PCR_COLS.values()) + [COL_TOTAL]))
#     df          = annual_biome_realm_from_parquet(cols)
#     records     = []
#     base_hist   = df[(df["scenario"]=="historical") & df["year"].between(*HIST_LAST)]
#     base_old    = df[(df["scenario"]=="historical") & df["year"].between(*HIST_BASE)]
#     for sc in SCENARIOS:
#         base_all = base_old  if sc == "historical" else base_hist
#         fut_all  = base_hist if sc == "historical" else df[(df["scenario"]==sc) & df["year"].between(*FUT_LAST)]
#         for label, col in PCR_COLS.items():
#             use_col = COL_TOTAL if col == COL_TOTAL else col
#             b = base_all.groupby("biome_realm", as_index=False)[use_col].mean().rename(columns={use_col:"base"})
#             f = fut_all.groupby( "biome_realm", as_index=False)[use_col].mean().rename(columns={use_col:"future"})
#             m = b.merge(f, on="biome_realm", how="outer")
#             m["abs_change_km2"] = m["future"] - m["base"]
#             ba = gdf_lookup.get(m["biome_realm"].iloc[0], np.nan)
#             m["pct_change"]            = np.where(ba > 0, m["abs_change_km2"]/ba*100, np.nan)
#             m["normalized_change_pct"] = np.where(m["base"] >= BASELINE_MIN,
#                                                    m["abs_change_km2"]/m["base"]*100, np.nan)
#             m["scenario"]  = sc
#             m["component"] = label
#             records.append(m)
#     out = pd.concat(records, ignore_index=True)
#     out.to_csv(OUT / "biome_realm_percent_change_gw_lu_both.csv", index=False)
#     return out

# # =============================================================================
# # DRIVER PIXEL MAPS
# # All driver labels use "Landuse" (no space) consistently
# # =============================================================================

# def plot_pixel_driver_direction_all_scenarios():
#     log("Computing pixel driver direction")
#     all_counts = []
#     class_labels = {
#         1: "Groundwater driven loss",
#         2: "Groundwater driven gain",
#         3: "Landuse driven loss",
#         4: "Landuse driven gain",
#         5: "Mixed loss",
#         6: "Mixed gain",
#     }
#     for sc in FUTURE_S:
#         ht = open_timmean_da("historical", COL_TOTAL)
#         ft = open_timmean_da(sc,           COL_TOTAL)
#         hn = open_timmean_da("historical", COL_NONLU)
#         fn = open_timmean_da(sc,           COL_NONLU)
#         dgw   = np.abs(fn - hn)
#         dlu   = np.abs((ft-fn) - (ht-hn))
#         total = dgw + dlu
#         sign  = ft - ht
#         fs    = total.compute().values
#         thr   = float(np.nanpercentile(fs[np.isfinite(fs)], 50)) if np.isfinite(fs).any() else 0.0
#         v     = total >= thr
#         dom   = xr.full_like(total, np.nan, dtype="float32")
#         dom = dom.where(~(v & (dgw > dlu) & (sign < 0)), 1)
#         dom = dom.where(~(v & (dgw > dlu) & (sign > 0)), 2)
#         dom = dom.where(~(v & (dlu > dgw) & (sign < 0)), 3)
#         dom = dom.where(~(v & (dlu > dgw) & (sign > 0)), 4)
#         dom = dom.where(~(v & np.isclose(dgw, dlu) & (sign < 0)), 5)
#         dom = dom.where(~(v & np.isclose(dgw, dlu) & (sign > 0)), 6)
#         dom.name = "dominant_driver_with_direction"
#         dom.attrs["scenario"] = sc
#         dom.to_netcdf(OUT / f"{sc}_pixel_dominant_driver_with_direction.nc")

#         dom_np = dom.compute().values.astype("float32")

#         # Load historical GDW area for area-weighted fractions.
#         # Historical timmean is used as the reference so fractions reflect
#         # the distribution of actual GDW extent rather than pixel count.
#         hist_area = ht.compute().values.astype("float32")
#         hist_area = np.where(np.isfinite(hist_area), hist_area, 0.0)

#         valid_mask  = np.isfinite(dom_np)
#         vp          = int(valid_mask.sum())
#         total_area  = float(np.nansum(hist_area[valid_mask]))

#         for cls, label in class_labels.items():
#             mask    = dom_np == cls
#             n       = int(np.nansum(mask))
#             area_km2 = float(np.nansum(hist_area[mask]))
#             all_counts.append({
#                 "scenario":          sc,
#                 "class":             cls,
#                 "label":             label,
#                 "n_pixels":          n,
#                 "valid_pixels":      vp,
#                 "fraction_pct":      n / vp * 100 if vp > 0 else np.nan,
#                 "area_km2":          area_km2,
#                 "total_area_km2":    total_area,
#                 "area_fraction_pct": area_km2 / total_area * 100 if total_area > 0 else np.nan,
#             })

#     pd.DataFrame(all_counts).to_csv(
#         OUT / "pixel_driver_direction_counts_all_scenarios.csv", index=False)
#     log("Saved driver direction outputs")

# # =============================================================================
# # FIGURE 1
# # =============================================================================
# def plot_figure1_four_panel():
#     log("Building Figure 1")

#     hist_da = open_timmean_da("historical", PIXEL_VAR)
#     lat, lon = hist_da["lat"].values, hist_da["lon"].values
#     diff_np  = ((open_timmean_da("ssp370", PIXEL_VAR) - hist_da)
#                 .where(hist_da >= BASELINE_MIN)
#                 .compute().values.astype("float32"))

#     SCEN_ORDER  = ["ssp126","ssp370","ssp585"]
#     SCEN_LABELS = {"ssp126":"SSP1-2.6","ssp370":"SSP3-7.0","ssp585":"SSP5-8.5"}
#     loss_vals   = {"ssp126":245,"ssp370":432,"ssp585":341}
#     gain_vals   = {"ssp126":194,"ssp370":102,"ssp585":300}

#     driver_nc = OUT / "ssp370_pixel_dominant_driver_with_direction.nc"
#     if not driver_nc.exists(): plot_pixel_driver_direction_all_scenarios()
#     with xr.open_dataset(driver_nc) as ds:
#         dom_np = ds["dominant_driver_with_direction"].values.astype("float32")

#     csv_path = OUT / "pixel_driver_direction_counts_all_scenarios.csv"
#     if not csv_path.exists(): plot_pixel_driver_direction_all_scenarios()
#     df_counts = pd.read_csv(csv_path)

#     # Regenerate if area_fraction_pct column is missing (old CSV)
#     if "area_fraction_pct" not in df_counts.columns:
#         log("area_fraction_pct missing from CSV, regenerating driver counts")
#         plot_pixel_driver_direction_all_scenarios()
#         df_counts = pd.read_csv(csv_path)

#     fig = plt.figure(figsize=(72, 52), dpi=300, constrained_layout=False)

#     top_b, top_h  = 0.56, 0.39
#     cb_b,  cb_h   = 0.515, 0.018
#     bot_b, bot_h  = 0.10, 0.34
#     map_l, map_w  = 0.035, 0.62
#     side_l, side_w = map_l + map_w + 0.035, 0.29

#     ax_a    = fig.add_axes([map_l,  top_b, map_w,  top_h], projection=ccrs.Robinson())
#     ax_bbar = fig.add_axes([side_l, top_b, side_w, top_h])
#     ax_cb   = fig.add_axes([map_l + 0.15*map_w, cb_b, map_w*0.70, cb_h])
#     ax_cmap = fig.add_axes([map_l,  bot_b, map_w,  bot_h], projection=ccrs.Robinson())
#     ax_d    = fig.add_axes([side_l, bot_b, side_w, bot_h])

#     LKW = dict(fontsize=FS["panel"]*S, fontweight="bold", va="top", ha="left")

#     # ------------------------------------------------------------------
#     # Panel a – pixel change map (SSP3-7.0)
#     # ------------------------------------------------------------------
#     add_map_background(ax_a, white=True)
#     pm_a = ax_a.pcolormesh(lon, lat, np.ma.masked_invalid(diff_np),
#                             transform=ccrs.PlateCarree(), cmap=_RDGREY_BU,
#                             norm=TwoSlopeNorm(vcenter=0, vmin=-8, vmax=8),
#                             shading="auto", rasterized=True, zorder=2)
#     ax_a.text(-0.04, 1.03, "(a)", transform=ax_a.transAxes, **LKW)

#     cb = fig.colorbar(pm_a, cax=ax_cb, orientation="horizontal",
#                       ticks=[-8, -4, 0, 4, 8], extend="both")
#     cb.set_label("Area change (km\u00b2)", fontsize=FS["axis"]*S, fontweight="bold")
#     cb.ax.tick_params(labelsize=FS["tick"]*S, length=12, width=2.0)
#     cb.outline.set_linewidth(2.0)
#     ax_cb.axhline(0.72, color="white", alpha=0.18, linewidth=14, zorder=5)

#     # ------------------------------------------------------------------
#     # Panel b – gain/loss bar chart
#     # ------------------------------------------------------------------
#     x_ins    = np.arange(len(SCEN_ORDER))
#     LOSS_COL = "#B2182B"
#     GAIN_COL = "#2166AC"
#     loss_arr = np.array([loss_vals[sc] for sc in SCEN_ORDER])
#     gain_arr = np.array([gain_vals[sc] for sc in SCEN_ORDER])

#     b_loss = ax_bbar.bar(x_ins - 0.17, -loss_arr, width=0.34,
#                          color=LOSS_COL, edgecolor="white", lw=2.0, label="Loss")
#     b_gain = ax_bbar.bar(x_ins + 0.17,  gain_arr, width=0.34,
#                          color=GAIN_COL, edgecolor="white", lw=2.0, label="Gain")

#     for bar, val in zip(b_loss, loss_arr):
#         ax_bbar.text(bar.get_x() + bar.get_width()/2, -val - 20, f"-{val:,}",
#                      ha="center", va="top",
#                      fontsize=FS["value"]*S, color=LOSS_COL, fontweight="bold")
#     for bar, val in zip(b_gain, gain_arr):
#         ax_bbar.text(bar.get_x() + bar.get_width()/2, val + 20, f"{val:,}",
#                      ha="center", va="bottom",
#                      fontsize=FS["value"]*S, color=GAIN_COL, fontweight="bold")

#     ax_bbar.text(-0.18, 1.03, "(b)", transform=ax_bbar.transAxes, **LKW)
#     ax_bbar.axhline(0, color="0.30", lw=2.2, zorder=3)
#     ax_bbar.set_ylim(-520, 340)
#     ax_bbar.set_xticks(x_ins)
#     ax_bbar.set_xticklabels([SCEN_LABELS[s] for s in SCEN_ORDER],
#                              fontsize=FS["tick"]*S, fontweight="bold")
#     ax_bbar.set_ylabel(r"Area change ($10^3$ km$^2$)",
#                        fontsize=FS["axis"]*S, fontweight="bold")
#     ax_bbar.yaxis.set_major_formatter(
#         matplotlib.ticker.FuncFormatter(lambda y, _: f"{int(y):,}"))
#     ax_bbar.tick_params(axis="y", labelsize=FS["tick"]*S)
#     ax_bbar.grid(axis="y", alpha=0.20, linewidth=1.8)
#     ax_bbar.legend(frameon=False, loc="lower left",
#                    prop={"size": FS["legend"]*S, "weight": "bold"})
#     for sp in ("top", "right"): ax_bbar.spines[sp].set_visible(False)
#     for sp in ("left", "bottom"): ax_bbar.spines[sp].set_linewidth(2.0)

#     # ------------------------------------------------------------------
#     # Panel c – dominant driver map (SSP3-7.0)
#     # ------------------------------------------------------------------
#     CLASS_COLORS = {1: "#08306B", 2: "#6BAED6", 3: "#7F2704",
#                     4: "#FDAE6B", 5: "#238B45", 6: "#A1D99B"}
#     CLASS_LABELS_MAP = {1: "Groundwater loss", 2: "Groundwater gain",
#                         3: "Landuse loss",     4: "Landuse gain",
#                         5: "Mixed loss",       6: "Mixed gain"}
#     cmap_c, norm_c = discrete_cmap_norm(CLASS_COLORS)
#     try: cmap_c.set_bad(color="white")
#     except: pass

#     add_map_background(ax_cmap, white=True)
#     ax_cmap.pcolormesh(lon, lat, np.ma.masked_invalid(dom_np),
#                        transform=ccrs.PlateCarree(), cmap=cmap_c, norm=norm_c,
#                        shading="auto", rasterized=True, zorder=2)
#     ax_cmap.text(-0.04, 1.03, "(c)", transform=ax_cmap.transAxes, **LKW)

#     # ------------------------------------------------------------------
#     # Panel d – area-weighted driver fraction bars
#     # ------------------------------------------------------------------
#     LOSS_CLASSES = ["Groundwater driven loss", "Landuse driven loss", "Mixed loss"]
#     LOSS_COLORS  = ["#08306B", "#7F2704", "#238B45"]
#     GAIN_CLASSES = ["Groundwater driven gain", "Landuse driven gain", "Mixed gain"]
#     GAIN_COLORS  = ["#6BAED6", "#FDAE6B", "#A1D99B"]
#     y_pos = np.arange(len(SCEN_ORDER))

#     for i, sc in enumerate(SCEN_ORDER):
#         d = df_counts[df_counts["scenario"] == sc].set_index("label")

#         ll = 0.0
#         for cls, col in zip(LOSS_CLASSES, LOSS_COLORS):
#             val = float(d.loc[cls, "area_fraction_pct"]) if cls in d.index else 0.0
#             ax_d.barh(y_pos[i], -val, left=-ll, height=0.5,
#                       color=col, edgecolor="white", linewidth=1.4)
#             if val >= 5:
#                 ax_d.text(-ll - val/2, y_pos[i], f"{val:.0f}%",
#                           ha="center", va="center",
#                           fontsize=FS["value"]*S, color="white", fontweight="bold")
#             ll += val

#         lg = 0.0
#         for cls, col in zip(GAIN_CLASSES, GAIN_COLORS):
#             val = float(d.loc[cls, "area_fraction_pct"]) if cls in d.index else 0.0
#             ax_d.barh(y_pos[i], val, left=lg, height=0.5,
#                       color=col, edgecolor="white", linewidth=1.4)
#             if val >= 5:
#                 ax_d.text(lg + val/2, y_pos[i], f"{val:.0f}%",
#                           ha="center", va="center",
#                           fontsize=FS["value"]*S, color="white", fontweight="bold")
#             lg += val

#     ax_d.text(-0.18, 1.03, "(d)", transform=ax_d.transAxes, **LKW)
#     ax_d.axvline(0, color="0.25", lw=2.2, zorder=3)
#     ax_d.set_yticks(y_pos)
#     ax_d.set_yticklabels([SCEN_LABELS[s] for s in SCEN_ORDER],
#                           fontsize=FS["tick"]*S, fontweight="bold")
#     ax_d.set_xlabel("% GDW area", fontsize=FS["axis"]*S, fontweight="bold")
#     ax_d.grid(axis="x", alpha=0.22, linewidth=1.8)
#     ax_d.xaxis.set_major_formatter(
#         matplotlib.ticker.FuncFormatter(lambda x, _: str(abs(int(x)))))
#     ax_d.tick_params(axis="x", labelsize=FS["tick"]*S)
#     ax_d.text(0.25, -0.12, "\u2190 Loss", transform=ax_d.transAxes,
#               ha="center", va="top", fontsize=FS["small"]*S, color="0.35")
#     ax_d.text(0.75, -0.12, "Gain \u2192", transform=ax_d.transAxes,
#               ha="center", va="top", fontsize=FS["small"]*S, color="0.35")
#     for sp in ("top", "right"): ax_d.spines[sp].set_visible(False)
#     for sp in ("left", "bottom"): ax_d.spines[sp].set_linewidth(2.0)

#     # ------------------------------------------------------------------
#     # Shared legend for panels c and d
#     # ------------------------------------------------------------------
#     fig.legend(
#         handles=[Patch(facecolor=CLASS_COLORS[i], edgecolor="0.5",
#                        label=CLASS_LABELS_MAP[i], linewidth=1.0) for i in range(1, 7)],
#         ncol=6, loc="lower center", bbox_to_anchor=(0.50, 0.0),
#         frameon=False, handlelength=1.6, handleheight=1.3, columnspacing=2.2,
#         prop={"size": FS["legend"]*S},
#     )

#     fig.savefig(OUT / "figure1_four_panel.png", dpi=300, bbox_inches="tight")
#     plt.close(fig)
#     log("Saved: figure1_four_panel.png")

# # =============================================================================
# # FIGURE 2
# # =============================================================================

# def plot_realm_ts_only():
#     log("Building Figure 2")
#     df = annual_realm_from_parquet([TS_VAR], keep_gcm=True)
#     df["value_plot"] = df[TS_VAR] / 1e8
#     realms = [r for r in REALM_ORDER if r in set(df["realm"])]
#     fig   = plt.figure(figsize=(22, 12), dpi=300, constrained_layout=False)
#     ncols, nrows = 3, 2
#     left0, bot0  = 0.07, 0.12
#     pw = (0.90-(ncols-1)*0.03)/ncols
#     ph = (0.80-(nrows-1)*0.06)/nrows
#     realm_axes = []
#     for row in range(nrows):
#         for col in range(ncols):
#             realm_axes.append(fig.add_axes([
#                 left0+col*(pw+0.03), bot0+(nrows-1-row)*(ph+0.06), pw, ph]))

#     def _ts(ax, src, title):
#         hist = src[(src["scenario"]=="historical") & (src["year"]<=2014)].copy()
#         piv  = hist.pivot_table(index="year", columns="source",
#                                 values="value_plot", aggfunc="mean").sort_index()
#         hm, hl, hh = smooth(piv.mean(1)), smooth(piv.min(1)), smooth(piv.max(1))
#         ax.fill_between(hm.index, hl.values, hh.values,
#                         color=SCEN_COLOR["historical"], alpha=0.18, linewidth=0)
#         ax.plot(hm.index, hm.values, color=SCEN_COLOR["historical"], lw=2.0)
#         hc = hm.dropna()
#         if hc.empty: return
#         ly, lv = int(hc.index.max()), float(hc.iloc[-1])
#         for sc in FUTURE_S:
#             d = src[(src["scenario"]==sc) & (src["year"]>=JOIN_YEAR)].copy()
#             if d.empty: continue
#             piv2 = d.pivot_table(index="year", columns="source",
#                                   values="value_plot", aggfunc="mean").sort_index()
#             mr, lr2, hr2 = piv2.mean(1), piv2.min(1), piv2.max(1)
#             mrc = mr.dropna()
#             if mrc.empty: continue
#             sh = lv - float(mrc.iloc[0])
#             m, l2, h2 = smooth(mr+sh), smooth(lr2+sh), smooth(hr2+sh)
#             sx = np.concatenate([[ly], m.index.values])
#             ax.fill_between(sx,
#                             np.concatenate([[float(hl.dropna().iloc[-1])], l2.values]),
#                             np.concatenate([[float(hh.dropna().iloc[-1])], h2.values]),
#                             color=SCEN_COLOR[sc], alpha=0.18, linewidth=0)
#             mc = m.dropna()
#             ax.plot([ly, int(mc.index.min())], [lv, float(mc.iloc[0])],
#                     color=SCEN_COLOR[sc], lw=2.0)
#             ax.plot(m.index, m.values, color=SCEN_COLOR[sc], lw=2.0)
#         ax.set_title(title, fontsize=FS["title"], fontweight="bold")
#         ax.set_ylabel("Area (M km2)", fontsize=FS["axis"])
#         ax.tick_params(labelsize=FS["tick"])
#         ax.grid(axis="y", alpha=0.25)
#         ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=5, prune="both"))
#         ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
#         for sp in ("top","right"): ax.spines[sp].set_visible(False)

#     for realm, ax in zip(realms, realm_axes):
#         _ts(ax, df[df["realm"]==realm].copy(), realm)
#     for j in range(len(realms), len(realm_axes)):
#         realm_axes[j].set_visible(False)
#     fig.legend(
#         handles=[Line2D([0],[0], color=SCEN_COLOR[s], lw=2.5, label=SCEN_LABEL[s])
#                  for s in SCENARIOS],
#         frameon=False, ncol=4, fontsize=FS["legend"],
#         loc="lower center", bbox_to_anchor=(0.5, 0.01),
#     )
#     fig.savefig(OUT / "figure2_realm_ts.png", dpi=300, bbox_inches="tight")
#     plt.close(fig)
#     log("Saved: figure2_realm_ts.png")

# # =============================================================================
# # FIGURE 3
# # =============================================================================

# def plot_figure3_lollipop():
#     log("Building Figure 3")
#     df   = annual_realm_from_parquet([COL_TOTAL, COL_NONLU], keep_gcm=False)
#     rows = []
#     for sc in SCENARIOS:
#         blo, bhi = HIST_BASE if sc=="historical" else HIST_LAST
#         flo, fhi = HIST_LAST if sc=="historical" else FUT_LAST
#         db = df[df["scenario"].eq("historical") & df["year"].between(blo,bhi)]
#         df2= df[df["scenario"].eq(sc)           & df["year"].between(flo,fhi)]
#         b  = db.groupby("realm",as_index=False)[[COL_TOTAL,COL_NONLU]].mean()
#         f  = df2.groupby("realm",as_index=False)[[COL_TOTAL,COL_NONLU]].mean()
#         m  = b.merge(f,on="realm",suffixes=("_b","_f"),how="outer")
#         m["delta_total"] = (m[f"{COL_TOTAL}_f"]-m[f"{COL_TOTAL}_b"])/1e5
#         m["delta_nonlu"] = (m[f"{COL_NONLU}_f"]-m[f"{COL_NONLU}_b"])/1e5
#         m["scenario"] = sc
#         rows.append(m)
#     tab    = pd.concat(rows, ignore_index=True)
#     realms = [r for r in REALM_ORDER if r in set(tab["realm"])]
#     y_pos  = np.arange(len(realms))[::-1]
#     fig, axes = plt.subplots(1, len(SCENARIOS), figsize=(6*len(SCENARIOS), 8), dpi=300)
#     for ax, sc in zip(axes, SCENARIOS):
#         d = tab[tab["scenario"]==sc].set_index("realm").reindex(realms)
#         ax.axvline(0, color="0.60", lw=1.0, zorder=0)
#         for yi, vt, vn in zip(y_pos, d["delta_total"], d["delta_nonlu"]):
#             if np.isfinite(vt):
#                 c = "#2166AC" if vt >= 0 else "#B2182B"
#                 ax.plot([0,vt],[yi+0.10,yi+0.10], color=c, lw=2.5, solid_capstyle="round")
#                 ax.plot(vt, yi+0.10, "o", color=c, ms=9, zorder=2)
#             if np.isfinite(vn):
#                 c = "#2166AC" if vn >= 0 else "#B2182B"
#                 ax.plot([0,vn],[yi-0.10,yi-0.10], color=c, lw=2.5, ls="--", solid_capstyle="round")
#                 ax.plot(vn, yi-0.10, "s", mfc="white", mec=c, ms=9, mew=2.0)
#         ax.set_yticks(y_pos)
#         ax.set_yticklabels(realms, fontsize=FS["tick"], fontweight="bold")
#         ax.set_title(SCEN_LABEL[sc], fontsize=FS["title"], fontweight="bold")
#         ax.set_xlabel(r"Area change ($10^3$ km$^2$)", fontsize=FS["axis"], fontweight="bold")
#         ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=5, prune="both"))
#         ax.tick_params(axis="x", labelsize=FS["tick"])
#         ax.grid(axis="x", alpha=0.22, linewidth=0.8)
#         for sp in ("top","right"): ax.spines[sp].set_visible(False)
#     fig.legend(
#         handles=[
#             Line2D([0],[0], color="0.3", marker="o", lw=2.5, ms=9, label="Total GDW"),
#             Line2D([0],[0], color="0.3", marker="s", mfc="white", mew=2.0,
#                    lw=2.5, ls="--", ms=9, label="GDW without landuse impact"),
#             Line2D([0],[0], color="#2166AC", lw=2.5, label="Gain"),
#             Line2D([0],[0], color="#B2182B", lw=2.5, label="Loss"),
#         ],
#         ncol=4, loc="lower center", bbox_to_anchor=(0.5, 0.00),
#         frameon=False, fontsize=FS["legend"], handlelength=2.0, columnspacing=1.8,
#     )
#     fig.tight_layout(rect=[0.0, 0.10, 1.0, 1.0])
#     fig.savefig(OUT / "figure3_lollipop_decadal_change.png", dpi=300, bbox_inches="tight")
#     plt.close(fig)
#     log("Saved: figure3_lollipop_decadal_change.png")

# # =============================================================================
# # FIGURE 4
# # =============================================================================

# def plot_figure4_biome_map():
#     log("Building Figure 4")
#     table = compute_biome_realm_pcr_table()
#     gdf   = load_biome_realm_gdf_checked(table)
#     value_col   = "normalized_change_pct"
#     components  = list(PCR_COLS_NORM.keys())
#     scenarios   = SCENARIOS
#     COMP_LABELS = {
#         "Groundwater Impact Only":       "Groundwater-only",
#         "Land-use Impact Only":          "Landuse-only",
#         "Groundwater + Land-use Impact": "Combined",
#     }
#     nrows, ncols = len(scenarios), len(components)
#     fig, axes = plt.subplots(
#         nrows, ncols, figsize=(6*ncols, 4*nrows), dpi=300,
#         subplot_kw={"projection": ccrs.Robinson()},
#         gridspec_kw={"hspace":-0.03, "wspace":0.03},
#     )
#     axes = np.array(axes).reshape(nrows, ncols)
#     norm = TwoSlopeNorm(vcenter=0, vmin=-PCR_VLIM, vmax=PCR_VLIM)
#     for r, sc in enumerate(scenarios):
#         for c, comp in enumerate(components):
#             ax = axes[r, c]
#             add_map_background(ax, white=True)
#             ax.coastlines(color="0.25", linewidth=0.8, zorder=3)
#             d        = table[(table["scenario"]==sc)&(table["component"]==comp)][["biome_realm",value_col]]
#             plot_gdf = gdf.merge(d, on="biome_realm", how="left")
#             plot_gdf.plot(column=value_col, ax=ax, transform=ccrs.PlateCarree(),
#                           cmap=CMAP_DIVERGING, norm=norm, linewidth=0.0,
#                           missing_kwds={"color":"white"}, zorder=2)
#             if r == 0:
#                 ax.set_title(COMP_LABELS.get(comp, comp),
#                              fontsize=FS["title"], fontweight="bold", pad=6)
#             if c == 0:
#                 ax.text(-0.06, 0.5, SCEN_LABEL[sc], transform=ax.transAxes,
#                         rotation=90, va="center", ha="right",
#                         fontsize=FS["axis"], fontweight="bold")
#     cax = fig.add_axes([0.20, 0.03, 0.60, 0.012])
#     sm  = plt.cm.ScalarMappable(norm=norm, cmap=CMAP_DIVERGING)
#     sm.set_array([])
#     cb  = fig.colorbar(sm, cax=cax, orientation="horizontal",
#                        ticks=[-15,-10,-5,0,5,10,15], extend="both")
#     cb.set_label("Area change (%)", fontsize=FS["axis"])
#     cb.ax.tick_params(labelsize=FS["tick"])
#     cb.outline.set_linewidth(0.8)
#     fig.savefig(OUT / "figure4_biome_realm_component_maps.png", dpi=300, bbox_inches="tight")
#     plt.close(fig)
#     log("Saved: figure4_biome_realm_component_maps.png")

# """
# Supplementary figures and tables for manuscript.
# Paste at the bottom of manuscript_figures_final.py before main().

# S1  – Future GDW persistence class map (SSP3-7.0)
# S2  – Persistence change maps (months, class gain/loss, transition)
# S3  – Biome-realm absolute change maps
# S4  – Continent GDW area table (CSV)
# """

# from matplotlib.colors import TwoSlopeNorm, ListedColormap, BoundaryNorm

# # =============================================================================
# # CONTINENT MAPPING
# # =============================================================================

# REALM_TO_CONTINENT = {
#     "Nearctic":                 "North America",
#     "Neotropical":              "South America",
#     "Afrotropical":             "Africa",
#     "Palearctic":               "Europe & Asia",
#     "Indo-Malayan":             "Asia (Indo-Malayan)",
#     "Australasian & Oceanian":  "Oceania",
# }

# # =============================================================================
# # S1 – Future GDW persistence class map
# # =============================================================================

# def plot_s1_persistence_class():
#     log("Building S1: future persistence class map")

#     fut_clim   = open_monthly_clim_da("ssp370", PIXEL_VAR)
#     fut_months = (fut_clim >= BASELINE_MIN).sum("month")

#     out_nc = OUT / "ssp370_future_persistence_class_per_pixel.nc"
#     if not out_nc.exists():
#         pers = xr.full_like(fut_months, np.nan, dtype="float32")
#         pers = pers.where(~((fut_months >= 1) & (fut_months <= 3)), 1)
#         pers = pers.where(~((fut_months >= 4) & (fut_months <= 6)), 2)
#         pers = pers.where(~(fut_months >= 7), 3)
#         pers.name = "future_persistence_class"
#         pers.to_netcdf(out_nc)
#     else:
#         with xr.open_dataset(out_nc) as ds:
#             pers = ds["future_persistence_class"]

#     pers_np = pers.compute().values.astype("float32")
#     lat = pers["lat"].values
#     lon = pers["lon"].values

#     PCOL = {1:"#FFD92F", 2:"#66BD3A", 3:"#0571B0"}
#     cmap, norm = discrete_cmap_norm(PCOL)

#     fig = plt.figure(figsize=(16, 8), dpi=300)
#     ax  = plt.axes(projection=ccrs.Robinson())
#     add_map_background(ax, white=True)
#     ax.pcolormesh(lon, lat, np.ma.masked_invalid(pers_np),
#                   transform=ccrs.PlateCarree(), cmap=cmap, norm=norm,
#                   shading="auto", rasterized=True, zorder=2)

#     handles = [
#         Patch(facecolor=PCOL[1], edgecolor="0.4", label="Episodic (1-3 months)"),
#         Patch(facecolor=PCOL[2], edgecolor="0.4", label="Seasonal (4-6 months)"),
#         Patch(facecolor=PCOL[3], edgecolor="0.4", label="Perennial (7-12 months)"),
#     ]
#     ax.legend(handles=handles, title="Persistence class",
#               frameon=True, framealpha=0.88, edgecolor="0.7",
#               loc="lower right", bbox_to_anchor=(1.0, -0.205),
#               fontsize=FS["legend"], title_fontsize=FS["legend"])

#     fig.savefig(OUT / "S1_persistence_class_ssp370.png", dpi=300, bbox_inches="tight")
#     plt.close(fig)
#     log("Saved: S1_persistence_class_ssp370.png")


# # =============================================================================
# # S2 – Persistence change maps (3-panel)
# # =============================================================================

# def plot_s2_persistence_change():
#     log("Building S2: persistence change maps")

#     hist_clim  = open_monthly_clim_da("historical", PIXEL_VAR)
#     fut_clim   = open_monthly_clim_da("ssp370",     PIXEL_VAR)

#     hist_months = (hist_clim >= BASELINE_MIN).sum("month")
#     fut_months  = (fut_clim  >= BASELINE_MIN).sum("month")

#     month_change = fut_months - hist_months

#     def classify(m):
#         out = xr.full_like(m, np.nan, dtype="float32")
#         out = out.where(~((m >= 1) & (m <= 3)), 1)
#         out = out.where(~((m >= 4) & (m <= 6)), 2)
#         out = out.where(~(m >= 7), 3)
#         return out

#     hist_class  = classify(hist_months)
#     fut_class   = classify(fut_months)
#     class_change = fut_class - hist_class
#     transition   = hist_class * 10 + fut_class

#     valid = np.isfinite(hist_class) & np.isfinite(fut_class)
#     month_change  = month_change.where(valid)
#     class_change  = class_change.where(valid)
#     transition    = transition.where(valid)

#     lat = month_change["lat"].values
#     lon = month_change["lon"].values
#     month_np  = month_change.compute().values.astype("float32")
#     class_np  = class_change.compute().values.astype("float32")
#     trans_np  = transition.compute().values.astype("float32")

#     norm_month = TwoSlopeNorm(vcenter=0, vmin=-6, vmax=6)

#     GAINLOSS = {-2:"#5E2A84",-1:"#B28AC7",0:"#F0F0F0",1:"#66BD3A",2:"#1B7837"}
#     TRANSCOL = {
#         11:"#F7F7F7",12:"#FFE066",13:"#1ABC9C",
#         21:"#F4A261",22:"#F7F7F7",23:"#2A9D8F",
#         31:"#D7191C",32:"#92C5DE",33:"#F7F7F7",
#     }
#     gl_cmap,  gl_norm  = discrete_cmap_norm(GAINLOSS)
#     tr_cmap,  tr_norm  = discrete_cmap_norm(TRANSCOL)

#     fig, axes = plt.subplots(
#         1, 3, figsize=(20, 6), dpi=300,
#         subplot_kw={"projection": ccrs.Robinson()},
#         gridspec_kw={"wspace": 0.04},
#     )

#     # Panel 1 – change in active months
#     add_map_background(axes[0], white=True)
#     pm = axes[0].pcolormesh(lon, lat, np.ma.masked_invalid(month_np),
#                              transform=ccrs.PlateCarree(), cmap=CMAP_DIVERGING,
#                              norm=norm_month, shading="auto", rasterized=True, zorder=2)
#     axes[0].text(0.01, 0.97, "(a)", transform=axes[0].transAxes,
#                  fontsize=FS["panel"], fontweight="bold", va="top")
#     cax1 = fig.add_axes([0.08, 0.16, 0.22, 0.03])
#     cb1  = fig.colorbar(pm, cax=cax1, orientation="horizontal",
#                         ticks=[-6,-4,-2,0,2,4,6])
#     cb1.set_label("Change in GDW-active months", fontsize=FS["small"])
#     cb1.ax.tick_params(labelsize=FS["small"])

#     # Panel 2 – persistence class gain/loss
#     add_map_background(axes[1], white=True)
#     axes[1].pcolormesh(lon, lat, np.ma.masked_invalid(class_np),
#                        transform=ccrs.PlateCarree(), cmap=gl_cmap, norm=gl_norm,
#                        shading="auto", rasterized=True, zorder=2)
#     axes[1].text(0.01, 0.97, "(b)", transform=axes[1].transAxes,
#                  fontsize=FS["panel"], fontweight="bold", va="top")
#     gl_handles = [
#         Patch(facecolor=GAINLOSS[k], edgecolor="0.4", label=l)
#         for k, l in [(-2,"Loss 2 classes"),(-1,"Loss 1 class"),
#                      (0,"No change"),(1,"Gain 1 class"),(2,"Gain 2 classes")]
#     ]
#     axes[1].legend(handles=gl_handles, frameon=True, framealpha=0.88,
#                    edgecolor="0.7", loc="lower right", bbox_to_anchor=(1.0,-0.60),
#                    fontsize=FS["small"]-1, ncol=1)

#     # Panel 3 – transition map
#     add_map_background(axes[2], white=True)
#     axes[2].pcolormesh(lon, lat, np.ma.masked_invalid(trans_np),
#                        transform=ccrs.PlateCarree(), cmap=tr_cmap, norm=tr_norm,
#                        shading="auto", rasterized=True, zorder=2)
#     axes[2].text(0.01, 0.97, "(c)", transform=axes[2].transAxes,
#                  fontsize=FS["panel"], fontweight="bold", va="top")
#     tr_handles = [
#         Patch(facecolor=TRANSCOL[k], edgecolor="0.4", label=l)
#         for k, l in [(12,"Episodic to Seasonal"),(13,"Episodic to Perennial"),
#                      (21,"Seasonal to Episodic"),(23,"Seasonal to Perennial"),
#                      (31,"Perennial to Episodic"),(32,"Perennial to Seasonal"),
#                      (11,"No class change")]
#     ]
#     axes[2].legend(handles=tr_handles, frameon=True, framealpha=0.88,
#                    edgecolor="0.7", loc="lower right", bbox_to_anchor=(1.0,-0.8),
#                    fontsize=FS["small"]-1, ncol=1)

#     fig.savefig(OUT / "S2_persistence_change_maps_ssp370.png", dpi=300, bbox_inches="tight")
#     plt.close(fig)
#     log("Saved: S2_persistence_change_maps_ssp370.png")


# # =============================================================================
# # S3 – Biome-realm absolute change maps
# # =============================================================================

# def plot_s3_biome_realm_absolute():
#     log("Building S3: biome-realm absolute change maps")

#     table = compute_biome_realm_pcr_table()
#     gdf   = load_biome_realm_gdf_checked(table)

#     value_col   = "abs_change_km2"
#     components  = list(PCR_COLS_NORM.keys())
#     scenarios   = SCENARIOS
#     COMP_LABELS = {
#         "Groundwater Impact Only":       "Groundwater-only",
#         "Land-use Impact Only":          "Landuse-only",
#         "Groundwater + Land-use Impact": "Combined",
#     }

#     # Symmetric vlim at 95th percentile of absolute values
#     vals = table[value_col].dropna().abs()
#     vlim = float(np.nanpercentile(vals, 95)) if vals.size else 1e4
#     vlim = float(np.ceil(vlim / 1000) * 1000)   # round up to nearest 1000

#     nrows, ncols = len(scenarios), len(components)
#     fig, axes = plt.subplots(
#         nrows, ncols,
#         figsize=(6*ncols, 4*nrows), dpi=300,
#         subplot_kw={"projection": ccrs.Robinson()},
#         gridspec_kw={"hspace":-0.08, "wspace":0.03},
#     )
#     axes = np.array(axes).reshape(nrows, ncols)
#     norm = TwoSlopeNorm(vcenter=0, vmin=-vlim, vmax=vlim)

#     for r, sc in enumerate(scenarios):
#         for c, comp in enumerate(components):
#             ax = axes[r, c]
#             add_map_background(ax, white=True)
#             d        = table[(table["scenario"]==sc)&(table["component"]==comp)][["biome_realm",value_col]]
#             plot_gdf = gdf.merge(d, on="biome_realm", how="left")
#             plot_gdf.plot(column=value_col, ax=ax, transform=ccrs.PlateCarree(),
#                           cmap=CMAP_DIVERGING, norm=norm, linewidth=0.0,
#                           missing_kwds={"color":"white"}, zorder=2)
#             if r == 0:
#                 ax.set_title(COMP_LABELS.get(comp, comp),
#                              fontsize=FS["title"], fontweight="bold", pad=6)
#             if c == 0:
#                 ax.text(-0.06, 0.5, SCEN_LABEL[sc], transform=ax.transAxes,
#                         rotation=90, va="center", ha="right",
#                         fontsize=FS["axis"], fontweight="bold")

#     cax = fig.add_axes([0.20, 0.03, 0.60, 0.012])
#     sm  = plt.cm.ScalarMappable(norm=norm, cmap=CMAP_DIVERGING)
#     sm.set_array([])
#     cb  = fig.colorbar(sm, cax=cax, orientation="horizontal", extend="both")
#     cb.set_label("Change in GDW area (km2)", fontsize=FS["axis"])
#     cb.ax.tick_params(labelsize=FS["tick"])
#     cb.outline.set_linewidth(0.8)

#     fig.savefig(OUT / "S3_biome_realm_absolute_change.png", dpi=300, bbox_inches="tight")
#     plt.close(fig)
#     log("Saved: S3_biome_realm_absolute_change.png")


# # =============================================================================
# # S4 – Continent GDW area table (CSV)
# # =============================================================================

# def make_s4_continent_gdw_table():
#     log("Building S4: continent GDW area table")

#     df = annual_realm_from_parquet([COL_TOTAL, COL_NONLU], keep_gcm=False)

#     rows = []
#     for sc in SCENARIOS:
#         lo, hi = HIST_LAST if sc == "historical" else FUT_LAST
#         d = df[df["scenario"].eq(sc) & df["year"].between(lo, hi)]
#         m = d.groupby("realm", as_index=False)[[COL_TOTAL, COL_NONLU]].mean()
#         m["scenario"] = sc
#         m["period"]   = f"{lo}-{hi}"
#         rows.append(m)

#     tab = pd.concat(rows, ignore_index=True)
#     tab["continent"] = tab["realm"].map(REALM_TO_CONTINENT)

#     tab["total_gdw_1000km2"] = tab[COL_TOTAL] / 1e5
#     tab["nonlu_gdw_1000km2"] = tab[COL_NONLU] / 1e5

#     cont = (
#         tab.groupby(["scenario","period","continent"], as_index=False)
#         [["total_gdw_1000km2","nonlu_gdw_1000km2"]]
#         .sum()
#     )

#     global_rows = []
#     for (sc, per), g in cont.groupby(["scenario","period"]):
#         global_rows.append({
#             "scenario":           sc,
#             "period":             per,
#             "continent":          "Global",
#             "total_gdw_1000km2":  g["total_gdw_1000km2"].sum(),
#             "nonlu_gdw_1000km2":  g["nonlu_gdw_1000km2"].sum(),
#         })
#     cont = pd.concat([cont, pd.DataFrame(global_rows)], ignore_index=True)
#     cont["total_gdw_1000km2"] = cont["total_gdw_1000km2"].round(1)
#     cont["nonlu_gdw_1000km2"] = cont["nonlu_gdw_1000km2"].round(1)
#     cont = cont.rename(columns={
#         "total_gdw_1000km2": "Total GDW area (thousand km2)",
#         "nonlu_gdw_1000km2": "GDW without landuse impact (thousand km2)",
#     })

#     cont_order = [
#         "North America","South America","Africa",
#         "Europe & Asia","Asia (Indo-Malayan)","Oceania","Global",
#     ]
#     cont["continent"] = pd.Categorical(cont["continent"],
#                                         categories=cont_order, ordered=True)
#     cont = cont.sort_values(["scenario","continent"]).reset_index(drop=True)

#     out_csv = OUT / "S4_continent_gdw_area_table.csv"
#     cont.to_csv(out_csv, index=False)
#     log(f"Saved: {out_csv}")

#     hist = cont[cont["scenario"]=="historical"][
#         ["continent","period",
#          "Total GDW area (thousand km2)",
#          "GDW without landuse impact (thousand km2)"]
#     ]
#     log("\nHistorical GDW area by continent (2005-2014):")
#     log(hist.to_string(index=False))

#     return cont


# # =============================================================================
# # SUPPLEMENTARY MAIN – call all four
# # =============================================================================

# def run_supplementary():
#     log("Running supplementary figures and tables")
#     plot_s1_persistence_class()
#     plot_s2_persistence_change()
#     plot_s3_biome_realm_absolute()
#     make_s4_continent_gdw_table()
#     log("Supplementary done.")

# # =============================================================================
# # MAIN
# # =============================================================================

# def main():
#     log(f"Output: {OUT}")
#     plot_pixel_driver_direction_all_scenarios()
#     plot_figure1_four_panel()
#     # # plot_realm_ts_only()
#     # # plot_figure3_lollipop()
#     # # plot_figure4_biome_map()
#     # run_supplementary()
#     log("Done.")

# if __name__ == "__main__":
#     main()



#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter, FFMpegWriter
import matplotlib.ticker
from matplotlib.colors import (
    TwoSlopeNorm, ListedColormap,
    BoundaryNorm, LinearSegmentedColormap,
)
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import geopandas as gpd
import cartopy.crs as ccrs
import cartopy.feature as cfeature

import matplotlib as mpl
mpl.rcParams["font.family"] = "sans-serif"
mpl.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Helvetica", "Liberation Sans"]

try:
    import cmocean
    CMAP_DIVERGING = cmocean.cm.curl
except ImportError:
    CMAP_DIVERGING = plt.get_cmap("RdBu")

# =============================================================================
# PATHS
# =============================================================================

BASE      = Path("/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3")
ENSEMBLE  = BASE / "ensemble"
GCMS_BASE = BASE / "gcms"
OUT       = BASE / "plots" / "figures_v2806"
WWF_SHAPE = "/path/to/scratch/paper_3/inputs/biomes/biomes/wwf_terr_ecos.shp"
OUT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# SETTINGS
# =============================================================================

GCMS      = ["gfdl-esm4", "ipsl-cm6a-lr", "mpi-esm1-2-hr", "mri-esm2-0", "ukesm1-0-ll"]
SCENARIOS = ["historical", "ssp126", "ssp370", "ssp585"]
FUTURE_S  = ["ssp126", "ssp370", "ssp585"]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

COL_TOTAL   = "area_gdw_km2"
COL_NONLU   = "area_gdw_nonlu_km2"
COL_GW_ONLY = "area_gdw_freeze_lu_km2"
COL_LU_ONLY = "area_gdw_freeze_wtd_km2"

PCR_COLS = {
    "Groundwater Impact Only":       COL_NONLU,
    "Land-use Impact Only":          COL_LU_ONLY,
    "Groundwater + Land-use Impact": COL_TOTAL,
}
PCR_COLS_NORM = PCR_COLS.copy()

TS_VAR         = COL_TOTAL
PIXEL_VAR      = COL_TOTAL
HIST_BASE      = (1995, 2004)
HIST_LAST      = (2005, 2014)
FUT_LAST       = (2041, 2050)
JOIN_YEAR      = 2015
SMOOTH_YEARS   = 5
BASELINE_MIN   = 0.01
PCR_VLIM       = 15
ABS_PERCENTILE = 95

SCEN_COLOR = {
    "historical": "#333333",
    "ssp126":     "#1a9850",
    "ssp370":     "#fdae61",
    "ssp585":     "#d73027",
}
SCEN_LABEL = {
    "historical": "Historical",
    "ssp126":     "SSP1-2.6",
    "ssp370":     "SSP3-7.0",
    "ssp585":     "SSP5-8.5",
}

MERGE_TO    = {"AA", "OC"}
MERGED_CODE = "AO"
REALM_NAME  = {
    "AT": "Afrotropical", "IM": "Indo-Malayan",
    "NA": "Nearctic",     "NT": "Neotropical",
    "PA": "Palearctic",   MERGED_CODE: "Australasian & Oceanian",
}
REALM_ORDER = [
    "Nearctic", "Neotropical", "Afrotropical",
    "Palearctic", "Indo-Malayan", "Australasian & Oceanian",
]

FS = {
    "panel":  22,
    "title":  20,
    "axis":   18,
    "tick":   16,
    "legend": 16,
    "value":  16,
    "small":  14,
}
S = 4.5

_RDGREY_BU = LinearSegmentedColormap.from_list(
    "rdgrey_bu",
    ["#67001F","#B2182B","#D6604D","#F4A582","#FDDBC7",
     "#AAAAAA",
     "#D1E5F0","#92C5DE","#4393C3","#2166AC","#053061"],
    N=512,
)
_RDGREY_BU.set_bad(color="white")

# =============================================================================
# HELPERS
# =============================================================================

def log(msg):
    print(f"[{pd.Timestamp.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

def smooth(s):
    return s.rolling(SMOOTH_YEARS, center=True,
                     min_periods=max(1, SMOOTH_YEARS // 2)).mean()

def normalize_realm_codes(s):
    x = s.astype(str).replace({r: MERGED_CODE for r in MERGE_TO})
    return x.map(REALM_NAME).fillna(x)

def period_for_scenario(sc):
    return HIST_LAST if sc == "historical" else FUT_LAST

def parquet_path(gcm, sc):
    return GCMS_BASE / gcm / sc / "parquet" / f"wetGDE_area_{gcm}_{sc}.parquet"

def timmean_path(sc):
    y1, y2 = period_for_scenario(sc)
    return ENSEMBLE / sc / "nc" / f"wetGDE_ensemble_timmean_{sc}_{y1}-{y2}.nc"

def monthly_clim_path(sc):
    y1, y2 = period_for_scenario(sc)
    return ENSEMBLE / sc / "nc" / f"wetGDE_ensemble_monthly_climatology_{sc}_{y1}-{y2}.nc"

def add_map_background(ax, white=False):
    ax.set_global()
    ax.set_extent([-180, 180, -58, 90], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND.with_scale("110m"),
                   facecolor="white" if white else "#f5f5f2",
                   edgecolor="none", zorder=0)
    ax.coastlines(linewidth=0.7, color="0.50", zorder=3)
    ax.axis("off")

def discrete_cmap_norm(vcm):
    vals   = sorted(vcm)
    cmap   = ListedColormap([vcm[v] for v in vals])
    bounds = [vals[0]-0.5] + [(vals[i]+vals[i+1])/2 for i in range(len(vals)-1)] + [vals[-1]+0.5]
    return cmap, BoundaryNorm(bounds, cmap.N)

def open_timmean_da(sc, var):
    path = timmean_path(sc)
    if not path.exists(): raise FileNotFoundError(path)
    ds = xr.open_dataset(path, decode_times=True, mask_and_scale=True)
    if var not in ds: raise KeyError(f"{var} missing in {path}")
    da = ds[var]
    return da.isel(time=0) if "time" in da.dims else da
def open_monthly_clim_da(sc, var):
    path = monthly_clim_path(sc)

    if not path.exists():
        raise FileNotFoundError(path)

    ds = xr.open_dataset(
        path,
        decode_times=True,
        mask_and_scale=True,
    )

    if var not in ds:
        raise KeyError(f"{var} missing in {path}")

    da = ds[var]

    if "time" in da.dims and "month" not in da.dims:
        da = da.assign_coords(month=da["time"].dt.month).swap_dims({"time": "month"})
        da = da.drop_vars("time")

    return da

# =============================================================================
# PARQUET LOADERS
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
    return d[~d["realm"].isin(["AN","Antarctica","Antarctic"])].copy()

def load_parquet_all(cols):
    frames = []
    for gcm in GCMS:
        for sc in SCENARIOS:
            p = parquet_path(gcm, sc)
            if not p.exists(): log(f"[missing] {p}"); continue
            df   = pd.read_parquet(p)
            keep = [c for c in ["time","BIOME_ID_REALM","realm","member"]+cols if c in df.columns]
            df   = df[keep].copy()
            df["time"]     = pd.to_datetime(df["time"])
            df["source"]   = gcm
            df["scenario"] = sc
            df = extract_realm(df)
            if "member" not in df.columns: df["member"] = "member_0"
            missing = [c for c in cols if c not in df.columns]
            if missing: raise KeyError(f"Missing cols in {p}: {missing}")
            frames.append(df)
    if not frames: raise FileNotFoundError("No parquet files loaded")
    return pd.concat(frames, ignore_index=True)

def annual_realm_from_parquet(cols, keep_gcm=False):
    df         = load_parquet_all(cols)
    area_cols  = [c for c in cols if c.startswith("area_")]
    frac_cols  = [c for c in cols if c.startswith("f_")]
    value_cols = area_cols + frac_cols
    mb = df.groupby(["source","scenario","realm","BIOME_ID_REALM","time"],
                    as_index=False)[value_cols].mean()
    parts = []
    if area_cols: parts.append(mb.groupby(["source","scenario","realm","time"], as_index=False)[area_cols].sum())
    if frac_cols: parts.append(mb.groupby(["source","scenario","realm","time"], as_index=False)[frac_cols].mean())
    monthly = parts[0]
    for p in parts[1:]: monthly = monthly.merge(p, on=["source","scenario","realm","time"], how="outer")
    monthly["year"] = monthly["time"].dt.year
    ag = monthly.groupby(["source","scenario","realm","year"], as_index=False)[value_cols].mean()
    return ag if keep_gcm else ag.groupby(["scenario","realm","year"], as_index=False)[value_cols].mean()

def annual_biome_realm_from_parquet(cols):
    df    = load_parquet_all(cols)
    parts = df["BIOME_ID_REALM"].astype(str).str.split("_", n=1, expand=True)
    df["biome_realm"] = parts[0] + "_" + parts[1].replace({r: MERGED_CODE for r in MERGE_TO})
    mmm   = df.groupby(["source","scenario","biome_realm","time"], as_index=False)[cols].mean()
    mmm["year"] = mmm["time"].dt.year
    ag    = mmm.groupby(["source","scenario","biome_realm","year"], as_index=False)[cols].mean()
    return ag.groupby(["scenario","biome_realm","year"], as_index=False)[cols].mean()

# =============================================================================
# SHAPEFILES
# =============================================================================

def load_biome_realm_gdf():
    gdf = gpd.read_file(WWF_SHAPE).to_crs("EPSG:4326")
    gdf = gdf[~gdf["REALM"].isin(["AN"])].copy()
    gdf["realm_code"]  = gdf["REALM"].astype(str).replace({r: MERGED_CODE for r in MERGE_TO})
    gdf["biome_realm"] = gdf["BIOME"].astype(int).astype(str) + "_" + gdf["realm_code"]
    return gdf.dissolve(by="biome_realm", as_index=False, aggfunc="first")[["biome_realm","geometry"]]

def load_biome_realm_gdf_checked(table):
    gdf = load_biome_realm_gdf()
    log(f"Missing in table: {sorted(set(gdf['biome_realm'])-set(table['biome_realm']))[:20]}")
    log(f"Extra in table:   {sorted(set(table['biome_realm'])-set(gdf['biome_realm']))[:20]}")
    return gdf

# =============================================================================
# BIOME-REALM TABLE
# =============================================================================

def compute_biome_realm_pcr_table():
    log("Computing biome-realm PCR table")
    gdf_area    = load_biome_realm_gdf()
    gdf_area["biome_area_km2"] = gdf_area.to_crs("ESRI:54009").geometry.area / 1e6
    gdf_lookup  = dict(zip(gdf_area["biome_realm"], gdf_area["biome_area_km2"]))
    cols        = list(dict.fromkeys(list(PCR_COLS.values()) + [COL_TOTAL]))
    df          = annual_biome_realm_from_parquet(cols)
    records     = []
    base_hist   = df[(df["scenario"]=="historical") & df["year"].between(*HIST_LAST)]
    base_old    = df[(df["scenario"]=="historical") & df["year"].between(*HIST_BASE)]
    for sc in SCENARIOS:
        base_all = base_old  if sc == "historical" else base_hist
        fut_all  = base_hist if sc == "historical" else df[(df["scenario"]==sc) & df["year"].between(*FUT_LAST)]
        for label, col in PCR_COLS.items():
            use_col = COL_TOTAL if col == COL_TOTAL else col
            b = base_all.groupby("biome_realm", as_index=False)[use_col].mean().rename(columns={use_col:"base"})
            f = fut_all.groupby( "biome_realm", as_index=False)[use_col].mean().rename(columns={use_col:"future"})
            m = b.merge(f, on="biome_realm", how="outer")
            m["abs_change_km2"] = m["future"] - m["base"]
            ba = gdf_lookup.get(m["biome_realm"].iloc[0], np.nan)
            m["pct_change"]            = np.where(ba > 0, m["abs_change_km2"]/ba*100, np.nan)
            m["normalized_change_pct"] = np.where(m["base"] >= BASELINE_MIN,
                                                   m["abs_change_km2"]/m["base"]*100, np.nan)
            m["scenario"]  = sc
            m["component"] = label
            records.append(m)
    out = pd.concat(records, ignore_index=True)
    out.to_csv(OUT / "biome_realm_percent_change_gw_lu_both.csv", index=False)
    return out

# =============================================================================
# DRIVER PIXEL MAPS
# All driver labels use "Landuse" (no space) consistently
# =============================================================================

def plot_pixel_driver_direction_all_scenarios():
    log("Computing pixel driver direction")
    all_counts = []
    class_labels = {
        1: "Groundwater driven loss",
        2: "Groundwater driven gain",
        3: "Landuse driven loss",
        4: "Landuse driven gain",
        5: "Mixed loss",
        6: "Mixed gain",
    }
    for sc in FUTURE_S:
        ht = open_timmean_da("historical", COL_TOTAL)
        ft = open_timmean_da(sc,           COL_TOTAL)
        hn = open_timmean_da("historical", COL_NONLU)
        fn = open_timmean_da(sc,           COL_NONLU)
        dgw   = np.abs(fn - hn)
        dlu   = np.abs((ft-fn) - (ht-hn))
        total = dgw + dlu
        sign  = ft - ht
        fs    = total.compute().values
        thr   = float(np.nanpercentile(fs[np.isfinite(fs)], 50)) if np.isfinite(fs).any() else 0.0
        v     = total >= thr
        dom   = xr.full_like(total, np.nan, dtype="float32")
        dom = dom.where(~(v & (dgw > dlu) & (sign < 0)), 1)
        dom = dom.where(~(v & (dgw > dlu) & (sign > 0)), 2)
        dom = dom.where(~(v & (dlu > dgw) & (sign < 0)), 3)
        dom = dom.where(~(v & (dlu > dgw) & (sign > 0)), 4)
        dom = dom.where(~(v & np.isclose(dgw, dlu) & (sign < 0)), 5)
        dom = dom.where(~(v & np.isclose(dgw, dlu) & (sign > 0)), 6)
        dom.name = "dominant_driver_with_direction"
        dom.attrs["scenario"] = sc
        dom.to_netcdf(OUT / f"{sc}_pixel_dominant_driver_with_direction.nc")

        dom_np = dom.compute().values.astype("float32")

        # Load historical GDW area for area-weighted fractions.
        # Historical timmean is used as the reference so fractions reflect
        # the distribution of actual GDW extent rather than pixel count.
        hist_area = ht.compute().values.astype("float32")
        hist_area = np.where(np.isfinite(hist_area), hist_area, 0.0)

        valid_mask  = np.isfinite(dom_np)
        vp          = int(valid_mask.sum())
        total_area  = float(np.nansum(hist_area[valid_mask]))

        for cls, label in class_labels.items():
            mask    = dom_np == cls
            n       = int(np.nansum(mask))
            area_km2 = float(np.nansum(hist_area[mask]))
            all_counts.append({
                "scenario":          sc,
                "class":             cls,
                "label":             label,
                "n_pixels":          n,
                "valid_pixels":      vp,
                "fraction_pct":      n / vp * 100 if vp > 0 else np.nan,
                "area_km2":          area_km2,
                "total_area_km2":    total_area,
                "area_fraction_pct": area_km2 / total_area * 100 if total_area > 0 else np.nan,
            })

    pd.DataFrame(all_counts).to_csv(
        OUT / "pixel_driver_direction_counts_all_scenarios.csv", index=False)
    log("Saved driver direction outputs")

# =============================================================================
# FIGURE 1
# =============================================================================
def plot_figure1_four_panel():
    log("Building Figure 1")

    hist_da = open_timmean_da("historical", PIXEL_VAR)
    lat, lon = hist_da["lat"].values, hist_da["lon"].values
    diff_np  = ((open_timmean_da("ssp370", PIXEL_VAR) - hist_da)
                .where(hist_da >= BASELINE_MIN)
                .compute().values.astype("float32"))

    SCEN_ORDER  = ["ssp126","ssp370","ssp585"]
    SCEN_LABELS = {"ssp126":"SSP1-2.6","ssp370":"SSP3-7.0","ssp585":"SSP5-8.5"}
    loss_vals   = {"ssp126":245,"ssp370":432,"ssp585":341}
    gain_vals   = {"ssp126":194,"ssp370":102,"ssp585":300}

    driver_nc = OUT / "ssp370_pixel_dominant_driver_with_direction.nc"
    if not driver_nc.exists(): plot_pixel_driver_direction_all_scenarios()
    with xr.open_dataset(driver_nc) as ds:
        dom_np = ds["dominant_driver_with_direction"].values.astype("float32")

    csv_path = OUT / "pixel_driver_direction_counts_all_scenarios.csv"
    if not csv_path.exists(): plot_pixel_driver_direction_all_scenarios()
    df_counts = pd.read_csv(csv_path)

    # Regenerate if area_fraction_pct column is missing (old CSV)
    if "area_fraction_pct" not in df_counts.columns:
        log("area_fraction_pct missing from CSV, regenerating driver counts")
        plot_pixel_driver_direction_all_scenarios()
        df_counts = pd.read_csv(csv_path)

    fig = plt.figure(figsize=(72, 52), dpi=300, constrained_layout=False)

    top_b, top_h  = 0.56, 0.39
    cb_b,  cb_h   = 0.515, 0.018
    bot_b, bot_h  = 0.10, 0.34
    map_l, map_w  = 0.035, 0.62
    side_l, side_w = map_l + map_w + 0.035, 0.29

    ax_a    = fig.add_axes([map_l,  top_b, map_w,  top_h], projection=ccrs.Robinson())
    ax_bbar = fig.add_axes([side_l, top_b, side_w, top_h])
    ax_cb   = fig.add_axes([map_l + 0.15*map_w, cb_b, map_w*0.70, cb_h])
    ax_cmap = fig.add_axes([map_l,  bot_b, map_w,  bot_h], projection=ccrs.Robinson())
    ax_d    = fig.add_axes([side_l, bot_b, side_w, bot_h])

    LKW = dict(fontsize=FS["panel"]*S, fontweight="bold", va="top", ha="left")

    # ------------------------------------------------------------------
    # Panel a – pixel change map (SSP3-7.0)
    # ------------------------------------------------------------------
    add_map_background(ax_a, white=True)
    pm_a = ax_a.pcolormesh(lon, lat, np.ma.masked_invalid(diff_np),
                            transform=ccrs.PlateCarree(), cmap=_RDGREY_BU,
                            norm=TwoSlopeNorm(vcenter=0, vmin=-8, vmax=8),
                            shading="auto", rasterized=True, zorder=2)
    ax_a.text(-0.04, 1.03, "(a)", transform=ax_a.transAxes, **LKW)

    cb = fig.colorbar(pm_a, cax=ax_cb, orientation="horizontal",
                      ticks=[-8, -4, 0, 4, 8], extend="both")
    cb.set_label("Area change (km\u00b2)", fontsize=FS["axis"]*S, fontweight="bold")
    cb.ax.tick_params(labelsize=FS["tick"]*S, length=12, width=2.0)
    cb.outline.set_linewidth(2.0)
    ax_cb.axhline(0.72, color="white", alpha=0.18, linewidth=14, zorder=5)

    # ------------------------------------------------------------------
    # Panel b – gain/loss bar chart
    # ------------------------------------------------------------------
    x_ins    = np.arange(len(SCEN_ORDER))
    LOSS_COL = "#B2182B"
    GAIN_COL = "#2166AC"
    loss_arr = np.array([loss_vals[sc] for sc in SCEN_ORDER])
    gain_arr = np.array([gain_vals[sc] for sc in SCEN_ORDER])

    b_loss = ax_bbar.bar(x_ins - 0.17, -loss_arr, width=0.34,
                         color=LOSS_COL, edgecolor="white", lw=2.0, label="Loss")
    b_gain = ax_bbar.bar(x_ins + 0.17,  gain_arr, width=0.34,
                         color=GAIN_COL, edgecolor="white", lw=2.0, label="Gain")

    for bar, val in zip(b_loss, loss_arr):
        ax_bbar.text(bar.get_x() + bar.get_width()/2, -val - 20, f"-{val:,}",
                     ha="center", va="top",
                     fontsize=FS["value"]*S, color=LOSS_COL, fontweight="bold")
    for bar, val in zip(b_gain, gain_arr):
        ax_bbar.text(bar.get_x() + bar.get_width()/2, val + 20, f"{val:,}",
                     ha="center", va="bottom",
                     fontsize=FS["value"]*S, color=GAIN_COL, fontweight="bold")

    ax_bbar.text(-0.18, 1.03, "(b)", transform=ax_bbar.transAxes, **LKW)
    ax_bbar.axhline(0, color="0.30", lw=2.2, zorder=3)
    ax_bbar.set_ylim(-520, 340)
    ax_bbar.set_xticks(x_ins)
    ax_bbar.set_xticklabels([SCEN_LABELS[s] for s in SCEN_ORDER],
                             fontsize=FS["tick"]*S, fontweight="bold")
    ax_bbar.set_ylabel(r"Area change ($10^3$ km$^2$)",
                       fontsize=FS["axis"]*S, fontweight="bold")
    ax_bbar.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda y, _: f"{int(y):,}"))
    ax_bbar.tick_params(axis="y", labelsize=FS["tick"]*S)
    ax_bbar.grid(axis="y", alpha=0.20, linewidth=1.8)
    ax_bbar.legend(frameon=False, loc="lower left",
                   prop={"size": FS["legend"]*S, "weight": "bold"})
    for sp in ("top", "right"): ax_bbar.spines[sp].set_visible(False)
    for sp in ("left", "bottom"): ax_bbar.spines[sp].set_linewidth(2.0)

    # ------------------------------------------------------------------
    # Panel c – dominant driver map (SSP3-7.0)
    # ------------------------------------------------------------------
    CLASS_COLORS = {1: "#08306B", 2: "#6BAED6", 3: "#7F2704",
                    4: "#FDAE6B", 5: "#238B45", 6: "#A1D99B"}
    CLASS_LABELS_MAP = {1: "Groundwater loss", 2: "Groundwater gain",
                        3: "Landuse loss",     4: "Landuse gain",
                        5: "Mixed loss",       6: "Mixed gain"}
    cmap_c, norm_c = discrete_cmap_norm(CLASS_COLORS)
    try: cmap_c.set_bad(color="white")
    except: pass

    add_map_background(ax_cmap, white=True)
    ax_cmap.pcolormesh(lon, lat, np.ma.masked_invalid(dom_np),
                       transform=ccrs.PlateCarree(), cmap=cmap_c, norm=norm_c,
                       shading="auto", rasterized=True, zorder=2)
    ax_cmap.text(-0.04, 1.03, "(c)", transform=ax_cmap.transAxes, **LKW)

    # ------------------------------------------------------------------
    # Panel d – area-weighted driver fraction bars
    # ------------------------------------------------------------------
    LOSS_CLASSES = ["Groundwater driven loss", "Landuse driven loss", "Mixed loss"]
    LOSS_COLORS  = ["#08306B", "#7F2704", "#238B45"]
    GAIN_CLASSES = ["Groundwater driven gain", "Landuse driven gain", "Mixed gain"]
    GAIN_COLORS  = ["#6BAED6", "#FDAE6B", "#A1D99B"]
    y_pos = np.arange(len(SCEN_ORDER))

    for i, sc in enumerate(SCEN_ORDER):
        d = df_counts[df_counts["scenario"] == sc].set_index("label")

        ll = 0.0
        for cls, col in zip(LOSS_CLASSES, LOSS_COLORS):
            val = float(d.loc[cls, "area_fraction_pct"]) if cls in d.index else 0.0
            ax_d.barh(y_pos[i], -val, left=-ll, height=0.5,
                      color=col, edgecolor="white", linewidth=1.4)
            if val >= 5:
                ax_d.text(-ll - val/2, y_pos[i], f"{val:.0f}%",
                          ha="center", va="center",
                          fontsize=FS["value"]*S, color="white", fontweight="bold")
            ll += val

        lg = 0.0
        for cls, col in zip(GAIN_CLASSES, GAIN_COLORS):
            val = float(d.loc[cls, "area_fraction_pct"]) if cls in d.index else 0.0
            ax_d.barh(y_pos[i], val, left=lg, height=0.5,
                      color=col, edgecolor="white", linewidth=1.4)
            if val >= 5:
                ax_d.text(lg + val/2, y_pos[i], f"{val:.0f}%",
                          ha="center", va="center",
                          fontsize=FS["value"]*S, color="white", fontweight="bold")
            lg += val

    ax_d.text(-0.18, 1.03, "(d)", transform=ax_d.transAxes, **LKW)
    ax_d.axvline(0, color="0.25", lw=2.2, zorder=3)
    ax_d.set_yticks(y_pos)
    ax_d.set_yticklabels([SCEN_LABELS[s] for s in SCEN_ORDER],
                          fontsize=FS["tick"]*S, fontweight="bold")
    ax_d.set_xlabel("% GDW area", fontsize=FS["axis"]*S, fontweight="bold")
    ax_d.grid(axis="x", alpha=0.22, linewidth=1.8)
    ax_d.xaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda x, _: str(abs(int(x)))))
    ax_d.tick_params(axis="x", labelsize=FS["tick"]*S)
    ax_d.text(0.25, -0.12, "\u2190 Loss", transform=ax_d.transAxes,
              ha="center", va="top", fontsize=FS["small"]*S, color="0.35")
    ax_d.text(0.75, -0.12, "Gain \u2192", transform=ax_d.transAxes,
              ha="center", va="top", fontsize=FS["small"]*S, color="0.35")
    for sp in ("top", "right"): ax_d.spines[sp].set_visible(False)
    for sp in ("left", "bottom"): ax_d.spines[sp].set_linewidth(2.0)

    # ------------------------------------------------------------------
    # Shared legend for panels c and d
    # ------------------------------------------------------------------
    fig.legend(
        handles=[Patch(facecolor=CLASS_COLORS[i], edgecolor="0.5",
                       label=CLASS_LABELS_MAP[i], linewidth=1.0) for i in range(1, 7)],
        ncol=6, loc="lower center", bbox_to_anchor=(0.50, 0.0),
        frameon=False, handlelength=1.6, handleheight=1.3, columnspacing=2.2,
        prop={"size": FS["legend"]*S},
    )

    fig.savefig(OUT / "figure1_four_panel.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    log("Saved: figure1_four_panel.png")

# =============================================================================
# FIGURE 2
# =============================================================================

def plot_realm_ts_only():
    log("Building Figure 2")
    df = annual_realm_from_parquet([TS_VAR], keep_gcm=True)
    df["value_plot"] = df[TS_VAR] / 1e8
    realms = [r for r in REALM_ORDER if r in set(df["realm"])]
    fig   = plt.figure(figsize=(22, 12), dpi=300, constrained_layout=False)
    ncols, nrows = 3, 2
    left0, bot0  = 0.07, 0.12
    pw = (0.90-(ncols-1)*0.03)/ncols
    ph = (0.80-(nrows-1)*0.06)/nrows
    realm_axes = []
    for row in range(nrows):
        for col in range(ncols):
            realm_axes.append(fig.add_axes([
                left0+col*(pw+0.03), bot0+(nrows-1-row)*(ph+0.06), pw, ph]))

    def _ts(ax, src, title):
        hist = src[(src["scenario"]=="historical") & (src["year"]<=2014)].copy()
        piv  = hist.pivot_table(index="year", columns="source",
                                values="value_plot", aggfunc="mean").sort_index()
        hm, hl, hh = smooth(piv.mean(1)), smooth(piv.min(1)), smooth(piv.max(1))
        ax.fill_between(hm.index, hl.values, hh.values,
                        color=SCEN_COLOR["historical"], alpha=0.18, linewidth=0)
        ax.plot(hm.index, hm.values, color=SCEN_COLOR["historical"], lw=2.0)
        hc = hm.dropna()
        if hc.empty: return
        ly, lv = int(hc.index.max()), float(hc.iloc[-1])
        for sc in FUTURE_S:
            d = src[(src["scenario"]==sc) & (src["year"]>=JOIN_YEAR)].copy()
            if d.empty: continue
            piv2 = d.pivot_table(index="year", columns="source",
                                  values="value_plot", aggfunc="mean").sort_index()
            mr, lr2, hr2 = piv2.mean(1), piv2.min(1), piv2.max(1)
            mrc = mr.dropna()
            if mrc.empty: continue
            sh = lv - float(mrc.iloc[0])
            m, l2, h2 = smooth(mr+sh), smooth(lr2+sh), smooth(hr2+sh)
            sx = np.concatenate([[ly], m.index.values])
            ax.fill_between(sx,
                            np.concatenate([[float(hl.dropna().iloc[-1])], l2.values]),
                            np.concatenate([[float(hh.dropna().iloc[-1])], h2.values]),
                            color=SCEN_COLOR[sc], alpha=0.18, linewidth=0)
            mc = m.dropna()
            ax.plot([ly, int(mc.index.min())], [lv, float(mc.iloc[0])],
                    color=SCEN_COLOR[sc], lw=2.0)
            ax.plot(m.index, m.values, color=SCEN_COLOR[sc], lw=2.0)
        ax.set_title(title, fontsize=FS["title"], fontweight="bold")
        ax.set_ylabel("Area (M km2)", fontsize=FS["axis"])
        ax.tick_params(labelsize=FS["tick"])
        ax.grid(axis="y", alpha=0.25)
        ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=5, prune="both"))
        ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
        for sp in ("top","right"): ax.spines[sp].set_visible(False)

    for realm, ax in zip(realms, realm_axes):
        _ts(ax, df[df["realm"]==realm].copy(), realm)
    for j in range(len(realms), len(realm_axes)):
        realm_axes[j].set_visible(False)
    fig.legend(
        handles=[Line2D([0],[0], color=SCEN_COLOR[s], lw=2.5, label=SCEN_LABEL[s])
                 for s in SCENARIOS],
        frameon=False, ncol=4, fontsize=FS["legend"],
        loc="lower center", bbox_to_anchor=(0.5, 0.01),
    )
    fig.savefig(OUT / "figure2_realm_ts.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    log("Saved: figure2_realm_ts.png")

# =============================================================================
# FIGURE 3
# =============================================================================

def plot_figure3_lollipop():
    log("Building Figure 3")
    df   = annual_realm_from_parquet([COL_TOTAL, COL_NONLU], keep_gcm=False)
    rows = []
    for sc in SCENARIOS:
        blo, bhi = HIST_BASE if sc=="historical" else HIST_LAST
        flo, fhi = HIST_LAST if sc=="historical" else FUT_LAST
        db = df[df["scenario"].eq("historical") & df["year"].between(blo,bhi)]
        df2= df[df["scenario"].eq(sc)           & df["year"].between(flo,fhi)]
        b  = db.groupby("realm",as_index=False)[[COL_TOTAL,COL_NONLU]].mean()
        f  = df2.groupby("realm",as_index=False)[[COL_TOTAL,COL_NONLU]].mean()
        m  = b.merge(f,on="realm",suffixes=("_b","_f"),how="outer")
        m["delta_total"] = (m[f"{COL_TOTAL}_f"]-m[f"{COL_TOTAL}_b"])/1e5
        m["delta_nonlu"] = (m[f"{COL_NONLU}_f"]-m[f"{COL_NONLU}_b"])/1e5
        m["scenario"] = sc
        rows.append(m)
    tab    = pd.concat(rows, ignore_index=True)
    realms = [r for r in REALM_ORDER if r in set(tab["realm"])]
    y_pos  = np.arange(len(realms))[::-1]
    fig, axes = plt.subplots(1, len(SCENARIOS), figsize=(6*len(SCENARIOS), 8), dpi=300)
    for ax, sc in zip(axes, SCENARIOS):
        d = tab[tab["scenario"]==sc].set_index("realm").reindex(realms)
        ax.axvline(0, color="0.60", lw=1.0, zorder=0)
        for yi, vt, vn in zip(y_pos, d["delta_total"], d["delta_nonlu"]):
            if np.isfinite(vt):
                c = "#2166AC" if vt >= 0 else "#B2182B"
                ax.plot([0,vt],[yi+0.10,yi+0.10], color=c, lw=2.5, solid_capstyle="round")
                ax.plot(vt, yi+0.10, "o", color=c, ms=9, zorder=2)
            if np.isfinite(vn):
                c = "#2166AC" if vn >= 0 else "#B2182B"
                ax.plot([0,vn],[yi-0.10,yi-0.10], color=c, lw=2.5, ls="--", solid_capstyle="round")
                ax.plot(vn, yi-0.10, "s", mfc="white", mec=c, ms=9, mew=2.0)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(realms, fontsize=FS["tick"], fontweight="bold")
        ax.set_title(SCEN_LABEL[sc], fontsize=FS["title"], fontweight="bold")
        ax.set_xlabel(r"Area change ($10^3$ km$^2$)", fontsize=FS["axis"], fontweight="bold")
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=5, prune="both"))
        ax.tick_params(axis="x", labelsize=FS["tick"])
        ax.grid(axis="x", alpha=0.22, linewidth=0.8)
        for sp in ("top","right"): ax.spines[sp].set_visible(False)
    fig.legend(
        handles=[
            Line2D([0],[0], color="0.3", marker="o", lw=2.5, ms=9, label="Total GDW"),
            Line2D([0],[0], color="0.3", marker="s", mfc="white", mew=2.0,
                   lw=2.5, ls="--", ms=9, label="GDW without landuse impact"),
            Line2D([0],[0], color="#2166AC", lw=2.5, label="Gain"),
            Line2D([0],[0], color="#B2182B", lw=2.5, label="Loss"),
        ],
        ncol=4, loc="lower center", bbox_to_anchor=(0.5, 0.00),
        frameon=False, fontsize=FS["legend"], handlelength=2.0, columnspacing=1.8,
    )
    fig.tight_layout(rect=[0.0, 0.10, 1.0, 1.0])
    fig.savefig(OUT / "figure3_lollipop_decadal_change.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    log("Saved: figure3_lollipop_decadal_change.png")

# =============================================================================
# FIGURE 4
# =============================================================================

def plot_figure4_biome_map():
    log("Building Figure 4")
    table = compute_biome_realm_pcr_table()
    gdf   = load_biome_realm_gdf_checked(table)
    value_col   = "normalized_change_pct"
    components  = list(PCR_COLS_NORM.keys())
    scenarios   = SCENARIOS
    COMP_LABELS = {
        "Groundwater Impact Only":       "Groundwater-only",
        "Land-use Impact Only":          "Landuse-only",
        "Groundwater + Land-use Impact": "Combined",
    }
    nrows, ncols = len(scenarios), len(components)
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(6*ncols, 4*nrows), dpi=300,
        subplot_kw={"projection": ccrs.Robinson()},
        gridspec_kw={"hspace":-0.03, "wspace":0.03},
    )
    axes = np.array(axes).reshape(nrows, ncols)
    norm = TwoSlopeNorm(vcenter=0, vmin=-PCR_VLIM, vmax=PCR_VLIM)
    for r, sc in enumerate(scenarios):
        for c, comp in enumerate(components):
            ax = axes[r, c]
            add_map_background(ax, white=True)
            ax.coastlines(color="0.25", linewidth=0.8, zorder=3)
            d        = table[(table["scenario"]==sc)&(table["component"]==comp)][["biome_realm",value_col]]
            plot_gdf = gdf.merge(d, on="biome_realm", how="left")
            plot_gdf.plot(column=value_col, ax=ax, transform=ccrs.PlateCarree(),
                          cmap=CMAP_DIVERGING, norm=norm, linewidth=0.0,
                          missing_kwds={"color":"white"}, zorder=2)
            if r == 0:
                ax.set_title(COMP_LABELS.get(comp, comp),
                             fontsize=FS["title"], fontweight="bold", pad=6)
            if c == 0:
                ax.text(-0.06, 0.5, SCEN_LABEL[sc], transform=ax.transAxes,
                        rotation=90, va="center", ha="right",
                        fontsize=FS["axis"], fontweight="bold")
    cax = fig.add_axes([0.20, 0.03, 0.60, 0.012])
    sm  = plt.cm.ScalarMappable(norm=norm, cmap=CMAP_DIVERGING)
    sm.set_array([])
    cb  = fig.colorbar(sm, cax=cax, orientation="horizontal",
                       ticks=[-15,-10,-5,0,5,10,15], extend="both")
    cb.set_label("Area change (%)", fontsize=FS["axis"])
    cb.ax.tick_params(labelsize=FS["tick"])
    cb.outline.set_linewidth(0.8)
    fig.savefig(OUT / "figure4_biome_realm_component_maps.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    log("Saved: figure4_biome_realm_component_maps.png")

"""
Supplementary figures and tables for manuscript.
Paste at the bottom of manuscript_figures_final.py before main().

S1  – Future GDW persistence class map (SSP3-7.0)
S2  – Persistence change maps (months, class gain/loss, transition)
S3  – Biome-realm absolute change maps
S4  – Continent GDW area table (CSV)
"""

from matplotlib.colors import TwoSlopeNorm, ListedColormap, BoundaryNorm

# =============================================================================
# CONTINENT MAPPING
# =============================================================================

REALM_TO_CONTINENT = {
    "Nearctic":                 "North America",
    "Neotropical":              "South America",
    "Afrotropical":             "Africa",
    "Palearctic":               "Europe & Asia",
    "Indo-Malayan":             "Asia (Indo-Malayan)",
    "Australasian & Oceanian":  "Oceania",
}

# =============================================================================
# S1 – Future GDW persistence class map
# =============================================================================

def plot_s1_persistence_class():
    log("Building S1: future persistence class map")

    fut_clim   = open_monthly_clim_da("ssp370", PIXEL_VAR)
    fut_months = (fut_clim >= BASELINE_MIN).sum("month")

    out_nc = OUT / "ssp370_future_persistence_class_per_pixel.nc"
    if not out_nc.exists():
        pers = xr.full_like(fut_months, np.nan, dtype="float32")
        pers = pers.where(~((fut_months >= 1) & (fut_months <= 3)), 1)
        pers = pers.where(~((fut_months >= 4) & (fut_months <= 6)), 2)
        pers = pers.where(~(fut_months >= 7), 3)
        pers.name = "future_persistence_class"
        pers.to_netcdf(out_nc)
    else:
        with xr.open_dataset(out_nc) as ds:
            pers = ds["future_persistence_class"]

    pers_np = pers.compute().values.astype("float32")
    lat = pers["lat"].values
    lon = pers["lon"].values

    PCOL = {1:"#FFD92F", 2:"#66BD3A", 3:"#0571B0"}
    cmap, norm = discrete_cmap_norm(PCOL)

    fig = plt.figure(figsize=(16, 8), dpi=300)
    ax  = plt.axes(projection=ccrs.Robinson())
    add_map_background(ax, white=True)
    ax.pcolormesh(lon, lat, np.ma.masked_invalid(pers_np),
                  transform=ccrs.PlateCarree(), cmap=cmap, norm=norm,
                  shading="auto", rasterized=True, zorder=2)

    handles = [
        Patch(facecolor=PCOL[1], edgecolor="0.4", label="Episodic (1-3 months)"),
        Patch(facecolor=PCOL[2], edgecolor="0.4", label="Seasonal (4-6 months)"),
        Patch(facecolor=PCOL[3], edgecolor="0.4", label="Perennial (7-12 months)"),
    ]
    ax.legend(handles=handles, title="Persistence class",
              frameon=True, framealpha=0.88, edgecolor="0.7",
              loc="lower right", bbox_to_anchor=(1.0, -0.205),
              fontsize=FS["legend"], title_fontsize=FS["legend"])

    fig.savefig(OUT / "S1_persistence_class_ssp370.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    log("Saved: S1_persistence_class_ssp370.png")


# =============================================================================
# S2 – Persistence change maps (3-panel)
# =============================================================================

def plot_s2_persistence_change():
    log("Building S2: persistence change maps")

    hist_clim  = open_monthly_clim_da("historical", PIXEL_VAR)
    fut_clim   = open_monthly_clim_da("ssp370",     PIXEL_VAR)

    hist_months = (hist_clim >= BASELINE_MIN).sum("month")
    fut_months  = (fut_clim  >= BASELINE_MIN).sum("month")

    month_change = fut_months - hist_months

    def classify(m):
        out = xr.full_like(m, np.nan, dtype="float32")
        out = out.where(~((m >= 1) & (m <= 3)), 1)
        out = out.where(~((m >= 4) & (m <= 6)), 2)
        out = out.where(~(m >= 7), 3)
        return out

    hist_class  = classify(hist_months)
    fut_class   = classify(fut_months)
    class_change = fut_class - hist_class
    transition   = hist_class * 10 + fut_class

    valid = np.isfinite(hist_class) & np.isfinite(fut_class)
    month_change  = month_change.where(valid)
    class_change  = class_change.where(valid)
    transition    = transition.where(valid)

    lat = month_change["lat"].values
    lon = month_change["lon"].values
    month_np  = month_change.compute().values.astype("float32")
    class_np  = class_change.compute().values.astype("float32")
    trans_np  = transition.compute().values.astype("float32")

    norm_month = TwoSlopeNorm(vcenter=0, vmin=-6, vmax=6)

    GAINLOSS = {-2:"#5E2A84",-1:"#B28AC7",0:"#F0F0F0",1:"#66BD3A",2:"#1B7837"}
    TRANSCOL = {
        11:"#F7F7F7",12:"#FFE066",13:"#1ABC9C",
        21:"#F4A261",22:"#F7F7F7",23:"#2A9D8F",
        31:"#D7191C",32:"#92C5DE",33:"#F7F7F7",
    }
    gl_cmap,  gl_norm  = discrete_cmap_norm(GAINLOSS)
    tr_cmap,  tr_norm  = discrete_cmap_norm(TRANSCOL)

    fig, axes = plt.subplots(
        1, 3, figsize=(20, 6), dpi=300,
        subplot_kw={"projection": ccrs.Robinson()},
        gridspec_kw={"wspace": 0.04},
    )

    # Panel 1 – change in active months
    add_map_background(axes[0], white=True)
    pm = axes[0].pcolormesh(lon, lat, np.ma.masked_invalid(month_np),
                             transform=ccrs.PlateCarree(), cmap=CMAP_DIVERGING,
                             norm=norm_month, shading="auto", rasterized=True, zorder=2)
    axes[0].text(0.01, 0.97, "(a)", transform=axes[0].transAxes,
                 fontsize=FS["panel"], fontweight="bold", va="top")
    cax1 = fig.add_axes([0.08, 0.16, 0.22, 0.03])
    cb1  = fig.colorbar(pm, cax=cax1, orientation="horizontal",
                        ticks=[-6,-4,-2,0,2,4,6])
    cb1.set_label("Change in GDW-active months", fontsize=FS["small"])
    cb1.ax.tick_params(labelsize=FS["small"])

    # Panel 2 – persistence class gain/loss
    add_map_background(axes[1], white=True)
    axes[1].pcolormesh(lon, lat, np.ma.masked_invalid(class_np),
                       transform=ccrs.PlateCarree(), cmap=gl_cmap, norm=gl_norm,
                       shading="auto", rasterized=True, zorder=2)
    axes[1].text(0.01, 0.97, "(b)", transform=axes[1].transAxes,
                 fontsize=FS["panel"], fontweight="bold", va="top")
    gl_handles = [
        Patch(facecolor=GAINLOSS[k], edgecolor="0.4", label=l)
        for k, l in [(-2,"Loss 2 classes"),(-1,"Loss 1 class"),
                     (0,"No change"),(1,"Gain 1 class"),(2,"Gain 2 classes")]
    ]
    axes[1].legend(handles=gl_handles, frameon=True, framealpha=0.88,
                   edgecolor="0.7", loc="lower right", bbox_to_anchor=(1.0,-0.60),
                   fontsize=FS["small"]-1, ncol=1)

    # Panel 3 – transition map
    add_map_background(axes[2], white=True)
    axes[2].pcolormesh(lon, lat, np.ma.masked_invalid(trans_np),
                       transform=ccrs.PlateCarree(), cmap=tr_cmap, norm=tr_norm,
                       shading="auto", rasterized=True, zorder=2)
    axes[2].text(0.01, 0.97, "(c)", transform=axes[2].transAxes,
                 fontsize=FS["panel"], fontweight="bold", va="top")
    tr_handles = [
        Patch(facecolor=TRANSCOL[k], edgecolor="0.4", label=l)
        for k, l in [(12,"Episodic to Seasonal"),(13,"Episodic to Perennial"),
                     (21,"Seasonal to Episodic"),(23,"Seasonal to Perennial"),
                     (31,"Perennial to Episodic"),(32,"Perennial to Seasonal"),
                     (11,"No class change")]
    ]
    axes[2].legend(handles=tr_handles, frameon=True, framealpha=0.88,
                   edgecolor="0.7", loc="lower right", bbox_to_anchor=(1.0,-0.8),
                   fontsize=FS["small"]-1, ncol=1)

    fig.savefig(OUT / "S2_persistence_change_maps_ssp370.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    log("Saved: S2_persistence_change_maps_ssp370.png")


# =============================================================================
# S3 – Biome-realm absolute change maps
# =============================================================================

def plot_s3_biome_realm_absolute():
    log("Building S3: biome-realm absolute change maps")

    table = compute_biome_realm_pcr_table()
    gdf   = load_biome_realm_gdf_checked(table)

    value_col   = "abs_change_km2"
    components  = list(PCR_COLS_NORM.keys())
    scenarios   = SCENARIOS
    COMP_LABELS = {
        "Groundwater Impact Only":       "Groundwater-only",
        "Land-use Impact Only":          "Landuse-only",
        "Groundwater + Land-use Impact": "Combined",
    }

    # Symmetric vlim at 95th percentile of absolute values
    vals = table[value_col].dropna().abs()
    vlim = float(np.nanpercentile(vals, 95)) if vals.size else 1e4
    vlim = float(np.ceil(vlim / 1000) * 1000)   # round up to nearest 1000

    nrows, ncols = len(scenarios), len(components)
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(6*ncols, 4*nrows), dpi=300,
        subplot_kw={"projection": ccrs.Robinson()},
        gridspec_kw={"hspace":-0.08, "wspace":0.03},
    )
    axes = np.array(axes).reshape(nrows, ncols)
    norm = TwoSlopeNorm(vcenter=0, vmin=-vlim, vmax=vlim)

    for r, sc in enumerate(scenarios):
        for c, comp in enumerate(components):
            ax = axes[r, c]
            add_map_background(ax, white=True)
            d        = table[(table["scenario"]==sc)&(table["component"]==comp)][["biome_realm",value_col]]
            plot_gdf = gdf.merge(d, on="biome_realm", how="left")
            plot_gdf.plot(column=value_col, ax=ax, transform=ccrs.PlateCarree(),
                          cmap=CMAP_DIVERGING, norm=norm, linewidth=0.0,
                          missing_kwds={"color":"white"}, zorder=2)
            if r == 0:
                ax.set_title(COMP_LABELS.get(comp, comp),
                             fontsize=FS["title"], fontweight="bold", pad=6)
            if c == 0:
                ax.text(-0.06, 0.5, SCEN_LABEL[sc], transform=ax.transAxes,
                        rotation=90, va="center", ha="right",
                        fontsize=FS["axis"], fontweight="bold")

    cax = fig.add_axes([0.20, 0.03, 0.60, 0.012])
    sm  = plt.cm.ScalarMappable(norm=norm, cmap=CMAP_DIVERGING)
    sm.set_array([])
    cb  = fig.colorbar(sm, cax=cax, orientation="horizontal", extend="both")
    cb.set_label("Change in GDW area (km2)", fontsize=FS["axis"])
    cb.ax.tick_params(labelsize=FS["tick"])
    cb.outline.set_linewidth(0.8)

    fig.savefig(OUT / "S3_biome_realm_absolute_change.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    log("Saved: S3_biome_realm_absolute_change.png")


# =============================================================================
# S4 – Continent GDW area table (CSV)
# =============================================================================

def make_s4_continent_gdw_table():
    log("Building S4: continent GDW area table")

    df = annual_realm_from_parquet([COL_TOTAL, COL_NONLU], keep_gcm=False)

    rows = []
    for sc in SCENARIOS:
        lo, hi = HIST_LAST if sc == "historical" else FUT_LAST
        d = df[df["scenario"].eq(sc) & df["year"].between(lo, hi)]
        m = d.groupby("realm", as_index=False)[[COL_TOTAL, COL_NONLU]].mean()
        m["scenario"] = sc
        m["period"]   = f"{lo}-{hi}"
        rows.append(m)

    tab = pd.concat(rows, ignore_index=True)
    tab["continent"] = tab["realm"].map(REALM_TO_CONTINENT)

    tab["total_gdw_1000km2"] = tab[COL_TOTAL] / 1e5
    tab["nonlu_gdw_1000km2"] = tab[COL_NONLU] / 1e5

    cont = (
        tab.groupby(["scenario","period","continent"], as_index=False)
        [["total_gdw_1000km2","nonlu_gdw_1000km2"]]
        .sum()
    )

    global_rows = []
    for (sc, per), g in cont.groupby(["scenario","period"]):
        global_rows.append({
            "scenario":           sc,
            "period":             per,
            "continent":          "Global",
            "total_gdw_1000km2":  g["total_gdw_1000km2"].sum(),
            "nonlu_gdw_1000km2":  g["nonlu_gdw_1000km2"].sum(),
        })
    cont = pd.concat([cont, pd.DataFrame(global_rows)], ignore_index=True)
    cont["total_gdw_1000km2"] = cont["total_gdw_1000km2"].round(1)
    cont["nonlu_gdw_1000km2"] = cont["nonlu_gdw_1000km2"].round(1)
    cont = cont.rename(columns={
        "total_gdw_1000km2": "Total GDW area (thousand km2)",
        "nonlu_gdw_1000km2": "GDW without landuse impact (thousand km2)",
    })

    cont_order = [
        "North America","South America","Africa",
        "Europe & Asia","Asia (Indo-Malayan)","Oceania","Global",
    ]
    cont["continent"] = pd.Categorical(cont["continent"],
                                        categories=cont_order, ordered=True)
    cont = cont.sort_values(["scenario","continent"]).reset_index(drop=True)

    out_csv = OUT / "S4_continent_gdw_area_table.csv"
    cont.to_csv(out_csv, index=False)
    log(f"Saved: {out_csv}")

    hist = cont[cont["scenario"]=="historical"][
        ["continent","period",
         "Total GDW area (thousand km2)",
         "GDW without landuse impact (thousand km2)"]
    ]
    log("\nHistorical GDW area by continent (2005-2014):")
    log(hist.to_string(index=False))

    return cont

# =============================================================================
# MONTHLY CLIMATOLOGY CHANGE ANIMATION
# =============================================================================

from matplotlib.animation import FuncAnimation, PillowWriter, FFMpegWriter
from matplotlib.gridspec import GridSpec
from matplotlib import patheffects
from matplotlib.patches import Rectangle

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]

def plot_monthly_climatology_change_animation(
    sc="ssp370",
    var=COL_TOTAL,
    baseline_sc="historical",
    out_name=None,
    fps=1.2,
    save_mp4=False,
):
    log("=" * 90)
    log(f"[monthly-animation] Scenario: {sc}")
    log(f"[monthly-animation] Variable: {var}")
    log(f"[monthly-animation] Baseline: {baseline_sc}")
    log(f"[monthly-animation] BASELINE_MIN: {BASELINE_MIN}")
    log(f"[monthly-animation] Output directory: {OUT}")

    HOTSPOTS = {
        "Central Valley": [-123, -118, 34, 40],
        "North India": [72, 82, 24, 33],
        "North China Plain": [112, 121, 33, 40],
        "Sahel": [-18, 35, 10, 18],
    }

    log("[monthly-animation] Opening monthly climatology datasets")
    hist = open_monthly_clim_da(baseline_sc, var).sortby("month")
    fut  = open_monthly_clim_da(sc,          var).sortby("month")

    log("[monthly-animation] Aligning grids and months")
    hist, fut = xr.align(hist, fut, join="inner")

    hist_active = hist >= BASELINE_MIN
    fut_active  = fut  >= BASELINE_MIN

    change = (fut - hist).where(hist_active | fut_active)

    total_loss = hist_active & (~fut_active)
    first_loss_month = total_loss.idxmax("month").where(total_loss.any("month"))

    log("[monthly-animation] Computing robust color scale")
    vals = change.compute().values.astype("float32")
    finite_vals = vals[np.isfinite(vals)]

    vmax = float(np.nanpercentile(np.abs(finite_vals), 98)) if finite_vals.size else 1.0
    vmax = max(vmax, 1.0)

    log(f"[monthly-animation] Color scale: {-vmax:.2f} to +{vmax:.2f} km2 per cell")

    lat = change["lat"].values
    lon = change["lon"].values
    months = [int(m) for m in change["month"].values]

    log(f"[monthly-animation] Months found: {months}")

    log("[monthly-animation] Computing global monthly totals")
    monthly_net = (
        change.sum(("lat", "lon"), skipna=True)
        .compute()
        .values
        .astype("float64")
    )
    monthly_gain = (
        change.where(change > 0)
        .sum(("lat", "lon"), skipna=True)
        .compute()
        .values
        .astype("float64")
    )
    monthly_loss = (
        change.where(change < 0)
        .sum(("lat", "lon"), skipna=True)
        .compute()
        .values
        .astype("float64")
    )

    net_k = monthly_net / 1e3
    gain_k = monthly_gain / 1e3
    loss_k = monthly_loss / 1e3

    ymax = np.nanmax([
        np.nanmax(np.abs(net_k)),
        np.nanmax(np.abs(gain_k)),
        np.nanmax(np.abs(loss_k)),
    ])
    ymax = max(float(ymax) * 1.20, 1.0)

    log(f"[monthly-animation] Time-series y-limit: ±{ymax:.1f} thousand km2")

    log("[monthly-animation] Initializing figure")
    fig = plt.figure(figsize=(34, 13), dpi=220)
    fig.patch.set_alpha(0.0)

    gs = GridSpec(
        4, 4,
        width_ratios=[1.30, 4.20, 0.12, 1.85],
        height_ratios=[0.70, 1, 1, 1],
        wspace=0.035,
        hspace=0.10,
    )

    ax_insets = [
        fig.add_subplot(gs[i, 0], projection=ccrs.PlateCarree())
        for i in range(4)
    ]

    ax = fig.add_subplot(gs[:, 1], projection=ccrs.Robinson())
    stats_ax = fig.add_subplot(gs[0, 3])
    ax_side = fig.add_subplot(gs[1:, 3])

    stats_ax.axis("off")
    stats_ax.patch.set_alpha(0.0)

    def style_map_axis(a, extent=None, global_map=False, inset=False):
        a.patch.set_alpha(0.0)

        if global_map:
            a.set_global()
            a.set_extent([-180, 180, -58, 90], crs=ccrs.PlateCarree())
        else:
            a.set_extent(extent, crs=ccrs.PlateCarree())

        # No land or ocean fill. Transparent background.
        # Only coastlines and borders provide geographic context.
        a.coastlines(
            linewidth=1.6 if not inset else 1.2,
            color="0.30",
            zorder=8,
        )
        a.add_feature(
            cfeature.BORDERS.with_scale("110m"),
            linewidth=0.55 if not inset else 0.40,
            edgecolor="0.58",
            zorder=8,
        )
        a.axis("off")

    style_map_axis(ax, global_map=True)

    norm = TwoSlopeNorm(vcenter=0, vmin=-vmax, vmax=vmax)

    first_month = months[0]
    first_change = change.sel(month=first_month).compute().values.astype("float32")

    prev_lost0 = (
        np.isfinite(first_loss_month)
        &
        (first_loss_month < first_month)
    ).compute().values.astype(bool)

    new_lost0 = (
        first_loss_month == first_month
    ).compute().values.astype(bool)

    log("[monthly-animation] Drawing global map layers")
    pm = ax.pcolormesh(
        lon, lat,
        np.ma.masked_invalid(first_change),
        transform=ccrs.PlateCarree(),
        cmap=_RDGREY_BU,
        norm=norm,
        shading="auto",
        rasterized=True,
        zorder=2,
    )

    prev_loss_layer = ax.pcolormesh(
        lon, lat,
        np.ma.masked_where(~prev_lost0, prev_lost0.astype("float32")),
        transform=ccrs.PlateCarree(),
        cmap=ListedColormap(["#6b6b6b"]),
        shading="auto",
        rasterized=True,
        alpha=0.45,
        zorder=4,
    )

    new_loss_layer = ax.pcolormesh(
        lon, lat,
        np.ma.masked_where(~new_lost0, new_lost0.astype("float32")),
        transform=ccrs.PlateCarree(),
        cmap=ListedColormap(["black"]),
        shading="auto",
        rasterized=True,
        alpha=0.98,
        zorder=5,
    )

    log("[monthly-animation] Drawing hotspot boxes on global map")
    for name, (xmin, xmax, ymin, ymax_) in HOTSPOTS.items():
        ax.add_patch(
            Rectangle(
                (xmin, ymin),
                xmax - xmin,
                ymax_ - ymin,
                transform=ccrs.PlateCarree(),
                fill=False,
                edgecolor="black",
                linewidth=2.8,
                zorder=9,
            )
        )

    cb = fig.colorbar(
        pm,
        ax=ax,
        orientation="horizontal",
        pad=0.035,
        shrink=0.76,
        extend="both",
    )
    cb.set_label("Change in GDW area per cell (km$^2$)", fontsize=28)
    cb.ax.tick_params(labelsize=24, length=8, width=1.6)
    cb.outline.set_linewidth(1.6)
    cb.ax.set_facecolor("none")

    ax.legend(
        handles=[
            Patch(facecolor="black", edgecolor="black", label="New disappearance"),
            Patch(facecolor="#6b6b6b", edgecolor="#6b6b6b", alpha=0.55, label="Earlier disappearance"),
        ],
        loc="lower left",
        frameon=True,
        framealpha=0.92,
        fontsize=22,
    )

    log("[monthly-animation] Drawing hotspot inset panels")
    inset_artists = []

    for inset_ax, (name, extent) in zip(ax_insets, HOTSPOTS.items()):
        xmin, xmax, ymin, ymax_ = extent
        pad_x = (xmax - xmin) * 0.08
        pad_y = (ymax_ - ymin) * 0.08
        ex = [xmin - pad_x, xmax + pad_x, ymin - pad_y, ymax_ + pad_y]

        style_map_axis(inset_ax, extent=ex, global_map=False, inset=True)

        pm_i = inset_ax.pcolormesh(
            lon, lat,
            np.ma.masked_invalid(first_change),
            transform=ccrs.PlateCarree(),
            cmap=_RDGREY_BU,
            norm=norm,
            shading="auto",
            rasterized=True,
            zorder=2,
        )

        prev_i = inset_ax.pcolormesh(
            lon, lat,
            np.ma.masked_where(~prev_lost0, prev_lost0.astype("float32")),
            transform=ccrs.PlateCarree(),
            cmap=ListedColormap(["#6b6b6b"]),
            shading="auto",
            rasterized=True,
            alpha=0.45,
            zorder=4,
        )

        new_i = inset_ax.pcolormesh(
            lon, lat,
            np.ma.masked_where(~new_lost0, new_lost0.astype("float32")),
            transform=ccrs.PlateCarree(),
            cmap=ListedColormap(["black"]),
            shading="auto",
            rasterized=True,
            alpha=0.98,
            zorder=5,
        )

        inset_ax.text(
            0.03, 0.95,
            name,
            transform=inset_ax.transAxes,
            ha="left",
            va="top",
            fontsize=22,
            fontweight="bold",
            bbox=dict(
                facecolor="white",
                edgecolor="none",
                alpha=0.90,
                pad=4.5,
            ),
            zorder=10,
        )

        inset_artists.append((pm_i, prev_i, new_i))

    log("[monthly-animation] Creating time-series panel")
    x = np.arange(1, len(months) + 1)
    xlabels = [MONTH_NAMES[m - 1] for m in months]

    ax_side.patch.set_alpha(0.0)

    net_line, = ax_side.plot([], [], lw=6.0, label="Net")
    gain_line, = ax_side.plot([], [], lw=6.0, label="Gain")
    loss_line, = ax_side.plot([], [], lw=6.0, label="Loss")

    for line in [net_line, gain_line, loss_line]:
        line.set_path_effects([
            patheffects.Stroke(linewidth=12.0, foreground="white"),
            patheffects.Normal(),
        ])

    net_point, = ax_side.plot([], [], "o", ms=16)
    gain_point, = ax_side.plot([], [], "o", ms=16)
    loss_point, = ax_side.plot([], [], "o", ms=16)

    ax_side.axhline(0, color="0.25", lw=2.2)
    ax_side.set_xlim(0.7, len(months) + 0.3)
    ax_side.set_ylim(-ymax, ymax)
    ax_side.set_xticks(x)
    ax_side.set_xticklabels(xlabels, rotation=45, ha="right", fontsize=22)
    ax_side.set_ylabel(r"Monthly area change ($10^3$ km$^2$)", fontsize=26)
    ax_side.grid(axis="y", alpha=0.18, linewidth=1.8)
    ax_side.grid(axis="x", visible=False)

    for sp in ("top", "right"):
        ax_side.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax_side.spines[sp].set_linewidth(2.4)
        ax_side.spines[sp].set_color("0.25")

    ax_side.tick_params(axis="y", labelsize=22, width=2.0, length=7)

    ax_side.legend(
        frameon=False,
        fontsize=24,
        loc="upper left",
        handlelength=2.2,
    )

    stats_text = stats_ax.text(
        0.02, 0.96,
        "",
        transform=stats_ax.transAxes,
        fontsize=30,
        fontweight="bold",
        va="top",
        ha="left",
        linespacing=1.28,
        bbox=dict(
            facecolor="white",
            edgecolor="0.80",
            boxstyle="round,pad=0.55",
            alpha=0.95,
        ),
    )

    log("[monthly-animation] Initializing animation update function")

    def update(frame_idx):
        month = months[frame_idx]
        month_label = MONTH_NAMES[month - 1]
        xx = x[:frame_idx + 1]

        arr = change.sel(month=month).compute().values.astype("float32")

        prev_lost = (
            np.isfinite(first_loss_month)
            &
            (first_loss_month < month)
        ).compute().values.astype(bool)

        new_lost = (
            first_loss_month == month
        ).compute().values.astype(bool)

        arr_masked = np.ma.masked_invalid(arr)
        prev_masked = np.ma.masked_where(~prev_lost, prev_lost.astype("float32"))
        new_masked = np.ma.masked_where(~new_lost, new_lost.astype("float32"))

        pm.set_array(arr_masked.ravel())
        prev_loss_layer.set_array(prev_masked.ravel())
        new_loss_layer.set_array(new_masked.ravel())

        for pm_i, prev_i, new_i in inset_artists:
            pm_i.set_array(arr_masked.ravel())
            prev_i.set_array(prev_masked.ravel())
            new_i.set_array(new_masked.ravel())

        net_line.set_data(xx, net_k[:frame_idx + 1])
        gain_line.set_data(xx, gain_k[:frame_idx + 1])
        loss_line.set_data(xx, loss_k[:frame_idx + 1])

        net_point.set_data([frame_idx + 1], [net_k[frame_idx]])
        gain_point.set_data([frame_idx + 1], [gain_k[frame_idx]])
        loss_point.set_data([frame_idx + 1], [loss_k[frame_idx]])

        stats_text.set_text(
            f"{month_label}\n"
            f"Net   {net_k[frame_idx]:+.1f}\n"
            f"Gain  {gain_k[frame_idx]:+.1f}\n"
            f"Loss  {loss_k[frame_idx]:+.1f}"
        )

        return (
            pm,
            prev_loss_layer,
            new_loss_layer,
            *[a for trio in inset_artists for a in trio],
            net_line,
            gain_line,
            loss_line,
            net_point,
            gain_point,
            loss_point,
            stats_text,
        )

    update(0)

    log("[monthly-animation] Creating FuncAnimation object")
    anim = FuncAnimation(
        fig,
        update,
        frames=len(months),
        interval=900,
        blit=False,
    )

    if out_name is None:
        suffix = "mp4" if save_mp4 else "gif"
        out_name = OUT / f"monthly_climatology_presentation_{sc}.{suffix}"

    out_name = Path(out_name)
    out_name.parent.mkdir(parents=True, exist_ok=True)

    log(f"[monthly-animation] Saving animation: {out_name}")

    if out_name.suffix.lower() == ".mp4":
        anim.save(
            out_name,
            writer=FFMpegWriter(fps=fps, bitrate=4000),
            savefig_kwargs={
                "transparent": True,
                "facecolor": "none",
                "edgecolor": "none",
            },
        )
    else:
        anim.save(
            out_name,
            writer=PillowWriter(fps=fps),
            savefig_kwargs={
                "transparent": True,
                "facecolor": "none",
                "edgecolor": "none",
            },
        )

    plt.close(fig)

    log(f"[monthly-animation] Saved: {out_name}")
    log("=" * 90)

    return out_name
# =============================================================================
# SUPPLEMENTARY MAIN – call all four
# =============================================================================

def run_supplementary():
    log("Running supplementary figures and tables")
    plot_s1_persistence_class()
    plot_s2_persistence_change()
    plot_s3_biome_realm_absolute()
    make_s4_continent_gdw_table()
    log("Supplementary done.")

# =============================================================================
# MAIN
# =============================================================================

def main():
    log(f"Output: {OUT}")

    # Main manuscript figures from the existing workflow.
    # plot_pixel_driver_direction_all_scenarios()
    # plot_figure1_four_panel()

    # New monthly climatology animation.
    # Default: SSP3-7.0 versus historical, Jan to Dec.
    plot_monthly_climatology_change_animation(sc="ssp370", save_mp4=False)

    # To make one animation for each future scenario, use this instead:
    # for sc in FUTURE_S:
    #     plot_monthly_climatology_change_animation(sc=sc, save_mp4=False)

    # Optional existing outputs.
    # plot_realm_ts_only()
    # plot_figure3_lollipop()
    # plot_figure4_biome_map()
    # run_supplementary()

    log("Done.")

if __name__ == "__main__":
    main()