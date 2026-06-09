#!/usr/bin/env bash
#SBATCH --job-name=atp_vllm
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --output=logs/vllm-%j.out
#SBATCH --error=logs/vllm-%j.err
#
# Persistent vLLM server for the prover (l40s, inference). Writes its host:port to
# results/_vllm_endpoint.txt so the agent (this or another job) can find it (config.model.endpoint_file).
# The served model name MUST match config.model.name so VLLMClient's `model=` field lines up.
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
ENDPOINT_FILE="$PROJ/results/_vllm_endpoint.txt"
SERVED_NAME="goedel-prover-v2-8b"                 # == config.model.name
HF_REPO="Goedel-LM/Goedel-Prover-V2-8B"           # == config.model.hf_repo
PORT="${ATP_VLLM_PORT:-8000}"

# Insomnia proxy trap: unset the inherited SSH proxy or the weight download fails.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

module load anaconda/2023.09
# Verify+retry the activation: with `set -uo pipefail` a silent activate failure under GPFS load
# falls through to the base python (no vllm/atp). Fail fast and loud instead. (See sweep.sh.)
ATP_ENV="$PROJ/scratch/conda-envs/atp"
activate_env() {
    local base; base="$(conda info --base 2>/dev/null)"
    [ -n "$base" ] && [ -f "$base/etc/profile.d/conda.sh" ] || return 1
    set +u
    source "$base/etc/profile.d/conda.sh"
    conda activate "$ATP_ENV" 2>/dev/null
    set -u
    # `conda activate` returns 0 without switching python on some nodes (ins095); force env onto PATH.
    export PATH="$ATP_ENV/bin:$PATH"; export CONDA_PREFIX="$ATP_ENV"
    hash -r 2>/dev/null || true
    [ "$(command -v python)" = "$ATP_ENV/bin/python" ] || return 1
    python -c "import atp" 2>/dev/null || return 1
}
ok=0
for attempt in 1 2 3; do
    if activate_env; then ok=1; break; fi
    echo "[vllm] conda activate/import atp failed (attempt $attempt) — retrying in 5s..."; sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV (python=$(command -v python))"; exit 1; }
export HF_HOME="$PROJ/scratch/hf-cache"
# Default the pinned revision from the base config (override via ATP_MODEL_REVISION).
REVISION="${ATP_MODEL_REVISION:-$(python -c "from atp.config import load_config, BASE_CONFIG; print(load_config(BASE_CONFIG).model.revision)" 2>/dev/null)}"
MAX_MODEL_LEN="${ATP_MAX_MODEL_LEN:-$(python -c "from atp.config import load_config, BASE_CONFIG; print(load_config(BASE_CONFIG).model.max_model_len)" 2>/dev/null)}"

mkdir -p "$PROJ/results" "$PROJ/logs"
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
echo "[vllm] serving $HF_REPO as '$SERVED_NAME' on $HOST_IP:$PORT (endpoint -> $ENDPOINT_FILE)"

REV_ARG=(); [ -n "$REVISION" ] && REV_ARG=(--revision "$REVISION")
exec python -m vllm.entrypoints.openai.api_server \
    --model "$HF_REPO" "${REV_ARG[@]}" \
    --served-model-name "$SERVED_NAME" \
    --host 0.0.0.0 --port "$PORT" \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization 0.90
