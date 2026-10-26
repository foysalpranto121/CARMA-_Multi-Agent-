#!/usr/bin/env bash
# Run the registered CARMA study for one model on the free tier.
#
#   bash scripts/run_study.sh openai/gpt-oss-120b
#   bash scripts/run_study.sh openai/gpt-oss-20b      # in parallel: separate quota
#
# Every step resumes, so the script can be re-launched at any time — after a
# reboot, a network outage or a Docker restart — and continues where it
# stopped without repeating a finished case.  Progress: artifacts/study_<model>.log
set -u
MODEL=${1:?usage: run_study.sh <model> [seed]}
SEED=${2:-42}
cd "$(dirname "$0")/../carma-backend" || exit 1
PY=./venv/Scripts/python.exe
[ -x "$PY" ] || PY=./venv/bin/python
mkdir -p ../artifacts
LOG="../artifacts/study_${MODEL//\//_}_seed${SEED}.log"
NOISE='^(INFO|DEBUG)|Batches|HTTP Request'
RETRY_WAIT=600   # seconds between attempts
MAX_ATTEMPTS=72  # 12 hours of retries per step

step() {
  local attempt rc
  for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    echo "== $(date '+%F %T') $*"
    $PY -W ignore manage.py "$@" --resume 2>&1 | tr -d '\r' | grep -avE "$NOISE"
    rc=${PIPESTATUS[0]}
    [ "$rc" -eq 0 ] && return 0
    echo "== $(date '+%F %T') stopped (exit $rc), attempt $attempt/$MAX_ATTEMPTS; resuming in ${RETRY_WAIT}s"
    sleep "$RETRY_WAIT"
  done
  return 1
}

{
  echo "== $(date '+%F %T') study for $MODEL, seed $SEED"
  # 1. tau of B7 on the 84 pilot cases (tuning only, never evaluated)
  step tune_tau --config B7 --model "$MODEL" --seed "$SEED" || exit 1
  # 2. confirmatory: the CAR x SCV factorial on the 196-case sample
  step run_experiment --configs B4 B5 B6 B7 --model "$MODEL" --seed "$SEED" --per-scenario 28 || exit 1
  # 3. secondary: the single-agent baselines on the same cases
  step run_experiment --configs B1 B2 B3 --model "$MODEL" --seed "$SEED" --per-scenario 28 || exit 1
  echo "== $(date '+%F %T') study for $MODEL, seed $SEED finished"
} >> "$LOG" 2>&1
