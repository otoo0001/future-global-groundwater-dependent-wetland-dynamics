#!/usr/bin/env python3
"""
Landscape GDW wet-month animation with a subtle hillshade, coastlines, and
legend.

TEST MODE
---------
TEST_MODE = True:
    - loads only TEST_YEAR;
    - renders TEST_FRAMES frames;
    - writes to frames_annual_test/.

FULL MODE
---------
TEST_MODE = False:
    - loads 1980-2019;
    - interpolates between consecutive years;
    - writes to frames_annual/.

Hillshade design
----------------
The shading is meant to read as a faint texture on the land colour, not as a
relief map in its own right. Three things keep it subtle:

  1. No percentile stretch. Stretching p2 to p98 forces the full tonal range
     onto whatever spread the data happen to have, which turns flat terrain
     into speckle. The raw 0-1 illumination is used directly.

  2. The effective vertical exaggeration is scaled to the display cell size
     against HILLSHADE_REFERENCE_SPACING_M, set so that the result lands near
     7 at the roughly 7 km display grid. Values near 70 saturate the shading
     into fully lit and fully dark faces with nothing between.

  3. The blend is a multiplicative deviation about the land base colour, with
     a deeper shadow than highlight and a hard cap below white. Multiplying
     all three channels by one scalar preserves hue exactly, so the land
     stays its own colour and never drifts toward grey. The previous grey
     cast came from clipping the highlight into white, not from the blend.

Smoothing
---------
The DEM is smoothed with a separable binomial kernel before the gradient is
taken, and the illumination is smoothed once afterwards. This removes the
single-cell noise that coarsening leaves behind and is the main reason the
earlier frames looked pixelated. The display grid is also matched to the
rendered map width so that no upsampling is needed at draw time.

Input annual files:
    /path/to/scratch/paper_2/no_of_months/
        wetGDE_months_{year}.nc

DEM:
    /projects/prjs1222/globgm_input/_data/globgm_input/
        topography_30sec_03sec/
        dem_average_topography_parameters_30sec_february_2021_
        global_covered_with_zero.nc

DEM variable:
    dem_average
"""

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.cm import ScalarMappable


# =============================================================================
# CONFIGURATION
# =============================================================================

SRC_DIR = Path(
    "/path/to/scratch/paper_2/no_of_months/"
)

VAR = "wetGDE_months"

DEM_FILE = Path(
    "/projects/prjs1222/globgm_input/_data/globgm_input/"
    "topography_30sec_03sec/"
    "dem_average_topography_parameters_30sec_february_2021_"
    "global_covered_with_zero.nc"
)

DEM_VAR = "dem_average"

# -------------------------------------------------------------------------
# Test/full toggle
# -------------------------------------------------------------------------

TEST_MODE = False
TEST_YEAR = 2019
TEST_FRAMES = 12

FULL_YEARS = list(range(1980, 2020))

YEARS = [TEST_YEAR] if TEST_MODE else FULL_YEARS

OUTDIR = (
    SRC_DIR / "frames_annual_test"
    if TEST_MODE
    else SRC_DIR / "frames_annual"
)

# Do not coarsen the GDW field.
COARSEN = 1

# Optional regional extent applied to the GDW input:
# (lon_min, lon_max, lat_min, lat_max)
EXTENT = None

# Map extent actually drawn. The southern limit trims the empty Antarctic band
# left by the DEM crop. Set to None to use the GDW data extent.
MAP_EXTENT = (-180.0, 180.0, -58.0, 84.0)

# Full animation interpolation.
SUBSTEPS = 4
PINGPONG = False

# Particle settings.
N_PARTICLES_TEST = 180_000
N_PARTICLES_FULL = 400_000

N_PARTICLES = (
    N_PARTICLES_TEST
    if TEST_MODE
    else N_PARTICLES_FULL
)

RESAMPLE_FRAC = 0.03
PRESENCE_FLOOR = 0.03
JITTER = 0.10
DASH_LEN = 0.50
LINE_WIDTH = 0.50
SEED = 42

