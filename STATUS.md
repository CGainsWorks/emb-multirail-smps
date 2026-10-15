# Project status

Last updated: 22 August 2026

This file records what actually exists in this repository, so that nothing in
the README or on a CV overstates it. Update it as items move between sections.

---

## The one sentence version

The electrical design is complete and validated in simulation. **No board has
been fabricated, assembled, powered or measured, and there is no Altium
project.** Every number in `test-results/` is computed, not measured.

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

**The two routes agree.** Worst crossover disagreement 5.8 percent, worst phase
margin disagreement 4.0 degrees, across all three switching rails. This is the
gate the project brief sets before boards are ordered, and it is met.

**Simulated regulation, ripple, transient, efficiency, thermal and conducted
EMC**, with the input filter also checked against Middlebrook's criterion.

**Netlist.** A Protel format connection list that Altium imports, 51 parts and
29 nets, with integrity checks in the test suite.

**A third simulator agrees.** The compensation networks are emitted as ngspice
decks and run by CI on every push, with the results compared against the closed
forms. Worst disagreement across the three networks and the input filter is
0.0001 dB and 0.110 degrees, against an enforced tolerance of 0.01 dB and
0.2 degrees. The switching deck settles the +3V3 rail at 3.3185 V, which is
what the divider asks for to five figures. The hand derivation and the switching
simulator are both written here, so a shared misconception in them would agree
with itself; ngspice knows nothing about either. LTspice decks are emitted in a
separate directory and have never been run, because no Linux runner has an
LTspice. An earlier version of this repository claimed the decks were portable
between the two, which was untrue and is now asserted against.

**Test suite.** 123 tests, no hardware needed, running in about a minute.
Among them, a set that reads the generated CSVs back and fails if any number
quoted in the README has drifted away from them, which it had, twice, before
that check existed. One test skips unless ngspice is installed; CI installs it.

**CI, running.** One job: tests, regeneration, a check that the committed
results still match what the code produces, and a guard on every number the
README quotes. Built for a free account, so it is one job rather than four,
with path filters, concurrency cancellation, a pip cache and a hard timeout.
About 2 to 3 minutes per push. `make ci` is the same sequence locally.

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

**No Altium project.** No schematic capture, no layout, no Gerbers, no
fabrication pack, no 3D model. `altium/README.md` says the same thing in the
place somebody would look for it. What exists instead is the netlist, the BOM,
the stackup definition and the layout constraint set.

**No part has been verified against a datasheet.** Every candidate part number
in `outputs/bom.csv` is marked unverified, and `outputs/VERIFY.csv` lists what
has to be checked for each one before anything is ordered. Rds(on), Qg, Qoss,
switching times, saturation currents, core loss coefficients, error amplifier
transconductance, ramp amplitude and the LDO's stability envelope are all
modelling assumptions.

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
mode only, because common mode depends on the parasitic capacitance of a layout
that does not exist. On real hardware it is very often the term that fails.

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
- [ ] Schematic capture in Altium. Netlist provided, schematic not captured
- [ ] 4-layer layout. Stackup defined and layout rules written, layout not done
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

Everything unticked needs hardware. Everything tickable without hardware is
ticked.

---

## Open items, in the order they would be done

1. Select real parts and replace every row of `outputs/VERIFY.csv` with a
   datasheet figure. Re-run and see what moves.
2. Run the vendor's LTspice model for the chosen controllers and compare
   against the loop gains here.
3. Schematic capture in Altium from `outputs/netlists/board.net`.
4. Layout against `docs/layout_rules.md`, with the review checklist in that
   file answered from measurements off the CAD file.
5. Fabricate and assemble.
6. Bring-up against `docs/bring_up.md`, which has a predicted value for every
   measurement, written before the board.
7. Add measured results to `test-results/` alongside the simulated ones,
   clearly named, without deleting the predictions.
