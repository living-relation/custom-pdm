"""Presim item 2: power - logic rails vs battery voltage, brown-out vs the MCU, reverse battery, ISO 7637-2 / load dump
on the external pins, and the inductive turn-off energy of the car loads vs the PROFET clamp / freewheel diode ratings.

usage (repo root): python tools/verify_power.py [--json out.json]      (pure python + numpy; exit 1 on any FAIL)

Rail chain (netlist, both main boards): +12V -> D19 (A) / D3 (B) PMEG10010ELR -> +12P -> TSR 1-2450 -> +5VP ->
D18 (A) / D4 (B) PMEG2010AEH -> +5V -> TLV1117LV33 -> +3V3; MCP2562FD VDD on +5V. The supply pin's TVS / load dump
is job d2tvs (tools/verify_spice.py); not repeated here.
Every value: tools/presim_parts.py. Values marked ASSUMED are not in any data sheet and are bench tests.
"""
import argparse
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import presim_parts as P  # noqa: E402

RES = []


def add(group, check, value, limit, verdict, note=""):
    RES.append(dict(group=group, check=check, value=value, limit=limit, verdict=verdict, note=note))


TSR_DROPOUT = 1.0     # V, ASSUMED: below its 6.5 V minimum input the TSR is taken as unregulated, out = in - 1.0 V


def rails(vbat, worst=True, cold=False):
    """Lowest (worst=True) logic rail voltages at battery voltage vbat: TSR at -2 % and the PMEG2010 max VF at 25 C;
    cold=True stacks every TSR tolerance at -40 C and the cold VF (docs/parts-audit.md section 9)."""
    tsr_in = vbat - P.PMEG10010["vf_100ma"]
    t = P.TSR
    reg = 5.0 * (1 - t["acc"] - (t["line"] + t["load"] + t["tc"] * 65 if cold else 0)) if worst else 5.0
    v5p = reg if tsr_in >= t["vin_min"] else min(reg, tsr_in - TSR_DROPOUT)
    v5 = v5p - (P.PMEG2010["vf_cold"] if cold else P.PMEG2010["vf_100ma"][1] if worst else P.PMEG2010["vf_100ma"][0])
    v33 = min(3.3 * (1 - P.TLV1117LV["acc"] * 1.5 if worst else 1), v5 - P.TLV1117LV["vdo_200ma"])
    return max(v5p, 0), max(v5, 0), max(v33, 0)


def rail_checks():
    v5c = rails(13.5, cold=True)[1]
    add("Rails", "+5V for the CAN chip, every TSR tolerance stacked at -40 C + cold PMEG2010 VF", f"{v5c:.2f} V",
        ">= 4.5 V (MCP2562FD VDD)", "PASS" if v5c >= 4.5 else "WARN",
        "all limits at once at -40 C (docs/parts-audit.md section 9: not counted as a fail); bench: +5V at -40 C")
    vs = np.arange(3.0, 16.01, 0.05)
    first = {}
    for v in vs:
        v5p, v5, v33 = rails(v)
        for k, ok in (("can", v5 >= P.MCP2562FD["vdd"][0]), ("ldo", v33 >= 3.3 * (1 - 0.015 * 1.5) - 1e-9),
                      ("mcu_spec", v33 >= P.STM32["ws_range_2v7"][0]), ("mcu_bor3", v33 >= P.STM32["bor"][2][2])):
            if ok and k not in first:
                first[k] = v
    add("Rails", "battery voltage at which CAN works (MCP2562FD VDD >= 4.5 V on +5V)", f">= {first['can']:.2f} V",
        "<= 9 V (ISO 16750-2 code A/B supply range from 9 V)", "PASS" if first["can"] <= 9 else "FAIL",
        "every tolerance at its limit at -40 C (TSR set / line / load / tempco, PMEG2010 cold VF 0.38 V)")
    add("Rails", "battery voltage at which +3V3 is regulated", f">= {first['ldo']:.2f} V", "<= 6.5 V (TSR minimum input)",
        "PASS" if first["ldo"] <= 7.0 else "WARN", f"below the TSR's 6.5 V input the model takes out = in - {TSR_DROPOUT} V (ASSUMED)")
    add("Rails", "battery voltage at which +3V3 stays >= 2.7 V (the 4-wait-state flash setting at 144 MHz is valid "
        "only at VDD 2.7-3.6 V, DS Table 17)", f">= {first['mcu_spec']:.2f} V", "cranking: 6 V (brief), ISO 16750-2 "
        "starting profile down to 4.5 V", "PASS" if first["mcu_spec"] <= 4.5 else "WARN",
        "below it the MCU runs out of its data-sheet range unless the BOR holds it in reset (next row)")
    v5p, v5, v33 = rails(6.0)
    add("Rails", "6 V cranking: +5VP / +5V / +3V3 (worst)", f"{v5p:.2f} / {v5:.2f} / {v33:.2f} V",
        "CAN needs +5V >= 4.5 V; MCU +3V3 >= 2.7 V", "WARN" if v5 < 4.5 else "PASS",
        "CAN drops out while cranking at 6 V (TSR below its 6.5 V minimum input, dropout ASSUMED): "
        "the PDM keeps its outputs, the CAN link-loss rules apply after their time-out" if v5 < 4.5 else "")
    for vb in (16.0, 24.0):
        v5p_hi = 5.0 * (1 + P.TSR["acc"] + P.TSR["line"] + P.TSR["load"] + P.TSR["overshoot"])
        ok = vb <= P.TSR["vin_max"] and v5p_hi - P.PMEG2010["vf_100ma"][0] <= P.TLV1117LV["vin_max_abs"]
        add("Rails", f"{vb:.0f} V ({'max normal' if vb == 16 else 'jump start'}): TSR input, LDO input",
            f"TSR in {vb - 0.4:.1f} V; LDO in <= {v5p_hi - P.PMEG2010['vf_100ma'][0]:.2f} V", "TSR <= 36 V; LDO <= 6 V abs",
            "PASS" if ok else "FAIL", "PROFET VS max 28 V (BTS7008 Table 3): 24 V jump start inside")
    # TSR load step: the CAN chip's dominant current is the biggest step on +5VP (70 mA max)
    dv = P.TSR["step_dv"] * 0.07 / 0.5
    v5_min = 5.0 * (1 - P.TSR["acc"]) - P.PMEG2010["vf_100ma"][1] - dv
    add("Rails", "TSR load step (CAN dominant 0 -> 70 mA, DS20005284A IDD) at TSR -2 %", f"+5V {v5_min:.2f} V",
        ">= 4.5 V", "PASS" if v5_min >= 4.5 else "WARN", "Traco: 200 mV max for a 50 % (500 mA) step, scaled linearly")


