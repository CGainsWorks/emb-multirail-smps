#!/usr/bin/env python3
"""Fail if any number the README quotes has stopped being true.

A README that quotes results is only worth reading if the results are still
what the code produces. This is the guard: CI runs it, and so can you.

    python scripts/check_headline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulation"))

from smps.results import headline  # noqa: E402
from smps.spec import SYSTEM  # noqa: E402


def checks(h: dict) -> list[tuple[str, bool, str]]:
    return [
        ("system efficiency at nominal input",
         h["system_efficiency_nom_pct"] > 85.0,
         f"{h['system_efficiency_nom_pct']:.1f} % against a floor of 85 %"),
        ("maximum ambient at full load",
         h["max_ambient_full_load_c"] > SYSTEM.ambient_max_c,
         f"{h['max_ambient_full_load_c']:.1f} C against a specification of "
         f"{SYSTEM.ambient_max_c:.0f} C"),
        ("conducted emissions margin",
         h["worst_emc_margin_db"] > 0.0,
         f"{h['worst_emc_margin_db']:.1f} dB at Vin "
         f"{h['worst_emc_v_in_v']:.0f} V"),
        ("input filter Middlebrook separation",
         h["worst_middlebrook_separation_db"] > 6.0,
         f"{h['worst_middlebrook_separation_db']:.1f} dB against a floor of "
         "6 dB"),
    ]


def main() -> int:
    h = headline()
    print(json.dumps(h, indent=2))
    print()

    failed = []
    for name, ok, detail in checks(h):
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")
        if not ok:
            failed.append(name)

    if failed:
        print(f"\nFAILED: {', '.join(failed)}", file=sys.stderr)
        print("The README quotes these. Fix the design or fix the README.",
              file=sys.stderr)
        return 1
    print("\nall headline numbers hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
