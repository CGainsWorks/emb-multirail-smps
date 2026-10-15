"""Netlist integrity, SPICE deck sanity and the honesty of the BOM.

An electrical netlist that a designer imports into Altium has to be correct in
ways that are cheap to check and expensive to discover on a fabricated board: a
net with one pin on it is a wire to nowhere, a part with no nets is a part
somebody forgot to connect, and a pin listed twice is usually a copy and paste
that put a component on the wrong node.
"""

import re

import pytest

from smps import components as C
from smps.netlist import (SCH_NETS, SCH_PARTS, netlist_stats, protel_netlist,
                          spice_decks)

DESIGNATORS = {d for d, _, _ in SCH_PARTS}
ALL_PINS = [p for pins in SCH_NETS.values() for p in pins]


def test_every_net_connects_at_least_two_pins():
    lonely = {n: pins for n, pins in SCH_NETS.items() if len(pins) < 2}
    assert not lonely, f"nets with fewer than two pins: {lonely}"


def test_every_pin_reference_names_a_part_that_exists():
    unknown = sorted({p.split("-")[0] for p in ALL_PINS} - DESIGNATORS)
    assert not unknown, f"pins on parts not in the BOM: {unknown}"


def test_every_part_is_connected_to_something():
    orphans = sorted(d for d in DESIGNATORS
                     if not any(p.startswith(d + "-") for p in ALL_PINS))
    assert not orphans, f"parts with no nets: {orphans}"


def test_no_pin_appears_on_two_nets():
    seen, dupes = set(), []
    for net, pins in SCH_NETS.items():
        for p in pins:
            if p in seen:
                dupes.append((p, net))
            seen.add(p)
    assert not dupes, f"pins shorted across nets: {dupes}"


def test_designators_are_unique():
    assert len(DESIGNATORS) == len(SCH_PARTS)


def test_ground_reaches_every_stage():
    gnd = set(SCH_NETS["GND"])
    for expected in ("J1-2", "U1-2", "U3-2", "U4-2", "U5-2"):
        assert expected in gnd


def test_protel_netlist_blocks_are_well_formed():
    text = protel_netlist()
    assert text.count("[") == text.count("]") == len(SCH_PARTS)
    assert text.count("(") == text.count(")") == len(SCH_NETS)
    # A Protel component block is the open marker, designator, footprint,
    # comment, then the blank fields Altium expects, then the close marker.
    block = text.split("]")[0].splitlines()
    assert block[0] == "["
    assert block[1:4] == list(SCH_PARTS[0])[:1] + [SCH_PARTS[0][1], SCH_PARTS[0][2]]
    assert all(line == "" for line in block[4:])
    assert len(block) == 7


def test_netlist_stats_agree_with_the_data():
    s = netlist_stats()
    assert s["parts"] == len(SCH_PARTS)
    assert s["nets"] == len(SCH_NETS)
    assert s["single_pin_nets"] == 0
    assert s["duplicate_pin_connections"] == 0
    assert s["parts_with_no_net"] == 0


# --------------------------------------------------------------------------
# SPICE decks
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name,text", sorted(spice_decks().items()))
def test_deck_is_syntactically_plausible(name, text):
    lines = [l for l in text.splitlines() if l.strip()]
    assert lines[0].startswith("*"), "a SPICE deck's first line is a comment"
    assert lines[-1].strip().lower() == ".end"
    assert any(l.lower().startswith((".ac", ".tran")) for l in lines)
    # No unresolved format placeholders left in a generated file.
    assert "{}" not in text and "None" not in text


@pytest.mark.parametrize("name,text", sorted(spice_decks().items()))
def test_deck_component_values_are_finite_numbers(name, text):
    for token in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text):
        assert float(token) == float(token)  # not NaN


def test_ac_decks_carry_the_values_the_design_module_chose():
    from smps import design as D

    c5 = D.buck5_compensator()
    deck = spice_decks()["comp_buck5_typeii_ac.cir"]
    assert f"{c5.rc_ohm:.6g}" in deck
    assert f"{c5.cc_f:.6g}" in deck

    c3 = D.buck3v3_compensator()
    deck = spice_decks()["comp_buck3v3_typeiii_ac.cir"]
    assert f"{c3.rf_ohm:.6g}" in deck
    assert f"{c3.cf3_f:.6g}" in deck


def test_no_switching_deck_is_emitted_for_the_current_mode_rails():
    """Emitting one would mean inventing a controller's internal slope
    compensation, blanking and latch. It would run, it would look convincing
    and it would validate nothing. See spice_decks.__doc__."""
    names = " ".join(spice_decks())
    assert "buck5" not in names.replace("comp_buck5", "")
    assert "boost12_transient" not in names


# --------------------------------------------------------------------------
# BOM honesty
# --------------------------------------------------------------------------

def test_every_bom_line_says_what_has_to_be_verified():
    for p in C.BOM:
        assert p.verify.strip(), f"{p.ref} has no verification note"
        assert p.qty >= 1


def test_no_bom_line_claims_a_verified_part_number():
    """Nothing in this repository has been checked against a live datasheet, so
    no BOM line may present a manufacturer part number as confirmed."""
    for row in C.bom_rows():
        assert row["mpn_status"] in {"candidate, unverified", "design value",
                                     "not selected"}


def test_verify_list_covers_the_whole_bom():
    assert len(C.verify_rows()) == len(C.BOM)


def test_compensation_parts_are_marked_as_design_values_not_products():
    comp_refs = [p for p in C.BOM
                 if "compensation network" in p.description.lower()]
    assert comp_refs
    for p in comp_refs:
        assert p.candidate_mpn == "-"


# --------------------------------------------------------------------------
# The outputs-are-current checker
# --------------------------------------------------------------------------

def _checker():
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_outputs_current.py"
    spec = importlib.util.spec_from_file_location("check_outputs_current", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tokeniser_splits_numbers_from_text():
    c = _checker()
    assert c.tokenise("a,1.5e-3,b") == [
        (False, "a,"), (True, "1.5e-3"), (False, ",b")]
    assert c.tokenise("no numbers here") == [(False, "no numbers here")]


def test_numeric_comparison_accepts_solver_noise_and_rejects_real_change():
    """One part per million is what the switching simulator reproduces to
    across platforms. One part per hundred is a design change."""
    c = _checker()
    ok, rel = c.close_enough("4.984290", "4.984295", 1e-5, 1e-9)
    assert ok and rel < 1e-5
    ok, rel = c.close_enough("4.984290", "5.034295", 1e-5, 1e-9)
    assert not ok and rel > 1e-3


def test_a_changed_word_is_caught_even_though_numbers_are_tolerant():
    c = _checker()
    problems, _ = c.compare("f", "rail,v_out\n+5V,5.0\n", "rail,v_in\n+5V,5.0\n",
                            1e-5, 1e-9)
    assert problems and "text changed" in problems[0]


def test_a_dropped_row_is_caught():
    c = _checker()
    problems, _ = c.compare("f", "a\nb\nc\n", "a\nb\n", 1e-5, 1e-9)
    assert problems and "line count" in problems[0]
