#!/usr/bin/env bash
#SBATCH --job-name=atp_sweep
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:A6000:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --array=0-7%8
# CPUs/mem sized for eval.n_workers concurrent Lean REPLs (each ~1 core + ~2-4 GB, Mathlib loaded)
# PLUS the vLLM server. 2026-06-15: the cluster's free-A6000 nodes are CPU-saturated — the 8-GPU-free
# nodes (ins083/086/087) had only ~4 free cores each, so the old 16c/110G request fit NOWHERE with a
# free A6000 and the job projected a ~20h wait. Slimmed to 4c/48G (eval.n_workers=3: 3 Lean REPLs +
# vLLM on 4 cores) to fit those slivers and schedule immediately; throughput/shard drops but 8 shards
# run in parallel NOW. n_workers is a concurrency knob only — pass@B is invariant to it.
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
# Per-shard port: co-located shards (A6000 packs up to 8/node) must NOT all bind 8000 — 4 shards on
# ins087 (job 10642214) collided on 8000 -> "Engine core init failed", vLLM died. Offset by shard id.
PORT=$(( ${ATP_VLLM_PORT:-8000} + ${SLURM_ARRAY_TASK_ID:-0} ))
# Per-shard endpoint file + the env override the eval honors (resolve_endpoint_file, eval/run.py:96).
# A SHARED _vllm_endpoint.txt is clobbered by every shard (last writer wins) -> co-located shards talk
# to the wrong shard's vLLM and cross-node shards read another node's IP -> APIConnectionError. Unique
# per shard AND per array job (SLURM_ARRAY_JOB_ID) so TWO concurrent arrays (e.g. DeepSeek miniF2F +
# ProofNet#, or the two provers' Step C) with overlapping task-ids don't clobber each other's endpoint.
# Pair this with a distinct ATP_VLLM_PORT base per concurrent array so co-located shards don't bind the
# same port. Export ATP_VLLM_ENDPOINT_FILE so the eval reads THIS shard's endpoint, not the race.
ENDPOINT_FILE="$PROJ/results/_vllm_endpoint.j${SLURM_ARRAY_JOB_ID:-x}.s${SLURM_ARRAY_TASK_ID:-0}.txt"
export ATP_VLLM_ENDPOINT_FILE="$ENDPOINT_FILE"

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
# HF_HOME holds the model weights. Default = repo scratch (Goedel); a second model (DeepSeek, cached
# under ~/.hf_cache) overrides via ATP_HF_HOME so vLLM finds it without re-download.
export HF_HOME="${ATP_HF_HOME:-$PROJ/scratch/hf-cache}"
# Serve OFFLINE from the cache: weights are always pre-staged (CLAUDE.md rule 6), and some compute
# nodes can't resolve huggingface.co — vLLM's revision-check (list_repo_files) then dies at startup
# with NameResolutionError before any GPU work (10786402, and the Phase 5 pilot). Offline skips that
# network call entirely → robust + reproducible. Override with ATP_HF_OFFLINE=0 if a download is ever
# truly needed (then weights must NOT be cached-incomplete).
export HF_HUB_OFFLINE="${ATP_HF_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${ATP_HF_OFFLINE:-1}"
# elan/Lean on PATH so the ReplBackend verifier can launch the repl + resolve the toolchain sysroot.
export PATH="$HOME/.elan/bin:$PATH"
# ELAN_HOME = where Lean toolchains live. Default ~/.elan (Goedel); the DeepSeek env's toolchain was
# relocated to scratch (HOME quota), so a DeepSeek run sets ELAN_HOME to scratch/elan-deepseek.
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

