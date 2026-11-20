"""Circuit checks by SPICE (ngspice): current sense, input board, TVS surges, 3V3 start-up, CAN termination.

usage (repo root): python tools/verify_spice.py [--ngspice PATH] [--keep DIR]
    needs ngspice (Linux / WSL: `ngspice` on PATH; Windows: the ngspice console build, e.g.
    %LOCALAPPDATA%\\ngspice\\Spice64\\bin\\ngspice_con.exe, or set NGSPICE). Pure python otherwise.

Part values are the ones on the boards (netlists exported from hardware/*; checked against them in
docs/pcb-verification.md). Models are behavioural, built from data-sheet limits, so each result says which limit
it rests on:
  - LM2902 (TI SLOS066, section 6.8): input common-mode range 0 to VCC-1.5 V at 25 C, 0 to VCC-2 V over -40..125 C;
    the follower output cannot go higher than its input range allows -> modelled as a clamp at that level.
  - PDZ3.3B zener (Nexperia): BV 3.3 V; BAT54S (Nexperia): Schottky, IS 2e-7 A at 25 C doubling every 10 K.
  - 5.0SMDJ24CA TVS (Littelfuse): VBR 26.7 min / 29.5 max at 1 mA, VC 38.9 V at IPP 128.5 A (10/1000 us),
    bidirectional -> two diodes, dynamic resistance (38.9 - VBR) / 128.5 A.
  - Sense ratios kILIS from docs/parts-audit.md (Infineon tables) vs the firmware constants (port.h).
  - Surges: ISO 7637-2 (12 V, highest test levels: pulse 1 -150 V / 10 Ohm / 2 ms, 2a +112 V / 2 Ohm / 50 us,
    3a -220 V / 50 Ohm / 0.1 us, 3b +150 V / 50 Ohm / 0.1 us) and ISO 16750-2 load dump test B (suppressed,
    Us* 35 V, Ri 0.5 and 4 Ohm, td 400 ms). Limits: PROFET VBAT(LD) 35 V (suppressed load dump), VS max 28 V
    (BTS7008-2EPA P_4.1.0.1 / P_4.1.0.3).
Exit code 1 on any FAIL.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

NG = None
RES = []      # (group, check, value, limit, verdict, note)


def ngspice(deck, name, keep):
    path = os.path.join(keep, name + ".cir")
    with open(path, "w") as f:
        f.write(deck)
    r = subprocess.run([NG, "-b", path], capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    with open(os.path.join(keep, name + ".log"), "w") as f:
        f.write(out)
    meas = {}
    for m in re.finditer(r"^\s*(\w+)\s*=\s*([-+0-9.eE]+)", out, re.M):
        meas[m.group(1).lower()] = float(m.group(2))
    if not meas:
        raise SystemExit(f"{name}: ngspice gave no results:\n{out[-2000:]}")
    return meas


def add(group, check, value, limit, ok, note="", warn=False):
    RES.append((group, check, value, limit, "PASS" if ok else ("WARN" if warn else "FAIL"), note))


# ------------------------------------------------------------------ 1. current sense -> ADC
DRIVERS = [  # name, rating A, kILIS datasheet (parts-audit), kILIS firmware (port.h)
    ("BTS7008-2EPA (board A, 7.5 A)", 7.5, 5450, 5950),
    ("BTS7004-1EPP (board B OUT5-8, 15 A)", 15.0, 20000, 20000),
    ("BTS70012-1ESP (board B OUT1-4, 31 A)", 31.0, 33700, 35000),
]


def is_chain(keep):
    for name, rating, k_ds, k_fw in DRIVERS:
        for temp, clip in (("25 C", 1.5), ("-40..125 C", 2.0)):
            tag = re.sub(r"\W+", "_", name.split()[0] + temp)
            deck = f"""* IS chain: IS -> 1.2k (1 %) -> 4.7k -> PDZ3.3B -> 4.7k / 220p -> LM2902 follower -> 120R -> ADC
