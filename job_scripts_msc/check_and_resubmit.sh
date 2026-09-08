#!/bin/bash
# check_and_resubmit.sh
# Checks NC completeness, lists failures, resubmits missing/incomplete jobs.
#
# Usage:
#   bash check_and_resubmit.sh          # dry run - just list status
#   bash check_and_resubmit.sh submit   # submit failed jobs

BASE=/path/to/scratch/paper_3/new_outputs/WetGDEs
SUBMIT=${1:-dryrun}
PYBIN="/path/to/user/.conda/envs/gdes_area/bin/python"

GCMS="gfdl-esm4 ipsl-cm6a-lr mpi-esm1-2-hr mri-esm2-0 ukesm1-0-ll"
SCENS="historical ssp126 ssp370 ssp585"

# expected time steps per scenario (1979-2014 hist=432, 2015-2050 ssp=432)
HIST_STEPS=432
SSP_STEPS=432

check_nc() {
    local f=$1
    local expected=$2
    if [ ! -f "$f" ]; then
        echo "MISSING_NC"
        return
    fi
    local n=$("$PYBIN" -c "
import xarray as xr, sys
try:
    ds = xr.open_dataset('$f', decode_times=False)
    print(ds.sizes.get('time', 0))
    ds.close()
except Exception as e:
    print(0)
" 2>/dev/null)
    if [ "$n" -ge "$expected" ] 2>/dev/null; then
        echo "NC_OK($n)"
    else
        echo "NC_SHORT($n/$expected)"
    fi
}

check_pq() {
    local f=$1
    [ -f "$f" ] && echo "PQ_OK" || echo "MISSING_PQ"
}

echo "============================================================"
echo "STATUS CHECK  $(date)"
echo "============================================================"

FAILED_ENSEMBLE=()
FAILED_GCMS=()

echo ""
echo "--- ENSEMBLE ---"
for scen in $SCENS; do
    [ "$scen" = "historical" ] && exp=$HIST_STEPS || exp=$SSP_STEPS
    nc="$BASE/ensemble/${scen}/nc/wetGDE_paper3_${scen}_5arcmin.nc"
    pq="$BASE/ensemble/${scen}/parquet/wetGDE_area_ensemble_${scen}.parquet"
    nc_status=$(check_nc "$nc" "$exp")
    pq_status=$(check_pq "$pq")
    if [ "$pq_status" = "PQ_OK" ]; then
        status="COMPLETE"
    elif [[ "$nc_status" == NC_OK* ]]; then
        status="NC_DONE_PQ_MISSING"
        FAILED_ENSEMBLE+=("$scen")
    else
        status="FAILED($nc_status)"
        FAILED_ENSEMBLE+=("$scen")
    fi
    printf "  %-12s  NC:%-20s  PQ:%-12s  => %s\n" "$scen" "$nc_status" "$pq_status" "$status"
done

echo ""
echo "--- GCMs ---"
for gcm in $GCMS; do
    for scen in $SCENS; do
        [ "$scen" = "historical" ] && exp=$HIST_STEPS || exp=$SSP_STEPS
        nc="$BASE/gcms/${gcm}/${scen}/nc/wetGDE_${gcm}_${scen}.nc"
        pq="$BASE/gcms/${gcm}/${scen}/parquet/wetGDE_area_${gcm}_${scen}.parquet"
        nc_status=$(check_nc "$nc" "$exp")
        pq_status=$(check_pq "$pq")
        if [ "$pq_status" = "PQ_OK" ]; then
            status="COMPLETE"
        elif [[ "$nc_status" == NC_OK* ]]; then
            status="NC_DONE_PQ_MISSING"
            FAILED_GCMS+=("${gcm}|${scen}")
        else
            status="FAILED($nc_status)"
            FAILED_GCMS+=("${gcm}|${scen}")
        fi
        printf "  %-22s  %-12s  NC:%-20s  PQ:%-12s  => %s\n" "$gcm" "$scen" "$nc_status" "$pq_status" "$status"
    done
done

echo ""
echo "============================================================"
echo "SUMMARY"
echo "  Ensemble failed: ${#FAILED_ENSEMBLE[@]}"
echo "  GCM failed:      ${#FAILED_GCMS[@]}"
echo "============================================================"

if [ "$SUBMIT" = "submit" ]; then
    echo ""
    echo "--- RESUBMITTING FAILED JOBS ---"
    cd ~/github/paper_3/future_gdes_new_v2026

    for scen in "${FAILED_ENSEMBLE[@]}"; do
        jobid=$(sbatch --export=ALL,SCENARIO=$scen \
                       --job-name=ensemble_${scen} \
                       submit_combined.sh | awk '{print $4}')
        echo "  submitted ensemble $scen -> $jobid"
    done

    for entry in "${FAILED_GCMS[@]}"; do
        gcm="${entry%%|*}"
        scen="${entry##*|}"
        # delete truncated NC if present
        nc="$BASE/gcms/${gcm}/${scen}/nc/wetGDE_${gcm}_${scen}.nc"
        if [ -f "$nc" ]; then
            n=$("$PYBIN" -c "
import xarray as xr
ds = xr.open_dataset('$nc', decode_times=False)
print(ds.sizes.get('time', 0))
ds.close()
" 2>/dev/null)
            exp=$SSP_STEPS
            [ "$scen" = "historical" ] && exp=$HIST_STEPS
            if [ "$n" -lt "$exp" ] 2>/dev/null; then
                rm -f "$nc"
                echo "  deleted truncated NC: $nc ($n steps)"
            fi
        fi
        jobid=$(sbatch --export=ALL,GCM=$gcm,SCENARIO=$scen \
                       --job-name=gcm_${gcm}_${scen} \
                       submit_gcms.sh | awk '{print $4}')
        echo "  submitted gcm $gcm $scen -> $jobid"
    done
else
    echo ""
    echo "  Run with 'submit' to resubmit failed jobs:"
    echo "  bash check_and_resubmit.sh submit"
fi
