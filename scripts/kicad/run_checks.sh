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
# The autorouter left this many connections on the board unrouted. They are
# listed in STATUS.md; DRC fails if there are more, or if anything else is
# wrong at all.
UNROUTED_ALLOWED=5
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
  echo "== DRC with schematic parity"
  in_kicad 'kicad-cli pcb drc --schematic-parity --severity-all -o /tmp/drc.rpt emb-multirail-smps.kicad_pcb >&2; cat /tmp/drc.rpt' > "$out/drc.rpt"
  grep -E '^\[' "$out/drc.rpt" | sed 's/:.*//' | sort | uniq -c || true
  # Errors by type: the line after each "[type]: ..." heading names the rule
  # and ends in its severity.
  awk '/^\[/ {t=$1} /; error$/ {n[t]++} END {for (k in n) print k, n[k]}'     "$out/drc.rpt" > "$out/drc_errors.txt"
  unrouted=$(awk '$1=="[unconnected_items]:" {print $2}' "$out/drc_errors.txt")
  others=$(awk '$1!="[unconnected_items]:" {s+=$2} END {print s+0}' "$out/drc_errors.txt")
  echo "DRC errors other than unrouted connections: $others"
  echo "unrouted connections: ${unrouted:-0} (STATUS.md lists the ${UNROUTED_ALLOWED} allowed)"
  if [ "$others" -ne 0 ]; then grep -B1 -A3 '; error' "$out/drc.rpt" | head -60; exit 1; fi
  if [ "${unrouted:-0}" -gt "$UNROUTED_ALLOWED" ]; then
    echo "more unrouted connections than STATUS.md admits to"; exit 1
  fi
  echo "== Gerber and drill files, for inspection only"
  in_kicad 'mkdir -p /tmp/fab && kicad-cli pcb export gerbers -o /tmp/fab/ emb-multirail-smps.kicad_pcb >&2 && kicad-cli pcb export drill -o /tmp/fab/ emb-multirail-smps.kicad_pcb >&2 && tar -C /tmp -cf - fab' | tar -C "$out" -xf -
  ls "$out/fab" | wc -l
fi
echo "KiCad checks passed"
