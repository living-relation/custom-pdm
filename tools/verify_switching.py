"""Presim item 3: output switching - PWM loss in the PROFETs at 16-400 Hz, PWM into motor loads (board B freewheel
diodes), minimum on-time, lamp inrush vs the presets and the PROFET overload limit, short circuit, parallel pairs.

usage (repo root): python tools/verify_switching.py [--json out.json]     (pure python + numpy; exit 1 on any FAIL)

Values: tools/presim_parts.py (PROFET data sheets: slew rates, EON / EOFF, RDS(ON), IL(OVL0), retry counters; car
loads from docs/car-loads.dummy.md, a DUMMY TEST COPY; load inductances ASSUMED, bench tests). Presets: the ui
PdmPresets.cs table (read here). Firmware: PWM 16-1000 Hz (functions/pwm.cpp), PWM_READ_DELAY (functions/profet.h).
"""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import presim_parts as P  # noqa: E402

RES = []
FREQS = (16, 50, 100, 200, 400)
VBAT = 14.4


def add(group, check, value, limit, verdict, note=""):
    RES.append(dict(group=group, check=check, value=value, limit=limit, verdict=verdict, note=note))


def edge_energy(model, i, v=VBAT, inductive=False):
    """Energy of one switching edge at the slowest data-sheet slew rate: resistive load V I t / 6 (t = V / (dV/dt)),
    which gives the data-sheet EON / EOFF (BTS70012 1.71 mJ vs 1.65 mJ typ at 18 V / 2.1 Ohm, 0.27 V/us); a motor
    with a freewheel diode switches hard (current flat while the voltage swings): V I t / 2."""
    d = P.PROFET[model]
    t = v / d["dvdt"][0]
    return v * i * t / (2 if inductive else 6)


def pwm_loss():
    for model in P.PROFET:
        d = P.PROFET[model]
        inom = d["inom"]
        p_dc = inom * inom * d["rds150"]
        for inductive in (False, True):
            rows = []
            for f in FREQS:
                # largest current whose conduction + switching loss stays within the DC loss at rating (100 % duty)
                lo, hi = 0.0, inom
                for _ in range(40):
                    mid = (lo + hi) / 2
                    p = mid * mid * d["rds150"] + 2 * edge_energy(model, mid, inductive=inductive) * f
                    lo, hi = (mid, hi) if p <= p_dc else (lo, mid)
                rows.append((f, lo))
            i100 = dict(rows)[100] / inom
            i400 = dict(rows)[400] / inom
            verdict = "PASS" if i400 >= 0.9 else ("WARN" if i100 >= 0.7 else "FAIL")
            add("PWM loss", f"{model}, {'motor + freewheel (hard switching)' if inductive else 'resistive / lamp'} load: "
                f"current that keeps PWM heat <= the DC heat at {inom} A", ", ".join(f"{f} Hz {a:.1f} A" for f, a in rows),
                ">= 90 % of the rating at 400 Hz (PASS); >= 70 % at 100 Hz (WARN)", verdict,
                f"slowest slew {d['dvdt'][0] / 1e6:.2f} V/us at {VBAT} V, RDS(ON) 150 C {d['rds150'] * 1e3:.2f} mOhm; "
                "above these currents a PWM'd output runs hotter than the heat model's DC case " + d["src"])


def pwm_motor_clamp():
    """PWM of an inductive load with no freewheel diode (board A, and board B since hwprotect): every PWM period ends
    in a turn-off whose L energy goes into the switch's clamp, E = L Vcl / R (I0 - Vz / R ln(1 + I0 R / Vz)) (data
    sheet eq. 7.1). Repetitive clamping: E <= EAR (1M cycles, TJ0 85 C) and E x f within a 1 W extra-heat budget per
    switch (heat model margin; the clamp power is not in the DC heat model). Gives the highest PWM frequency per load."""
    budget = 1.0
    for name, board, out, drv, i, (l_lo, l_hi), *_, kind in P.CAR_LOADS:
        if kind != "motor" or P.FREEWHEEL[board]:      # coils (horn, clutch, solenoid) are switched, not PWM'd
            continue
        d = P.PROFET[drv]
        vcl, vbat = d["clamp"][0], 16.0
        r = 13.5 / i
        vz = vcl - vbat
        i0 = vbat / r
        e = l_hi * vcl / r * (i0 - vz / r * math.log(1 + i0 * r / vz))
        ear = d["ear"][0]
        fmax = budget / e if e > 0 else float("inf")
        ok = e <= ear and fmax >= 100
        add("PWM into an inductive load (no freewheel diode)", f"{name} ({board} OUT{out}, {drv}, {i} A, L {l_hi * 1e3:g} mH "
            "ASSUMED): clamp energy per PWM period", f"{e * 1e3:.1f} mJ; {budget:.0f} W extra heat at {fmax:.1f} Hz",
            f"EAR {ear * 1e3:.0f} mJ (1M cycles); >= 100 Hz within {budget:.0f} W", "PASS" if ok else ("WARN" if e <= ear else "FAIL"),
            ("PWM fine" if ok else f"PWM (soft start, fan curve) only up to {fmax:.1f} Hz with this L, or on / off only; "
             "a PWM'd motor on this output needs its own freewheel path (a diode at the load, or a reverse-protected "
             "freewheel on the board: design choice). Firmware presets: BACKLOG (fwsafety)"))


