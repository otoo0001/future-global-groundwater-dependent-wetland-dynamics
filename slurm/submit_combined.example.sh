#!/bin/bash
# submit_combined.sh  --  submit all 20 GCM x scenario jobs for v3
# Usage: bash submit_combined.sh

GCMS=(
    "gfdl-esm4"
    "ipsl-cm6a-lr"
    "mpi-esm1-2-hr"
    "mri-esm2-0"
    "ukesm1-0-ll"
)
SCENARIOS=("historical" "ssp126" "ssp370" "ssp585")

SCRIPT="/path/to/future_gdes_new_v2026/slurm/submit_gcms.sh"
LOG_DIR="/path/to/WetGDEs_fgdw_v3/logs"
mkdir -p "${LOG_DIR}"

echo "Submitting v3 GCM jobs: ${#GCMS[@]} GCMs x ${#SCENARIOS[@]} scenarios = $((${#GCMS[@]} * ${#SCENARIOS[@]})) jobs"

for gcm in "${GCMS[@]}"; do
    for sc in "${SCENARIOS[@]}"; do
        if [ "${sc}" = "historical" ]; then
            START=1979
        else
            START=2015
        fi
        JOB_NAME="v3_${gcm:0:4}_${sc}"
        JID=$(sbatch \
            --job-name="${JOB_NAME}" \
            --export=ALL,GCM="${gcm}",SCENARIO="${sc}",START_YEAR="${START}" \
            "${SCRIPT}" | awk '{print $NF}')
        echo "  submitted ${gcm} ${sc} -> job ${JID}"
    done
done

echo "All jobs submitted. Monitor with: squeue -u ${USER}"
