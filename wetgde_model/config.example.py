"""
config.py  --  all paths, thresholds, and run parameters.

Run flags (set any combination to 1):
    RUN_ENSEMBLE=1      ensemble member, biome x realm, QA + open water
    RUN_GCMS=1          all 5 GCMs, realm only, QA + open water
    RUN_SENSITIVITY=1   threshold sweep on ensemble, realm only, QA + open water

Ensemble freeze options (only apply when RUN_ENSEMBLE=1):
    FREEZE_LU=1    freeze LU to historical reference period, WTD dynamic
                   uses LU period mean over LU_FREEZE_START..LU_FREEZE_END
    FREEZE_WTD=1   freeze WTD to historical monthly climatology, LU dynamic
                   climatology computed from historical/ensemble.zarr over WTD_CLIM_WINDOW
                   mask computed inline (pre-written NC not used for this path)
    Neither set    full dynamic: WTD dynamic, LU dynamic
    Both set       runs all three variants: full, freeze_lu, freeze_wtd

LU freeze settings (used when FREEZE_LU=1):
    LU_FREEZE_MODE=period   period | year
    LU_FREEZE_START=1995
    LU_FREEZE_END=2014
    FIX_LU_YEAR=2000

WTD climatology settings (used when FREEZE_WTD=1):
    WTD_CLIM_WINDOW=1995-01-01,2014-12-31
    Climatology is always computed from {wtd_base_dir}/historical/ensemble.zarr.
    No pre-built climatology file is expected or needed.

LU general:
    APPLY_LU_MASK=1         weight area by (1 - lu_frac)  default: 1
    INCLUDE_PASTURE=0

Sensitivity thresholds (comma-separated):
    SAT_THRESHOLDS   default "0.3,0.4,0.5,0.6,0.7"
    WTD_THRESHOLDS   default "3.0,4.0,5.0,6.0,7.0"

Sensitivity aggregation:
    SENS_AGG_YEARS=10
    SENS_HIST_END_YEAR
    SENS_FUT_END_YEAR

Process-based model (Modules 1-5):
    PCR_ISIMIP_ROOT   root directory for PCR-GLOBWB ISIMIP3 diagnostic outputs
                      default: /projects/2/managed_datasets/hypflowsci6_v1.0/output
    RUN_PROCESS_MODEL=1   run classify + dependency + loss + feedback + uncertainty
    BASELINE_START    first year of historical baseline for loss/uncertainty (default 1995)
    BASELINE_END      last year of historical baseline (default 2014)
    PROJECTION_YEARS  years to accumulate recharge deficit in feedback module (default 35)

Filters:
    GCM=<member>        e.g. GCM=gfdl-esm4
    SCENARIO=<scenario> e.g. SCENARIO=ssp370
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


CMIP6_GCMS: List[str] = [
    "gfdl-esm4",
    "ipsl-cm6a-lr",
    "mpi-esm1-2-hr",
    "mri-esm2-0",
    "ukesm1-0-ll",
]
ENSEMBLE_MEMBER: str = "ensemble"
ALL_SCENARIOS: List[str] = ["historical", "ssp126", "ssp370", "ssp585"]


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default).strip() or default

def _env_int(key: str, default: int) -> int:
    v = os.environ.get(key)
    return int(v) if v not in (None, "") else default

def _env_opt_int(key: str) -> Optional[int]:
    v = os.environ.get(key)
    return int(v) if v not in (None, "") else None

def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y")

def _env_floats(key: str, default: List[float]) -> List[float]:
    v = os.environ.get(key)
    if not v:
        return default
    return [float(x.strip()) for x in v.split(",") if x.strip()]


@dataclass
class Config:

    # ---- run flags ----
    run_ensemble: bool = field(default_factory=lambda: _env_bool("RUN_ENSEMBLE", False))
    run_gcms: bool = field(default_factory=lambda: _env_bool("RUN_GCMS", False))
    run_sensitivity: bool = field(default_factory=lambda: _env_bool("RUN_SENSITIVITY", False))
    run_process_model: bool = field(default_factory=lambda: _env_bool("RUN_PROCESS_MODEL", False))

    # ---- ensemble freeze options ----
    freeze_lu: bool = field(default_factory=lambda: _env_bool("FREEZE_LU", False))
    freeze_wtd: bool = field(default_factory=lambda: _env_bool("FREEZE_WTD", False))

    # ---- input: sat + WTD ----
    sat_dir: str = _env("SAT_DIR", "/projects/prjs1578/sat_future")
    wtd_base_dir: str = _env(
        "WTD_BASE_DIR", "/projects/prjs1222/globgm_output/cmip6/monthly"
    )

    # ---- input: QA ----
    qa_dir: str = _env(
        "QA_DIR",
        "/path/to/from_projects/futurewetgde/quality_flags/",
    )

    # ---- input: open water mask ----
    open_water_mask_tif: str = _env(
        "OPEN_WATER_MASK_TIF",
        "/path/to/glwd_rebuilt_masks/glwd_open_water_mask.tif",
    )

    # ---- input: PCR land use ----
    pcr_corrected_root: str = _env(
        "PCR_CORRECTED_ROOT",
        "/path/to/from_projects/futurewetgde/quality_flags/future_agric_area/pcr_irrigated_corrected",
    )
    pcr_root: str = _env(
        "PCR_ROOT",
        "/path/to/from_projects/futurewetgde/quality_flags/future_agric_area/pcr_irrigated",
    )

    # ---- input: PCR ISIMIP3 diagnostics (gwRecharge, actualET, precipitation) ----
    # Used by: classify.py, dependency.py, loss.py, feedback.py
    pcr_isimip_root: str = _env(
        "PCR_ISIMIP_ROOT",
        "/projects/2/managed_datasets/hypflowsci6_v1.0/output",
    )

    # ---- cell area file ----
    cell_area_path: str = _env(
        "CELL_AREA_PATH",
        "/path/to/paper_2/revisions/shapefiles/cellsize05min.nc",
    )
    cell_area_var: str = _env("CELL_AREA_VAR", "cell_area")
    cell_area_units: str = _env("CELL_AREA_UNITS", "m2")

    # ---- output paths ----
    out_nc_dir: str = _env(
        "OUT_NC_DIR",
        "/path/to/paper_3/new_outputs/WetGDEs_fgdw_gdi",
    )
    out_parquet_dir: str = _env(
        "OUT_PARQUET_DIR",
        "/path/to/paper_3/new_outputs/WetGDEs_fgdw_gdi",
    )
    log_dir: str = _env(
        "LOG_DIR",
        "/path/to/paper_3/new_outputs/WetGDEs_fgdw_gdi/logs",
    )

    # ---- shapefile ----
    biome_shp: str = _env(
        "BIOME_SHP",
        "/path/to/from_projects/futurewetgde/shapefiles/biomes_new/biomes/wwf_terr_ecos.shp",
    )

    # ---- standard thresholds ----
    sat_threshold: float = float(_env("SAT_THRESHOLD", "0.5"))
    wtd_threshold: float = float(_env("WTD_THRESHOLD", "5.0"))

    # ---- LU general ----
    apply_lu_mask: bool = field(default_factory=lambda: _env_bool("APPLY_LU_MASK", True))
    include_pasture: bool = field(default_factory=lambda: _env_bool("INCLUDE_PASTURE", False))

    # ---- LU freeze settings (FREEZE_LU=1) ----
    lu_freeze_mode: str = _env("LU_FREEZE_MODE", "period")
    lu_freeze_start: int = field(default_factory=lambda: _env_int("LU_FREEZE_START", 1995))
    lu_freeze_end: int = field(default_factory=lambda: _env_int("LU_FREEZE_END", 2014))
    fix_lu_year: int = field(default_factory=lambda: _env_int("FIX_LU_YEAR", 2000))

    # ---- WTD climatology settings (FREEZE_WTD=1) ----
    wtd_clim_window: str = _env("WTD_CLIM_WINDOW", "1995-01-01,2014-12-31")

    # ---- sensitivity thresholds (25-combination grid) ----
    sensitivity_sat_thresholds: List[float] = field(
        default_factory=lambda: _env_floats("SAT_THRESHOLDS", [0.3, 0.4, 0.5, 0.6, 0.7])
    )
    sensitivity_wtd_thresholds: List[float] = field(
        default_factory=lambda: _env_floats("WTD_THRESHOLDS", [3.0, 4.0, 5.0, 6.0, 7.0])
    )

    # ---- time range ----
    start_year: int = field(default_factory=lambda: _env_int("START_YEAR", 1979))
    end_year: int = field(default_factory=lambda: _env_int("END_YEAR", 2050))

    # ---- sensitivity aggregation window ----
    sens_agg_years: int = field(default_factory=lambda: _env_int("SENS_AGG_YEARS", 10))
    sens_hist_end_year: Optional[int] = field(
        default_factory=lambda: _env_opt_int("SENS_HIST_END_YEAR")
    )
    sens_fut_end_year: Optional[int] = field(
        default_factory=lambda: _env_opt_int("SENS_FUT_END_YEAR")
    )

    # ---- process-based model settings (Modules 1-5) ----
    # Historical baseline window for loss detection and uncertainty decomposition.
    baseline_start: int = field(default_factory=lambda: _env_int("BASELINE_START", 1995))
    baseline_end: int = field(default_factory=lambda: _env_int("BASELINE_END", 2014))
    # Years to accumulate recharge deficit in feedback.py (2015-2050 = 35 years).
    projection_years: int = field(default_factory=lambda: _env_int("PROJECTION_YEARS", 35))

    # ---- GCMs / scenarios ----
    gcms: List[str] = field(default_factory=lambda: list(CMIP6_GCMS))
    scenarios: List[str] = field(default_factory=lambda: list(ALL_SCENARIOS))

    # ---- filters ----
    only_member: Optional[str] = field(
        default_factory=lambda: os.environ.get("GCM", "").strip() or None
    )
    only_scenario: Optional[str] = field(
        default_factory=lambda: os.environ.get("SCENARIO", "").strip() or None
    )

    # ---- small test / regional subset ----
    small_test: bool = field(default_factory=lambda: _env_bool("SMALL_TEST", False))
    region_name: str = _env("REGION", "amazon")
    regions: dict = field(default_factory=lambda: {
        "great_plains": dict(lat=(25.0,  50.0), lon=(-106.0, -94.0)),
        "sahel":        dict(lat=(10.0,  20.0), lon=(-20.0,   30.0)),
        "amazon":       dict(lat=(-15.0,  5.0), lon=(-75.0,  -50.0)),
        "europe":       dict(lat=(36.0,  60.0), lon=(-10.0,   30.0)),
        "australia_se": dict(lat=(-40.0,-25.0), lon=(140.0,  155.0)),
    })

    # ---- tiling / batching ----
    tile_y: int = field(default_factory=lambda: _env_int("TILE_Y", 360))
    tile_x: int = field(default_factory=lambda: _env_int("TILE_X", 720))
    time_batch: int = field(default_factory=lambda: _env_int("TIME_BATCH", 12))
    spatial_chunk: int = field(default_factory=lambda: _env_int("SPATIAL_CHUNK", 512))

    # ---- output control ----
    parquet_codec: str = _env("PARQUET_CODEC", "snappy")
    skip_existing: bool = field(default_factory=lambda: _env_bool("SKIP_EXISTING", True))
    write_nc: bool = field(default_factory=lambda: _env_bool("WRITE_NC", False))

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def lu_vars(self) -> List[str]:
        base = ["rainfed", "nonpaddy", "paddy", "urban"]
        if self.include_pasture:
            base.append("pasture")
        return base

    @property
    def pcr_files(self) -> Dict[str, dict]:
        lu_dir = Path(
            "/path/to/from_projects/futurewetgde"
            "/quality_flags/future_agric_area/pcr_irrigated/lu_total_2014_2015split"
        )
        hist = lu_dir / "lu_total_hist_ssp2_1970-2014_clamp01.nc"
        return {
            "historical": {"hist": hist},
            "ssp126":     {"hist": hist, "fut": lu_dir / "lu_total_ssp1_2015-2100_clamp01.nc"},
            "ssp370":     {"hist": hist, "fut": lu_dir / "lu_total_ssp3_2015-2100_clamp01.nc"},
            "ssp585":     {"hist": hist, "fut": lu_dir / "lu_total_ssp5_2015-2100_clamp01.nc"},
        }

    @property
    def baseline_period(self) -> tuple:
        """Convenience tuple for uncertainty.time_of_emergence and loss detection."""
        return (str(self.baseline_start), str(self.baseline_end))

    def wtd_clim_zarr_path(self, member: str = "ensemble") -> str:
        return str(Path(self.wtd_base_dir) / "historical" / f"{member}.zarr")

    def ensemble_run_variants(self) -> List[str]:
        variants = ["full"]
        if self.freeze_lu:
            variants.append("freeze_lu")
        if self.freeze_wtd:
            variants.append("freeze_wtd")
        return variants

    def validate(self) -> None:
        if not any([
            self.run_ensemble,
            self.run_gcms,
            self.run_sensitivity,
            self.run_process_model,
        ]):
            raise ValueError(
                "Nothing to run. Set at least one of: "
                "RUN_ENSEMBLE=1, RUN_GCMS=1, RUN_SENSITIVITY=1, RUN_PROCESS_MODEL=1"
            )

    def agg_window_for_scenario(self, scenario: str, last_year: int):
        end = (
            self.sens_hist_end_year if scenario == "historical" else self.sens_fut_end_year
        ) or last_year
        return end - self.sens_agg_years + 1, end

    def sat_path(self, scenario: str) -> str:
        return str(Path(self.sat_dir) / f"satAreaFrac_monthly_ensemble_mean_{scenario}.nc")

    def gcm_sat_path(self, member: str, scenario: str) -> str:
        return str(
            Path("/projects/prjs1222/globgm_input/_data/cmip6_input")
            / member / scenario / "sat_area_fraction_monthly.nc"
        )

    def wtd_path(self, member: str, scenario: str) -> str:
        return str(Path(self.wtd_base_dir) / scenario / f"{member}.zarr")

    def nc_out_path(self, member: str, scenario: str) -> str:
        base = Path(self.out_nc_dir)
        if member == "ensemble":
            p = base / "ensemble" / scenario / "nc" / f"wetGDE_paper3_{scenario}_5arcmin.nc"
        else:
            p = base / "gcms" / member / scenario / "nc" / f"wetGDE_{member}_{scenario}.nc"
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)

    def parquet_out_path(self, member: str, scenario: str, variant: str = "full") -> str:
        base = Path(self.out_parquet_dir)
        tag  = f"_{variant}" if variant and variant != "full" else ""
        name = f"wetGDE_area_{member}_{scenario}{tag}.parquet"
        if member == "ensemble":
            p = base / "ensemble" / scenario / "parquet" / name
        else:
            p = base / "gcms" / member / scenario / "parquet" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)

    def sensitivity_parquet_path(self) -> str:
        Path(self.out_parquet_dir).mkdir(parents=True, exist_ok=True)
        return str(Path(self.out_parquet_dir) / "wetGDE_sensitivity_ensemble.parquet")

    def process_model_out_dir(self, member: str, scenario: str) -> str:
        """Output directory for process-based model results (Modules 1-5)."""
        p = Path(self.out_nc_dir) / "process_model" / member / scenario
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


def get_config() -> Config:
    return Config()