"""The SPICE decks, and the claim that they run.

An earlier version of this repository said the decks "run in LTspice and in
ngspice". Nothing had ever executed one, and on inspection the claim was false:
``Rser=`` on a reactive component, ``IF()`` and ``LIMIT()`` are LTspice
extensions that ngspice rejects. These tests exist so that claim cannot come
back.

The static tests run everywhere. The one that actually invokes ngspice skips
when it is not installed, which is the normal case on a development machine and
never the case in CI.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from smps import design as D
from smps.spice import LTSPICE_ONLY, ltspice_decks, ngspice_decks

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Dialect
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name,text", sorted(ngspice_decks().items()))
def test_ngspice_decks_contain_no_ltspice_only_syntax(name, text):
    found = [tok for tok in LTSPICE_ONLY if tok.lower() in text.lower()]
    assert not found, f"{name} uses LTspice only syntax: {found}"


def test_the_two_dialects_are_actually_different():
    """If they were interchangeable there would be no reason to emit both, and
    the honest thing would be to say so rather than ship two copies."""
    ng, lt = ngspice_decks(), ltspice_decks()
    assert set(ng) == set(lt)
    assert all(ng[k] != lt[k] for k in ng)
    # The LTspice decks are the ones allowed to use its extensions, and at
    # least one of them does, or the split would be pointless.
    assert any(tok.lower() in "".join(lt.values()).lower() for tok in LTSPICE_ONLY)


@pytest.mark.parametrize("name,text", sorted(ngspice_decks().items()))
def test_ngspice_deck_is_well_formed(name, text):
    lines = [l for l in text.splitlines() if l.strip()]
    assert lines[0].startswith("*"), "a SPICE deck's first line is a comment"
    assert lines[-1].strip().lower() == ".end"
    # Every ngspice deck drives its own analysis from a control block, which is
    # what lets a batch run write machine readable output.
    assert ".control" in text and ".endc" in text
    assert "quit" in text


@pytest.mark.parametrize("name,text", sorted(ltspice_decks().items()))
def test_ltspice_deck_says_it_has_never_been_run(name, text):
    assert "NOT EXECUTED BY CI" in text


@pytest.mark.parametrize("name,text",
                         sorted({**ngspice_decks(), **ltspice_decks()}.items()))
def test_deck_numbers_are_finite(name, text):
    for token in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text):
        assert float(token) == float(token)
    assert "nan" not in text.lower()
    assert "None" not in text


# --------------------------------------------------------------------------
# The decks carry the design, not a copy of it
# --------------------------------------------------------------------------

def test_ac_decks_carry_the_values_the_design_module_chose():
    ng = ngspice_decks()
    c5 = D.buck5_compensator()
    assert f"{c5.rc_ohm:.6g}" in ng["comp_buck5_typeii_ac.cir"]
    assert f"{c5.cc_f:.6g}" in ng["comp_buck5_typeii_ac.cir"]

    c3 = D.buck3v3_compensator()
    assert f"{c3.rf_ohm:.6g}" in ng["comp_buck3v3_typeiii_ac.cir"]
    assert f"{c3.cf3_f:.6g}" in ng["comp_buck3v3_typeiii_ac.cir"]

    c12 = D.boost12_compensator()
    assert f"{c12.rc_ohm:.6g}" in ng["comp_boost12_typeii_ac.cir"]


def test_no_switching_deck_for_the_current_mode_rails():
    """Emitting one would mean inventing a controller's internal slope
    compensation, blanking and latch. It would run, it would look convincing
    and it would validate nothing."""
    names = " ".join(ngspice_decks())
    assert "buck5_transient" not in names
    assert "boost12_transient" not in names
    assert "buck3v3_transient.cir" in names


# --------------------------------------------------------------------------
# Actually running it
# --------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("ngspice") is None,
                    reason="ngspice is not installed; CI installs it")
def test_ngspice_agrees_with_the_models():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_ngspice.py")],
                       capture_output=True, text=True, cwd=ROOT, timeout=1800)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_runner_skips_cleanly_when_ngspice_is_absent():
    """The script has to be usable on a machine without ngspice, otherwise
    nobody runs it before pushing."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_ngspice.py"),
                        "--ngspice", "definitely-not-a-real-binary",
                        "--skip-missing"],
                       capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert r.returncode == 0
    assert "SKIPPED" in r.stdout
