#!/usr/bin/env bash
#SBATCH --job-name=atp_header_confound
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=4
#SBATCH --mem-per-cpu=6000M
#SBATCH --time=1:00:00
#SBATCH --output=logs/header-confound-%j.out
#SBATCH --error=logs/header-confound-%j.err
#
# DECISIONS.md 2026-07-25h -- header-confound check. Re-verifies the 6 calibration-cell recoveries
# under a simulated OLD (pre-2026-07-06) verifier that omits `set_option maxHeartbeats 0`, to
# separate genuine sampling recoveries from header/verifier-fix recoveries. 6 proofs only -- one
# cold `import Mathlib` (~2-5min) plus 12 quick verifies, well inside the 1h cap. Staging pattern
# copied from slurm/audit_trapped_reverify.sh (per-job-ID local dir, no shared-path races).
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"

unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

module load anaconda/2023.09
ATP_ENV="$PROJ/scratch/conda-envs/atp"
activate_env() {
    local base; base="$(conda info --base 2>/dev/null)"
    [ -n "$base" ] && [ -f "$base/etc/profile.d/conda.sh" ] || return 1
    set +u; source "$base/etc/profile.d/conda.sh"; conda activate "$ATP_ENV" 2>/dev/null; set -u
    export PATH="$ATP_ENV/bin:$PATH"; export CONDA_PREFIX="$ATP_ENV"
    hash -r 2>/dev/null || true
    [ "$(command -v python)" = "$ATP_ENV/bin/python" ] || return 1
    python -c "import atp" 2>/dev/null || return 1
}
ok=0
for attempt in 1 2 3; do
    if activate_env; then ok=1; break; fi
    echo "[header-confound] conda activate failed (attempt $attempt) — retrying in 5s..."; sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV with importable atp."; exit 1; }
echo "[header-confound] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

LEAN_ENV_NAME="atp-lean-env"
GPFS_ENV="$PROJ/scratch/lean-cache/$LEAN_ENV_NAME"
LOCAL_BASE="/local/$USER"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/${LEAN_ENV_NAME}-j${SLURM_JOB_ID:-$$}"
mkdir -p "$LOCAL_BASE"
rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
echo "[header-confound] staging Lean env -> $LOCAL_ENV ..."
cp -a "$GPFS_ENV/." "$LOCAL_ENV/" \
    || { echo "FATAL: staging copy to $LOCAL_ENV failed"; exit 1; }
echo "[header-confound] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
export ATP_LEAN_PROJECT="$LOCAL_ENV"

python scripts/header_confound_reverify.py \
    --config configs/calibration_trapped32_goedel_minif2f.yaml \
    --run-dir results/calibration_trapped32_goedel_minif2f
rc=$?
echo "[header-confound] done (rc=$rc)"
exit $rc
