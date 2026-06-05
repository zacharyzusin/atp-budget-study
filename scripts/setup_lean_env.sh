#!/usr/bin/env bash
# Acquire the Goedel-pinned Lean verification env (Lean v4.9.0-rc1 + xinhjBrant/mathlib4 fork).
#
# Strategy (per DECISIONS.md 2026-06-04 hybrid plan): try the CACHE SHORTCUT first
# (`lake exe cache get` downloads prebuilt oleans in minutes). Only if that misses do we need a
# from-source `lake build`, which belongs on a burst compute node (slurm/build_lean.sh), not here.
#
# Safe to re-run: elan/lake are idempotent. Logs everything; prints CACHE_HIT or CACHE_MISS at the end.
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
ENV_DIR="$PROJ/scratch/lean-cache/atp-lean-env"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"

echo "[setup_lean_env] $(date) host=$(hostname)"
echo "[setup_lean_env] env dir: $ENV_DIR"
cd "$ENV_DIR" || { echo "FATAL: env dir missing"; exit 1; }

TOOLCHAIN="$(cat lean-toolchain)"
echo "[setup_lean_env] installing toolchain: $TOOLCHAIN"
elan toolchain install "$TOOLCHAIN" || { echo "FATAL: toolchain install failed"; exit 1; }

echo "[setup_lean_env] lake update (resolve mathlib fork + deps, write manifest)..."
lake update 2>&1 || { echo "FATAL: lake update failed"; exit 1; }

echo "[setup_lean_env] lake exe cache get (cache shortcut)..."
# `cache get` is mathlib's olean downloader. If the fork commit's oleans aren't hosted it reports a
# miss; we detect that and DEFER the build to a compute node (never compile mathlib on a login node).
CACHE_LOG="/tmp/atp_cache_get.$$"
lake exe cache get 2>&1 | tee "$CACHE_LOG"

# Write the trivial probe lib used to confirm the env later (cheap once oleans exist).
mkdir -p AtpLeanEnv
cat > AtpLeanEnv/Probe.lean <<'EOF'
import Mathlib
theorem atp_probe_true : True := by trivial
EOF

if grep -qi 'not found in the cache\|0% success\|diverged from upstream' "$CACHE_LOG"; then
    echo "[setup_lean_env] RESULT: CACHE_MISS — fork oleans not hosted; from-source build required."
    echo "[setup_lean_env] -> submit slurm/build_lean.sh on a BURST node (do NOT build on login)."
    echo "CACHE_MISS"
elif [ "$(find . -name '*.olean' -path '*mathlib*' 2>/dev/null | wc -l)" -gt 1000 ]; then
    echo "[setup_lean_env] RESULT: CACHE_HIT (Mathlib oleans downloaded; env ready)."
    echo "CACHE_HIT"
else
    echo "[setup_lean_env] RESULT: UNKNOWN — inspect $CACHE_LOG; do not build on login."
    echo "UNKNOWN"
fi
echo "[setup_lean_env] done $(date)"
