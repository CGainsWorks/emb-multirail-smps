#!/usr/bin/env bash
# Rebuild the board from the schematic: place, autoroute, pour, check.
#
#   FREEROUTING_JAR=/path/to/freerouting-2.4.1.jar scripts/kicad/route_board.sh
#
# Two pinned containers: KiCad for placement, zones and DRC, and a Java
# runtime for Freerouting. This is a design step, run by hand when the
# schematic or the placement changes; the board it writes is committed. CI
# does not reroute, it runs DRC and the schematic parity check on what is
# committed.
set -euo pipefail

KICAD_IMAGE=${KICAD_IMAGE:-kicad/kicad:8.0.9}
JAVA_IMAGE=${JAVA_IMAGE:-eclipse-temurin:25-jre}
PASSES=${PASSES:-40}
: "${FREEROUTING_JAR:?set FREEROUTING_JAR to the Freerouting 2.4.1 jar}"

repo=$(cd "$(dirname "$0")/../.." && pwd)
build=hardware/kicad/build
board=hardware/kicad/emb-multirail-smps.kicad_pcb
mkdir -p "$repo/$build"
jar_dir=$(cd "$(dirname "$FREEROUTING_JAR")" && pwd)
jar_name=$(basename "$FREEROUTING_JAR")

kicad() {
  docker run --rm -v "$repo:/repo" -w /repo "$KICAD_IMAGE" "$@"
}

route() {
  docker run --rm -v "$repo:/repo" -v "$jar_dir:/fr:ro" -w /repo "$JAVA_IMAGE" \
    java -jar "/fr/$jar_name" --gui.enabled=false \
    -de "$build/board.dsn" -do "$build/board.ses" -mp "$1"
}

finish() {
  kicad python3 scripts/kicad/gen_pcb.py finish --board "$board" --ses "$build/board.ses"
  kicad kicad-cli pcb drc --schematic-parity --format json \
    -o "$build/drc.json" "$board" >/dev/null || true
}

errors() {
  kicad python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(sum(v['severity']=='error' for v in d['violations'])+len(d['unconnected_items']))" \
    "$build/drc.json"
}

# REPAIR_ONLY=1 skips placement and the first pass and goes straight to the
# repair passes on the board as it stands.
if [ -z "${REPAIR_ONLY:-}" ]; then
  kicad kicad-cli sch export netlist -o "$build/netlist.net" \
    hardware/kicad/emb-multirail-smps.kicad_sch
  kicad python3 scripts/kicad/gen_pcb.py place --netlist "$build/netlist.net" \
    --out "$board" --dsn "$build/board.dsn"
  route "$PASSES"
  finish
fi
# Up to three repair passes: take up what DRC objects to and route again.
for pass in 1 2 3; do
  n=$(errors)
  echo "DRC errors after routing: $n"
  [ "$n" -eq 0 ] && break
  kicad python3 scripts/kicad/gen_pcb.py rip --board "$board" \
    --drc "$build/drc.json" --dsn "$build/board.dsn"
  route 20
  finish
done

kicad kicad-cli pcb drc --schematic-parity --severity-all \
  -o "$build/drc.rpt" "$board" || true
grep -E '^\[' "$repo/$build/drc.rpt" | sed 's/:.*//' | sort | uniq -c || true
