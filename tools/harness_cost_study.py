"""Harness cost study: relay route vs PDM route for the ST185 (worker harnesscost, 2026-11-23).

Dan's brief (2026-11-23 08:54-08:56): find the point where the PDM drastically cuts the length and the work of the
st185 harness plans; every relay new or from the on-hand list (the OEM relays are too old); all wiring in Raychem
DR-25 with moulded boots / transitions; labour, tools, box builds; the ECU's loads count the same on both routes.

Reads (read only, never written): a clone of st185-link-ecu-config (`--st185`, the commit is printed and written into
every output): docs/harness/MASTER-wirelist.csv and its layout tree (docs/harness/tools/ST185-harness.layout.json via
build_drawings.Harness), docs/sourcing/PROJECT-BOM.csv, cad/fusebox/rev8/fusebox-parts-*.csv. In this repo:
harness/enclosure-wire-list.csv (the PDM box inside).
Writes: docs/harness-cost/*.dummy.csv (line 1 names the source and commit) and docs/diagrams/harness-breakpoint.png.

Method (cited in docs/pdm-vs-relays.md):
- Relay route = the st185 harness and boxes as designed + new relays where st185 keeps an OEM relay or module.
- PDM route after k moves = the relay route minus the relay-side wires / seats / parts of moves 1..k, plus the PDM
  wires of those moves, plus the PDM itself (boards, enclosure, X1 / X2, feed, CAN, IN5 / IN16).
- Every wire is routed on the st185 layout tree (same end allowances); new PDM wires start at node GB_LOGIC (the PDM
  sits in the glove box next to LOGIC: ASSUMED, memory: "mounted inside the cabin").
- Bundle OD per segment D = 1.2 * sqrt(sum d_i^2) (st185 build_project_bom.py; Twisted_Builds_Harness_Designer
  PROJECT_PLAN 8.2: D = sqrt(sum d^2 / k), k = 0.70 -> 1.195). DR-25 size = smallest with expanded ID >= 1.25 D (HP
  Academy: shrink at least 20 %) and recovered ID <= D (TBHD 8.3: warn if recovered > D, i.e. loose).
"""
import argparse, collections, csv, math, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# ---------------------------------------------------------------------------------------------- prices and times
# Wire USD per ft. Source: st185 PROJECT-BOM (Custom Connector Kits TXL per ft, 2026-11-08) for 16 / 18 / 10 AWG;
# the rest ASSUMED (CCK sells no other TXL red sizes, checked 2026-11-23; 20 AWG = the CCK 22 AWG $0.39 price).
WIRE_FT = {"20": 0.40, "18": 0.50, "16": 0.42, "14": 0.60, "12": 0.75, "10": 0.95, "8": 1.60, "6": 2.40, "4": 3.20,
           "2": 4.00, "1/0": 5.50, "": 2.50}
WIRE_FT_SRC = {"18": "st185", "16": "st185", "10": "st185"}
OD = {20: 1.57, 18: 1.85, 16: 2.11, 14: 2.41, 12: 2.97, 10: 3.81, 8: 5.08, 6: 6.6, 4: 8.0, 2: 9.8}   # st185 OD table + ASSUMED 6/4/2
# DR-25 (expanded ID, recovered ID mm, USD per ft, source). KSV Looms yellow label (st185 bom-links 2026-10-20 and
# products.json 2026-11-23); 1-1/2 in: KSV white label (only one listed); 2 in: ASSUMED.
DR25 = [("DR-25-1/8-0", 3.2, 1.6, 1.69, "KSV 2026-11-23"), ("DR-25-3/16-0", 4.8, 2.4, 1.69, "st185 / KSV 2026-10-20"),
        ("DR-25-1/4-0", 6.4, 3.2, 1.71, "st185 / KSV"), ("DR-25-3/8-0", 9.53, 4.8, 3.30, "st185 / KSV"),
        ("DR-25-1/2-0", 12.7, 6.4, 4.34, "st185 / KSV"), ("DR-25-3/4-0", 19.0, 9.5, 4.57, "st185 / KSV"),
        ("DR-25-1-0", 25.4, 12.8, 6.12, "st185 / KSV"), ("DR-25-1-1/2-0", 38.1, 19.0, 14.11, "KSV white label 2026-11-23"),
        ("DR-25-2-0", 50.8, 25.4, 20.00, "ASSUMED")]
BOOT_SMALL, BOOT_LARGE = 14.00, 23.40     # KSV 202A121-25/225-0 / 202A132-25/225-0 (adhesive lined), 2026-11-23
EPOXY = 40.50                              # KSV ResinTech RT125 cartridge, 2026-11-23; ASSUMED 25 transitions each
HOURLY = 35.0                              # ASSUMED value of Dan's hour (hours are also shown alone)

# Minutes per operation. HooHA "How long does wire harness assembly take" (manual figures): crimp 55 s incl. strip and
# check, insert ~70 s per pin, +30 s per loose seal, solder joint ~100 s, manual cut / strip 200-300 wires per hour,
# manual continuity test 150 circuits in 45-60 min. The rest ASSUMED (no time study found).
MIN = {"cut": 1.0,        # cut, strip both ends, fit a marker (12-18 s prep + ASSUMED 30 s marker + handling)
       "crimp": 0.9, "insert": 1.2, "seal": 0.5, "solder": 1.7 + 0.5,     # + 0.5 ASSUMED heat-shrink over the joint
       "oem": (1.7 + 0.5) * 2,   # in-car tie-in onto a factory lead: solder + sleeve, x2 for working in the car (ASSUMED)
       "ring": 2.0,       # heavy ring / tubular lug (ASSUMED)
       "splice": 2.2,     # one splice joint (solder + sleeve), plus 0.3 per wire end into it
       "test": 0.4,       # per wire (45-60 min / 150 circuits)
       "dr25_piece": 5.0, "dr25_m": 4.0,      # ASSUMED
       "boot": 8.0,       # boot or transition incl. epoxy (ASSUMED; cure time not labour)
       "seg_route": 5.0, "conn_mate": 10.0, "box_mount": 30.0}           # install in the car (ASSUMED)


