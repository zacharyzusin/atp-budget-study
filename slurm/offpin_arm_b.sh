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
# Off-pin Arm B: REAL hammer (duper@v4.29.0) on trapped ProofNet# STATEMENTS. Stages the ISOLATED
# duper-enabled env copy (scratch/lean-cache/lean_env_duper, already `lake update`d on login so duper+
# auto sources are present — batteries matches the env exactly so mathlib is NOT rebuilt) to node-local
# SSD, runs `lake build Duper` offline (no network on compute), computes LEAN_PATH from the filesystem,
# then runs the Pantograph Arm-B runner under the sibling venv. Does NOT touch the shared lean_env.
set -uo pipefail
# NB: do NOT unset proxy here — but no network is needed (deps pre-cloned on login); lake build is offline.

SIB="/insomnia001/depts/edu/COMS-E6998-012/$USER/theorem-proving-research"
ATP="/insomnia001/depts/edu/COMS-E6998-012/$USER/atp-budget-study"
ISO="$ATP/scratch/lean-cache/lean_env_duper"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
ENV="$LOCAL_BASE/lean_env_duper"
mkdir -p "$LOCAL_BASE"
export XDG_CACHE_HOME="$SIB/.xdg_cache"
export ELAN_NO_AUTO_INSTALL=1
export PATH="$HOME/.elan/bin:$PATH"

[ -d "$ISO/.lake/packages/Duper" ] || { echo "FATAL: $ISO has no duper package — run the login lake-update step first"; exit 1; }

echo "[armB] staging isolated duper env -> $ENV ..."
rm -rf "$ENV"; mkdir -p "$ENV"; t0=$SECONDS
cp -a "$ISO/." "$ENV/" || { echo "FATAL staging"; exit 1; }
echo "[armB] staged in $((SECONDS-t0))s."

cd "$ENV"
echo "[armB] lake build Duper (offline; deps pre-cloned; batteries/mathlib reused)..."
lake build Duper 2>&1 | tail -20
echo "[armB] duper oleans: $(find .lake/packages/Duper -name '*.olean' 2>/dev/null | wc -l) ; auto oleans: $(find .lake/packages/auto -name '*.olean' 2>/dev/null | wc -l)"

# --- compute LEAN_PATH from filesystem (toolchain stdlib + every package lib + project lib) ---
TC="$(cat lean-toolchain | tr '/:' '--' | sed 's/--lean4/--lean4--/' )"  # leanprover/lean4:v4.29.0 -> leanprover--lean4---v4.29.0
TCDIR="$HOME/.elan/toolchains/$(cat lean-toolchain | sed 's#/#--#; s#:#---#')/lib/lean"
LP="$TCDIR"
for p in "$ENV"/.lake/packages/*/.lake/build/lib/lean; do [ -d "$p" ] && LP="$LP:$p"; done
[ -d "$ENV/.lake/build/lib/lean" ] && LP="$LP:$ENV/.lake/build/lib/lean"
export LEAN_PATH="$LP"
echo "[armB] LEAN_PATH set (${LEAN_PATH:0:120}...) ; entries=$(echo $LEAN_PATH | tr ':' '\n' | wc -l)"

echo "[armB] running Arm-B Pantograph runner under sibling venv..."
source "$SIB/venv/bin/activate"
cd "$ATP"
python scripts/hammer_arm_b_pantograph.py \
  --statements scratch/phase3/trapped_proofnet_statements.json \
  --project "$ENV" \
  --out "${ARM_B_OUT:-results/phase3/arm_b_duper_goedel_proofnet.json}" \
  --tactic "${ARM_B_TACTIC:-duper}" --timeout "${ARM_B_TIMEOUT:-90}" ${ARM_B_LIMIT:+--limit $ARM_B_LIMIT}
rc=$?
echo "[armB] done (rc=$rc)"
exit $rc
