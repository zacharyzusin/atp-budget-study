#!/usr/bin/env bash
#SBATCH --job-name=p7_fmt_diag
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --time=00:45:00
#SBATCH --output=logs/p7fmtdiag-%j.out
#SBATCH --error=logs/p7fmtdiag-%j.err
#
# Diagnostic-only: print RAW completions for a config's own prompt_template on a few real goal
# states, before trusting a Mode 4 run's numbers. Generalized (model repo/served-name/max-tokens all
# read from the config, not hardcoded) so it works for any model — first used to catch
# Goedel-Prover-V2-8B ignoring the single-tactic instruction (2026-07-05), now reused to validate
# BFS-Prover-V1-7B's format + Lean-pin compatibility before its real Mode 4 run.
#
# Usage: sbatch slurm/phase7_format_e_diagnostic.sh <config> <max_tokens> <name1> [name2] ...
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${1:?need config}"; shift
MAX_TOKENS="${1:?need max_tokens}"; shift
NAMES=("$@")
PORT="${ATP_VLLM_PORT:-8000}"
ENDPOINT_FILE="$PROJ/results/_vllm_endpoint.txt"

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
    sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV"; exit 1; }
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[p7fmtdiag] Lean env already staged — reusing."
else
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging failed"; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

HF_REPO="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.hf_repo)")"
SERVED_NAME="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.name)")"
REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
echo "[p7fmtdiag] serving $HF_REPO (as $SERVED_NAME) @ revision=$REVISION max_model_len=$MAX_MODEL_LEN"
python -m vllm.entrypoints.openai.api_server \
    --model "$HF_REPO" --revision "$REVISION" \
    --served-model-name "$SERVED_NAME" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/p7fmtdiag-vllm-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[p7fmtdiag] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died"; exit 1; }
done

python scripts/phase7_format_e_diagnostic.py --config "$CONFIG" --max-tokens "$MAX_TOKENS" --names "${NAMES[@]}"
