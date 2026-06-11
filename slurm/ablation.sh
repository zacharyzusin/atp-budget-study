#!/usr/bin/env bash
#SBATCH --job-name=atp_ablation
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --array=0-6%4
# --array=0-6 == the 7 cells of phase1_ablation.yaml (`atp ablation --config <f> --list`); %4 caps
# concurrency (each cell needs its OWN l40s + vLLM). If the config's cell count changes, update the
# range — over-provisioning is SAFE (a task whose id >= cell count exits 0 below), under-provisioning
# silently drops cells. CPUs/mem sized for eval.n_workers Lean REPLs + the vLLM server (as sweep.sh).
#SBATCH --output=logs/abl-%A_%a.out
#SBATCH --error=logs/abl-%A_%a.err
#
# Run ONE Phase 1 ablation cell per array task: bring up vLLM, probe Lean, run that cell's
# problems×seeds grid via `atp ablation --cell-id`, into results/<run>/<cell>/. Restartable (rule
# 0.3): completed (problem,seed) cells are skipped on requeue. Each array task serves its own vLLM
# and (under flock) shares the node-local Lean env. Adapted from slurm/sweep.sh — KEEP THE SHARED
# HARDENING (proxy/conda/Lean-stage/norm_num probe) IN SYNC with that file.
#
# Usage:  sbatch slurm/ablation.sh [configs/phase1_ablation.yaml] [run_name]
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${1:-configs/phase1_ablation.yaml}"
RUN_NAME="${2:-phase1_ablation}"
TASK="${SLURM_ARRAY_TASK_ID:-0}"
# Per-task vLLM port + endpoint file so co-located array tasks never collide (sweep.sh's single
# shared endpoint file would be clobbered). run_eval honors ATP_VLLM_ENDPOINT_FILE.
PORT="$(( ${ATP_VLLM_PORT:-8000} + TASK ))"
ENDPOINT_FILE="$PROJ/results/_vllm_endpoint_${SLURM_ARRAY_JOB_ID:-local}_${TASK}.txt"
export ATP_VLLM_ENDPOINT_FILE="$ENDPOINT_FILE"

# Insomnia proxy trap: Slurm jobs inherit a per-session SSH proxy that breaks ALL downloads.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

module load anaconda/2023.09
# conda activate in a non-interactive batch shell needs the hook sourced; some nodes return 0 without
# switching python, so force the env bin onto PATH + verify `import atp`. (See sweep.sh / PROGRESS.)
ATP_ENV="$PROJ/scratch/conda-envs/atp"
activate_env() {
    local base; base="$(conda info --base 2>/dev/null)"
    [ -n "$base" ] && [ -f "$base/etc/profile.d/conda.sh" ] || return 1
    set +u
    source "$base/etc/profile.d/conda.sh"
    conda activate "$ATP_ENV" 2>/dev/null
    set -u
    export PATH="$ATP_ENV/bin:$PATH"; export CONDA_PREFIX="$ATP_ENV"
    hash -r 2>/dev/null || true
    [ "$(command -v python)" = "$ATP_ENV/bin/python" ] || return 1
    python -c "import atp" 2>/dev/null || return 1
}
ok=0
for attempt in 1 2 3; do
    if activate_env; then ok=1; break; fi
    echo "[abl $TASK] conda activate/import atp failed (attempt $attempt) — retrying in 5s..."
    sleep 5
done
if [ "$ok" != 1 ]; then
    echo "FATAL: could not activate $ATP_ENV with importable atp after 3 tries."
    exit 1
fi
echo "[abl $TASK] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

# Resolve this task's cell (id → name) and SKIP cleanly if the array over-provisioned past the cells.
N_CELLS="$(python -c "from atp.config import load_config; from atp.eval.ablation import expand_ablation; print(len(expand_ablation(load_config('$CONFIG'))))")" || {
    echo "FATAL: could not expand $CONFIG"; exit 1; }
if [ "$TASK" -ge "$N_CELLS" ]; then
    echo "[abl $TASK] no cell for task $TASK (only $N_CELLS cells) — nothing to do, exiting 0."
    exit 0
fi
CELL_NAME="$(python -c "from atp.config import load_config; from atp.eval.ablation import expand_ablation; print(expand_ablation(load_config('$CONFIG'))[$TASK].name)")" || {
    echo "FATAL: could not resolve cell name for task $TASK"; exit 1; }
echo "[abl $TASK] cell=$CELL_NAME ($((TASK+1))/$N_CELLS) run=$RUN_NAME"

