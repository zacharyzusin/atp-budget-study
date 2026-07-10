#!/usr/bin/env bash
#SBATCH --job-name=atp_reverify
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=03:00:00
#SBATCH --requeue
#SBATCH --output=logs/reverify-%j.out
#SBATCH --error=logs/reverify-%j.err
#
# Re-verify already-collected p8battery2_* completions against the FIXED backend (missing-theorem-
# header bug, PROGRESS.md/DECISIONS.md 2026-07-06) — NO GPU, NO new vLLM generation. Mirrors
# validate_statements.sh's Lean-env staging exactly.
#
# Usage:  sbatch slurm/phase8_reverify.sh <config> <run_dir> <out_dir> [--limit N]
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${1:?config required}"
RUN_DIR="${2:?run_dir required}"
OUT_DIR="${3:?out_dir required}"
shift 3
EXTRA_ARGS="$*"   # e.g. "--limit 20" for a smoke

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
    echo "[reverify] conda activate failed (attempt $attempt) — retrying in 5s..."; sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV with importable atp."; exit 1; }
echo "[reverify] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

if [ ! -f "$PROJ/results/_lean_env_ready.txt" ]; then
    echo "FATAL: Goedel-pin Lean env not built (no results/_lean_env_ready.txt). Run slurm/build_lean.sh."
    exit 1
fi

# Lean env to stage. Default atp-lean-env (Goedel pin); pass ATP_LEAN_ENV_NAME=deepseek-lean-env
# (via --export=ALL,ATP_LEAN_ENV_NAME=...) for a DeepSeek-Prover-V2 config — its pin is a DIFFERENT
# mathlib commit, and its package lib dir is named differently (DeepseekLeanEnv/ vs AtpLeanEnv/), so
# copying the WHOLE env dir (not enumerating a hardcoded lib name) is required for this to work for
# any pin — an earlier version of this script hardcoded the Goedel naming and would have silently
# re-verified DeepSeek-V2 completions against the WRONG (Goedel) mathlib pin (caught 2026-07-07,
# before trusting the harness-sanity control check — see PROGRESS.md/DECISIONS.md that date).
LEAN_ENV_NAME="${ATP_LEAN_ENV_NAME:-atp-lean-env}"
GPFS_ENV="$PROJ/scratch/lean-cache/$LEAN_ENV_NAME"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/$LEAN_ENV_NAME"
mkdir -p "$LOCAL_BASE"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
exec 9>"$LOCAL_BASE/.atp_stage.${LEAN_ENV_NAME}.lock"
flock 9
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[reverify] Lean env '$LEAN_ENV_NAME' already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    echo "[reverify] staging Lean env '$LEAN_ENV_NAME' -> $LOCAL_ENV (cp $N_GPFS oleans)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
    cp -a "$GPFS_ENV/." "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy to $LOCAL_ENV failed"; flock -u 9; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[reverify] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
fi
flock -u 9; exec 9>&-
export ATP_LEAN_PROJECT="$LOCAL_ENV"

echo "[reverify] running on $CONFIG $RUN_DIR -> $OUT_DIR $EXTRA_ARGS"
# shellcheck disable=SC2086
python scripts/phase8_reverify.py --config "$CONFIG" --run-dir "$RUN_DIR" --out-dir "$OUT_DIR" $EXTRA_ARGS
rc=$?
echo "[reverify] done (rc=$rc)"
exit $rc
