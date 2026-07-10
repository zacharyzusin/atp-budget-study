#!/usr/bin/env bash
#SBATCH --job-name=atp_audit_trapped
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=11:00:00
#SBATCH --requeue
#SBATCH --output=logs/audit-trapped-%j.out
#SBATCH --error=logs/audit-trapped-%j.err
#
# AUDIT_PLAN.md Task B: does `set_option maxHeartbeats 0` (added 2026-07-06, absent for every
# Phase 0-7 sweep) retroactively change any Phase 0-7 HEADLINE (whole_proof, Goedel-V2/DeepSeek-V2)
# result? Offline CPU re-verify of trapped-core recorded failures against the current, fully-patched
# ReplBackend -- NO GPU, NO new generation. Found live 2026-07-10 (interactive attempt, killed after
# 1h+ with zero completed cells): `maxHeartbeats 0` disables Lean's OWN internal heartbeat timeout,
# so a genuinely-wrong trapped-cell attempt that would previously fail FAST on Lean's internal limit
# now runs to the much slower external `verify_timeout_s=120` wall-clock timeout instead -- this job
# needs real wall-clock time (hence the 11h cap, near partition max), not a quick interactive check.
#
# Usage: sbatch slurm/audit_trapped_reverify.sh <config> <run-dir> <trapped-file> [limit-problems]
#   sbatch slurm/audit_trapped_reverify.sh configs/proofnet_baseline.yaml results/proofnet_baseline \
#       scratch/phase2/trapped_proofnet.txt 150
#   sbatch slurm/audit_trapped_reverify.sh configs/baseline.yaml results/baseline \
#       scratch/phase2/trapped_minif2f.txt 55
#   sbatch slurm/audit_trapped_reverify.sh configs/deepseek_proofnet_baseline.yaml \
#       results/deepseek_proofnet_baseline scratch/phase2/trapped_proofnet_deepseek.txt 140
#   sbatch slurm/audit_trapped_reverify.sh configs/deepseek_minif2f_baseline.yaml \
#       results/deepseek_minif2f_baseline scratch/phase2/trapped_minif2f_deepseek.txt 61
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${1:?usage: sbatch slurm/audit_trapped_reverify.sh <config> <run-dir> <trapped-file> [limit]}"
RUN_DIR="${2:?run-dir required}"
TRAPPED_FILE="${3:?trapped-file required}"
LIMIT="${4:-}"

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
    echo "[audit-trapped] conda activate failed (attempt $attempt) — retrying in 5s..."; sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV with importable atp."; exit 1; }
echo "[audit-trapped] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

# --- Stage the Lean env to node-local SSD, flock-guarded (same pattern as validate_statements.sh) --
GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
mkdir -p "$LOCAL_BASE"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
exec 9>"$LOCAL_BASE/.atp_stage.lock"
flock 9
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[audit-trapped] Lean env already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    echo "[audit-trapped] staging Lean env -> $LOCAL_ENV (cp $N_GPFS oleans)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy to $LOCAL_ENV failed"; flock -u 9; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[audit-trapped] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
fi
flock -u 9; exec 9>&-
export ATP_LEAN_PROJECT="$LOCAL_ENV"

LIMIT_ARGS=()
[ -n "$LIMIT" ] && LIMIT_ARGS=(--limit-problems "$LIMIT")

echo "[audit-trapped] re-verifying trapped core: config=$CONFIG run-dir=$RUN_DIR trapped=$TRAPPED_FILE limit=${LIMIT:-all}"
python scripts/audit_trapped_heartbeat_reverify.py \
    --config "$CONFIG" --run-dir "$RUN_DIR" --trapped-file "$TRAPPED_FILE" "${LIMIT_ARGS[@]}"
rc=$?
echo "[audit-trapped] done (rc=$rc)"
exit $rc
