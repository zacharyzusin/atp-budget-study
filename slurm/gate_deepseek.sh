#!/usr/bin/env bash
#SBATCH --job-name=ds_gate
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=03:55:00
#SBATCH --requeue
#SBATCH --output=logs/gate_deepseek-%j.out
#SBATCH --error=logs/gate_deepseek-%j.err
#
# Phase 2 Step B pre-GPU gates against the DeepSeek env (Lean v4.9.0 + standard mathlib @ f0957a7).
# Runs on a COMPUTE node with the env staged to node-local /dev/shm — reading 4.7k Mathlib oleans from
# GPFS per import is the open-storm (>2700s); staged-local it is ~100s (see reference_lean_repl_cluster).
# Three gates, all zero-GPU:
#   G3 contract tests (-m lean): the verifier+REPL wiring + sorry/admit/native_decide rejection in env #2
#   G2 validate_statements: miniF2F + ProofNet# heads elaborate on this pin -> compile-on-both intersection
#   G1 verify DeepSeek's OWN published miniF2F proofs -> the empirical pin-confirmation fraction
set -uo pipefail
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
cd "$PROJ" || exit 1
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="$PROJ/scratch/elan-deepseek"   # relocated toolchain home (HOME quota)
PY="$PROJ/scratch/conda-envs/atp/bin/python"
GPFS_ENV="$PROJ/scratch/lean-cache/deepseek-lean-env"

echo "[gate] $(date) host=$(hostname) job=${SLURM_JOB_ID:-none}"

# --- stage env to node-local /dev/shm (epilog-safe, fast) ---------------------------------
LOCAL_BASE="/dev/shm/$USER"; [ -d /dev/shm ] || LOCAL_BASE="/local/$USER"
LOCAL_ENV="$LOCAL_BASE/deepseek-lean-env"
mkdir -p "$LOCAL_BASE"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
REPL_REL=".lake/packages/REPL/.lake/build/bin/repl"
if [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ] && [ -x "$LOCAL_ENV/$REPL_REL" ]; then
    echo "[gate] reuse staged env ($N_LOCAL oleans)"
else
    echo "[gate] staging $N_GPFS oleans GPFS->/dev/shm (one sequential copy)..."
    rm -rf "$LOCAL_ENV.tmp" "$LOCAL_ENV"
    cp -a "$GPFS_ENV" "$LOCAL_ENV.tmp" && mv -T "$LOCAL_ENV.tmp" "$LOCAL_ENV"
    N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
    echo "[gate] staged $N_LOCAL oleans; repl: $([ -x "$LOCAL_ENV/$REPL_REL" ] && echo ok || echo MISSING)"
fi
export ATP_LEAN_ENV_DIR="$LOCAL_ENV"

RESULTS="$PROJ/results/phase2/deepseek_gates.txt"
mkdir -p "$PROJ/results/phase2"
{ echo "DeepSeek env gates — $(date -Is) — host $(hostname)"; echo "env=$LOCAL_ENV oleans=$N_LOCAL"; } > "$RESULTS"

# --- G3: contract tests (wiring + soundness in env #2) ------------------------------------
echo "[gate] === G3 contract tests (-m lean) ==="
$PY -m pytest tests/ -m lean -q 2>&1 | tee -a "$RESULTS" | tail -8

# --- G2: statement elaboration on this pin (-> intersection) ------------------------------
for cfg in validate_minif2f_deepseek validate_proofnet_deepseek; do
  echo "[gate] === G2 validate_statements: $cfg ==="
  $PY scripts/validate_statements.py --config "configs/$cfg.yaml" 2>&1 | tee -a "$RESULTS" | tail -4
done

# --- G1: verify DeepSeek's published proofs (-> pin fraction) ------------------------------
echo "[gate] === G1 verify DeepSeek published miniF2F proofs (ALL) ==="
bash scripts/verify_deepseek_proofs.sh all 14 2>&1 | tee -a "$RESULTS" | tail -6

echo "[gate] DONE $(date). Summary -> $RESULTS"
printf 'gates done: %s\n' "$(date -Is)" > "$PROJ/results/phase2/_deepseek_gates_done.txt"
