#!/bin/bash
# Re-chain the ProofNet# baseline (sweep) + Phase 1 ablation (array) across the 12h `short` wall.
# `short` is non-preemptible (unlike burst, which starved both jobs ~3.5h on 2026-06-14), so once a
# job starts it runs the full 12h; this watcher just resubmits it when it leaves the queue still
# unfinished. Both runs are resume-keyed (per problem-seed), so a resubmit skips completed work.
# Runs detached (Bash run_in_background) so it survives session/Claude restarts. Exits when BOTH
# runs are complete or the resubmit cap is hit.
set -uo pipefail
cd /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study

LOG=logs/proofnet_watcher.log
USER_=zwz2000
POLL=300
MAX_RESUBMITS=30          # generous: 128k baseline needs many 12h chains
bl_resubs=0; ab_resubs=0

# baseline: sweep.sh, job-name atp_sweep, run=proofnet_baseline, 558 problem-seeds + metrics.json
BL_CONFIG=configs/proofnet_baseline.yaml; BL_RUN=proofnet_baseline; BL_DIR=results/$BL_RUN
BL_TARGET=558
# ablation: ablation.sh array, job-name atp_ablation, run=phase1_proofnet, 7 cell metrics.json
AB_CONFIG=configs/phase1_ablation_proofnet.yaml; AB_RUN=phase1_proofnet; AB_DIR=results/$AB_RUN
AB_TARGET=7

PYBIN=scratch/conda-envs/atp/bin/python   # CPU-only aggregate step; no GPU/Lean needed

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
njobs() { squeue -u "$USER_" -h -n "$1" 2>/dev/null | wc -l; }
bl_cells() { ls "$BL_DIR/problems/" 2>/dev/null | wc -l; }
ab_done() { ls "$AB_DIR"/*/metrics.json 2>/dev/null | wc -l; }
bl_complete() { [ "$(bl_cells)" -ge "$BL_TARGET" ] && [ -f "$BL_DIR/metrics.json" ]; }
ab_complete() { [ "$(ab_done)" -ge "$AB_TARGET" ]; }

log "watcher start (baseline $BL_TARGET cells, ablation $AB_TARGET cells, poll=${POLL}s, cap=$MAX_RESUBMITS)"

while true; do
  bl_ok=0; ab_ok=0
  bl_complete && bl_ok=1
  ab_complete && ab_ok=1
  if [ "$bl_ok" = 1 ] && [ "$ab_ok" = 1 ]; then
    log "BOTH COMPLETE: baseline $(bl_cells)/$BL_TARGET + metrics, ablation $(ab_done)/$AB_TARGET. Done."
    exit 0
  fi

  # Baseline (sharded array sweep_array.sh): all shards write per-cell JSONs only. Once every cell
  # exists, aggregate ONCE to write metrics.json (the completion signal). Otherwise, if no shard job
  # is queued/running, resubmit the array (each shard --resume-skips its done cells).
  if [ "$bl_ok" != 1 ]; then
    if [ "$(bl_cells)" -ge "$BL_TARGET" ]; then
      if [ ! -f "$BL_DIR/metrics.json" ]; then
        log "baseline all $BL_TARGET cells present — aggregating metrics.json"
        if "$PYBIN" -m atp.cli sweep --config "$BL_CONFIG" --name "$BL_RUN" --aggregate >> "$LOG" 2>&1
        then log "baseline COMPLETE: metrics.json written"; else log "WARN aggregate failed; retry"; fi
      fi
    elif [ "$(njobs atp_sweep)" -eq 0 ]; then
      if [ "$bl_resubs" -ge "$MAX_RESUBMITS" ]; then
        log "STOP baseline: hit cap at $(bl_cells)/$BL_TARGET cells. Needs a human."
      else
        out=$(sbatch slurm/sweep_array.sh "$BL_CONFIG" "$BL_RUN" 2>&1); bl_resubs=$((bl_resubs+1))
        log "RESUBMIT baseline array ($bl_resubs/$MAX_RESUBMITS) at $(bl_cells)/$BL_TARGET -> $out"
        sleep 60
      fi
    fi
  fi

  # Ablation: resubmit the whole array if not complete and no ablation job queued/running.
  if [ "$ab_ok" != 1 ] && [ "$(njobs atp_ablation)" -eq 0 ]; then
    if [ "$ab_resubs" -ge "$MAX_RESUBMITS" ]; then
      log "STOP ablation: hit cap at $(ab_done)/$AB_TARGET cells. Needs a human."
    else
      out=$(sbatch slurm/ablation.sh "$AB_CONFIG" "$AB_RUN" 2>&1); ab_resubs=$((ab_resubs+1))
      log "RESUBMIT ablation ($ab_resubs/$MAX_RESUBMITS) at $(ab_done)/$AB_TARGET -> $out"
      sleep 60
    fi
  fi

  # If both are capped-out and incomplete, stop spinning.
  if [ "$bl_ok" != 1 ] && [ "$bl_resubs" -ge "$MAX_RESUBMITS" ] && \
     [ "$ab_ok" != 1 ] && [ "$ab_resubs" -ge "$MAX_RESUBMITS" ]; then
    log "STOP: both runs hit resubmit cap, still incomplete. Needs a human."
    exit 2
  fi
  sleep "$POLL"
done
