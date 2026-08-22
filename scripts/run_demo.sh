#!/usr/bin/env bash
# Regenerate every result, plot, CSV and generated document in this repository.
# Takes about two minutes; the switching simulator sweeps are most of it.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 simulation/run_all.py "$@"

echo
echo "Written:"
echo "  outputs/          netlists, BOM, compensation values, verification list"
echo "  test-results/     simulated Bode, regulation, transient, efficiency,"
echo "                    thermal and EMC results"
echo "  docs/spec.md      specification table"
echo "  docs/validation_report.md"
