# Project status

Last updated: 2026-10-16

This file records what actually exists in this repository, so that nothing in
the README or on a CV overstates it. Update it as items move between sections.

---

## The one sentence version

The electrical design is complete and validated in simulation, real parts are
selected, the schematic is captured in KiCad and held to the simulation by CI,
and a four layer board is laid out with five connections still unrouted. **No
board has been fabricated, assembled, powered or measured.** Every number in
`test-results/` is computed, not measured.

---

## Complete

**Specification.** Four rails, input range, ripple, transient, thermal and EMC
targets, written down first and held in one place as code. `docs/spec.md` is
generated from it, and every model and every test reads the same source, so a
requirement cannot be stale in one place and current in another.

**Topology selection and power stage sizing.** Synchronous buck, synchronous
buck, synchronous boost and an LDO, in a cascaded tree. Inductors, capacitors,
sense resistors and switching frequencies chosen, with the required value and
the chosen value reported side by side for every line and asserted in the test
suite.

**Small signal models.** Each power stage written as two linear systems from
Kirchhoff's laws, averaged and linearised, with the current mode loops closed
using the Ridley sampled data model. No transfer function is quoted from
memory. The numeric model is checked against independently derived closed
forms, including finding the boost right half plane zero from the state space
matrices directly rather than reading it off a plot.

**Loop compensation, derived by hand.** Type II on the two peak current mode
rails, Type III on the voltage mode rail, with the placement rules argued
rather than asserted, the gain element solved for numerically and the values
snapped to stocked E series parts. The working is in `docs/compensation/`.

**Cycle accurate switching simulation.** Each converter run switching cycle by
switching cycle, closed loop, with exact state propagation and the switching
instant found by root finding on the real comparator condition.

**Loop gain measured from the switching simulation.** A small signal injected
in series with the feedback divider, the loop gain extracted as `-VA/VB`, which
is the same formula a Bode analyser uses. Sweep frequencies are commensurate
with the switching clock so the ripple lands on the DC bin and is rejected
exactly. Linearity confirmed by re-running at double amplitude.

**The two routes agree.** Worst crossover disagreement 5.5 percent, worst phase
margin disagreement 2.6 degrees, across all three switching rails. This is the
gate the project brief sets before boards are ordered, and it is met.

**Simulated regulation, ripple, transient, efficiency, thermal and conducted
EMC**, with the input filter also checked against Middlebrook's criterion. Line
and load regulation, ripple and load steps come from the switching simulation;
efficiency across load from the loss model; Bode plots and phase margins from
both the hand model and the simulated injection measurement; junction
temperatures from the thermal model. Every plot carries the caption
"Simulated, not measured" and `test-results/README.md` says the same of every
file.

**Part selection.** Every part on the board has a real manufacturer part
number: LTC3891 (+5V buck controller), TPS54317 (+3V3 regulator), TPS43061
(+12V boost controller), LP5912-1.8 (LDO), CSD18543Q3A and AO3400A FETs,
Coilcraft XAL and XGL inductors, Vishay shunts, Murata, Samsung and KEMET
capacitors, Yageo resistors, an Eaton fuse, a Littelfuse TVS and Phoenix
terminals. The headline figures of each were read from the manufacturer's or a
distributor's listing. Each controller's reference voltage and error amplifier
figures were taken from its data sheet into the model, which moved the +3V3
and +12V references from an assumed 0.8 V to 0.891 V and 1.22 V and re-derived
the dividers and compensation. Where a data sheet and the model still disagree
it is written against that line in `outputs/VERIFY.csv`.

**KiCad schematic.** `hardware/kicad/`, KiCad 8: a root sheet and four stage
sheets, 79 parts, 52 nets, with footprints from KiCad's library and two
controller symbols drawn from their data sheet pin tables. Every value the
simulation uses is the one on the schematic; the support parts each
controller needs (timing, bootstrap, soft start, bias, pull-ups) are sized
from its data sheet with the equation quoted on the part. A 0 ohm link in each
divider becomes the 20 ohm Bode injection point at bring-up. The schematic is
generated from `simulation/smps/hardware.py` in the label style, which is
checkable and less pleasant to read than one drawn by hand.

**The schematic is held to the simulation.** CI runs `kicad-cli sch erc` in the
pinned `kicad/kicad:8.0.9` image with every severity enabled and it reports
nothing, warnings included. The exported netlist is then checked by
`scripts/kicad/check_netlist.py` against every R, L and C in every ngspice deck
(value after DC bias derating and the nets each part joins), the model's
inductors, shunts and capacitor banks, the compensation table and each rail's
set point from its controller's reference: 575 checks. Change a value in KiCad
and CI fails.

**Four layer board.** `hardware/kicad/emb-multirail-smps.kicad_pcb`, 100 by
80 mm on the `docs/stackup.md` stackup: 2/1/1/2 oz, 0.2 mm prepreg, 1.065 mm
core, ground plane on In1, VIN, +5V and +3V3 pours on In2, 0.30 mm thermal
vias under every exposed pad. Placement is by stage region, generated by
`scripts/kicad/gen_pcb.py`; routing is Freerouting 2.4.1's, with power tracks
widened afterwards as far as clearance allows. CI runs `kicad-cli pcb drc` with
schematic parity: no clearance, short, hole or parity errors. Gerbers and
drill files are exported for the manual run's artifact. Five connections are
not routed, listed under "Not done".

