#!/bin/bash
#SBATCH --job-name=wetgde_process_model
#SBATCH --partition=fat_genoa
#SBATCH --time=10:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=600G
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=your.email@example.com
#SBATCH --output=/path/to/WetGDEs_fgdw_gdi/logs/slurm_%x_%j.out
#SBATCH --open-mode=truncate
#SBATCH --error=/path/to/WetGDEs_fgdw_gdi/logs/slurm_%x_%j.err
#SBATCH --export=ALL

set -euo pipefail
# Load site-specific environment/modules here if required.

PYBIN="${PYBIN:-python}"
if [ ! -x "${PYBIN}" ]; then echo "[error] python not found: ${PYBIN}"; exit 2; fi
echo "[env] python=${PYBIN}"; "${PYBIN}" -V

mkdir -p /path/to/WetGDEs_fgdw_gdi/logs

# ── output paths ──────────────────────────────────────────────────────────────
export OUT_NC_DIR="/path/to/WetGDEs_fgdw_gdi"
export OUT_PARQUET_DIR="/path/to/WetGDEs_fgdw_gdi"
export LOG_DIR="/path/to/WetGDEs_fgdw_gdi/logs"

# ── run flags ─────────────────────────────────────────────────────────────────
export RUN_PROCESS_MODEL=1
export RUN_ENSEMBLE=0
export RUN_GCMS=0
export RUN_SENSITIVITY=0
export RUN_GDI_ONLY="${RUN_GDI_ONLY:-0}"

# ── per-job filters (set by submission loop) ──────────────────────────────────
export GCM="${GCM:-}"
export SCENARIO="${SCENARIO:-}"

# ── PCR ISIMIP3 diagnostics root ──────────────────────────────────────────────
export PCR_ISIMIP_ROOT="/projects/2/managed_datasets/hypflowsci6_v1.0/output"

# ── baseline and thresholds ───────────────────────────────────────────────────
export BASELINE_START=1995
export BASELINE_END=2014
export SAT_THRESHOLD=0.5
export WTD_THRESHOLD=5.0
export SAT_THRESHOLDS="0.3,0.4,0.5,0.6,0.7"
export WTD_THRESHOLDS="3.0,4.0,5.0,6.0,7.0"

# ── time ──────────────────────────────────────────────────────────────────────
export START_YEAR="${START_YEAR:-1979}"
export END_YEAR=2050

# ── misc ──────────────────────────────────────────────────────────────────────
export SKIP_EXISTING=1
export SMALL_TEST=0
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
  >> "${LOG_DIR}/all_errors.log"

echo "=== wetGDE process model ==="
echo "GCM: ${GCM:-ALL}  SCENARIO: ${SCENARIO:-ALL}  RUN_GDI_ONLY: ${RUN_GDI_ONLY}"
echo "PCR_ISIMIP_ROOT: ${PCR_ISIMIP_ROOT}"
echo "OUT_NC_DIR: ${OUT_NC_DIR}"

cd ~/github/paper_3/future_gdes_new_v2026
/usr/bin/time -v "${PYBIN}" -u -X faulthandler scripts/run_process_model.py 2>&1 \
  | tee -a "${LOG_DIR}/all_errors.log"