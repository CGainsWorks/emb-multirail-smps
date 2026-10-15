#!/usr/bin/env python3
"""Check the committed results still match what the code produces.

Run ``run_all.py`` first, then this. It compares every generated text file in
the working tree against the version committed at HEAD.

Why not ``git diff``
--------------------
Because these files are the output of a numerical simulation, and a numerical
simulation is not bit reproducible across platforms. The switching simulator
finds each switching instant by secant iteration, and where that iteration
stops depends on the last bits of a double precision subtraction, which depend
on the BLAS build, the compiler and the processor. The closed loop then
integrates the resulting duty ratio differences over thousands of cycles.

Measured: the settled output voltages reproduce to about 1 part per million
between Windows with numpy 1.26 and Linux with numpy 2.5. That is three orders
of magnitude finer than any claim this repository makes, and about four orders
finer than the uncertainty in the component values the numbers are computed
from. It is also enough to change the sixth decimal place of a voltage, which
a byte comparison would report as a failure.

So this compares numbers as numbers. Every non-numeric token still has to match
exactly, so a renamed column, a reordered row or a changed sentence is caught
the way it should be.

    python scripts/check_outputs_current.py [--rtol 1e-5] [--atol 1e-9]

Exit status 0 if everything matches within tolerance, 1 otherwise. The worst
relative deviation seen is always reported, so slow drift is visible long
before it trips the threshold.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from pathlib import Path

#: Directories and files whose generated contents are checked.
TARGETS = ("outputs", "test-results", "docs/spec.md", "docs/validation_report.md")

#: Plots are excluded. matplotlib does not render byte identically across
#: versions, fonts or freetype builds, so comparing them would fail for reasons
#: that have nothing to do with the design. The workflow checks separately that
#: every plot was produced and is non-empty.
SKIP_SUFFIXES = {".png", ".pdf", ".svg", ".jpg"}

NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--", *TARGETS],
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines()
            if p and Path(p).suffix.lower() not in SKIP_SUFFIXES]


def committed(path: str) -> str | None:
    r = subprocess.run(["git", "show", f"HEAD:{path}"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def tokenise(line: str) -> list[tuple[bool, str]]:
    """Split a line into (is_number, text) pieces."""
    out: list[tuple[bool, str]] = []
    pos = 0
    for m in NUMBER.finditer(line):
        if m.start() > pos:
            out.append((False, line[pos:m.start()]))
        out.append((True, m.group()))
        pos = m.end()
    if pos < len(line):
        out.append((False, line[pos:]))
    return out


def close_enough(a: str, b: str, rtol: float, atol: float) -> tuple[bool, float]:
    x, y = float(a), float(b)
    if x == y:
        return True, 0.0
    diff = abs(x - y)
    scale = max(abs(x), abs(y))
    rel = diff / scale if scale else math.inf
    return diff <= atol or rel <= rtol, rel


def compare(path: str, old: str, new: str, rtol: float, atol: float):
    """Yield problem descriptions, and return the worst relative deviation."""
    problems: list[str] = []
    worst = 0.0
    old_lines = old.splitlines()
    new_lines = new.splitlines()

    if len(old_lines) != len(new_lines):
        problems.append(f"{path}: line count {len(old_lines)} -> {len(new_lines)}")
        return problems, worst

    for n, (lo, ln) in enumerate(zip(old_lines, new_lines), start=1):
        if lo == ln:
            continue
        to, tn = tokenise(lo), tokenise(ln)
        if len(to) != len(tn) or [t[0] for t in to] != [t[0] for t in tn]:
            problems.append(f"{path}:{n}: structure changed\n    was: {lo}\n    now: {ln}")
            continue
        for (is_num, a), (_, b) in zip(to, tn):
            if is_num:
                ok, rel = close_enough(a, b, rtol, atol)
                worst = max(worst, rel if math.isfinite(rel) else 0.0)
                if not ok:
                    problems.append(
                        f"{path}:{n}: {a} -> {b}  (relative {rel:.2e}, "
                        f"tolerance {rtol:.0e})")
            elif a != b:
                problems.append(f"{path}:{n}: text changed {a!r} -> {b!r}")
    return problems, worst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtol", type=float, default=1e-5,
                    help="relative tolerance for numbers (default 1e-5, about "
                         "eight times the observed cross platform spread)")
    ap.add_argument("--atol", type=float, default=1e-9,
                    help="absolute tolerance, for values near zero")
    args = ap.parse_args()

    files = tracked_files()
    if not files:
        print("no generated files are tracked; nothing to check", file=sys.stderr)
        return 1

    all_problems: list[str] = []
    worst = 0.0
    worst_file = ""
    missing = []

    for path in files:
        old = committed(path)
        if old is None:
            missing.append(path)
            continue
        p = Path(path)
        if not p.exists():
            all_problems.append(f"{path}: committed but not regenerated")
            continue
        new = p.read_text(encoding="utf-8")
        problems, w = compare(path, old, new, args.rtol, args.atol)
        all_problems += problems
        if w > worst:
            worst, worst_file = w, path

    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *TARGETS],
        capture_output=True, text=True, check=True).stdout.split()
    untracked = [p for p in untracked if Path(p).suffix.lower() not in SKIP_SUFFIXES]

    print(f"compared {len(files)} generated files against HEAD")
    print(f"worst relative deviation {worst:.2e}"
          + (f" in {worst_file}" if worst_file else "")
          + f", tolerance {args.rtol:.0e}")

    if untracked:
        all_problems += [f"{p}: produced but never committed" for p in untracked]
    if missing:
        all_problems += [f"{p}: tracked but missing from HEAD" for p in missing]

    if all_problems:
        print("\nFAILED. Run 'make demo' and commit the result.\n", file=sys.stderr)
        for p in all_problems[:40]:
            print("  " + p, file=sys.stderr)
        if len(all_problems) > 40:
            print(f"  ... and {len(all_problems) - 40} more", file=sys.stderr)
        return 1

    print("committed outputs match a fresh run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
