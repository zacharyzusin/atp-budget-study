#!/usr/bin/env bash
#SBATCH --job-name=atp_reverify_debug
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=00:30:00
#SBATCH --output=logs/reverify-debug-%j.out
#SBATCH --error=logs/reverify-debug-%j.err
set -uo pipefail
PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="$1"; RUN_DIR="$2"; PROBLEM="$3"; SEED="$4"
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
module load anaconda/2023.09
source "$(conda info --base)/etc/profile.d/conda.sh"; conda activate "$PROJ/scratch/conda-envs/atp"
export PATH="$PROJ/scratch/conda-envs/atp/bin:$PATH"
export HF_HOME="$PROJ/scratch/hf-cache"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="${ELAN_HOME:-$HOME/.elan}"
cd "$PROJ"

GPFS_ENV="$PROJ/scratch/lean-cache/atp-lean-env"
LOCAL_BASE="${ATP_LOCAL_BASE:-/local/$USER}"; [ -d /local ] || LOCAL_BASE="/tmp/$USER"
LOCAL_ENV="$LOCAL_BASE/atp-lean-env"
mkdir -p "$LOCAL_BASE"
N_GPFS="$(find "$GPFS_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
exec 9>"$LOCAL_BASE/.atp_stage.lock"
flock 9
N_LOCAL="$(find "$LOCAL_ENV/.lake" -name '*.olean' 2>/dev/null | wc -l)"
if [ -f "$LOCAL_ENV/.staged_ok" ] && [ "$N_LOCAL" = "$N_GPFS" ] && [ "$N_GPFS" -gt 0 ]; then
    echo "[debug] Lean env already staged on $(hostname) ($N_LOCAL oleans) — reusing."
else
    rm -rf "$LOCAL_ENV"; mkdir -p "$LOCAL_ENV"
    cp -a "$GPFS_ENV/.lake" "$GPFS_ENV/lakefile.lean" "$GPFS_ENV/lake-manifest.json" \
          "$GPFS_ENV/lean-toolchain" "$GPFS_ENV/AtpLeanEnv" "$LOCAL_ENV/"
    touch "$LOCAL_ENV/.staged_ok"
fi
flock -u 9; exec 9>&-
export ATP_LEAN_PROJECT="$LOCAL_ENV"

python scripts/phase8_reverify_debug_one.py "$CONFIG" "$RUN_DIR" "$PROBLEM" "$SEED"
