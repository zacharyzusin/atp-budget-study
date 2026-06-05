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
REVISION="${ATP_MODEL_REVISION:-}"                # TODO: pin config.model.revision, pass via env
PORT="${ATP_VLLM_PORT:-8000}"

module load anaconda/2023.09
conda activate "$PROJ/scratch/conda-envs/atp"
export HF_HOME="$PROJ/scratch/hf-cache"

mkdir -p "$PROJ/results" "$PROJ/logs"
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
echo "[vllm] serving $HF_REPO as '$SERVED_NAME' on $HOST_IP:$PORT (endpoint -> $ENDPOINT_FILE)"

REV_ARG=(); [ -n "$REVISION" ] && REV_ARG=(--revision "$REVISION")
exec python -m vllm.entrypoints.openai.api_server \
    --model "$HF_REPO" "${REV_ARG[@]}" \
    --served-model-name "$SERVED_NAME" \
    --host 0.0.0.0 --port "$PORT" \
    --max-model-len 16384 \
    --gpu-memory-utilization 0.90
