"""Presim item 6: whole-box heat - steady state and transient (fans on / fans failed), copper losses included, the air
under the lid, and every part against its temperature rating.

usage (repo root, KiCad 9 python + numpy + scipy, as tools/thermal_board_b.py):
    python tools/verify_thermal_box.py [--fans JSON --nofan JSON] [--cabin 60] [--json out.json]
    Without --fans / --nofan it runs tools/thermal_board_b.py itself (cases car, feed150, rating; about 8 min).

Built on, not instead of, tools/thermal_board_b.py (job hwfix, PR #114: board B finite-volume model on the real
copper with the sink, gap pad and lid air; its sink temperature = 60 C cabin + R_sys x box heat, R_sys 0.47 K/W fans /
0.98 K/W fans off on a wall, from the Elmer enclosure model, docs/heat-analysis.md / docs/enclosure-v2c.md 4). Added:
  * the air under the lid as one node: heat in from the X1 / X2 contacts and the internal harness (docs/heat-analysis.md
    3 values, per output current), from the board tops (h 3 W/m2K, thermal_board_b's htop) and the sink's open top;
    heat out through the lid (0.12 m2 x 1.8 W/m2K overall, docs/heat-analysis.md 3) - all ASSUMED values from there;
  * the transient: the sink's heat capacity (1775 g aluminium, mass_v2c.py, c 896 J/kgK) with R_sys: warm-up and a fan
    failure at full load, against the board's own MCP9808 critical limit (80 C) and the laminate limit;
  * each temperature-rated part (docs/parts-audit.md section 6 / 10 ratings) against its local temperature;
  * board B's firmware temperature limits (job fwsafety, ADR-2026-11-20-presim-findings item 1), read from
    firmware/tools_custom/port_boards.py: the sensor -> hot-spot map over every case in the input (laminate - U6 and
    Tj - U6), then: no warning at the car loads with fans on; at the critical limit (+ the MCP9808's +-1 C, DS20005095B)
    the laminate stays <= 130 C and Tj <= 150 C at the largest modelled offset; the board B logic-area parts (at the
    sensor reading) stay within their rating; and the limit any part rating would need.
Limits: laminate <= 130 C, Tj <= 150 C.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import copper_order  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = []
R_SYS = {"fans": 0.54, "nofan": 1.25}      # = tools/thermal_board_b.py R_SYS (revF whole-box Elmer, 2026-11-23)
C_SINK = 1.775 * 896.0                       # J/K
G_LID = 0.12 * 1.8                           # W/K lid to cabin
G_SINK_AIR = 0.010 * 3.0                     # W/K open sink top (about 0.01 m2 not under a board) to the lid air
G_BOARD_AIR = 0.024 * 3.0                    # W/K three board tops (2 x 72 x 95 mm + board B) to the lid air
DT_BOARD_A = 15.0                            # K, board A mean over the sink (ASSUMED from docs/heat-analysis.md 2)
LAMINATE_C, TJ_C = 130.0, 150.0
SENSOR_ERR = 1.0                             # MCP9808 +-1 C max at -40..125 C (DS20005095B DC characteristics)
RES_MM = "0.3"                               # thermal_board_b grid for this check: the grid-checked one (0.3 / 0.25 mm
#                                              agree within 0.2 K, docs/pcb-verification.md); 0.4 reads the +12V neck low


def bom_grades(tag):
    """Crystal and ceramic-capacitor temperature grade of one board, read from its generated full BOM
    (hardware/fab/<tag>/<tag>-bom-full.csv), so this table follows the parts that are really fitted.
    Returns (crystal name, rating C, capacitor text, rating C)."""
    import csv
    xtal, x5r, n_cap = ("?", 85.0), [], 0
    with open(os.path.join(ROOT, "hardware", "fab", tag, f"{tag}-bom-full.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r["Fitted by"].startswith("JLCPCB"):
                continue
            refs, mpn = r["Designator"].split(","), r["MPN"]
            if "Y1" in refs:      # ECS-...-CES: -40..125 C; ECS-...-VY: 105 C (ecsxtal.com 30Q data sheets); ABM3: 85 C
                xtal = (mpn, 125.0 if "-CES-" in mpn else 105.0 if "-VY-" in mpn else 85.0)
            if refs[0].startswith("C") and r["Footprint"].startswith("C_"):
                n_cap += len(refs)
                # X5R (85 C) by maker code: Samsung CL..A.., Murata GRM..R6.. (the X7R / C0G parts are 125 C)
                if re.match(r"CL\d\dA|GRM\d\d\wR6", mpn):
                    x5r += refs
    caps = (f"X5R capacitors {' '.join(x5r)}", 85.0) if x5r else (f"ceramic capacitors (all {n_cap} X7R / C0G)", 125.0)
    return xtal + caps


GRADE = {k: bom_grades(tag) for k, tag in (("A", "board-a"), ("B", "board-b"))}
# 5 V module board limit: TJ 125 C less its own loss x PsiJB 20 K/W; the loss is the board models' (TI SNVSAQ4C Figure
# 8-46 at 0.22 A, 13.5 V + hot conduction share, thermal_board_b P_5V, job hwtemp): set from the JSON in main()
LIMIT_5V = [125.0 - 20.0 * 0.131]
# board B logic-area parts at its MCP9808 reading: rating C (crystal / capacitors: from board B's BOM)
LOGIC_PARTS = [("STM32F446RET7 (ambient, suffix 7)", 105.0), ("CY15B064J-SXE FRAM (Automotive-E, hwtemp)", 125.0),
               (f"crystal Y1 {GRADE['B'][0]}", GRADE["B"][1]), (GRADE["B"][2], GRADE["B"][3])]
# parts the board models report on their own (thermal_*.py "parts": hottest board cell under the part), with ratings
PART_RATING = {"U4": ("MCU STM32F446RET7 (105 C ambient)", 105.0), "U5": ("FRAM CY15B064J-SXE (125 C)", 125.0),
               "U21": ("5 V module LMZM23601V5 (board under it)", None), "U27": ("5 V module LMZM23601V5 (board under it)", None)}


def board_limits(board="B"):
    """A board's factory warn / critical from firmware/tools_custom/port_boards.py (board B: the FAN_B block, board A:
    the FAN_A block)."""
    py = open(os.path.join(ROOT, "firmware", "tools_custom", "port_boards.py"), encoding="utf-8").read()
    m = re.search(rf"#define DEFAULT_TEMP_WARN (\d+)\s+// board {board}\b.*?\n#define DEFAULT_TEMP_CRIT (\d+)", py, re.S)
    return (int(m.group(1)), int(m.group(2))) if m else None


def board_b_limits():
    return board_limits("B")


CRIT_C = float(board_b_limits()[1])
# parts rated below the board limit (docs/parts-audit.md section 10 table): name, rating C, where it sits
RATED = [("TI LMZM23601V5 5 V module (hw5v; TJ 125 C less its own loss x PsiJB)", None, "board")] + [
         (f"board {k}: {name}", rating, "board") for k in ("A", "B") for name, rating in
         ((f"crystal Y1 {GRADE[k][0]}", GRADE[k][1]), (GRADE[k][2], GRADE[k][3]))] + [
         ("input-board solder jumpers JP1-JP16 (FR-4 laminate; the 70 C DIP switches until hwtemp)", 130.0, "air"),
         ("CY15B064J-SXE FRAM (Automotive-E)", 125.0, "board"),
         ("STM32F446RET7 (ambient)", 105.0, "board"), ("MCP2562FD / MCP9808 / TLV9004 / TLV1117LV", 125.0, "board")]


def add(group, check, value, limit, verdict, note=""):
    RES.append(dict(group=group, check=check, value=value, limit=limit, verdict=verdict, note=note))


def contacts_harness(case):
    """Heat into the lid air from the X1 / X2 contacts and the internal harness, W (docs/heat-analysis.md 3)."""
    if case == "drive":      # s5 drive cycle RMS currents (thermal_board_b.drive_currents, same file and phase)
        d = drive_currents()
        a7 = [d["A1"].get(f"PF_OUT{i}", 0.0) for i in range(1, 9)] + [d["A2"].get(f"PF_OUT{i}", 0.0) for i in range(1, 9)]
        b15 = [d["B"].get(f"PF_OUT{i}", 0.0) for i in range(5, 9)]
        return sum(i * i * (2e-3 + 3.3e-3) for i in a7) + sum(i * i * (1e-3 + 0.78e-3) for i in b15)
    a7 = {"car": [2.0, 2.5, 0.5, 0.2, 5.0, 0.15, 5.0, 5.0, 0.2, 0.13, 0.2, 3.0, 0, 0, 0, 0],
          "feed150": [7.5 * 0.4] * 16, "feed150hi": [7.5 * 0.4] * 16, "feed150lo": [7.5 * 0.4] * 16, "rating": [7.5] * 16}[case]
    b15 = {"car": [8.1, 3.6, 6.0, 0], "feed150": [15.0 * 0.815] * 4, "feed150hi": [26.0 / 4] * 4, "feed150lo": [15.0] * 4,
           "rating": [15.0] * 4}[case]   # board B OUT5-8 (thermal_board_b.py case_currents)
    return sum(i * i * (2e-3 + 3.3e-3) for i in a7) + sum(i * i * (1e-3 + 0.78e-3) for i in b15)


def drive_currents():
    """thermal_board_b.drive_currents without pcbnew: RMS per output over the s5 coolant / fan phase."""
    import csv
    path = os.path.join(ROOT, "firmware", "sim", "data", "s5_board_power.csv")
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(ln for ln in f if not ln.startswith("#")) if r["phase"].startswith("coolant")]
    out = {"A1": {}, "A2": {}, "B": {}}
    for c in rows[0]:
        if c.startswith("I") and c.endswith("_A") and c.count("_") == 3:
            _, board, o, _ = c.split("_")
            out[board][f"PF_{o}"] = math.sqrt(sum(float(r[c]) ** 2 for r in rows) / len(rows))
    return out


def run_board_b(air, cases):
    out = os.path.join(tempfile.gettempdir(), f"presim_thb_{air}.json")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "thermal_board_b.py"), "--case", *cases, "--air", air,
                    "--res", RES_MM, "--json", out], check=False)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fans")
    ap.add_argument("--nofan")
    ap.add_argument("--afans", help="tools/thermal_a.py --air fans JSON: board A's limits are checked too")
    ap.add_argument("--anofan", help="tools/thermal_a.py --air nofan JSON")
    ap.add_argument("--cabin", type=float, default=60.0)
    ap.add_argument("--json")
    a = ap.parse_args()
    cases = ["car", "drive", "feed150", "feed150hi", "feed150lo", "rating"]
    data = {}
    for air in ("fans", "nofan"):
        path = getattr(a, air) or run_board_b(air, cases)
        data[air] = {r["case"]: r for r in json.load(open(path))}
        notord = [c for c, r in data[air].items() if r.get("ordered") is not True]
        if notord:        # no verdict on a copper thickness that is not ordered (tools/copper_order.py)
            raise SystemExit(f"{path}: cases {notord} were not run at the ordered copper ({copper_order.text('B')}): "
                             "re-run tools/thermal_board_b.py without --outer-um / --inner-um")
    print(f"board B copper: {copper_order.text('B')} (ordered, tools/copper_order.py)")
    lim5 = next((r["limit_5v_board"] for r in data["fans"].values() if "limit_5v_board" in r), None)
    if lim5 is not None:
        LIMIT_5V[0] = lim5
    for air in ("fans", "nofan"):
        for case in cases:
            r = data[air].get(case)
            if not r:
                continue
            ts = r["t_sink"] + (a.cabin - 60.0)
            tb_b = sum(c["t_board"] for c in r["chips"]) / len(r["chips"]) + (a.cabin - 60.0)
            tb_a = ts + DT_BOARD_A
            p_air = contacts_harness(case)
            g_tot = G_LID + G_SINK_AIR + G_BOARD_AIR
            t_air = (p_air + G_LID * a.cabin + G_SINK_AIR * ts + G_BOARD_AIR * (2 * tb_a + tb_b) / 3) / g_tot
            lam = r["laminate_max"] + (a.cabin - 60.0)
            tj = r["tj_max"] + (a.cabin - 60.0)
            sens = (r.get("t_sensor_u6") or float("nan")) + (a.cabin - 60.0)
            label = f"{case} ({r['I_B']:.0f} A on B), {'fans on' if air == 'fans' else 'fans failed / off'}, cabin {a.cabin:.0f} C"
            ok = lam <= LAMINATE_C and tj <= TJ_C
            if case in ("car", "feed150"):
                # normal use = the car loads with the fans on: must not cut; anything hotter: a cut is the protection
                v = ("PASS" if sens < CRIT_C else "FAIL") if (case, air) == ("car", "fans") else "INFO"
                add("Firmware limits", f"board B's own MCP9808 vs its critical limit {CRIT_C:.0f} C (port_boards.py "
                    f"DEFAULT_TEMP_CRIT) at {label}", f"reads {sens:.1f} C (laminate max {lam:.1f} C)",
                    f"< {CRIT_C:.0f} C, else board B cuts its outputs in normal use" if v != "INFO" else
                    f"{'cuts here' if sens >= CRIT_C else 'no cut'} (not normal use)", v,
                    "" if v == "PASS" else f"{lam - sens:.0f} K between the sensor and the laminate hot spot; a cut here "
                    "is the protection working (see the firmware-limit rows below for normal use)")
            add("Box steady", label, f"box {r['p_box']:.1f} W (B copper {r['p_copper']:.1f} W); sink {ts:.1f} C; lid air "
                f"{t_air:.1f} C; board B: Tj max {tj:.1f} C ({r['hottest_chip']}), laminate {lam:.1f} C, own MCP9808 {sens:.1f} C",
                f"Tj <= {TJ_C:.0f}, laminate <= {LAMINATE_C:.0f} C", "PASS" if ok else ("INFO" if case == "rating" else "FAIL"),
                "every output at its rating = 184 A on B, above the 150 A feed limit the firmware enforces: upper bound "
                "only" if case == "rating" else "" if ok or sens >= CRIT_C else f"the board's own sensor reads {sens:.0f} C < the {CRIT_C:.0f} C critical "
                "limit while the laminate is over its limit: the firmware does not see it (see the transient row)")
            if case == "feed150":
                for name, rating, where in RATED:
                    rating = LIMIT_5V[0] if rating is None else rating
                    t = t_air if where == "air" else max(tb_a, sens)
                    v = "PASS" if t <= rating else ("WARN" if t <= rating + 10 else "FAIL")
                    add("Part ratings", f"{name} at {label}", f"local {t:.0f} C (" + ("lid air" if where == "air" else
                        f"board B at its MCP9808 {sens:.0f} C / board A sink + {DT_BOARD_A:.0f} K = {tb_a:.0f} C") + ")",
                        f"<= {rating:.0f} C", v, "" if v == "PASS" else "parts-audit section 10 lists the higher-rated "
                        "drop-in / alternate; local temperature is an estimate (bench: thermocouple on the part)")
    # transient: fan failure at 150 A on board B (sink time constant), vs the firmware critical limit
    f, n = data["fans"].get("feed150"), data["nofan"].get("feed150")
    if f and n:
        p = n["p_box"]
        tau = R_SYS["nofan"] * C_SINK
        t0, t1 = f["t_sink"], n["t_sink"]
        d_lam = n["laminate_max"] - n["t_sink"]
        d_sen = (n.get("t_sensor_u6") or n["t_sink"]) - n["t_sink"]

        def t_cross(limit, offset):
            target = limit - offset
            if target >= t1:
                return None
            if target <= t0:
                return 0.0
            return -tau * math.log((t1 - target) / (t1 - t0))
        tl = t_cross(LAMINATE_C, d_lam)
        tc = t_cross(CRIT_C, d_sen)
        ok = tl is None or (tc is not None and tc < tl)
        add("Box transient", "fans fail at 150 A on board B (sink tau = R_sys x C = "
            f"{tau / 60:.0f} min, sink {t0:.0f} -> {t1:.0f} C)",
            f"laminate reaches {LAMINATE_C:.0f} C after {('%.0f min' % (tl / 60)) if tl is not None else 'never'}; board B's "
            f"MCP9808 reaches {CRIT_C:.0f} C after {('%.0f min' % (tc / 60)) if tc is not None else 'never'}",
            "the firmware's critical cut comes first", "PASS" if ok else "FAIL",
            f"{p:.1f} W in the box; offsets held from the fans-off steady model; the fans' own failure is not detected "
            "by the firmware (no tach); the critical limit is the protection")
        add("Box transient", "warm-up from cold at 150 A, fans on", f"sink reaches 90 % of {f['t_sink']:.0f} C after "
            f"{2.3 * R_SYS['fans'] * C_SINK / 60:.0f} min", "information", "INFO", "a 30 s fan-curve or a short run "
            "never sees the steady numbers above")
    firmware_limits(data, a.cabin)
    for tag, path_f, path_n in (("A", a.afans, a.anofan),):
        if path_f and path_n:
            dA = {air: {r["case"]: r for r in json.load(open(p))} for air, p in (("fans", path_f), ("nofan", path_n))}
            part_map(tag, dA, a.cabin)
    part_map("B", data, a.cabin)
    for r in RES:
        print(f"{r['verdict']:<5} [{r['group']}] {r['check']}: {r['value']} (limit {r['limit']})" + (f" - {r['note']}" if r['note'] else ""))
    cnt = {v: sum(r["verdict"] == v for r in RES) for v in ("PASS", "WARN", "FAIL", "INFO")}
    print("TOTAL", cnt)
    if a.json:
        json.dump(RES, open(a.json, "w"), indent=1)
    return 1 if cnt["FAIL"] else 0


def firmware_limits(data, cabin):
    """Board B's factory limits against the sensor -> hot-spot map of every modelled case."""
    warn, crit = board_b_limits()
    rows = [(air, r["case"], r["t_sensor_u6"] + cabin - 60.0, r["laminate_max"] - r["t_sensor_u6"], r["tj_max"] - r["t_sensor_u6"])
            for air in ("fans", "nofan") for r in data[air].values() if r.get("t_sensor_u6") is not None]
    if not rows:
        return
    d_lam = max(x[3] for x in rows)
    d_tj = max(x[4] for x in rows)
    add("Board B limits", "sensor -> hot-spot map (laminate - U6, Tj - U6) over the modelled cases",
        "; ".join(f"{c} {'fans' if a == 'fans' else 'no fans'}: U6 {t:.1f} C, +{dl:.1f} / +{dt:.1f} K" for a, c, t, dl, dt in rows),
        "information", "INFO", f"largest offsets: laminate +{d_lam:.1f} K, Tj +{d_tj:.1f} K")
    car = next((x for x in rows if x[0] == "fans" and x[1] == "car"), None)
    if car:
        add("Board B limits", f"no warning in normal use: U6 at the car loads, fans on, cabin {cabin:.0f} C, vs warn {warn} C",
            f"{car[2]:.1f} C", f"< {warn} C", "PASS" if car[2] < warn else "FAIL",
            f"critical-soon from {crit - 5} C, critical {crit} C: a {cabin + 10:.0f} C cabin adds 10 K")
    lam_at = crit + SENSOR_ERR + d_lam
    tj_at = crit + SENSOR_ERR + d_tj
    add("Board B limits", f"laminate / Tj when U6 reaches critical {crit} C (+{SENSOR_ERR:.0f} C sensor error, largest offset)",
        f"laminate {lam_at:.1f} C, Tj {tj_at:.1f} C", f"<= {LAMINATE_C:.0f} / {TJ_C:.0f} C",
        "PASS" if lam_at <= LAMINATE_C and tj_at <= TJ_C else "FAIL")
    # the UI's hot-spot offset (ui PdmThermal.cs) must cover this map: /pdm converts the hot-spot set with it
    cs = os.path.join(ROOT, "ui", "dingoConfig", "domain", "CustomPdm", "PdmThermal.cs")
    if os.path.exists(cs):
        ui = float(re.search(r"BoardBLaminateOffsetK = ([0-9.]+)", open(cs, encoding="utf-8").read()).group(1))
        ok = round(d_lam, 1) <= ui <= round(d_lam, 1) + 1.0
        add("Board B limits", "UI hot-spot offset (PdmThermal.BoardBLaminateOffsetK) vs the largest laminate offset of this map",
            f"UI {ui:.1f} K, map {d_lam:.1f} K (UI sensor limit = hot spot - {math.ceil(ui + SENSOR_ERR)} K)",
            "map <= UI <= map + 1 K", "PASS" if ok else "FAIL",
            "" if ok else "set the constant to the map value (and docs/system-verification.md, port_boards.py: the UI test ties them)")
    for name, rating in LOGIC_PARTS:
        t = crit + SENSOR_ERR
        add("Board B limits", f"{name} at the critical limit (logic area at the U6 reading + {SENSOR_ERR:.0f} C)",
            f"{t:.0f} C", f"<= {rating:.0f} C", "PASS" if t <= rating else ("FAIL" if rating < 100 else "WARN"),
            "" if t <= rating else f"would need critical <= {rating - SENSOR_ERR:.0f} C, which trips at the car loads "
            f"({car[2]:.1f} C) unless the part is a higher grade" if car else "")