**Netlist.** A Protel format connection list that Altium imports, now derived
from the same data as the KiCad schematic, 79 parts and 52 nets, with
integrity checks in the test suite.

**A third simulator agrees.** The compensation networks are emitted as ngspice
decks and run by CI on every push, with the results compared against the closed
forms. Worst disagreement across the three networks and the input filter is
0.0001 dB and 0.099 degrees, against an enforced tolerance of 0.01 dB and
0.2 degrees. The switching deck settles the +3V3 rail at 3.3210 V, which is
what the divider asks for to five figures, with 4.23 mVpp of ripple against
2.74 mVpp from the simulator here: a factor of 1.54 against the 1.6 the check
allows. The hand derivation and the switching
simulator are both written here, so a shared misconception in them would agree
with itself; ngspice knows nothing about either. LTspice decks are emitted in a
separate directory and have never been run, because no Linux runner has an
LTspice. An earlier version of this repository claimed the decks were portable
between the two, which was untrue and is now asserted against.

**Test suite.** 129 tests, no hardware needed, running in about a minute.
Among them, a set that reads the generated CSVs back and fails if any number
quoted in the README has drifted away from them, which it had, twice, before
that check existed. One test skips unless ngspice is installed; CI installs it.

**CI, running.** One job: tests, regeneration, a check that the committed
results still match what the code produces, ngspice, a guard on every number
the README quotes and the KiCad ERC, cross-check and DRC. Built for a free
account, so it is one job rather than four, with path filters, concurrency
cancellation, a pip cache and a hard timeout. About 3 minutes per push, of
which KiCad is about 20 seconds. `make ci` is the same sequence locally, with
Docker for KiCad.

The repository was private until the design was worth showing, and while it was
private the Actions jobs were never assigned a runner, which is what an
exhausted private repository allowance looks like. Making it public resolved
that, and the first public run confirmed it: zero billable milliseconds,
because public repositories do not consume the allowance.

Python 3.9 and 3.11 are checked on manual dispatch rather than on every push,
3.12 on every push as the main job's interpreter. All three have been run and
pass: the dispatch run took 101 seconds of wall clock for all three jobs
together.

The outputs check compares numbers rather than bytes, and that was forced by a
real failure rather than chosen for convenience. The settled output voltages
differ by about one part per million between Windows with numpy 1.26 and Linux
with numpy 2.5, because the simulator locates each switching instant by secant
iteration and the closed loop integrates those last bit differences over
thousands of cycles. The tolerance is stated, the worst deviation is printed on
every run, and non-numeric tokens still have to match exactly.

---

## Not done, and honestly so

**No hardware exists.** No board has been fabricated, no part has been bought,
nothing has been assembled, powered, probed or measured. Every directory called
`test-results` contains simulation output. The name is the layout the project
brief asks for, not a claim.

**No Altium project.** The brief named Altium; it is not available here, so
the schematic and board are in KiCad, the free tool a team without an Altium
licence would use. `altium/README.md` says so where somebody would look.

**Five connections are unrouted.** The autorouter left three at the +12V
boost's synchronous FET Q4 (its source pad, on SW_12V, is not joined to the
rest of the switch node) and two in the +5V controller's VIN feed (U1 pin 17,
the RUN divider top R11 and the bypass C16 are not joined to the VIN pour).
DRC reports them and nothing else; CI fails if the count rises. They need
routing by hand before the board could be built.

**The layout has not been reviewed.** Placement is generated by stage region
and the routing is an autorouter's. Neither has been through the checklist in
`docs/layout_rules.md`: switching loop areas, Kelvin routing of the shunts,
keeping the feedback nodes away from the switch nodes and the ground return
paths have not been checked against the CAD file. The board is spread out
rather than compact and the switch node and input loop copper is narrower than
a hand layout would make it. It is a DRC-clean starting point, not a design
ready for fabrication.

**Parts are selected but not fully verified.** Every part is real and its
headline figures were checked; no part has had its whole data sheet read
against the model. `outputs/VERIFY.csv` says where they disagree and several
do: the TPS54317's FETs are 59 mOhm against 30 and 20 mOhm modelled, so +3V3
efficiency and U3's temperature are optimistic; the AO3400A's gate charge is
more than double the model's; the LTC3891 drives its gates at about 5.1 V where
the loss model assumes 7.5 V; the input filter's real L4 DCR, C3 ESR and C12
(an X7R MLCC, not film) all change its damping, so the Middlebrook margin has
to be re-run; and the two current mode loops' current sense gains are still
model assumptions. Core loss coefficients, switching times and the LDO's
stability envelope are also still assumptions.

**Two parts need a land pattern check.** The TPS54317 uses a generic 4 by 5 mm
QFN-24 footprint and the XGL inductors the XAL footprints of the same body
size. Both are noted on the parts and have to be checked against the
manufacturers' drawings.

