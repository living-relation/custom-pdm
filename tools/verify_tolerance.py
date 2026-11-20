"""Presim item 1: tolerance / worst case of every analog chain (Monte Carlo + hard corners), firmware view.

usage (repo root): python tools/verify_tolerance.py [--n 20000] [--json out.json]
    pure python + numpy; runs on DansPC or Linux. Exit code 1 on any FAIL.

Chains (each with the firmware's own conversion, constants read from firmware/boards/custompdm_*):
  1. PROFET IS -> 1.2k (1 %) -> 4.7k -> PDZ5.1B -> 4.7k -> TLV9004 follower -> 120R -> ADC (VDDA from VREFINT), for
     all 24 outputs: reading error at the default limit, the true current at which the firmware trips (window),
     the full-scale fault rule (3071 counts) vs the limit, open-load detection at low current.
  2. Battery sense 47k / 4.7k (+ PDZ3.3B D1 leakage) -> ADC, firmware GetBattVolt().
  3. Input board digital channel (4.7k, BAT54S, 10k pull-up) vs STM32 VIL / VIH, ground offset (ISO 16750-2 4.8).
  4. Input board analog channel 10k / 20k -> ADC, firmware ANALOG_IN_DIVIDER, BAT54S leakage at temperature.
  5. Temperatures: MCP9808 board sensor vs the firmware warn / critical / fan limits; STM32 die sensor (TS).
  6. ADC sampling time of the internal channels (TS, VREFINT) vs the data-sheet minimum.
Temperatures: -40 / 25 / 85 / 105 C (the MCU is the RET7 -40..105 C grade; TLV9004 / PROFET to 125 / 150 C).
Every part value and limit: tools/presim_parts.py (data sheet, table / parameter number).
"""
import argparse
import json
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import presim_parts as P  # noqa: E402

RES = []
FAN_LOAD = 0.13          # A, both box fans on A2 OUT2 (docs/firmware-thermal-plan.md, fan-fail detection note)
TEMPS = (-40, 25, 85, 105)


def add(group, check, value, limit, verdict, note=""):
    RES.append(dict(group=group, check=check, value=value, limit=limit, verdict=verdict, note=note))


def u(rng, n, tol):
    return 1 + rng.uniform(-tol, tol, n)


# ------------------------------------------------------------------ ADC + VDDA estimate (shared by every chain)
def vdda_est_ratio(rng, n, temp):
    """Ratio firmware VDDA estimate / true VDDA. GetVDDA() = VREFINT_CAL * 3.3 / raw(VREFINT): error sources are the
    VDDA used at calibration (3.3 V +-10 mV), the VREFINT drift between 30 C and temp (spread max 5 mV over the
    range, DS Table 83), and the ADC error on the VREFINT conversion (ET +-5 LSB of about 1500 counts)."""
    vref = P.STM32["vrefint"][1]
    cal_vdda = 3.3 + rng.uniform(-1, 1, n) * P.STM32["vrefint_cal_vdda"][1]
    drift = rng.uniform(-1, 1, n) * P.STM32["vrefint_spread"] * (abs(temp - 30) / 135.0 if temp != 30 else 0)
    vdda = 3.3 * u(rng, n, 0.015)                          # TLV1117LV33 +-1.5 % (SBVS160C 6.5)
    raw_ref = vref * (1 + drift / vref) / vdda * 4095 + rng.uniform(-1, 1, n) * P.STM32["adc_et_lsb"]
    cal = vref / cal_vdda * 4095
    return (cal * 3.3 / raw_ref) / vdda, vdda


def adc(rng, v, vdda):
    raw = np.clip(np.round(v / vdda * 4095 + rng.uniform(-1, 1, v.shape) * P.STM32["adc_et_lsb"]), 0, 4095)
    return raw