def part_map(tag, data, cabin):
    """Every reported part against U6 over every modelled case of one board: the critical limit each one needs, the
    binding one, and the board's factory warn / critical (port_boards.py) against it (job hwtemp)."""
    lim = board_limits(tag)
    rows = []
    for air in ("fans", "nofan"):
        for r in data[air].values():
            u6 = r.get("t_sensor_u6")
            if u6 is None:
                continue
            offs = {"laminate": (r["laminate_max"] - u6, LAMINATE_C), "Tj": (r["tj_max"] - u6, TJ_C)}
            for ref, p in r.get("parts", {}).items():
                if ref in PART_RATING:
                    name, rating = PART_RATING[ref]
                    offs[name] = (p["t"] - u6, LIMIT_5V[0] if rating is None else rating)
            rows.append((air, r["case"], u6, offs))
    if not rows:
        return
    need = {}                                     # item -> (critical it allows, largest offset over U6)
    for _, _, _, offs in rows:
        for k, (d, rating) in offs.items():
            allow = rating - d - SENSOR_ERR
            prev = need.get(k, (float("inf"), float("-inf")))
            need[k] = (min(prev[0], allow), max(prev[1], d))
    bind = min(need, key=lambda k: need[k][0])
    add(f"Board {tag} limits (part map)", "largest offset over U6 of every reported part (all modelled cases) and the "
        "critical it allows (rating - offset - 1 C sensor error)",
        "; ".join(f"{k} +{v[1]:.1f} K -> <= {v[0]:.1f} C" for k, v in need.items()), "information", "INFO",
        f"binding: {bind}")
    if lim is None:
        add(f"Board {tag} limits (part map)", "factory warn / critical in port_boards.py", "none (stock 55 / 80)",
            "board's own limits", "FAIL", "board has a thermal model now: set DEFAULT_TEMP_WARN / _CRIT for it")
        return
    warn, crit = lim
    add(f"Board {tag} limits (part map)", f"factory critical {crit} C vs the binding part ({bind})",
        f"critical {crit} C, allowed <= {need[bind][0]:.1f} C", f"<= {need[bind][0]:.1f} C",
        "PASS" if crit <= need[bind][0] + 1e-9 else "FAIL")
    cs = os.path.join(ROOT, "ui", "dingoConfig", "domain", "CustomPdm", "PdmThermal.cs")
    if tag == "A" and os.path.exists(cs):      # board B: firmware_limits() checks its constant
        ui = float(re.search(r"BoardALaminateOffsetK = ([0-9.]+)", open(cs, encoding="utf-8").read()).group(1))
        lam = need["laminate"][1]
        ok = round(lam, 1) <= ui <= round(lam, 1) + 1.0
        add(f"Board {tag} limits (part map)", "UI hot-spot offset (PdmThermal.BoardALaminateOffsetK) vs the largest laminate "
            "offset of this map", f"UI {ui:.1f} K, map {lam:.1f} K (UI sensor limit = hot spot - {math.ceil(ui + SENSOR_ERR)} K)",
            "map <= UI <= map + 1 K", "PASS" if ok else "FAIL", "" if ok else "set the constant to the map value")
    car = [x for x in rows if x[0] == "fans" and x[1] in ("car", "drive")]
    for air, case, u6, _ in car:
        add(f"Board {tag} limits (part map)", f"no warning in normal use: U6 at {case}, fans on, cabin {cabin:.0f} C, "
            f"vs warn {warn} C", f"{u6 + cabin - 60.0:.1f} C", f"< {warn} C", "PASS" if u6 + cabin - 60.0 < warn else "FAIL")


if __name__ == "__main__":
    sys.exit(main())
