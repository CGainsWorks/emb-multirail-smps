#!/usr/bin/env bash
# The KiCad checks CI runs, runnable locally with Docker:
#
#   scripts/kicad/run_checks.sh            ERC, netlist export, cross-check
#   scripts/kicad/run_checks.sh --board    the same, then DRC on the board
#
# KiCad runs in the pinned kicad/kicad image. It works on a copy of the
# project inside the container and prints its reports to stdout, so nothing
# is written through the bind mount: a Linux runner's checkout is owned by a
# different uid from the container's user and a writable mount that works on
# Docker Desktop fails there.
set -euo pipefail

IMAGE=${KICAD_IMAGE:-kicad/kicad:8.0.9}
PY=${PY:-python}
repo=$(cd "$(dirname "$0")/../.." && pwd)
out="$repo/hardware/kicad/build"
mkdir -p "$out"

in_kicad() {
  docker run --rm -v "$repo/hardware/kicad:/src:ro" "$IMAGE" bash -c \
    "cp -r /src /tmp/p && cd /tmp/p && $1"
}

echo "== ERC (kicad-cli, every severity, must be clean)"
set +e
in_kicad 'kicad-cli sch erc --severity-all --exit-code-violations -o /tmp/erc.rpt emb-multirail-smps.kicad_sch >&2; s=$?; cat /tmp/erc.rpt; exit $s' > "$out/erc.rpt"
erc=$?
set -e
grep -E '^\[|ERC messages' "$out/erc.rpt" || true
if [ "$erc" -ne 0 ]; then echo "ERC failed"; exit 1; fi

echo "== netlist export"
in_kicad 'kicad-cli sch export netlist -o /tmp/n.net emb-multirail-smps.kicad_sch >&2 && cat /tmp/n.net' > "$out/netlist.net"

echo "== schematic against the simulation"
(cd "$repo" && "$PY" scripts/kicad/check_netlist.py hardware/kicad/build/netlist.net)

if [ "${1:-}" = "--board" ]; then
  echo "== DRC with schematic parity (errors fail, warnings are listed)"
  set +e
  in_kicad 'kicad-cli pcb drc --schematic-parity --severity-all -o /tmp/drc.rpt emb-multirail-smps.kicad_pcb >&2; cat /tmp/drc.rpt' > "$out/drc.rpt"
  set -e
  grep -E '^\[' "$out/drc.rpt" | sed 's/:.*//' | sort | uniq -c || true
  grep -E 'Found [0-9]+ (violations|unconnected|schematic parity)' "$out/drc.rpt" || true
  errors=$(grep -c '; error' "$out/drc.rpt" || true)
  echo "DRC errors: $errors"
  if [ "$errors" -ne 0 ]; then grep -B1 -A3 '; error' "$out/drc.rpt" | head -60; exit 1; fi
fi
echo "KiCad checks passed"
