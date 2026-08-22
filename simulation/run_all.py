#!/usr/bin/env python3
"""Run the whole design and validation pass and write every output.

    python run_all.py            regenerate everything
    python run_all.py --quick    skip the switching sweeps, models only

Everything under ``outputs/`` and ``test-results/``, plus ``docs/spec.md`` and
``docs/validation_report.md``, is produced by this script. Nothing in those
directories should ever be edited by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from smps import plots, report, results as R  # noqa: E402
from smps.losses import efficiency_curve  # noqa: E402
from smps.netlist import write_all, write_csv  # noqa: E402
from smps.spec import SYSTEM, rail  # noqa: E402

OUT = REPO / "outputs"
TR = REPO / "test-results"
DOCS = REPO / "docs"


def _say(msg: str, t0: float) -> None:
    print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="skip the switching simulator sweeps")
    args = ap.parse_args()
    t0 = time.time()

    _say("specification and netlists", t0)
    report.write_spec(DOCS)
    written = write_all(OUT)
    _say(f"wrote {len(written)} files under outputs/", t0)

    data: dict = {"sizing_rows": R.sizing_rows()}
    write_csv(OUT / "sizing_check.csv", data["sizing_rows"])
    failed = [r for r in data["sizing_rows"] if not r["pass"]]
    if failed:
        print("SIZING CHECK FAILED:", failed, file=sys.stderr)
        return 1

    _say("efficiency and power tree", t0)
    data["eff_rows"] = R.efficiency_rows()
    data["system_eff_rows"] = R.system_efficiency_rows()
    write_csv(TR / "efficiency" / "stage_efficiency.csv", data["eff_rows"])
    write_csv(TR / "efficiency" / "system_efficiency.csv", data["system_eff_rows"])
    for rail_name in ("+5V", "+3V3", "+12V", "+1V8A"):
        v_in = (SYSTEM.vin_nom_v if rail_name == "+5V"
                else rail("+3V3").v_out_v if rail_name == "+1V8A"
                else rail("+5V").v_out_v)
        i, eta = efficiency_curve(rail_name, v_in, 40)
        write_csv(TR / "efficiency" / f"curve_{rail_name.replace('+','').lower()}.csv",
                  [{"i_out_a": round(float(a), 5), "efficiency_pct": round(100 * float(e), 4)}
                   for a, e in zip(i, eta)])
    plots.plot_efficiency(TR / "efficiency")
    plots.plot_power_tree(TR)

    _say("thermal", t0)
    data["thermal_rows"] = R.thermal_rows()
    write_csv(TR / "thermal" / "junction_temperatures.csv", data["thermal_rows"])
    write_csv(TR / "thermal" / "ambient_derating.csv", R.derating_rows())
    plots.plot_thermal(TR / "thermal")

    _say("EMC pre-scan and input filter interaction", t0)
    data["emc_summary_rows"] = R.emc_summary_rows()
    write_csv(TR / "emc-prescan" / "spectrum.csv", R.emc_rows())
    write_csv(TR / "emc-prescan" / "summary.csv", data["emc_summary_rows"])
    plots.plot_emc(TR / "emc-prescan")

    _say("LDO loop and supply rejection", t0)
    plots.plot_ldo_loops(TR / "bode")
    plots.plot_ldo_psrr(TR / "bode")

    if args.quick:
        print("--quick: skipping switching simulator sweeps", flush=True)
        data.update(loop_rows=[], load_reg_rows=[], line_reg_rows=[],
                    transient_rows=[])
    else:
        _say("switching simulation: loop gain sweeps", t0)
        comparisons = R.all_loop_comparisons()
        data["loop_rows"] = [c.row() for c in comparisons]
        write_csv(TR / "bode" / "loop_margins.csv", data["loop_rows"])
        for c in comparisons:
            plots.plot_loop(c, TR / "bode")
            write_csv(TR / "bode" / f"sweep_{c.rail.replace('+','').lower()}.csv",
                      [{"f_hz": round(float(f), 3),
                        "gain_db": round(float(20 * __import__("numpy").log10(abs(t))), 4),
                        "phase_deg": round(float(__import__("numpy").degrees(
                            __import__("numpy").angle(t))), 4)}
                       for f, t in zip(c.f_sim, c.t_sim)])

        _say("switching simulation: regulation", t0)
        data["load_reg_rows"] = R.load_regulation_rows()
        data["line_reg_rows"] = R.line_regulation_rows()
        write_csv(TR / "load-regulation" / "load_regulation.csv", data["load_reg_rows"])
        write_csv(TR / "line-regulation" / "line_regulation.csv", data["line_reg_rows"])
        plots.plot_load_regulation(data["load_reg_rows"], TR / "load-regulation")
        plots.plot_line_regulation(data["line_reg_rows"], TR / "line-regulation")

        _say("switching simulation: load transients", t0)
        trs = [R.load_transient(r) for r in R.SWITCHED_RAILS]
        data["transient_rows"] = [t.row() for t in trs]
        write_csv(TR / "transient" / "load_step.csv", data["transient_rows"])
        for t in trs:
            plots.plot_transient(t, TR / "transient")

    _say("headline numbers and validation report", t0)
    data["headline"] = R.headline()
    (OUT / "headline.json").write_text(
        json.dumps(data["headline"], indent=2) + "\n", encoding="utf-8")
    report.write_validation(DOCS, data)

    _say("done", t0)
    print(json.dumps(data["headline"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
