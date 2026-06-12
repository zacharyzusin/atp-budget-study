#!/usr/bin/env bash
#SBATCH --job-name=atp_validate
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=00:40:00
#SBATCH --requeue
#SBATCH --output=logs/validate-%j.out
#SBATCH --error=logs/validate-%j.err
#
# Compile-gate a benchmark's statement HEADS against the pinned mathlib — NO GPU, NO model. Stages
# the Lean env to node-local SSD (same hardening as ablation.sh: import Mathlib off GPFS times out)
# and runs scripts/validate_statements.py. Use BEFORE the first baseline GPU run on a new benchmark
# (e.g. ProofNet#): a bench whose heads don't elaborate is silently all-zeros.
#
# Usage:  sbatch slurm/validate_statements.sh configs/proofnet_baseline.yaml [--limit N]
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${1:-configs/proofnet_baseline.yaml}"
shift || true
EXTRA_ARGS="$*"   # e.g. "--limit 20" for a smoke

# Insomnia proxy trap: Slurm jobs inherit a per-session SSH proxy that breaks downloads/HF.
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
    echo "[validate] conda activate failed (attempt $attempt) — retrying in 5s..."; sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV with importable atp."; exit 1; }
echo "[validate] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

if [ ! -f "$PROJ/results/_lean_env_ready.txt" ]; then
    echo "FATAL: Goedel-pin Lean env not built (no results/_lean_env_ready.txt). Run slurm/build_lean.sh."
    exit 1
fi

# --- Stage the Lean env to node-local SSD, flock-guarded (kept in sync with ablation.sh) ----------
GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
mkdir -p "$LOCAL_BASE"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
exec 9>"$LOCAL_BASE/.atp_stage.lock"
flock 9
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[validate] Lean env already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    echo "[validate] staging Lean env -> $LOCAL_ENV (cp $N_GPFS oleans, ~10-20min off GPFS)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy to $LOCAL_ENV failed"; flock -u 9; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[validate] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
fi
flock -u 9; exec 9>&-
export ATP_LEAN_PROJECT="$LOCAL_ENV"

echo "[validate] running compile-gate on $CONFIG $EXTRA_ARGS"
# shellcheck disable=SC2086
python scripts/validate_statements.py --config "$CONFIG" $EXTRA_ARGS
rc=$?
echo "[validate] done (rc=$rc)"
exit $rc