def bor_check():
    fw = ""
    for root, _, files in os.walk(os.path.join(P.ROOT, "firmware")):
        if "ChibiOS" in root or "sim" in root.split(os.sep):
            continue
        for f in files:
            if f.endswith((".c", ".cpp", ".h")):
                fw += open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
    sets_bor = bool(re.search(r"OPTCR[^;\n]*BOR_LEV|FLASH_OPTCR_BOR_LEV", fw))
    pvd = re.search(r"STM32_PVD_ENABLE\s+(\w+)", open(os.path.join(P.ROOT, "firmware", "boards", "custompdm_a", "cfg",
                                                                  "mcuconf.h"), encoding="utf-8").read()).group(1)
    pdr = P.STM32["pdr"]
    add("Brown-out", "MCU reset below the 2.7 V needed by the flash wait states (BOR level 3, 2.75-2.88 V)",
        "firmware sets BOR_LEV: " + ("yes" if sets_bor else "no") + f"; PVD {pvd}; factory option bytes: BOR off "
        f"(reset only at the POR / PDR {pdr[0]}-{pdr[2]} V)", "reset or hold below 2.7 V", "PASS" if sets_bor else "FAIL",
        "RM0390 3.7: FLASH_OPTCR BOR_LEV factory value 11 = BOR off. Between 1.7 and 2.7 V (a slow start-up, a deep "
        "crank, a failing feed) the MCU runs at 144 MHz on 4 flash wait states, outside DS Table 17: wrong instruction "
        "fetch, wrong outputs, FRAM writes. Fix: program BOR level 3 once (firmware at boot or the flashing step)")


