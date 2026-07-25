#!/usr/bin/env bash
#SBATCH --job-name=p_decomp
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --output=logs/pdecomp-%j.out
#SBATCH --error=logs/pdecomp-%j.err
#
# WS6 item 3 -- subgoal decomposition real eval run. Verbatim copy of slurm/phase7_stepwise_run.sh's
# staging + vLLM-serve blocks (same sizing rationale); only the final invocation differs
# (scripts/phase_decomp_run.py instead of phase7_stepwise_run.py). Restartable via run_sweep's
# per-cell resume (rule 3) -- --requeue lets Slurm auto-requeue a preemption.
#
# Usage: sbatch slurm/phase_decomp_run.sh <config> <trapped_file> <out_dir> [seeds] [budget] \
#            [max_rounds] [max_subgoal_rounds]
#   sbatch slurm/phase_decomp_run.sh configs/phase0_baseline.yaml \
#       scratch/phase2/trapped_minif2f_decomp_smoke.txt results/phase_decomp/smoke 0 20000 2 2
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
    echo "[pdecomp] conda activate/import atp failed (attempt $attempt) — retrying in 5s..."
    sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV"; exit 1; }
echo "[pdecomp] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

[ -f "$PROJ/results/_lean_env_ready.txt" ] || { echo "FATAL: Goedel-pin Lean env not built"; exit 1; }

# --- Stage the Lean env to node-local SSD (verbatim from slurm/sweep.sh) ---------------------------
GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[pdecomp] Lean env already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    echo "[pdecomp] staging Lean env -> $LOCAL_ENV (cp $N_GPFS oleans)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy to $LOCAL_ENV failed"; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[pdecomp] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

echo "[pdecomp] Lean guardrail probe (cold Mathlib load ~2-3min)..."
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
# Also probe the sketch-check path DecompositionAgent relies on: backend.verify() directly (not
# Verifier.verify()) must ACCEPT a sorry-filled have as structurally valid.
backend = ReplBackend(cfg)
sketch = "theorem probe2 : True := by\n  have h1 : True := sorry\n  exact h1"
raw = backend.verify(Theorem(name="probe2", statement="theorem probe2 : True"), sketch)
assert raw.success and raw.declares_goal and not raw.timed_out, f"sketch probe failed: {raw.output[:500]}"
print(f"[pdecomp] Lean probe OK incl. sketch-check semantics ({time.time()-t0:.0f}s)")
PY

REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
echo "[pdecomp] serving Goedel-Prover-V2-8B @ revision=$REVISION max_model_len=$MAX_MODEL_LEN"
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
python -m vllm.entrypoints.openai.api_server \
    --model "Goedel-LM/Goedel-Prover-V2-8B" --revision "$REVISION" \
    --served-model-name "goedel-prover-v2-8b" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/pdecomp-vllm-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

echo "[pdecomp] waiting for vLLM on $HOST_IP:$PORT ..."
for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[pdecomp] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done

echo "[pdecomp] running: config=$CONFIG trapped=$TRAPPED out=$OUT seeds=$SEEDS budget=$BUDGET max_rounds=$MAX_ROUNDS max_subgoal_rounds=$MAX_SUBGOAL_ROUNDS"
python scripts/phase_decomp_run.py --config "$CONFIG" --trapped "$TRAPPED" --out "$OUT" \
    --seeds "$SEEDS" --budget "$BUDGET" --max-rounds "$MAX_ROUNDS" \
    --max-subgoal-rounds "$MAX_SUBGOAL_ROUNDS" --n-workers 4
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "FATAL: run exited $rc — see logs/pdecomp-${SLURM_JOB_ID:-local}.err"
    exit "$rc"
fi
if [ ! -f "$PROJ/$OUT/metrics.json" ]; then
    echo "FATAL: exited 0 but $PROJ/$OUT/metrics.json is missing."
    exit 1
fi
echo "[pdecomp] done; results in $PROJ/$OUT"
