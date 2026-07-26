#!/usr/bin/env bash
#SBATCH --job-name=p_decomp_ds
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --output=logs/pdecompds-%j.out
#SBATCH --error=logs/pdecompds-%j.err
#
# DeepSeek-Prover-V2-7B analog of slurm/phase_decomp_run.sh (WS6 item 3 second-model probe, per user
# request 2026-07-26: the Goedel-only decomposition NO-GO is a stronger claim as a two-model result,
# and 4 smoke rounds cost ~2 GPU-h, cheap relative to what it buys). Model identity + Lean env are
# config/env-driven (same pattern as slurm/sweep_array.sh), NOT hardcoded to Goedel, so this is the
# same phase_decomp_run.py driving DecompositionAgent against a different served model + Lean pin.
#
# Usage: sbatch --export=ALL,ATP_LEAN_ENV_NAME=deepseek-lean-env,ELAN_HOME=scratch/elan-deepseek,\
#   ATP_HF_HOME=/insomnia001/depts/edu/COMS-E6998-012/zwz2000/.hf_cache,ATP_VLLM_PORT=8300 \
#   slurm/phase_decomp_deepseek_run.sh <config> <trapped_file> <out_dir> [seeds] [budget] \
#       [max_rounds] [max_subgoal_rounds]
#   sbatch --export=ALL,ATP_LEAN_ENV_NAME=deepseek-lean-env,ELAN_HOME=scratch/elan-deepseek,\
#     ATP_HF_HOME=/insomnia001/depts/edu/COMS-E6998-012/zwz2000/.hf_cache,ATP_VLLM_PORT=8300 \
#     slurm/phase_decomp_deepseek_run.sh configs/deepseek_minif2f_baseline.yaml \
#       scratch/phase2/trapped_minif2f_decomp_smoke.txt results/phase_decomp/smoke_ds1 0 60000 3 3
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${1:?need config}"
TRAPPED="${2:?need trapped file}"
OUT="${3:?need out dir}"
SEEDS="${4:-0}"
BUDGET="${5:-32000}"
MAX_ROUNDS="${6:-8}"
MAX_SUBGOAL_ROUNDS="${7:-8}"
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
    echo "[pdecompds] conda activate/import atp failed (attempt $attempt) — retrying in 5s..."
    sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV"; exit 1; }
echo "[pdecompds] env OK: python=$(command -v python)"
export HF_HOME="${ATP_HF_HOME:-$PROJ/scratch/hf-cache}"
export HF_HUB_OFFLINE="${ATP_HF_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${ATP_HF_OFFLINE:-1}"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

[ -f "$PROJ/results/_deepseek_lean_env_ready.txt" ] || { echo "FATAL: DeepSeek-pin Lean env not built"; exit 1; }

# --- Stage the Lean env to node-local SSD, PER-JOB-ID path (same fix as phase_decomp_run.sh) --------
LEAN_ENV_NAME="${ATP_LEAN_ENV_NAME:?need ATP_LEAN_ENV_NAME=deepseek-lean-env}"
GPFS_ENV="$PROJ/scratch/lean-cache/$LEAN_ENV_NAME"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/${LEAN_ENV_NAME}-j${SLURM_JOB_ID:-$$}"
mkdir -p "$LOCAL_BASE"
rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
echo "[pdecompds] staging Lean env -> $LOCAL_ENV ..."
cp -a "$GPFS_ENV/." "$LOCAL_ENV/" \
    || { echo "FATAL: staging copy to $LOCAL_ENV failed"; exit 1; }
echo "[pdecompds] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
export ATP_LEAN_PROJECT="$LOCAL_ENV"

echo "[pdecompds] Lean guardrail probe (cold Mathlib load ~2-3min)..."
python - "$CONFIG" <<'PY' || { echo "FATAL: Lean probe failed — refusing to spend GPU."; exit 1; }
import sys, time
from atp.config import load_config
from atp.lean import ReplBackend, Verifier, Theorem
cfg = load_config(sys.argv[1])
v = Verifier.from_config(cfg, ReplBackend(cfg))
t0 = time.time()
ok = v.verify(Theorem(name="probe", statement="theorem probe : True"), "theorem probe : True := by\n  trivial")
nn = v.verify(Theorem(name="nn", statement="theorem nn : (2:Nat)+2=4"), "theorem nn : (2:Nat) + 2 = 4 := by\n  norm_num")
bad = v.verify(Theorem(name="bad", statement="theorem bad : (1:Nat)=2"), "theorem bad : (1:Nat) = 2 := by\n  rfl")
assert ok.ok and nn.ok and (not bad.ok), f"probe bad: true={ok.reason} nn={nn.reason} false={bad.reason}"
backend = ReplBackend(cfg)
sketch = "theorem probe2 : True := by\n  have h1 : True := sorry\n  exact h1"
raw = backend.verify(Theorem(name="probe2", statement="theorem probe2 : True"), sketch)
assert raw.success and raw.declares_goal and not raw.timed_out, f"sketch probe failed: {raw.output[:500]}"
print(f"[pdecompds] Lean probe OK incl. sketch-check semantics ({time.time()-t0:.0f}s)")
PY

HF_REPO="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.hf_repo)")"
SERVED_NAME="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.name)")"
REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
echo "[pdecompds] serving $HF_REPO (as $SERVED_NAME) @ revision=$REVISION max_model_len=$MAX_MODEL_LEN"
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
python -m vllm.entrypoints.openai.api_server \
    --model "$HF_REPO" --revision "$REVISION" \
    --served-model-name "$SERVED_NAME" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/pdecompds-vllm-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

echo "[pdecompds] waiting for vLLM on $HOST_IP:$PORT ..."
for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[pdecompds] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done

echo "[pdecompds] running: config=$CONFIG trapped=$TRAPPED out=$OUT seeds=$SEEDS budget=$BUDGET max_rounds=$MAX_ROUNDS max_subgoal_rounds=$MAX_SUBGOAL_ROUNDS"
python scripts/phase_decomp_run.py --config "$CONFIG" --trapped "$TRAPPED" --out "$OUT" \
    --seeds "$SEEDS" --budget "$BUDGET" --max-rounds "$MAX_ROUNDS" \
    --max-subgoal-rounds "$MAX_SUBGOAL_ROUNDS" --n-workers 4
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "FATAL: run exited $rc — see logs/pdecompds-${SLURM_JOB_ID:-local}.err"
    exit "$rc"
fi
if [ ! -f "$PROJ/$OUT/metrics.json" ]; then
    echo "FATAL: exited 0 but $PROJ/$OUT/metrics.json is missing."
    exit 1
fi
echo "[pdecompds] done; results in $PROJ/$OUT"
