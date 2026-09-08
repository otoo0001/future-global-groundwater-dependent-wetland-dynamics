#!/bin/bash
#SBATCH --job-name=wtd_sensi
#SBATCH --partition=genoa
#SBATCH --time=06:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=120G
#SBATCH --array=0-3
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=REMOVED
#SBATCH --output=/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/plots/figures_v2806/slurm/wtd_sensi_%A_%a.out
#SBATCH --error=/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/plots/figures_v2806/slurm/wtd_sensi_%A_%a.err
#SBATCH --export=ALL

set -euo pipefail

set +u
. "/path/to/user/load_all_default.sh"
set -u

export PYTHONNOUSERSITE=1
export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK}
export MKL_NUM_THREADS=${SLURM_CPUS_PER_TASK}
export OPENBLAS_NUM_THREADS=${SLURM_CPUS_PER_TASK}

PYBIN="/path/to/user/.conda/envs/gdes_area/bin/python"
SCRIPT="/path/to/user/github/paper_3/future_gdes_new_v2026/wtd_sensitivity.py"

if [ ! -x "${PYBIN}" ]; then echo "[error] python not found: ${PYBIN}"; exit 2; fi
if [ ! -f "${SCRIPT}" ]; then echo "[error] script not found: ${SCRIPT}"; exit 2; fi

"${PYBIN}" -V
"${PYBIN}" -c "import xarray, zarr, numba; print('xarray:', xarray.__version__); print('zarr:', zarr.__version__); print('numba:', numba.__version__)"

SCENARIOS=(historical ssp126 ssp370 ssp585)
export SCENARIO=${SCENARIOS[$SLURM_ARRAY_TASK_ID]}

LOGDIR="/path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_v3/plots/figures_v2806/slurm"
mkdir -p "${LOGDIR}"

echo "Job: wtd_sensi | Scenario: ${SCENARIO} | Task: ${SLURM_ARRAY_TASK_ID} | Start: $(date)"

"${PYBIN}" "${SCRIPT}"

echo "End: $(date)"