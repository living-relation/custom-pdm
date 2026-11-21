"""Circuit checks by SPICE (ngspice): current sense, input board, TVS surges, 3V3 start-up, CAN termination.

usage (repo root): python tools/verify_spice.py [--ngspice PATH] [--keep DIR]
    needs ngspice (Linux / WSL: `ngspice` on PATH; Windows: the ngspice console build, e.g.
    %LOCALAPPDATA%\\ngspice\\Spice64\\bin\\ngspice_con.exe, or set NGSPICE). Pure python otherwise.

Part values are the ones on the boards (netlists exported from hardware/*; checked against them in
docs/pcb-verification.md). Models are behavioural, built from data-sheet limits, so each result says which limit
it rests on:
  - Sense buffer: TLV9004 (fitted since ADR-2026-11-20-is-buffer; TI SBOS833R) rail-to-rail, or LM2902 (--opamp
    LM2902, the part before; TI SLOS066 6.8: input range to VCC-1.5 V at 25 C / VCC-2 V hot) -> clamp at that level.
  - IS clamp zener PDZ5.1B (fitted since 2026-11-20) or PDZ3.3B (--zener, before): two corners, see ZENER_PARTS; BAT54S (Nexperia): Schottky, IS 2e-7 A at 25 C
    doubling every 10 K.
  - TVS parts in TVS (bidirectional -> two diodes, dynamic resistance (VC - VBR) / IPP); --tvs picks the part(s).
  - Sense ratios kILIS from docs/parts-audit.md (Infineon tables) vs the firmware constants (port.h).
  - Surges: ISO 7637-2 (12 V, highest test levels: pulse 1 -150 V / 10 Ohm / 2 ms, 2a +112 V / 2 Ohm / 50 us,
    3a -220 V / 50 Ohm / 0.1 us, 3b +150 V / 50 Ohm / 0.1 us) and ISO 16750-2 load dump test B (suppressed,
    Us* 35 V, Ri 0.5 and 4 Ohm, td 400 ms). Limits: PROFET VBAT(LD) 35 V (suppressed load dump), VS max 28 V
    (BTS7008-2EPA P_4.1.0.1 / P_4.1.0.3).
Exit code 1 on any FAIL.
"""
import argparse
import math
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
DRIVERS = [  # name, rating A, kILIS datasheet (parts-audit), kILIS firmware (port_boards.py; ADR-2026-11-20-kilis, PR #112)
    ("BTS7008-2EPA (board A, 7.5 A)", 7.5, 5450, 5450),
    ("BTS7004-1EPP (board B OUT5-8, 15 A)", 15.0, 20000, 20000),
    ("BTS70012-1ESP (board B OUT1-4, 31 A)", 31.0, 33700, 33700),
]
# IS current limits, all three PROFET +2 12V data sheets: IIS(FAULT) 4.4 min / 5.5 typ / 10 max mA (BTS7008 P_9.6.0.x,
# BTS7004 / BTS70012 P_9.6.4.1); IIS(SAT) 4.4 min / 15 max mA (BTS7008 P_9.6.0.13).
IIS_FAULT_MIN, IIS_SAT_MIN, IIS_SAT_MAX = 4.4e-3, 4.4e-3, 15e-3
IIS_FAULT_MAX = 10e-3
FULL_SCALE = 3071          # firmware PROFET_IS_FULL_SCALE (counts of 4095 at VDDA = +3V3) = 2.475 V
                           # (ADR-2026-11-20-is-fullscale, PR #112; was 4054)
