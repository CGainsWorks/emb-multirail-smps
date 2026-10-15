#!/usr/bin/env python3
"""Run the generated decks in ngspice and compare the results with the models.

This is the third independent route to the same numbers. The first is the hand
derivation, the second is the switching simulator written for this repository,
and this is a forty year old general purpose circuit simulator that knows
nothing about any of it.

The compensator decks are the sharpest check available without hardware. Each
is passive components plus one ideal controlled source, so ngspice and the
closed form in :mod:`smps.compensation` are solving the same linear system by
completely different means. They have to agree to numerical precision, and if
they do not, the closed form is the one to doubt.

    python scripts/run_ngspice.py [--ngspice PATH] [--skip-missing]

Exit status 0 if every comparison passes, 1 if any fails, and 2 if ngspice is
not installed, unless ``--skip-missing`` is given, which turns that into a
skip. CI installs ngspice, so there it is a real failure.
"""

from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simulation"))

from smps import design as D  # noqa: E402
from smps.emc import InputFilter  # noqa: E402
from smps.spec import rail  # noqa: E402

DECKS = ROOT / "outputs" / "netlists" / "ngspice"

#: Where each AC deck's comparison band is. Below the first decade and above
#: the last the networks are dominated by component values that are exact in
#: both tools anyway; the interesting disagreement, if any, is in the middle.
AC_BAND = {
    "comp_buck5_typeii_ac.cir": (10.0, 1e6),
    "comp_boost12_typeii_ac.cir": (10.0, 1e6),
    "comp_buck3v3_typeiii_ac.cir": (10.0, 1e6),
    "input_filter_ac.cir": (1e5, 2e7),
}

GAIN_TOL_DB = 0.05
PHASE_TOL_DEG = 0.5


def find_ngspice(explicit: str | None) -> str | None:
    if explicit:
        return explicit if Path(explicit).exists() or shutil.which(explicit) else None
    return shutil.which("ngspice")


def run_deck(exe: str, deck: Path, workdir: Path) -> tuple[str, str]:
    """Run one deck in batch mode and return (stdout, stderr)."""
    text = deck.read_text(encoding="utf-8")
    local = workdir / deck.name
    local.write_text(text, encoding="utf-8")
    r = subprocess.run([exe, "-b", local.name], cwd=workdir,
                       capture_output=True, text=True, timeout=900)
    return r.stdout, r.stderr