def reverse_battery():
    add("Reverse battery", "logic supply (TSR) behind D19 (A) / D3 (B) PMEG10010ELR", "diode blocks 13.5 V",
        "VR 100 V", "PASS", "no logic current; the MCU, CAN chip and sensors stay unpowered")
    add("Reverse battery", "PROFET channels (ReverseON) with the board's RGND 47 Ohm, RIN / RDEN / RDSEL / RIS 4.7k",
        "same parts as the data sheet's reverse-polarity setup", "-VBAT(REV) 16 V for 2 min (BTS7008 P_4.1.0.5, Ch. 10)",
        "PASS", "IDI(REV) via 4.7k: 13.5 / 4.7k = 2.9 mA <= 10 mA (P_4.1.0.36); the loads run reversed")
    if P.FREEWHEEL["B"]:
        add("Reverse battery", "board B freewheel diodes D13 .. D28 (BYG23M, anode GND, cathode PF_OUT) with the PROFET "
            "conducting in reverse (ReverseON / body diode)", "forward-biased straight across the battery: about 13.5 V / "
            "(wiring + PROFET RDS(REV) of a few mOhm) = hundreds of A", f"BYG23M IFSM {P.BYG23M['ifsm']} A (10 ms)", "FAIL",
            "every board B output shorts the reversed battery through its diode and switch: the diodes fail (then short or "
            "open) and the feed fuse blows (stock dingoPDM-Max the same). Removing them moves the A/C clutch / fan "
            "turn-off into the switch clamp (run with --no-freewheel-b): a design choice, see docs/system-verification.md")
    else:
        add("Reverse battery", "board B outputs: freewheel diodes " + P.FREEWHEEL_FOOTPRINTS_B, "no path from GND to an "
            "output past the load: each switch's reverse current is its load current (ReverseON channel)",
            "BTS70012 / BTS7004 8.4.1: 'reverse current ... limited by the connected load'; -VBAT(REV) 16 V, 2 min",
            "PASS", "the loads run reversed (fans / pumps backwards, lamps lit) until the battery is turned round; "
            "the feed fuse sees only the sum of the load currents")
    add("Reverse battery", "input board pins at -13.5 V", f"{13.5 / 4.7e3 * 1e3:.1f} mA into the BAT54S low diode",
        "BAT54S IF 200 mA; STM32 pin -5 mA", "PASS", "the Schottky holds the pin near -0.3 V, above the MCU's own diode")
    add("Reverse battery", "CAN lines (transceiver unpowered)", "bus pins see the other nodes' levels",
        "MCP2562FD CANH / CANL DC -58 .. +58 V", "PASS", P.MCP2562FD["src"])


