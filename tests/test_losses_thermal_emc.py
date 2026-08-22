"""Loss model, power tree bookkeeping, thermal derating and the EMC pre-scan."""

import numpy as np
import pytest

from smps import components as C
from smps.emc import (InputFilter, en55032_class_b_qp_dbuv, middlebrook,
                      prescan, trapezoid_harmonics)
from smps.losses import (efficiency_curve, rail_losses, solve_power_tree,
                         system_efficiency_curve)
from smps.spec import SYSTEM, rail
from smps.thermal import (BOARD, RTH_JB_KW, T_J_MAX_C, device_powers,
                          max_ambient_c, solve_thermal)

CORNERS = (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v)


# --------------------------------------------------------------------------
# Losses
# --------------------------------------------------------------------------

@pytest.mark.parametrize("v_in", CORNERS)
def test_power_tree_conserves_power(v_in):
    t = solve_power_tree(v_in)
    accounted = t.p_useful_w + sum(lb.total_w for lb in t.per_rail.values())
    assert accounted == pytest.approx(t.p_in_w, rel=1e-9)


@pytest.mark.parametrize("v_in", CORNERS)
def test_efficiency_is_physical(v_in):
    t = solve_power_tree(v_in)
    assert 0.70 < t.efficiency < 0.95
    for lb in t.per_rail.values():
        assert 0.0 < lb.efficiency < 1.0
        assert all(v >= 0 for v in lb.terms.values())


def test_the_5v_stage_really_does_carry_the_downstream_rails():
    """The connector rating of the 5 V rail is 1.5 A. The stage has to deliver
    far more than that because it feeds the other two switchers. Getting this
    wrong by hand is how a power budget ends up undersized."""
    t = solve_power_tree(SYSTEM.vin_nom_v)
    r5 = rail("+5V")
    assert t.per_rail["+5V"].i_out_a > 2.5 * r5.i_external_a
    assert t.per_rail["+5V"].i_out_a <= r5.i_max_a


def test_ldo_efficiency_is_close_to_the_voltage_ratio():
    lb = rail_losses("+1V8A", rail("+3V3").v_out_v, 0.5)
    ratio = rail("+1V8A").v_out_v / rail("+3V3").v_out_v
    assert lb.efficiency == pytest.approx(ratio, rel=0.10)


def test_efficiency_falls_at_very_light_load():
    """Fixed losses, gate drive and quiescent current, dominate at light load."""
    i, eta = efficiency_curve("+5V", SYSTEM.vin_nom_v)
    assert eta[0] < eta[-1]
    assert eta.max() > 0.9


def test_switching_loss_grows_with_input_voltage():
    lo = rail_losses("+5V", SYSTEM.vin_min_v, 4.6).terms["hs_switching_w"]
    hi = rail_losses("+5V", SYSTEM.vin_max_v, 4.6).terms["hs_switching_w"]
    assert hi > 4 * lo


def test_system_efficiency_curve_is_monotonic_enough_to_plot():
    frac, eta, _ = system_efficiency_curve(SYSTEM.vin_nom_v)
    assert len(frac) == len(eta)
    assert np.all(np.isfinite(eta))
    assert eta[-1] > eta[0]


# --------------------------------------------------------------------------
# Thermal
# --------------------------------------------------------------------------

def test_every_device_has_a_thermal_resistance():
    t = solve_power_tree(SYSTEM.vin_nom_v)
    assert set(device_powers(t)) == set(RTH_JB_KW)


@pytest.mark.parametrize("v_in", CORNERS)
def test_junctions_stay_under_the_limit_at_the_specified_ambient(v_in):
    res = solve_thermal(v_in, SYSTEM.ambient_max_c)
    name, hottest = res.hottest
    assert hottest < T_J_MAX_C, f"{name} at {hottest:.1f} C"


@pytest.mark.parametrize("v_in", CORNERS)
def test_ambient_headroom_exists_at_full_load(v_in):
    assert max_ambient_c(v_in) > SYSTEM.ambient_max_c


def test_derating_gives_more_ambient_headroom_at_lower_load():
    assert max_ambient_c(SYSTEM.vin_max_v, 0.5) > max_ambient_c(SYSTEM.vin_max_v, 1.0)


def test_board_thermal_resistance_is_in_a_plausible_range():
    """Roughly 5 to 15 K/W is what a board this size does in still air. This
    test exists so that an accidental edit to the board geometry gets caught,
    not because 7.4 K/W is a measured number. It is not."""
    assert 4.0 < BOARD.rth_ba_kw < 16.0


# --------------------------------------------------------------------------
# EMC
# --------------------------------------------------------------------------

def test_limit_line_matches_the_published_breakpoints():
    f = np.array([150e3, 500e3, 1e6, 5e6, 30e6])
    limits = en55032_class_b_qp_dbuv(f)
    assert limits[0] == pytest.approx(66.0, abs=0.01)
    assert limits[1] == pytest.approx(56.0, abs=0.01)
    assert limits[2] == pytest.approx(56.0, abs=0.01)
    assert limits[3] == pytest.approx(60.0, abs=0.01)
    assert limits[4] == pytest.approx(60.0, abs=0.01)
    assert np.isnan(en55032_class_b_qp_dbuv(np.array([100e3]))[0])


