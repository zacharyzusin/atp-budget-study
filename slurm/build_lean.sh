#!/usr/bin/env bash
#SBATCH --job-name=atp_build_lean
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=11:55:00
#SBATCH --requeue
#SBATCH --output=logs/build_lean-%j.out
#SBATCH --error=logs/build_lean-%j.err
#
# From-source build of the Goedel-pinned Mathlib (Lean v4.9.0-rc1 + xinhjBrant/mathlib4@2f65ba7).
# Required because `lake exe cache get` MISSED (fork oleans not hosted) — see DECISIONS.md.
# CPU-only (no --gres): building Lean/Mathlib is a CPU+RAM job, not a GPU one.
#
# Restartable (rule 0.3): `lake build` is incremental — a requeue resumes from the oleans already on
# disk in scratch/lean-cache, so a preempt doesn't restart the multi-thousand-module build from zero.
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
ENV_DIR="$PROJ/scratch/lean-cache/atp-lean-env"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"

echo "[build_lean] $(date) host=$(hostname) job=${SLURM_JOB_ID:-none} cpus=${SLURM_CPUS_PER_TASK:-?}"
cd "$ENV_DIR" || { echo "FATAL: $ENV_DIR missing (run scripts/setup_lean_env.sh first)"; exit 1; }
echo "[build_lean] toolchain: $(cat lean-toolchain)"

# This lake (v4.9.0-rc1) has no jobs flag; it parallelizes across all visible cores by default,
# so the --cpus-per-task=32 allocation sets the build width.
echo "[build_lean] building full Mathlib from source (this is the multi-hour step)..."
lake build Mathlib
RC=$?
if [ $RC -ne 0 ]; then
    echo "[build_lean] lake build Mathlib FAILED (rc=$RC). Requeue/resume will continue incrementally."
    exit $RC
fi

echo "[build_lean] Mathlib built. Confirming with the trivial probe (AtpLeanEnv.Probe)..."
lake build AtpLeanEnv.Probe || { echo "FATAL: probe build failed"; exit 1; }

# Build the version-matched verification REPL (leanprover-community/repl, vendored as a dep package).
# This is the Goedel-pin verification backend (DECISIONS.md 2026-06-05, supersedes PyPantograph).
# Cheap (~1 min): depends only on Lean core, not Mathlib. Produces .lake/packages/REPL/.lake/build/bin/repl.
echo "[build_lean] building the repl exe (leanprover-community/repl @ v4.9.0-rc1)..."
( cd "$ENV_DIR/.lake/packages/REPL" && lake build repl ) || { echo "FATAL: repl build failed"; exit 1; }
REPL_BIN="$ENV_DIR/.lake/packages/REPL/.lake/build/bin/repl"
[ -x "$REPL_BIN" ] || { echo "FATAL: repl exe missing at $REPL_BIN"; exit 1; }
echo "[build_lean] repl exe ready: $REPL_BIN"

OLEANS=$(find .lake -name '*.olean' | wc -l)
echo "[build_lean] DONE $(date) — $OLEANS oleans present."
# Marker the rest of the harness can check for env readiness.
printf 'goedel-pin ready: %s\nlean v4.9.0-rc1 + xinhjBrant/mathlib4@2f65ba7\noleans=%s\nrepl: %s\n' \
    "$(date -Is)" "$OLEANS" "$REPL_BIN" > "$PROJ/results/_lean_env_ready.txt"
echo "[build_lean] wrote results/_lean_env_ready.txt"