# Confirm the Goedel-pin Lean env is built (guardrail: reported numbers require it).
if [ ! -f "$PROJ/results/_lean_env_ready.txt" ]; then
    echo "FATAL: Goedel-pin Lean env not built (no results/_lean_env_ready.txt). Run slurm/build_lean.sh."
    exit 1
fi

# --- Stage the Lean env to node-local SSD, flock-guarded (array tasks may co-locate) --------------
# import Mathlib off contended GPFS timed out at 2700s; from node-local SSD it's ~141s. Co-located
# array tasks would otherwise race the rm -rf + copy, so serialize per node with flock: the first
# task stages, the rest wait for the lock then reuse the .staged_ok env. (See sweep.sh for the why.)
GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
mkdir -p "$LOCAL_BASE"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
exec 9>"$LOCAL_BASE/.atp_stage.lock"
flock 9   # blocks until this node's staging lock is free
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[abl $TASK] Lean env already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    echo "[abl $TASK] staging Lean env -> $LOCAL_ENV (cp $N_GPFS oleans, ~10-20min off GPFS)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"
    t0=$SECONDS
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy to $LOCAL_ENV failed"; flock -u 9; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[abl $TASK] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
fi
flock -u 9; exec 9>&-
export ATP_LEAN_PROJECT="$LOCAL_ENV"

# GUARDRAIL probe: env must accept trivial-true AND norm_num, and reject a false proof, BEFORE GPU.
echo "[abl $TASK] Lean trivial-true/false + norm_num probe (cold Mathlib load ~2-3min)..."
python - "$CONFIG" <<'PY' || { echo "FATAL: Lean probe failed — env broken, refusing to spend GPU."; exit 1; }
import sys, time
from atp.config import load_config
from atp.lean import ReplBackend, Verifier, Theorem
cfg = load_config(sys.argv[1])
v = Verifier.from_config(cfg, ReplBackend(cfg))
t0 = time.time()
ok = v.verify(Theorem(name="probe", statement="theorem probe : True"),
              "theorem probe : True := by\n  trivial")
print(f"[abl] import Mathlib + first verify took {time.time()-t0:.0f}s")
nn = v.verify(Theorem(name="nn", statement="theorem nn : (2:Nat)+2=4"),
              "theorem nn : (2:Nat) + 2 = 4 := by\n  norm_num")
bad = v.verify(Theorem(name="bad", statement="theorem bad : (1:Nat)=2"),
               "theorem bad : (1:Nat) = 2 := by\n  rfl")
assert ok.ok, f"trivial-true rejected: {ok.feedback}"
assert nn.ok, f"norm_num proof rejected (broken env?): {nn.reason} / {nn.feedback}"
assert (not bad.ok) and bad.reason == "compile_error", f"false-proof not rejected: {bad.reason}"
print("[abl] Lean probe OK (true + norm_num accepted, false rejected)")
PY

# Pin the served weights to the exact reviewed revision (reproducibility rule 4).
REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
echo "[abl $TASK] serving Goedel-Prover-V2-8B @ revision=$REVISION max_model_len=$MAX_MODEL_LEN port=$PORT"

# Start vLLM in the background on this task's GPU + per-task port.
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
python -m vllm.entrypoints.openai.api_server \
    --model "Goedel-LM/Goedel-Prover-V2-8B" --revision "$REVISION" \
    --served-model-name "goedel-prover-v2-8b" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/vllm-abl-${SLURM_ARRAY_JOB_ID:-local}_${TASK}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null; rm -f "$ENDPOINT_FILE"' EXIT

echo "[abl $TASK] waiting for vLLM on $HOST_IP:$PORT ..."
for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[abl $TASK] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done

echo "[abl $TASK] running cell: config=$CONFIG cell-id=$TASK ($CELL_NAME) name=$RUN_NAME"
# set -uo pipefail (no -e): capture rc and fail LOUDLY so a crashed cell shows Slurm FAILED, not
# COMPLETED (the baseline's silent-COMPLETED-on-crash trap, PROGRESS 2026-06-07).
python -m atp.cli ablation --config "$CONFIG" --cell-id "$TASK" --name "$RUN_NAME" --resume
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "FATAL: ablation cell $CELL_NAME exited $rc — see logs/abl-${SLURM_ARRAY_JOB_ID}_${TASK}.err"
    exit "$rc"
fi
METRICS="$PROJ/results/$RUN_NAME/$CELL_NAME/metrics.json"
if [ ! -f "$METRICS" ]; then
    echo "FATAL: cell exited 0 but $METRICS is missing."
    exit 1
fi
echo "[abl $TASK] done; results in $PROJ/results/$RUN_NAME/$CELL_NAME"