def test_trapezoidal_edges_roll_the_spectrum_off_faster_than_a_rectangle():
    """A rectangular pulse rolls off at 20 dB per decade for ever, which is
    physically wrong and makes a high frequency prediction meaningless."""
    f, sharp = trapezoid_harmonics(4.0, 5.0, 0.2, 500e3, 1e-12, 1e-12, 200)
    _, real = trapezoid_harmonics(4.0, 5.0, 0.2, 500e3, 12e-9, 12e-9, 200)
    assert real[-1] < 0.5 * sharp[-1]
    assert real[0] == pytest.approx(sharp[0], rel=0.02)


@pytest.mark.parametrize("v_in", CORNERS)
def test_conducted_prescan_stays_under_the_reference_envelope(v_in):
    tree = solve_power_tree(v_in)
    res = prescan(v_in, tree.per_rail["+5V"].i_out_a)
    assert res.worst_margin_db > 0.0, (
        f"Vin {v_in} V: {res.worst_margin_db:.1f} dB at "
        f"{res.worst_frequency_hz/1e3:.0f} kHz")


@pytest.mark.parametrize("v_in", CORNERS)
def test_input_filter_satisfies_middlebrook(v_in):
    """A converter in regulation is a constant power load, so it looks like a
    negative resistance. The filter output impedance has to stay well below the
    magnitude of that resistance or the pair oscillates."""
    tree = solve_power_tree(v_in)
    mb = middlebrook(v_in, tree.p_in_w)
    assert mb.separation_db > 6.0, (
        f"Vin {v_in} V: Zout peak {mb.peak_z_out_ohm:.2f} ohm at "
        f"{mb.peak_f_hz/1e3:.1f} kHz against |Zin| {mb.z_in_ohm:.2f} ohm")


def test_the_bulk_capacitance_is_what_makes_the_input_filter_benign():
    """The peak of the filter output impedance goes as ``Q sqrt(L/C)``, so the
    bulk capacitor is sized by the stability requirement, not by the ripple
    requirement. 47 uF is enough for the ripple and fails Middlebrook; the
    220 uF actually fitted passes. This test is the record of that decision so
    that nobody shrinks the part to save board area."""
    tree = solve_power_tree(SYSTEM.vin_min_v)
    fitted = middlebrook(SYSTEM.vin_min_v, tree.p_in_w)
    smaller = middlebrook(SYSTEM.vin_min_v, tree.p_in_w,
                          InputFilter(cbulk_f=47e-6, cbulk_esr_ohm=25e-3))
    assert fitted.separation_db > 6.0
    assert smaller.separation_db < 6.0
    assert smaller.peak_z_out_ohm > 3 * fitted.peak_z_out_ohm


def test_bulk_capacitor_esr_contributes_damping():
    """Less of the damping than the capacitance contributes, but not nothing,
    which is why the part is specified as aluminium polymer rather than left as
    "220 uF, any technology"."""
    tree = solve_power_tree(SYSTEM.vin_min_v)
    fitted = middlebrook(SYSTEM.vin_min_v, tree.p_in_w)
    zero_esr = middlebrook(SYSTEM.vin_min_v, tree.p_in_w,
                           InputFilter(cbulk_esr_ohm=1e-4))
    assert zero_esr.peak_z_out_ohm > fitted.peak_z_out_ohm


def test_more_input_inductance_helps_emissions_and_hurts_stability():
    """The trade-off the input filter design turns on, asserted so that the
    chosen value is visibly a choice rather than a default."""
    tree = solve_power_tree(SYSTEM.vin_min_v)
    i5 = tree.per_rail["+5V"].i_out_a
    small = InputFilter(l_dm_h=2.2e-6)
    large = InputFilter(l_dm_h=47e-6)
    assert (prescan(SYSTEM.vin_min_v, i5, large).worst_margin_db
            > prescan(SYSTEM.vin_min_v, i5, small).worst_margin_db)
    assert (middlebrook(SYSTEM.vin_min_v, tree.p_in_w, large).separation_db
            < middlebrook(SYSTEM.vin_min_v, tree.p_in_w, small).separation_db)


def test_ceramic_derating_is_applied_everywhere_it_should_be():
    """Every bank in components.py must be below its nameplate value, because
    an MLCC under DC bias is. Forgetting this is the classic reason a bench
    ripple measurement comes in two or three times worse than the model."""
    assert C.BUCK5["Cout_F"] < 3 * 22e-6
    assert C.BUCK3V3["Cout_F"] < 2 * 22e-6
    assert C.BOOST12["Cout_F"] < 2 * 22e-6
    assert C.LDO1V8["Cout_F"] < 10e-6
    assert all(0.3 <= v <= 0.95 for v in C.CERAMIC_DERATING.values())
