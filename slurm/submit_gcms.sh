#!/bin/bash
#SBATCH --job-name=wetgde_gcm_v3
#SBATCH --partition=genoa
#SBATCH --time=10:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=300G
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=REMOVED
#SBATCH --output=/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/logs/slurm_%x_%j.out
#SBATCH --open-mode=truncate
#SBATCH --error=/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/logs/slurm_%x_%j.err
#SBATCH --export=ALL

set -euo pipefail
set +u; . "/path/to/user/load_all_default.sh"; set -u

PYBIN="/path/to/user/.conda/envs/gdes_area/bin/python"
if [ ! -x "${PYBIN}" ]; then echo "[error] python not found: ${PYBIN}"; exit 2; fi
echo "[env] python=${PYBIN}"; "${PYBIN}" -V

mkdir -p /path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/logs

# ── output paths (v3) ─────────────────────────────────────────────────────────
export OUT_NC_DIR="/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3"
export OUT_PARQUET_DIR="/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3"
export LOG_DIR="/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/logs"

# ── run flags ─────────────────────────────────────────────────────────────────
export RUN_GCMS=1
export RUN_ENSEMBLE=0
export RUN_SENSITIVITY=0

# ── per-job filters (set by submission loop) ──────────────────────────────────
export GCM="${GCM:-}"
export SCENARIO="${SCENARIO:-}"

# ── LU ────────────────────────────────────────────────────────────────────────
export APPLY_LU_MASK=1
export LU_FREEZE_MODE=period
export LU_FREEZE_START=1995
export LU_FREEZE_END=2014

# ── WTD climatology ───────────────────────────────────────────────────────────
export WTD_CLIM_WINDOW="1995-01-01,2014-12-31"
export WTD_CLIM_CACHE_DIR="/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/wtd_clim_cache"

# ── time ──────────────────────────────────────────────────────────────────────
export START_YEAR="${START_YEAR:-1979}"
export END_YEAR=2050

# ── misc ──────────────────────────────────────────────────────────────────────
export SMALL_TEST=0
export WRITE_NC=1
export SKIP_EXISTING=1
export TILE_Y=360
export TILE_X=720
export SPATIAL_CHUNK=512
export TIME_BATCH=12

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export HDF5_USE_FILE_LOCKING=FALSE
export PYTHONUNBUFFERED=1
export TMPDIR="${SLURM_TMPDIR:-/tmp}"

echo "========== $(date) JOB=$SLURM_JOB_ID GCM=${GCM:-ALL} SCENARIO=${SCENARIO:-ALL} ==========" \
  >> /path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/logs/all_errors.log

echo "=== wetGDE v3 GCM run ==="
echo "GCM: ${GCM}  SCENARIO: ${SCENARIO}  START_YEAR: ${START_YEAR}  END_YEAR: ${END_YEAR}"
echo "OUT_NC_DIR: ${OUT_NC_DIR}"

cd ~/github/paper_3/future_gdes_new_v2026
/usr/bin/time -v "${PYBIN}" -u -X faulthandler wetgde_model/run.py 2>&1 \
  | tee -a /path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/logs/all_errors.log