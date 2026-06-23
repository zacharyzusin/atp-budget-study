#!/usr/bin/env bash
#SBATCH --job-name=p6_train
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --gres=gpu:A6000:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --requeue
#SBATCH --output=logs/p6_train-%j.out
#SBATCH --error=logs/p6_train-%j.err
#
# Phase 6 LoRA SFT (Stage A / B). No Lean (training only). Loads the base model from the HF cache and
# trains an adapter on a sft_*.jsonl. Single-variable: same args for A and B, only --data differs.
#
# Usage (one arm/seed):
#   ATP_TRAIN_CONFIG=configs/phase6_harvest_goedel.yaml \
#   ATP_TRAIN_DATA=scratch/phase6/sft/goedel/sft_B.jsonl \
#   ATP_TRAIN_OUT=scratch/phase6/ckpt/goedel/B_seed0 \
#   ATP_TRAIN_SEED=0 ATP_TRAIN_MAX_STEPS=200 \
#   sbatch --exclude=ins082,ins087 slurm/phase6_train.sh
# DeepSeek: add ATP_HF_HOME=/insomnia001/depts/edu/COMS-E6998-012/zwz2000/.hf_cache
set -uo pipefail

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
CONFIG="${ATP_TRAIN_CONFIG:-configs/phase6_harvest_goedel.yaml}"
DATA="${ATP_TRAIN_DATA:-scratch/phase6/sft/goedel/sft_B.jsonl}"
OUT="${ATP_TRAIN_OUT:-scratch/phase6/ckpt/goedel/B_seed0}"
SEED="${ATP_TRAIN_SEED:-0}"
MAX_STEPS="${ATP_TRAIN_MAX_STEPS:-200}"
LR="${ATP_TRAIN_LR:-1e-4}"
MAX_LEN="${ATP_TRAIN_MAX_LEN:-4096}"

unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
module load anaconda/2023.09
ATP_ENV="$PROJ/scratch/conda-envs/atp"
activate_env() {
    local base; base="$(conda info --base 2>/dev/null)"
    [ -n "$base" ] && [ -f "$base/etc/profile.d/conda.sh" ] || return 1
    set +u; source "$base/etc/profile.d/conda.sh"; conda activate "$ATP_ENV" 2>/dev/null; set -u
    export PATH="$ATP_ENV/bin:$PATH"; export CONDA_PREFIX="$ATP_ENV"
    hash -r 2>/dev/null || true
    [ "$(command -v python)" = "$ATP_ENV/bin/python" ] || return 1
    python -c "import atp, peft, trl, transformers" 2>/dev/null || return 1
}
ok=0
for attempt in 1 2 3; do
    if activate_env; then ok=1; break; fi
    echo "[train] activate failed (attempt $attempt) — retry in 5s..."; sleep 5
done
[ "$ok" = 1 ] || { echo "FATAL: could not activate $ATP_ENV with peft/trl importable."; exit 1; }
echo "[train] env OK: python=$(command -v python)"

export HF_HOME="${ATP_HF_HOME:-$PROJ/scratch/hf-cache}"
export HF_HUB_OFFLINE="${ATP_HF_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${ATP_HF_OFFLINE:-1}"
cd "$PROJ"
mkdir -p "$(dirname "$OUT")"

echo "[train] config=$CONFIG data=$DATA out=$OUT seed=$SEED max_steps=$MAX_STEPS lr=$LR"
python scripts/phase6_train_sft.py \
    --config "$CONFIG" --data "$DATA" --out "$OUT" \
    --seed "$SEED" --max-steps "$MAX_STEPS" --lr "$LR" --max-len "$MAX_LEN"
rc=$?
echo "[train] done (rc=$rc)"
exit $rc
