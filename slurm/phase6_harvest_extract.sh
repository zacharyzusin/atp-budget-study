#!/usr/bin/env bash
#SBATCH --job-name=p6_extract
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --requeue
#SBATCH --output=logs/p6_extract-%j.out
#SBATCH --error=logs/p6_extract-%j.err
#
# Phase 6 Task 6.1 EXTRACTION (CPU + Lean, NO GPU, NO model): turn a generation run dir into the SFT
# datasets (rft.jsonl + closing_targets.jsonl) via scripts/phase6_harvest.py. The closing-target step
# elaborates `<prefix> … sorry` sources in the REPL, so it needs the (model-matched) Lean env staged
# to node-local SSD — same pin-agnostic staging as slurm/phase5_pilot.sh.
#
# Usage (Goedel):
#   ATP_HARVEST_CONFIG=configs/phase6_harvest_goedel.yaml \
#   ATP_HARVEST_RUN_DIR=results/phase6_harvest_goedel \
#   ATP_HARVEST_OUT_DIR=scratch/phase6/sft/goedel \
#   sbatch slurm/phase6_harvest_extract.sh
# Usage (DeepSeek): add ELAN_HOME=$PWD/scratch/elan-deepseek ATP_LEAN_ENV_NAME=deepseek-lean-env
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${ATP_HARVEST_CONFIG:-configs/phase6_harvest_goedel.yaml}"
RUN_DIR="${ATP_HARVEST_RUN_DIR:-results/phase6_harvest_goedel}"
OUT_DIR="${ATP_HARVEST_OUT_DIR:-scratch/phase6/sft/goedel}"
MAX_PER_PROOF="${ATP_HARVEST_MAX_PER_PROOF:-2}"

# Insomnia proxy trap: Slurm jobs inherit a per-session SSH proxy that breaks downloads.
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
    echo "[extract] conda activate failed (attempt $attempt) — retrying in 5s..."; sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV with importable atp."; exit 1; }
echo "[extract] env OK: python=$(command -v python)"
export HF_HOME="${ATP_HF_HOME:-$PROJ/scratch/hf-cache}"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

if [ ! -d "$PROJ/$RUN_DIR/agent_states" ]; then
    echo "FATAL: run dir $PROJ/$RUN_DIR/agent_states missing (need a generation run first)."
    exit 1
fi

# --- Stage the (pin-agnostic) Lean env to node-local /dev/shm ---------------------------------------
LEAN_ENV_NAME="${ATP_LEAN_ENV_NAME:-atp-lean-env}"
GPFS_ENV="$PROJ/scratch/lean-cache/$LEAN_ENV_NAME"
LOCAL_BASE="${ATP_LOCAL_BASE:-/dev/shm/$USER}"
[ -d /dev/shm ] || LOCAL_BASE="/local/$USER"; [ -d /local ] || [ -d /dev/shm ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/${LEAN_ENV_NAME}-extract"
REPL_REL=".lake/packages/REPL/.lake/build/bin/repl"
mkdir -p "$LOCAL_BASE"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ] \
   && [ -x "$LOCAL_ENV/$REPL_REL" ]; then
    echo "[extract] Lean env '$LEAN_ENV_NAME' already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    STAGE="$LOCAL_BASE/${LEAN_ENV_NAME}.stage.${SLURM_JOB_ID:-x}"
    echo "[extract] staging '$LEAN_ENV_NAME' -> $LOCAL_ENV (cp $N_GPFS oleans)..."
    rm -rf "$STAGE"; mkdir -p "$STAGE"
    cp -a "$GPFS_ENV/." "$STAGE/" \
        || { echo "FATAL: staging copy to $STAGE failed"; rm -rf "$STAGE"; exit 1; }
    [ -x "$STAGE/$REPL_REL" ] \
        || { echo "FATAL: staged env missing repl exe at $STAGE/$REPL_REL"; rm -rf "$STAGE"; exit 1; }
    touch "$STAGE/.staged_ok"
    rm -rf "$LOCAL_ENV.old"; mv -T "$LOCAL_ENV" "$LOCAL_ENV.old" 2>/dev/null || true
    mv -T "$STAGE" "$LOCAL_ENV"; rm -rf "$LOCAL_ENV.old"
    echo "[extract] staged ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans + repl)."
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

echo "[extract] harvest: config=$CONFIG run_dir=$RUN_DIR out_dir=$OUT_DIR max_per_proof=$MAX_PER_PROOF"
python scripts/phase6_harvest.py \
    --config "$CONFIG" --run-dir "$RUN_DIR" --out-dir "$OUT_DIR" --max-per-proof "$MAX_PER_PROOF"
rc=$?
echo "[extract] done (rc=$rc)"
exit $rc