def pwm_motor_diode():
    """PWM of a motor on board B: in the off time the load current freewheels in the BYG23M (I e^-t/tau, tau = L/R,
    back-EMF ignored = more diode current, conservative). Average diode current at the worst duty."""
    pwm_motor_clamp()                                    # every board without a freewheel diode (A; B in the what-if)
    if not P.FREEWHEEL["B"]:
        return
    lim = P.BYG23M["if_av"]
    for name, board, out, drv, i, (l_lo, l_hi), *_, kind in P.CAR_LOADS:
        if board != "B" or kind != "motor":
            continue
        r = 13.5 / i
        tau = l_hi / r
        rows, fmax = [], None
        for f in FREQS:
            worst = 0
            for duty in [x / 20 for x in range(1, 20)]:
                toff = (1 - duty) / f
                worst = max(worst, i * tau * (1 - math.exp(-toff / tau)) * f)
            rows.append((f, worst))
        for f in range(1, 1001):
            if max(i * tau * (1 - math.exp(-((1 - dd / 20) / f) / tau)) * f for dd in range(1, 20)) > lim:
                fmax = f - 1
                break
        add("PWM into a motor (board B)", f"{name} ({board} OUT{out}, {i} A, L {l_hi * 1e3:g} mH ASSUMED): BYG23M "
            "average current", ", ".join(f"{f} Hz {a:.1f} A" for f, a in rows), f"IF(AV) {lim} A (TA 65 C)",
            "FAIL" if rows[2][1] > lim else "PASS",
            f"continuous PWM is only safe up to about {fmax} Hz with this L; a fan curve at 100-400 Hz overloads D13 .. D28 "
            "(SMA, RthJA 125 K/W); the /pdm presets hold board B motor PWM and the fan soft start at PdmPresets.MaxPwmHz "
            "(same model, preset current limit: fans 22 Hz; job fwsafety) until the diodes change. A design choice: a larger "
            "freewheel diode (e.g. a 10-15 A Schottky, footprint change) on the PWM'd board B outputs, or PWM only below "
            "that frequency (bench: measure the fan's L and current decay)")


def min_on_time():
    src = open(os.path.join(P.ROOT, "firmware", "functions", "profet.h"), encoding="utf-8").read()
    rd = int(re.search(r"#define PWM_READ_DELAY_SINGLE_CH (\d+)", src).group(1))
    for model in P.PROFET:
        d = P.PROFET[model]
        t_on = d["ton"][2]
        rows = ", ".join(f"{f} Hz {t_on * f * 100:.1f} %" for f in FREQS)
        add("PWM minimum duty", f"{model}: duty below which the output never fully turns on (tON max {t_on * 1e6:.0f} us)",
            rows, "duty steps used (fan curve 20-80 %, tach 50 %) above it", "PASS" if t_on * 400 < 0.2 else "WARN",
            f"current reading needs {rd} us of on-time (PWM_READ_DELAY_SINGLE_CH): at 400 Hz below "
            f"{rd * 1e-6 * 400 * 100:.0f} % duty the IS reading holds its last value")