# -------------------------------------------------------------------------
# Output geometry
# -------------------------------------------------------------------------

# Exported pixel dimensions.
FIG_W = 5760
FIG_H = 3240

# Canvas width in inches. Font sizes are points on this canvas, so this
# controls text size relative to the frame. The export DPI is derived from it,
# keeping the PNG at FIG_W x FIG_H.
FIG_WIDTH_INCHES = 16.0

DPI = FIG_W / FIG_WIDTH_INCHES
FIG_HEIGHT_INCHES = FIG_WIDTH_INCHES * FIG_H / FIG_W

# Map axes rectangle: left, bottom, width, height.
MAP_AXES_RECT = [0.03, 0.13, 0.94, 0.75]

# Legend axes rectangle.
LEGEND_AXES_RECT = [0.36, 0.055, 0.30, 0.022]

# Font sizes in points on the FIG_WIDTH_INCHES canvas.
TITLE_FONTSIZE = 28
SUBTITLE_FONTSIZE = 16
YEAR_FONTSIZE = 34
CREDIT_FONTSIZE = 11
LEGEND_LABEL_FONTSIZE = 13
LEGEND_TICK_FONTSIZE = 11

# -------------------------------------------------------------------------
# Hillshade
# -------------------------------------------------------------------------

# Display grid for the hillshade. This does not coarsen the GDW input. The
# width is set close to the rendered map width in pixels, so the raster is
# drawn near 1:1 and does not need upsampling.
HILLSHADE_MAX_WIDTH = 5600
HILLSHADE_MAX_HEIGHT = 2800

HILLSHADE_AZIMUTH = 315.0
HILLSHADE_ALTITUDE = 45.0

# Relief multiplier on top of the automatic cell-size scaling below.
HILLSHADE_VERTICAL_EXAGGERATION = 1.0

# Cell size at which HILLSHADE_VERTICAL_EXAGGERATION is exact. At the roughly
# 7 km display grid this gives an effective exaggeration near 7. Raise it to
# flatten the shading further, lower it for more relief.
HILLSHADE_REFERENCE_SPACING_M = 1000.0

# No stretch. Set to a (low, high) percentile pair only if the raw
# illumination turns out too compressed for a particular DEM crop.
HILLSHADE_STRETCH_PERCENTILES = None

# Blend amplitudes about the land base colour, as fractions of it. The shadow
# is deeper than the highlight, and the highlight is small enough that the
# land never clips into white.
HILLSHADE_SHADOW_DEPTH = 0.16
HILLSHADE_HIGHLIGHT_LIFT = 0.06

# Illumination range, either side of the land median, mapped onto the full
# shadow and highlight amplitudes. Larger values make the shading flatter.
HILLSHADE_DEVIATION_SCALE = 0.35

# Separable binomial smoothing passes. Applied to the elevation before the
# gradient, and once to the illumination afterwards. Raising these softens the
# texture further at the cost of fine detail.
DEM_SMOOTH_PASSES = 2
HILLSHADE_SMOOTH_PASSES = 1

# Minimum cosine of latitude used when converting longitude spacing to metres,
# to keep the polar rows finite.
MIN_COS_LATITUDE = 0.05

# -------------------------------------------------------------------------
# Colours and labels
# -------------------------------------------------------------------------

OCEAN_COLOR = "#d8e8ea"
LAND_BASE_RGB = np.array([232, 227, 213], dtype=np.float32) / 255.0
COASTLINE_COLOR = "#5e7377"

TEXT_COLOR = "#222222"
SUBTEXT_COLOR = "#5f5f5f"

VMIN = 1.0
VMAX = 12.0

TITLE = "Groundwater-dependent wetlands"
SUBTITLE = "Number of months with groundwater dependency, 1980-2019"

CREDIT = (
    "N. G. Otoo, Utrecht University"
)

CMAP = LinearSegmentedColormap.from_list(
    "gdw_google_earth",
    [
        "#8fae2a",
        "#62b33f",
        "#36bd72",
        "#24b7a6",
        "#1fa4c9",
        "#1976d2",
        "#0d47a1",
    ],
)