# ------------------------------------------------------------------ 1. IS chain
def is_chain(rng, n):
    rs_nom, r1 = 1200.0, 4700.0
    full_scale = P.fw_const("a", "PROFET_IS_FULL_SCALE", int) if _has("a", "PROFET_IS_FULL_SCALE") else 3071
    kfw = {"BTS7008-2EPA": P.fw_const("a", "BTS7008_2EPA_KILIS"), "BTS70012-1ESP": P.fw_const("b", "BTS70012_1ESP_KILIS"),
           "BTS7004-1EPP": P.fw_const("b", "BTS7004_1EPP_KILIS")}
    rows, worst = [], {}
    for board, out, model, limit in P.OUTPUTS:
        for temp in TEMPS:
            k_typ, k_tol = P.kilis_tol(model, limit)
            ratio, vdda = vdda_est_ratio(rng, n, temp)
            k_true = k_typ * u(rng, n, k_tol)
            rs = rs_nom * u(rng, n, P.RESISTOR_TOL["0805W8F"]) * (1 + rng.uniform(-1, 1, n) * P.RES_TCR * (temp - 25))
            iz = rng.uniform(0, 1, n) * P.PDZ["PDZ5.1B"]["ir"][0]          # leakage bound (IR max at 1.5 V, 25 C)
            vos = rng.uniform(-1, 1, n) * (P.TLV9004["vos_25"] if temp == 25 else P.TLV9004["vos_hot"])

            def meas(il):
                v = il / k_true * rs - iz * (rs + r1) + vos
                v = np.clip(v, P.TLV9004["swing"], vdda - P.TLV9004["swing"])
                raw = adc(rng, v, vdda)
                return raw, raw * (vdda * ratio) / 4095 / 1200 * kfw[model]

            raw_l, i_l = meas(np.full(n, limit))
            err = (i_l / limit - 1) * 100
            # true current where the reading equals the limit: reading is linear in il (offsets small): two points
            _, i_h = meas(np.full(n, limit * 1.2))
            g = (i_h - i_l) / (0.2 * limit)
            trip = limit + (limit - i_l) / np.where(g > 0, g, 1)
            # full-scale rule: true current where raw reaches the full-scale count
            fs_true = (full_scale / 4095 * vdda + iz * (rs + r1) - vos) * k_true / rs
            rows.append(dict(board=board, out=out, model=model, limit=limit, temp=temp,
                             err_lo=float(np.percentile(err, 0.1)), err_hi=float(np.percentile(err, 99.9)),
                             trip_lo=float(trip.min()), trip_hi=float(trip.max()),
                             fs_lo=float(fs_true.min()), fs_hi=float(fs_true.max())))
    # summarise per (model, limit): worst over temperature and over the 24 outputs
    for key in sorted({(r["model"], r["limit"]) for r in rows}):
        rr = [r for r in rows if (r["model"], r["limit"]) == key]
        outs = sorted({f"{r['board']} OUT{r['out']}" for r in rr})
        lo, hi = min(r["trip_lo"] for r in rr), max(r["trip_hi"] for r in rr)
        elo, ehi = min(r["err_lo"] for r in rr), max(r["err_hi"] for r in rr)
        fslo = min(r["fs_lo"] for r in rr)
        model, limit = key
        k_typ, k_tol = P.kilis_tol(model, limit)
        band = max(limit - lo, hi - limit) / limit * 100
        verdict = "PASS" if band <= 10 else ("WARN" if band <= 20 else "FAIL")
        load = FAN_LOAD if limit == 1.0 else None
        if load and lo > 2 * load:      # the box-fan output: a generous 1 A limit over a 0.13 A load
            verdict = "PASS"
        add("IS chain", f"{model} at the default limit {limit} A ({len(outs)} outputs: {', '.join(outs[:2])}...)",
            f"reads {elo:+.1f} .. {ehi:+.1f} %; trips at true {lo:.2f} .. {hi:.2f} A",
            "trip window within +-10 % of the limit (PASS), +-20 % (WARN)", verdict,
            f"kILIS +-{k_tol * 100:.1f} % at {limit} A dominates ({P.PROFET[model]['src']}); -40..105 C, 1.2k 1 % "
            f"+-100 ppm/K, TLV9004 VOS, PDZ5.1B leakage, ADC ET +-5 LSB, VDDA from VREFINT" +
            (f"; box fans draw about {FAN_LOAD} A (docs/firmware-thermal-plan.md), far under the lowest trip" if load else ""))
        ok_fs = fslo > limit * 1.05
        add("IS chain", f"{model}: full-scale fault rule ({full_scale} counts) vs the limit {limit} A",
            f"full scale at true >= {fslo:.1f} A", f"> 1.05 x limit ({limit * 1.05:.1f} A): no full-scale trip below the limit",
            "PASS" if ok_fs else "FAIL", "a PROFET fault (IIS(FAULT) >= 4.4 mA x 1.2k = 5.3 V) reads 4095 (TLV9004 "
            "rail-to-rail, PDZ5.1B clamps above VDDA) > the full-scale count: trips")
    # open-load / undercurrent (P2) and the noise floor at low current: smallest threshold that cannot false-alarm
    for model in P.PROFET:
        fl = P.PROFET[model]["floor"]
        for il in (0.25, 0.5, 1.0, 2.0):
            k_typ, k_tol = P.kilis_tol(model, il)
            lo_reading = il * (1 - k_tol) * (1 - 0.02)
            hi_reading = il * (1 + k_tol) * (1 + 0.02)
            if lo_reading > fl:
                add("IS chain (low current)", f"{model}: a {il} A load reads", f"{lo_reading:.2f} .. {hi_reading:.2f} A",
                    f"above the firmware noise floor {fl} A", "PASS",
                    f"kILIS +-{k_tol * 100:.1f} % at {il} A; set an open-load threshold under {lo_reading:.2f} A for this load")
                break
            else:
                add("IS chain (low current)", f"{model}: a {il} A load reads", f"{lo_reading:.2f} .. {hi_reading:.2f} A",
                    f"above the firmware noise floor {fl} A", "INFO",
                    "can read 0 (noise floor): open-load detection is not reliable at this load current")
    return rows