# --- Stage the Lean env to node-local tmpfs (/dev/shm), PER-SHARD ----------------------------------
# `import Mathlib` opens ~4.7k oleans; off contended GPFS that timed out at 2700s (2026-06-05/06,
# sequential read measured ~3.8 MB/s). From node-local storage the same import is ~141s (faster still
# from tmpfs/RAM). A6000 nodes pack up to 8 shards of this array on ONE node. History of failures under
# that co-location:
#   2026-06-14: concurrent rm -rf + cp into a single $LOCAL_BASE/atp-lean-env -> "Directory not empty"
#               / "File exists", all 8 shards FAILED in <1min.
#   2026-06-15: flock + atomic-publish (private stage dir, mv -T publish) closed the *publish* window,
#               but REUSE shares the published inodes, so when ONE shard re-staged it yanked the files
#               out from under 4 co-located REUSING shards (job 10634722 on ins086: 3 lost the env).
#   2026-06-16a: PER-SHARD dirs ("...-sN") so no shard touches another's files. STILL failed: env -sN
#               vanished mid-run on co-located nodes. ROOT CAUSE found via /etc/slurm/epilogs/cleanup.sh:
#                   find /local -user $SLURM_JOB_UID -maxdepth 1 -exec rm -rf {} \;
#               The epilog wipes ALL of /local/$USER whenever ANY of MY jobs ends on the node — so the
#               first co-located shard to finish deletes the live envs of my other running shards. Also
#               all shards bound vLLM port 8000 -> collision -> "Engine core init failed" (now offset).
# Fix (2026-06-16b): stage to /dev/shm (tmpfs, 504G, RAM-fast) — the epilog only touches /tmp and
#   /local, never /dev/shm, so a co-located shard's exit can't wipe a running shard's env. Per-shard
#   dirs retained. Cost: 4.2G RAM/shard (<=8 -> ~34G/node of 1TB, and counts within the 64G --mem);
#   GPFS->shm is one sequential 4.2G cp/shard/wall (cheap vs the random olean opens we were avoiding).
# Lean env to stage. Default atp-lean-env (Goedel pin); a DeepSeek run sets ATP_LEAN_ENV_NAME=
# deepseek-lean-env (Lean v4.9.0 + standard mathlib). The local staged dir name follows it.
LEAN_ENV_NAME="${ATP_LEAN_ENV_NAME:-atp-lean-env}"
GPFS_ENV="$PROJ/scratch/lean-cache/$LEAN_ENV_NAME"
# /dev/shm is NOT epilog-wiped (unlike /local); fall back to /local then /tmp if shm is absent.
LOCAL_BASE="${ATP_LOCAL_BASE:-/dev/shm/$USER}"
[ -d /dev/shm ] || LOCAL_BASE="/local/$USER"; [ -d /local ] || [ -d /dev/shm ] || LOCAL_BASE="/tmp/$USER"
SHARD_ID="${SLURM_ARRAY_TASK_ID:-0}"
LOCAL_ENV="$LOCAL_BASE/${LEAN_ENV_NAME}-s${SHARD_ID}"   # PER-SHARD: never shared, never raced
mkdir -p "$LOCAL_BASE"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
REPL_REL=".lake/packages/REPL/.lake/build/bin/repl"   # the exe _env_built() requires (repl.py:258)
exec 9>"$LOCAL_BASE/.atp_stage.s${SHARD_ID}.lock"
flock 9   # only serializes a requeued duplicate of THIS shard id (normally uncontended)
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
# Reuse ONLY a provably-complete env: marker + full olean set + the repl exe. The count-only guard
# (2026-06-15) once reused a stale exe-LESS env and every cell failed LeanEnvNotReady. When invalid,
# stage to a PRIVATE temp dir and publish with an atomic rename — the .old cleanup here is safe because
# nothing else points at this shard's dir.
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ] \
   && [ -x "$LOCAL_ENV/$REPL_REL" ]; then
    echo "[sweep] Lean env already staged on $(hostname) for shard ${SHARD_ID} ($N_LOCAL oleans + repl exe) — reusing."
else
    STAGE="$LOCAL_BASE/atp-lean-env.stage.${SLURM_JOB_ID:-x}.${SHARD_ID}"
    echo "[sweep] staging Lean env (shard ${SHARD_ID}) -> $STAGE, atomic-publish -> $LOCAL_ENV (cp $N_GPFS oleans, ~3-20min off GPFS)..."
    rm -rf "$STAGE"; mkdir -p "$STAGE"
    t0=$SECONDS
    # Copy the WHOLE env dir (.lake + lakefile + manifest + toolchain + the package lib dir, whatever
    # its name) so this works for any pin — the Goedel env's lib is AtpLeanEnv/, the DeepSeek env's is
    # DeepseekLeanEnv/; enumerating a hardcoded lib name broke the DeepSeek stage.
    cp -a "$GPFS_ENV/." "$STAGE/" \
        || { echo "FATAL: staging copy to $STAGE failed"; rm -rf "$STAGE"; flock -u 9; exit 1; }
    [ -x "$STAGE/$REPL_REL" ] \
        || { echo "FATAL: staged env missing repl exe at $STAGE/$REPL_REL"; rm -rf "$STAGE"; flock -u 9; exit 1; }
    touch "$STAGE/.staged_ok"
    rm -rf "$LOCAL_ENV.old"                              # publish atomically (sub-ms vs ~250s absent)
    mv -T "$LOCAL_ENV" "$LOCAL_ENV.old" 2>/dev/null || true
    mv -T "$STAGE" "$LOCAL_ENV"
    rm -rf "$LOCAL_ENV.old"
    echo "[sweep] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean' | wc -l) oleans + repl exe)."
