#!/usr/bin/env bash
#SBATCH --job-name=offpin_elab
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --requeue
#SBATCH --output=logs/offpin_elab-%j.out
#SBATCH --error=logs/offpin_elab-%j.err
#
# H? off-pin Arm-B gate 1: do the trapped ProofNet# statements ELABORATE in the sibling v4.29.0 mathlib
# stack? Stages lean_env to node-local SSD (full-Mathlib import off GPFS risks the open-storm timeout),
# then `lake env lean ElabProbe.lean` (150 `theorem ... := sorry`). A statement that elaborates yields
# only a 'declaration uses sorry' warning; a drifted one yields an elaboration ERROR we can map by line.
set -uo pipefail
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

SIB="/insomnia001/depts/edu/COMS-E6998-012/$USER/theorem-proving-research"
ATP="/insomnia001/depts/edu/COMS-E6998-012/$USER/atp-budget-study"
GPFS_ENV="$SIB/lean_env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/lean_env_v429"
mkdir -p "$LOCAL_BASE"

export XDG_CACHE_HOME="$SIB/.xdg_cache"
export ELAN_NO_AUTO_INSTALL=1
export PATH="$HOME/.elan/bin:$PATH"

N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
exec 9>"$LOCAL_BASE/.v429_stage.lock"; flock 9
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[elab] lean_env already staged ($N_LOCAL oleans) — reusing."
else
    echo "[elab] staging lean_env -> $LOCAL_ENV ($N_GPFS oleans, ~10-20min off GPFS)..."
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"; t0=$SECONDS
    cp -a "$GPFS_ENV/." "$LOCAL_ENV/" || { echo "FATAL: staging cp failed"; flock -u 9; exit 1; }
    touch "$LOCAL_ENV/.staged_ok"
    echo "[elab] staged in $((SECONDS-t0))s ($(find "$LOCAL_ENV/.lake" -name '*.olean'|wc -l) oleans)."
fi
flock -u 9; exec 9>&-

cp "$ATP/scratch/phase3/ElabProbe.lean" "$LOCAL_ENV/ElabProbe.lean"
cd "$LOCAL_ENV"
echo "[elab] elaborating 150 statements via lake env lean (cold Mathlib import may take minutes)..."
lake env lean ElabProbe.lean > "$ATP/scratch/phase3/elab_probe_out.txt" 2>&1
rc=$?
echo "[elab] lake env lean rc=$rc"
# summary: count PROBE markers vs error lines
ERR=$(grep -cE "error:" "$ATP/scratch/phase3/elab_probe_out.txt" 2>/dev/null || echo 0)
SORRY=$(grep -cE "declaration uses 'sorry'" "$ATP/scratch/phase3/elab_probe_out.txt" 2>/dev/null || echo 0)
echo "[elab] DONE: sorry-warnings(=elaborated) ~$SORRY ; error-lines ~$ERR ; full output -> scratch/phase3/elab_probe_out.txt"
exit 0
