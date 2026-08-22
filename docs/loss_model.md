# Loss model

What `simulation/smps/losses.py` computes, term by term, and how wrong each
term is likely to be. Nothing here is measured.

The point of a loss breakdown rather than a single efficiency figure is that it
says *where* the power goes, and therefore what is worth changing. A fitted
efficiency curve tells you nothing you can act on.

---

## Terms

### Conduction

```
I_rms^2 = I_avg^2 + dI^2 / 12                triangular ripple on a DC level
P_hs    = D  * I_rms^2 * Rds(on,hs)
P_ls    = D' * I_rms^2 * Rds(on,ls)
P_dcr   =      I_rms^2 * DCR
```

Expected error: **plus 30 to 40 percent** on a hot board. Every Rds(on) and DCR
in `components.py` is a room temperature value, and silicon Rds(on) rises
roughly 0.4 percent per degree. At a 95 degree junction that is about 30 percent
more than modelled. The model does not iterate temperature against loss, and it
says so here rather than pretending the number is a prediction at temperature.

### Switching

```
P_sw = 0.5 * V_switched * I_out * (t_rise + t_fall) * fsw
```

Expected error: **a factor of two, either way.** This is the least trustworthy
term in the model, and on the +5V rail at high line it is also the largest one.
The overlap times depend on gate drive current, gate charge, common source
inductance and the layout's loop inductance, and the first is a design choice
that has not been made while the last does not exist yet. The 12 ns used for
the buck FETs is a plausible figure for a well driven 60 V device, and it is an
assumption.

At 36 V and full load this term alone is 0.99 W of the board's 3.3 W. If a
bench measurement ever disagrees with the efficiency curves in this repository,
this is the first term to suspect.

### Output charge and gate drive

```
P_oss  = Qoss * V_switched * fsw
P_gate = (Qg_hs + Qg_ls) * Vgs * fsw
```

Both are exactly proportional to switching frequency and both are load
independent, which is what makes the light load end of the efficiency curves
fall. Gate drive loss is attributed to the FETs in the thermal model, which is
a simplification: most of it is actually dissipated in the driver inside the
controller. `docs/thermal_model.md` repeats that caveat where it matters.

### Dead time

```
P_dt = Vf_body * I_out * 2 * t_dead * fsw
```

The body diode conducts for both dead time intervals every cycle. Thirty
nanoseconds of dead time on the buck at 500 kHz is 3 percent of the period, and
it costs 120 mW at full load. Halving the dead time would recover most of that,
which is a real design lever, and it is not free: too little dead time is
shoot-through.

### Core loss

```
B_ac = L (dI/2) / (N Ae)
Pv   = k f^alpha B^beta                      W per cubic metre
P_core = Pv * Ve
```

Expected error: **a factor of three.** The Steinmetz coefficients are assumed
rather than fitted to any real part's loss curves, and the effective area,
volume and turn count are estimates for a package size rather than measurements
of a component. The saving grace is that core loss is small here, about 10 mW
on the largest inductor against 234 mW of DCR loss, so even a factor of three
does not move the total much. That would not be true at a higher ripple ratio
or a higher frequency.

### Capacitor ESR

```
buck  Cin  : I_rms^2 = I_out^2 D D'
buck  Cout : I_rms^2 = dI^2 / 12
boost Cout : I_rms^2 = I_out^2 D / D'
```

Small everywhere on this board, single digit milliwatts, because the capacitors
are ceramic. Included because a design that later moved to electrolytics would
see these terms grow by two orders of magnitude and the model should not have
to be rewritten to notice.

### LDO

```
P_filter = R_f1 * I_total^2
P_pass   = (V_after_filter - Vout) * I_total
P_preload= Vout * I_preload
P_q      = Vin * Iq
```

This one is not really a model, it is arithmetic. A linear regulator's loss is
the voltage it drops times the current through it, and the only modelling
choice is remembering that the preload current and the input filter resistor
are both in that path. At 0.5 A the whole rail dissipates 0.78 W to deliver
0.90 W.

---

## Where it lands

At 24 V in and full load on every rail, from
`test-results/efficiency/system_efficiency.csv`:

```
input           24.4 W
useful output   21.4 W
total loss       2.95 W
efficiency      87.9 %
```

The twelve largest terms are plotted in
`test-results/efficiency/loss_breakdown.png`. At 36 V the total rises to 3.3 W
and switching loss on the +5V stage is the single biggest line by a factor of
three over anything else.

## The obvious levers, and why they were not pulled

**Lower the +5V switching frequency.** Halving it to 250 kHz would roughly
halve 1.2 W of frequency proportional loss. It would also double the inductor
value needed for the same ripple, which means a physically larger part, and
halve the achievable loop bandwidth, which fails the transient specification.
500 kHz is the point where those meet for this specification.

**Faster edges.** Going from 12 ns to 6 ns halves the switching loss. It also
doubles the dv/dt at the switch node, which is the driver for both the common
mode emissions this repository cannot predict and the switch node ringing that
depends on a layout that does not exist. That trade cannot honestly be made
before there is a board to measure.

**Better FETs.** Conduction loss on the +5V stage is only 244 mW, so a lower
Rds(on) part buys very little. A lower Qoss and Qg part would buy more. That is
a part selection exercise that needs real datasheets, and it is on
`outputs/VERIFY.csv`.
