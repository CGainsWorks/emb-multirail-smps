# +3V3 buck: voltage mode, Type III compensation

Target: crossover 100 kHz, phase margin at least 55 degrees, gain margin at
least 8 dB, from a regulated 5 V input.

This rail is deliberately compensated differently from the other two. It is fed
from the +5V rail rather than from VIN, so the one percent input band removes
the main argument for current mode, and at 1 MHz a current sense chain costs a
shunt, an amplifier and a leading edge blanking window that a sawtooth and a
comparator do not. What it costs instead is six passives rather than three, and
an LC double pole to get the phase back over.

---

## 1. The plant

```
L        = 1.5 uH             DCR     = 15 mOhm
Cout     = 33 uF              ESR     = 1.0 mOhm  (two 22 uF 16 V, derated 0.75)
Rds(on)  = 30 mOhm high side, 20 mOhm low side
fsw      = 1 MHz
Vin      = 5.0 V              Vramp   = 1.0 Vpp
```

A voltage mode buck's control to output response is the modulator gain times
the LC filter:

```
Gvd(s) = (Vin / Vramp) * (1 + s/w_esr) / (1 + s/(w0 Q) + (s/w0)^2)
```

with

```
Vin/Vramp = 5.0                                            (14.0 dB)
f0        = 1 / (2 pi sqrt(1.5e-6 * 33e-6))   = 22.6 kHz
Q         = R sqrt(C/L) = 1.1 * sqrt(22)      = 5.16       at full load
f_esr     = 1 / (2 pi * 1e-3 * 33e-6)         = 4.8 MHz    (irrelevant)
```

The numeric model, which includes the DCR and the switch resistances, puts the
magnitude peak at 22.2 kHz rather than 22.6 kHz, and damps it somewhat. That is
the whole difference between the closed form above and what
`statespace.buck_model` produces.

The problem to solve is the 180 degrees the double pole takes out inside about
one octave. At 100 kHz the plant has already given up essentially all of it,
so the compensator has to hand back roughly 50 degrees to reach a 55 degree
margin. One zero cannot do that. Two can.

---

## 2. The network

Type III around a voltage feedback error amplifier:

```
Zf = (Rf + 1/sCf1) || 1/sCf2            from COMP back to FB
Zi = R1 || (R3 + 1/sCf3)                from Vout to FB
Gc(s) = Zf / Zi
```

`R1` is the top divider resistor, so the divider is inside the network and does
not appear separately in the loop gain. The bottom resistor sits on a virtual
earth and does not appear in the small signal transfer at all, which is worth
knowing when reading the loop gain plot and wondering where it went.

Zeros, poles and the values that produce them:

```
fz1 = 1 / (2 pi Rf Cf1)
fz2 = 1 / (2 pi (R1 + R3) Cf3)
fp2 = 1 / (2 pi Rf (Cf1 Cf2 / (Cf1 + Cf2)))
fp3 = 1 / (2 pi R3 Cf3)
```

### Placement

* **Both zeros at half the LC resonance, 11.1 kHz.** Putting them together at
  `f0/2` gives close to the maximum phase boost at 100 kHz while keeping the
  loop gain shape simple. Splitting them, one below `f0` and one above, buys a
  slightly flatter magnitude and slightly less boost.
* **First pole at fsw/2, 500 kHz**, to attenuate switching ripple on the FB
  pin. With ceramic output capacitors the ESR zero is at 4.8 MHz, so there is
  nothing at a sensible frequency for this pole to cancel and its job is purely
  noise rejection.
* **Second pole at fsw, 1 MHz**, for the same reason.
* **Gain solved for** so that `|Gc(fc) Gvd(fc)| = 1` at exactly 100 kHz.

### Values

