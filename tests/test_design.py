"""Specification, sizing, compensator placement and closed loop margins."""

import numpy as np
import pytest

from smps import design as D
from smps.analysis import margins
from smps.compensation import E12, E24, E96, snap
from smps.sizing import all_sizing, f_rhpz_hz
from smps.spec import RAILS, SYSTEM, rail, rail_order, useful_output_power_w
from smps.switching import type_ii_tf, type_iii_tf


# --------------------------------------------------------------------------
# Specification
# --------------------------------------------------------------------------

def test_power_tree_has_no_cycles_and_every_source_exists():
    order = rail_order()
    assert len(order) == len(RAILS)
    seen = {"VIN"}
    for r in order:
        assert r.source in seen
        seen.add(r.name)


def test_connector_current_never_exceeds_stage_rating():
    for r in RAILS:
        assert 0 < r.i_external_a <= r.i_max_a


def test_useful_output_power_matches_the_rail_table():
    assert useful_output_power_w() == pytest.approx(
        5.0 * 1.5 + 3.3 * 2.5 + 12.0 * 0.4 + 1.8 * 0.5)


def test_input_range_is_ordered():
    assert SYSTEM.vin_min_v < SYSTEM.vin_nom_v < SYSTEM.vin_max_v
    assert SYSTEM.vin_max_v < SYSTEM.vin_transient_max_v


# --------------------------------------------------------------------------
# Sizing
# --------------------------------------------------------------------------

def test_every_sizing_requirement_is_met():
    failures = [s for s in all_sizing() if not s.ok]
    assert not failures, "\n".join(
        f"{s.quantity}: required {s.required:.4g} {s.unit}, "
        f"chosen {s.chosen:.4g} {s.unit} ({s.note})" for s in failures)


def test_boost_crossover_stays_well_below_the_right_half_plane_zero():
    r = rail("+12V")
    assert f_rhpz_hz() / r.f_cross_target_hz >= 5.0


def test_boost_rhpz_falls_at_light_load_but_stays_above_crossover():
    """The RHP zero moves with load. Full load is the worst case for a boost,
    so the check above is the binding one, but the light load case is worth
    asserting so that a future change to the load range does not slip past."""
    r = rail("+12V")
    assert f_rhpz_hz(r.i_max_a) < f_rhpz_hz(0.1 * r.i_max_a)
    assert f_rhpz_hz(r.i_max_a) > 5 * r.f_cross_target_hz


# --------------------------------------------------------------------------
# E series
# --------------------------------------------------------------------------

@pytest.mark.parametrize("series", [E12, E24, E96])
def test_snap_returns_a_stocked_value(series):
    for v in (1.03e3, 4.44e-9, 7.7e6, 2.51e-12):
        s = snap(v, series)
        mant = s / 10 ** np.floor(np.log10(s))
        assert min(abs(mant - x) for x in series + [10.0]) < 1e-6
        assert 0.5 < s / v < 2.0


def test_snap_rejects_non_positive():
    with pytest.raises(ValueError):
        snap(0.0)


# --------------------------------------------------------------------------
# Compensators
# --------------------------------------------------------------------------

def test_type_ii_zero_and_pole_land_where_the_design_asked():
    r = rail("+5V")
    c = D.buck5_compensator()
    # The pole is placed at fsw/2, within one E series step.
    assert c.f_pole_hz == pytest.approx(r.f_sw_hz / 2, rel=0.25)
    assert c.f_zero_hz < c.f_pole_hz / 10


def test_type_iii_zeros_below_the_lc_pole_and_poles_above_crossover():
    r = rail("+3V3")
    c = D.buck3v3_compensator()
    for fz in (c.f_zero1_hz, c.f_zero2_hz):
        assert 0.2 * r.f_cross_target_hz > fz > 0.02 * r.f_cross_target_hz
    for fp in (c.f_pole2_hz, c.f_pole3_hz):
        assert fp > 2 * r.f_cross_target_hz


def test_divider_sets_the_right_output_voltage():
    for div, target in ((D.BUCK5_DIVIDER, 5.0), (D.BOOST12_DIVIDER, 12.0)):
        assert div.v_out_v == pytest.approx(target, rel=0.005)