fi
flock -u 9; exec 9>&-
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
# Model identity is fully config-driven (hf_repo/name/revision) so a second prover (DeepSeek) serves
# from the same script — only the config + the ATP_* env (HF_HOME, lean env, ELAN_HOME) change.
HF_REPO="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.hf_repo)")"
SERVED_NAME="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.name)")"
REVISION="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.revision)")"
MAX_MODEL_LEN="$(python -c "from atp.config import load_config; print(load_config('$CONFIG').model.max_model_len)")"
echo "[sweep] serving $HF_REPO (as $SERVED_NAME) @ revision=$REVISION max_model_len=$MAX_MODEL_LEN"

# Stagger vLLM startup across co-located shards: when many shards on one node init CUDA/NVML at the
# same instant, nvmlDeviceGetHandleByIndex throws NVMLError_Unknown -> "Engine core init failed" ->
# vLLM dies during startup (a thundering herd; 15/16 ProofNet# shards died this way 2026-06-18 when the
# 16-way array launched on top of the running miniF2F array). Spread the inits by shard id (up to 8/node).
STAGGER=$(( (${SLURM_ARRAY_TASK_ID:-0} % 8) * 25 ))
[ "$STAGGER" -gt 0 ] && { echo "[sweep] staggering vLLM start by ${STAGGER}s (anti-NVML-herd)"; sleep "$STAGGER"; }

# Start vLLM in the background on this node's GPU.
HOST_IP="$(hostname -i | awk '{print $1}')"
echo "http://$HOST_IP:$PORT/v1" > "$ENDPOINT_FILE"
# OPTIONAL LoRA serving (Phase 6 FT eval): ATP_VLLM_LORA="name=/abs/adapter/dir" serves an adapter
# ALONGSIDE the base. The eval then targets it via ATP_SERVED_MODEL=name (client.py honors it); leave
# both unset for a plain base sweep (every prior phase). Additive — no effect when unset.
LORA_ARGS=()
if [ -n "${ATP_VLLM_LORA:-}" ]; then
    LORA_ARGS=(--enable-lora --lora-modules "$ATP_VLLM_LORA" --max-lora-rank "${ATP_LORA_RANK:-16}")
    echo "[sweep] LoRA serving enabled: $ATP_VLLM_LORA (max-lora-rank ${ATP_LORA_RANK:-16})"
fi
python -m vllm.entrypoints.openai.api_server \
    --model "$HF_REPO" --revision "$REVISION" \
    --served-model-name "$SERVED_NAME" "${LORA_ARGS[@]}" \
    --host 0.0.0.0 --port "$PORT" --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization 0.90 \
    > "logs/vllm-inproc-${SLURM_JOB_ID:-local}.out" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

# Wait up to ~40min: under cluster contention vLLM startup (weight load + CUDA graph capture, +LoRA)
# can exceed 20min; the old 120x10s=20min cap let the loop fall through with the PID still ALIVE (so no
# FATAL) straight into the eval, where every cell fast-failed with APIConnectionError and the run logged
# 0 cells (Phase 6 pn_B 10799548). FAIL LOUDLY if vLLM never answers, instead of running a dead sweep.
vllm_up=0
for _ in $(seq 1 240); do
    curl -sf "http://$HOST_IP:$PORT/v1/models" >/dev/null 2>&1 && { echo "[sweep] vLLM up."; vllm_up=1; break; }
    sleep 10
    kill -0 $VLLM_PID 2>/dev/null || { echo "FATAL: vLLM died during startup"; exit 1; }
done
[ "$vllm_up" = 1 ] || { echo "FATAL: vLLM did not answer on $HOST_IP:$PORT within ~40min"; exit 1; }

# NSHARDS normally = the array task COUNT (N GPUs split the cells). ATP_NSHARDS pins the stride
# denominator so a RESUME of only the failed shard indices (e.g. --array=0 after shards 1-3 finished)
# keeps the correct 1/N stride instead of collapsing to "do everything" when the sub-array count != N.
NSHARDS="${ATP_NSHARDS:-${SLURM_ARRAY_TASK_COUNT:-1}}"; SHARD="${SLURM_ARRAY_TASK_ID:-0}"
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