```
R1   = 10.2 kOhm      chosen, sets the divider current at about 0.25 mA
Rbot = R1 * 0.8 / (3.3 - 0.8) = 3.264 kOhm -> 3.24 kOhm (E96)
Vout = 0.8 * (10.2 + 3.24) / 3.24 = 3.3185 V     (+0.56 % from nominal)

R3   = R1 / (fp3/fz2 - 1) = 10.2k / 89 = 115 Ohm (E96)
Cf3  = 1 / (2 pi * 11.1e3 * (10.2k + 115)) = 1.39 nF -> 1.3 nF (E24)
Rf   = 4.53 kOhm (E96), solved for the crossover
Cf1  = 1 / (2 pi * 11.1e3 * 4.53e3) = 3.17 nF -> 3.3 nF (E24)
Cf2  = Cf1 / (2 pi fp2 Rf Cf1 - 1)  = 76 pF   -> 75 pF (E24)
```

With those snapped values the network actually sits at

```
fz1 = 10.65 kHz     fz2 = 11.87 kHz
fp2 = 479 kHz       fp3 = 1.065 MHz
```

---

## 3. Predicted margins

Contributions at 100 kHz:

| term | phase at 100 kHz |
|---|---|
| compensator integrator | -90.0 deg |
| zero at 10.65 kHz | +83.9 deg |
| zero at 11.87 kHz | +83.2 deg |
| pole at 479 kHz | -11.8 deg |
| pole at 1.065 MHz | -5.4 deg |
| plant LC double pole, 22.2 kHz, Q ~ 5 | -177.4 deg |
| plant ESR zero, 4.8 MHz | +1.2 deg |
| **total** | **-116.2 deg** |

Phase margin 63.8 degrees by hand against the numeric model's **65.3 degrees at
99.1 kHz**. The switching simulation gives **69.3 degrees at 95.5 kHz**.

The hand sum is the pessimistic one of the three, by about 1.5 degrees, and the
reason is in the row that dominates it. The closed form treats the LC pair as
undamped apart from the load, so at 100 kHz it has already surrendered 177.4 of
its 180 degrees. The numeric model carries the inductor DCR and both switch
resistances as well, which damps the resonance and leaves a little phase still
to give up at crossover. That is the correction the parasitics buy, and it is
why the numeric model is the one the compensator is designed against.

Gain margin from the model is 16.9 dB, with the -180 degree crossing at
456 kHz. The switching measurement cannot confirm that one: sampling once per
switching cycle puts a Nyquist limit at 500 kHz and the sweep stops short of
it, so the simulated trace never reaches -180 degrees inside the measurable
band. A bench analyser triggered off the switching clock has the same limit for
the same reason, and the honest statement is that the phase stays above -180
degrees everywhere the measurement can see.

The finite gain bandwidth of the error amplifier, taken as 12 MHz with 80 dB of
open loop gain, is included in the analytic response. It costs about 1.4
degrees at crossover.

---

## 4. Across the operating range

| operating point | fc | PM | GM |
|---|---|---|---|
| 5.00 V, 3.0 A | 99.1 kHz | 65.3 deg | 16.9 dB |
| 4.95 V, 3.0 A | 98.3 kHz | 65.4 deg | 17.0 dB |
| 5.05 V, 3.0 A | 100.0 kHz | 65.2 deg | 16.8 dB |
| 5.00 V, 0.3 A | 99.8 kHz | 62.8 deg | 16.7 dB |

A one percent input band moves the crossover by one percent, which is what a
voltage mode modulator with gain `Vin/Vramp` should do and is the reason this
scheme is only acceptable on a rail with a regulated input. Put the same loop
on 8 to 36 V and the crossover would move by a factor of 4.5.

Light load raises the LC Q, which is why the phase margin is worst at 0.3 A
rather than at full load. It is still 7.8 degrees above target.

---

## 5. What would change this

1. **The ramp amplitude.** `Vramp = 1.0 Vpp` is an assumption about an
   unselected part, and crossover is inversely proportional to it. On
   `outputs/VERIFY.csv`.
2. **Ceramic derating at 3.3 V.** The 0.75 retention factor sets the LC
   resonance. If the real parts hold 0.6, `f0` moves to 25 kHz and both
   compensator zeros are then placed too low.
3. **Discontinuous conduction below about 0.4 A.** Below that the inductor
   current touches zero, the plant becomes first order and this compensator is
   over compensated rather than under, which is the safe direction but is not
   modelled here.
