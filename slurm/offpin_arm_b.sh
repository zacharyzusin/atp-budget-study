#!/usr/bin/env bash
#SBATCH --job-name=offpin_armB
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --time=08:00:00
#SBATCH --requeue
#SBATCH --output=logs/offpin_armB-%j.out
#SBATCH --error=logs/offpin_armB-%j.err
#
# Off-pin Arm B: a REAL hammer (duper@v4.29.0, version-matched to the env) on trapped ProofNet#
# STATEMENTS. Stages the sibling v4.29.0 lean_env to an ISOLATED node-local copy (does NOT touch the
# shared GPFS env), adds + builds Duper there, then runs the Pantograph Arm-B runner under the sibling
# venv. This is the decisive real-hammer test the reviewer required before locking NO-GO.
set -uo pipefail
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

SIB="/insomnia001/depts/edu/COMS-E6998-012/$USER/theorem-proving-research"
ATP="/insomnia001/depts/edu/COMS-E6998-012/$USER/atp-budget-study"
GPFS_ENV="$SIB/lean_env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
ENV="$LOCAL_BASE/lean_env_duper"
mkdir -p "$LOCAL_BASE"
export XDG_CACHE_HOME="$SIB/.xdg_cache"
export ELAN_NO_AUTO_INSTALL=1
export PATH="$HOME/.elan/bin:$PATH"

# --- stage isolated copy ---
echo "[armB] staging isolated lean_env copy -> $ENV ..."
rm -rf "$ENV"; mkdir -p "$ENV"; t0=$SECONDS
cp -a "$GPFS_ENV/." "$ENV/" || { echo "FATAL: staging cp failed"; exit 1; }
echo "[armB] staged in $((SECONDS-t0))s ($(find "$ENV/.lake" -name '*.olean'|wc -l) oleans)."

# --- add + build Duper (version-matched v4.29.0) ---
cd "$ENV"
if ! grep -q "Duper" lakefile.lean; then
  cat >> lakefile.lean <<'LK'

require Duper from git
  "https://github.com/leanprover-community/duper.git" @ "v4.29.0"
LK
fi
echo "[armB] lake update Duper (network; clones duper)..."
lake update Duper 2>&1 | tail -8
echo "[armB] lake build Duper (deps prebuilt; duper compiles)..."
lake build Duper 2>&1 | tail -15
echo "[armB] Duper build rc=$?; duper oleans: $(find .lake/packages/duper -name '*.olean' 2>/dev/null | wc -l)"

# --- sorry-rejection / sanity: confirm duper is importable + closes a trivial goal ---
echo "[armB] running Arm-B Pantograph runner under sibling venv..."
source "$SIB/venv/bin/activate"
cd "$ATP"
python scripts/hammer_arm_b_pantograph.py \
  --statements scratch/phase3/trapped_proofnet_statements.json \
  --project "$ENV" \
  --out results/phase3/arm_b_duper_goedel_proofnet.json \
  --tactic duper --timeout 90 ${ARM_B_LIMIT:+--limit $ARM_B_LIMIT}
rc=$?
echo "[armB] done (rc=$rc)"
exit $rc
