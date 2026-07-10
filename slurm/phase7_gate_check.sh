#!/usr/bin/env bash
#SBATCH --job-name=p7_gate_check
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=logs/p7gate-%j.out
#SBATCH --error=logs/p7gate-%j.err
#
# Phase 7 Track 1 — CPU-only sanity check that the Mode 3 `elaborate` boundary gate discriminates
# both ways (accepts a known-valid prefix, rejects a dangling one) on REAL Lean, no GPU/vLLM needed.
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="configs/proofnet_baseline.yaml"

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
ok=0; for a in 1 2 3; do activate_env && { ok=1; break; }; echo "[p7gate] activate retry $a"; sleep 5; done
[ "$ok" = 1 ] || { echo "FATAL: cannot activate $ATP_ENV"; exit 1; }
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

[ -f "$PROJ/results/_lean_env_ready.txt" ] || { echo "FATAL: Goedel-pin Lean env not built"; exit 1; }

GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[p7gate] Lean env already staged ($N_LOCAL oleans) — reusing."
else
    echo "[p7gate] staging Lean env -> $LOCAL_ENV ..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy failed"; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[p7gate] staged in $((SECONDS-t0))s."
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

echo "[p7gate] running elaborate-gate sanity check..."
python scripts/phase7_elaborate_gate_check.py "$CONFIG"
rc=$?
[ "$rc" -ne 0 ] && { echo "FATAL: gate check exited $rc"; exit "$rc"; }
echo "[p7gate] GATE CHECK PASSED"