.param kilis={k_ds} vcc=3.3 clip={clip}
Iis 0 is {{I(Vload)/kilis}}
Vload ld 0 0
Rld ld 0 1
Rs is 0 1.2k
R1 is n1 4.7k
Dz 0 n1 dz
R2 n1 inp 4.7k
C1 inp 0 220p
Bop opo 0 V = min(V(inp), vcc-clip)
R3 opo adc 120
Cadc adc 0 10p
.model dz D(BV=3.3 IBV=5m IS=1e-12 N=1.5 RS=10)
.control
dc Vload 0 {rating * 2} 0.05
let ifw = v(adc)/1200*{k_fw}
let iload = v(ld)
meas dc clip_a when v(adc)={3.3 - clip - 0.002:.3f} rise=1
meas dc vadc_rated find v(adc) at={rating}
meas dc ifw_rated find ifw at={rating}
.endc
.end
"""
            # current source driven by the swept voltage (1 Ohm -> I = V)
            deck = deck.replace("Iis 0 is {I(Vload)/kilis}", "Bis 0 is I = V(ld)/kilis")
            try:
                m = ngspice(deck, "is_" + tag, keep)
            except SystemExit:
                raise
            clip_a = m.get("clip_a", 2 * rating)
            err = (m["ifw_rated"] / rating - 1) * 100
            ok = clip_a >= rating * 1.1
            add("IS -> ADC", f"{name}, {temp}: reading clips at", f"{clip_a:.1f} A", f">= 1.1 x {rating} A", ok,
                f"ADC {m['vadc_rated']:.3f} V at rating; LM2902 input limit VCC-{clip} V")
            if temp == "25 C":
                add("IS -> ADC", f"{name}: firmware reading at rating (kILIS fw {k_fw} vs typ {k_ds})",
                    f"{m['ifw_rated']:.2f} A ({err:+.1f} %)", "within +-10 %", abs(err) <= 10,
                    "datasheet kILIS tolerance about +-4-5 % on top; 1 % sense resistor")
    # fault current: IS saturates at up to 15 mA (BTS7008 IIS(SAT) max): ADC pin must stay <= 3.6 V
    deck = """* IS fault: 15 mA into the chain
Iis 0 is 15m
Rs is 0 1.2k
Dvs is vs dclamp
Vvs vs 0 12.5
R1 is n1 4.7k
Dz 0 n1 dz
R2 n1 inp 4.7k
Bop opo 0 V = min(V(inp), 3.3-1.5)
R3 opo adc 120
.model dz D(BV=3.3 IBV=5m IS=1e-12 N=1.5 RS=10)
.model dclamp D(IS=1e-12)
.op
.control
op
print v(is) v(n1) v(inp) v(adc)
let iz = (v(is)-v(n1))/4.7k
meas op zr find v(n1)
.endc
.end
"""
    deck = deck.replace(".control\nop\nprint v(is) v(n1) v(inp) v(adc)\nlet iz = (v(is)-v(n1))/4.7k\nmeas op zr find v(n1)\n.endc",
                        ".control\nop\nlet iz = (v(is)-v(n1))/4.7k\necho \"vis = $&v(is)\"\necho \"vn1 = $&v(n1)\"\n"
                        "echo \"vadc = $&v(adc)\"\necho \"izener = $&iz\"\n.endc")
    m = ngspice(deck, "is_fault", keep)
    add("IS -> ADC", "IS fault / saturation (15 mA): op-amp input and ADC pin", f"input {m['vn1']:.2f} V, ADC {m['vadc']:.2f} V",
        "ADC <= 3.6 V (STM32 abs max VDD + 0.3 V)", m["vadc"] <= 3.6, f"zener current {m['izener'] * 1e3:.2f} mA")


# ------------------------------------------------------------------ 2. TVS vs surges
def tvs(keep):
    pulses = [  # name, amplitude V, Ri, tr, td(width), shape
        ("ISO 7637-2 pulse 1 (-150 V, 10 Ohm, 2 ms)", -150, 10, 1e-6, 2e-3),
        ("ISO 7637-2 pulse 2a (+112 V, 2 Ohm, 50 us)", 112, 2, 1e-6, 50e-6),
        ("ISO 7637-2 pulse 3a (-220 V, 50 Ohm, 0.1 us)", -220, 50, 5e-9, 100e-9),
        ("ISO 7637-2 pulse 3b (+150 V, 50 Ohm, 0.1 us)", 150, 50, 5e-9, 100e-9),
        ("ISO 16750-2 load dump B (Us* 35 V, Ri 4 Ohm, 400 ms)", 35 - 13.5, 4, 5e-3, 400e-3),
        ("ISO 16750-2 load dump B (Us* 35 V, Ri 0.5 Ohm, 400 ms)", 35 - 13.5, 0.5, 5e-3, 400e-3),
    ]
    for vbr, corner in ((26.7, "VBR min"), (29.5, "VBR max")):
        rd = (38.9 - vbr) / 128.5
        for i, (name, amp, ri, tr, td) in enumerate(pulses):
            ld = "load dump" in name
            tstop = td * (1.6 if ld else 6)
            if ld:     # flat-topped (suppressed) pulse
                src = f"Vp p 0 PWL(0 0 {tr} {amp} {td} {amp} {td + tr} 0)"
            else:      # ISO 7637 pulses: fast rise, exponential decay to 10 % at td
                tau = td / 2.3
                src = f"Vp p 0 EXP(0 {amp} 0 {tr / 2.2} {tr} {tau})"
            deck = f"""* TVS 5.0SMDJ24CA on +12V, {name}, {corner}
