"""Lumped thermal model, and the ambient derating that falls out of it.

Two resistances per part, which is the least you can get away with and still
say anything useful:

* one board-to-ambient resistance shared by everything, because on a small
  board in still air the copper is the heatsink and every dissipating part is
  bolted to the same one; and
* one junction-to-board resistance per part.

So ``Tj = Tamb + Ptotal * Rth_ba + Ppart * Rth_jb``.

This is a model, not a measurement. No board has been built, no thermocouple
has been attached and no thermal camera has been pointed at anything. It is
also the crudest model in the repository: it assumes the board is isothermal,
which it will not be, so the hot spot under the high side FET will be worse
than this predicts and the parts far from it will be better.

The board-to-ambient figure is estimated from natural convection plus radiation
over the board area, derated for the fraction of the board that is actually
thermally connected to the power stage. ``docs/thermal_model.md`` shows the
arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .losses import PowerTree, solve_power_tree
from .spec import SYSTEM


@dataclass(frozen=True)
class Board:
    length_m: float = 0.100
    width_m: float = 0.080
    #: Natural convection coefficient, both faces, W/m^2K.
    h_conv: float = 8.0
    #: Radiative coefficient for a soldermask finish near 350 K, W/m^2K.
    h_rad: float = 6.0
    #: Fraction of the board area that is thermally coupled to the power stage.
    coupled_fraction: float = 0.60

    @property
    def area_m2(self) -> float:
        return 2.0 * self.length_m * self.width_m

    @property
    def rth_ba_kw(self) -> float:
        return 1.0 / ((self.h_conv + self.h_rad) * self.area_m2 * self.coupled_fraction)


BOARD = Board()

#: Junction (or hot spot) to board thermal resistance, K/W. Package level
#: assumptions, to be replaced by datasheet Rth(j-b) figures before ordering.
RTH_JB_KW = {
    "Q1 buck HS FET": 12.0,
    "Q2 buck LS FET": 12.0,
    "L1 buck inductor": 25.0,
    "U3 3V3 regulator": 18.0,
    "L2 3V3 inductor": 30.0,
    "Q3/Q4 boost FETs": 35.0,
    "L3 boost inductor": 30.0,
    "U5 1V8 LDO": 20.0,
    "Rs1 sense resistor": 40.0,
}

T_J_MAX_C = 125.0


def device_powers(tree: PowerTree) -> dict[str, float]:
    """Allocate the loss terms to physical parts.

    Gate drive loss is split evenly between the two devices, which is a
    simplification: most of it is actually burnt in the driver inside the
    controller, not in the FET. It is called out in docs/thermal_model.md.
    """
    l5 = tree.per_rail["+5V"].terms
    l3 = tree.per_rail["+3V3"].terms
    l12 = tree.per_rail["+12V"].terms
    l18 = tree.per_rail["+1V8A"].terms
    p5 = tree.per_rail["+5V"]

    return {
        "Q1 buck HS FET": (l5["hs_conduction_w"] + l5["hs_switching_w"]
                           + l5["output_charge_w"] + 0.5 * l5["gate_drive_w"]),
        "Q2 buck LS FET": (l5["ls_conduction_w"] + l5["dead_time_w"]
                           + 0.5 * l5["gate_drive_w"]),
        "L1 buck inductor": l5["inductor_dcr_w"] + l5["inductor_core_w"],
        "Rs1 sense resistor": p5.i_out_a ** 2 * 5e-3,
        "U3 3V3 regulator": (l3["hs_conduction_w"] + l3["ls_conduction_w"]
                             + l3["hs_switching_w"] + l3["output_charge_w"]
                             + l3["gate_drive_w"] + l3["dead_time_w"]
                             + l3["controller_w"]),
        "L2 3V3 inductor": l3["inductor_dcr_w"] + l3["inductor_core_w"],
        "Q3/Q4 boost FETs": (l12["lo_conduction_w"] + l12["hi_conduction_w"]
                             + l12["switching_w"] + l12["output_charge_w"]
                             + l12["gate_drive_w"] + l12["dead_time_w"]),
        "L3 boost inductor": l12["inductor_dcr_w"] + l12["inductor_core_w"],
        "U5 1V8 LDO": l18["pass_device_w"] + l18["quiescent_w"],
    }


@dataclass(frozen=True)
class ThermalResult:
    t_ambient_c: float
    t_board_c: float
    total_loss_w: float
    junctions_c: dict
    device_w: dict

    @property
    def hottest(self) -> tuple[str, float]:
        k = max(self.junctions_c, key=self.junctions_c.get)
        return k, self.junctions_c[k]

    def rows(self) -> list[dict]:
        return [
            {"device": k, "power_w": round(self.device_w[k], 4),
             "rth_jb_k_per_w": RTH_JB_KW[k],
             "t_board_c": round(self.t_board_c, 2),
             "t_junction_c": round(v, 2),
             "margin_to_125c_k": round(T_J_MAX_C - v, 2)}
            for k, v in sorted(self.junctions_c.items(), key=lambda kv: -kv[1])
        ]


def solve_thermal(v_in: float, t_ambient_c: float,
                  load_fraction: float = 1.0,
                  board: Board = BOARD) -> ThermalResult:
    tree = solve_power_tree(v_in, load_fraction)
    dev = device_powers(tree)
    # Everything dissipated on the board heats the board, including the parts
    # not in the device list such as capacitor ESR.
    t_board = t_ambient_c + tree.total_loss_w * board.rth_ba_kw
    junctions = {k: t_board + p * RTH_JB_KW[k] for k, p in dev.items()}
    return ThermalResult(t_ambient_c, t_board, tree.total_loss_w, junctions, dev)


def max_ambient_c(v_in: float, load_fraction: float = 1.0,
                  t_j_max_c: float = T_J_MAX_C, board: Board = BOARD) -> float:
    """Highest ambient that keeps every junction below ``t_j_max_c``.

    The model is linear in ambient temperature, so this is one subtraction
    rather than a search.
    """
    res = solve_thermal(v_in, 0.0, load_fraction, board)
    _, hottest = res.hottest
    return t_j_max_c - hottest


def derating_curve(v_in: float, points: int = 21):
    """Maximum ambient against load fraction, the classic derating plot."""
    frac = np.linspace(0.1, 1.0, points)
    amb = np.array([max_ambient_c(v_in, float(f)) for f in frac])
    return frac, amb


def meets_ambient_spec(v_in: float) -> bool:
    return max_ambient_c(v_in) >= SYSTEM.ambient_max_c
