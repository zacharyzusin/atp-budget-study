#!/usr/bin/env bash
#SBATCH --job-name=atp_diag
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=00:40:00
#SBATCH --requeue
#SBATCH --output=logs/diag-%j.out
#SBATCH --error=logs/diag-%j.err
#
# CPU-only Lean-REPL diagnostic: stage the env to node-local SSD, then dump the RAW repl response for
# the real proofs the smoke wrongly rejected (scripts/diag_repl.py). No GPU (Lean is CPU-bound).
set -uo pipefail
PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
module load anaconda/2023.09
ATP_ENV="$PROJ/scratch/conda-envs/atp"
activate_env() {
    local base; base="$(conda info --base 2>/dev/null)"
    [ -n "$base" ] && [ -f "$base/etc/profile.d/conda.sh" ] || { echo "[diag] no base/conda.sh"; return 1; }
    set +u  # conda activate scripts reference unset vars; nounset trips them on some nodes
    source "$base/etc/profile.d/conda.sh"
    conda activate "$ATP_ENV" 2>/dev/null
    set -u
    # On some nodes `conda activate` returns 0 WITHOUT switching python (observed ins095/10260159).
    # Force the env bin onto PATH so python + console scripts resolve to the env unconditionally.
    export PATH="$ATP_ENV/bin:$PATH"; export CONDA_PREFIX="$ATP_ENV"
    hash -r 2>/dev/null || true
    [ "$(command -v python)" = "$ATP_ENV/bin/python" ] || { echo "[diag] python=$(command -v python)"; return 1; }
    python -c "import atp" 2>/dev/null || { echo "[diag] import atp failed"; return 1; }
}
ok=0; for a in 1 2 3; do activate_env && { ok=1; break; }; echo "[diag] activate retry $a"; sleep 5; done
[ "$ok" = 1 ] || { echo "FATAL: activate failed (python=$(command -v python))"; exit 1; }
echo "[diag] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"; export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[diag] env already staged on $(hostname) ($N_LOCAL oleans)."
else
    echo "[diag] staging Lean env -> $LOCAL_ENV ($N_GPFS oleans)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy failed"; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[diag] staged in $((SECONDS-t0))s."
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

python scripts/diag_repl.py configs/smoke.yaml
echo "[diag] done."
