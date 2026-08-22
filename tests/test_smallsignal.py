"""The numeric state space models against the closed forms derived by hand.

The closed forms are the ones written out in ``docs/design_notes.md``. They
drop every parasitic, so the tolerances here are set by how much the parasitics
actually move each quantity, not by how confident anybody feels. Where a
tolerance is loose, the reason is stated.
"""

import numpy as np
import pytest

from smps import components as C
from smps.spec import rail
from smps.statespace import boost_model, buck_model, he

IDEAL = dict(r_dcr=1e-6, r_esr=1e-9, rds_hs=1e-6, rds_ls=1e-6)


def test_buck_dc_gain_is_vin():
    """``Gvd(0) = Vin`` for a buck, exactly, once the parasitics are removed."""
    m = buck_model(6.8e-6, 46.2e-6, IDEAL["r_dcr"], IDEAL["r_esr"],
                   IDEAL["rds_hs"], IDEAL["rds_ls"], 1.0)
    u = np.array([24.0, 0.0])
    d = m.duty_for_vout(5.0, u)
    assert d == pytest.approx(5.0 / 24.0, rel=1e-4)
    assert abs(m.g_vd(np.array([1e-3]), d, u)[0]) == pytest.approx(24.0, rel=1e-4)


def test_buck_resonance_matches_1_over_sqrt_lc():
    l, c = 6.8e-6, 46.2e-6
    m = buck_model(l, c, IDEAL["r_dcr"], IDEAL["r_esr"], IDEAL["rds_hs"],
                   IDEAL["rds_ls"], 1.0)
    u = np.array([24.0, 0.0])
    d = m.duty_for_vout(5.0, u)
    f = np.logspace(2, 6, 20001)
    f_peak = f[int(np.argmax(np.abs(m.g_vd(f, d, u))))]
    f0 = 1.0 / (2 * np.pi * np.sqrt(l * c))
    # The peak of a second order response sits slightly below the undamped
    # natural frequency, by 1 - 1/(2 Q^2). Q here is about 6.8.
    assert f_peak == pytest.approx(f0, rel=0.05)


def test_boost_dc_gain_is_vout_over_dprime():
    m = boost_model(22e-6, 24.2e-6, IDEAL["r_dcr"], IDEAL["r_esr"],
                    IDEAL["rds_hs"], IDEAL["rds_ls"], 30.0)
    u = np.array([5.0, 0.0])
    d = m.duty_for_vout(12.0, u)
    assert d == pytest.approx(1 - 5.0 / 12.0, rel=1e-4)
    dc = abs(m.g_vd(np.array([1e-3]), d, u)[0])
    assert dc == pytest.approx(12.0 / (1 - d), rel=1e-3)


def test_boost_right_half_plane_zero_where_hand_calculation_says():
    """``f_rhpz = D'^2 R / (2 pi L)``, found from the numerator roots."""
    l, c, r_load = 22e-6, 24.2e-6, 30.0
    m = boost_model(l, c, IDEAL["r_dcr"], IDEAL["r_esr"], IDEAL["rds_hs"],
                    IDEAL["rds_ls"], r_load)
    u = np.array([5.0, 0.0])
    d = m.duty_for_vout(12.0, u)
    a, _, cmat, _ = m.averaged(d)
    _, bd, dd = m.duty_input_vectors(d, u)

    # Transfer function zeros of C(sI-A)^-1 B + D are the eigenvalues of the
    # system matrix with the output fed back, which for a scalar D is
    # eig(A - B D^-1 C).
    zeros = np.linalg.eigvals(a - np.outer(bd, cmat) / dd)
    rhp = [z for z in zeros if z.real > 0]
    assert len(rhp) == 1, f"expected exactly one RHP zero, got {zeros}"
    f_num = rhp[0].real / (2 * np.pi)
    f_hand = (1 - d) ** 2 * r_load / (2 * np.pi * l)
    assert f_num == pytest.approx(f_hand, rel=0.02)


def test_boost_has_no_rhp_zero_in_the_buck():
    l, c = 6.8e-6, 46.2e-6
    m = buck_model(l, c, IDEAL["r_dcr"], IDEAL["r_esr"], IDEAL["rds_hs"],
                   IDEAL["rds_ls"], 1.0)
    u = np.array([24.0, 0.0])
    d = m.duty_for_vout(5.0, u)
    _, bd, dd = m.duty_input_vectors(d, u)
    # Dd is zero for a buck, so there is no finite transmission zero from the
    # feedthrough term at all. That is the structural reason a buck has no RHP
    # zero: the inductor feeds the output in both switch states.
    assert abs(dd) < 1e-9
    assert np.all(np.isfinite(bd))


def test_he_puts_a_pole_pair_at_half_the_switching_frequency():
    f_sw = 500e3
    assert abs(he(np.array([1e-3]), f_sw)[0]) == pytest.approx(1.0, abs=1e-6)
    # He(s) is zero at s = j pi/Ts only in the limit; what matters is that it
    # dips hard at fsw/2 and lifts the closed current loop gain there.
    mag = np.abs(he(np.array([f_sw / 2]), f_sw)[0])
    assert mag < 1.7
    assert np.abs(he(np.array([f_sw / 10]), f_sw)[0]) == pytest.approx(1.0, abs=0.2)


def test_current_mode_buck_loop_is_independent_of_input_voltage():
    """With Se = Sf the averaged current mode loop gain does not see Vin.

    Sn + Se = Ri Vin / L, so Fm goes as 1/Vin while Gvd and Gid both go as Vin.
    Everything cancels. This is a real property of the choice of slope
    compensation, not a modelling artefact, and it is why the simulated line
    regulation of the +5V rail looks suspiciously flat.
    """
    from smps.design import buck5_plant, OperatingPoint

    f = np.logspace(2, 5, 60)
    ref = buck5_plant(OperatingPoint("ref", 24.0, 5.0))(f)
    for v_in in (8.0, 12.0, 36.0):
        other = buck5_plant(OperatingPoint("x", v_in, 5.0))(f)
        assert np.allclose(other, ref, rtol=1e-6)


def test_parasitics_move_the_answer_but_not_by_much():
    """Sanity check that including the real parasitics is a correction, not a
    different circuit."""
    p = C.BUCK5
    ideal = buck_model(p["L_H"], p["Cout_F"], 1e-6, 1e-9, 1e-6, 1e-6, 1.0)
    real = buck_model(p["L_H"], p["Cout_F"], p["L_dcr_ohm"], p["Cout_esr_ohm"],
                      p["rds_hs_ohm"], p["rds_ls_ohm"], 1.0)
    u = np.array([24.0, 0.0])
    f = np.array([1e-3])
    g_i = abs(ideal.g_vd(f, ideal.duty_for_vout(5.0, u), u)[0])
    g_r = abs(real.g_vd(f, real.duty_for_vout(5.0, u), u)[0])
    assert 0.9 < g_r / g_i < 1.1