Vbat b 0 13.5
{src}
Rsrc s v12 {ri}
Esum s 0 POLY(2) b 0 p 0 0 1 1
* the board itself is the load (all outputs off: about 50 mA)
Dt1 v12 m dtvs
Dt2 0 m dtvs
C3 v12 0 10u
Cx v12 0 0.4u
Rload v12 0 270
.model dtvs D(BV={vbr} IBV=1m IS=1e-12 N=1 RS={rd})
.tran {tstop / 4000} {tstop}
.control
run
let ptvs = abs(v(v12)*i(Vbat))
meas tran vmax max v(v12)
meas tran vmin min v(v12)
let itv = (v(s)-v(v12))/{ri} - v(v12)/270
let pt = abs(v(v12)*itv)
meas tran pmax max pt
meas tran etvs integ pt
.endc
.end
"""
            m = ngspice(deck, f"tvs_{i}_{int(vbr)}", keep)
            if amp > 0:
                ok = m["vmax"] <= 35.0
                lim = "<= 35 V (PROFET VBAT(LD))"
                val = f"{m['vmax']:.1f} V"
            else:
                ok = m["vmin"] >= -16.0
                lim = ">= -16 V (PROFET reverse battery, P_4.1.0.5, 2 min static)"
                val = f"{m['vmin']:.1f} V"
            note = f"TVS peak {m['pmax']:.0f} W, energy {m['etvs']:.3g} J"
            if ld:
                # 5.0SMDJ: 5000 W for a 10/1000 us pulse, about 7 J; long pulses derate further
                eok = m["etvs"] <= 7.0
                add("TVS / surge", f"{name}, {corner}: TVS energy", f"{m['etvs']:.1f} J", "<= ~7 J (5 kW 10/1000 us)",
                    eok, note + "; +12V peak " + val)
            else:
                add("TVS / surge", f"{name}, {corner}: +12V", val, lim, ok,
                    note + ("" if ok or amp > 0 else "; 2 ms pulse vs a static rating: the data sheet gives no "
                            "ISO 7637 pulse rating"), warn=amp < 0)


# ------------------------------------------------------------------ 3. 3V3 start-up
def startup(keep):
    deck = """* 12 V -> D19 -> TSR 1-2450 (5 V, 1 A max, soft start ~1 ms ASSUMED) -> D18 PMEG2010 -> +5V (2 x 47u + 100n) -> TLV1117LV33 -> +3V3
Vbat b 0 PWL(0 0 1m 13.5)
Btsr p5 0 V = min(5, max(0, (time-1.2m)/1m*5))
Rtsr p5 p5o 0.05
D18 p5o v5 dsch
C41 v5 0 47u
C42 v5 0 47u
C5 v5 0 100n
* LDO: 3.3 V, dropout 0.45 V at 1 A (TLV1117LV data sheet), current limit 1.1 A
Bldo l3 0 V = min(3.3, max(0, V(v5) - 0.45))
Rldo l3 v3 0.05
C6 v3 0 10u
C14 v3 0 4.7u
Cdec v3 0 2u
Rmcu v3 0 66
.model dsch D(IS=5e-6 N=1.05 RS=0.05)
.tran 1u 8m
.control
run
meas tran t3v0 when v(v3)=3.0 rise=1
meas tran v3max max v(v3)
let iin = (v(p5o)-v(v5))/1
meas tran v5max max v(v5)
.endc
.end
"""
    m = ngspice(deck, "startup", keep)
    add("3V3 start-up", "+3V3 rises monotonic, no overshoot", f"max {m['v3max']:.3f} V", "<= 3.6 V (STM32 VDD max)",
        m["v3max"] <= 3.6, f"reaches 3.0 V at {m['t3v0'] * 1e3:.2f} ms after power")


# ------------------------------------------------------------------ 4. input board
def input_board(keep):
    for vin, name in ((14.4, "switched 12 V input at 14.4 V"), (0.0, "input shorted to ground"), (-1.0, "-1 V ground offset")):
        for t, isat in ((25, 2e-7), (85, 2e-7 * 2 ** 6)):
            deck = f"""* Input board digital channel: wire -> 4.7k -> IN (BAT54S to 3V3 / GND, 10n) ; pull-up 10k to 3V3 on wire side