# Sense buffer (U7 / U12 on A, U7 / U22 on B), unity-gain follower on +3V3:
#   LM2902 (TI SLOS066, 6.8): input common-mode 0 .. VCC-1.5 V (25 C) / VCC-2 V (-40..125 C) -> output clamp there.
#   TLV9004 (TI SBOS833R, 7.5 / 7.1): rail-to-rail in ((V-)-0.1 .. (V+)+0.1 V) and out (swing from rail 20 mV max at
#   RL 10 k, VS 5.5 V; here the DC load is the 120R + ADC pin, so 20 mV is conservative); inputs diode-clamped to the
#   rails, 10 mA abs max; TA -40..125 C.
OPAMPS = {"LM2902": {"25": 1.5, "-40": 2.0, "125": 2.0}, "TLV9004": {"25": 0.02, "-40": 0.02, "125": 0.02}}
# IS-chain clamp zener (Nexperia PDZ-B series data sheet, Tables 1 / 2): VZ at 5 mA (min, max), rdif max at 5 mA and
# at the low test current, IR max at VR, temperature coefficient SZ (typ). PDZ3.3B = fitted until 2026-11-20,
# PDZ5.1B = fitted since (tools/sch_board_power.py). Two corners each:
#   sharp  = VZ max, a hard knee (the PR #109 model): the best case for the clamp level;
#   limit  = VZ min and the softest single-exponential knee all three data-sheet limits allow (rdif at 5 mA, rdif at
#            the low current, IR at VR): the worst case for leakage and for how high a fault can read.
ZENER_PARTS = {
    "PDZ3.3B": dict(vz=(3.32, 3.53), rdif=((5e-3, 95), (0.5e-3, 1000)), ir=(5e-6, 1.0), sz=-2.4e-3),
    "PDZ5.1B": dict(vz=(4.96, 5.20), rdif=((5e-3, 60), (0.5e-3, 250)), ir=(2e-6, 1.5), sz=0.3e-3),
}
ZENER = "PDZ5.1B"
ZENERS = ("sharp", "limit")


def zener_corner(corner):
    z = ZENER_PARTS[ZENER]
    if corner == "sharp":
        return z["vz"][1], 1.5 * 0.025865
    nvt = min([r * i for i, r in z["rdif"]] + [(z["vz"][0] - z["ir"][1]) / math.log(5e-3 / z["ir"][0])])
    return z["vz"][0], nvt


TEMPS = (-40, 25, 125)


def zener_model(corner, temp=25):
    """Reverse branch of the zener at node n1 as a behavioural current: 5 mA at VZ(T), exponential knee."""
    vz, nvt = zener_corner(corner)
    bv = vz + ZENER_PARTS[ZENER]["sz"] * (temp - 25)
    return f"Bz n1 0 I = 5m*exp(min((V(n1)-{bv:.4f})/{nvt:.4f}, 40)) - 5m*exp(-{bv:.4f}/{nvt:.4f})"


def opamp_line(opamp, temp):
    clip = OPAMPS[opamp]["25" if temp == 25 else str(temp) if str(temp) in OPAMPS[opamp] else "125"]
    if opamp == "TLV9004":     # rail-to-rail: follows its input to 20 mV from either rail
        return f"Bop opo 0 V = min(max(V(inp), 0.02), 3.3-{clip})", clip
    return f"Bop opo 0 V = min(V(inp), 3.3-{clip})", clip