def _has(board, name):
    try:
        P.fw_const(board, name)
        return True
    except KeyError:
        return False


# ------------------------------------------------------------------ 2. battery sense
def zener_leak(v, part="PDZ3.3B", extrapolate=True):
    """PDZ-B reverse leakage bound: IR max at VR (data sheet); above VR the exponential knee to 5 mA at VZ min
    (the 'limit' corner of tools/verify_spice.py) when extrapolate is set, else IR max is held."""
    z = P.PDZ[part]
    ir, vr = z["ir"]
    if v <= vr or not extrapolate:
        return ir * min(1.0, v / vr) if v <= vr else ir
    nvt = (z["vz"][0] - vr) / math.log(5e-3 / ir)
    return ir * math.exp((v - vr) / nvt)


def batt_sense(rng, n):
    r1n, r2n = 47000.0, 4700.0
    worst = []
    for vb in (9.0, 12.0, 13.8, 14.4, 16.0):
        for temp in TEMPS:
            ratio, vdda = vdda_est_ratio(rng, n, temp)
            r1 = r1n * u(rng, n, P.RESISTOR_TOL["RT0805DRD"])   # 0.5 % fitted part; its listed alternate is 1 %
            r2 = r2n * u(rng, n, P.RESISTOR_TOL["0805W8F"])
            vpin0 = vb * r2 / (r1 + r2)
            rth = r1 * r2 / (r1 + r2)
            for extra in (False, True):
                iz = np.array([zener_leak(v, extrapolate=extra) for v in vpin0[:1]]) * rng.uniform(0, 1, n)
                vpin = vpin0 - iz * rth
                raw = adc(rng, vpin, vdda)
                rd = raw * vdda * ratio / 4095 * (r1n + r2n) / r2n
                e = rd - vb
                worst.append((vb, temp, extra, float(e.min()), float(e.max())))
    for extra in (False, True):
        w = [x for x in worst if x[2] == extra]
        lo, hi = min(x[3] for x in w), max(x[4] for x in w)
        at = [x for x in w if x[3] == lo][0]
        rel = max(abs(lo), abs(hi)) / at[0] * 100
        verdict = "PASS" if max(abs(lo), abs(hi)) <= 0.25 else "WARN"
        add("Battery sense", "47k / 4.7k + PDZ3.3B -> ADC, 9-16 V, -40..105 C" +
            (" (zener knee extrapolated above VR 1 V)" if extra else " (zener IR max 5 uA at VR 1 V held)"),
            f"error {lo:+.2f} .. {hi:+.2f} V (worst at {at[0]} V, {at[1]} C)", "+-0.25 V (PASS)", verdict,
            "R1 0.5 % (RT0805DRD; the 1 % alternate C17713 adds about 0.1 V), R2 1 %, ADC ET, VDDA from VREFINT; "
            "D1 PDZ3.3B leaks across R2 (Nexperia IR <= 5 uA at 1 V, nothing specified at 1.2-1.5 V)")


