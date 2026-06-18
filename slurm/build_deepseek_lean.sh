#!/usr/bin/env bash
#SBATCH --job-name=ds_build_lean
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=05:55:00
#SBATCH --requeue
#SBATCH --output=logs/build_deepseek_lean-%j.out
#SBATCH --error=logs/build_deepseek_lean-%j.err
#
# Stand up DeepSeek-Prover-V2's authoritative Lean env (Phase 2 Step B): Lean v4.9.0 + STANDARD
# mathlib4 @ f0957a757531 (the sole v4.9.0-final commit) + leanprover-community/repl @ bump_to_v4.9.0.
# Unlike the Goedel fork (cache MISS → multi-hour from-source build), STANDARD mathlib oleans ARE
# hosted, so `lake exe cache get` should HIT in minutes. If it MISSES we fall back to `lake build`
# (incremental, restartable on requeue) — that's why this asks for 16 cpus / ~6h, not a login node.
# CPU-only (no --gres). Compute nodes have direct internet; strip the per-session SSH proxy that
# Slurm jobs inherit (it breaks all downloads).
set -uo pipefail
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
ENV_DIR="$PROJ/scratch/lean-cache/deepseek-lean-env"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"

echo "[ds_build] $(date) host=$(hostname) job=${SLURM_JOB_ID:-none} cpus=${SLURM_CPUS_PER_TASK:-?}"
cd "$ENV_DIR" || { echo "FATAL: $ENV_DIR missing"; exit 1; }
TOOLCHAIN="$(cat lean-toolchain)"
echo "[ds_build] toolchain: $TOOLCHAIN"
elan toolchain install "$TOOLCHAIN" || { echo "FATAL: toolchain install failed"; exit 1; }

echo "[ds_build] lake update (resolve standard mathlib f0957a7 + REPL bump_to_v4.9.0)..."
lake update 2>&1 || { echo "FATAL: lake update failed"; exit 1; }

# Confirm the manifest pinned what we asked for (guard against a moved branch / wrong resolve).
echo "[ds_build] resolved deps:"
python3 - <<'PY' 2>/dev/null || true
import json
d=json.load(open("lake-manifest.json"))
for p in d["packages"]:
    if p["name"].lower() in ("mathlib","repl"):
        print(f"   {p['name']:8s} {p.get('url')}  rev={p.get('rev')}  inputRev={p.get('inputRev')}")
PY

echo "[ds_build] lake exe cache get (STANDARD mathlib → expect HIT)..."
CACHE_LOG="/tmp/ds_cache_get.$$"
lake exe cache get 2>&1 | tee "$CACHE_LOG"

N_OLEAN=$(find .lake -name '*.olean' -path '*[Mm]athlib*' 2>/dev/null | wc -l)
if [ "$N_OLEAN" -gt 1000 ]; then
    echo "[ds_build] CACHE_HIT — $N_OLEAN mathlib oleans present."
else
    echo "[ds_build] CACHE_MISS/partial ($N_OLEAN oleans) — building Mathlib from source (incremental)..."
    lake build Mathlib || { echo "FATAL: lake build Mathlib failed (requeue resumes)"; exit 1; }
    N_OLEAN=$(find .lake -name '*.olean' -path '*[Mm]athlib*' 2>/dev/null | wc -l)
fi

echo "[ds_build] building the verification REPL (leanprover-community/repl @ bump_to_v4.9.0)..."
( cd "$ENV_DIR/.lake/packages/REPL" && lake build repl ) || { echo "FATAL: repl build failed"; exit 1; }
REPL_BIN="$ENV_DIR/.lake/packages/REPL/.lake/build/bin/repl"
[ -x "$REPL_BIN" ] || { echo "FATAL: repl exe missing at $REPL_BIN"; exit 1; }

echo "[ds_build] building the probe (import Mathlib + norm_num) to confirm the env elaborates..."
lake build DeepseekLeanEnv.Probe || { echo "FATAL: probe build failed (env not usable)"; exit 1; }

N_TOTAL=$(find .lake -name '*.olean' | wc -l)
echo "[ds_build] DONE $(date) — mathlib_oleans=$N_OLEAN total_oleans=$N_TOTAL"
printf 'deepseek-pin ready: %s\nlean v4.9.0 + leanprover-community/mathlib4@f0957a7575317490107578ebaee9efaf8e62a4ab\nrepl: leanprover-community/repl@bump_to_v4.9.0 -> %s\nmathlib_oleans=%s total_oleans=%s\n' \
    "$(date -Is)" "$REPL_BIN" "$N_OLEAN" "$N_TOTAL" > "$PROJ/results/_deepseek_lean_env_ready.txt"
echo "[ds_build] wrote results/_deepseek_lean_env_ready.txt"