def presets():
    cs = open(os.path.join(P.ROOT, "ui", "dingoConfig", "domain", "CustomPdm", "PdmPresets.cs"), encoding="utf-8").read()
    rows = re.findall(r'new\(PdmDeviceKind\.(\w+), "([^"]+)", ([\d.]+|double\.MaxValue), ([\d.]+), (\d+), (\d+),', cs)
    pre = {k: (n, float(m) if m[0].isdigit() else 1e9, float(fx), int(ms), int(tr)) for k, n, m, fx, ms, tr in rows}
    # halogen lamp on board A: cold filament 13-15 x (preset note); IS full scale on A about 10.5 A (verify_tolerance)
    d = P.PROFET["BTS7008-2EPA"]
    for watts in (21, 55, 65):
        i_hot = watts / 13.2
        peak = i_hot * 14.0
        verdict = "PASS" if peak < d["ovl0_150"][0] else ("WARN" if peak < d["ovl0_25"][0] else "FAIL")
        add("Lamp inrush", f"{watts} W halogen on a board A output (cold filament 14 x {i_hot:.1f} A)",
            f"peak {peak:.0f} A", f"BTS7008 IL(OVL0) min {d['ovl0_150'][0]} A (TJ 150 C) / {d['ovl0_25'][0]} A (25 C)",
            verdict, "above IL(OVL0) the PROFET switches off and retries itself (5 restarts, then 2 retry cycles, "
            "P_8.6.1.x); each try warms the filament. The lamp preset's inrush limit "
            f"({min(100, 7.5 * pre['Lamp'][2]):.0f} A) is above what board A can read (full scale about 10.5 A): "
            "inside the inrush window only the PROFET limits the current (by design, ADR-2026-11-20-is-fullscale)")
    for kind in ("RadiatorFan", "FuelPump", "Motor"):
        name, steady, fx, ms, tr = pre[kind]
        for board_drv, rating in (("BTS70012-1ESP", 31.0), ("BTS7004-1EPP", 15.0)):
            d = P.PROFET[board_drv]
            lim = min(rating, steady)
            peak = lim * 5
            add("Motor inrush", f"{name} preset on a {board_drv} ({rating} A): 5 x {lim:.0f} A start",
                f"{peak:.0f} A for up to {ms} ms", f"IL(OVL0) min {d['ovl0_150'][0]} A (TJ 150 C)",
                "PASS" if peak < d["ovl0_150"][0] else "WARN", f"preset inrush limit {min(100, lim * fx):.0f} A for {ms} ms")


def short_circuit():
    for model in P.PROFET:
        d = P.PROFET[model]
        rt = d["retry"]
        tries = 1 + rt["n_cr"] + rt["n_cyc"] * rt["n_nt"]
        add("Short circuit", f"{model}: hard short while the output is on",
            f"PROFET trips at IL(OVL0) {d['ovl0_150'][0]}-{d['ovl0_25'][2]} A, restarts itself up to {tries - 1} times "
            f"({rt['t_retry'][1] * 1e3:.0f} ms apart), then latches until IN is low > tDELAY(CR)",
            "self-protected (AEC-Q100-012 short-circuit setup, VBAT(SC) <= 24 V)", "PASS",
            "the firmware sees IIS(FAULT) as full scale and switches IN off on the next 2 ms pass after the inrush "
            "window; its own retries (reset limit) come 1 s apart, past tDELAY(CR) 100 ms max, so each firmware retry "
            "starts a fresh PROFET counter: worst case per firmware try = the PROFET's own restarts inside the window")


def pairing():
    d = P.PROFET["BTS70012-1ESP"]
    spread = 0.20     # ASSUMED unit-to-unit RDS(ON) spread at equal TJ (data sheet gives typ and max only)
    r_cu = 2.1e-3 / 31.0      # copper path per output, verify_copper.py B (2.1 mV at 31 A)
    r1 = d["rds25"] * (1 - spread) + r_cu
    r2 = d["rds25"] * (1 + spread) + r_cu
    share = r2 / (r1 + r2)
    imax = 31.0 / share
    add("Parallel pair", "B OUT3 + OUT4 (row 34, fuel pump option): current split with RDS(ON) +-20 % (ASSUMED)",
        f"the lower-RDS output carries {share * 100:.0f} %: the pair trips at {imax:.0f} A total, not 62 A",
        "pair rating used for a load <= 2 x 31 x min share", "WARN",
        f"plan a paired load at <= {imax * 0.9:.0f} A steady; switch-on skew (tON {d['ton'][0] * 1e6:.0f}-"
        f"{d['ton'][2] * 1e6:.0f} us) puts the full load on one switch for <= 160 us, far under IL(OVL0); "
        "the hotter switch takes less (RDS rises with TJ), which helps")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--no-freewheel-b", action="store_true", help="board B without its BYG23M freewheel diodes (what-if)")
    a = ap.parse_args()
    if a.no_freewheel_b:
        P.FREEWHEEL["B"] = None
    pwm_loss()
    pwm_motor_diode()
    min_on_time()
    presets()
    short_circuit()
    pairing()
    for r in RES:
        print(f"{r['verdict']:<5} [{r['group']}] {r['check']}: {r['value']} (limit {r['limit']})" + (f" - {r['note']}" if r['note'] else ""))
    cnt = {v: sum(r["verdict"] == v for r in RES) for v in ("PASS", "WARN", "FAIL", "INFO")}
    print("TOTAL", cnt)
    if a.json:
        json.dump(RES, open(a.json, "w"), indent=1)
    return 1 if cnt["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
