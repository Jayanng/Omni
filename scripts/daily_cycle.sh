#!/usr/bin/env bash
# Omni daily governance cycle.
#
# Runs one full event -> decision -> execution cycle against Bitget's demo
# environment so the paper log accumulates equity observations for the
# hackathon submission. Also cleans up any open demo positions afterwards so
# the account stays hygienic.
#
# Safety: demo (paper) environment only. No live orders are possible with the
# demo-scoped credentials, and the executor has no transfer/withdraw path.
set -uo pipefail

cd "$(dirname "$0")/.."

STAMP="$(date -u +%Y-%m-%d)"
LOG="/home/ubuntu/omni/logs/cycle-${STAMP}.log"
mkdir -p /home/ubuntu/omni/logs

{
  echo "=== omni daily cycle ${STAMP} $(date -u +%H:%M:%S) UTC ==="
  python3 -m omni.cli doctor || echo "doctor failed"
  echo
  python3 -m omni.cli demo --portfolio demo/portfolio.small.json \
    --rtoken-shock -0.08 --crypto-shock -0.25
  echo
  python3 -m omni.cli flatten
  echo
  python3 -m omni.cli report
} >> "$LOG" 2>&1

echo "cycle written to ${LOG}"