def git_head(path):
    try:
        return subprocess.run(["git", "-C", path, "log", "-1", "--format=%h"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------------------------- parts and seats
def P(desc, pn, qty, unit, src, minutes=0.0):
    """A part line: qty x unit USD (0 for on hand), its source, and the labour minutes it adds beyond its wire ends."""
    return {"desc": desc, "pn": pn, "qty": qty, "unit": unit, "src": src, "min": minutes}


ST = "st185 PROJECT-BOM / fusebox-parts (Digi-Key / CCK / Waytek 2026-10-20..11-14)"
CCK = "customconnectorkits.com products.json 2026-11-23"


def micro_seat(name, pn, price, owned=True):
    # LOGIC micro relay seat: relay (on hand = $0) + its 2 coil (280919-2) + 2 load (42281-1) receptacles; the receptacle
    # crimps are the ends of the master wires that land on it, so only the relay push-in is extra labour.
    return [P("%s relay %s (%s)" % (name, pn, "on hand" if owned else "buy"), pn, 1, 0.0 if owned else price, ST, 0.5),
            P("%s receptacles 280919-2 x2 + 42281-1 x2" % name, "280919-2/42281-1", 1, 0.44, ST)]


def fuse_seat(name):
    # LOGIC mini fuse seat: ATM fuse, 2 MCP 2.8 receptacles, input jumper (60 mm wire + ring lug 320554 + M4 bolt +
    # spring washer + PEM nut). Labour: the jumper (cut 1, 2 crimps, insert, bolt, PEM press) = 5.0 min, fuse 0.3 min.
    return [P("%s fuse seat (ATM fuse, 2 x MCP 2.8, jumper, lug, M4 hardware, PEM)" % name, "ATM+1-968849-1", 1, 1.93, ST, 5.3)]


AMI_SEAT = P("POWER AMI seat (AMI-30, 2R5 lug, M5 bolts / nuts, PEM stud, C-strap share)", "AMI-30", 1, 10.63, ST, 6.0)
HOLDER = [P("GEP FRH-A12 holder (holds up to 2 micro relays, GEP drawing via st185 BOM)", "FRH-A12", 1, 8.99, CCK),
          P("FRH-A12-T TPA", "FRH-A12-T", 1, 0.65, CCK), P("FRH-A12-C cover", "FRH-A12-C", 1, 5.99, CCK),
          P("FRH-A12-MB-B1 bracket", "FRH-A12-MB-B1", 1, 1.59, CCK, MIN["box_mount"])]


def W(wid, a, ka, b, kb, awg, note=""):
    """A new wire: ends a / b are a layout node ('@NODE') or an st185 id placed on the layout; kinds: pdm (X1 / X2 harness
    contact: crimp + insert), stud (ring lug on a PDM stud), oem (in-car tie-in onto a factory lead), splice (into an
    existing splice), conn (contact into an existing st185 housing), term (soldered flying lead), hold (FRH-A12
    Metri-Pack 280 terminal: crimp + insert + seal), box (receptacle in an st185 box), lug (small ring on a bus bolt)."""
    return {"wid": wid, "a": a, "ka": ka, "b": b, "kb": kb, "awg": str(awg), "note": note}


def relay_in_holder(name, node, gauges, relay_price=3.79, relay_pn="301-1A-C-R1-U03-12VDC"):
    """Relay route only: a new relay where st185 keeps an old OEM one (Dan: OEM relays too old), in an FRH-A12 holder
    beside the OEM relay seat, spliced into the 4 factory socket leads (pigtails; ASSUMED retrofit)."""
    parts = [P("%s: new relay %s (35 A micro, Song Chuan)" % (name, relay_pn), relay_pn, 1, relay_price, CCK, 0.5),
             P("%s: Metri-Pack 280 terminals 12129409-L x%d" % (name, len(gauges)), "12129409-L", len(gauges), 0.26, CCK)]
    wires = [W("r_%s_%d" % (name, i), "@" + node, "hold", "@" + node, "oem", g, "pigtail to the factory socket lead")
             for i, g in enumerate(gauges)]
    return parts, wires


# ---------------------------------------------------------------------------------------------- the moves
# Each move takes loads off relays and puts them on PDM outputs (docs/st185-car-config.dummy.md). `remove` = st185
# master wires that only the relay route has; `add` = the PDM route's wires; `seats` = st185 box / holder parts that go;
# `relay_only` = the new relays the relay route needs because the OEM ones are too old (Dan 2026-11-23), which the PDM
# route never builds; `boxes` = boxes or holders that disappear with this move.
X1, X2, STUD = "@PDM#X1", "@PDM#X2", "@PDM#STUD"     # all three sit at layout node GB_LOGIC
MOVES = []

_popup_parts, _popup_wires = relay_in_holder("popup", "R8", ["16"] * 5 + ["16"] * 5, 4.69, "301-1C-C-R1-U01-12VDC")
_popup_parts[0]["qty"] = 2
_popup_parts[1].update(qty=10, desc="popup: Metri-Pack 280 terminals 12129409-L x10")
MOVES.append(dict(
    id="M1", name="Front lamps: low, high, DRL, pop-ups", loads=[1, 2, 3, 12, 13],
    outputs="A1 OUT1-3, A2 OUT4-5", inputs="IN1 IN2 IN3 IN11-14 IN23",
    remove=["w_hl_cp", "w_hl_30_cp", "w_hl_86_cp", "w_hr_86_cp", "w_hl_on_cp", "w_hr_on_cp", "w_hl_85_cp",
            "w_head_coil_cp", "w_hl_low",
            "w_drl_85_cp", "w_drl_sw_cp", "w_r8_up_cp", "w_r8_d1_a_cp", "w_r8_d1_k_cp", "w_r8_d2_a_cp", "w_r8_d2_k_cp",
            "w_drl_87_cp", "w_drlc_86_cp", "w_drlc_85_cp", "w_pod_85_cp", "w_pod_87_cp", "w_pmu_drl",
            "w_pmu_rtr", "w_rtr_r3_4", "w_rtr_r2_4", "w_rtr_r2_2", "w_rtr_r3_2", "w_rtr_close", "w_rtr_open",
            "w_rtr_close_r2", "w_rtr_close_r3", "w_rtr_open_r2", "w_rtr_open_r3"],
    add=[W("p_lo", X1, "pdm", "SP-HL-ON", "splice", 14), W("p_hi", X1, "pdm", "SP-HR-HI", "splice", 14),
         W("p_drl", X1, "pdm", "SP-DRL", "splice", 16), W("p_in_drlsw", X2, "pdm", "DRL-SW", "conn", 20),
         W("p_in_head", "@JB1", "oem", X2, "pdm", 20, "IE1-2 R-Y"), W("p_in_high", "@JB1", "oem", X2, "pdm", 20, "IE1-18 R-W"),
         W("p_pod_lh", X1, "pdm", "SP-RTR-R2-4", "splice", 14), W("p_pod_rh", X1, "pdm", "SP-RTR-R3-4", "splice", 14),
         W("p_lim_lh_up", "@RTR_LH", "oem", X2, "pdm", 20), W("p_lim_lh_dn", "@RTR_LH", "oem", X2, "pdm", 20),
         W("p_lim_rh_up", "@RTR_RH", "oem", X2, "pdm", 20), W("p_lim_rh_dn", "@RTR_RH", "oem", X2, "pdm", 20),
         W("p_in_off", "@COLUMN", "oem", X2, "pdm", 20, "light switch OFF contact")],
    seats=micro_seat("K-HL", "5-1393292-8", 3.66) + micro_seat("K-HR", "5-1393292-8", 3.66)
    + micro_seat("K-DRL", "4-1904124-2", 5.05) + micro_seat("K-POD", "4-1904124-3", 4.54)
    + fuse_seat("HL 15 A") + fuse_seat("HR 15 A") + fuse_seat("DRL 7.5 A") + [AMI_SEAT]
    + [dict(p, lump=True) for p in [P("RLY-DRL relay 301-1C (B5)", "301-1C-C-R1-U01-12VDC", 1, 4.69, ST, 0.5),
                                    P("RLY-DRL terminals 12129409-L x4", "12129409-L", 4, 0.26, ST)] + HOLDER
       + [P("D1 / D2 inline diodes DT04-2P-RT01 (MUR460)", "DT04-2P-RT01", 2, 8.99, ST)]],
    relays=5, fuses=4,
    relay_only=dict(parts=_popup_parts + HOLDER + [P("pop-up relay circuit design (replaces R8; ASSUMED)", "-", 1, 0.0, "ASSUMED", 90)],
                    wires=_popup_wires, relays=2, fuses=0),
    boxes=["RLY-DRL holder B5", "R8 retract relay (relay route: its new 2-relay holder)", "POWER AMI OUT-2 (RTR 30 A)",
           "LOGIC: 4 of 9 relay seats, 3 fuse seats"]))

MOVES.append(dict(
    id="M2", name="Horns", loads=[5], outputs="A1 OUT5", inputs="IN4",
    remove=["w_horn_85_cp", "w_horn_30_cp", "w_horn_86_cp", "w_pmu_horn_cp"],
    add=[W("p_horn", X1, "pdm", "SP-HORN", "splice", 14), W("p_in_horn", "@JB1", "oem", X2, "pdm", 20, "IE1-19")],
    seats=micro_seat("K-HORN", "4-1904124-3", 4.54), relays=1, fuses=0,
    relay_only=dict(parts=[], wires=[], relays=0, fuses=0), boxes=["LOGIC: K-HORN seat"]))

MOVES.append(dict(
    id="M3", name="Turn signals + hazards", loads=[9, 11], outputs="A2 OUT1, OUT3", inputs="IN8 IN9 IN10",
    remove=["w_haz_cp", "w_hz_cp"],
    add=[W("p_turn_l", X1, "pdm", "@COLUMN", "oem", 18), W("p_turn_r", X1, "pdm", "@COLUMN", "oem", 18),
         W("p_in_tl", "@COLUMN", "oem", X2, "pdm", 20), W("p_in_tr", "@COLUMN", "oem", X2, "pdm", 20),
         W("p_in_haz", "@CLUSTER", "oem", X2, "pdm", 20),
         W("p_turn_com", "@COLUMN", "oem", "@COLUMN", "oem", 20, "turn switch common to ground (ASSUMED)"),
         W("p_haz_rw", "@CLUSTER", "oem", "@CLUSTER", "oem", 20, "hazard switch rewire (ASSUMED)")],
    seats=fuse_seat("HZ 15 A"), relays=0, fuses=1,
    relay_only=dict(parts=[P("new LED flasher CF13JL-02 (st185 BOM line, unpriced there; ASSUMED $15)", "CF13JL-02", 1, 15.0, "ASSUMED", 2)],
                    wires=[], relays=1, fuses=0),
    boxes=["OEM flasher (its new CF13JL-02)", "LOGIC: HZ fuse seat"]))

_tail_parts, _tail_wires = relay_in_holder("tail", "JB1", ["18"] * 4)
MOVES.append(dict(
    id="M4", name="Tail / park lamps", loads=[14, 15], outputs="A2 OUT6, OUT7", inputs="IN7",
    remove=["w_clr"],
    add=[W("p_park", X1, "pdm", "SP-CLR", "splice", 16), W("p_tail", X1, "pdm", "@JB1", "oem", 16, "TAIL rear / licence / dash"),
         W("p_in_tail", "@JB1", "oem", X2, "pdm", 20, "light switch TAIL (relay coil lead)")],
    seats=[], relays=0, fuses=0,
    relay_only=dict(parts=_tail_parts + [P("relay retrofit design share (ASSUMED)", "-", 1, 0.0, "ASSUMED", 30)],
                    wires=_tail_wires, relays=1, fuses=0, holder="B1"),
    boxes=["OEM taillight relay (its new relay)"]))

MOVES.append(dict(
    id="M5", name="CAN-Lambda, CSB3, cluster feeds", loads=[21, 7, 8], outputs="B OUT5, A1 OUT7, OUT8", inputs="IN16 (fixed)",
    remove=["w_k_on_86_cp", "w_lam12_cp", "w_csb12", "w_dev_clu"],
    add=[W("p_lam", X1, "pdm", "DRB102-CABIN", "conn", 14), W("p_csb", X1, "pdm", "CSB3", "conn", 20),
         W("p_dev", X1, "pdm", "T-CLUSTER-PWR", "term", 16)],
    seats=micro_seat("K-ON", "6-1419137-4", 4.49) + [P("K-ON 85 ground ring 320572", "320572", 1, 0.30, ST, 3)]
    + fuse_seat("LAM 10 A") + fuse_seat("CSB 5 A") + fuse_seat("DEV 5 A"), relays=1, fuses=3,
    relay_only=dict(parts=[], wires=[], relays=0, fuses=0), boxes=["LOGIC: K-ON seat, 3 fuse seats"]))

_defog_parts, _defog_wires = relay_in_holder("defog", "JB1", ["14", "14", "18", "18"])
MOVES.append(dict(
    id="M6", name="Rear defogger", loads=[20], outputs="B OUT4 (stud)", inputs="IN22",
    remove=[],
    add=[W("p_defog", STUD, "stud", "@JB1", "oem", 12, "defogger relay 87 lead"), W("p_in_defog", "@CLUSTER", "oem", X2, "pdm", 20)],
    seats=[], relays=0, fuses=0,
    relay_only=dict(parts=_defog_parts + [P("relay retrofit design share (ASSUMED)", "-", 1, 0.0, "ASSUMED", 30)],
                    wires=_defog_wires, relays=1, fuses=0, holder="B1"),
    boxes=["OEM defogger relay (its new relay)"]))

_win_parts, _win_wires = relay_in_holder("windows", "JB1", ["12", "12", "18", "18"])
_win_parts[1].update(unit=0.30, src="ASSUMED (Metri-Pack 280 12-10 AWG terminal)")
MOVES.append(dict(
    id="M7", name="Power windows", loads=[17], outputs="B OUT1 (stud)", inputs="IN16 (fixed)",
    remove=[],
    add=[W("p_win", STUD, "stud", "@JB1", "oem", 10, "power main relay 87 lead")],
    seats=[], relays=0, fuses=0,
    relay_only=dict(parts=_win_parts + [P("relay retrofit design share (ASSUMED)", "-", 1, 0.0, "ASSUMED", 30)],
                    wires=_win_wires, relays=1, fuses=0, holder="B2"),
    boxes=["OEM power main relay (its new relay)"]))

MOVES.append(dict(
    id="M8", name="Stop lamps", loads=[4], outputs="A1 OUT4", inputs="IN6",
    remove=[], add=[W("p_stop", X1, "pdm", "@PEDAL", "oem", 16, "lamp side of the cut switch output"),
                    W("p_in_stop", "@PEDAL", "oem", X2, "pdm", 20, "stop switch output")],
    seats=[], relays=0, fuses=0, relay_only=dict(parts=[], wires=[], relays=0, fuses=0), boxes=[]))

MOVES.append(dict(
    id="M9", name="Back-up lamps", loads=[22], outputs="B OUT6", inputs="IN24",
    remove=["w_rev_lamps"],
    add=[W("p_rev", X1, "pdm", "@IG2C", "oem", 14, "IG2-13"), W("p_in_rev", "SP-REV", "splice", X2, "pdm", 20)],
    seats=[], relays=0, fuses=0, relay_only=dict(parts=[], wires=[], relays=0, fuses=0), boxes=[]))

MOVES.append(dict(
    id="M10", name="Wipers + washer", loads=[23, 24, 16], outputs="B OUT7, OUT8, A2 OUT8", inputs="IN17-21",
    remove=["w_wip_lo", "w_wip_hi", "w_wip_park", "w_wash_pos"],
    add=[W("p_wip_lo", X1, "pdm", "@WIPER", "oem", 14), W("p_wip_hi", X1, "pdm", "@WIPER", "oem", 14),
         W("p_in_park", "@WIPER", "oem", X2, "pdm", 20), W("p_wash", X1, "pdm", "@WASH", "oem", 16)]
    + [W("p_in_w%d" % i, "@COLUMN", "oem", X2, "pdm", 20) for i in range(4)]
    + [W("p_wip_com", "@COLUMN", "oem", "@COLUMN", "oem", 20, "switch common to ground (ASSUMED)")],
    seats=[], relays=0, fuses=0, relay_only=dict(parts=[], wires=[], relays=0, fuses=0), boxes=[]))

HOLDERS = {"B1": ["M4", "M6"], "B2": ["M7"]}    # body relay holders of the relay route and the moves that empty them


# Both routes (counted the same): the OEM heater and starter relays (ECU / interlock loads, Dan: OEM relays too old)
# move into the vacant POWER seats R1 / R3 (st185 sot/fuse-relay-map.csv: "was k_htr", "was k_str") as on-hand F7
# relays 1-1393304-0 (te-on-hand-bom.csv: 2 on hand), wired to the R/B No.4 leads (ASSUMED 1 x 10 + 2 x 18 AWG each).
COMMON_EXTRA = dict(
    parts=[P("heater + starter relays 1-1393304-0 (on hand)", "1-1393304-0", 2, 0.0, "st185 te-on-hand-bom.csv", 1.0),
           P("their seat receptacles 280756-4 x4 + 42281-1 x4", "280756-4/42281-1", 1, 2.00, ST)],
    wires=[W("c_htr87", "K-EFI", "box", "@RHKICK", "oem", 10), W("c_htr86", "K-EFI", "box", "@RHKICK", "oem", 18),
           W("c_htr85", "K-EFI", "box", "@RHKICK", "oem", 18), W("c_str87", "K-EFI", "box", "@RHKICK", "oem", 10),
           W("c_str86", "K-EFI", "box", "@RHKICK", "oem", 18), W("c_str85", "K-EFI", "box", "@RHKICK", "oem", 18)],
    relays=2)

# The PDM itself (built once, the first move needs all of it: the enclosure holds three boards).
PDM_FIXED = dict(
    parts=[P("Boards A1, A2, B assembled (JLCPCB / PCBWay) with spares: $650-850", "boards", 1, 750.0,
             "docs/order-checklist.md order, coordinator figure (first estimate)"),
           P("Enclosure: machined sink + lid, printed parts, fasteners, seals: $80-200", "enclosure", 1, 140.0, "ASSUMED (first estimate)"),
           P("Box internal wiring, fans: $20-40", "box-internal", 1, 30.0, "ASSUMED (first estimate)"),
           P("USB-CAN adapter for setup: $0-40", "usb-can", 1, 20.0, "ASSUMED (the RealDash CANable may do)"),
           P("X1 harness plug HD36-24-21PN + X2 plug HDP26-24-47PE-L015 (on hand)", "HD36/HDP26", 2, 0.0, "st185 te-on-hand-bom.csv"),
           P("X1 / X2 boots HD30-24BT-BK (on hand, 5)", "HD30-24BT-BK", 2, 0.0, "st185 te-on-hand-bom.csv"),
           P("PDM feed fuse AMI-100 + single AMI holder", "AMI-100", 1, 17.30, "AMI price st185 (Waytek $5.30) + holder ASSUMED $12"),
           P("Feed / ground lugs (2 x Klauke 3R5MS, 2 x M6 ring)", "3R5MS", 4, 1.10, ST),
           P("Y transition at the glove-box PDM breakout 382A023-25-0", "382A023-25-0", 1, 46.90, ST, MIN["boot"]),
           P("PDM design of the harness changes (ASSUMED)", "-", 1, 0.0, "ASSUMED", 240),
           P("PDM setup: bench + car, UI config (first estimate 4-6 h)", "-", 1, 0.0, "first estimate", 300),
           P("PDM mechanical assembly (sink, boards, lid, fans; ASSUMED)", "-", 1, 0.0, "ASSUMED", 240),
           P("PDM mounted in the glove box", "-", 1, 0.0, "ASSUMED", MIN["box_mount"])],
    wires=[W("f_bat", "T-PWR-POS-BAT", "ring", STUD, "stud", 6, "PDM feed"), W("f_gnd", "T-PWR-NEG-BAT", "ring", STUD, "stud", 6),
           W("f_in5", "T-LOG-BUS2", "lug", X2, "pdm", 20, "IN5 = K-EFI 87 Bus 2"),
           W("f_in16", "@JB1", "oem", X2, "pdm", 20, "IN16 ignition J/B 1H-7"),
           W("f_canh", X2, "pdm", "@CANJ", "oem", 20, "CAN H into the CAN joins"), W("f_canl", X2, "pdm", "@CANJ", "oem", 20),
           W("f_sgnd", X2, "pdm", "SP-CABIN-GND", "splice", 20)],
    relays=0, fuses=1)


# ---------------------------------------------------------------------------------------------- the engine
class Study:
    def __init__(self, st185):
        sys.path.insert(0, os.path.join(st185, "docs", "harness", "tools"))
        import build_drawings as BD   # st185's own model: layout tree, routes, OD table (read only)
        self.BD, self.st185, self.commit = BD, st185, git_head(st185)
        self.H = BD.Harness(BD.own_harnesses()[0])
        self.L = self.H.layout
        self.master = [r for r in self.H.wires if not BD.is_integral(r)]
        self.by_id = {r["wire_id"]: r for r in self.master}
        self.where = {}
        for r in self.master:
            for s in ("from", "to"):
                n = self.H.place(r, s)
                if n:
                    self.where.setdefault(r[s + "_conn"], n)
        self.bom = list(csv.DictReader(open(os.path.join(st185, "docs", "sourcing", "PROJECT-BOM.csv"), encoding="utf-8-sig")))
        self.boxes = {b: list(csv.DictReader(open(os.path.join(st185, "cad", "fusebox", "rev8", "fusebox-parts-%s.csv" % b),
                                                  encoding="utf-8-sig"))) for b in ("power", "logic", "battrelay")}
        self.encl = list(csv.DictReader(open(os.path.join(REPO, "harness", "enclosure-wire-list.csv"), encoding="utf-8-sig")))
        for m in MOVES:
            for w in m["remove"]:
                assert w in self.by_id, "move %s: %s is not in the st185 master" % (m["id"], w)

    def node(self, x):
        if x.startswith("@"):
            return "GB_LOGIC" if x.startswith("@PDM") else x[1:]
        n = self.L["place"].get(x) or self.where.get(x)
        assert n, "no layout node for %s" % x
        return n

    def route_new(self, w):
        a, b = self.node(w["a"]), self.node(w["b"])
        p = self.H.path(a, b)
        end, spl = self.L.get("end_allowance_mm", 100), self.L.get("splice_allowance_mm", 25)
        mm = sum(self.H.seg_len(x, y) for x, y in zip(p, p[1:])) + sum(spl if k == "splice" else end for k in (w["ka"], w["kb"]))
        return p, mm

    @staticmethod
    def kind_of(r, s):
        t, tp = r[s + "_type"], (r[s + "_terminal_pn"] or "").lower()
        if t == "connector":
            return "screw" if "screw" in tp else ("solderpin" if "solder" in tp else "conn")
        if t == "terminal":
            return "term" if ("flying" in tp or "solder" in tp) else "ring"
        return {"OEM": "oem", "splice": "splice", "diode": "term", "resistor": "term", "cable screen": "term"}.get(t, "")


    # ------------------------------------------------------------------ one configuration: k moves on the PDM
    def config(self, k):
        done = MOVES[:k]
        gone = {w for m in done for w in m["remove"]}
        wires = []
        for r in self.master:
            if r["wire_id"] in gone:
                continue
            p, mm = self.H.route(r)
            wires.append(dict(id=r["wire_id"], awg=r["gauge_awg"], mm=mm or num(r["est_length_mm"]), path=p or [],
                              kinds=(self.kind_of(r, "from"), self.kind_of(r, "to")), cable=r["cable"],
                              ends=(r["from_conn"], r["to_conn"]), types=(r["from_type"], r["to_type"]),
                              housings=(r["from_housing_pn"], r["to_housing_pn"]), src="st185 master"))
        new = list(COMMON_EXTRA["wires"])
        parts = [dict(p, group="common: new heater / starter relays") for p in COMMON_EXTRA["parts"]]
        relays = 15 + COMMON_EXTRA["relays"]     # st185: POWER 3, K-EPS 1, LOGIC 9, K-FP 1, RLY-DRL 1 (+2 common)
        fuses = 10 + 20 + 1                       # POWER AMI 10, LOGIC ATM 20, BATTRELAY FP 1 (OEM J/B fuses not counted)
        boxes_gone, holders = [], {"B1", "B2"}
        for m in MOVES:
            if m in done:
                new += m["add"]
                relays -= m["relays"]
                fuses -= m["fuses"]
                boxes_gone += m["boxes"]
            else:
                ro = m["relay_only"]
                new += ro["wires"]
                parts += [dict(p, group="relay route only: " + m["name"]) for p in ro["parts"]]
                parts += [dict(p, group=("st185 harness parts: " if p.get("lump") else "st185 box seats: ") + m["name"])
                          for p in m["seats"]]
                relays += ro["relays"]
                fuses += ro["fuses"]
        for h, ms in HOLDERS.items():
            if all(any(d["id"] == x for d in done) for x in ms):
                holders.discard(h)
                boxes_gone.append("relay holder %s (relay route only)" % h)
        for h in sorted(holders):
            parts += [dict(p, group="relay route only: body holder " + h) for p in HOLDER]
        if k:
            new += PDM_FIXED["wires"]
            parts += [dict(p, group="PDM") for p in PDM_FIXED["parts"]]
            fuses += PDM_FIXED["fuses"]
        for w in new:
            p, mm = self.route_new(w)
            wires.append(dict(id=w["wid"], awg=w["awg"], mm=mm, path=p, kinds=(w["ka"], w["kb"]), cable="",
                              ends=(w["a"], w["b"]), types=("new", "new"), housings=("", ""), src="new"))
        return dict(k=k, wires=wires, parts=parts, relays=relays, fuses=fuses, boxes_gone=boxes_gone,
                    pdm=bool(k))

    # ------------------------------------------------------------------ sleeving per segment
    def sleeving(self, cfg):
        seg, sq = collections.Counter(), collections.Counter()
        cab_seen = set()
        for w in cfg["wires"]:
            if not w["path"]:
                continue
            for a, b in zip(w["path"], w["path"][1:]):
                key = tuple(sorted((a, b)))
                seg[key] += 1
                if w["cable"]:
                    if (w["cable"], key) in cab_seen:
                        continue
                    cab_seen.add((w["cable"], key))
                    sq[key] += self.BD.CABLE_OD ** 2
                else:
                    g = w["awg"]
                    sq[key] += OD.get(int(g), 1.6) ** 2 if g.isdigit() else (11.0 ** 2 if g == "1/0" else 1.6 ** 2)
        rows = []
        for a, b, mm in self.L["segments"]:
            key = tuple(sorted((a, b)))
            if not seg[key] or mm <= 0:        # a zero-length layout link (a node drawn twice) needs no tubing
                continue
            D = 1.2 * math.sqrt(sq[key])
            pick = next((d for d in DR25 if d[1] >= 1.25 * D and d[2] <= D), None)
            ok = pick is not None
            if not ok:
                pick = next((d for d in DR25 if d[1] >= 1.25 * D), DR25[-1])
                ok = "loose (recovered > OD)" if pick[2] > D else "tight: expanded < 1.25 x OD (split the bundle)"
            m = mm * 1.10 / 1000.0
            rows.append(dict(seg="%s-%s" % key, mm=mm, wires=seg[key], od=round(D, 1), pn=pick[0] + "-SP",
                             exp=pick[1], rec=pick[2], shrink_ok="yes" if ok is True else ok,
                             ratio=round(pick[1] / D, 2), m=round(m, 2), usd=round(m * 3.2808 * pick[3], 2), src=pick[4]))
        return rows

    # ------------------------------------------------------------------ the st185 fuse boxes as designed
    def box_build(self):
        cost, mins, lines = 0.0, 0.0, []
        for b, rows in self.boxes.items():
            c = m = 0.0
            for r in rows:
                q, g, it = num(r["qty_need"]), r["group"], r["item"]
                usd = num(r["line_usd"])
                if not usd and r["buy"] not in ("", "0") and g.startswith("Relay"):
                    usd = num(r["buy"]) * (4.49 if "6-1419137-4" in r["part_number"] else 8.22)   # PROJECT-BOM / ASSUMED
                c += usd
                if g == "Printed":
                    m += 30 * q
                elif g == "Copper":
                    m += q * 1.0 if ("PEM" in r["part_number"] or "clinch" in it.lower()) else 45
                elif g in ("Fasteners", "Mounting"):
                    m += 0.5 * q
                elif g == "Fuses":
                    m += 0.3 * q
                elif g.startswith("Relay"):
                    m += 0.5 * q
                elif g == "Terminals":
                    m += 0.0 if "receptacle" in it.lower() else 10     # receptacle crimps = wire ends; RNF sleeve stick 10 min
                elif g == "Lugs":
                    m += MIN["ring"] * q
                elif g == "Box wiring":
                    pcs = [int(x) for x in it.replace(",", " ").split() if x.isdigit()]
                    m += 3.0 * (pcs[0] if pcs else q)
                elif g == "Jumpers":
                    m += 1.0 * q if "lug" in it.lower() else (0.5 * q if ("bolt" in it.lower() or "washer" in it.lower()) else 5)
            m += 15 + MIN["box_mount"]      # bench check + mount in the car (ASSUMED)
            lines.append((b, round(c, 2), round(m / 60, 2)))
            cost, mins = cost + c, mins + m
        return cost, mins, lines

    def harness_lump(self):
        """PROJECT-BOM 'Wire harness' parts other than wire, cable, DR-25, transitions, markers and the lines this study
        prices itself (same on both routes): need qty x unit price, and the count of unpriced lines."""
        skip = ("J1128-", "M22759", "55A", "BC-", "DR-25", "301A", "342A", "382A", "462A", "TMS-SCE", "12129409-L",
                "DT04-2P-RT01", "FRH-A12", "301-1C-C-R1", "CF13JL")
        usd, unpriced = 0.0, 0
        for r in self.bom:
            if r["section"] != "Wire harness" or r["part_number"].startswith(skip):
                continue
            if r["unit_price_usd"]:
                usd += num(r["qty_needed"]) * num(r["unit_price_usd"])
            else:
                unpriced += 1
        trans = [(r["part_number"], num(r["qty_needed"]), num(r["unit_price_usd"])) for r in self.bom
                 if r["section"] == "Wire harness" and r["part_number"][:4] in ("301A", "342A", "382A", "462A")]
        return usd, unpriced, trans


    # ------------------------------------------------------------------ everything counted for one configuration
    END_MIN = {"conn": MIN["crimp"] + MIN["insert"], "pdm": MIN["crimp"] + MIN["insert"], "box": MIN["crimp"] + MIN["insert"],
               "hold": MIN["crimp"] + MIN["insert"] + MIN["seal"], "ring": MIN["ring"], "lug": MIN["crimp"] + 0.5,
               "stud": MIN["ring"] + 0.5, "term": MIN["solder"], "solderpin": MIN["solder"], "screw": 1.0,
               "oem": MIN["oem"], "splice": 0.3}
    END_USD = {"pdm": 0.0, "oem": 0.30, "stud": 0.40, "lug": 0.40}   # X2 pins priced below; ATUM piece ASSUMED $0.30
    BOX_IDS = ("K-", "LOGIC", "BUS-", "RLY-", "OPTO", "D-R8", "BATT-RELAY", "D-HB", "D-IG2", "F-PI")

    def metrics(self, cfg):
        W_, out = cfg["wires"], collections.OrderedDict()
        m_by_g, n_by_g = collections.Counter(), collections.Counter()
        ends, splices, conns, hous = collections.Counter(), set(), set(), {}
        wire_usd, cab_len = 0.0, {}
        x2_pins = 0
        for w in W_:
            g = w["awg"] or "cable"
            m_by_g[g] += w["mm"] / 1000.0
            n_by_g[g] += 1
            if w["cable"]:
                cab_len[w["cable"]] = max(cab_len.get(w["cable"], 0), w["mm"])
            else:
                wire_usd += w["mm"] / 304.8 * WIRE_FT.get(w["awg"], 2.5)
            for s in (0, 1):
                kd = w["kinds"][s]
                if not kd:
                    continue
                ends[kd] += 1
                if w["src"] != "new" and w["types"][s] == "splice":
                    splices.add(w["ends"][s])
                if w["src"] != "new" and w["types"][s] == "connector" and not w["ends"][s].startswith(self.BOX_IDS):
                    conns.add(w["ends"][s])
                    hous[w["ends"][s]] = w["housings"][s]
                if kd == "pdm" and w["ends"][s] == X2:
                    x2_pins += 1
        if cfg["pdm"]:
            conns |= {"PDM-X1", "PDM-X2"}
        wire_usd += sum(mm / 304.8 * 2.50 for mm in cab_len.values())
        sl = self.sleeving(cfg)
        big = ("DRB", "4-1437290", "HD3", "HDP", "DT06-12", "DT04-12", "DT06-08", "DT04-08")
        boots_usd = sum(0.0 if c.startswith("PDM-") else (BOOT_LARGE if hous.get(c, "").startswith(big) else BOOT_SMALL) for c in conns)
        lump, unpriced, trans = self.harness_lump()
        n_trans = int(sum(q for _, q, _ in trans)) + (1 if cfg["pdm"] else 0)
        trans_usd = sum(q * u for _, q, u in trans)          # the PDM Y transition is a PDM part line
        epoxy_usd = math.ceil(n_trans / 25.0) * EPOXY
        box_usd, box_min, box_lines = self.box_build()
        seat_back = sum(p["qty"] * p["unit"] for m in MOVES[:cfg["k"]] for p in m["seats"] if not p.get("lump"))
        seat_back_min = sum(p["min"] * p["qty"] for m in MOVES[:cfg["k"]] for p in m["seats"] if not p.get("lump"))
        parts_usd = sum(p["qty"] * p["unit"] for p in cfg["parts"] if not p["group"].startswith("st185 box seats"))
        parts_min = sum(p["min"] * p["qty"] for p in cfg["parts"] if not p["group"].startswith("st185 box seats"))
        end_usd = sum(self.END_USD.get(k, 0.0) * n for k, n in ends.items() if k in self.END_USD) + 0.88 * x2_pins
        encl_min = encl_usd = 0.0
        if cfg["pdm"]:
            for r in self.encl:
                encl_min += MIN["cut"] + MIN["test"]
                for s in ("From terminal PN", "To terminal PN"):
                    t = r[s].strip()
                    if t.lower() == "solder":
                        encl_min += MIN["solder"]
                    elif t.startswith(("0462-", "0460-", "43030-", "SSHL-")):    # HD / Micro-Fit / JST contacts
                        encl_min += MIN["crimp"] + MIN["insert"]
                    if t == "0462-201-2031":
                        encl_usd += 0.89
            used_x1 = sum(1 for w in W_ if X1 in w["ends"])
            encl_usd += (21 - min(21, used_x1 + 1)) * 0.22 + (47 - min(47, x2_pins + 4)) * 0.10   # sealing plugs (st185 prices)
        # labour (minutes)
        L = collections.OrderedDict()
        L["cut, strip, mark"] = len(W_) * MIN["cut"]
        L["terminate (crimp / insert / solder / tie-in)"] = sum(self.END_MIN.get(k, 0) * n for k, n in ends.items()) + MIN["splice"] * len(splices)
        L["sleeve DR-25"] = sum(MIN["dr25_piece"] + MIN["dr25_m"] * r["m"] for r in sl)
        L["boots + transitions"] = MIN["boot"] * (len(conns) + n_trans - (2 if cfg["pdm"] else 0))   # X1 / X2: on-hand rubber boots
        L["route + install in the car"] = MIN["seg_route"] * len(sl) + MIN["conn_mate"] * len(conns)
        L["test (continuity)"] = len(W_) * MIN["test"]
        L["build boxes (POWER / LOGIC / BATTRELAY)"] = box_min - seat_back_min
        L["relays / holders / design / PDM build and setup"] = parts_min + encl_min
        deg = collections.Counter()
        used = {tuple(sorted((a, b))) for w in W_ for a, b in zip(w["path"], w["path"][1:])}
        for a, b in used:
            deg[a] += 1
            deg[b] += 1
        C = collections.OrderedDict()
        C["wire and cable"] = wire_usd
        C["connectors, contacts, seals, splices (st185 harness BOM, same both routes)"] = lump
        C["new terminations (X2 pins, tie-in sleeves, lugs)"] = end_usd
        C["DR-25 sleeving"] = sum(r["usd"] for r in sl)
        C["boots (adhesive lined)"] = boots_usd
        C["transitions + epoxy"] = trans_usd + epoxy_usd
        C["fuse boxes POWER / LOGIC / BATTRELAY"] = box_usd - seat_back
        C["relays, holders, PDM parts (part lines)"] = parts_usd + encl_usd
        out.update(k=cfg["k"], usd=sum(C.values()), hours=sum(L.values()) / 60.0, cost=C, labour={a: b / 60 for a, b in L.items()},
                   metres=sum(m_by_g.values()), m_by_g=m_by_g, n_by_g=n_by_g, wires=len(W_),
                   terminations=sum(v for k, v in ends.items() if k != "splice") + len(splices),
                   ends=ends, splices=len(splices), connectors=len(conns), relays=cfg["relays"], fuses=cfg["fuses"],
                   branch_points=sum(1 for n in deg if deg[n] >= 3), sleeve_m=sum(r["m"] for r in sl),
                   sleeve_usd=C["DR-25 sleeving"], sleeve_rows=sl, boots=len(conns), transitions=n_trans,
                   boxes_gone=cfg["boxes_gone"], unpriced=unpriced, box_lines=box_lines, parts=cfg["parts"])
        return out


# ---------------------------------------------------------------------------------------------- outputs
def write_csv(path, head, rows, line1):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(line1 + "\n")
        w = csv.writer(f, lineterminator="\n")
        w.writerow(head)
        w.writerows(rows)


def chart(res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    BLUE, ORANGE, INK, INK2, MUTED, GRID, AXIS, SURF = ("#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#898781",
                                                        "#e1e0d9", "#c3c2b7", "#fcfcfb")
    ks = [r["k"] for r in res]
    labels = ["relay\nroute"] + [m["id"] for m in MOVES]
    for r in res:
        r["sockets"] = r["relays"] + r["fuses"]
    panels = [("Parts cost (USD)", "usd", "$%.0f"), ("Labour (hours)", "hours", "%.0f h"), ("Wire (metres)", "metres", "%.0f m"),
              ("Terminations (crimps, tie-ins, splices)", "terminations", "%.0f"), ("Splices", "splices", "%.0f"),
              ("Relay sockets + fuse positions", "sockets", "%.0f")]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5), facecolor=SURF, sharey=True)
    for ax, (title, key, fmt) in zip(axes.flat, panels):
        vals = [r[key] for r in res]
        ys = [100.0 * v / vals[0] for v in vals]          # indexed: relay route = 100 (one scale for all panels)
        ax.set_facecolor(SURF)
        ax.set_ylim(50, 130)
        ax.axhline(100, color=ORANGE, lw=2, ls=(0, (6, 3)), label="Relay route = 100 (all 20 loads on relays)")
        ax.plot(ks, ys, color=BLUE, lw=2, marker="o", ms=8, mec=SURF, mew=2, label="PDM route after each move (% of relay route)")
        ax.annotate(fmt % vals[-1], (ks[-1], ys[-1]), textcoords="offset points", xytext=(-10, 10), color=INK2, fontsize=9)
        ax.annotate(fmt % vals[0], (0, 100), textcoords="offset points", xytext=(4, 6), color=INK2, fontsize=9)
        for m_i, m in enumerate(MOVES, start=1):
            if any(b.startswith(("RLY-DRL", "relay holder", "OEM flasher")) for b in res[m_i]["boxes_gone_step"]):
                ax.axvline(m_i, color=GRID, lw=1, zorder=0)
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        ax.set_xticks(ks)
        ax.set_xticklabels(labels, fontsize=8, color=INK2)
        ax.tick_params(colors=MUTED)
        ax.grid(axis="y", color=GRID, lw=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(AXIS)
    h, l_ = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l_, loc="upper center", ncol=2, frameon=False, fontsize=10, labelcolor=INK)
    fig.suptitle("", y=0.99)
    fig.text(0.5, 0.015, "Moves (loads leave their relays for PDM outputs, in order): " + "; ".join(
        "%s %s" % (m["id"], m["name"]) for m in MOVES) + ". Grey lines: a box or holder disappears.",
        ha="center", fontsize=8, color=INK2, wrap=True)
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    fig.savefig(path, dpi=130, facecolor=SURF)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--st185", required=True, help="a clone of st185-link-ecu-config (read only)")
    ap.add_argument("--out", default=os.path.join(REPO, "docs", "harness-cost"))
    ap.add_argument("--png", default=os.path.join(REPO, "docs", "diagrams", "harness-breakpoint.png"))
    a = ap.parse_args()
    S = Study(a.st185)
    line1 = ("# DUMMY / DERIVED - harness cost study (tools/harness_cost_study.py); source: st185-link-ecu-config @ %s "
             "(read only) + this repo; not a source of truth" % S.commit)
    res, prev = [], None
    for k in range(len(MOVES) + 1):
        r = S.metrics(S.config(k))
        r["boxes_gone_step"] = [b for b in r["boxes_gone"] if not prev or b not in prev["boxes_gone"]]
        res.append(r)
        prev = r
    R, Pd = res[0], res[-1]
    head = ["k", "move", "loads moved (car config #)", "parts USD", "labour h", "USD incl. labour @ %.0f/h" % HOURLY,
            "wire m", "wires", "terminations", "splices", "connectors", "relay sockets", "fuse positions",
            "branch points", "DR-25 m", "DR-25 USD", "boots", "transitions", "boxes / holders gone at this move"]
    rows = []
    for r in res:
        m = MOVES[r["k"] - 1] if r["k"] else None
        rows.append([r["k"], (m["id"] + " " + m["name"]) if m else "relay route (st185 + new relays)",
                     " ".join(str(x) for x in m["loads"]) if m else "", round(r["usd"], 0), round(r["hours"], 1),
                     round(r["usd"] + HOURLY * r["hours"], 0), round(r["metres"], 1), r["wires"], r["terminations"],
                     r["splices"], r["connectors"], r["relays"], r["fuses"], r["branch_points"], round(r["sleeve_m"], 1),
                     round(r["sleeve_usd"], 0), r["boots"], r["transitions"], "; ".join(r["boxes_gone_step"])])
    write_csv(os.path.join(a.out, "breakpoint.dummy.csv"), head, rows, line1)
    # both routes side by side
    rows = [["parts USD (total)", round(R["usd"], 2), round(Pd["usd"], 2)]]
    rows += [["cost: " + c, round(R["cost"][c], 2), round(Pd["cost"][c], 2)] for c in R["cost"]]
    rows += [["labour h (total)", round(R["hours"], 2), round(Pd["hours"], 2)]]
    rows += [["labour: " + c, round(R["labour"][c], 2), round(Pd["labour"][c], 2)] for c in R["labour"]]
    for g in sorted(set(R["m_by_g"]) | set(Pd["m_by_g"]), key=lambda x: (not x.isdigit(), -int(x) if x.isdigit() else 0, x)):
        rows.append(["wire m, %s AWG" % g, round(R["m_by_g"][g], 2), round(Pd["m_by_g"][g], 2)])
        rows.append(["wires, %s AWG" % g, R["n_by_g"][g], Pd["n_by_g"][g]])
    for key in ("metres", "wires", "terminations", "splices", "connectors", "relays", "fuses", "branch_points",
                "sleeve_m", "sleeve_usd", "boots", "transitions"):
        rows.append([key, round(R[key], 2), round(Pd[key], 2)])
    for kd in sorted(set(R["ends"]) | set(Pd["ends"])):
        rows.append(["wire ends: " + kd, R["ends"][kd], Pd["ends"][kd]])
    rows.append(["st185 harness BOM lines with no price (same both routes)", R["unpriced"], Pd["unpriced"]])
    for b, c, h in R["box_lines"]:
        rows.append(["st185 %s box as designed: USD / build h" % b.upper(), c, h])
    write_csv(os.path.join(a.out, "routes.dummy.csv"), ["item", "relay route", "PDM route (all 10 moves)"], rows, line1)
    # sleeving per segment
    rows = []
    for name, r in (("relay", R), ("pdm", Pd)):
        for s in r["sleeve_rows"]:
            rows.append([name, s["seg"], s["mm"], s["wires"], s["od"], s["pn"], s["exp"], s["rec"], s["ratio"],
                         s["shrink_ok"], s["m"], s["usd"], s["src"]])
    write_csv(os.path.join(a.out, "sleeving.dummy.csv"),
              ["route", "segment", "segment mm", "wires", "bundle OD mm (1.2 sqrt sum d^2)", "DR-25", "expanded ID",
               "recovered ID", "expanded / OD (>= 1.25)", "recovered <= OD", "cut m (+10 %)", "USD", "price source"], rows, line1)
    # route-specific part lines
    rows = []
    for name, r in (("relay", R), ("pdm", Pd)):
        for p in r["parts"]:
            rows.append([name, p["group"], p["desc"], p["pn"], p["qty"], p["unit"], round(p["qty"] * p["unit"], 2), p["src"], p["min"]])
    write_csv(os.path.join(a.out, "parts.dummy.csv"),
              ["route", "group", "part", "part number", "qty", "unit USD", "line USD", "price source", "labour min each"], rows, line1)
    chart(res, a.png)
    for r in res:
        print("k=%2d usd=%7.0f h=%6.1f m=%6.1f wires=%4d term=%4d spl=%3d conn=%3d rel=%2d fus=%2d bp=%3d slv=%5.1fm $%5.0f %s" % (
            r["k"], r["usd"], r["hours"], r["metres"], r["wires"], r["terminations"], r["splices"], r["connectors"],
            r["relays"], r["fuses"], r["branch_points"], r["sleeve_m"], r["sleeve_usd"], "; ".join(r["boxes_gone_step"])))
    print("st185 commit", S.commit)


if __name__ == "__main__":
    main()