def test_transfer_function_form_matches_the_closed_form_response():
    """``type_ii_tf`` and ``type_iii_tf`` feed the switching simulator, while
    ``TypeII.response`` and ``TypeIII.response`` feed the analytic loop. If
    they ever disagree the comparison between the two is meaningless."""
    from scipy.signal import freqs

    f = np.logspace(1, 5.5, 60)
    w = 2 * np.pi * f

    c2 = D.buck5_compensator()
    _, h = freqs(*type_ii_tf(c2.rc_ohm, c2.cc_f, c2.cp_f, c2.gm_s,
                             c2.ro_ohm, c2.k_div), w)
    assert np.allclose(h, c2.response(f), rtol=1e-9)

    from dataclasses import replace

    c3 = D.buck3v3_compensator()
    _, h = freqs(*type_iii_tf(c3.r1_ohm, c3.r3_ohm, c3.rf_ohm, c3.cf1_f,
                              c3.cf2_f, c3.cf3_f), w)
    # The simulator carries an ideal amplifier, so compare against the ideal
    # analytic response.
    ideal = replace(c3, gbw_hz=float("inf"))
    assert np.allclose(h, ideal.response(f), rtol=1e-9)
    # And confirm the finite gain bandwidth correction is a small correction
    # rather than a different answer, below crossover at least.
    lo = f < 50e3
    assert np.allclose(ideal.response(f)[lo], c3.response(f)[lo], rtol=0.05)


# --------------------------------------------------------------------------
# Closed loop margins, every operating point
# --------------------------------------------------------------------------

def test_every_operating_point_meets_its_margin_targets():
    bad = []
    for res in D.all_loops():
        r = rail(res.rail)
        m = res.margins
        if m.phase_margin_deg < r.phase_margin_target_deg:
            bad.append(f"{res.rail} {res.op}: PM {m.phase_margin_deg:.1f} deg "
                       f"< {r.phase_margin_target_deg:.0f}")
        if np.isfinite(m.gain_margin_db) and m.gain_margin_db < r.gain_margin_target_db:
            bad.append(f"{res.rail} {res.op}: GM {m.gain_margin_db:.1f} dB "
                       f"< {r.gain_margin_target_db:.0f}")
    assert not bad, "\n".join(bad)


def test_crossover_lands_close_to_target_at_the_design_point():
    for res in D.all_loops():
        if not res.is_design_point or res.rail == "+1V8A":
            continue
        target = rail(res.rail).f_cross_target_hz
        assert res.margins.f_cross_hz == pytest.approx(target, rel=0.10)


def test_crossover_stays_below_a_fifth_of_the_switching_frequency():
    """Above about fsw/5 an averaged model stops describing the converter, so a
    design that crosses over up there is not designed, it is hoped."""
    for res in D.all_loops():
        r = rail(res.rail)
        if r.f_sw_hz:
            assert res.margins.f_cross_hz < r.f_sw_hz / 5.0


def test_slope_compensation_keeps_the_sampling_pole_pair_damped():
    """``Se = Sf`` gives ``mc D' = 1`` at every duty ratio, so Q is 2/pi.

    The identity is exact for the lossless duty ratio. The duty ratio actually
    used includes the conduction drops, which pushes D up a little and mc D'
    down by the same little, so the tolerance below is set by how lossy this
    converter is rather than by anything to do with the control design.
    """
    for op in D.buck5_ops():
        loop = D.buck5_loop(op)
        assert loop.mc * (1 - loop.duty) == pytest.approx(1.0, rel=0.06)
        assert loop.q_sampling == pytest.approx(2 / np.pi, rel=0.15)


def test_ldo_is_stable_across_the_whole_load_range():
    from smps.spec import rail as _rail
    target = _rail("+1V8A").phase_margin_target_deg
    f = D.sweep_for("+1V8A")
    for i_load in (0.0, 0.01, 0.05, 0.1, 0.25, 0.5):
        m = margins(f, D.ldo_loop_gain(i_load)(f))
        assert m.phase_margin_deg > target, f"{i_load} A: {m.phase_margin_deg:.1f} deg"


def test_ldo_rejects_enough_of_the_3v3_switching_ripple():
    """The analogue rail's ripple budget is met by the LDO's rejection of the
    3V3 buck's ripple, so the two have to be checked together."""
    r18 = rail("+1V8A")
    f_sw = rail("+3V3").f_sw_hz
    # The LDO alone does not do it. The series RC on its input is what makes
    # the budget, and this test exists to stop somebody deleting that resistor
    # to recover the headroom it costs.
    psrr_only = float(D.ldo_psrr_db(np.array([f_sw]))[0])
    total = float(D.ldo_total_rejection_db(np.array([f_sw]))[0])
    assert total > psrr_only + 15.0

    # Use the 3V3 specification limit as the input, not the simulated ripple,
    # so this test does not depend on a simulation run.
    v_in_ripple = rail("+3V3").v_ripple_max_vpp
    assert v_in_ripple * 10 ** (-total / 20) < r18.v_ripple_max_vpp