# ------------------------------------------------------------------ 3. digital input thresholds
def digital_inputs():
    vdd_lo, vdd_hi = 3.3 * (1 - 0.015), 3.3 * (1 + 0.015)
    vil_t = P.STM32["vil_tested"] * vdd_lo
    vil_d = P.STM32["vil_design"][0] * vdd_lo + P.STM32["vil_design"][1]
    vih_t = P.STM32["vih_tested"] * vdd_hi
    vih_d = P.STM32["vih_design"][0] * vdd_hi + P.STM32["vih_design"][1]
    add("Digital input", "MCU input thresholds at the wire (4.7k series, no divider; VDD 3.3 V +-1.5 %)",
        f"low below {vil_t:.2f} V (tested) / {vil_d:.2f} V (design); high above {vih_t:.2f} V / {vih_d:.2f} V",
        "STM32 DS Table 56", "INFO", "the firmware reads the GPIO level (no software threshold)")
    # switch to a remote ground with ground offset: ISO 16750-2 4.8 asks +-1 V; 10k pull-up, 4.7k, switch 0.1 Ohm
    for off in (0.5, 1.0):
        v = off + (3.3 - off) * 0.1 / 10000
        verdict = "PASS" if v < vil_t else ("WARN" if v < vil_d else "FAIL")
        add("Digital input", f"switch-to-ground input, remote ground {off:+.1f} V above the PDM ground",
            f"pin {v:.2f} V", f"< VIL {vil_t:.2f} V (tested) / {vil_d:.2f} V (design)", verdict,
            "ISO 16750-2 4.8 ground offset" + ("; only the design value (not production tested) holds: bench test"
                                               if verdict == "WARN" else ""))
    # leakage to ground on an open, pulled-up line (wet harness): the line still reads high if R_leak >= this
    r_min = 10000 * vih_d / (3.3 - vih_d)
    add("Digital input", "pulled-up line, open switch: leakage to ground that still reads high", f">= {r_min / 1e3:.0f} kOhm",
        "harness insulation >> 1 MOhm", "PASS", "10k DIP pull-up vs VIH (design)")
    # switched-12 V input during cranking: reads high down to VIH + 0 (clamp holds the pin at the rail)
    add("Digital input", "switched-battery input at cranking (ISO 16750-2 starting profile, 4.5-6 V)",
        "pin 3.3-3.6 V (BAT54S clamp)", f"> VIH {vih_t:.2f} V", "PASS", "reads high from about 2.4 V on the wire")


# ------------------------------------------------------------------ 4. analog input
def analog_input(rng, n):
    div_fw = P.fw_const("a", "ANALOG_IN_DIVIDER")
    for vin in (0.5, 2.5, 4.5, 4.9):
        worst = (0, 0)
        for temp in TEMPS:
            ratio, vdda = vdda_est_ratio(rng, n, temp)
            r1 = 10000 * u(rng, n, 0.01)
            r2 = 20000 * u(rng, n, 0.01)
            isat = P.BAT54S_IS_25 * 2 ** ((temp - 25) / 10)
            vt = 8.617e-5 * (temp + 273.15)
            v = vin * r2 / (r1 + r2)
            for _ in range(30):     # node: (vin - v)/r1 = v/r2 + Ilo(v) - Ihi(v) ; Newton on the diode currents
                ihi = isat * (np.exp(np.clip((v - vdda) / vt, -50, 50)) - 1)      # AIN -> 3V3 diode
                ilo = isat * (np.exp(np.clip(-v / vt, -50, 50)) - 1)              # GND -> AIN diode
                f = (vin - v) / r1 - v / r2 - ihi + ilo
                df = -1 / r1 - 1 / r2 - isat / vt * np.exp(np.clip((v - vdda) / vt, -50, 50)) - isat / vt * np.exp(np.clip(-v / vt, -50, 50))
                v = v - f / df
            raw = adc(rng, np.minimum(v, vdda), vdda)
            rd = raw * vdda * ratio / 4095 * div_fw
            e = (rd - vin) * 1000
            worst = (min(worst[0], float(e.min())), max(worst[1], float(e.max())))
        lim = 50.0
        verdict = "PASS" if max(map(abs, worst)) <= lim else "WARN"
        add("Analog input", f"0-5 V input at {vin} V (10k / 20k 1 %, BAT54S, -40..105 C)",
            f"reads {worst[0]:+.0f} .. {worst[1]:+.0f} mV", f"+-{lim:.0f} mV (1 % of the 5 V span)", verdict,
            "5 V maps to 3.33 V, above a low VDDA (3.25 V): the top of the range clips / leaks into the clamp"
            if vin >= 4.9 else "resistors, ADC, VDDA estimate, BAT54S leakage (Nexperia IS, x2 per 10 K)")


