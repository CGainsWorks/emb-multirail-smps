"""Single source of truth for the supply specification.

Every number quoted anywhere in this repository - README, docs, plots, CSVs -
originates here or is derived from here by code. Nothing is typed twice.

Reference: docs/spec.md, which is generated from this module by
``smps.report.write_spec_table``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# --------------------------------------------------------------------------
# System level
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SystemSpec:
    """Board level requirements."""

    vin_min_v: float = 8.0
    vin_nom_v: float = 24.0
    vin_max_v: float = 36.0

    #: Survivable but non-operating input excursion. Clamping is external,
    #: see docs/spec.md section "Out of scope".
    vin_transient_max_v: float = 40.0

    ambient_min_c: float = 0.0
    ambient_max_c: float = 55.0

    #: Free air, no heatsink, no forced convection.
    cooling: str = "natural convection, no heatsink"

    #: Conducted emissions target used for the pre-scan model.
    emc_standard: str = "EN 55032 Class B, conducted, 150 kHz to 30 MHz"


@dataclass(frozen=True)
class Rail:
    """One output rail.

    Attributes
    ----------
    source
        Name of the rail that feeds this one, or ``"VIN"`` for the board input.
        This defines the power tree and is used by :mod:`smps.losses` to
        propagate load current back towards the input.
    i_max_a
        Total current the stage must deliver, including any downstream rails
        that draw from it.
    i_external_a
        Of ``i_max_a``, how much is available at the connector for a user load.
        The remainder is consumed by downstream rails.
    """

    name: str
    v_out_v: float
    i_max_a: float
    i_external_a: float
    v_ripple_max_vpp: float
    topology: Literal["buck", "boost", "ldo"]
    control: Literal["peak-current-mode", "voltage-mode", "linear"]
    f_sw_hz: float
    source: str
    v_tol_pct: float = 1.0

    #: Load step used for the transient requirement, and the allowed excursion.
    load_step_a: float = 0.0
    load_step_slew_a_per_us: float = 1.0
    v_deviation_max_v: float = 0.0
    settle_time_max_s: float = 0.0

    #: Peak to peak inductor ripple as a fraction of the rated output current.
    #: 0.30 is the usual starting point. The boost runs higher on purpose: its
    #: right half plane zero sits at D'^2 R / (2 pi L), so a larger inductor
    #: pushes the zero down and takes achievable loop bandwidth with it. Ripple
    #: current is the thing worth spending to keep the zero where it is.
    ripple_ratio: float = 0.30

    #: Design targets for the compensated loop.
    f_cross_target_hz: float = 0.0
    phase_margin_target_deg: float = 50.0
    gain_margin_target_db: float = 8.0


SYSTEM = SystemSpec()


RAILS: tuple[Rail, ...] = (
    Rail(
        name="+5V",
        v_out_v=5.0,
        i_max_a=5.0,
        i_external_a=1.5,
        v_ripple_max_vpp=25e-3,
        topology="buck",
        control="peak-current-mode",
        f_sw_hz=500e3,
        source="VIN",
        v_tol_pct=1.0,
        load_step_a=1.5,
        load_step_slew_a_per_us=1.0,
        v_deviation_max_v=150e-3,
        settle_time_max_s=100e-6,
        f_cross_target_hz=50e3,
        phase_margin_target_deg=55.0,
        gain_margin_target_db=8.0,
    ),
    Rail(
        name="+3V3",
        v_out_v=3.3,
        i_max_a=3.0,
        i_external_a=2.5,
        v_ripple_max_vpp=20e-3,
        topology="buck",
        control="voltage-mode",
        f_sw_hz=1e6,
        source="+5V",
        v_tol_pct=1.0,
        load_step_a=1.0,
        load_step_slew_a_per_us=1.0,
        v_deviation_max_v=100e-3,
        settle_time_max_s=50e-6,
        f_cross_target_hz=100e3,
        phase_margin_target_deg=55.0,
        gain_margin_target_db=8.0,
    ),
    Rail(
        name="+12V",
        v_out_v=12.0,
        i_max_a=0.4,
        i_external_a=0.4,
        v_ripple_max_vpp=50e-3,
        topology="boost",
        control="peak-current-mode",
        f_sw_hz=400e3,
        source="+5V",
        v_tol_pct=2.0,
        ripple_ratio=0.35,
        load_step_a=0.2,
        load_step_slew_a_per_us=0.1,
        v_deviation_max_v=300e-3,
        settle_time_max_s=1e-3,
        f_cross_target_hz=6e3,
        phase_margin_target_deg=50.0,
        gain_margin_target_db=8.0,
    ),
    Rail(
        name="+1V8A",
        v_out_v=1.8,
        i_max_a=0.5,
        i_external_a=0.5,
        v_ripple_max_vpp=2e-3,
        topology="ldo",
        control="linear",
        f_sw_hz=0.0,
        source="+3V3",
        v_tol_pct=2.0,
        load_step_a=0.25,
        load_step_slew_a_per_us=1.0,
        v_deviation_max_v=50e-3,
        settle_time_max_s=20e-6,
        f_cross_target_hz=120e3,
        phase_margin_target_deg=45.0,
        gain_margin_target_db=10.0,
    ),
)


RAILS_BY_NAME = {r.name: r for r in RAILS}


def rail(name: str) -> Rail:
    return RAILS_BY_NAME[name]


# --------------------------------------------------------------------------
# Derived system quantities
# --------------------------------------------------------------------------

def useful_output_power_w() -> float:
    """Power delivered to user loads at the connectors.

    Downstream rails are excluded from their parent's contribution so the
    figure is not double counted.
    """
    return sum(r.v_out_v * r.i_external_a for r in RAILS)


def rail_order() -> list[Rail]:
    """Rails ordered so that a rail always appears after the one feeding it."""
    ordered: list[Rail] = []
    remaining = list(RAILS)
    resolved = {"VIN"}
    while remaining:
        progressed = False
        for r in list(remaining):
            if r.source in resolved:
                ordered.append(r)
                resolved.add(r.name)
                remaining.remove(r)
                progressed = True
        if not progressed:  # pragma: no cover - guards against a bad edit
            raise ValueError(f"cycle in power tree: {[r.name for r in remaining]}")
    return ordered