**Ceramic derating factors are assumptions.** Every capacitance in the models is
derated for DC bias, which is the right thing to do, but by assumed factors
rather than measured ones. They are the single most likely reason a bench
ripple measurement would disagree with the predictions here.

**The LDO loop model is behavioural.** Its gain, poles and zero are parameters
chosen to represent a device class, not a device. `docs/compensation/ldo1v8.md`
is explicit about which parts of that rail this project designs, which is the
output capacitor, the preload and the input filter, and which it inherits.

**No switching SPICE deck for the current mode rails.** A peak current
modulator is a comparator, a latch, an artificial ramp and a blanking window,
and the numbers that matter live inside a specific controller. Writing an
invented version would produce a deck that runs, looks convincing and validates
nothing. The right move once a controller is chosen is to run the vendor's own
model. The voltage mode rail does have a full switching deck, because a
sawtooth and a comparator are fully specified.

**Common mode emissions are not modelled at all.** The pre-scan is differential
mode only, because common mode depends on the parasitic capacitance of a
finished, reviewed layout, which this is not yet. On real hardware it is very often the term that fails.

**Discontinuous conduction is not modelled.** Below roughly 10 percent load the
models stop describing the converters. The efficiency curves are plotted down
to 2 percent anyway and their light load ends should be read as optimistic.

**Cascaded converter interaction is not modelled.** The +3V3 and +12V stages
draw pulsed current from the +5V rail, and the +5V stage's output impedance and
their input impedances interact. That is the same class of problem as the input
filter check that *is* done, one level down, and it has not been done.

**The thermal model assumes an isothermal board.** It will not be. Expect the
FET hot spot to be worse than predicted and the far corners better.

---

## The thinnest result

The conducted emissions margin at low line is **4.7 dB**. That is a positive
margin against a reference envelope, from a model that omits common mode
entirely. It should be treated as the weakest claim in the repository and as
the first thing a real pre-scan looks at.

The second thinnest is the switching loss estimate on the +5V stage, which is
the largest single loss term at high line and carries roughly a factor of two
of uncertainty in either direction.

---

## The project brief's build checklist

The brief this repository was built from lists fourteen milestones. Where they
stand:

- [x] Written specification: rails, currents, ripple, transient, thermal
- [x] Topology selection and component sizing
- [x] Pre-layout validation. Done with the switching simulator in this
      repository rather than LTspice, plus SPICE decks for the parts that can
      be checked in SPICE exactly. See `outputs/README.md` for what is emitted
      and what deliberately is not
- [x] Loop compensation derivation, by hand, with the working shown
- [x] Schematic capture. In KiCad 8 rather than Altium, ERC clean, every
      value held to the simulation in CI
- [ ] 4-layer layout. Done to the stackup and DRC clean apart from five
      unrouted connections; not yet reviewed against `docs/layout_rules.md`
- [ ] Fabrication and assembly
- [ ] Bring-up. Procedure written with a predicted value for every measurement,
      not performed
- [ ] Load and line regulation **measurement**. Simulated only
- [ ] Efficiency curves **measured**. Predicted only
- [ ] Bode **measurement**. Simulated only, using the same injection method and
      the same formula a bench analyser uses
- [ ] Transient response **measured**. Simulated only
- [ ] Thermal **measured** under full load. Modelled only
- [ ] EMC near-field pre-scan. Conducted differential mode modelled only, and
      near field needs a board
- [x] Validation report, generated, and explicit about which of the above it
      does and does not cover

Everything unticked apart from the layout needs hardware.

### Hardware TODO

These are the bench measurements the simulation stands in for. None has been
done and none can be without a board and instruments:

* **Efficiency curves**, across load at 8, 24 and 36 V in, against
  `test-results/efficiency/`.
* **Bode plots** of all three switching loops with an injection transformer
  across the 20 ohm links (R14, R22, R32), against `test-results/bode/`.
* **EMC pre-scan**, conducted through a LISN and near field over the board,
  against `test-results/emc-prescan/`, which is differential mode only.
* Line and load regulation, ripple, load steps and a full load thermal soak,
  against the matching directories in `test-results/`.

`docs/bring_up.md` gives the predicted value for each.

---

## Open items, in the order they would be done

1. Finish reading each selected part's data sheet into the model, starting
   with the TPS54317 FET resistance, the input filter parts and the two current
   sense gains. Re-run and see what moves.
2. Run the vendors' models for the LTC3891 and TPS43061 and compare against
   the loop gains here.
3. Route the five open connections by hand, then review the layout against
   `docs/layout_rules.md`, answering its checklist from measurements off the
   CAD file. Tighten the switching loops.
4. Check the TPS54317 and XGL land patterns against the manufacturers'
   drawings.
5. Fabricate and assemble.
6. Bring-up against `docs/bring_up.md`, which has a predicted value for every
   measurement, written before the board.
7. Add measured results to `test-results/` alongside the simulated ones,
   clearly named, without deleting the predictions.
