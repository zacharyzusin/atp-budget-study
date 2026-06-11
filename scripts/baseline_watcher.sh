#!/bin/bash
# Overnight watcher: keep the Phase-0 baseline sweep alive across 12h Slurm TIMEOUTs.
# Polls squeue; when no atp_sweep job is queued/running, checks for completion and otherwise
# resubmits with --resume (the resubmit reloads the current code, incl. the checkpoint fix, so the
# 10 stuck seed1 cells finally complete). Exits when the run is complete or the resubmit cap is hit.
set -uo pipefail
cd /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study

LOG=logs/baseline_watcher.log
USER_=zwz2000
CONFIG=configs/phase0_baseline.yaml
RUN=baseline
RUNDIR=results/$RUN
TARGET_CELLS=732
POLL=300            # seconds between polls
MAX_RESUBMITS=6     # safety cap
resubmits=0

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "watcher start (target=$TARGET_CELLS cells, poll=${POLL}s, cap=$MAX_RESUBMITS resubmits)"

while true; do
  # Any sweep job currently queued or running?
  njobs=$(squeue -u "$USER_" -h -n atp_sweep 2>/dev/null | wc -l)

  cells=$(ls "$RUNDIR/problems/" 2>/dev/null | wc -l)

  if [ "$njobs" -gt 0 ]; then
    log "sweep alive (jobs=$njobs, cells=$cells/$TARGET_CELLS); sleeping ${POLL}s"
    sleep "$POLL"
    continue
  fi

  # No sweep in queue. Done?
  if [ "$cells" -ge "$TARGET_CELLS" ] && [ -f "$RUNDIR/metrics.json" ]; then
    log "COMPLETE: $cells/$TARGET_CELLS cells and metrics.json present. Done."
    exit 0
  fi

  # Not done -> resubmit (unless capped).
  if [ "$resubmits" -ge "$MAX_RESUBMITS" ]; then
    log "STOP: hit resubmit cap ($MAX_RESUBMITS) with $cells/$TARGET_CELLS cells, metrics=$( [ -f "$RUNDIR/metrics.json" ] && echo yes || echo no ). Needs a human."
    exit 2
  fi

  out=$(sbatch slurm/sweep.sh "$CONFIG" "$RUN" 2>&1)
  rc=$?
  resubmits=$((resubmits+1))
  if [ "$rc" -ne 0 ]; then
    log "RESUBMIT FAILED (rc=$rc): $out  (attempt $resubmits/$MAX_RESUBMITS); retrying after ${POLL}s"
    sleep "$POLL"
    continue
  fi
  newid=$(echo "$out" | grep -oE '[0-9]+' | tail -1)
  log "RESUBMITTED (attempt $resubmits/$MAX_RESUBMITS) -> job $newid at $cells/$TARGET_CELLS cells"
  sleep 120   # let Slurm register the new job before the next poll
done