def is_chain(keep, opamp):
    for name, rating, k_ds, k_fw in DRIVERS:
        short = name.split()[0]
        for zc in ZENERS:
            for temp in TEMPS:
                tag = re.sub(r"\W+", "_", f"{short}_{opamp}_{zc}_{temp}")
                op, clip = opamp_line(opamp, temp)
                imax = IIS_SAT_MIN * k_ds          # the PROFET IS output saturates here (IIS(SAT) min)
                deck = f"""* IS chain: IS -> 1.2k (1 %) -> 4.7k -> PDZ3.3B -> 4.7k / 220p -> {opamp} follower -> 120R -> ADC
.temp {temp}
Bis 0 is I = min(V(ld)/{k_ds}, {IIS_SAT_MIN})
Vload ld 0 0
Rs is 0 1.2k
R1 is n1 4.7k
R2 n1 inp 4.7k
C1 inp 0 220p
{op}
R3 opo adc 120
Cadc adc 0 10p
{zener_model(zc, temp)}
.control
dc Vload 0 {imax:.3f} {imax / 2000:.5f}
let ideal = v(ld)/{k_ds}*1200
let ratio = v(adc)/(ideal + 1e-6)
meas dc clip_a when ratio=0.95 fall=1
meas dc vadc_rated find v(adc) at={rating}
meas dc vadc_top max v(adc)
.endc
.end
"""
                m = ngspice(deck, "is_" + tag, keep)
                clip_a = m.get("clip_a", imax)
                ok = clip_a >= rating * 1.1
                err = (m["vadc_rated"] / (rating / k_ds * 1200) - 1) * 100
                vth = FULL_SCALE / 4095 * 3.3
                add("IS -> ADC", f"{short} {rating:g} A, {opamp}, {ZENER} {zc}, {temp} C: rated current below the "
                    f"fault threshold", f"{m['vadc_rated']:.3f} V", f"< {vth:.3f} V", m["vadc_rated"] < vth,
                    f"margin {vth - m['vadc_rated']:.3f} V; threshold = {vth / 1200 * k_ds:.1f} A typ "
                    f"({vth / 1200 * k_ds / rating:.2f} x rating)")
                add("IS -> ADC", f"{short} {rating:g} A, {opamp}, {ZENER} {zc}, {temp} C: reading 5 % low at",
                    f"{clip_a:.1f} A", f">= 1.1 x {rating:g} A", ok,
                    f"reading at rating {err:+.1f} % (ADC {m['vadc_rated']:.3f} V); top of range {m['vadc_top']:.3f} V "
                    f"= {m['vadc_top'] / 3.3 * 4095:.0f} counts; {opamp} limit VCC-{clip} V", warn=zc == "limit")
                if zc == "sharp" and temp == 25:
                    ifw = m["vadc_rated"] / 1200 * k_fw
                    e = (ifw / rating - 1) * 100
                    add("IS -> ADC", f"{short}: firmware reading at rating (kILIS fw {k_fw} vs typ {k_ds})",
                        f"{ifw:.2f} A ({e:+.1f} %)", "within +-10 %", abs(e) <= 10,
                        "data-sheet kILIS tolerance about +-4-5 % on top; 1 % sense resistor")
        # firmware fault rule: a latched fault drives IIS(FAULT) (4.4 mA min) -> must read >= PROFET_IS_FULL_SCALE
        for zc in ZENERS:
            for temp in TEMPS:
                op, clip = opamp_line(opamp, temp)
                deck = f"""* IS fault current (IIS(FAULT) min) into the chain
.temp {temp}
Iis 0 is {IIS_FAULT_MIN}
Rs is 0 1.2k
R1 is n1 4.7k
R2 n1 inp 4.7k
{op}
R3 opo adc 120
{zener_model(zc, temp)}
.op
.control
op
echo "vadc = $&v(adc)"
echo "vn1 = $&v(n1)"
.endc
.end
"""
                m = ngspice(deck, f"isf_{short}_{opamp}_{zc}_{temp}", keep)
                counts = m["vadc"] / 3.3 * 4095
                add("IS -> ADC", f"{short}, {opamp}, {ZENER} {zc}, {temp} C: fault (IIS(FAULT) 4.4 mA) reads",
                    f"{m['vadc']:.3f} V ({counts:.0f})", f">= {FULL_SCALE / 4095 * 3.3:.3f} V ({FULL_SCALE}, "
                    f"PROFET_IS_FULL_SCALE)", counts >= FULL_SCALE,
                    f"margin {m['vadc'] - FULL_SCALE / 4095 * 3.3:+.3f} V; zener node {m['vn1']:.2f} V")
    # IS saturation (15 mA, IIS(SAT) max) into the chain: ADC pin <= 3.6 V and op-amp input current <= 10 mA
    for temp in TEMPS:
        op, clip = opamp_line(opamp, temp)
        deck = f"""* IS saturation: 15 mA into the chain
.temp {temp}
Iis 0 is {IIS_SAT_MAX}
Rs is 0 1.2k
R1 is n1 4.7k
R2 n1 inp 4.7k
Dclamp inp vcc dclamp
Vcc vcc 0 3.3
{op}
R3 opo adc 120
{zener_model("sharp", temp)}
.model dclamp D(IS=1e-12)
.op
.control
op
let iin = (v(n1)-v(inp))/4.7k
echo "vn1 = $&v(n1)"
echo "vadc = $&v(adc)"
echo "iin = $&iin"
.endc
.end
"""
        m = ngspice(deck, f"is_sat_{opamp}_{temp}", keep)
        add("IS -> ADC", f"IS saturation 15 mA, {temp} C: ADC pin / op-amp input current",
            f"{m['vadc']:.2f} V / {m['iin'] * 1e3:.2f} mA", "ADC <= 3.6 V; input <= 10 mA (TLV9004 abs max)",
            m["vadc"] <= 3.6 and m["iin"] <= 10e-3, f"zener node {m['vn1']:.2f} V ({ZENER} VZ max corner)")
    tlv_input(keep)