# =============================================================================
# SMOOTHING
# =============================================================================

def binomial_smooth(
    array: np.ndarray,
    passes: int,
) -> np.ndarray:
    """
    Apply a separable [1, 2, 1] / 4 kernel the requested number of times.

    Edges are handled by replication, so coastlines and the array border do
    not pull values toward zero.
    """

    if passes <= 0:
        return array

    result = array.astype(np.float32, copy=True)

    for _ in range(passes):

        for axis in (0, 1):

            padded = np.pad(
                result,
                pad_width=[
                    (1, 1) if a == axis else (0, 0)
                    for a in (0, 1)
                ],
                mode="edge",
            )

            if axis == 0:
                result = (
                    padded[:-2, :]
                    + 2.0 * padded[1:-1, :]
                    + padded[2:, :]
                ) * 0.25
            else:
                result = (
                    padded[:, :-2]
                    + 2.0 * padded[:, 1:-1]
                    + padded[:, 2:]
                ) * 0.25

    return result.astype(np.float32)


# =============================================================================
# DATA HELPERS
# =============================================================================

def input_path(year: int) -> Path:
    """Return the annual GDW NetCDF path."""
    return SRC_DIR / f"wetGDE_months_{year}.nc"


def load_year(year: int) -> xr.DataArray:
    """Load one annual wet-month raster."""

    file_path = input_path(year)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {file_path}"
        )

    with xr.open_dataset(file_path) as dataset:

        if VAR not in dataset:
            raise KeyError(
                f"Variable '{VAR}' not found in {file_path}"
            )

        data = dataset[VAR]

        if "year" in data.dims:
            data = data.squeeze("year", drop=True)

        rename_map = {}

        if "latitude" in data.coords and "lat" not in data.coords:
            rename_map["latitude"] = "lat"

        if "longitude" in data.coords and "lon" not in data.coords:
            rename_map["longitude"] = "lon"

        if rename_map:
            data = data.rename(rename_map)

        if "lat" not in data.coords or "lon" not in data.coords:
            raise KeyError(
                "The GDW file must contain lat/lon or latitude/longitude "
                "coordinates."
            )

        if EXTENT is not None:
            lon_min, lon_max, lat_min, lat_max = EXTENT

            latitude_ascending = bool(
                data.lat.values[0] < data.lat.values[-1]
            )

            latitude_slice = (
                slice(lat_min, lat_max)
                if latitude_ascending
                else slice(lat_max, lat_min)
            )

            data = data.sel(
                lon=slice(lon_min, lon_max),
                lat=latitude_slice,
            )

        if COARSEN > 1:
            data = data.coarsen(
                lat=COARSEN,
                lon=COARSEN,
                boundary="trim",
            ).mean()

        return data.astype("float32").load()


