"""Figure generation.

Every figure is titled and captioned as simulated, because it is. Nothing in
``test-results/`` came off a bench.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import design as D  # noqa: E402
from . import results as R  # noqa: E402
from .analysis import db, phase_deg  # noqa: E402
from .emc import en55032_class_b_qp_dbuv, middlebrook, prescan  # noqa: E402
from .losses import (efficiency_curve, rail_losses, solve_power_tree,  # noqa: E402
                     system_efficiency_curve)
from .spec import SYSTEM, RAILS, rail  # noqa: E402
from .thermal import derating_curve, solve_thermal  # noqa: E402

SIM_NOTE = "Simulated, not measured. No hardware exists."
plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": 130,
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "figure.autolayout": False,
})


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _footer(fig, text: str = SIM_NOTE) -> None:
    # Below the axes rather than on top of the x label. bbox_inches="tight"
    # grows the canvas to include it.
    fig.text(0.99, -0.015, text, ha="right", va="top", fontsize=7,
             color="0.35")


# --------------------------------------------------------------------------
# Bode
# --------------------------------------------------------------------------

def plot_loop(cmp: R.LoopComparison, out_dir: Path) -> Path:
    r = rail(cmp.rail)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 6.0), sharex=True,
                                   gridspec_kw={"hspace": 0.08})
    ax1.semilogx(cmp.f_ana, db(cmp.t_ana), lw=1.6,
                 label="hand derived model")
    ax1.semilogx(cmp.f_sim, db(cmp.t_sim), "o", ms=4,
                 label="switching simulation, injected sweep")
    ax1.axhline(0, color="0.5", lw=0.8)
    ax1.axvline(cmp.m_ana.f_cross_hz, color="0.7", lw=0.8, ls=":")
    ax1.set_ylabel("loop gain [dB]")
    ax1.legend(loc="lower left", fontsize=8)
    ax1.set_title(
        f"{cmp.rail} loop gain  |  fc {cmp.m_ana.f_cross_hz/1e3:.1f} kHz hand, "
        f"{cmp.m_sim.f_cross_hz/1e3:.1f} kHz simulated  |  "
        f"PM {cmp.m_ana.phase_margin_deg:.1f} deg hand, "
        f"{cmp.m_sim.phase_margin_deg:.1f} deg simulated")

    ax2.semilogx(cmp.f_ana, phase_deg(cmp.t_ana), lw=1.6)
    ax2.semilogx(cmp.f_sim, phase_deg(cmp.t_sim), "o", ms=4)
    ax2.axhline(-180, color="0.5", lw=0.8)
    ax2.axvline(cmp.m_ana.f_cross_hz, color="0.7", lw=0.8, ls=":")
    ax2.annotate(f"PM = {cmp.m_ana.phase_margin_deg:.1f} deg",
                 xy=(cmp.m_ana.f_cross_hz, cmp.m_ana.phase_margin_deg - 180),
                 xytext=(10, 18), textcoords="offset points", fontsize=8,
                 arrowprops=dict(arrowstyle="->", lw=0.8))
    ax2.set_ylabel("phase [deg]")
    ax2.set_xlabel("frequency [Hz]")
    _footer(fig, f"{SIM_NOTE}  Target fc {r.f_cross_target_hz/1e3:.0f} kHz, "
                 f"target PM {r.phase_margin_target_deg:.0f} deg.")
    name = cmp.rail.replace("+", "").lower()
    return _save(fig, out_dir / f"{name}_loop_gain.png")


def plot_ldo_loops(out_dir: Path) -> Path:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 5.6), sharex=True,
                                   gridspec_kw={"hspace": 0.08})
    f = D.sweep_for("+1V8A")
    for i_load, label in ((0.5, "0.50 A"), (0.05, "50 mA"),
                          (0.0, "no external load, preload only")):
        t = D.ldo_loop_gain(i_load)(f)
        ax1.semilogx(f, db(t), lw=1.4, label=label)
        ax2.semilogx(f, phase_deg(t), lw=1.4)
    ax1.axhline(0, color="0.5", lw=0.8)
    ax1.set_ylabel("loop gain [dB]")
    ax1.legend(fontsize=8)
    ax1.set_title("+1V8A LDO loop gain, behavioural model")
    ax2.axhline(-180, color="0.5", lw=0.8)
    ax2.set_ylabel("phase [deg]")
    ax2.set_xlabel("frequency [Hz]")
    _footer(fig, "Behavioural model of a bought in part, not a measurement and "
                 "not read from a datasheet. See STATUS.md.")
    return _save(fig, out_dir / "1v8a_ldo_loop_gain.png")


def plot_ldo_psrr(out_dir: Path) -> Path:
    f = np.logspace(1, 7, 600)
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    ax.semilogx(f, D.ldo_psrr_db(f, 0.5), lw=1.4, label="LDO alone, 0.50 A")
    ax.semilogx(f, D.ldo_input_filter_db(f), lw=1.4, ls="--",
                label="series RC on the LDO input")
    ax.semilogx(f, D.ldo_total_rejection_db(f, 0.5), lw=2.0,
                label="total, what the rail sees")
    f_sw = rail("+3V3").f_sw_hz
    ax.axvline(f_sw, color="0.5", ls="--", lw=1.0)
    total_at_fsw = float(D.ldo_total_rejection_db(np.array([f_sw]), 0.5)[0])
    ax.annotate(f"3V3 buck fsw\n{total_at_fsw:.0f} dB total",
                xy=(f_sw, total_at_fsw), xytext=(-105, 26),
                textcoords="offset points", fontsize=8,
                arrowprops=dict(arrowstyle="->", lw=0.8))
    ax.set_xlabel("frequency [Hz]")
    ax.set_ylabel("rejection [dB]")
    ax.set_title("+1V8A supply rejection, modelled")
    ax.legend(fontsize=8)
    _footer(fig, "Model, not a measurement. The LDO on its own does not meet "
                 "the analogue rail's ripple budget at 1 MHz; the input RC is "
                 "what makes it.")
    return _save(fig, out_dir / "1v8a_ldo_psrr.png")


# --------------------------------------------------------------------------
# Regulation and transient
# --------------------------------------------------------------------------

def plot_load_regulation(rows: list[dict], out_dir: Path) -> Path:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 3.6))
    for rail_name in R.SWITCHED_RAILS:
        sub = [r for r in rows if r["rail"] == rail_name]
        i = [r["i_out_a"] for r in sub]
        dev = [r["deviation_from_light_load_pct"] for r in sub]
        ax1.plot(i, dev, "o-", ms=4, label=rail_name)
        ax2.plot(i, [r["ripple_mvpp"] for r in sub], "o-", ms=4, label=rail_name)
        ax2.plot(i, [r["ripple_limit_mvpp"] for r in sub], "--", lw=0.9,
                 color=ax2.lines[-1].get_color(), alpha=0.5)
    ax1.set_xlabel("load current [A]")
    ax1.set_ylabel("deviation from light load [%]")
    ax1.set_title("Load regulation")
    ax1.legend(fontsize=8)
    ax2.set_xlabel("load current [A]")
    ax2.set_ylabel("output ripple [mVpp]")
    ax2.set_title("Ripple against load, dashed lines are the limits")
    ax2.legend(fontsize=8)
    _footer(fig)
    return _save(fig, out_dir / "load_regulation.png")


def plot_line_regulation(rows: list[dict], out_dir: Path) -> Path:
    sub = [r for r in rows if r["rail"] == "+5V"]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.plot([r["v_in_v"] for r in sub],
            [r["deviation_from_8v_pct"] for r in sub], "o-", ms=5)
    ax.axhline(1.0, color="r", ls="--", lw=0.9)
    ax.axhline(-1.0, color="r", ls="--", lw=0.9)
    ax.set_xlabel("input voltage [V]")
    ax.set_ylabel("deviation from the 8 V point [%]")
    ax.set_title("+5V line regulation over the full 8 to 36 V input range")
    _footer(fig, f"{SIM_NOTE}  Red lines are the plus or minus 1 % spec.")
    return _save(fig, out_dir / "line_regulation_5v.png")


def plot_transient(tr: R.TransientResult, out_dir: Path) -> Path:
    r = rail(tr.rail)
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    ax.plot(tr.t_us, 1e3 * (tr.v_out - tr.v_settled), lw=0.9)
    ax.axhline(1e3 * r.v_deviation_max_v, color="r", ls="--", lw=0.9)
    ax.axhline(-1e3 * r.v_deviation_max_v, color="r", ls="--", lw=0.9)
    ax.axvline(0, color="0.5", lw=0.8)
    ax.set_xlim(-20, min(tr.t_us.max(), 6 * max(tr.settle_time_us, 20)))
    ax.set_xlabel("time from the load step [us]")
    ax.set_ylabel("output deviation [mV]")
    ax.set_title(f"{tr.rail} load step {tr.step_a:.2f} A: "
                 f"undershoot {tr.undershoot_mv:.0f} mV, "
                 f"settled in {tr.settle_time_us:.0f} us")
    _footer(fig, f"{SIM_NOTE}  Red lines are the spec limit of "
                 f"{1e3*r.v_deviation_max_v:.0f} mV.")
    name = tr.rail.replace("+", "").lower()
    return _save(fig, out_dir / f"{name}_load_step.png")


# --------------------------------------------------------------------------
# Efficiency
# --------------------------------------------------------------------------

def plot_efficiency(out_dir: Path) -> list[Path]:
    paths = []
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    for rail_name in ("+5V", "+3V3", "+12V", "+1V8A"):
        v_in = (SYSTEM.vin_nom_v if rail_name == "+5V"
                else rail("+3V3").v_out_v if rail_name == "+1V8A"
                else rail("+5V").v_out_v)
        i, eta = efficiency_curve(rail_name, v_in)
        ax.semilogx(i, 100 * eta, lw=1.5, label=f"{rail_name} from {v_in:.1f} V")
    ax.set_xlabel("output current [A]")
    ax.set_ylabel("stage efficiency [%]")
    ax.set_ylim(40, 100)
    ax.set_title("Predicted efficiency of each stage in isolation")
    ax.legend(fontsize=8, loc="lower right")
    _footer(fig, "Predicted from the loss model, not measured. The LDO sits "
                 "near 1.8/3.3 because that is what a linear regulator is.")
    paths.append(_save(fig, out_dir / "stage_efficiency.png"))

    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    for v_in in (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v):
        frac, eta, _ = system_efficiency_curve(v_in)
        ax.plot(100 * frac, 100 * eta, lw=1.5, label=f"Vin {v_in:.0f} V")
    ax.set_xlabel("load, percent of full load on every rail")
    ax.set_ylabel("system efficiency [%]")
    ax.set_title("Predicted whole board efficiency, input to useful output")
    ax.legend(fontsize=8)
    _footer(fig, "Includes the cascade: the 5 V stage carries the 3V3 and 12 V "
                 "stages as well as its own connector load.")
    paths.append(_save(fig, out_dir / "system_efficiency.png"))

    # Where the power goes at the worst case corner.
    tree = solve_power_tree(SYSTEM.vin_max_v)
    terms: dict[str, float] = {}
    for name, lb in tree.per_rail.items():
        for k, v in lb.terms.items():
            terms[f"{name} {k.replace('_w','').replace('_',' ')}"] = v
    top = sorted(terms.items(), key=lambda kv: -kv[1])[:12]
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    ax.barh([t[0] for t in top][::-1], [1e3 * t[1] for t in top][::-1])
    ax.set_xlabel("loss [mW]")
    ax.set_title(f"Twelve largest loss terms at Vin {SYSTEM.vin_max_v:.0f} V, "
                 f"full load, total {tree.total_loss_w:.2f} W")
    _footer(fig, "Predicted. Switching loss dominates at high line, and it is "
                 "the term with the widest error band.")
    paths.append(_save(fig, out_dir / "loss_breakdown.png"))
    return paths


# --------------------------------------------------------------------------
# Thermal
# --------------------------------------------------------------------------

def plot_thermal(out_dir: Path) -> list[Path]:
    paths = []
    res = solve_thermal(SYSTEM.vin_max_v, SYSTEM.ambient_max_c)
    rows = res.rows()
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    names = [r["device"] for r in rows][::-1]
    temps = [r["t_junction_c"] for r in rows][::-1]
    ax.barh(names, temps)
    ax.axvline(125, color="r", ls="--", lw=1.0)
    ax.axvline(res.t_board_c, color="0.4", ls=":", lw=1.0)
    ax.annotate(f"board {res.t_board_c:.0f} C", xy=(res.t_board_c, -0.4),
                fontsize=8, color="0.3")
    ax.set_xlabel("junction temperature [C]")
    ax.set_xlim(0, 140)
    ax.set_title(f"Predicted junctions at {SYSTEM.ambient_max_c:.0f} C ambient, "
                 f"Vin {SYSTEM.vin_max_v:.0f} V, full load")
    _footer(fig, "Two resistance lumped model, no measurement. Red line is the "
                 "125 C limit assumed for every part.")
    paths.append(_save(fig, out_dir / "junction_temperatures.png"))

    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    for v_in in (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v):
        frac, amb = derating_curve(v_in)
        ax.plot(100 * frac, amb, lw=1.5, label=f"Vin {v_in:.0f} V")
    ax.axhline(SYSTEM.ambient_max_c, color="r", ls="--", lw=1.0)
    ax.set_xlabel("load, percent of full load")
    ax.set_ylabel("maximum ambient [C]")
    ax.set_title("Ambient derating for a 125 C junction limit")
    ax.legend(fontsize=8)
    _footer(fig, f"{SIM_NOTE}  Red line is the {SYSTEM.ambient_max_c:.0f} C "
                 "specification.")
    paths.append(_save(fig, out_dir / "ambient_derating.png"))
    return paths


# --------------------------------------------------------------------------
# EMC
# --------------------------------------------------------------------------

def plot_emc(out_dir: Path) -> list[Path]:
    paths = []
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    worst = None
    for v_in in (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v):
        tree = solve_power_tree(v_in)
        res = prescan(v_in, tree.per_rail["+5V"].i_out_a)
        # Markers, not a line. The spectrum of a periodic waveform exists only
        # at the harmonics; joining them up would draw content that is not
        # there.
        line, = ax.semilogx(res.f_hz, res.v_dbuv, "o", ms=3.5,
                            label=f"Vin {v_in:.0f} V")
        ax.vlines(res.f_hz, -60, res.v_dbuv, lw=0.6, alpha=0.35,
                  color=line.get_color())
        if worst is None or res.worst_margin_db < worst[0]:
            worst = (res.worst_margin_db, res.worst_frequency_hz,
                     float(res.v_dbuv[int(np.argmin(np.where(
                         np.isfinite(res.limit_dbuv),
                         res.margin_db, np.inf)))]))
    f_line = np.logspace(np.log10(150e3), np.log10(30e6), 500)
    ax.semilogx(f_line, en55032_class_b_qp_dbuv(f_line), "r--", lw=1.4,
                label="EN 55032 Class B quasi peak, reference envelope")
    ax.annotate(f"worst margin {worst[0]:.1f} dB{chr(10)}"
                f"at {worst[1]/1e3:.0f} kHz",
                xy=(worst[1], worst[2]), xytext=(40, 22),
                textcoords="offset points", fontsize=8,
                arrowprops=dict(arrowstyle="->", lw=0.8))
    ax.set_xlim(1e5, 4e7)
    ax.set_ylim(-40, 90)
    ax.set_xlabel("frequency [Hz]")
    ax.set_ylabel("level at the LISN [dBuV]")
    ax.set_title("Conducted emissions pre-scan, differential mode only")
    ax.legend(fontsize=8, loc="lower left")
    _footer(fig, "Modelled, not measured. Differential mode only. Common mode "
                 "depends on layout that does not exist yet.")
    paths.append(_save(fig, out_dir / "conducted_prescan.png"))

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    corners = (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v)
    # The filter output impedance does not depend on the operating point, so
    # it is one curve. What moves with input voltage is the converter's
    # constant power input impedance, |Zin| = Vin^2/Pin, and low line is the
    # binding case because that is where the input current is largest.
    mb0 = middlebrook(corners[0], solve_power_tree(corners[0]).p_in_w)
    ax.loglog(mb0.f_hz, mb0.z_out_ohm, lw=1.8, color="k",
              label="input filter Zout, source shorted")
    for v_in, colour in zip(corners, ("#c0392b", "#2e86c1", "#28a745")):
        mb = middlebrook(v_in, solve_power_tree(v_in).p_in_w)
        ax.axhline(mb.z_in_ohm, ls="--", lw=1.2, color=colour,
                   label=f"|Zin| at Vin {v_in:.0f} V  "
                         f"({mb.separation_db:.1f} dB separation)")
    ax.annotate(f"peak {mb0.peak_z_out_ohm:.2f} ohm at "
                f"{mb0.peak_f_hz/1e3:.1f} kHz",
                xy=(mb0.peak_f_hz, mb0.peak_z_out_ohm),
                xytext=(18, 22), textcoords="offset points", fontsize=8,
                arrowprops=dict(arrowstyle="->", lw=0.8))
    ax.set_xlabel("frequency [Hz]")
    ax.set_ylabel("impedance [ohm]")
    ax.set_ylim(5e-3, 3e2)
    ax.set_title("Input filter interaction, Middlebrook criterion")
    ax.legend(fontsize=8, loc="upper left")
    _footer(fig, "The filter output impedance has to stay well under the "
                 "converter input impedance at every frequency. Low line is "
                 "the binding case.")
    paths.append(_save(fig, out_dir / "input_filter_middlebrook.png"))
    return paths


# --------------------------------------------------------------------------
# Power tree summary, used as the README opening figure
# --------------------------------------------------------------------------

def plot_power_tree(out_dir: Path) -> Path:
    tree = solve_power_tree(SYSTEM.vin_nom_v)
    fig, ax = plt.subplots(figsize=(9.6, 3.4))
    ax.axis("off")

    positions = {"VIN": (0.02, 0.50), "+5V": (0.26, 0.50),
                 "+3V3": (0.53, 0.80), "+12V": (0.53, 0.20),
                 "+1V8A": (0.79, 0.80)}
    width = 0.20

    nl = chr(10)
    texts = {"VIN": (f"VIN{nl}"
                     f"{SYSTEM.vin_min_v:.0f} to {SYSTEM.vin_max_v:.0f} V{nl}"
                     f"{tree.i_in_a:.2f} A at {SYSTEM.vin_nom_v:.0f} V")}
    for name in ("+5V", "+3V3", "+12V", "+1V8A"):
        r = rail(name)
        lb = tree.per_rail[name]
        texts[name] = (f"{name}  {r.topology}{nl}"
                       f"{r.v_out_v:.1f} V, {lb.i_out_a:.2f} A total{nl}"
                       f"{r.i_external_a:.2f} A to the connector{nl}"
                       f"eta {100*lb.efficiency:.1f} %, "
                       f"loss {1e3*lb.total_w:.0f} mW")

    for src, dst in (("VIN", "+5V"), ("+5V", "+3V3"), ("+5V", "+12V"),
                     ("+3V3", "+1V8A")):
        x0, y0 = positions[src]
        x1, y1 = positions[dst]
        ax.annotate("", xy=(x1 - 0.012, y1), xytext=(x0 + width + 0.012, y0),
                    arrowprops=dict(arrowstyle="-|>", lw=1.4, color="#41608a",
                                    shrinkA=0, shrinkB=0))

    for name, (x, y) in positions.items():
        ax.text(x, y, texts[name], fontsize=8.5, va="center", ha="left",
                bbox=dict(boxstyle="round,pad=0.45", fc="#eef3f8", ec="#41608a",
                          lw=1.2))

    ax.set_xlim(0, 1.02)
    ax.set_ylim(0.02, 0.98)
    ax.set_title(f"Power tree at Vin {SYSTEM.vin_nom_v:.0f} V, full load:  "
                 f"{tree.p_in_w:.1f} W in, {tree.p_useful_w:.1f} W useful out, "
                 f"{100*tree.efficiency:.1f} % overall", fontsize=10)
    _footer(fig, "Predicted from the loss model in this repository. Nothing "
                 "here has been measured.")
    return _save(fig, out_dir / "power_tree.png")