def tlv_input(keep):
    """TLV9004 input pin vs its absolute maximum (TI SBOS833R 7.1, p. 14): signal input pins -10 .. +10 mA; common
    mode (V-)-0.5 .. (V+)+0.5 V, and note 2: 'Input pins are diode-clamped to the power-supply rails. Input signals
    that may swing more than 0.5 V beyond the supply rails must be current limited to 10 mA or less.' With PDZ5.1B
    the zener node sits above +3V3, so the pin is held by its upper clamp diode and the 4.7k (R2) is the limit.
    Worst case for the pin current: the highest PROFET IS current (IIS(FAULT) max 10 mA; IIS(SAT) max 15 mA), the
    highest zener voltage the data sheet allows (VZ max 5.20 V at 5 mA, rdif max 60 Ohm, SZ +0.3 mV/K: hard knee at
    VZ max + 60 Ohm in series), the lowest clamp-diode drop (Schottky-like IS 1e-8: 0.3 V at 0.3 mA; TI gives no
    curve) and the +3V3 rail at 3.3 V or not yet up (0 V: power-up, the TSR / LDO start-up of section 3)."""
    z = ZENER_PARTS[ZENER]
    for iis, iname in ((IIS_FAULT_MAX, "IIS(FAULT) max 10 mA"), (IIS_SAT_MAX, "IIS(SAT) max 15 mA")):
        for v3 in (3.3, 0.0):
            for temp in TEMPS:
                bv = z["vz"][1] + z["sz"] * (temp - 25)
                deck = f"""* TLV9004 input current: {iname}, +3V3 = {v3} V, {temp} C
.temp {temp}
Iis 0 is {iis}
Rs is 0 1.2k
R1 is n1 4.7k
Rz n1 nz {z['rdif'][0][1]}
Bz nz 0 I = 5m*exp(min((V(nz)-{bv:.4f})/0.002, 40))
R2 n1 inp 4.7k
C1 inp 0 220p
Dhi inp vcc desd
Dlo 0 inp desd
Vcc vcc 0 {v3}
Rrail vcc 0 1e6
.model desd D(IS=1e-8 N=1.0)
.op
.control
op
let iin = (v(n1)-v(inp))/4.7k
echo "vn1 = $&v(n1)"
echo "vinp = $&v(inp)"
echo "iin = $&iin"
.endc
.end
"""
                m = ngspice(deck, f"tlv_in_{int(iis * 1e3)}_{int(v3 * 10)}_{temp}", keep)
                add("TLV9004 in", f"{iname}, +3V3 {v3:g} V, {temp} C: input pin current", f"{m['iin'] * 1e3:.2f} mA",
                    "<= 10 mA (SBOS833R 7.1 note 2)", abs(m["iin"]) <= 10e-3,
                    f"zener node {m['vn1']:.2f} V, pin {m['vinp']:.2f} V ({m['vinp'] - v3:+.2f} V vs V+: allowed, "
                    f"current-limited by R2 4.7k); margin x{10e-3 / max(abs(m['iin']), 1e-9):.0f}")


# ------------------------------------------------------------------ 2. TVS vs surges
# TVS parts (bidirectional, so ISO pulse 1 / reverse battery see the same clamp): VBR min / max at IT, VC at IPP
# (10/1000 us), and the long-pulse rating used for the load dump:
#   5.0SMDJ24CA (Littelfuse 5.0SMDJ data sheet v.4, DO-214AB, fitted until 2026-11-20): 5 kW 10/1000 us only (about 7 J).
#   SM8S24CA (Vishay doc 98229 rev 23-Jan-2026, DO-218AC/AB, bidirectional; AEC-Q101 HM3; fitted as D2 since
#     2026-11-20, tools/d2_tvs.py): VBR 26.7 / 29.5 V, VC 38.9 V at IPPM 170 A (p. 2 table), 6.6 kW 10/1000 us, 5.2 kW 10/10000 us;
#     pulse-width derating for the same SM8S die / package (Vishay doc 98647 fig. 1): 6.6 kW 1 ms, 5.2 kW 10 ms,
#     1.9 kW 100 ms; beyond 100 ms extrapolated with the 10-100 ms slope (P ~ td^-0.44, the heat-diffusion law):
#     about 1.04 kW at 400 ms; initial-TJ derating linear to 0 at 175 C (doc 98229 fig. 3).
#   5.0SMDJ33CA (Littelfuse, DO-214AB; Infineon's application list asks for a 33 V TVS, DZ2): VBR 36.7 .. 40.6 V, VC
#     53.3 V at 93.8 A: it stays off in the 35 V suppressed load dump; fast pulses clamp above 35 V.
TVS = {
    "5.0SMDJ24CA": dict(vbr=(26.7, 29.5), vc=38.9, ipp=128.5, pkg="DO-214AB", ld=None, e1000=7.0),
    "SM8S24CA": dict(vbr=(26.7, 29.5), vc=38.9, ipp=170.0, pkg="DO-218AB", ld=[(1e-3, 6600), (10e-3, 5200),
                                                                              (100e-3, 1900)], e1000=9.2),
    "5.0SMDJ33CA": dict(vbr=(36.7, 40.6), vc=53.3, ipp=93.8, pkg="DO-214AB", ld=None, e1000=7.0),
}
# D2 sits away from the feed terminal J1 since ADR-2026-11-20-d2-move (tools/d2_tvs.py): board A 16 mm (bottom +12V
# pour over In1 GND), board B 66 mm (In2 + bottom +12V planes over In1 GND). Plane-pair inductance L = mu0 * h * len /
# width with h 1.07 mm (In1 - In2 / B.Cu core, JLCPCB 4-layer 1.6 mm), width >= 25 mm: A 0.9 nH, B 3.5 nH, plus 8+
# parallel 0.4 mm vias (about 0.1 nH): 4 nH covers both (the old spot hung on a 5 mm x 1.75 mm top track, about 4 nH).
LPATH = 4e-9
TJ_START = 85.0      # C, board / TVS temperature before the pulse (enclosure inside, docs/heat-analysis.md: sink 71-75 C
                     # fans on, board around the feed warmer): ASSUMED