def load_dem_for_display(
    target_lon: np.ndarray,
    target_lat: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Load the DEM, crop it to the map extent, and reduce it only for display.

    The land mask is built at native resolution, where ocean is exactly zero in
    this zero-filled product, then coarsened alongside the elevation. The
    resulting land fraction gives soft coastlines and keeps below sea-level
    land, which an elevation > 0 test would drop.

    Returns
    -------
    elevation, land_fraction, lat, lon
    """

    if not DEM_FILE.exists():
        raise FileNotFoundError(
            f"DEM file not found: {DEM_FILE}"
        )

    with xr.open_dataset(DEM_FILE) as dataset:

        if DEM_VAR not in dataset:
            raise KeyError(
                f"Variable '{DEM_VAR}' not found in {DEM_FILE}. "
                f"Available variables: {list(dataset.data_vars)}"
            )

        dem = dataset[DEM_VAR]

        rename_map = {}

        if "latitude" in dem.coords and "lat" not in dem.coords:
            rename_map["latitude"] = "lat"

        if "longitude" in dem.coords and "lon" not in dem.coords:
            rename_map["longitude"] = "lon"

        if rename_map:
            dem = dem.rename(rename_map)

        if "lat" not in dem.coords or "lon" not in dem.coords:
            raise KeyError(
                "The DEM must contain lat/lon coordinates."
            )

        lon_min = float(np.nanmin(target_lon))
        lon_max = float(np.nanmax(target_lon))
        lat_min = float(np.nanmin(target_lat))
        lat_max = float(np.nanmax(target_lat))

        dem_lat_ascending = bool(
            dem.lat.values[0] < dem.lat.values[-1]
        )

        lat_slice = (
            slice(lat_min, lat_max)
            if dem_lat_ascending
            else slice(lat_max, lat_min)
        )

        dem = dem.sel(
            lon=slice(lon_min, lon_max),
            lat=lat_slice,
        )

        # Land mask at native resolution: ocean is the zero fill.
        land = xr.where(
            dem.notnull() & (dem != 0.0),
            1.0,
            0.0,
        )

        combined = xr.Dataset(
            {
                "elevation": dem.fillna(0.0).astype("float32"),
                "land": land.astype("float32"),
            }
        )

        ny_dem = int(combined.sizes["lat"])
        nx_dem = int(combined.sizes["lon"])

        coarsen_y = max(
            1,
            int(np.ceil(ny_dem / HILLSHADE_MAX_HEIGHT)),
        )

        coarsen_x = max(
            1,
            int(np.ceil(nx_dem / HILLSHADE_MAX_WIDTH)),
        )

        if coarsen_y > 1 or coarsen_x > 1:
            combined = combined.coarsen(
                lat=coarsen_y,
                lon=coarsen_x,
                boundary="trim",
            ).mean()

        elevation = combined["elevation"].values.astype(np.float32)
        land_fraction = combined["land"].values.astype(np.float32)
        dem_lat = combined.lat.values.astype(np.float64)
        dem_lon = combined.lon.values.astype(np.float64)

    elevation = np.nan_to_num(
        elevation,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    land_fraction = np.clip(
        np.nan_to_num(land_fraction, nan=0.0),
        0.0,
        1.0,
    )

    return elevation, land_fraction, dem_lat, dem_lon


# =============================================================================
# HILLSHADE
# =============================================================================

def compute_hillshade(
    elevation: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    land_fraction: np.ndarray | None = None,
) -> np.ndarray:
    """
    Calculate a 0-1 illumination from elevation.

    The vertical exaggeration is scaled to the display cell size, the
    north-south gradient sign follows the DEM row order, and the east-west cell
    width varies with latitude. The elevation is smoothed before the gradient
    and the illumination once afterwards, which is what keeps the result free
    of single-cell speckle.
    """

    elevation = elevation.astype(np.float32)

    dy_degrees = float(np.nanmedian(np.abs(np.diff(lat))))
    dx_degrees = float(np.nanmedian(np.abs(np.diff(lon))))

    dy_m = max(dy_degrees * 111_320.0, 1.0)

    cos_latitude = np.clip(
        np.cos(np.deg2rad(lat.astype(np.float64))),
        MIN_COS_LATITUDE,
        1.0,
    )

    dx_m_row = np.maximum(
        dx_degrees * 111_320.0 * cos_latitude,
        1.0,
    )

    reference_spacing = max(dy_m, float(dx_m_row.max()))

    effective_exaggeration = max(
        HILLSHADE_VERTICAL_EXAGGERATION
        * reference_spacing
        / HILLSHADE_REFERENCE_SPACING_M,
        1.0,
    )

    print(
        f"Hillshade cell size: {dx_m_row.max() / 1000.0:.2f} km east-west "
        f"(equatorial), {dy_m / 1000.0:.2f} km north-south; "
        f"effective vertical exaggeration {effective_exaggeration:.2f}",
        flush=True,
    )

    smoothed_elevation = binomial_smooth(
        elevation,
        DEM_SMOOTH_PASSES,
    )

    scaled = smoothed_elevation * np.float32(effective_exaggeration)

    # Gradients per index step, then converted to per metre.
    gradient_row, gradient_column = np.gradient(scaled)

    grad_x = gradient_column / dx_m_row[:, None].astype(np.float32)

    latitude_descending = bool(lat[0] > lat[-1])

    # Row index increases southward when latitude descends, so the
    # north-positive gradient is the negated row gradient.
    grad_y = (
        -gradient_row if latitude_descending else gradient_row
    ) / np.float32(dy_m)

    slope = np.pi / 2.0 - np.arctan(
        np.sqrt(grad_x**2 + grad_y**2)
    )

    aspect = np.arctan2(
        -grad_x,
        grad_y,
    )

    azimuth = np.deg2rad(
        360.0 - HILLSHADE_AZIMUTH + 90.0
    )

    altitude = np.deg2rad(
        HILLSHADE_ALTITUDE
    )

    shaded = (
        np.sin(altitude) * np.sin(slope)
        + np.cos(altitude)
        * np.cos(slope)
        * np.cos(azimuth - aspect)
    )

    shaded = np.clip(shaded, 0.0, 1.0).astype(np.float32)

    shaded = binomial_smooth(
        shaded,
        HILLSHADE_SMOOTH_PASSES,
    )

    if HILLSHADE_STRETCH_PERCENTILES is not None:

        if land_fraction is not None:
            sample = shaded[land_fraction > 0.5]
        else:
            sample = shaded.ravel()

        if sample.size > 0:

            low, high = np.percentile(
                sample,
                HILLSHADE_STRETCH_PERCENTILES,
            )

            if high - low > 1e-6:
                shaded = np.clip(
                    (shaded - low) / (high - low),
                    0.0,
                    1.0,
                ).astype(np.float32)

    return np.clip(shaded, 0.0, 1.0).astype(np.float32)


def colourise_land_hillshade(
    hillshade: np.ndarray,
    land_fraction: np.ndarray,
) -> np.ndarray:
    """
    Blend the land base colour with the hillshade.

    The illumination is expressed as a deviation from its median over land,
    then mapped to a multiplicative factor with a deeper shadow than highlight.
    Scaling all three channels by one factor preserves hue, so flat terrain
    keeps the base colour exactly and only relief picks up tone. The highlight
    cap keeps the land clear of white, which is what previously read as grey
    once it clipped.

    Ocean cells are transparent, leaving the axes ocean colour visible.
    """

    land_mask = land_fraction > 0.5

    reference = (
        float(np.median(hillshade[land_mask]))
        if land_mask.any()
        else float(np.median(hillshade))
    )

    deviation = np.clip(
        (hillshade - reference) / HILLSHADE_DEVIATION_SCALE,
        -1.0,
        1.0,
    )

    shade_factor = 1.0 + np.where(
        deviation < 0.0,
        deviation * HILLSHADE_SHADOW_DEPTH,
        deviation * HILLSHADE_HIGHLIGHT_LIFT,
    )

    print(
        f"Land shade factor: min={shade_factor[land_mask].min():.3f}, "
        f"median={np.median(shade_factor[land_mask]):.3f}, "
        f"max={shade_factor[land_mask].max():.3f}"
        if land_mask.any()
        else "Land shade factor: no land cells",
        flush=True,
    )

    rgb = (
        LAND_BASE_RGB[None, None, :]
        * shade_factor[..., None].astype(np.float32)
    )

    rgb = np.clip(rgb, 0.0, 1.0)

    alpha = np.clip(
        land_fraction,
        0.0,
        1.0,
    ).astype(np.float32)

    rgba = np.dstack(
        [rgb, alpha]
    )

    return rgba.astype(np.float32)


# =============================================================================
# FRAME SEQUENCE
# =============================================================================

def build_frame_order(
    number_of_years: int,
) -> list[int]:
    """Build test or full frame order."""

    if TEST_MODE:
        return list(range(TEST_FRAMES))

    number_of_forward_frames = (
        (number_of_years - 1) * SUBSTEPS + 1
    )

    forward = list(
        range(number_of_forward_frames)
    )

    if PINGPONG:
        return (
            forward
            + list(
                range(
                    number_of_forward_frames - 2,
                    0,
                    -1,
                )
            )
        )

    return forward


def frame_field(
    frame_index: int,
    annual_stack: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Return one test or interpolated full-animation field."""

    if TEST_MODE:
        return (
            annual_stack[0],
            float(TEST_YEAR),
        )

    continuous_index = frame_index / SUBSTEPS

    lower_index = min(
        int(continuous_index),
        annual_stack.shape[0] - 2,
    )

    weight = continuous_index - lower_index

    field = (
        (1.0 - weight)
        * annual_stack[lower_index]
        + weight
        * annual_stack[lower_index + 1]
    )

    decimal_year = (
        FULL_YEARS[0]
        + continuous_index
    )

    return (
        field.astype(np.float32, copy=False),
        decimal_year,
    )


# =============================================================================
# PARTICLES
# =============================================================================

rng = np.random.default_rng(SEED)


def sample_positions(
    field: np.ndarray,
    number_of_particles: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample particle locations proportional to wet-month values."""

    weights = field.ravel().astype(np.float64)
    weights[weights < PRESENCE_FLOOR] = 0.0

    total_weight = weights.sum()

    if total_weight <= 0:
        return (
            np.zeros(number_of_particles, dtype=np.float32),
            np.zeros(number_of_particles, dtype=np.float32),
        )

    indices = rng.choice(
        weights.size,
        size=number_of_particles,
        replace=True,
        p=weights / total_weight,
    )

    iy, ix = np.divmod(
        indices,
        field.shape[1],
    )

    x = (
        ix.astype(np.float32)
        + rng.random(number_of_particles).astype(np.float32)
    )

    y = (
        iy.astype(np.float32)
        + rng.random(number_of_particles).astype(np.float32)
    )

    return x, y


def values_at_positions(
    field: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
) -> np.ndarray:
    """Return raster values at particle positions."""

    ny, nx = field.shape

    ix = np.clip(
        x.astype(np.int32),
        0,
        nx - 1,
    )

    iy = np.clip(
        y.astype(np.int32),
        0,
        ny - 1,
    )

    return field[iy, ix]


def pixel_to_lonlat(
    x: np.ndarray,
    y: np.ndarray,
    lon: np.ndarray,
    lat: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert floating raster indices to map coordinates."""

    nx = len(lon)
    ny = len(lat)

    x_clipped = np.clip(
        x,
        0.0,
        nx - 1.0,
    )

    y_clipped = np.clip(
        y,
        0.0,
        ny - 1.0,
    )

    lon_positions = np.interp(
        x_clipped,
        np.arange(nx, dtype=np.float32),
        lon,
    )

    lat_positions = np.interp(
        y_clipped,
        np.arange(ny, dtype=np.float32),
        lat,
    )

    return (
        lon_positions.astype(np.float32),
        lat_positions.astype(np.float32),
    )


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:

    print(
        f"Mode: {'TEST' if TEST_MODE else 'FULL'}",
        flush=True,
    )

    print(
        f"Canvas: {FIG_WIDTH_INCHES:.1f} x {FIG_HEIGHT_INCHES:.2f} inches "
        f"at {DPI:.0f} dpi, export {FIG_W} x {FIG_H} px",
        flush=True,
    )

    print(
        "Loading year(s): "
        + ", ".join(str(year) for year in YEARS),
        flush=True,
    )

    annual_data = []

    for year in YEARS:
        annual_data.append(load_year(year))
        print(f"  loaded {year}", flush=True)

    reference = annual_data[0]

    lat = reference.lat.values.astype(np.float64)
    lon = reference.lon.values.astype(np.float64)

    annual_stack = np.stack(
        [data.values for data in annual_data],
        axis=0,
    ).astype(np.float32)

    valid = np.isfinite(annual_stack).all(axis=0)

    annual_stack = np.nan_to_num(
        annual_stack,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    annual_stack[:, ~valid] = 0.0

    print(
        f"GDW grid: {annual_stack.shape[1]} x "
        f"{annual_stack.shape[2]}",
        flush=True,
    )

    print("Loading DEM for hillshade...", flush=True)

    dem, land_fraction, dem_lat, dem_lon = load_dem_for_display(
        target_lon=lon,
        target_lat=lat,
    )

    print(
        f"DEM display grid: {dem.shape[0]} x {dem.shape[1]}, "
        f"land cells {int((land_fraction > 0.5).sum()):,}",
        flush=True,
    )

    hillshade = compute_hillshade(
        elevation=dem,
        lat=dem_lat,
        lon=dem_lon,
        land_fraction=land_fraction,
    )

    land_sample = hillshade[land_fraction > 0.5]

    if land_sample.size > 0:
        p1, p50, p99 = np.percentile(land_sample, [1, 50, 99])
        print(
            f"Hillshade over land: p1={p1:.3f}, p50={p50:.3f}, "
            f"p99={p99:.3f}, spread={p99 - p1:.3f}",
            flush=True,
        )

    land_rgba = colourise_land_hillshade(
        hillshade=hillshade,
        land_fraction=land_fraction,
    )

    frame_order = build_frame_order(
        number_of_years=annual_stack.shape[0],
    )

    print(
        f"Frames to render: {len(frame_order)}",
        flush=True,
    )

    print(
        f"Particles per frame: {N_PARTICLES:,}",
        flush=True,
    )

    initial_field, _ = frame_field(
        frame_order[0],
        annual_stack,
    )

    particle_x, particle_y = sample_positions(
        initial_field,
        N_PARTICLES,
    )

    OUTDIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Frames will be saved to: {OUTDIR}",
        flush=True,
    )

    norm = Normalize(
        vmin=VMIN,
        vmax=VMAX,
        clip=True,
    )

    lon_min = float(np.nanmin(lon))
    lon_max = float(np.nanmax(lon))
    lat_min = float(np.nanmin(lat))
    lat_max = float(np.nanmax(lat))

    map_extent = (
        list(MAP_EXTENT)
        if MAP_EXTENT is not None
        else [lon_min, lon_max, lat_min, lat_max]
    )

    dem_lon_min = float(np.nanmin(dem_lon))
    dem_lon_max = float(np.nanmax(dem_lon))
    dem_lat_min = float(np.nanmin(dem_lat))
    dem_lat_max = float(np.nanmax(dem_lat))

    dem_origin = "upper" if dem_lat[0] > dem_lat[-1] else "lower"

    ny, nx = initial_field.shape

    for output_index, temporal_index in enumerate(frame_order):

        field, decimal_year = frame_field(
            temporal_index,
            annual_stack,
        )

        particle_x += rng.normal(
            0.0,
            JITTER,
            N_PARTICLES,
        ).astype(np.float32)

        particle_y += rng.normal(
            0.0,
            JITTER,
            N_PARTICLES,
        ).astype(np.float32)

        np.clip(
            particle_x,
            0.0,
            nx - 1.001,
            out=particle_x,
        )

        np.clip(
            particle_y,
            0.0,
            ny - 1.001,
            out=particle_y,
        )

        values = values_at_positions(
            field,
            particle_x,
            particle_y,
        )

        dead = (
            (values < PRESENCE_FLOOR)
            | (
                rng.random(N_PARTICLES)
                < RESAMPLE_FRAC
            )
        )

        number_dead = int(
            np.count_nonzero(dead)
        )

        if number_dead > 0:

            new_x, new_y = sample_positions(
                field,
                number_dead,
            )

            particle_x[dead] = new_x
            particle_y[dead] = new_y

            values[dead] = values_at_positions(
                field,
                new_x,
                new_y,
            )

        angles = (
            rng.random(N_PARTICLES).astype(np.float32)
            * np.float32(2.0 * np.pi)
        )

        dx = (
            DASH_LEN
            * np.cos(angles)
        )

        dy = (
            DASH_LEN
            * np.sin(angles)
        )

        lon0, lat0 = pixel_to_lonlat(
            particle_x,
            particle_y,
            lon,
            lat,
        )

        lon1, lat1 = pixel_to_lonlat(
            particle_x + dx,
            particle_y + dy,
            lon,
            lat,
        )

        segment_start = np.column_stack(
            [lon0, lat0]
        )

        segment_end = np.column_stack(
            [lon1, lat1]
        )

        segments = np.stack(
            [segment_start, segment_end],
            axis=1,
        )

        normalized_values = norm(values)
        colours = CMAP(normalized_values)

        colours[:, 3] = np.clip(
            normalized_values * 0.35 + 0.65,
            0.0,
            1.0,
        )

        figure = plt.figure(
            figsize=(
                FIG_WIDTH_INCHES,
                FIG_HEIGHT_INCHES,
            ),
            dpi=DPI,
            facecolor="white",
        )

        axis = figure.add_axes(
            MAP_AXES_RECT,
            projection=ccrs.Robinson(),
        )

        axis.set_facecolor(OCEAN_COLOR)

        # Set once, before drawing. set_global() must not be called later,
        # since it would discard this extent.
        axis.set_extent(
            map_extent,
            crs=ccrs.PlateCarree(),
        )

        axis.imshow(
            land_rgba,
            origin=dem_origin,
            extent=[
                dem_lon_min,
                dem_lon_max,
                dem_lat_min,
                dem_lat_max,
            ],
            transform=ccrs.PlateCarree(),
            interpolation="bilinear",
            zorder=0,
        )

        axis.add_feature(
            cfeature.COASTLINE.with_scale("110m"),
            linewidth=0.55,
            edgecolor=COASTLINE_COLOR,
            zorder=4,
        )

        collection = LineCollection(
            segments,
            colors=colours,
            linewidths=LINE_WIDTH,
            capstyle="round",
            transform=ccrs.PlateCarree(),
            rasterized=False,
            antialiased=True,
            zorder=5,
        )

        axis.add_collection(collection)

        figure.text(
            0.03,
            0.945,
            TITLE,
            color=TEXT_COLOR,
            fontsize=TITLE_FONTSIZE,
            weight="bold",
        )

        figure.text(
            0.03,
            0.905,
            SUBTITLE,
            color=SUBTEXT_COLOR,
            fontsize=SUBTITLE_FONTSIZE,
        )

        displayed_year = int(
            round(decimal_year)
        )

        figure.text(
            0.03,
            0.050,
            str(displayed_year),
            color=TEXT_COLOR,
            fontsize=YEAR_FONTSIZE,
            weight="light",
        )

        figure.text(
            0.03,
            0.020,
            CREDIT,
            color=SUBTEXT_COLOR,
            fontsize=CREDIT_FONTSIZE,
        )

        # Horizontal wet-month legend.
        colorbar_axis = figure.add_axes(
            LEGEND_AXES_RECT
        )

        scalar_mappable = ScalarMappable(
            norm=norm,
            cmap=CMAP,
        )

        scalar_mappable.set_array([])

        colorbar = figure.colorbar(
            scalar_mappable,
            cax=colorbar_axis,
            orientation="horizontal",
            ticks=[1, 3, 5, 7, 9, 12],
        )

        colorbar.set_label(
            "Number of months with groundwater dependency",
            fontsize=LEGEND_LABEL_FONTSIZE,
            color=TEXT_COLOR,
            labelpad=7,
        )

        colorbar.ax.tick_params(
            labelsize=LEGEND_TICK_FONTSIZE,
            colors=TEXT_COLOR,
            length=3,
        )

        colorbar.outline.set_linewidth(0.5)
        colorbar.outline.set_edgecolor("#777777")

        output_file = (
            OUTDIR / f"frame_{output_index:04d}.png"
        )

        figure.savefig(
            output_file,
            facecolor="white",
            dpi=DPI,
            pil_kwargs={"compress_level": 1},
        )

        plt.close(figure)

        print(
            f"Rendered frame "
            f"{output_index + 1}/{len(frame_order)} "
            f"({displayed_year})",
            flush=True,
        )

    print("Rendering complete.", flush=True)
    print(f"Frames saved in: {OUTDIR}", flush=True)

    if TEST_MODE:
        print(
            f"TEST MODE: only {TEST_YEAR} was loaded. "
            "Inspect the test frames, then set TEST_MODE = False.",
            flush=True,
        )


if __name__ == "__main__":
    main()