def read_wrdata(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read an ngspice ``wrdata`` file holding one complex vector.

    The layout is one row per frequency: scale, real, imaginary. ngspice
    repeats the scale column for every vector written, so taking the first
    three columns is correct for a single vector and is checked below.
    """
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            rows.append([float(x) for x in parts])
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"{path.name} holds no numeric rows")
    a = np.array(rows)
    if a.shape[1] < 3:
        raise ValueError(f"{path.name} has {a.shape[1]} columns, expected at least 3")
    return a[:, 0], a[:, 1] + 1j * a[:, 2]


def expected(deck_name: str, f: np.ndarray) -> np.ndarray:
    """What the Python model says the deck's measured node should be."""
    if deck_name == "comp_buck5_typeii_ac.cir":
        # Deck is wired non-inverting so it matches the repository's Gc
        # convention directly. See smps.spice.type_ii_ac.
        return D.buck5_compensator().response(f)
    if deck_name == "comp_boost12_typeii_ac.cir":
        return D.boost12_compensator().response(f)
    if deck_name == "comp_buck3v3_typeiii_ac.cir":
        # The deck is physically wired, so its amplifier inverts and the node
        # is -Zf/Zi. The repository's Gc drops that inversion because it is
        # supplied by the negative feedback, hence the minus sign here. The
        # ideal amplifier in the deck has no gain bandwidth limit, so compare
        # against the ideal form.
        from dataclasses import replace
        c = replace(D.buck3v3_compensator(), gbw_hz=float("inf"))
        return -c.response(f)
    if deck_name == "input_filter_ac.cir":
        # One amp injected at the converter port, so the node voltage is the
        # transfer impedance. The model returns a magnitude only, so only
        # magnitudes are compared for this one.
        return InputFilter().transfer_ohm(f).astype(complex)
    raise KeyError(deck_name)


def compare_ac(deck_name: str, f: np.ndarray, got: np.ndarray) -> list[str]:
    lo, hi = AC_BAND[deck_name]
    band = (f >= lo) & (f <= hi)
    f, got = f[band], got[band]
    want = expected(deck_name, f)

    problems = []
    gain_err = np.abs(20 * np.log10(np.abs(got) / np.abs(want)))
    worst_g = float(np.max(gain_err))
    if worst_g > GAIN_TOL_DB:
        i = int(np.argmax(gain_err))
        problems.append(f"{deck_name}: gain differs by {worst_g:.3f} dB at "
                        f"{f[i]:.4g} Hz (tolerance {GAIN_TOL_DB} dB)")

    worst_p = 0.0
    if deck_name != "input_filter_ac.cir":
        d = np.degrees(np.angle(got / want))
        d = (d + 180) % 360 - 180
        worst_p = float(np.max(np.abs(d)))
        if worst_p > PHASE_TOL_DEG:
            i = int(np.argmax(np.abs(d)))
            problems.append(f"{deck_name}: phase differs by {worst_p:.3f} deg at "
                            f"{f[i]:.4g} Hz (tolerance {PHASE_TOL_DEG} deg)")

    print(f"  {deck_name:34s} {len(f):4d} points  "
          f"worst gain {worst_g:.4f} dB"
          + (f", worst phase {worst_p:.3f} deg" if worst_p else ", magnitude only"))
    return problems


MEAS = re.compile(r"^\s*(\w+)\s*=\s*([-+0-9.eE]+)", re.MULTILINE)


def compare_transient(stdout: str) -> list[str]:
    vals = {m.group(1).lower(): float(m.group(2)) for m in MEAS.finditer(stdout)}
    need = {"vavg", "vmax", "vmin"}
    if not need <= vals.keys():
        return [f"buck3v3_transient.cir: ngspice reported {sorted(vals)}, "
                f"expected {sorted(need)}"]

    r = rail("+3V3")
    c = D.buck3v3_compensator()
    v_target = 0.8 * (c.r1_ohm + c.rbot_ohm) / c.rbot_ohm
    ripple_mv = 1e3 * (vals["vmax"] - vals["vmin"])

    problems = []
    # Half a percent. The two simulators share component values and nothing
    # else: different integration, different modulator implementation,
    # different switch model.
    if abs(vals["vavg"] / v_target - 1) > 5e-3:
        problems.append(f"buck3v3_transient.cir: settled {vals['vavg']:.4f} V "
                        f"against {v_target:.4f} V from the divider")
    if ripple_mv > 1e3 * r.v_ripple_max_vpp:
        problems.append(f"buck3v3_transient.cir: ripple {ripple_mv:.2f} mVpp "
                        f"exceeds the {1e3 * r.v_ripple_max_vpp:.0f} mVpp limit")

    print(f"  {'buck3v3_transient.cir':34s} settled {vals['vavg']:.4f} V "
          f"(divider says {v_target:.4f} V), ripple {ripple_mv:.2f} mVpp")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ngspice", default=None, help="path to the ngspice binary")
    ap.add_argument("--skip-missing", action="store_true",
                    help="exit 0 instead of 2 when ngspice is not installed")
    args = ap.parse_args()

    exe = find_ngspice(args.ngspice)
    if exe is None:
        msg = ("ngspice not found. Install it with 'apt-get install ngspice', "
               "'brew install ngspice' or 'choco install ngspice'.")
        if args.skip_missing:
            print(f"SKIPPED: {msg}")
            return 0
        print(f"ERROR: {msg}", file=sys.stderr)
        return 2

    ver = subprocess.run([exe, "-v"], capture_output=True, text=True)
    first = (ver.stdout or ver.stderr).strip().splitlines()
    print(f"ngspice: {first[0] if first else exe}")
    print(f"decks:   {DECKS}")

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for deck in sorted(DECKS.glob("*.cir")):
            out, err = run_deck(exe, deck, work)
            lowered = (out + err).lower()
            if "error" in lowered or "fatal" in lowered:
                problems.append(f"{deck.name}: ngspice reported an error\n"
                                + "\n".join("      " + l
                                            for l in (out + err).splitlines()[:25]))
                continue

            if deck.name == "buck3v3_transient.cir":
                problems += compare_transient(out)
                continue

            data = sorted(work.glob("*.dat"))
            match = [d for d in data if d.stat().st_mtime_ns]
            if not match:
                problems.append(f"{deck.name}: wrote no data file")
                continue
            newest = max(match, key=lambda p: p.stat().st_mtime_ns)
            try:
                f, v = read_wrdata(newest)
            except ValueError as exc:
                problems.append(f"{deck.name}: {exc}")
                continue
            problems += compare_ac(deck.name, f, v)
            newest.unlink()

    if problems:
        print("\nFAILED\n", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1

    print("\nngspice agrees with the models on every deck")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
