#!/usr/bin/env bash
#SBATCH --job-name=p7_freshcontrol
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --output=logs/p7fresh-%j.out
#SBATCH --error=logs/p7fresh-%j.err
#
# Phase 7 Track 1 — Mode 3 (verified-state re-grounding) real trapped-first eval. Reuses
# slurm/sweep.sh's proven Lean-staging + vLLM-serve blocks verbatim (same sizing: 16c/110G/l40s
# comfortably covers n_workers=8 concurrent Lean REPLs + the vLLM server); only the final invocation
# differs (phase7_freshcontrol_run.py instead of `atp sweep`) — the SAME existing WholeProofAgent
# (whole-proof + error-feedback refinement, no re-grounding) as the committed baselines, but in a
# FRESH vLLM session on the trapped set, so Mode 3's solve rate can be compared against what mere
# re-sampling (no state-grounding mechanism) achieves by chance alone. Restartable via run_sweep's
# per-cell resume (rule 3) — --requeue lets Slurm auto-requeue a preemption.
#
# Usage: sbatch slurm/phase7_freshcontrol_run.sh <config> <trapped_file> <out_dir> [seeds] [budget]
#   sbatch slurm/phase7_freshcontrol_run.sh configs/proofnet_baseline.yaml \
#       scratch/phase2/trapped_proofnet.txt results/phase7/goedel_proofnet_freshcontrol 0 32000
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${1:?need config}"
TRAPPED="${2:?need trapped file}"
OUT="${3:?need out dir}"
SEEDS="${4:-0}"
BUDGET="${5:-8000}"

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
    echo "[p7fresh] conda activate/import atp failed (attempt $attempt) — retrying in 5s..."
    sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV"; exit 1; }
echo "[p7fresh] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

[ -f "$PROJ/results/_lean_env_ready.txt" ] || { echo "FATAL: Goedel-pin Lean env not built"; exit 1; }

# --- Stage the Lean env to node-local SSD, PER-JOB-ID path -----------------------------------------
# FIXED 2026-07-25: was a fixed shared path (`/local/$USER/atp-lean-env`), which raced against
# phase7_stepwise_run.sh's mode3 job when both landed on the same node (job 11684256's `cp -a`
# collided with a concurrent `rm -rf` from the mode3 job using the identical path — confirmed via
# the exact "No such file or directory" mid-copy error pattern). Per-job-ID path removes the race
# (same fix as slurm/header_confound_reverify.sh / slurm/phase_decomp_run.sh); costs one full
# re-stage per job instead of cross-job reuse, acceptable at this script's call volume.
GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env-j${SLURM_JOB_ID:-$$}"
mkdir -p "$LOCAL_BASE"
rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
echo "[p7fresh] staging Lean env -> $LOCAL_ENV ..."
cp -a "$GPFS_ENV/." "$LOCAL_ENV/" \
    || { echo "FATAL: staging copy to $LOCAL_ENV failed"; exit 1; }
echo "[p7fresh] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
export ATP_LEAN_PROJECT="$LOCAL_ENV"

echo "[p7fresh] Lean guardrail probe (cold Mathlib load ~2-3min)..."
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
print(f"[p7fresh] Lean probe OK ({time.time()-t0:.0f}s)")
PY

REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
echo "[p7fresh] serving Goedel-Prover-V2-8B @ revision=$REVISION max_model_len=$MAX_MODEL_LEN"
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
python -m vllm.entrypoints.openai.api_server \
    --model "Goedel-LM/Goedel-Prover-V2-8B" --revision "$REVISION" \
    --served-model-name "goedel-prover-v2-8b" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/p7fresh-vllm-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

echo "[p7fresh] waiting for vLLM on $HOST_IP:$PORT ..."
for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[p7fresh] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done

echo "[p7fresh] running fresh-control: config=$CONFIG trapped=$TRAPPED out=$OUT seeds=$SEEDS budget=$BUDGET"
python scripts/phase7_freshcontrol_run.py --config "$CONFIG" --trapped "$TRAPPED" --out "$OUT" \
    --seeds "$SEEDS" --budget "$BUDGET" --n-workers 8
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "FATAL: run exited $rc — see logs/p7fresh-${SLURM_JOB_ID:-local}.err"
    exit "$rc"
fi
if [ ! -f "$PROJ/$OUT/metrics.json" ]; then
    echo "FATAL: exited 0 but $PROJ/$OUT/metrics.json is missing."
    exit 1
fi
echo "[p7fresh] done; results in $PROJ/$OUT"
