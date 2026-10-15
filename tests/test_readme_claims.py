"""The README's tables have to agree with the generated results.

This exists because the README drifted from the data twice while it was being
written, both times in the direction of quoting a number that used to be true.
A README that quotes results is only worth reading if something checks it, and
a human rereading a table of forty numbers is not that something.

These tests read the committed CSVs, so they fail if the README is edited away
from the data *or* if the data moves and the README is not updated. They do not
regenerate anything, so they are cheap.
"""

import csv
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def rows(path: str) -> list[dict]:
    with (ROOT / path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def readme_table(after: str) -> list[list[str]]:
    """The first markdown table appearing after a marker string."""
    start = README.index(after)
    lines = README[start:].splitlines()
    table = []
    for line in lines:
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            table.append(cells)
        elif table:
            break
    return table


def number(text: str) -> float:
    m = re.search(r"[-+]?\d*\.?\d+", text.replace(",", ""))
    assert m, f"no number in {text!r}"
    return float(m.group())


# --------------------------------------------------------------------------
# The headline loop comparison
# --------------------------------------------------------------------------

def test_readme_loop_table_matches_the_generated_margins():
    data = {r["rail"]: r for r in rows("test-results/bode/loop_margins.csv")}
    table = readme_table("## The result this repository exists for")
    header, body = table[0], table[1:]
    assert header[0] == "rail"
    assert len(body) == 3, "expected one row per switching rail"

    for row in body:
        rail = row[0]
        d = data[rail]
        # columns: rail, control, target fc, hand fc, sim fc, fc error,
        #          target PM, hand PM, sim PM, PM error
        assert number(row[3]) == pytest.approx(float(d["f_cross_hand_hz"]) / 1e3, rel=2e-3)
        assert number(row[4]) == pytest.approx(float(d["f_cross_sim_hz"]) / 1e3, rel=2e-3)
        assert number(row[5]) == pytest.approx(float(d["f_cross_error_pct"]), abs=0.1)
        assert number(row[7]) == pytest.approx(float(d["pm_hand_deg"]), abs=0.1)
        assert number(row[8]) == pytest.approx(float(d["pm_sim_deg"]), abs=0.1)
        assert number(row[9]) == pytest.approx(float(d["pm_error_deg"]), abs=0.1)


def test_readme_quotes_the_worst_disagreement_correctly():
    data = rows("test-results/bode/loop_margins.csv")
    worst_fc = max(abs(float(r["f_cross_error_pct"])) for r in data)
    worst_pm = max(abs(float(r["pm_error_deg"])) for r in data)
    m = re.search(r"Worst crossover disagreement ([\d.]+) percent, worst phase "
                  r"margin disagreement\s+([\d.]+)", README)
    assert m, "the README no longer states the worst disagreement"
    assert float(m.group(1)) == pytest.approx(worst_fc, abs=0.1)
    assert float(m.group(2)) == pytest.approx(worst_pm, abs=0.1)


# --------------------------------------------------------------------------
# Regulation, ripple and transient
# --------------------------------------------------------------------------

def test_readme_ripple_and_transient_match_the_generated_results():
    load = rows("test-results/load-regulation/load_regulation.csv")
    trans = {r["rail"]: r for r in rows("test-results/transient/load_step.csv")}
    table = readme_table("### Regulation, ripple and transient")
    body = table[1:]
    assert len(body) == 3

    for row in body:
        rail = row[0]
        full = max((r for r in load if r["rail"] == rail),
                   key=lambda r: float(r["i_out_a"]))
        assert number(row[3]) == pytest.approx(float(full["ripple_mvpp"]), abs=0.05)
        assert number(row[4]) == pytest.approx(float(full["ripple_limit_mvpp"]), abs=0.05)

        t = trans[rail]
        assert number(row[5]) == pytest.approx(float(t["step_a"]), abs=0.001)
        assert number(row[6]) == pytest.approx(float(t["undershoot_mv"]), abs=1.0)
        assert number(row[7]) == pytest.approx(float(t["limit_mv"]), abs=0.5)


def test_readme_regulation_bounds_are_not_overstated():
    """The README quotes regulation as a bound. The bound has to hold."""
    load = rows("test-results/load-regulation/load_regulation.csv")
    line = rows("test-results/line-regulation/line_regulation.csv")
    table = readme_table("### Regulation, ripple and transient")

    for row in table[1:]:
        rail = row[0]
        worst_line = max(abs(float(r["deviation_from_8v_pct"]))
                         for r in line if r["rail"] == rail)
        worst_load = max(abs(float(r["deviation_from_light_load_pct"]))
                         for r in load if r["rail"] == rail)
        assert worst_line <= number(row[1]) + 1e-9, f"{rail} line regulation"
        assert worst_load <= number(row[2]) + 1e-9, f"{rail} load regulation"


# --------------------------------------------------------------------------
# Headline numbers
# --------------------------------------------------------------------------

def test_readme_headline_numbers_match_the_generated_json():
    import json
    h = json.loads((ROOT / "outputs" / "headline.json").read_text(encoding="utf-8"))

    eff = re.search(r"([\d.]+) percent at 24 V and full load", README)
    assert eff, "the README no longer states the system efficiency"
    assert float(eff.group(1)) == pytest.approx(h["system_efficiency_nom_pct"], abs=0.05)

    amb = re.search(r"Maximum ambient for a 125 degree junction at full load is\s+"
                    r"([\d.]+) degrees", README)
    assert amb, "the README no longer states the maximum ambient"
    assert float(amb.group(1)) == pytest.approx(h["max_ambient_full_load_c"], abs=0.1)

    emc = re.search(r"Worst margin \*\*([\d.]+) dB\*\*", README)
    assert emc, "the README no longer states the EMC margin"
    assert float(emc.group(1)) == pytest.approx(h["worst_emc_margin_db"], abs=0.05)

    mb = re.search(r"Worst separation ([\d.]+) dB", README)
    assert mb, "the README no longer states the Middlebrook separation"
    assert float(mb.group(1)) == pytest.approx(
        h["worst_middlebrook_separation_db"], abs=0.05)


def test_readme_test_count_matches_the_suite():
    """The README says how many tests there are. Keep it true."""
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                          str(ROOT / "tests")],
                         capture_output=True, text=True, cwd=ROOT).stdout
    m = re.search(r"(\d+) tests? collected", out)
    assert m, f"could not count the tests: {out[-400:]}"
    collected = int(m.group(1))
    stated = re.search(r"(\d+) tests, about", README)
    assert stated, "the README no longer states a test count"
    assert int(stated.group(1)) == collected
