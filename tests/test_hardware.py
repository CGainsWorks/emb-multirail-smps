"""The board data the KiCad schematic is generated from and checked against.

These run without KiCad. The checks that need it, ERC, DRC and the exported
netlist against the simulation, run in CI through scripts/kicad/run_checks.sh.
"""

import importlib.util
from pathlib import Path

import pytest

from smps import components as C
from smps import hardware as H
from smps.spec import rail

ROOT = Path(__file__).resolve().parents[1]


def _checker():
    path = ROOT / "scripts" / "kicad" / "check_netlist.py"
    spec = importlib.util.spec_from_file_location("check_netlist", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_part_has_a_footprint_a_maker_and_a_part_number():
    for p in H.board():
        assert ":" in p.footprint, p.ref
        assert p.manufacturer and p.mpn, p.ref
        assert p.basis in {"model", "datasheet", "choice"}, p.ref


def test_every_modelled_value_is_the_one_the_simulation_uses():
    d = H.by_ref()
    assert d["L1"].nominal == C.BUCK5["L_H"]
    assert d["L2"].nominal == C.BUCK3V3["L_H"]
    assert d["L3"].nominal == C.BOOST12["L_H"]
    assert d["Rs1"].nominal == C.BUCK5["r_sense_ohm"]
    assert d["Rs2"].nominal == C.BOOST12["r_sense_ohm"]
    assert d["Rpl1"].nominal == C.LDO1V8["preload_r_ohm"]


def test_each_rail_regulates_within_one_percent_of_nominal():
    d = H.by_ref()
    for ctl in H.controllers():
        top = sum(d[r].nominal for r in ctl.divider_top)
        v = ctl.v_ref_v * (1 + top / d[ctl.divider_bottom].nominal)
        assert v == pytest.approx(rail(ctl.rail).v_out_v, rel=0.01), ctl.rail


def test_the_value_reader_understands_kicad_values():
    read = _checker().parse_value
    assert read("26.1k") == pytest.approx(26100)
    assert read("15nF") == pytest.approx(15e-9)
    assert read("6.8uH") == pytest.approx(6.8e-6)
    assert read("5m") == pytest.approx(5e-3)
    assert read("0") == 0
    with pytest.raises(ValueError):
        read("LTC3891EFE#PBF")


def test_every_ngspice_deck_element_is_accounted_for():
    """A new element in a deck has to be either matched to a part on the board
    or named as something the board does not have."""
    chk = _checker()
    for deck, spec in chk.DECK_MAP.items():
        elements = chk.read_deck(ROOT / "outputs" / "netlists" / "ngspice" / deck)
        assert set(elements) == set(spec["parts"]) | set(spec["model_only"]), deck


def test_bill_of_materials_counts_every_part_once():
    rows = H.bom_rows()
    assert sum(r["qty"] for r in rows) == len(H.board())
    refs = [r for row in rows for r in row["refs"].split()]
    assert len(refs) == len(set(refs)) == len(H.board())
