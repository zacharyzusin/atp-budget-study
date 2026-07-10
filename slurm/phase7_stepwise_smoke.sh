#!/usr/bin/env bash
#SBATCH --job-name=p7_stepwise_smoke
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=1:30:00
#SBATCH --output=logs/p7smoke-%j.out
#SBATCH --error=logs/p7smoke-%j.err
#
# Phase 7 Track 1 — Mode 3 (verified-state re-grounding) smoke, Goedel x ProofNet# trapped core.
# Rule 5 (smoke before scale) + feedback_test_before_submit: prove the real GPU+Lean path works on a
# tiny (3-name, seed 0) slice before scaling to the full trapped-first eval. Reuses slurm/sweep.sh's
# proven Lean-staging + vLLM-serve blocks verbatim; only the final invocation differs
# (phase7_stepwise_run.py instead of `atp sweep`).
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="configs/proofnet_baseline.yaml"
TRAPPED="scratch/phase7/trapped_proofnet_smoke3.txt"
OUT="results/phase7/smoke_goedel_proofnet_mode3"
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
ok=0; for attempt in 1 2 3; do activate_env && { ok=1; break; }; echo "[p7smoke] activate retry $attempt"; sleep 5; done
[ "$ok" = 1 ] || { echo "FATAL: cannot activate $ATP_ENV"; exit 1; }
echo "[p7smoke] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

[ -f "$PROJ/results/_lean_env_ready.txt" ] || { echo "FATAL: Goedel-pin Lean env not built"; exit 1; }

# Tiny trapped-name slice for the smoke (first 3 of trapped_proofnet.txt).
mkdir -p scratch/phase7
head -n 3 scratch/phase2/trapped_proofnet.txt > "$TRAPPED"
echo "[p7smoke] smoke trapped names:"; cat "$TRAPPED"

# --- Stage the Lean env to node-local SSD (verbatim from slurm/sweep.sh) ---------------------------
GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[p7smoke] Lean env already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    echo "[p7smoke] staging Lean env -> $LOCAL_ENV ..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy to $LOCAL_ENV failed"; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[p7smoke] staged in $((SECONDS-t0))s."
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

echo "[p7smoke] Lean guardrail probe (cold Mathlib load ~2-3min)..."
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
print(f"[p7smoke] Lean probe OK ({time.time()-t0:.0f}s)")
PY

REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
echo "[p7smoke] serving Goedel-Prover-V2-8B @ revision=$REVISION max_model_len=$MAX_MODEL_LEN"
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
python -m vllm.entrypoints.openai.api_server \
    --model "Goedel-LM/Goedel-Prover-V2-8B" --revision "$REVISION" \
    --served-model-name "goedel-prover-v2-8b" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/p7smoke-vllm-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

echo "[p7smoke] waiting for vLLM on $HOST_IP:$PORT ..."
for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[p7smoke] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done

echo "[p7smoke] running Mode 3 smoke: 3 trapped names, seed 0, budget 8000, max-rounds 3"
python scripts/phase7_stepwise_run.py --config "$CONFIG" --trapped "$TRAPPED" --out "$OUT" \
    --seeds 0 --budget 8000 --max-rounds 3 --n-workers 1
rc=$?
[ "$rc" -ne 0 ] && { echo "FATAL: smoke exited $rc"; exit "$rc"; }
[ -f "$PROJ/$OUT/metrics.json" ] || { echo "FATAL: exited 0 but no metrics.json in $OUT"; exit 1; }
echo "[p7smoke] SMOKE PASSED -> $OUT"
