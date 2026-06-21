#!/usr/bin/env bash
#SBATCH --job-name=p5_pilot_g
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --time=04:55:00
#SBATCH --requeue
#SBATCH --output=logs/p5_pilot_goedel-%j.out
#SBATCH --error=logs/p5_pilot_goedel-%j.err
#
# Phase 5 Task 5.2 PILOT GATE (Goedel × ProofNet#): resume-extend ~10 still-progressing extend-set
# cells from their logged 128k checkpoints to E=512k, early-stopping on solve, and count extension
# solves (per-seed). This is the go/no-go before any full extension run. Reuses sweep.sh's proven
# Goedel-serving + Goedel-pin Lean staging + soundness probe wholesale; only the trailing command is
# swapped (atp sweep -> scripts/phase5_pilot.py). Restartable (rule 0.3): finished cells skip on requeue.
#
# Usage:  sbatch slurm/phase5_pilot_goedel.sh
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${ATP_PILOT_CONFIG:-configs/proofnet_baseline.yaml}"
BASELINE="${ATP_PILOT_BASELINE:-results/proofnet_baseline}"
NEW_BUDGET="${ATP_PILOT_BUDGET:-512000}"
RUN_NAME="${ATP_PILOT_NAME:-phase5_pilot_goedel_proofnet}"
PORT="${ATP_VLLM_PORT:-8000}"
ENDPOINT_FILE="$PROJ/results/_vllm_endpoint.txt"

# Insomnia proxy trap: Slurm jobs inherit a per-session SSH proxy that breaks ALL downloads.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

module load anaconda/2023.09
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
    echo "[pilot] conda activate/import atp failed (attempt $attempt) — retrying in 5s..."; sleep 5
done
if [ "$ok" != 1 ]; then
    echo "FATAL: could not activate $ATP_ENV with importable atp after 3 tries."; exit 1
fi
echo "[pilot] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

if [ ! -f "$PROJ/results/_lean_env_ready.txt" ]; then
    echo "FATAL: Goedel-pin Lean env not built (no results/_lean_env_ready.txt). Run slurm/build_lean.sh."
    exit 1
fi
if [ ! -d "$PROJ/$BASELINE/agent_states" ]; then
    echo "FATAL: baseline agent_states dir missing at $PROJ/$BASELINE/agent_states (need 128k checkpoints)."
    exit 1
fi
if [ ! -f "$PROJ/results/phase5/candidates.json" ]; then
    echo "FATAL: results/phase5/candidates.json missing. Run scripts/phase5_candidates.py first."
    exit 1
fi

# --- Stage the Goedel-pin Lean env to node-local SSD (the cold-load fix) --------------------------
GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[pilot] Lean env already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    echo "[pilot] staging Lean env -> $LOCAL_ENV (cp $N_GPFS oleans, ~10-20min off GPFS)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy to $LOCAL_ENV failed"; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[pilot] staged ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

# GUARDRAIL probe: true + norm_num accepted, false rejected — before spending GPU.
echo "[pilot] Lean trivial-true/norm_num/false probe (cold Mathlib load ~2-3min)..."
python - "$CONFIG" <<'PY' || { echo "FATAL: Lean probe failed — refusing to spend GPU."; exit 1; }
import sys, time
from atp.config import load_config
from atp.lean import ReplBackend, Verifier, Theorem
cfg = load_config(sys.argv[1])
v = Verifier.from_config(cfg, ReplBackend(cfg))
t0 = time.time()
ok = v.verify(Theorem(name="probe", statement="theorem probe : True"),
              "theorem probe : True := by\n  trivial")
print(f"[pilot] import Mathlib + first verify took {time.time()-t0:.0f}s")
nn = v.verify(Theorem(name="nn", statement="theorem nn : (2:Nat)+2=4"),
              "theorem nn : (2:Nat) + 2 = 4 := by\n  norm_num")
bad = v.verify(Theorem(name="bad", statement="theorem bad : (1:Nat)=2"),
               "theorem bad : (1:Nat) = 2 := by\n  rfl")
assert ok.ok, f"trivial-true rejected: {ok.feedback}"
assert nn.ok, f"norm_num proof rejected (broken env?): {nn.reason} / {nn.feedback}"
assert (not bad.ok) and bad.reason == "compile_error", f"false-proof not rejected: {bad.reason}"
print("[pilot] Lean probe OK (true + norm_num accepted, false rejected)")
PY

# Pin the served weights to the exact reviewed revision (reproducibility rule 4).
REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
echo "[pilot] serving Goedel-Prover-V2-8B @ revision=$REVISION max_model_len=$MAX_MODEL_LEN"

HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
python -m vllm.entrypoints.openai.api_server \
    --model "Goedel-LM/Goedel-Prover-V2-8B" --revision "$REVISION" \
    --served-model-name "goedel-prover-v2-8b" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/vllm-pilot-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

echo "[pilot] waiting for vLLM to come up on $HOST_IP:$PORT ..."
for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[pilot] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done

echo "[pilot] extend pilot: config=$CONFIG baseline=$BASELINE E=$NEW_BUDGET name=$RUN_NAME"
python scripts/phase5_pilot.py \
    --config "$CONFIG" --baseline "$BASELINE" \
    --model goedel --benchmark proofnet_sharp \
    --new-budget "$NEW_BUDGET" --name "$RUN_NAME"
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "FATAL: pilot exited $rc — see logs/p5_pilot_goedel-${SLURM_JOB_ID:-local}.err"
    exit "$rc"
fi
if [ ! -f "$PROJ/results/$RUN_NAME/pilot_summary.json" ]; then
    echo "FATAL: pilot exited 0 but $PROJ/results/$RUN_NAME/pilot_summary.json is missing."
    exit 1
fi
echo "[pilot] done; summary in $PROJ/results/$RUN_NAME/pilot_summary.json"