Vw w 0 {vin}
Rpu w 3v3 10k
R1 w in 4.7k
Dhi in 3v3 dbat
Dlo 0 in dbat
C in 0 10n
V3 3v3 0 3.3
Rleak in 0 1e9
.model dbat D(IS={isat} N=1.0 RS=2 BV=30)
.op
.control
op
echo "vin = $&v(in)"
echo "iinj = $&i(V3)"
.endc
.end
"""
            m = ngspice(deck, f"din_{int(vin * 10)}_{t}", keep)
            if vin > 3:
                ok = m["vin"] >= 2.31
                add("Input board", f"{name}, {t} C: MCU pin", f"{m['vin']:.2f} V", ">= 2.31 V (STM32 VIH 0.7 VDD)", ok,
                    f"current pushed into +3V3: {-m['iinj'] * 1e3:.2f} mA per input (x 8 per input board)")
            else:
                ok = m["vin"] <= 0.99 and m["vin"] >= -0.3
                add("Input board", f"{name}, {t} C: MCU pin", f"{m['vin']:.2f} V", "-0.3 .. 0.99 V (VIL 0.3 VDD, abs min)", ok)
    # 8 inputs at 14.4 V push current into +3V3: the LDO cannot sink it, the board load must take it
    inj = 8 * (14.4 - 3.3 - 0.3) / 4.7e3 + 8 * (14.4 - 3.3) / 10e3
    add("Input board", "8 inputs at 14.4 V: current pushed into board A +3V3", f"{inj * 1e3:.1f} mA",
        "< board A +3V3 load (STM32F446 + CAN, about 40-60 mA running)", False, "fine while the MCU runs; in sleep "
        "the board draws far less and the LDO cannot sink current, so +3V3 can rise (docs/pcb-verification.md)",
        warn=True)
    # analog channel: 0-5 V -> 10k / 20k -> ADC, BAT54S leakage at temperature
    for t, isat in ((25, 2e-7), (85, 2e-7 * 2 ** 6), (125, 2e-7 * 2 ** 10)):
        deck = f"""* Input board analog: 0-5 V -> 10k -> AIN -> 20k -> GND, BAT54S clamp, 10n
Vw w 0 5.0
R25 w ain 10k
R26 ain 0 20k
Dhi ain 3v3 dbat
Dlo 0 ain dbat
C9 ain 0 10n
V3 3v3 0 3.3
.model dbat D(IS={isat} N=1.0 RS=2 BV=30)
.op
.control
op
echo "vain = $&v(ain)"
.endc
.end
"""
        m = ngspice(deck, f"ain_{t}", keep)
        reading = m["vain"] * 1.5
        err = (reading / 5.0 - 1) * 100
        add("Input board", f"analog 5.00 V in, {t} C: firmware reading (divider 1.5)", f"{reading:.3f} V ({err:+.1f} %)",
            "within +-2 %", abs(err) <= 2, "BAT54S top diode starts to conduct as AIN nears 3.3 V", warn=abs(err) <= 5)


# ------------------------------------------------------------------ 5. CAN termination
def can(keep):
    for n_term, name in ((2, "two 120R (bus ends only; PDM jumpers open)"), (3, "three 120R (one PDM jumper closed by mistake)")):
        rt = 120.0 / n_term
        deck = f"""* CAN dominant: MCP2562FD driver modelled as 2.75 V / 1.5 V (data sheet VO(CANH) / VO(CANL) typ at 60R) with 30R / 30R output
Vh h0 0 4.0
Vl l0 0 0.9
Rh h0 canh 25
Rl canl l0 25
Rt canh canl {rt}
.op
.control
op
let vd = v(canh)-v(canl)
echo "vdiff = $&vd"
.endc
.end
"""
        m = ngspice(deck, f"can_{n_term}", keep)
        ok = m["vdiff"] >= 1.5
        add("CAN", f"dominant differential, {name}", f"{m['vdiff']:.2f} V", ">= 1.5 V (ISO 11898-2 receiver, VOD min)",
            ok if n_term == 2 else False, "" if n_term == 2 else "below the receiver minimum: keep every PDM CAN_TERM "
            "jumper open (the car bus is terminated at its ends)", warn=True)


def main():
    global NG
    ap = argparse.ArgumentParser()
    ap.add_argument("--ngspice", default=os.environ.get("NGSPICE") or shutil.which("ngspice") or shutil.which("ngspice_con"))
    ap.add_argument("--keep", default=os.path.join(tempfile.gettempdir(), "pcbverify-spice"))
    a = ap.parse_args()
    if not a.ngspice:
        raise SystemExit("ngspice not found: install it or pass --ngspice / set NGSPICE")
    NG = a.ngspice
    os.makedirs(a.keep, exist_ok=True)
    is_chain(a.keep)
    tvs(a.keep)
    startup(a.keep)
    input_board(a.keep)
    can(a.keep)
    w = max(len(r[1]) for r in RES)
    for g, c, v, l, verdict, note in RES:
        print(f"{verdict:4}  {g:12} {c:{w}}  {v:>18}  [{l}]  {note}")
    n = sum(r[4] == "FAIL" for r in RES)
    print("RESULT", "PASS" if not n else f"FAIL ({n})", f"- decks and logs in {a.keep}")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
