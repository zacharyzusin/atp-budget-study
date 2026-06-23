#!/usr/bin/env bash
#SBATCH --job-name=p6_probe
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:A6000:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --time=03:00:00
#SBATCH --requeue
#SBATCH --output=logs/p6_probe-%j.out
#SBATCH --error=logs/p6_probe-%j.err
#
# Phase 6 Stage B continuation probe (Task 6.3 smoke / 6.4 hard-target). Serves the base model with
# vLLM (same startup as sweep_array.sh) + stages the model-matched Lean env to /dev/shm (same as
# phase6_harvest_extract.sh), then runs scripts/phase6_continuation_probe.py: feed the OPTION-1
# continuation prompt (statement+verified-prefix) to the base model and classify each pair HARD (base
# can't close it → keep for Stage B) vs already-closable (drop).
#
# Usage (Goedel smoke):
#   ATP_PROBE_CONFIG=configs/phase6_harvest_goedel.yaml \
#   ATP_PROBE_PAIRS=scratch/phase6/sft/goedel/closing_targets.jsonl \
#   ATP_PROBE_OUT=scratch/phase6/sft/goedel/probe_smoke.json \
#   ATP_PROBE_LIMIT=8 ATP_PROBE_SAMPLES=1 ATP_PROBE_BUDGET=4096 \
#   sbatch --exclude=ins082,ins087 slurm/phase6_probe.sh
# DeepSeek: add ELAN_HOME=$PWD/scratch/elan-deepseek ATP_LEAN_ENV_NAME=deepseek-lean-env and
#   ATP_HF_HOME=/insomnia001/depts/edu/COMS-E6998-012/zwz2000/.hf_cache  (the DeepSeek weights live in
#   the project PARENT dir's .hf_cache — NOT $HOME/.hf_cache and NOT $HOME/.cache/huggingface).
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${ATP_PROBE_CONFIG:-configs/phase6_harvest_goedel.yaml}"
PAIRS="${ATP_PROBE_PAIRS:-scratch/phase6/sft/goedel/closing_targets.jsonl}"
OUT="${ATP_PROBE_OUT:-scratch/phase6/sft/goedel/probe_smoke.json}"
LIMIT="${ATP_PROBE_LIMIT:-8}"
SAMPLES="${ATP_PROBE_SAMPLES:-1}"
BUDGET="${ATP_PROBE_BUDGET:-4096}"
# Sharding: an array job splits the pairs across tasks (each probes rows[shard::N]). Per-shard out
# file; merge after with `--merge`. Non-array (no SLURM_ARRAY_*) => single shard 0/1 = all pairs.
NSHARDS="${SLURM_ARRAY_TASK_COUNT:-1}"
SHARD="${SLURM_ARRAY_TASK_ID:-0}"
[ "$NSHARDS" -gt 1 ] && OUT="${OUT%.json}.s${SHARD}.json"
# Per-shard port + endpoint so co-located array tasks don't collide (sweep_array.sh lesson).
PORT=$(( ${ATP_VLLM_PORT:-8200} + SHARD ))
ENDPOINT_FILE="$PROJ/results/_vllm_endpoint.probe.j${SLURM_ARRAY_JOB_ID:-${SLURM_JOB_ID:-local}}.s${SHARD}.txt"
export ATP_VLLM_ENDPOINT_FILE="$ENDPOINT_FILE"

# Insomnia proxy trap: Slurm jobs inherit a per-session SSH proxy that breaks all downloads.
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
    echo "[probe] conda activate failed (attempt $attempt) — retrying in 5s..."; sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV with importable atp."; exit 1; }
echo "[probe] env OK: python=$(command -v python)"

export HF_HOME="${ATP_HF_HOME:-$PROJ/scratch/hf-cache}"
export HF_HUB_OFFLINE="${ATP_HF_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${ATP_HF_OFFLINE:-1}"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

# --- Stage the (pin-agnostic) Lean env to node-local /dev/shm -------------------------------------
LEAN_ENV_NAME="${ATP_LEAN_ENV_NAME:-atp-lean-env}"
GPFS_ENV="$PROJ/scratch/lean-cache/$LEAN_ENV_NAME"
LOCAL_BASE="${ATP_LOCAL_BASE:-/dev/shm/$USER}"
[ -d /dev/shm ] || LOCAL_BASE="/local/$USER"; [ -d /local ] || [ -d /dev/shm ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/${LEAN_ENV_NAME}-probe-s${SHARD}"  # per-shard: co-located tasks never race
REPL_REL=".lake/packages/REPL/.lake/build/bin/repl"
mkdir -p "$LOCAL_BASE"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ] \
   && [ -x "$LOCAL_ENV/$REPL_REL" ]; then
    echo "[probe] Lean env '$LEAN_ENV_NAME' already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    STAGE="$LOCAL_BASE/${LEAN_ENV_NAME}.probe.stage.${SLURM_JOB_ID:-x}"
    echo "[probe] staging '$LEAN_ENV_NAME' -> $LOCAL_ENV (cp $N_GPFS oleans)..."
    rm -rf "$STAGE"; mkdir -p "$STAGE"
    cp -a "$GPFS_ENV/." "$STAGE/" \
        || { echo "FATAL: staging copy to $STAGE failed"; rm -rf "$STAGE"; exit 1; }
    [ -x "$STAGE/$REPL_REL" ] \
        || { echo "FATAL: staged env missing repl exe at $STAGE/$REPL_REL"; rm -rf "$STAGE"; exit 1; }
    touch "$STAGE/.staged_ok"
    rm -rf "$LOCAL_ENV.old"; mv -T "$LOCAL_ENV" "$LOCAL_ENV.old" 2>/dev/null || true
    mv -T "$STAGE" "$LOCAL_ENV"; rm -rf "$LOCAL_ENV.old"
    echo "[probe] staged ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans + repl)."
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

# --- Start vLLM on this node's GPU (same pattern as sweep_array.sh) --------------------------------
HF_REPO="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.hf_repo)")"
SERVED_NAME="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.name)")"
REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
echo "[probe] serving $HF_REPO (as $SERVED_NAME) @ $REVISION on $HOST_IP:$PORT"
python -m vllm.entrypoints.openai.api_server \
    --model "$HF_REPO" --revision "$REVISION" --served-model-name "$SERVED_NAME" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/vllm-probe-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT
echo "[probe] waiting for vLLM ..."
for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[probe] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done

echo "[probe] config=$CONFIG pairs=$PAIRS out=$OUT limit=$LIMIT samples=$SAMPLES budget=$BUDGET shard=$SHARD/$NSHARDS"
LIMIT_ARG=(); [ "$LIMIT" != "0" ] && [ -n "$LIMIT" ] && LIMIT_ARG=(--limit "$LIMIT")
python scripts/phase6_continuation_probe.py \
    --config "$CONFIG" --pairs "$PAIRS" --out "$OUT" \
    "${LIMIT_ARG[@]}" --samples "$SAMPLES" --budget "$BUDGET" \
    --num-shards "$NSHARDS" --shard-id "$SHARD"
rc=$?
echo "[probe] done (rc=$rc)"
exit $rc