RGND = 47.0          # Ohm, PROFET GND resistor fitted on every switch (R16 / R31 / ... ; Infineon Table 24 RGND)
VS_CLAMP_MIN = 33.0  # V, PROFET VS(CLAMP) min at -40 C (35 V at >= 25 C), P_8.6.0.6 / 7; IGND abs max 50 mA (P_4.1.0.9)


def tvs_rating_w(part, td):
    """Allowed rectangular-pulse power for td seconds at TJ_START (None: no long-pulse rating published)."""
    pts = TVS[part]["ld"]
    if not pts:
        return None
    (t1, p1), (t2, p2) = pts[-2], pts[-1]
    slope = math.log(p2 / p1) / math.log(t2 / t1)
    if td <= pts[-1][0]:
        for (ta, pa), (tb, pb) in zip(pts, pts[1:]):
            if ta <= td <= tb:
                slope = math.log(pb / pa) / math.log(tb / ta)
                return pa * (td / ta) ** slope * (175 - TJ_START) / 150
    return p2 * (td / t2) ** slope * (175 - TJ_START) / 150


def tvs(keep, part):
    d = TVS[part]
    pulses = [  # name, amplitude V, Ri, tr, td(width)
        ("ISO 7637-2 pulse 1 (-150 V, 10 Ohm, 2 ms)", -150, 10, 1e-6, 2e-3),
        ("ISO 7637-2 pulse 2a (+112 V, 2 Ohm, 50 us)", 112, 2, 1e-6, 50e-6),
        ("ISO 7637-2 pulse 3a (-220 V, 50 Ohm, 0.1 us)", -220, 50, 5e-9, 100e-9),
        ("ISO 7637-2 pulse 3b (+150 V, 50 Ohm, 0.1 us)", 150, 50, 5e-9, 100e-9),
        ("ISO 16750-2 load dump B (Us* 35 V, Ri 4 Ohm, 400 ms)", 35 - 13.5, 4, 5e-3, 400e-3),
        ("ISO 16750-2 load dump B (Us* 35 V, Ri 2 Ohm, 400 ms)", 35 - 13.5, 2, 5e-3, 400e-3),
        ("ISO 16750-2 load dump B (Us* 35 V, Ri 0.5 Ohm, 400 ms)", 35 - 13.5, 0.5, 5e-3, 400e-3),
    ]
    for vbr, corner in zip(d["vbr"], ("VBR min", "VBR max")):
        rd = (d["vc"] - vbr) / d["ipp"]
        for i, (name, amp, ri, tr, td) in enumerate(pulses):
            ld = "load dump" in name
            tstop = td * (1.6 if ld else 6)
            if ld:     # flat-topped (suppressed) pulse
                src = f"Vp p 0 PWL(0 0 {tr} {amp} {td} {amp} {td + tr} 0)"
            else:      # ISO 7637 pulses: fast rise, exponential decay to 10 % at td
                tau = td / 2.3
                src = f"Vp p 0 EXP(0 {amp} 0 {tr / 2.2} {tr} {tau})"
            deck = f"""* TVS {part} on +12V, {name}, {corner}
Vbat b 0 13.5
{src}
Rsrc s v12 {ri}
Esum s 0 POLY(2) b 0 p 0 0 1 1
* v12 = the feed terminal J1 and the switches' VS (C3 + the 47n / 100n at the switches); the board itself is the
* load (all outputs off: about 50 mA). D2 sits LPATH away on the +12V / GND planes (ADR-2026-11-20-d2-move).
Lp v12 t {LPATH}
Dt1 t m dtvs
Dt2 0 m dtvs
C3 v12 0 10u
Cx v12 0 0.4u
Rload v12 0 270
.model dtvs D(BV={vbr} IBV=1m IS=1e-12 N=1 RS={rd})
.tran {min(tstop / 4000, 2e-9 if td < 1e-6 else tstop)} {tstop}
.control
run
meas tran vmax max v(v12)
meas tran vmin min v(v12)
let itv = lp#branch
let iab = abs(itv)
let pt = abs(v(t)*itv)
meas tran ipk max iab
meas tran pmax max pt
meas tran etvs integ pt
.endc
.end
"""
            m = ngspice(deck, f"tvs_{part}_{i}_{int(vbr)}", keep)
            note = f"TVS peak {m['pmax']:.0f} W / {m['ipk']:.1f} A, energy {m['etvs']:.3g} J"
            grp = f"TVS {part}"
            if ld:
                pav = m["etvs"] / td
                rate = tvs_rating_w(part, td)
                if rate is None:
                    ok = m["etvs"] <= d["e1000"] * 0.05 or pav < 1.0
                    add(grp, f"{name}, {corner}: TVS energy", f"{m['etvs']:.1f} J",
                        f"<= ~{d['e1000']:.0f} J (10/1000 us rating only)", ok, note + f"; +12V peak {m['vmax']:.1f} V")
                else:
                    ok = pav <= rate
                    add(grp, f"{name}, {corner}: TVS power over {td * 1e3:.0f} ms", f"{pav:.0f} W ({m['etvs']:.0f} J)",
                        f"<= {rate:.0f} W (data-sheet derating, TJ start {TJ_START:.0f} C)", ok,
                        note + f"; +12V peak {m['vmax']:.1f} V; repeated each minute: {m['etvs'] / 60:.1f} W mean")
            elif amp > 0:
                ok = m["vmax"] <= 35.0
                ignd = max(0.0, (m["vmax"] - VS_CLAMP_MIN) / RGND)
                add(grp, f"{name}, {corner}: +12V", f"{m['vmax']:.1f} V", "<= 35 V (PROFET VBAT(LD))", ok,
                    note + (f"; above VS(CLAMP) min 33 V: GND current through RGND 47R up to {ignd * 1e3:.0f} mA "
                            f"(abs max 50 mA static)" if ignd else ""))
            else:
                ok = m["vmin"] >= -16.0
                ignd = max(0.0, (-m["vmin"] - 16.0) / RGND)
                add(grp, f"{name}, {corner}: +12V", f"{m['vmin']:.1f} V",
                    ">= -16 V (PROFET reverse battery, P_4.1.0.5, 2 min static)", ok,
                    note + ("" if ok else f"; GND-VS breakdown (-VS(REV) 16 V min) then drives up to {ignd * 1e3:.0f} mA "
                            "through RGND 47R (IGND abs max 50 mA static); no pulse rating in the data sheets"),
                    warn=amp < 0)


