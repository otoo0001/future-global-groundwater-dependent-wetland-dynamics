#!/bin/bash
GCMS=("gfdl-esm4" "ipsl-cm6a-lr" "mpi-esm1-2-hr" "mri-esm2-0" "ukesm1-0-ll")
SCENARIOS=("historical" "ssp126" "ssp370" "ssp585")
SCRIPT="/path/to/user/github/paper_3/future_gdes_new_v2026/submit_process_model.sh"

mkdir -p /path/to/scratch/paper_3/new_outputs/WetGDEs_fgdw_gdi/logs

echo "Submitting GDI-only jobs: ${#GCMS[@]} x ${#SCENARIOS[@]} = $((${#GCMS[@]} * ${#SCENARIOS[@]})) jobs"

for gcm in "${GCMS[@]}"; do
    for sc in "${SCENARIOS[@]}"; do
        JID=$(sbatch \
            --job-name="gdi_${gcm:0:4}_${sc}" \
            --export=ALL,GCM="${gcm}",SCENARIO="${sc}",RUN_GDI_ONLY=1 \
            "${SCRIPT}" | awk '{print $NF}')
        echo "  submitted ${gcm} ${sc} -> job ${JID}"
    done
done
echo "Monitor: squeue -u otoo0001"
