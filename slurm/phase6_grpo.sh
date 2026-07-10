#!/usr/bin/env bash
#SBATCH --job-name=p6grpo
#SBATCH --account=edu
#SBATCH --partition=burst
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --output=logs/grpo-%j.out
#SBATCH --error=logs/grpo-%j.err
#
# Stage C GRPO RL probe (STAGE_C_PROBE_SPEC.md). Trains the DeepSeek policy on the H100 with HF
# generate (no vLLM server); the reward is Lean-in-the-loop, so the DeepSeek Lean env is staged
# node-local (/dev/shm) exactly like the eval sweep and the trainer's reward pool verifies against it.
# Restartable (rule 3): GRPOTrainer checkpoints every --save-steps; a requeue resumes.
#
# Usage:  sbatch slurm/phase6_grpo.sh <train.jsonl> <out_dir> [extra phase6_grpo.py flags...]
#   sbatch slurm/phase6_grpo.sh scratch/phase6/grpo/deepseek/train.jsonl scratch/phase6/grpo/deepseek/smoke --max-steps 3   # §0(c) smoke
#   sbatch slurm/phase6_grpo.sh scratch/phase6/grpo/deepseek/train.jsonl scratch/phase6/grpo/deepseek/ckpt  --max-steps 150 # probe
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
TRAIN="${1:?need train.jsonl}"; OUT="${2:?need out dir}"; shift 2
EXTRA=("$@")
CONFIG="${ATP_GRPO_CONFIG:-configs/phase6_grpo_deepseek.yaml}"

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
ok=0; for a in 1 2 3; do activate_env && { ok=1; break; }; echo "[grpo] activate retry $a"; sleep 5; done
[ "$ok" = 1 ] || { echo "FATAL: cannot activate $ATP_ENV"; exit 1; }
echo "[grpo] env OK: python=$(command -v python)"
cd "$PROJ"

# DeepSeek-specific caches + relocated Lean toolchain (matches scripts/phase6_launch_eval.sh d).
export HF_HOME="${ATP_HF_HOME:-/insomnia001/depts/edu/COMS-E6998-012/zwz2000/.hf_cache}"
export ELAN_HOME="${ELAN_HOME:-$PROJ/scratch/elan-deepseek}"
export PATH="$ELAN_HOME/bin:$PATH"
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
# GRPO holds a big KV cache during the generation phase, then frees it before the training
# forward/backward — leaving fragmented "reserved but unallocated" segments the default allocator
# can't reuse for the next big contiguous alloc (smoke 11061509 OOM'd with 35 GiB reserved-free on
# an 80 GiB H100). expandable_segments lets the allocator grow/reuse those segments -> real ~59 GiB
# peak fits. Zero effect on training semantics.
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
LEAN_ENV_NAME="${ATP_LEAN_ENV_NAME:-deepseek-lean-env}"

# --- Stage the DeepSeek Lean env to node-local /dev/shm (cold-load fix; reward pool needs it) ------
GPFS_ENV="$PROJ/scratch/lean-cache/$LEAN_ENV_NAME"
LOCAL_BASE="${ATP_LOCAL_BASE:-/dev/shm/$USER}"; [ -d /dev/shm ] || LOCAL_BASE="/local/$USER"
LOCAL_ENV="$LOCAL_BASE/${LEAN_ENV_NAME}-grpo${SLURM_JOB_ID:-local}"
REPL_REL=".lake/packages/REPL/.lake/build/bin/repl"
mkdir -p "$LOCAL_BASE"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ] && [ -x "$LOCAL_ENV/$REPL_REL" ]; then
    echo "[grpo] Lean env already staged ($N_LOCAL oleans) — reusing."
else
    echo "[grpo] staging Lean env -> $LOCAL_ENV (cp $N_GPFS oleans)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
    cp -a "$GPFS_ENV/." "$LOCAL_ENV/" || { echo "FATAL: staging copy failed"; exit 1; }
    [ -x "$LOCAL_ENV/$REPL_REL" ] || { echo "FATAL: staged env missing repl exe"; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[grpo] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

# GUARDRAIL probe: env accepts a true + norm_num proof and rejects a false one BEFORE spending GPU.
echo "[grpo] Lean probe (cold Mathlib load ~2-3min)..."
python - "$CONFIG" <<'PY' || { echo "FATAL: Lean probe failed — refusing to spend GPU."; exit 1; }
import sys, time
from atp.config import load_config
from atp.lean import ReplBackend, Verifier, Theorem
cfg = load_config(sys.argv[1]); v = Verifier.from_config(cfg, ReplBackend(cfg)); t0=time.time()
ok = v.verify(Theorem(name="probe", statement="theorem probe : True"), "theorem probe : True := by\n  trivial")
print(f"[grpo] import Mathlib + first verify {time.time()-t0:.0f}s")
nn = v.verify(Theorem(name="nn", statement="theorem nn : (2:Nat)+2=4"), "theorem nn : (2:Nat) + 2 = 4 := by\n  norm_num")
bad = v.verify(Theorem(name="bad", statement="theorem bad : (1:Nat)=2"), "theorem bad : (1:Nat) = 2 := by\n  rfl")
assert ok.ok and nn.ok and (not bad.ok), f"probe bad: true={ok.reason} nn={nn.reason} false={bad.reason}"
print("[grpo] Lean probe OK")
PY

echo "[grpo] training: config=$CONFIG train=$TRAIN out=$OUT extra=${EXTRA[*]}"
python scripts/phase6_grpo.py --config "$CONFIG" --train "$TRAIN" --out "$OUT" "${EXTRA[@]}"
rc=$?
[ "$rc" -ne 0 ] && { echo "FATAL: grpo exited $rc"; exit "$rc"; }
[ -f "$OUT/atp_grpo_manifest.json" ] || { echo "FATAL: exited 0 but no manifest in $OUT"; exit 1; }
echo "[grpo] done -> $OUT"