# ------------------------------------------------------------------ 3. 3V3 start-up
def startup(keep):
    deck = """* 12 V -> D19 -> LMZM23601V5 (5 V; enable 1.0 ms, fastest soft start 1.8 ms, SNVSAQ4C 6.5; hw5v) -> D18 PMEG2010 -> +5V (2 x 47u + 100n) -> TLV1117LV33 -> +3V3
Vbat b 0 PWL(0 0 1m 13.5)
Btsr p5 0 V = min(5, max(0, (time-1.0m)/1.8m*5))
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


# ------------------------------------------------------------------ 3b. 5 V module (hw5v): TI LMZM23601V5 in place of the TSR
# TI SNVSAQ4C (rev C, March 2023): VIN 4-36 V recommended, 40 V abs max (6.1 / 6.3); UVLO 3.5 V rising (6.5);
# turn-on delay 0.7 ms at 12 V, soft start 1.8 min / 3.5 typ ms (6.5); low-side (valley) current limit 1.0 min /
# 1.2 typ A, high-side 1.45 min A (6.5); max duty 93 % (fixed 5 V), HS RDS(on) 220 mOhm + inductor DCR 390 mOhm (6.5);
# MODE low = auto PFM with diode emulation (no negative inductor current, 7.3.7.2). The LMZM23600 (0.5 A, SNVSB53C)
# has a 0.5 A min valley limit. TI's own model is a PSpice transient model (encrypted): this is an AVERAGED
# current-mode model with an ASSUMED loop (proportional, 10 A/V, 2 us current lag); it checks the energy / current
# budget and the rails, not TI's real loop.
M5 = dict(ilim=1.0, ilim_0p5=0.5, ten=1.0e-3, tss=(1.8e-3, 3.5e-3), dmax=0.93, rdrop=0.61, kp=10.0, tau=2e-6, eff=0.85,
          vin_rec=36.0, vin_abs=40.0)
# 2 x 4.7 uF 50 V X7R 0805 at 13.5-34 V: ~3 uF each left (DC bias, ASSUMED); output 22 uF 10 V X7R x 2 (new C_out + C4):
# ~12 uF each at 5 V (ASSUMED, stability case) or 22 uF each (nominal, inrush case); +5V 2 x 47 uF + 100 nF nominal.
M5_DECK = """* hw5v: 12 V -> D3 / D19 -> +12P (2 x 4.7u) -> LMZM23601V5 (averaged) -> +5VP (C_out + C4) -> D4 / D18 -> +5V
Vbat b 0 {vbat}
D3 b p12 dsch
Cin p12 0 6u
Brefe refe 0 V = min(5*min(1, max(0, (time-{ten})/{tss})), {dmax}*V(p12) - {rdrop}*V(il))
Bcmd c 0 V = max(0, min({ilim}, {kp}*(V(refe)-V(p5))))
Rl c il 1
Cl il 0 {tau}
Bout 0 p5 I = V(il)
Bin p12 0 I = V(p5)*V(il)/({eff}*max(V(p12), 1))
Cout p5 0 {cout}
D4 p5 v5 dsch
C41 v5 0 47u
C42 v5 0 47u
C5 v5 0 100n
{load}
.model dsch D(IS=5e-6 N=1.05 RS=0.05)
.tran 1u {tstop}
.control
run
{meas}
.endc
.end
"""


def module5v(keep):
    grp = "5V module"
    ldo = """Bldo l3 0 V = min(3.3, max(0, V(v5) - 0.45))
