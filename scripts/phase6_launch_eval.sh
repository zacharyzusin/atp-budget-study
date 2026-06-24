#!/usr/bin/env bash
# Phase 6 3-seed eval launcher. Submits ONE eval sweep (model, seed, arm, benchmark) with the exact
# per-model env + per-arm LoRA wiring, so seeds 1,2 differ from seed-0 only in --seed/--out/run-name
# (single-variable). Wraps slurm/sweep_array.sh; relies on its fail-loud + --resume net.
#
# Usage: scripts/phase6_launch_eval.sh <g|d> <seed> <base|A|B> <pn|mf> [extra sbatch args...]
#   scripts/phase6_launch_eval.sh g 1 base pn
#   scripts/phase6_launch_eval.sh d 2 B mf --array=0-3%4
set -uo pipefail
PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
cd "$PROJ"

M="$1"; SEED="$2"; ARM="$3"; BENCH="$4"; shift 4
SBATCH_EXTRA=("$@"); [ ${#SBATCH_EXTRA[@]} -eq 0 ] && SBATCH_EXTRA=(--array=0-3%4)

case "$M" in
  g) MODEL=goedel;   BENCH_LONG_PREFIX=goedel ;;
  d) MODEL=deepseek; BENCH_LONG_PREFIX=deepseek ;;
  *) echo "model must be g|d"; exit 2 ;;
esac
case "$BENCH" in
  pn) BLONG=proofnet ;;
  mf) BLONG=minif2f ;;
  *) echo "bench must be pn|mf"; exit 2 ;;
esac

CONFIG="configs/phase6_eval_${MODEL}_${BLONG}_s${SEED}.yaml"
[ -f "$CONFIG" ] || { echo "missing config $CONFIG"; exit 2; }
RUN="p6eval_${M}_${BENCH}_${ARM}_s${SEED}"

# Per-model env (DeepSeek lives in a separate HF cache + relocated Lean toolchain).
ENV=()
if [ "$M" = d ]; then
  ENV+=(ATP_HF_HOME=/insomnia001/depts/edu/COMS-E6998-012/zwz2000/.hf_cache)
  ENV+=(ELAN_HOME=$PROJ/scratch/elan-deepseek)
  ENV+=(ATP_LEAN_ENV_NAME=deepseek-lean-env)
fi
# Per-arm LoRA wiring (base = no adapter).
if [ "$ARM" != base ]; then
  CKPT="$PROJ/scratch/phase6/ckpt/${MODEL}/${ARM}_seed${SEED}"
  [ -d "$CKPT" ] || { echo "missing adapter $CKPT (train not done?)"; exit 3; }
  ENV+=(ATP_VLLM_LORA="${MODEL}-${ARM}=${CKPT}")
  ENV+=(ATP_SERVED_MODEL="${MODEL}-${ARM}")
fi

echo "[launch] $RUN  config=$CONFIG  env={${ENV[*]}}  sbatch=${SBATCH_EXTRA[*]}"
env "${ENV[@]}" sbatch --job-name="$RUN" --exclude=ins082,ins087 "${SBATCH_EXTRA[@]}" \
    slurm/sweep_array.sh "$CONFIG" "$RUN"
