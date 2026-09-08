#!/bin/bash
#SBATCH --job-name=wetgde_mask
#SBATCH --partition=fat_genoa
#SBATCH --time=10:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=400G
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=REMOVED
#SBATCH --output=/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw/logs/slurm_%j_%x.out
#SBATCH --error=/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw/logs/slurm_%j_%x.err
#SBATCH --export=NONE

set -euo pipefail
set +u; . "/path/to/user/load_all_default.sh"; set -u

PYBIN="/path/to/user/.conda/envs/gdes_area/bin/python"
if [ ! -x "${PYBIN}" ]; then echo "[error] python not found: ${PYBIN}"; exit 2; fi
echo "[env] python=${PYBIN}"; "${PYBIN}" -V

mkdir -p /path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw/logs

export SCENARIO="${SCENARIO:-}"
export SMALL_TEST=0
export SPATIAL_CHUNK=512
export START_YEAR="${START_YEAR:-1979}"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export HDF5_USE_FILE_LOCKING=FALSE
export PYTHONUNBUFFERED=1
export TMPDIR="${SLURM_TMPDIR:-/tmp}"

echo "=== MASK ONLY ==="
echo "SCENARIO: ${SCENARIO:-all}  START_YEAR: ${START_YEAR}"

cd ~/github/paper_3/future_gdes_new_v2026
/usr/bin/time -v "${PYBIN}" -u -X faulthandler run_wetgde_paper3.py