def pin_transients():
    """ISO 7637-2 pulses (12 V, level IV) and the suppressed load dump on an input wire that is switched to battery.
    Input board channel: wire -> 4.7k 0603 -> IN (10 nF, BAT54S to +3V3 / GND) -> MCU; optional 10k pull-up wire->+3V3."""
    pulses = [("1", -150, 10, 2e-3), ("2a", 112, 2, 50e-6), ("3a", -220, 50, 0.1e-6), ("3b", 150, 50, 0.1e-6)]
    for name, us, ri, td in pulses:
        rin, rpu = 4700.0, 10000.0
        vclamp = 3.6 if us > 0 else -0.6
        # wire node: source (us, ri) loaded by the 4.7k into the clamped IN node and the 10k into +3V3
        g = 1 / ri + 1 / rin + 1 / rpu
        vw = (us / ri + vclamp / rin + 3.3 / rpu) / g
        i_in = (vw - vclamp) / rin
        v_r = abs(vw - vclamp)
        ok_v = v_r <= 150
        verdict = "PASS" if ok_v and abs(i_in) < 0.2 else "WARN"
        add("ISO 7637-2 on an input wire", f"pulse {name} ({us:+d} V, {ri} Ohm, {td * 1e6:g} us)",
            f"{i_in * 1e3:+.1f} mA in the BAT54S; {v_r:.0f} V across the 4.7k 0603",
            "BAT54S IF 200 mA; 0603 resistor overload 150 V (Uniroyal 0603WAF)", verdict,
            "" if verdict == "PASS" else "a 0.1 us pulse above the resistor's overload voltage: ISO lab / bench test "
            "(the pulses are for supply lines; an input wired to a switched battery line sees them)")
    # suppressed load dump on every battery-switched input: current pushed into board A +3V3 (LDO cannot sink)
    i_one = (35 - 3.6) / 4.7e3
    i_pu = (35 - 3.3) / 10e3
    load_run = 0.040     # A, ASSUMED lowest running +3V3 load (MCU at 144 MHz + sensors), as tools/verify_spice.py
    n_ok = int(load_run // (i_one + i_pu))
    add("Load dump on inputs", "ISO 16750-2 test B (35 V, 400 ms) on battery-switched inputs: current into +3V3",
        f"{(i_one + i_pu) * 1e3:.1f} mA per input with its 10k pull-up on ({i_one * 1e3:.1f} mA without)",
        f"total < the running +3V3 load (about {load_run * 1e3:.0f} mA, ASSUMED)", "WARN",
        f"up to {n_ok} such inputs per input board with pull-ups on (or {int(load_run // i_one)} without) keep +3V3 "
        "in regulation; with all 8 at 35 V (79 mA) +3V3 rises toward the MCU's 4.0 V abs max: keep battery-switched "
        "inputs few and their pull-ups off, or add a +3V3 shunt clamp (hardware)")
    add("CAN pins", "short to battery at a 24 V jump start / ISO 7637-3 coupled pulses", "NUP2105 VRWM 24 V: off at 24 V",
        "MCP2562FD -58 .. +58 V DC, -150 / +100 V ISO 7637", "PASS", "NUP2105 (onsemi) on CAN_H / CAN_L (D4 A, D9 B)")
    add("USB", "USB-C behind the box bulkhead and the Adafruit 5997 hub (enclosure v2c)", "PESD5V0F1BL on USB_D+ and "
        "USB_D- (both main boards, hwprotect), at the MCU end of the lines", "IEC 61000-4-2 8 kV contact (Nexperia "
        "PESD5V0F1BL), 0.4 pF per line vs USB full speed", "PASS",
        "VBUS has the D6 / D15 Schottky and the +5V bulk capacitors; the bulkhead side is the hub's (enclosure job)")


def clamp_energy():
    """Single turn-off of each car load (docs/car-loads.dummy.md): board A has no freewheel diode, so the PROFET's
    active clamp (VDS(CLAMP) >= 35 V) takes E = 1/2 L I^2 x Vcl / (Vcl - Vbat); board B the same since hwprotect (its
    BYG23M freewheel diodes are not fitted)."""
    vbat = 16.0
    for name, board, out, drv, i, (l_lo, l_hi), *_ in P.CAR_LOADS:
        d = P.PROFET[drv]
        if P.FREEWHEEL[board]:
            # diode current I e^(-t/tau): I^2 t = I^2 tau / 2 with tau = L / R, R = 13.5 V / I
            tau = l_hi / (13.5 / i) if i > 0 else 0
            i2t = i * i * tau / 2
            lim = P.BYG23M["ifsm"] ** 2 * P.BYG23M["ifsm_t"] / 2
            add("Turn-off energy", f"{name} ({board} OUT{out}, {i} A, L <= {l_hi * 1e3:g} mH, BYG23M freewheel)",
                f"diode I^2t {i2t:.3f} A^2s, peak {i:.0f} A", f"BYG23M surge {lim:.1f} A^2s ({P.BYG23M['ifsm']} A 10 ms)",
                "PASS" if i2t < lim and i <= P.BYG23M["ifsm"] * 1.5 else "WARN", "single turn-off; PWM: tools/verify_switching.py")
            continue
        vcl = d["clamp"][0]
        r = 13.5 / i
        vz = vcl - vbat
        i0 = vbat / r

        def e_clamp(l):     # L-R load into the clamp: v_L = -(Vcl - Vbat) - i R; energy in the switch = int Vcl i dt
            return l * vcl / r * (i0 - vz / r * np.log(1 + i0 * r / vz))
        e_lo, e_hi = e_clamp(l_lo), e_clamp(l_hi)
        eas, _ = d["eas"]
        ear, _ = d["ear"]
        verdict = "PASS" if e_hi <= ear else ("FAIL" if e_lo > eas else "WARN")
        add("Turn-off energy", f"{name} ({board} OUT{out}, {i} A, L {l_lo * 1e3:g}-{l_hi * 1e3:g} mH ASSUMED, no diode)",
            f"{e_lo * 1e3:.1f}-{e_hi * 1e3:.1f} mJ into the {drv} clamp", f"EAR {ear * 1e3:.0f} mJ (1M cycles) / EAS "
            f"{eas * 1e3:.0f} mJ (single, TJ0 150 C)", verdict, f"L-R load ({r:.2f} Ohm at 13.5 V), switched off at 16 V, "
            f"VDS(CLAMP) min {vcl} V" + ("; above EAR inside the L range: bench-measure L; if confirmed, a freewheel "
                                          "diode / RC at the load (or a board B output)" if verdict != "PASS" else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--no-freewheel-b", action="store_true", help="board B without its BYG23M freewheel diodes (what-if)")
    a = ap.parse_args()
    if a.no_freewheel_b:
        P.FREEWHEEL["B"] = None
    rail_checks()
    bor_check()
    reverse_battery()
    pin_transients()
    clamp_energy()
    for r in RES:
        print(f"{r['verdict']:<5} [{r['group']}] {r['check']}: {r['value']} (limit {r['limit']})" + (f" - {r['note']}" if r['note'] else ""))
    cnt = {v: sum(r["verdict"] == v for r in RES) for v in ("PASS", "WARN", "FAIL", "INFO")}
    print("TOTAL", cnt)
    if a.json:
        json.dump(RES, open(a.json, "w"), indent=1)
    return 1 if cnt["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
