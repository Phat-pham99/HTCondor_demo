#!/usr/bin/env bash
set -euo pipefail

term_handler() {
  if [[ -n "${master_pid:-}" ]]; then
    kill -TERM "$master_pid" 2>/dev/null || true
  fi
}
trap term_handler TERM INT

/usr/sbin/condor_master -f &
master_pid=$!
idle_since=0
idle_limit=${WORKER_IDLE_SECONDS:-60}
poll_interval=${WORKER_POLL_SECONDS:-5}

while kill -0 "$master_pid" 2>/dev/null; do
  state=$(/usr/sbin/condor_status -direct -format '%s' 2>/dev/null || true)
  if [[ "$state" != *Busy* && "$state" != *Running* ]]; then
    if (( idle_since == 0 )); then
      idle_since=$SECONDS
    fi
    if (( SECONDS - idle_since >= idle_limit )); then
      kill -TERM "$master_pid" 2>/dev/null || true
      break
    fi
  else
    idle_since=0
  fi
  sleep "$poll_interval"
done

wait "$master_pid" 2>/dev/null || true