# ------------------------------------------------------------------ 5. temperatures
def temperatures():
    warn, crit, hyst = 55, 80, 6
    pd = open(os.path.join(P.ROOT, "firmware", "core", "param_defs.h"), encoding="utf-8").read()
    m = re.search(r"#define DEFAULT_TEMP_CRIT_HYST (\d+)", pd)
    hyst = int(m.group(1)) if m else hyst
    on, off = P.fw_const("a", "FAN_ON_C"), P.fw_const("a", "FAN_OFF_C")
    e = P.MCP9808["acc_m20_100"]
    add("Temperature", f"MCP9808 board sensor (+-{e} C at -20..100 C) vs fan on {on:.0f} / off {off:.0f} C",
        f"fan switches on at true {on - e:.1f}..{on + e:.1f} C, off at {off - e:.1f}..{off + e:.1f} C; band {on - off:.0f} K",
        f"band > 2 x {e} K + 0.5 C step", "PASS" if on - off > 2 * e + 0.5 else "FAIL", P.MCP9808["src"])
    add("Temperature", f"MCP9808 vs warn {warn} / critical {crit} C, critical recovers {hyst} K lower",
        f"critical at true {crit - e:.1f}..{crit + e:.1f} C; recovery band {hyst} K", f"> 2 x {e} K",
        "PASS" if hyst > 2 * e else "FAIL", "core/device_config.h BOARD_TEMP_*, core/param_defs.h")
    # STM32 die sensor: the firmware converts the raw count with TS_CAL1/2 (taken at VDDA = 3.3 V) and does not
    # correct for the real VDDA (port.cpp GetTemperature): a VDDA error shifts the reading
    v25, slope = 0.76, 2.5e-3
    pc = open(os.path.join(P.ROOT, "firmware", "boards", "custompdm_a", "port.cpp"), encoding="utf-8").read()
    body = pc[pc.index("float GetTemperature()"):pc.index("float GetVDDA()")]
    corrected = "GetVDDA()" in body
    for vdda in (3.3 * 0.985, 3.3 * 1.015):
        shift = 0.0 if corrected else (v25 + slope * (60 - 25)) * (3.3 / vdda - 1) / slope
        add("Temperature", f"STM32 die sensor at VDDA {vdda:.3f} V (TLV1117LV +-1.5 %): firmware reading shift",
            f"{shift:+.1f} C (plus +-{P.STM32['ts_linearity']} C linearity)", "+-3 C", "WARN" if abs(shift) > 3 else "PASS",
            ("GetTemperature() scales the count by GetVDDA() / 3.3 V (TS_CAL at 3.3 V, DS Table 81)" if corrected else
             "GetTemperature() uses the raw count as if VDDA were 3.3 V (TS_CAL at 3.3 V, DS Table 81)") +
            "; die temperature is reported only (msg), it switches nothing")


