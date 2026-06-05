#!/usr/bin/env bash
#SBATCH --job-name=atp_sweep
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --output=logs/sweep-%j.out
#SBATCH --error=logs/sweep-%j.err
#
# One-command baseline eval: bring up vLLM on the GPU, wait for it, run the restartable sweep
# (`atp sweep`), then shut the server down. Restartable (rule 0.3): completed (problem,seed) cells
# are skipped on requeue. Verification runs on the Goedel-pinned Lean env (the only env whose numbers
# we report — DECISIONS.md guardrail); build it first with slurm/build_lean.sh.
#
# Usage:  sbatch slurm/sweep.sh configs/phase0_baseline.yaml [run_name]
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${1:-configs/phase0_baseline.yaml}"
RUN_NAME="${2:-baseline}"
PORT="${ATP_VLLM_PORT:-8000}"
ENDPOINT_FILE="$PROJ/results/_vllm_endpoint.txt"

module load anaconda/2023.09
conda activate "$PROJ/scratch/conda-envs/atp"
export HF_HOME="$PROJ/scratch/hf-cache"
cd "$PROJ"

# Confirm the Goedel-pin Lean env is built (guardrail: reported numbers require it).
if [ ! -f "$PROJ/results/_lean_env_ready.txt" ]; then
    echo "FATAL: Goedel-pin Lean env not built (no results/_lean_env_ready.txt). Run slurm/build_lean.sh."
    exit 1
fi

# Start vLLM in the background on this node's GPU.
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
python -m vllm.entrypoints.openai.api_server \
    --model "Goedel-LM/Goedel-Prover-V2-8B" \
    --served-model-name "goedel-prover-v2-8b" \
    --host 0.0.0.0 --port "$PORT" --max-model-len 16384 --gpu-memory-utilization 0.90 \
    > "logs/vllm-inproc-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

echo "[sweep] waiting for vLLM to come up on $HOST_IP:$PORT ..."
for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[sweep] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done

echo "[sweep] running eval: config=$CONFIG name=$RUN_NAME"
python -m atp.cli sweep --config "$CONFIG" --name "$RUN_NAME" --resume
echo "[sweep] done; results in $PROJ/results/$RUN_NAME"
