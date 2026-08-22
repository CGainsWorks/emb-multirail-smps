"""The headline check: the hand derived loop gain against the switching sim.

This is the gate the project brief sets, that the simulation has to agree with
the hand calculation before boards are ordered. It is slower than the rest of
the suite because it runs three converters cycle by cycle over a swept sine, so
it uses a coarser sweep than ``run_all.py`` does. The margins it extracts are
the same ones, from the same code.
"""

import numpy as np
import pytest

from smps import design as D
from smps.analysis import log_sweep, margins
from smps.loopmeas import (F_MAX_FRACTION, linearity_check, measure_loop,
                           measure_point, snap_commensurate)
from smps.results import steady_state, load_transient
from smps.spec import SYSTEM, rail
from smps.switching import ConverterSim

RAILS = ("+5V", "+3V3", "+12V")

# Coarse sweeps, an octave either side of the target crossover. Enough to
# place the 0 dB crossing and read the phase there, which is all this test
# needs; run_all.py sweeps far wider for the published plots.
SWEEP = {"+5V": (12e3, 200e3, 12),
         "+3V3": (25e3, 400e3, 12),
         "+12V": (1.5e3, 25e3, 12)}


@pytest.mark.parametrize("rail_name", RAILS)
def test_simulated_loop_matches_the_hand_derived_loop(rail_name):
    op = D.design_point(rail_name)
    cfg = D.sim_config(rail_name, op)
    f_lo, f_hi, n = SWEEP[rail_name]

    f_sim, t_sim = measure_loop(cfg, f_lo, f_hi, points=n)
    m_sim = margins(f_sim, t_sim)

    f_ana = log_sweep(f_lo, f_hi, 200)
    m_ana = margins(f_ana, D.analytic_loop(rail_name, op)(f_ana))

    assert m_sim.f_cross_hz == pytest.approx(m_ana.f_cross_hz, rel=0.10), (
        f"{rail_name}: simulated fc {m_sim.f_cross_hz:.0f} Hz against "
        f"hand derived {m_ana.f_cross_hz:.0f} Hz")
    assert abs(m_sim.phase_margin_deg - m_ana.phase_margin_deg) < 6.0, (
        f"{rail_name}: simulated PM {m_sim.phase_margin_deg:.1f} deg against "
        f"hand derived {m_ana.phase_margin_deg:.1f} deg")


@pytest.mark.parametrize("rail_name", RAILS)
def test_simulated_loop_meets_the_specification(rail_name):
    r = rail(rail_name)
    op = D.design_point(rail_name)
    cfg = D.sim_config(rail_name, op)
    f_lo, f_hi, n = SWEEP[rail_name]
    f_sim, t_sim = measure_loop(cfg, f_lo, f_hi, points=n)
    m = margins(f_sim, t_sim)
    assert m.phase_margin_deg >= r.phase_margin_target_deg
    assert m.f_cross_hz == pytest.approx(r.f_cross_target_hz, rel=0.12)


def test_injection_stays_in_the_small_signal_regime():
    """Doubling the stimulus must not move the answer. If it does, the
    measurement is of a large signal behaviour, not of a loop gain."""
    for rail_name in RAILS:
        cfg = D.sim_config(rail_name, D.design_point(rail_name))
        rel = linearity_check(cfg, rail(rail_name).f_cross_target_hz)
        assert rel < 5e-3, f"{rail_name}: {rel:.2e}"


def test_measurement_frequencies_are_commensurate_with_the_switching_clock():
    """The whole reason the ripple is rejected exactly is that every sweep
    point is an integer number of bins of an integer number of cycles."""
    for f_req in (137.0, 1000.0, 4321.0, 90e3):
        f_act, m, k = snap_commensurate(f_req, 500e3)
        assert f_act == pytest.approx(500e3 * k / m, rel=1e-12)
        assert 1 <= k <= F_MAX_FRACTION * m
        assert m >= 32


def test_sweep_never_asks_for_a_frequency_at_or_above_nyquist():
    cfg = D.sim_config("+5V", D.design_point("+5V"))
    f, _ = measure_loop(cfg, 1e3, 10 * cfg.f_sw, points=6)
    assert f.max() < 0.5 * cfg.f_sw


def test_steady_state_output_is_where_the_divider_puts_it():
    for rail_name in RAILS:
        r = rail(rail_name)
        v_in = SYSTEM.vin_nom_v if rail_name == "+5V" else rail("+5V").v_out_v
        v, _ = steady_state(rail_name, v_in, r.i_max_a, cycles=2000)
        assert v == pytest.approx(r.v_out_v, rel=r.v_tol_pct / 100.0)


def test_ripple_is_inside_the_specification():
    for rail_name in RAILS:
        r = rail(rail_name)
        v_in = SYSTEM.vin_nom_v if rail_name == "+5V" else rail("+5V").v_out_v
        _, ripple = steady_state(rail_name, v_in, r.i_max_a, cycles=2000)
        assert ripple < r.v_ripple_max_vpp, (
            f"{rail_name}: {1e3*ripple:.2f} mVpp against a limit of "
            f"{1e3*r.v_ripple_max_vpp:.1f} mVpp")


def test_load_step_stays_inside_the_transient_window():
    for rail_name in RAILS:
        r = rail(rail_name)
        tr = load_transient(rail_name)
        assert tr.undershoot_mv < 1e3 * r.v_deviation_max_v
        assert tr.overshoot_mv < 1e3 * r.v_deviation_max_v
        assert tr.settle_time_us < 1e6 * r.settle_time_max_s


def test_line_regulation_of_the_5v_rail_over_the_full_input_range():
    r = rail("+5V")
    volts = [steady_state("+5V", v, r.i_max_a, cycles=2000)[0]
             for v in (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v)]
    spread = (max(volts) - min(volts)) / np.mean(volts)
    assert spread < r.v_tol_pct / 100.0


def test_simulator_conserves_the_operating_point_it_was_started_at():
    """A converter started at its own steady state should stay there. If the
    solver were leaking energy through the propagation this would drift."""
    cfg = D.sim_config("+5V", D.design_point("+5V"))
    sim = ConverterSim(cfg)
    u = np.array([cfg.v_in, 0.0, cfg.v_target])
    res = sim.run(400, lambda _k: u)
    assert res.v_out_cycle[-1] == pytest.approx(cfg.v_target, rel=2e-3)
    assert np.all(np.isfinite(res.duty))
    assert 0.0 < res.duty.min() and res.duty.max() < 1.0