Rldo l3 v3 0.05
C6 v3 0 10u
C14 v3 0 4.7u
Cdec v3 0 4u
Rmcu v3 0 22
Rcan v5 0 66"""
    # (a) start-up, nominal caps (most charge), fastest soft start (most current): the current the loop asks for
    for tss in M5["tss"]:
        deck = M5_DECK.format(vbat="PWL(0 0 1m 13.5)", ten=M5["ten"], tss=tss, dmax=M5["dmax"], rdrop=M5["rdrop"],
                              ilim=10.0, kp=M5["kp"], tau=M5["tau"], eff=M5["eff"], cout="44u", load=ldo, tstop="12m",
                              meas="meas tran ilpk max v(il)\nmeas tran t3v0 when v(v3)=3.0 rise=1\n"
                                   "meas tran v5max max v(v5)\nmeas tran v3max max v(v3)")
        m = ngspice(deck, f"m5_start_{int(tss * 1e4)}", keep)
        add(grp, f"start-up, soft start {tss * 1e3:.1f} ms: inductor current asked for", f"{m['ilpk']:.2f} A",
            f"<= {M5['ilim']:.1f} A (LMZM23601 valley limit min)", m["ilpk"] <= M5["ilim"],
            f"nominal 157 uF on +5VP / +5V / +3V3 + CAN 70 mA + 3V3 150 mA; the 0.5 A LMZM23600 would "
            f"{'also fit' if m['ilpk'] <= M5['ilim_0p5'] else 'hit its 0.5 A limit'}; +3V3 at 3.0 V after "
            f"{m['t3v0'] * 1e3:.2f} ms")
        add(grp, f"start-up, soft start {tss * 1e3:.1f} ms: overshoot", f"+5V {m['v5max']:.2f} / +3V3 {m['v3max']:.2f} V",
            "+5V <= 5.5 V (MCP2562FD VDD max), +3V3 <= 3.6 V", m["v5max"] <= 5.5 and m["v3max"] <= 3.6)
    # (b) load step on +5V 0.02 -> 0.22 A -> 0.02 A (1 us edges), DC-bias output caps (least capacitance)
    step = "Iload v5 0 PWL(0 0 4m 0 4.01m 0.02 6m 0.02 6.001m 0.22 8m 0.22 8.001m 0.02)"   # load after start-up
    deck = M5_DECK.format(vbat="PWL(0 0 1m 13.5)", ten=M5["ten"], tss=M5["tss"][1], dmax=M5["dmax"], rdrop=M5["rdrop"],
                          ilim=M5["ilim"], kp=M5["kp"], tau=M5["tau"], eff=M5["eff"], cout="24u", load=step, tstop="10m",
                          meas="meas tran v5pre find v(v5) at=5.9m\nmeas tran v5min min v(v5) from=6m to=7.9m\n"
                               "meas tran v5max max v(v5) from=8m to=9.9m\nmeas tran v5pmin min v(p5) from=6m to=7.9m")
    m = ngspice(deck, "m5_step", keep)
    add(grp, "load step +5V 0.02 -> 0.22 -> 0.02 A (1 us)", f"+5V {m['v5min']:.3f} .. {m['v5max']:.3f} V",
        ">= 4.5 V (MCP2562FD VDD min), <= 5.5 V", m["v5min"] >= 4.5 and m["v5max"] <= 5.5,
        f"before {m['v5pre']:.3f} V; +5VP min {m['v5pmin']:.3f} V; loop ASSUMED (averaged model)")
    # (c) input transients at the clamp levels of verify_spice section 2 (SM8S24CA, VBR max corner): ISO 7637-2
    # pulse 2a peak 34.0 V on +12V (50 us) and the ISO 16750-2 suppressed load dump 31.3 V (held 20 ms here, 400 ms real)
    for name, pwl in (("pulse 2a clamp, 34.0 V for 50 us", "PWL(0 0 1m 13.5 6m 13.5 6.001m 34 6.05m 34 6.06m 13.5)"),
                      ("load dump clamp, 31.3 V (5 ms rise)", "PWL(0 0 1m 13.5 6m 13.5 11m 31.3 31m 31.3 36m 13.5)")):
        deck = M5_DECK.format(vbat=pwl, ten=M5["ten"], tss=M5["tss"][1], dmax=M5["dmax"], rdrop=M5["rdrop"],
                              ilim=M5["ilim"], kp=M5["kp"], tau=M5["tau"], eff=M5["eff"], cout="24u",
                              load="Iload v5 0 PWL(0 0 4m 0 4.01m 0.22)", tstop="40m",
                              meas="meas tran p12max max v(p12)\nmeas tran v5pmax max v(p5) from=5m to=40m\n"
                                   "meas tran v5pmin min v(p5) from=5m to=40m")
        m = ngspice(deck, f"m5_line_{name.split()[0]}", keep)
        add(grp, f"input {name}: module VIN", f"{m['p12max']:.1f} V",
            f"<= {M5['vin_rec']:.0f} V recommended, {M5['vin_abs']:.0f} V abs max (SNVSAQ4C 6.1 / 6.3)",
            m["p12max"] <= M5["vin_rec"], f"+5VP {m['v5pmin']:.3f} .. {m['v5pmax']:.3f} V at 0.22 A")


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
    ap.add_argument("--opamp", default="TLV9004", choices=sorted(OPAMPS), help="IS buffer (LM2902 = before 2026-11-20)")
    ap.add_argument("--zener", default="PDZ5.1B", choices=sorted(ZENER_PARTS), help="IS-chain zener (PDZ3.3B = before)")
    ap.add_argument("--tvs", nargs="+", default=["SM8S24CA"], choices=sorted(TVS),
                    help="input TVS part(s) to check (first = fitted)")
    ap.add_argument("--only", nargs="*", help="groups to run: is tvs startup module5v input can")
    a = ap.parse_args()
    if not a.ngspice:
        raise SystemExit("ngspice not found: install it or pass --ngspice / set NGSPICE")
    NG = a.ngspice
    global ZENER
    ZENER = a.zener
    os.makedirs(a.keep, exist_ok=True)
    run = set(a.only or ["is", "tvs", "startup", "module5v", "input", "can"])
    if "is" in run:
        is_chain(a.keep, a.opamp)
    if "tvs" in run:
        for part in a.tvs:
            tvs(a.keep, part)
    if "startup" in run:
        startup(a.keep)
    if "module5v" in run:
        module5v(a.keep)
    if "input" in run:
        input_board(a.keep)
    if "can" in run:
        can(a.keep)
    w = max(len(r[1]) for r in RES)
    for g, c, v, l, verdict, note in RES:
        print(f"{verdict:4}  {g:12} {c:{w}}  {v:>18}  [{l}]  {note}")
    n = sum(r[4] == "FAIL" for r in RES)
    print("RESULT", "PASS" if not n else f"FAIL ({n})", f"- decks and logs in {a.keep}")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
