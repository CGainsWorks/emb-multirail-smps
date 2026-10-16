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
from smps.netlist import (SCH_NETS, SCH_PARTS, netlist_stats,
                          protel_netlist)

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
    for expected in ("J1-2", "U1-2", "U3-11", "U4-9", "U5-5"):
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
# BOM honesty
# --------------------------------------------------------------------------

def test_every_bom_line_says_what_has_to_be_verified():
    for p in C.BOM:
        assert p.verify.strip(), f"{p.ref} has no verification note"
        assert p.qty >= 1


def test_no_bom_line_claims_a_verified_part_number():
    """Parts have been selected and their headline figures read, but no part
    has had its whole data sheet checked against the model, so no BOM line may
    present one as verified."""
    for row in C.bom_rows():
        assert row["mpn_status"] in {"selected, data sheet check pending",
                                     "design value"}
    from smps import hardware as H
    for row in H.bom_rows():
        assert row["status"] == "selected, data sheet check pending"
        assert row["mpn"] and row["manufacturer"]


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
    across platforms. One percent is a design change.

    close_enough returns how much of the allowed tolerance the difference
    used, so under 1.0 passes and over 1.0 fails.
    """
    c = _checker()
    ok, used = c.close_enough("4.984290", "4.984295", 1e-5, 5e-4)
    assert ok and used < 0.1
    ok, used = c.close_enough("4.984290", "5.034295", 1e-5, 5e-4)
    assert not ok and used > 10


def test_near_zero_derived_columns_are_judged_on_the_absolute_floor():
    """The regulation deviations are differences of two nearly equal voltages,
    so their relative spread between platforms reaches 100 percent while their
    absolute spread is meaningless. Relative tolerance alone would fail the
    build over the solver's own resolution."""
    c = _checker()
    ok, used = c.close_enough("-0.0003", "-0.0001", 1e-5, 5e-4)
    assert ok and used < 1.0
    # A real change in the same column is still caught.
    ok, _ = c.close_enough("-0.0003", "-0.05", 1e-5, 5e-4)
    assert not ok


def test_a_changed_word_is_caught_even_though_numbers_are_tolerant():
    c = _checker()
    problems, _ = c.compare("f", "rail,v_out\n+5V,5.0\n", "rail,v_in\n+5V,5.0\n",
                            1e-5, 1e-9)
    assert problems and "text changed" in problems[0]


def test_a_dropped_row_is_caught():
    c = _checker()
    problems, _ = c.compare("f", "a\nb\nc\n", "a\nb\n", 1e-5, 1e-9)
    assert problems and "line count" in problems[0]
