#!/usr/bin/env bash
# Omni end to end demo.
#
# Runs the complete event -> decision -> execution loop against Bitget's demo
# (paper) environment and writes the result to the paper log.
#
# Usage: ./demo/run_demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "########################################################################"
echo "# 0. dependency check (public data, demo account, agent hub, llm)"
echo "########################################################################"
python3 -m omni.cli doctor

echo
echo "########################################################################"
echo "# 1. clean slate: close any open demo positions"
echo "########################################################################"
python3 -m omni.cli flatten

echo
echo "########################################################################"
echo "# 2. construct the demo book: a leveraged crypto perpetual leg"
echo "########################################################################"
python3 -m omni.cli setup --setup-symbol BTCUSDT --setup-qty 2

echo
echo "########################################################################"
echo "# 3. RUN A: large declared rToken book, policy cap engages"
echo "########################################################################"
python3 -m omni.cli demo

echo
echo "########################################################################"
echo "# 4. RUN B: right sized book, protective hedge fills in full"
echo "########################################################################"
python3 -m omni.cli demo --portfolio demo/portfolio.small.json

echo
echo "########################################################################"
echo "# 5. flatten for hygiene"
echo "########################################################################"
python3 -m omni.cli flatten

echo
echo "########################################################################"
echo "# 6. paper metrics from the ledger"
echo "########################################################################"
python3 -m omni.cli report
