# emb-multirail-smps

> **Status: planned. This repository is a brief, not an implementation.**
> Nothing here is built yet. The sections below define what goes in it.

A multi-rail SMPS designed for a documented specification, with the emphasis on measured validation rather than a schematic alone: derived loop compensation confirmed with Bode plots, load and line regulation, efficiency curves, thermal rise and an EMC pre-compliance scan.

---

## What this covers

CV entries this repository is the evidence for:

- Multi-Rail Switch-Mode Power Supply (Altium)

---

## Requirements

### Hardware

- 4-layer Altium board with synchronous buck, boost and LDO stages
- Test gear: oscilloscope, electronic load, Bode analyser or vector network analyser, near-field EMC probes, thermal camera or thermocouples

### Software

- Altium Designer
- Loop compensation calculations
- Thermal simulation
- LTspice or similar for pre-layout validation

### Report and documentation deliverables

- Schematic and stackup
- Loop compensation derivation with Bode plots
- Load and line regulation results
- Efficiency curves across load
- Thermal analysis with measured rise
- EMC pre-compliance scan results
- BOM

---

## Inputs

- Input voltage range
- Per-rail output voltage, current and ripple specifications
- Transient response requirements
- Thermal envelope

## Outputs

- Design files, Gerbers and BOM
- Measured regulation and ripple
- Phase and gain margin plots
- Efficiency data
- EMC pre-scan traces
- Validation report

---

## Intended structure

```
altium/                 project, schematic, PCB
simulation/             LTspice models, loop compensation calcs
outputs/                gerbers, drill, bom.csv, pick_and_place.csv,
                        schematic.pdf, 3d/
test-results/
  bode/                 gain and phase margin plots
  efficiency/
  load-regulation/
  line-regulation/
  transient/
  thermal/
  emc-prescan/
docs/                   spec.md, stackup.md, design_notes.md,
                        validation_report.md
```

Plus the standard baseline: `README.md`, `LICENSE`, `.gitignore`, `.gitattributes`
(Git LFS rules for weights, bags and media), `.github/workflows/ci.yml`, `docs/`,
`scripts/setup.sh`, `scripts/run_demo.sh` and `tests/`.

---

## Build checklist

- [ ] Written specification: rails, currents, ripple, transient, thermal
- [ ] Topology selection and component sizing
- [ ] LTspice pre-layout validation
- [ ] Loop compensation derivation
- [ ] Schematic capture in Altium
- [ ] 4-layer layout with stackup definition
- [ ] Fabrication and assembly
- [ ] Bring-up and basic function check
- [ ] Load and line regulation measurement
- [ ] Efficiency curves across load
- [ ] Bode measurement confirming phase and gain margin
- [ ] Transient response measurement
- [ ] Thermal measurement under full load
- [ ] EMC near-field pre-scan
- [ ] Validation report

---

## Definition of done

This repository is finished when:

- [ ] The whole thing runs from one command on a clean machine.
- [ ] The README opens with a diagram or a GIF, not a wall of text.
- [ ] Every number quoted in the README is reproducible from a script in the repo.
- [ ] Limitations are stated honestly in their own section.
- [ ] A licence is declared.
- [ ] Large binaries live in Releases or LFS, not in the Git history.
- [ ] The repository URL is added to the matching CV bullet point.

---

## Starter prompt

Paste this into your coding agent of choice to begin.

<details>
<summary>Expand</summary>

```
You are helping me build a portfolio project from scratch. Read this brief and then
propose a concrete implementation plan before writing any code.

PROJECT: emb-multirail-smps
A multi-rail SMPS designed for a documented specification, with the emphasis on measured validation rather than a schematic alone: derived loop compensation confirmed with Bode plots, load and line regulation, efficiency curves, thermal rise and an EMC pre-compliance scan.

TARGET STACK
- Altium Designer
- Loop compensation calculations
- Thermal simulation
- LTspice or similar for pre-layout validation

HARDWARE CONTEXT
- 4-layer Altium board with synchronous buck, boost and LDO stages
- Test gear: oscilloscope, electronic load, Bode analyser or vector network analyser, near-field EMC probes, thermal camera or thermocouples

THE SYSTEM MUST TAKE THESE INPUTS
- Input voltage range
- Per-rail output voltage, current and ripple specifications
- Transient response requirements
- Thermal envelope

AND PRODUCE THESE OUTPUTS
- Design files, Gerbers and BOM
- Measured regulation and ripple
- Phase and gain margin plots
- Efficiency data
- EMC pre-scan traces
- Validation report

INTENDED REPOSITORY LAYOUT
altium/                 project, schematic, PCB
simulation/             LTspice models, loop compensation calcs
outputs/                gerbers, drill, bom.csv, pick_and_place.csv,
                        schematic.pdf, 3d/
test-results/
  bode/                 gain and phase margin plots
  efficiency/
  load-regulation/
  line-regulation/
  transient/
  thermal/
  emc-prescan/
docs/                   spec.md, stackup.md, design_notes.md,
                        validation_report.md

CONSTRAINTS
- Everything must run from a single command: `docker compose up` or `make demo`.
- No placeholder or stub code presented as working. If something is not implemented, say so.
- Every quantitative claim in the README must be reproducible from a script in this repo.
- Use only public or synthetic data. Record the licence of every dataset used.


START BY
1. Confirming or challenging the proposed repository layout.
2. Listing the specific libraries and versions you intend to pin.
3. Identifying the single riskiest technical unknown and how to de-risk it first.
Then work through the milestones in the README build checklist, one at a time.

```

</details>

---

## Notes

- Do not backdate commits to match CV dates. Publishing older work today is normal and expected.
- Record dataset licences before training on anything. Several common research datasets are
  non-commercial only.
- Flip this repository to public once there is something in it worth showing.
