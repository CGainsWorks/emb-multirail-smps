#!/usr/bin/env bash
# Install everything needed to run the design and validation pass.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo
echo "Ready. Next:"
echo "  ./scripts/run_demo.sh     regenerate every result"
echo "  python3 -m pytest tests   run the test suite"
