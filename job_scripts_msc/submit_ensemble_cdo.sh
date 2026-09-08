#!/bin/bash
#SBATCH --job-name=wetgde_ens
#SBATCH --partition=genoa
#SBATCH --time=12:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=60G
#SBATCH --array=0-3
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=REMOVED
#SBATCH --output=/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/ensemble/slurm/slurm_ens_%A_%a.out
#SBATCH --error=/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/ensemble/slurm/slurm_ens_%A_%a.err
#SBATCH --export=ALL

set -euo pipefail

# ------------------------------------------------------------------ #
# Environment                                                         #
# ------------------------------------------------------------------ #
set +u
. "/path/to/user/load_all_default.sh"
set -u

export PYTHONNOUSERSITE=1          # ignore ~/.local packages — avoids xarray/zarr mismatch
export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK}
export MKL_NUM_THREADS=${SLURM_CPUS_PER_TASK}
export OPENBLAS_NUM_THREADS=${SLURM_CPUS_PER_TASK}

PYBIN="/path/to/user/.conda/envs/gdes_area/bin/python"
SCRIPT="/path/to/user/github/paper_3/future_gdes_new_v2026/run_ensemble_means_fromgcm.py"

# ------------------------------------------------------------------ #
# Sanity checks                                                       #
# ------------------------------------------------------------------ #
if [ ! -x "${PYBIN}" ]; then
    echo "[error] python not found: ${PYBIN}"
    exit 2
fi

if [ ! -f "${SCRIPT}" ]; then
    echo "[error] script not found: ${SCRIPT}"
    exit 2
fi

"${PYBIN}" -V
"${PYBIN}" -c "import xarray, netCDF4; print('xarray:', xarray.__version__); print('netCDF4 ok')"

# ------------------------------------------------------------------ #
# Scenario selection                                                  #
# ------------------------------------------------------------------ #
SCENARIOS=(historical ssp126 ssp370 ssp585)
export SCENARIO=${SCENARIOS[$SLURM_ARRAY_TASK_ID]}

# ------------------------------------------------------------------ #
# Output dirs                                                         #
# ------------------------------------------------------------------ #
LOGDIR="/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/ensemble/slurm"
OUTDIR="/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/ensemble/${SCENARIO}/nc"
mkdir -p "${LOGDIR}" "${OUTDIR}"

# ------------------------------------------------------------------ #
# Run                                                                 #
# ------------------------------------------------------------------ #
echo "====================================="
echo "Scenario : ${SCENARIO}"
echo "Task ID  : ${SLURM_ARRAY_TASK_ID}"
echo "Host     : $(hostname)"
echo "Start    : $(date)"
echo "Python   : ${PYBIN}"
echo "====================================="

"${PYBIN}" "${SCRIPT}"

echo "====================================="
echo "End: $(date)"
echo "====================================="