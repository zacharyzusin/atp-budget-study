#!/usr/bin/env bash
#SBATCH --job-name=atp_sweep
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --array=0-7%8
# CPUs/mem sized for eval.n_workers concurrent Lean REPLs (each ~1 core + ~2-4 GB, Mathlib loaded)
# PLUS the vLLM server. 16c/110G comfortably covers n_workers=8. n_workers=1 (smoke) underuses it.
#SBATCH --output=logs/sweep-%A_%a.out
#SBATCH --error=logs/sweep-%A_%a.err
#
# SHARDED baseline eval: same per-task setup as sweep.sh (vLLM + Lean stage + probe) but each array
# task proves a DISJOINT stride of the (seed,problem) cells (--num-shards = SLURM_ARRAY_TASK_COUNT,
# --shard-id = SLURM_ARRAY_TASK_ID) into the SAME shared run dir, so N GPUs split the problem set and
# the 128k baseline finishes in ~1 wall instead of ~6. Cells are file-keyed → shards never collide;
# the union == the unsharded set. Shards write per-cell JSONs ONLY; run `atp sweep --aggregate` once
# all cells exist to write metrics.json (the watcher does this). --array=0-7 == 8 shards; %8 lets all
# 8 run at once. SAME total GPU-h as the serial run — this is parallelism, not extra spend.
#
# Usage:  sbatch slurm/sweep_array.sh configs/proofnet_baseline.yaml [run_name]
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${1:-configs/phase0_baseline.yaml}"
RUN_NAME="${2:-baseline}"
PORT="${ATP_VLLM_PORT:-8000}"
ENDPOINT_FILE="$PROJ/results/_vllm_endpoint.txt"

# Insomnia proxy trap: Slurm jobs inherit a per-session SSH proxy that breaks ALL downloads
# (model weights etc.). Unset before any network. (See reference_insomnia_compute_proxy.)
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

module load anaconda/2023.09
# `conda activate` needs the shell hook sourced in a non-interactive batch shell (else it errors
# "invalid choice: activate" and atp isn't importable). With `set -uo pipefail` (no -e) a silent
# activation failure under GPFS load falls through to the base python — which made smoke 10260159
# die at the Lean probe with "No module named 'atp'" only AFTER a 1022s stage. Verify+retry HERE so
# a bad activation aborts in seconds, before any expensive work. (See PROGRESS.md 2026-06-06.)
ATP_ENV="$PROJ/scratch/conda-envs/atp"
activate_env() {
    local base; base="$(conda info --base 2>/dev/null)"
    [ -n "$base" ] && [ -f "$base/etc/profile.d/conda.sh" ] || return 1
    set +u  # conda's activate scripts reference unset vars; nounset trips them on some nodes
    source "$base/etc/profile.d/conda.sh"
    conda activate "$ATP_ENV" 2>/dev/null
    set -u
    # On some nodes `conda activate` returns 0 WITHOUT switching python (observed ins095, and the
    # cause of smoke 10260159's "No module named 'atp'"). Force the env bin onto PATH so python +
    # console scripts resolve to the env unconditionally, regardless of conda's activation quirk.
    export PATH="$ATP_ENV/bin:$PATH"; export CONDA_PREFIX="$ATP_ENV"
    hash -r 2>/dev/null || true   # drop any cached `python` path from the base shell
    [ "$(command -v python)" = "$ATP_ENV/bin/python" ] || return 1
    python -c "import atp" 2>/dev/null || return 1
}
ok=0
for attempt in 1 2 3; do
    if activate_env; then ok=1; break; fi
    echo "[sweep] conda activate/import atp failed (attempt $attempt) — retrying in 5s..."
    sleep 5
done
if [ "$ok" != 1 ]; then
    echo "FATAL: could not activate $ATP_ENV with importable atp after 3 tries."
    echo "  conda base: $(conda info --base 2>/dev/null)"
    echo "  which python: $(command -v python)"
    exit 1
fi
echo "[sweep] env OK: python=$(command -v python)"
export HF_HOME="$PROJ/scratch/hf-cache"
# elan/Lean on PATH so the ReplBackend verifier can launch the repl + resolve the toolchain sysroot.
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
# One-time cold `import Mathlib` reads ~4.7k oleans off GPFS; under contention this measured 869s on
# 2026-06-05, so give a generous ceiling (it's paid once per sweep; per-proof timeout is separate).
export ATP_IMPORT_TIMEOUT_S="${ATP_IMPORT_TIMEOUT_S:-2700}"
cd "$PROJ"

# Confirm the Goedel-pin Lean env is built (guardrail: reported numbers require it).
if [ ! -f "$PROJ/results/_lean_env_ready.txt" ]; then
    echo "FATAL: Goedel-pin Lean env not built (no results/_lean_env_ready.txt). Run slurm/build_lean.sh."
    exit 1
fi

