#!/usr/bin/env bash
#SBATCH --job-name=p7_tactic
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --output=logs/p7tac-%j.out
#SBATCH --error=logs/p7tac-%j.err
#
# Phase 7 Track 1 — Mode 4 (true stepwise, one tactic per call) real eval. The strong
# exposure-bias disambiguator vs Mode 3's whole-continuation re-grounding (see
# scripts/phase7_tactic_run.py's module docstring). Reuses slurm/sweep.sh's proven Lean-staging +
# vLLM-serve blocks verbatim; adds a Format-E pre-flight smoke (rule 5: smoke before scale) before
# spending the real run's GPU — confirms the base model emits a USABLE single tactic given the
# TacticTemplate goal-state prompt, since Mode 4 has never been format-validated live before this.
#
# Usage: sbatch slurm/phase7_tactic_run.sh <config> <trapped_file> <out_dir> [seeds] [budget] [max_steps] [retries_per_step] [beam_width]
#   sbatch slurm/phase7_tactic_run.sh configs/proofnet_baseline.yaml \
#       scratch/phase7/mode3_engaged_goedel_proofnet.txt results/phase7/goedel_proofnet_mode4 0 32000 40 4 3
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${1:?need config}"
TRAPPED="${2:?need trapped file}"
OUT="${3:?need out dir}"
SEEDS="${4:-0}"
BUDGET="${5:-32000}"
MAX_STEPS="${6:-40}"
RETRIES_PER_STEP="${7:-4}"
BEAM_WIDTH="${8:-3}"
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
    echo "[p7tac] conda activate/import atp failed (attempt $attempt) — retrying in 5s..."
    sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV"; exit 1; }
echo "[p7tac] env OK: python=$(command -v python)"
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
    echo "[p7tac] Lean env already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    echo "[p7tac] staging Lean env -> $LOCAL_ENV (cp $N_GPFS oleans)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy to $LOCAL_ENV failed"; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[p7tac] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

echo "[p7tac] Lean guardrail probe (cold Mathlib load ~2-3min)..."
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
print(f"[p7tac] Lean probe OK ({time.time()-t0:.0f}s)")
PY

HF_REPO="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.hf_repo)")"
SERVED_NAME="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.name)")"
REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
echo "[p7tac] serving $HF_REPO (as $SERVED_NAME) @ revision=$REVISION max_model_len=$MAX_MODEL_LEN"
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
python -m vllm.entrypoints.openai.api_server \
    --model "$HF_REPO" --revision "$REVISION" \
    --served-model-name "$SERVED_NAME" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/p7tac-vllm-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

echo "[p7tac] waiting for vLLM on $HOST_IP:$PORT ..."
for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[p7tac] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done

# --- Format pre-flight guard (rule 5: smoke before scale) ------------------------------------------
# Mode 4 has burned real GPU on a bad format before (Goedel, 2026-07-05: 0/19 with every cell stuck
# at step 0, because a reasoning model doesn't answer with a bare tactic — see DECISIONS.md). This
# guard is model-agnostic: uses whatever `config.model.prompt_template` selects
# (`atp.models.templates.template_from_config`), and validates the extracted candidate the SAME way
# the real agent will — via `elaborate` (does it advance to a legal next state?), not a
# model-specific markdown heuristic. A real acceptance here means format + Lean pin both check out.
echo "[p7tac] Format pre-flight guard..."
python - "$CONFIG" "$HOST_IP" "$PORT" <<'PY' || { echo "FATAL: Format guard failed — refusing to spend GPU."; exit 1; }
import sys
from atp.config import load_config
from atp.models.client import OpenAITransport, VLLMClient
from atp.models.templates import candidate_tactic_lines, template_from_config
from atp.lean.backends import Theorem
from atp.lean.repl import ReplBackend
from atp.budget.meter import BudgetMeter

config_path, host, port = sys.argv[1], sys.argv[2], sys.argv[3]
config = load_config(config_path)
transport = OpenAITransport(base_url=f"http://{host}:{port}/v1", timeout_s=120, max_retries=2)
client = VLLMClient.from_config(config, transport, BudgetMeter(limit=10_000))
template = template_from_config(config)
thm = Theorem(
    name="probe",
    statement=(
        "theorem probe {G : Type*} [Group G] [Fintype G] (hG : Fintype.card G = 224) : "
        "¬ IsSimpleGroup G"
    ),
)
state = "G : Type u_1\ninst : Group G\ninst : Fintype G\nhG : Fintype.card G = 224\n⊢ ¬ IsSimpleGroup G"
prompt = template.render(thm, state=state, prev_tactics=())
backend = ReplBackend(config)
accepted = None
# Retry across FRESH samples (temperature > 0 means one bad sample is sampling variance, not a
# format problem) — mirrors the real agent's own retries_per_step, so the guard's pass/fail
# threshold matches what the real run will actually tolerate.
for attempt in range(4):
    completion = client.generate(prompt, max_tokens=768, label="format_guard")
    print(f"[p7tac] guard attempt {attempt}: {completion.text[:200]!r}")
    for cand in candidate_tactic_lines(completion.text):
        src = f"{thm.statement.rstrip()} := by\n  {cand}\n  sorry"
        resp = backend.elaborate(thm, src)
        if (not resp["infra_error"]) and resp["errors"] == 0:
            accepted = cand
            break
    if accepted is not None:
        break
backend.close()
print(f"[p7tac] guard accepted: {accepted!r}")
assert accepted is not None, "no candidate elaborated cleanly across 4 fresh samples"
print("[p7tac] Format guard OK")
PY

echo "[p7tac] running Mode 4: config=$CONFIG trapped=$TRAPPED out=$OUT seeds=$SEEDS budget=$BUDGET max_steps=$MAX_STEPS retries=$RETRIES_PER_STEP beam_width=$BEAM_WIDTH"
python scripts/phase7_tactic_run.py --config "$CONFIG" --trapped "$TRAPPED" --out "$OUT" \
    --seeds "$SEEDS" --budget "$BUDGET" --max-steps "$MAX_STEPS" --retries-per-step "$RETRIES_PER_STEP" \
    --beam-width "$BEAM_WIDTH" --n-workers 8
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "FATAL: run exited $rc — see logs/p7tac-${SLURM_JOB_ID:-local}.err"
    exit "$rc"
fi
if [ ! -f "$PROJ/$OUT/metrics.json" ]; then
    echo "FATAL: exited 0 but $PROJ/$OUT/metrics.json is missing."
    exit 1
fi
echo "[p7tac] done; results in $PROJ/$OUT"