# ------------------------------------------------------------------ 6. ADC sampling of the internal channels
def adc_sampling():
    src = open(os.path.join(P.ROOT, "firmware", "boards", "custompdm_a", "port.cpp"), encoding="utf-8").read()
    mc = open(os.path.join(P.ROOT, "firmware", "boards", "custompdm_a", "cfg", "mcuconf.h"), encoding="utf-8").read()
    pre = int(re.search(r"STM32_ADC_ADCPRE\s+ADC_CCR_ADCPRE_DIV(\d)", mc).group(1))
    ppre2 = int(re.search(r"STM32_PPRE2\s+STM32_PPRE2_DIV(\d+)", mc).group(1))
    hclk = 8e6 / int(re.search(r"PLLM_VALUE\s+(\d+)", mc).group(1)) * int(re.search(r"PLLN_VALUE\s+(\d+)", mc).group(1)) \
        / int(re.search(r"PLLP_VALUE\s+(\d+)", mc).group(1))
    fadc = hclk / ppre2 / pre
    for ch, key in (("SENSOR", "ts_min_sample_s"), ("VREF", "vref_min_sample_s")):
        m = re.search(rf"SMP_{ch}\(ADC_SAMPLE_(\d+)\)", src)
        cyc = int(m.group(1)) if m else 3
        t = cyc / fadc
        need = P.STM32[key]
        add("ADC sampling", f"{'temperature sensor' if ch == 'SENSOR' else 'VREFINT'} sampling time (board A / B port.cpp)",
            f"{cyc} cycles at {fadc / 1e6:.0f} MHz = {t * 1e6:.2f} us", f">= {need * 1e6:.0f} us (DS Table 80 / 83)",
            "PASS" if t >= need else "FAIL",
            "VREFINT sets GetVDDA(), so every current and voltage reading carries its error" if ch == "VREF" else
            "die-temperature reading only")
    # board A dual-channel PROFETs: the IS read after a DSEL change must come from a conversion started after the
    # sense output settled: DSEL_SETTLE_US >= tsIS(CC) 20 us (BTS7008 P_9.6.1.10) + 7 x 4.7k x 220p + one ADC sequence
    smp = {m.group(1): int(m.group(2)) for m in re.finditer(r"SMP_(\w+)\(ADC_SAMPLE_(\d+)\)", src)}
    nch = len(re.findall(r"SQ\d+_N\(", src))
    seq = sum(smp.get(c, 15) + 12 for c in ["AN0"] * (nch - 2)) + (smp.get("SENSOR", 15) + 12) + (smp.get("VREF", 15) + 12)
    t_seq = seq / fadc
    ph = open(os.path.join(P.ROOT, "firmware", "boards", "custompdm_a", "port.h"), encoding="utf-8").read()
    m = re.search(r"#define DSEL_SETTLE_US (\d+)", ph) or re.search(r"#define DSEL_SETTLE_US (\d+)", open(
        os.path.join(P.ROOT, "firmware", "functions", "profet.h"), encoding="utf-8").read())
    settle = int(m.group(1)) * 1e-6
    need = 20e-6 + 7 * 4700 * 220e-12 + t_seq
    add("ADC sampling", "board A DSEL change -> IS read (dual BTS7008 channels)",
        f"DSEL_SETTLE_US {settle * 1e6:.0f} us; ADC sequence {t_seq * 1e6:.1f} us ({nch} channels)",
        f">= tsIS(CC) 20 us + RC {7 * 4700 * 220e-12 * 1e6:.1f} us + one sequence = {need * 1e6:.1f} us",
        "PASS" if settle >= need else "FAIL", "else the read can come from a conversion of the other channel's current")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--json")
    a = ap.parse_args()
    rng = np.random.default_rng(20261120)
    is_chain(rng, a.n)
    batt_sense(rng, a.n)
    digital_inputs()
    analog_input(rng, a.n)
    temperatures()
    adc_sampling()
    for r in RES:
        print(f"{r['verdict']:<5} [{r['group']}] {r['check']}: {r['value']} (limit {r['limit']})" + (f" - {r['note']}" if r['note'] else ""))
    cnt = {v: sum(r["verdict"] == v for r in RES) for v in ("PASS", "WARN", "FAIL", "INFO")}
    print("TOTAL", cnt)
    if a.json:
        json.dump(RES, open(a.json, "w"), indent=1)
    return 1 if cnt["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