# --- Stage the Lean env to node-local SSD (the cold-load fix) -------------------------------------
# `import Mathlib` opens ~4.7k oleans; off contended GPFS that timed out at 2700s (2026-06-05/06,
# sequential read measured ~3.8 MB/s). From node-local disk the same import is ~141s and can't be
# throttled by GPFS token contention. We copy the env once per node (sequential ~10-20min, bounded),
# then point ReplBackend at the local copy via ATP_LEAN_PROJECT. The REPL pickle is only a ~1KB olean
# index (lazy mmap), so it must live next to LOCAL oleans — which it does once project_path is local.
GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[sweep] Lean env already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    echo "[sweep] staging Lean env -> $LOCAL_ENV (cp $N_GPFS oleans, ~10-20min off GPFS)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"
    t0=$SECONDS
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/" \
        || { echo "FATAL: staging copy to $LOCAL_ENV failed"; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[sweep] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans)."
fi
export ATP_LEAN_PROJECT="$LOCAL_ENV"

# GUARDRAIL probe: confirm the Lean env accepts a trivial-true proof AND rejects a false one BEFORE
# spending GPU. A silent env regression (empty LEAN_PATH / wrong sysroot / repl flush bug) makes every
# proof fail and would masquerade as a low pass@B. Also warms the page cache for the sweep.
echo "[sweep] Lean trivial-true/false probe (cold Mathlib load from local SSD ~2-3min)..."
python - "$CONFIG" <<'PY' || { echo "FATAL: Lean probe failed — env broken, refusing to spend GPU."; exit 1; }
import sys, time
from atp.config import load_config
from atp.lean import ReplBackend, Verifier, Theorem
cfg = load_config(sys.argv[1])
v = Verifier.from_config(cfg, ReplBackend(cfg))
t0 = time.time()
ok = v.verify(Theorem(name="probe", statement="theorem probe : True"),
              "theorem probe : True := by\n  trivial")
print(f"[sweep] import Mathlib + first verify took {time.time()-t0:.0f}s")
# A norm_num proof is the canary: an env restored from a broken pickle ABORTS the Lean process here
# (cannot evaluate the @[init] normNumExt) — exactly the failure that scored the smoke 0. `trivial`
# alone never exercises a compiled meta extension, so it can't catch it. (DECISIONS 2026-06-06.)
nn = v.verify(Theorem(name="nn", statement="theorem nn : (2:Nat)+2=4"),
              "theorem nn : (2:Nat) + 2 = 4 := by\n  norm_num")
bad = v.verify(Theorem(name="bad", statement="theorem bad : (1:Nat)=2"),
               "theorem bad : (1:Nat) = 2 := by\n  rfl")
assert ok.ok, f"trivial-true rejected: {ok.feedback}"
assert nn.ok, f"norm_num proof rejected (broken env?): {nn.reason} / {nn.feedback}"
assert (not bad.ok) and bad.reason == "compile_error", f"false-proof not rejected: {bad.reason}"
print("[sweep] Lean probe OK (true + norm_num accepted, false rejected)")
PY

# Pin the served weights to the exact reviewed revision (reproducibility rule 4).
REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
echo "[sweep] serving Goedel-Prover-V2-8B @ revision=$REVISION max_model_len=$MAX_MODEL_LEN"

# Start vLLM in the background on this node's GPU.
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
python -m vllm.entrypoints.openai.api_server \
    --model "Goedel-LM/Goedel-Prover-V2-8B" --revision "$REVISION" \
    --served-model-name "goedel-prover-v2-8b" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/vllm-inproc-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

echo "[sweep] waiting for vLLM to come up on $HOST_IP:$PORT ..."
for _ in $(seq 1 120); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[sweep] vLLM up."; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done

NSHARDS="${SLURM_ARRAY_TASK_COUNT:-1}"; SHARD="${SLURM_ARRAY_TASK_ID:-0}"
echo "[sweep] running eval: config=$CONFIG name=$RUN_NAME shard=$SHARD/$NSHARDS"
# `set -uo pipefail` (no -e) means a CRASHED sweep would otherwise fall through to the success echo
# and exit 0 — exactly how baseline 10272937 logged COMPLETED after dying at 165 cells with no
# metrics.json. Capture the exit code and fail LOUDLY (non-zero) so Slurm shows FAILED, not COMPLETED.
python -m atp.cli sweep --config "$CONFIG" --name "$RUN_NAME" --resume \
    --num-shards "$NSHARDS" --shard-id "$SHARD"
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "FATAL: sweep shard $SHARD exited $rc — see logs/sweep-${SLURM_ARRAY_JOB_ID}_${SHARD}.err"
    exit "$rc"
fi
# A shard writes per-cell JSONs only (no metrics.json — that's the aggregate step's job once ALL
# shards finish; the watcher runs `atp sweep --aggregate`). So DON'T gate on metrics.json here.
echo "[sweep] shard $SHARD/$NSHARDS done; cells in $PROJ/results/$RUN_NAME/problems"
