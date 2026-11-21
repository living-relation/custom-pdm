"""Enclosure (inside-the-box) wire harness for the custom PDM: wire list -> harness.design files -> checks.

Usage (repo root, Python 3 with openpyxl):
  python harness/src/enclosure_harness.py wirelist [--force]   # write harness/enclosure-wire-list.xlsx + .csv from the tables below
  python harness/src/enclosure_harness.py build                # read the xlsx (the source of truth) -> enclosure.harnesslib + enclosure.harness
  python harness/src/enclosure_harness.py check                # wire list <-> .harness, gauge vs current, contact vs gauge, seal vs OD

The spreadsheet is the source of truth once it exists (harness-design skill: "fix the list first, then the drawing"):
`wirelist` refuses to overwrite it without --force. `build` and `check` read it. Geometry (route lengths, layout positions)
comes from the enclosure model, enclosure/v2c/src/build_v2c.py rev D (branch chore/cad-models-fusion, meta.json of the
2026-11-20 revD build); the numbers used are copied into ROUTE below with the model coordinates they came from.
"""
import csv, json, math, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HDIR = os.path.dirname(HERE)
XLSX = os.path.join(HDIR, "enclosure-wire-list.xlsx")
CSVF = os.path.join(HDIR, "enclosure-wire-list.csv")
LIBF = os.path.join(HDIR, "enclosure.harnesslib")
HARF = os.path.join(HDIR, "enclosure.harness")

COLS = ["Wire ID", "Signal", "Description", "Signal group", "Twist/Shield group", "Color", "AWG", "Wire part number",
        "Length (mm)", "From device", "From connector", "From pin", "From terminal PN", "From seal PN", "From strip (mm)",
        "From label", "To device", "To connector", "To pin", "To terminal PN", "To seal PN", "To strip (mm)", "To label",
        "Net", "Notes"]

# ------------------------------------------------------------------------------------------------------------------
# Length rule (stated in harness/circuit-list.md): route length in the enclosure model + 20 mm fan-out at an X1 / X2 end
# (shell-24 insert, cavities up to about 20 mm off the axis) + 2 x 15 mm service loop (one re-termination per end),
# rounded UP to 5 mm. TBD where the model has no route.
# ------------------------------------------------------------------------------------------------------------------
def plen(pts):
    return sum(math.dist(a, b) for a, b in zip(pts[:-1], pts[1:]))
ZT = 5.769872                                   # board top (Z_BOT 4.0 + PCB 1.769872)
YR = -127.0 + 2.54 + 19.6 + 4.0                 # REAR: rear of X1 / X2 (build_v2c.py REAR)
ROUTE = {   # model polylines, build_v2c.py rev D "wiring" section (x east, y north, z up, mm)
    "A1": [(151.236, -33.274, ZT + 2.5), (151.236, -41.274, ZT + 7), (151.236, -97.0, ZT + 7), (102.0, YR, 25.0)],
    "A2": [(225.626, -33.274, ZT + 2.5), (223.0, -41.274, ZT + 7), (223.0, -97.0, ZT + 7), (165.0, -99.5, ZT + 13), (114.0, YR, 25.0)],
    "BJ6": [(36.346, -31.774, ZT + 2), (37.09, -31.774, ZT + 5), (37.09, -60.0, ZT + 5), (37.09, -103.0, ZT + 6), (37.09, -106.0, 9.7),
            (180.0, -105.0, 9.7), (180.0, -103.5, 37.0)],
    "IN3": [(97.0, -82.6, 41.77), (97.0, -92.6, 47.0), (194.0, YR, 47.0)],
    "IN1": [(163.0, -82.6, 41.77), (163.0, -92.6, 47.0), (194.0, YR, 47.0)],
    "IN2": [(229.0, -82.6, 41.77), (229.0, -92.6, 47.0), (194.0, YR, 47.0)],
    "U1": [(246.0, -99.8, 30.0), (246.0, -97.3, 30.0), (234.0, -95.0, 27.0), (80.0, -95.0, 30.0), (68.0, -95.0, 22.0), (27.0, -95.0, 22.0),
           (27.0, -100.5, 22.0), (27.0, -100.5, 14.0), (27.0, -106.0, 9.0), (28.0, -109.34, 7.0)],
}
T58Y = {"T5": -9.69, "T6": -32.98, "T7": -56.27, "T8": -79.56}
for k, y in T58Y.items():
    ROUTE[k] = [(106.24, y, 16.0), (96.5, y, 16.0), (96.5, -97.0, 16.0), (122.0, YR, 19.0)]
HUB_PAD = (29.593 - 4.0, -99.18 + 1.0, 7.0)    # hub_bbox xmax - 4, ymax + 1 (build_v2c.py)
for k, X in {"U2": 20.75, "U3": 134.14, "U4": 208.53}.items():   # board USB-C J5 / J2 at W(n, -17.0974, 55.7412)
    ROUTE[k] = [HUB_PAD, (HUB_PAD[0] + 6.0, -99.0, 7.8), (X, -99.0, 7.8), (X, -97.5, ZT + 1.6)]
def rlen(key, xend=True, loop=True, splice_at_end=False):
    pts = ROUTE[key]
    if splice_at_end: pts = pts[:-1]             # B J6 ribbon: CAN legs stop at the splices by X2 (180, -105)
    L = plen(pts) + (20.0 if xend else 0.0) + (30.0 if loop else 0.0)
    return int(math.ceil(L / 5.0) * 5)

# ------------------------------------------------------------------------------------------------------------------
# Wire parts (SAE J1128 GXL for the X1 size 16 / 12 N-seal cavities, M22759/16 for 20 AWG: see circuit-list.md defaults)
# ------------------------------------------------------------------------------------------------------------------
WP = {  # key: (part id, part number, colour, awg, OD mm, description)
    "GXL16RD": ("wp_gxl16_rd", "J1128-GXL-16-RED", "Red", 16, 2.80, "WIRE, ELECTRICAL, 16 AWG, RED, GXL CROSS-LINKED POLYETHYLENE (XLPE), SAE J1128, -40 TO 125 C, OD 2.70-2.90 MM (IEWC SAE J1128 SHEET)"),
    "GXL12RD": ("wp_gxl12_rd", "J1128-GXL-12-RED", "Red", 12, 3.65, "WIRE, ELECTRICAL, 12 AWG, RED, GXL CROSS-LINKED POLYETHYLENE (XLPE), SAE J1128, -40 TO 125 C, OD 3.50-3.80 MM (IEWC SAE J1128 SHEET)"),
    "M20WH": ("m16_20_9", "M22759/16-20-9", "White", 20, 1.52, "WIRE, ELECTRICAL, 20 AWG, WHITE, ETFE (TEFZEL) INSULATED, TIN PLATED COPPER, 150 C, 600 V"),
    "M20VT": ("m16_20_7", "M22759/16-20-7", "Violet", 20, 1.52, "WIRE, ELECTRICAL, 20 AWG, VIOLET, ETFE (TEFZEL) INSULATED, TIN PLATED COPPER, 150 C, 600 V"),
    "M20BK": ("m16_20_0", "M22759/16-20-0", "Black", 20, 1.52, "WIRE, ELECTRICAL, 20 AWG, BLACK, ETFE (TEFZEL) INSULATED, TIN PLATED COPPER, 150 C, 600 V"),
    "M20YE": ("m16_20_4", "M22759/16-20-4", "Yellow", 20, 1.52, "WIRE, ELECTRICAL, 20 AWG, YELLOW, ETFE (TEFZEL) INSULATED, TIN PLATED COPPER, 150 C, 600 V"),
    "M20GN": ("m16_20_5", "M22759/16-20-5", "Green", 20, 1.52, "WIRE, ELECTRICAL, 20 AWG, GREEN, ETFE (TEFZEL) INSULATED, TIN PLATED COPPER, 150 C, 600 V"),
    "M20RD": ("m16_20_2", "M22759/16-20-2", "Red", 20, 1.52, "WIRE, ELECTRICAL, 20 AWG, RED, ETFE (TEFZEL) INSULATED, TIN PLATED COPPER, 150 C, 600 V"),
    "FANRD": ("wp_ul1571_28_rd", "UL1571 28AWG RED (Sunon factory lead)", "Red", 28, None, "WIRE, LEAD, UL1571 28 AWG, RED, PVC 80 C, FACTORY LEAD OF THE SUNON MF30101V1 FAN (PART OF THE FAN, NOT BOUGHT)"),
    "FANBK": ("wp_ul1571_28_bk", "UL1571 28AWG BLACK (Sunon factory lead)", "Black", 28, None, "WIRE, LEAD, UL1571 28 AWG, BLACK, PVC 80 C, FACTORY LEAD OF THE SUNON MF30101V1 FAN (PART OF THE FAN, NOT BOUGHT)"),
    "GH28WH": ("wp_gh28_wh", "TBD 28 AWG >=105 C WHITE (JST GH)", "White", 28, None, "WIRE, 28 AWG, WHITE, INSULATION RATED >= 105 C, OD WITHIN THE JST GH SSHL-002T-P0.2 RANGE (PART NUMBER TBD)"),
    "GH28RD": ("wp_gh28_rd", "TBD 28 AWG >=105 C RED (JST GH)", "Red", 28, None, "WIRE, 28 AWG, RED, INSULATION RATED >= 105 C, OD WITHIN THE JST GH SSHL-002T-P0.2 RANGE (PART NUMBER TBD)"),
    "GH28BK": ("wp_gh28_bk", "TBD 28 AWG >=105 C BLACK (JST GH)", "Black", 28, None, "WIRE, 28 AWG, BLACK, INSULATION RATED >= 105 C, OD WITHIN THE JST GH SSHL-002T-P0.2 RANGE (PART NUMBER TBD)"),
    "GH28VT": ("wp_gh28_vt", "TBD 28 AWG >=105 C VIOLET (JST GH)", "Violet", 28, None, "WIRE, 28 AWG, VIOLET, INSULATION RATED >= 105 C, OD WITHIN THE JST GH SSHL-002T-P0.2 RANGE (PART NUMBER TBD)"),
}
CODE = {"Red": "RD", "White": "WH", "Violet": "VT", "Black": "BK", "Yellow": "YE", "Green": "GN", "Gray": "GY"}
PN2WP = {v[1]: k for k, v in WP.items()}

# Connector / end catalogue (the Connectors sheet). kind: box = TE box receptacle, pads = solder pads on a board,
# housing = crimp housing, ring = ring lug on a terminal, splice, leads = a device's factory leads, plug = USB plug (bought cable)
CONN = {
    "X1": dict(device="Box wall X1 (outputs)", pn="HD34-24-21SN", mate="HD36-24-21PN (outside harness, not in this file)", kind="box",
               labels=list("ABCDEFGHJKLMNPRSTUVWX"), size12=set("BDEG"),
               desc="TE DEUTSCH HD30 receptacle, shell 24, 24-21 insert (17 x size 16 + 4 x size 12), sockets, N seal; contacts loaded from inside the box"),
    "X2": dict(device="Box wall X2 (signals, CAN)", pn="HDP24-24-47SE-L017", mate="HDP26-24-47PE-L015 (outside harness, not in this file)", kind="box",
               labels=[str(i) for i in range(1, 48)], size16={"1", "4", "5", "6", "34"},
               desc="TE DEUTSCH HDP20 receptacle, shell 24, 24-47 insert (42 x size 20 + 5 x size 16), sockets, E seal; contacts loaded from inside the box"),
    "A1-J3": dict(device="Board A1", pn="(board A J3 wire pads)", mate="-", kind="pads", labels=[str(i) for i in range(1, 13)],
                  desc="Board A J3 wire pads (old DT15-12PA holes, drill 1.77 mm; tools/wirepads.py), wires soldered"),
    "A2-J3": dict(device="Board A2", pn="(board A J3 wire pads)", mate="-", kind="pads", labels=[str(i) for i in range(1, 13)],
                  desc="Board A J3 wire pads (old DT15-12PA holes, drill 1.77 mm; tools/wirepads.py), wires soldered"),
    "B-J6": dict(device="Board B", pn="(board B J6 wire pads)", mate="-", kind="pads", labels=["1", "2", "3", "4"],
                 desc="Board B J6 wire pads (old Micro-Fit 2x2 holes, drill 1.02 mm; tools/wirepads.py), wires soldered"),
    "IN1-J2": dict(device="Input board #1 (A1)", pn="43025-1200", mate="Molex 43045-1200 (input board J2)", kind="housing", labels=[str(i) for i in range(1, 13)],
                   desc="Molex Micro-Fit 3.0 receptacle housing, 2x6, dual row"),
    "IN2-J2": dict(device="Input board #2 (A2)", pn="43025-1200", mate="Molex 43045-1200 (input board J2)", kind="housing", labels=[str(i) for i in range(1, 13)],
                   desc="Molex Micro-Fit 3.0 receptacle housing, 2x6, dual row"),
    "IN3-J2": dict(device="Input board #3 (B)", pn="43025-1200", mate="Molex 43045-1200 (input board J2)", kind="housing", labels=[str(i) for i in range(1, 13)],
                   desc="Molex Micro-Fit 3.0 receptacle housing, 2x6, dual row"),
    "A1-J6": dict(device="Board A1", pn="GHR-12V-S", mate="JST SM12B-GHS-TB (board A J6)", kind="housing", labels=[str(i) for i in range(1, 13)],
                  desc="JST GH housing 12 way (board end of the input-board link)"),
    "A2-J6": dict(device="Board A2", pn="GHR-12V-S", mate="JST SM12B-GHS-TB (board A J6)", kind="housing", labels=[str(i) for i in range(1, 13)],
                  desc="JST GH housing 12 way (board end of the input-board link)"),
    "B-J7": dict(device="Board B", pn="GHR-12V-S", mate="JST BM12B-GHS-TBT (board B J7)", kind="housing", labels=[str(i) for i in range(1, 13)],
                 desc="JST GH housing 12 way (board end of the input-board link)"),
    "IN1-J1": dict(device="Input board #1 (A1)", pn="GHR-12V-S", mate="JST SM12B-GHS-TB (input board J1)", kind="housing", labels=[str(i) for i in range(1, 13)],
                   desc="JST GH housing 12 way (input-board end)"),
    "IN2-J1": dict(device="Input board #2 (A2)", pn="GHR-12V-S", mate="JST SM12B-GHS-TB (input board J1)", kind="housing", labels=[str(i) for i in range(1, 13)],
                   desc="JST GH housing 12 way (input-board end)"),
    "IN3-J1": dict(device="Input board #3 (B)", pn="GHR-12V-S", mate="JST SM12B-GHS-TB (input board J1)", kind="housing", labels=[str(i) for i in range(1, 13)],
                   desc="JST GH housing 12 way (input-board end)"),
    "FAN1": dict(device="Fan 1 (Sunon MF30101V1-1000U-A99)", pn="(fan factory leads)", mate="-", kind="leads", labels=["+", "-"],
                 desc="Sunon fan, UL1571 28 AWG leads 145 +/- 10 mm, + red, - black (Sunon D03033580G-01 p. 6)"),
    "FAN2": dict(device="Fan 2 (Sunon MF30101V1-1000U-A99)", pn="(fan factory leads)", mate="-", kind="leads", labels=["+", "-"],
                 desc="Sunon fan, UL1571 28 AWG leads 145 +/- 10 mm, + red, - black (Sunon D03033580G-01 p. 6)"),
    "U1-A": dict(device="USB-C bulkhead (CnLinko LP-16-C05SX-02-101) rear socket", pn="TBD (USB-C plug of cable U1)", mate="CnLinko LP-16-C05SX-02-101 rear USB-C socket", kind="plug",
                 labels=["VBUS", "D+", "D-", "GND", "CC"], desc="USB-C plug, end A of USB 2.0 C-to-C cable U1 (cable part TBD)"),
    "U1-B": dict(device="USB hub (Adafruit 5997) upstream USB-C", pn="TBD (USB-C plug of cable U1)", mate="Adafruit 5997 USB-C (upstream)", kind="plug",
                 labels=["VBUS", "D+", "D-", "GND", "CC"], desc="USB-C plug, end B of USB 2.0 C-to-C cable U1 (cable part TBD)"),
    "HUB-P1": dict(device="USB hub (Adafruit 5997) PORT1 pads", pn="(hub PORT1 pads)", mate="-", kind="pads", labels=["5V", "D+", "D-", "GND"],
                   desc="Adafruit 5997 downstream PORT1 pads (5V, D+, D-, GND per Adafruit learn guide), wires soldered"),
    "HUB-P2": dict(device="USB hub (Adafruit 5997) PORT2 pads", pn="(hub PORT2 pads)", mate="-", kind="pads", labels=["5V", "D+", "D-", "GND"],
                   desc="Adafruit 5997 downstream PORT2 pads, wires soldered"),
    "HUB-P3": dict(device="USB hub (Adafruit 5997) PORT3 pads", pn="(hub PORT3 pads)", mate="-", kind="pads", labels=["5V", "D+", "D-", "GND"],
                   desc="Adafruit 5997 downstream PORT3 pads, wires soldered"),
    "U2-B": dict(device="Board B USB-C J2", pn="TBD (USB-C plug pigtail U2)", mate="GCT USB4085-GF-A (board B J2)", kind="plug", labels=["VBUS", "D+", "D-", "GND", "CC"],
                 desc="USB-C plug pigtail (VBUS, D+, D-, GND wired; CC: 56 kohm Rp to VBUS inside the plug, part TBD)"),
    "U3-B": dict(device="Board A1 USB-C J5", pn="TBD (USB-C plug pigtail U3)", mate="GCT USB4085-GF-A (board A J5)", kind="plug", labels=["VBUS", "D+", "D-", "GND", "CC"],
                 desc="USB-C plug pigtail (VBUS, D+, D-, GND wired; CC: 56 kohm Rp to VBUS inside the plug, part TBD)"),
    "U4-B": dict(device="Board A2 USB-C J5", pn="TBD (USB-C plug pigtail U4)", mate="GCT USB4085-GF-A (board A J5)", kind="plug", labels=["VBUS", "D+", "D-", "GND", "CC"],
                 desc="USB-C plug pigtail (VBUS, D+, D-, GND wired; CC: 56 kohm Rp to VBUS inside the plug, part TBD)"),
    "SP1": dict(device="-", pn="D-436-37", mate="-", kind="splice", labels=["S"], desc="TE Raychem D-436-37 sealed crimp splice, 20-16 AWG, max 2 wires per side (CAN_H)"),
    "SP2": dict(device="-", pn="D-436-37", mate="-", kind="splice", labels=["S"], desc="TE Raychem D-436-37 sealed crimp splice, 20-16 AWG, max 2 wires per side (CAN_L)"),
    "SP3": dict(device="-", pn="GENERIC SOLDER SPLICE", mate="-", kind="splice", labels=["S"], desc="Solder splice + adhesive heat shrink (Dan's library part), fan + (2 x 28 AWG + 1 x 20 AWG)"),
    "SP4": dict(device="-", pn="GENERIC SOLDER SPLICE", mate="-", kind="splice", labels=["S"], desc="Solder splice + adhesive heat shrink (Dan's library part), fan - (2 x 28 AWG + 1 x 20 AWG)"),
}
for t in ("T5", "T6", "T7", "T8"):
    CONN["B-" + t] = dict(device="Board B", pn="3240083", mate="Wurth REDCUBE 74650074R (board B %s), M4 x 8 screw" % t, kind="ring", labels=["R"],
                          desc="Phoenix Contact C-RC 6/M4 DIN ring cable lug, M4, 2.6-6 mm2, non-insulated (same lug as OUT1-4)")

TERM = {  # end kind / cavity size -> (contact PN, seal PN, strip mm)
    ("X1", 16): ("0462-201-1631", "integral grommet (N seal)", "7.1"),
    ("X1", 12): ("0462-210-1231", "integral grommet (N seal)", "6.4"),
    ("X2", 20): ("0462-201-20141", "integral grommet (E seal)", "4.8"),
    "pads": ("solder", "-", "4.0"), "housing_mf": ("43030-0007", "-", "TBD"), "housing_gh": ("SSHL-002T-P0.2", "-", "TBD"),
    "ring": ("3240083", "-", "8.0"), "splice": ("-", "-", "TBD"), "leads": ("factory", "-", "5.0"), "plug": ("cable assembly", "-", "factory"),
}

# ------------------------------------------------------------------------------------------------------------------
# Circuits -> wires. Each tuple: (signal, description, group, twist, wire key, from conn, from pin, to conn, to pin,
# length (int or "TBD"), current A, note). The "from" end is where the signal originates (harness-design skill).
# ------------------------------------------------------------------------------------------------------------------
ROWS = []
def add(*r): ROWS.append(r)
OUTA = [(1, "8", "H", "S"), (2, "7", "J", None), (3, "10", "K", "U"), (4, "9", "L", "V"), (5, "6", "M", "W"), (6, "5", "N", "X"), (7, "4", "P", "A"), (8, "3", "R", "C")]
for n, pad, c1, c2 in OUTA:
    add(f"A1_OUT{n}", f"Board A1 output {n}, 7.5 A, to X1", "C01 A1 outputs", "", "GXL16RD", "A1-J3", pad, "X1", c1, rlen("A1"), 7.5,
        "route: A1 ribbon (CPDM-HAR-202), J3 pad field +/-12 mm")
for n, pad, c1, c2 in OUTA:
    if c2: add(f"A2_OUT{n}", f"Board A2 output {n}, 7.5 A, to X1", "C02 A2 outputs", "", "GXL16RD", "A2-J3", pad, "X1", c2, rlen("A2"), 7.5,
               "route: A2 ribbon (CPDM-HAR-202), J3 pad field +/-12 mm")
for n, c in ((5, "B"), (6, "D"), (7, "E"), (8, "G")):
    add(f"B_OUT{n}", f"Board B output {n}, 15 A, ring lug on T{n} to X1", "C03 B outputs 5-8", "", "GXL12RD", f"B-T{n}", "R", "X1", c, rlen(f"T{n}"), 15.0,
        "route: T5-T8 ribbon (CPDM-HAR-202); 12 AWG replaces box-connectors.md 14 AWG (needs Dan's yes, see PR)")
for b, conn, pads, cav in (("A1", "A1-J3", ("12", "11"), ("7", "8")), ("A2", "A2-J3", ("12", "11"), ("15", "16")), ("B", "B-J6", ("4", "3"), ("23", "24"))):
    for i in (0, 1):
        L = rlen("BJ6") if b == "B" else "TBD"
        note = "route: B J6 ribbon (CPDM-HAR-202)" if b == "B" else "route not in the model; est. %d mm (board ribbon to (x, -97), then to X2 rear)" % (150 if b == "A1" else 155)
        add(f"{b}_IN{i + 1}", f"Board {b} input {i + 1} (switch to GND or 12 V)", f"C04 {b} board inputs", "", "M20WH", "X2", cav[i], conn, pads[i], L, 0.01, note)
for ib, b, x2in, x2an, x2gnd, nin, key in (("IN1", "A1", 9, 14, ["35"], 5, "IN1"), ("IN2", "A2", 17, 22, ["36"], 5, "IN2"), ("IN3", "B", 25, 33, ["37", "38"], 8, "IN3")):
    for ch in range(1, nin + 1):
        add(f"{b}_IN{ch + 2}", f"{b} input {ch + 2} via input board {ib[-1]} ch {ch}", f"C05 {b} input-board inputs", "", "M20WH", "X2", str(x2in + ch - 1),
            f"{ib}-J2", str(ch), rlen(key), 0.01, f"route: input-board {ib[-1]} ribbon (CPDM-HAR-202)")
    add(f"{b}_AN", f"{b} analog input 0-5 V via input board {ib[-1]} ch 9", f"C06 {b} analog input", "", "M20VT", "X2", str(x2an), f"{ib}-J2", "9", rlen(key), 0.01,
        f"route: input-board {ib[-1]} ribbon (CPDM-HAR-202)")
    for j, cav in enumerate(x2gnd):
        add("SIG_GND", f"Signal ground for switches / sensors, input board {ib[-1]} J2 pin {10 + j}", "C07 signal ground", "", "M20BK", f"{ib}-J2", str(10 + j),
            "X2", cav, rlen(key), 0.1, "switch / sensor returns only, never a load return; X2 35-38 mapping = default (this job)")
# CAN: X2 2 / 3 -> one splice per line by X2 -> each board (stubs < 0.3 m at 1 Mbit/s)
add("CAN_H", "CAN high, X2 to splice SP1", "C08 CAN", "TP1", "M20YE", "X2", "2", "SP1", "S", int(math.ceil((ROUTE["BJ6"][-1][2] - 9.7 + 1.5 + 20 + 30) / 5) * 5), 0.1,
    "twisted with CAN_L (TP1); splice by the X2 rear at the B ribbon end (180, -105)")
add("CAN_L", "CAN low, X2 to splice SP2", "C08 CAN", "TP1", "M20GN", "X2", "3", "SP2", "S", int(math.ceil((ROUTE["BJ6"][-1][2] - 9.7 + 1.5 + 20 + 30) / 5) * 5), 0.1, "twisted with CAN_H (TP1)")
for b, conn, tp, L, est in (("B", "B-J6", "TP2", rlen("BJ6", xend=False, splice_at_end=True), None), ("A1", "A1-J3", "TP3", "TBD", 125), ("A2", "A2-J3", "TP4", "TBD", 140)):
    note = "route: B J6 ribbon to the splice" if est is None else f"route not in the model; est. {est} mm (board ribbon to (x, -97), then to the splice)"
    add("CAN_H", f"CAN high stub, SP1 to board {b}", "C08 CAN", tp, "M20YE", "SP1", "S", conn, "2", L, 0.1, note)
    add("CAN_L", f"CAN low stub, SP2 to board {b}", "C08 CAN", tp, "M20GN", "SP2", "S", conn, "1", L, 0.1, note)
# Fans: A2 OUT2 (always-on / temperature fan output, r7a) -> SP3 -> both fan + leads; fan - leads -> SP4 -> input board #2 J2 pin 11 (GND)
add("FAN_12V", "Fan supply from A2 OUT2 (fan output, 1 A limit) to splice SP3", "C09 fans", "", "M20RD", "A2-J3", "7", "SP3", "S", "TBD", 1.0,
    "fan leads enter through a plate pass-through that the enclosure model does not have yet (TBD, enclosure job)")
add("FAN_GND", "Fan return to input board #2 GND (J2 pin 11)", "C09 fans", "", "M20BK", "IN2-J2", "11", "SP4", "S", "TBD", 1.0, "pass-through TBD (enclosure job)")
for f in ("FAN1", "FAN2"):
    add("FAN_12V", f"{f} + lead (factory)", "C09 fans", "", "FANRD", "SP3", "S", f, "+", 145, 1.0, "Sunon factory lead 145 +/- 10 mm, UL1571 80 C PVC: keep it out of the hot air under the lid")
    add("FAN_GND", f"{f} - lead (factory)", "C09 fans", "", "FANBK", f, "-", "SP4", "S", 145, 1.0, "Sunon factory lead 145 +/- 10 mm")
# Input-board links (JST GH, pin n <-> pin n; board A uses ch 1-5 + 9-12 only)
for b, bc, ic, chans, est in (("A1", "A1-J6", "IN1-J1", [1, 2, 3, 4, 5, 9, 10, 11, 12], 70), ("A2", "A2-J6", "IN2-J1", [1, 2, 3, 4, 5, 9, 10, 11, 12], 65),
                               ("B", "B-J7", "IN3-J1", list(range(1, 13)), 90)):
    for p in chans:
        if p <= 8:
            sig, wk, d, I = f"{b}_IN{p + 2}_MCU", "GH28WH", f"{b} input {p + 2} to the MCU", 0.01
        elif p == 9:
            sig, wk, d, I = f"{b}_AN_MCU", "GH28VT", f"{b} analog input to the MCU ADC", 0.01
        elif p == 10:
            sig, wk, d, I = f"+3V3_{b}", "GH28RD", f"Board {b} +3.3 V to the input-board pull-ups", 0.05
        else:
            sig, wk, d, I = f"GND_{b}", "GH28BK", f"Board {b} GND to the input board", 0.2 if b == "A2" else 0.05
        add(sig, d, f"C10 {b} input-board link", "", wk, bc, str(p), ic, str(p), "TBD", I,
            f"not in the enclosure model; straight-line est. {est} mm board J6/J7 to input board J1 (deck 32 mm above)")
# USB
for i, (s, wk) in enumerate((("USB_VBUS", "Red"), ("USB_D+", "Green"), ("USB_D-", "White"), ("USB_GND", "Black"), ("USB_CC", "Gray"))):
    cav = ["VBUS", "D+", "D-", "GND", "CC"][i]
    add(s, f"USB cable U1 core {cav}: bulkhead rear socket to hub upstream", "C11 USB", "U1", "USB:" + wk, "U1-A", cav, "U1-B", cav, 300, 0.5,
        "bought USB 2.0 C-to-C cable 0.3 m (model route 250 mm + plug bodies); cable part TBD")
for u, hub, plug, key in (("U2", "HUB-P1", "U2-B", "U2"), ("U3", "HUB-P2", "U3-B", "U3"), ("U4", "HUB-P3", "U4-B", "U4")):
    for i, (s, wk) in enumerate((("USB_VBUS", "Red"), ("USB_D+", "Green"), ("USB_D-", "White"), ("USB_GND", "Black"))):
        add(s, f"USB pigtail {u} core {['VBUS', 'D+', 'D-', 'GND'][i]}: hub pad to board USB-C", "C11 USB", u, "USB:" + wk, hub, ["5V", "D+", "D-", "GND"][i],
            plug, ["VBUS", "D+", "D-", "GND"][i], rlen(key, xend=False), 0.5, "USB-C plug pigtail, part TBD (56 kohm Rp on CC in the plug)")

def wire_rows():
    out = []
    for i, r in enumerate(ROWS, 1):
        sig, desc, grp, tw, wk, fc, fp, tc, tp, L, I, note = r
        wid = f"W{i:03d}"
        if wk.startswith("USB:"):
            col, awg, pn = wk[4:], "TBD", "core of cable %s (TBD)" % tw
        else:
            pid, pn, col, awg, od, _ = WP[wk]
        def end(c, p):
            k = CONN[c]["kind"]
            if k == "box":
                size = 12 if (c == "X1" and p in CONN["X1"]["size12"]) else 16 if c == "X1" else (16 if p in CONN["X2"]["size16"] else 20)
                return TERM[(c, size)]
            if k == "housing": return TERM["housing_mf" if c.endswith("J2") else "housing_gh"]
            return TERM[k]
        ft, fs, fst = end(fc, fp); tt, ts, tst = end(tc, tp)
        fl = f"{wid} {sig} >{tc}.{tp}"; tl = f"{wid} {sig} >{fc}.{fp}"
        net = sig if not sig.startswith("USB") else f"{tw}_{sig}"
        out.append([wid, sig, desc, grp, tw, CODE.get(col, col), awg, pn, L, CONN[fc]["device"], fc, fp, ft, fs, fst, fl,
                    CONN[tc]["device"], tc, tp, tt, ts, tst, tl, net, f"I = {I} A; {note}"])
    return out

KEY = [["Code", "Colour", "Used for"], ["RD", "Red", "switched +12 V outputs, fan supply, +3.3 V, USB VBUS"], ["WH", "White", "digital inputs, USB D-"],
       ["VT", "Violet", "analog inputs (0-5 V)"], ["BK", "Black", "SIG_GND, fan return, GND, USB GND"], ["YE", "Yellow", "CAN_H"], ["GN", "Green", "CAN_L, USB D+"], ["GY", "Gray", "USB CC core (cable maker colour TBD)"],
       ["", "", ""], ["Wire families", "", ""],
       ["J1128-GXL-16/12", "SAE J1128 GXL, 125 C", "X1 size 16 / 12 cavities (N seal needs OD 2.54-3.40 / 3.40-4.32 mm)"],
       ["M22759/16-20", "ETFE, 150 C", "20 AWG: X2 (E seal 1.02-2.41 mm), Micro-Fit (insulation <= 1.85 mm), CAN, fans"],
       ["UL1571 28", "PVC 80 C", "Sunon factory fan leads only"], ["28 AWG (TBD)", ">= 105 C", "JST GH links"],
       ["", "", ""], ["Labels", "", "printed heat-shrink sleeve at each end: '<wire ID> <signal> ><far end>'"],
       ["Length rule", "", "model route + 20 mm X1/X2 fan-out + 2 x 15 mm service loop, rounded up to 5 mm; TBD = not in the model"]]

def connectors_rows():
    rows = [["Connector", "Device", "Part number", "Mating part number", "Kind", "Description"]]
    for k, c in CONN.items():
        rows.append([k, c["device"], c["pn"], c["mate"], c["kind"], c["desc"]])
    return rows

def cmd_wirelist(force):
    if os.path.exists(XLSX) and not force:
        sys.exit(f"{XLSX} exists (it is the source of truth); use --force to regenerate from the tables")
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    rows = wire_rows()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Wires"
    ws.append(COLS)
    for r in rows: ws.append(r)
    for name, data in (("Connectors", connectors_rows()), ("Key", KEY)):
        s = wb.create_sheet(name)
        for r in data: s.append(r)
    for s in wb.worksheets:
        for c in s[1]: c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
        s.freeze_panes = "B2"
        for col in s.columns:
            w = max(len(str(c.value or "")) for c in col)
            s.column_dimensions[col[0].column_letter].width = min(60, max(8, w + 2))
    tmp = XLSX + ".tmp"; wb.save(tmp); os.replace(tmp, XLSX)
    export_csv()
    print(f"wrote {XLSX} and {CSVF}: {len(rows)} wires, {len(CONN)} connectors / ends")

def read_xlsx():
    import openpyxl
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb["Wires"]; hdr = [c.value for c in ws[1]]
    assert hdr == COLS, ("Wires sheet columns changed", hdr)
    rows = [dict(zip(COLS, [("" if v is None else v) for v in r])) for r in ws.iter_rows(min_row=2, values_only=True) if r[0]]
    return rows

def export_csv():
    rows = read_xlsx()
    tmp = CSVF + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(COLS)
        for r in rows: w.writerow([r[c] for c in COLS])
    os.replace(tmp, CSVF)

# ------------------------------------------------------------------------------------------------------------------
# Parts (library + harness). Reused from Dan's harness.design library "Parts Library" (5LO8) with the same ids where the
# part number is the same; the rest researched (sources in harness/circuit-list.md).
# ------------------------------------------------------------------------------------------------------------------
def G(v, u="AWG"): return {"value": v, "unit": u}
def parts():
    P = {k: [] for k in ("wireParts", "connectorParts", "contactParts", "terminalParts", "spliceParts", "cavityPlugParts")}
    for k, (pid, pn, col, awg, od, desc) in WP.items():
        p = {"id": pid, "partNumber": pn, "description": desc, "color": col, "gauge": G(awg)}
        p["manufacturer"] = "M22759" if pn.startswith("M22759") else "SAE J1128" if pn.startswith("J1128") else "Sunon" if "Sunon" in pn else "TBD"
        if od: p["diameter"] = {"value": od, "unit": "mm"}
        P["wireParts"].append(p)
    P["contactParts"] += [
        {"id": "n2P7k5Wp2TRezmHgd1q87", "partNumber": "0462-201-1631", "manufacturer": "TE DEUTSCH", "description": "CONTACT, SOCKET, SOLID, SIZE 16, GOLD, 16-20 AWG, 13 A",
         "type": "Crimp", "gender": "Socket", "contactColor": "Gold", "minGauge": G(20), "maxGauge": G(16)},
        {"id": "ct_hdp12s", "partNumber": "0462-210-1231", "manufacturer": "TE DEUTSCH", "description": "CONTACT, SOCKET, SOLID, SIZE 12, GOLD, 12-14 AWG, 25 A",
         "type": "Crimp", "gender": "Socket", "minGauge": G(14), "maxGauge": G(12)},
        {"id": "ct_0462_201_20141", "partNumber": "0462-201-20141", "manufacturer": "TE DEUTSCH", "description": "CONTACT, SOCKET, SOLID, SIZE 20, NICKEL, 20 AWG, 7.5 A",
         "url": "https://www.te.com/en/product-0462-201-20141.html", "type": "Crimp", "gender": "Socket", "contactColor": "Silver", "minGauge": G(20), "maxGauge": G(20)},
        {"id": "ct_43030_0007", "partNumber": "43030-0007", "manufacturer": "Molex", "description": "CONTACT, SOCKET, CRIMP, MICRO-FIT 3.0, TIN, 20-24 AWG, INSULATION 1.85 MM MAX, 5 A",
         "url": "https://www.molex.com/en-us/products/part-detail/430300007", "type": "Crimp", "gender": "Socket", "contactColor": "Silver", "minGauge": G(24), "maxGauge": G(20)},
        {"id": "ct_sshl_002t", "partNumber": "SSHL-002T-P0.2", "manufacturer": "JST", "description": "CONTACT, SOCKET, CRIMP, GH 1.25 MM, 26-30 AWG, 1 A",
         "type": "Crimp", "gender": "Socket", "minGauge": G(30), "maxGauge": G(26)},
    ]
    P["cavityPlugParts"] += [
        {"id": "pl_sz20", "partNumber": "0413-204-2005", "manufacturer": "TE DEUTSCH", "description": "PLUG, SEALING, CAVITY, SIZE 20, RED"},
        {"id": "F6dRxdC4XlgPgmxZh_zyn", "partNumber": "114017", "manufacturer": "TE DEUTSCH", "description": "PLUG, SEALING, CAVITY, SIZE 16, WHITE"},
    ]
    P["terminalParts"].append({"id": "tp_3240083", "partNumber": "3240083", "manufacturer": "Phoenix Contact", "type": "Ring", "size": "M4",
                               "description": "RING CABLE LUG C-RC 6/M4 DIN, NON-INSULATED, 2.6-6 MM2, M4 (ID 4.3), MAX STRIP 9 MM",
                               "url": "https://www.phoenixcontact.com/us/products/3240083", "minGauge": G(2.6, "Metric"), "maxGauge": G(6, "Metric")})
    P["spliceParts"] += [
        {"id": "spp_d436_37", "partNumber": "D-436-37", "manufacturer": "TE Connectivity (Raychem)",
         "description": "SPLICE, CRIMP, IN-LINE, SEALED, AS81824/1 (M81824/1-2), 20-16 AWG WIRES, 1058-2680 CMA PER SIDE, MAX 2 WIRES PER SIDE"},
        {"id": "HP4pP__XZ40Qy8PCarkKn", "partNumber": "GENERIC SOLDER SPLICE", "manufacturer": "generic", "description": "SPLICE, SOLDERED, ADHESIVE HEATSHRINK OVER"},
    ]
    P["connectorParts"] += [
        {"id": "cp_hd34_24_21sn", "partNumber": "HD34-24-21SN", "manufacturer": "TE DEUTSCH", "url": "https://www.te.com/en/product-HD34-24-21SN.html",
         "description": "CONNECTOR, RECEPTACLE, HD30, SHELL 24, 21 POS (17 X SIZE 16, 4 X SIZE 12), SOCKET CONTACTS, N SEAL, FLANGE / JAM NUT",
         "gender": "Female", "numberOfCavities": 21, "hasShell": False, "designationStrategy": {"type": "custom", "labels": CONN["X1"]["labels"]},
         "configurations": [{"id": "cfg", "accessories": [
             {"id": "a1", "type": "ContactPart", "partId": "ct_hdp12s", "rule": {"gaugeFromPart": True}},
             {"id": "a2", "type": "ContactPart", "partId": "n2P7k5Wp2TRezmHgd1q87", "rule": {"gaugeFromPart": True}},
             {"id": "a3", "type": "CavityPlugPart", "partId": "F6dRxdC4XlgPgmxZh_zyn"}]}]},
        {"id": "cp_hdp24_24_47se", "partNumber": "HDP24-24-47SE-L017", "manufacturer": "TE DEUTSCH", "url": "https://www.te.com/en/product-HDP24-24-47SE-L017.html",
         "description": "CONNECTOR, RECEPTACLE, HDP20, SHELL 24, 47 POS (42 X SIZE 20, 5 X SIZE 16), SOCKET CONTACTS, E SEAL",
         "gender": "Female", "numberOfCavities": 47, "hasShell": False, "designationStrategy": {"type": "sequential"},
         "configurations": [{"id": "cfg", "accessories": [
             {"id": "a1", "type": "ContactPart", "partId": "ct_0462_201_20141"},
             {"id": "a2", "type": "CavityPlugPart", "partId": "pl_sz20"}]}]},
        {"id": "cp_43025_1200", "partNumber": "43025-1200", "manufacturer": "Molex", "url": "https://www.molex.com/en-us/products/part-detail/430251200",
         "description": "CONNECTOR, RECEPTACLE HOUSING, MICRO-FIT 3.0, 2 X 6, 12 POS, DUAL ROW", "gender": "Female", "numberOfCavities": 12, "hasShell": False,
         "designationStrategy": {"type": "sequential"}, "configurations": [{"id": "cfg", "accessories": [{"id": "a1", "type": "ContactPart", "partId": "ct_43030_0007"}]}]},
        {"id": "cp_ghr_12v_s", "partNumber": "GHR-12V-S", "manufacturer": "JST", "description": "CONNECTOR, HOUSING, GH 1.25 MM, 12 POS",
         "gender": "Female", "numberOfCavities": 12, "hasShell": False, "designationStrategy": {"type": "sequential"},
         "configurations": [{"id": "cfg", "accessories": [{"id": "a1", "type": "ContactPart", "partId": "ct_sshl_002t"}]}]},
    ]
    return P

CPART = {"X1": "cp_hd34_24_21sn", "X2": "cp_hdp24_24_47se", "IN1-J2": "cp_43025_1200", "IN2-J2": "cp_43025_1200", "IN3-J2": "cp_43025_1200",
         "A1-J6": "cp_ghr_12v_s", "A2-J6": "cp_ghr_12v_s", "B-J7": "cp_ghr_12v_s", "IN1-J1": "cp_ghr_12v_s", "IN2-J1": "cp_ghr_12v_s", "IN3-J1": "cp_ghr_12v_s"}
SPART = {"SP1": "spp_d436_37", "SP2": "spp_d436_37", "SP3": "HP4pP__XZ40Qy8PCarkKn", "SP4": "HP4pP__XZ40Qy8PCarkKn"}

# Layout (top view of the box, from the model: 3 px per mm, x0 = -15 mm, north up; snapped to the 30 grid)
def LP(x, y): return {"x": int(round((x + 15) * 3 / 30)) * 30, "y": int(round((15 - y) * 3 / 30)) * 30}
LAY = {"X1": (108, -127), "X2": (186, -127), "A1-J3": (151.2, -33.3), "A2-J3": (225.6, -33.3), "B-J6": (36.3, -31.8),
       "B-T5": (106.2, -9.7), "B-T6": (106.2, -33.0), "B-T7": (106.2, -56.3), "B-T8": (106.2, -79.6),
       "IN1-J2": (163.0, -82.6), "IN2-J2": (229.0, -82.6), "IN3-J2": (97.0, -82.6),
       "A1-J6": (118.8, -31.8), "A2-J6": (193.2, -31.8), "B-J7": (76.1, -77.9), "IN1-J1": (154.0, -20.6), "IN2-J1": (220.0, -20.6), "IN3-J1": (88.0, -20.6),
       "FAN1": (251.0, -76.0), "FAN2": (251.0, -44.0), "U1-A": (246.0, -117.0), "U1-B": (13.8, -119.0), "HUB-P1": (4.0, -103.0), "HUB-P2": (14.0, -103.0),
       "HUB-P3": (24.0, -103.0), "U2-B": (20.75, -89.0), "U3-B": (134.14, -89.0), "U4-B": (208.53, -89.0)}
BPS = {"BP_A1": (151.2, -97.0), "BP_A2": (223.0, -97.0), "BP_A2V": (165.0, -99.5), "BP_T": (96.5, -97.0), "BP_B": (37.1, -104.0),
       "BP_X2": (180.0, -105.0), "BP_FAN": (262.0, -100.0)}
SPLOC = {"SP1": "BP_X2", "SP2": "BP_X2", "SP3": "BP_FAN", "SP4": "BP_FAN"}
def seglen(key, i0, i1): return round(plen(ROUTE[key][i0:i1 + 1]), 1)
BUNDLES = [  # (id, from, to, length mm or None, label)
    ("bn_a1_1", "A1-J3", "BP_A1", seglen("A1", 0, 2), None), ("bn_a1_2", "BP_A1", "X1", seglen("A1", 2, 3), None), ("bn_a1_3", "BP_A1", "BP_X2", None, "A1 IN / CAN: route TBD"),
    ("bn_a2_1", "A2-J3", "BP_A2", seglen("A2", 0, 2), None), ("bn_a2_2", "BP_A2", "BP_A2V", seglen("A2", 2, 3), None), ("bn_a2_3", "BP_A2V", "X1", seglen("A2", 3, 4), None),
    ("bn_a2_4", "BP_A2", "BP_X2", None, "A2 IN / CAN: route TBD"),
    ("bn_b_1", "B-J6", "BP_B", seglen("BJ6", 0, 3), None), ("bn_b_2", "BP_B", "BP_X2", seglen("BJ6", 3, 5), None), ("bn_x2", "BP_X2", "X2", seglen("BJ6", 5, 6), None),
    ("bn_t_x1", "BP_T", "X1", seglen("T5", 2, 3), None),
    ("bn_in1", "IN1-J2", "X2", seglen("IN1", 0, 2), None), ("bn_in2", "IN2-J2", "X2", seglen("IN2", 0, 2), None), ("bn_in3", "IN3-J2", "X2", seglen("IN3", 0, 2), None),
    ("bn_fan1", "FAN1", "BP_FAN", None, "pass-through TBD"), ("bn_fan2", "FAN2", "BP_FAN", None, None), ("bn_fan3", "BP_FAN", "A2-J3", None, None),
    ("bn_fan4", "BP_FAN", "IN2-J2", None, None),
    ("bn_gh_a1", "A1-J6", "IN1-J1", None, "not modelled"), ("bn_gh_a2", "A2-J6", "IN2-J1", None, "not modelled"), ("bn_gh_b", "B-J7", "IN3-J1", None, "not modelled"),
    ("bn_u1", "U1-A", "U1-B", round(plen(ROUTE["U1"]), 1), "USB U1"),
    ("bn_u2", "HUB-P1", "U2-B", round(plen(ROUTE["U2"]), 1), None), ("bn_u3", "HUB-P2", "U3-B", round(plen(ROUTE["U3"]), 1), None),
    ("bn_u4", "HUB-P3", "U4-B", round(plen(ROUTE["U4"]), 1), None),
] + [(f"bn_{t.lower()}", "B-" + t, "BP_T", round(plen(ROUTE[t][0:3]), 1), None) for t in ("T5", "T6", "T7", "T8")]

def sid(name): return "c_" + name.replace("-", "_").replace("+", "p").lower()
def cav_id(name, lab): return sid(name) + "_" + {"+": "p", "-": "m", "D+": "dp", "D-": "dm"}.get(lab, lab.lower())

def cmd_build():
    rows = read_xlsx(); export_csv()
    P = parts()
    lib = {"version": 1.3, "kind": "library", "currency": "$"}; lib.update({k: v for k, v in P.items() if v})
    doc = {"version": 1.3, "currency": "$", "lengthUnit": "mm", "gaugeUnit": "AWG"}
    used = set()
    for r in rows: used.update([r["From connector"], r["To connector"]])
    # ---------------- schematic placement: box connectors left, devices right, inline parts in the middle ----------------
    LEFT = ["X1", "X2", "U1-A"]
    RIGHT = ["A1-J3", "A2-J3", "B-J6", "B-T5", "B-T6", "B-T7", "B-T8", "IN1-J2", "IN2-J2", "IN3-J2", "FAN1", "FAN2", "U1-B"]
    FAR = [("A1-J6", "IN1-J1"), ("A2-J6", "IN2-J1"), ("B-J7", "IN3-J1"), ("HUB-P1", "U2-B"), ("HUB-P2", "U3-B"), ("HUB-P3", "U4-B")]
    def height(n): return 30 + 30 * len(CONN[n]["labels"]) if CONN[n]["kind"] not in ("ring", "splice") else 30
    pos = {}; y = 0
    for n in LEFT: pos[n] = (0, y); y += height(n) + 90
    XR = 1500; y = 0
    for n in RIGHT: pos[n] = (XR, y); y += height(n) + (60 if CONN[n]["kind"] == "ring" else 90)
    yfar = max(y, max(p[1] + height(n) for n, p in pos.items())) + 180
    for a, b in FAR:
        pos[a] = (0, yfar); pos[b] = (600, yfar); yfar += max(height(a), height(b)) + 120
    conns, terms, spls = [], [], []
    sig_origin = {}
    for r in rows: sig_origin.setdefault((r["From connector"], str(r["From pin"])), r["Signal"])
    wired = {(r["From connector"], str(r["From pin"])) for r in rows} | {(r["To connector"], str(r["To pin"])) for r in rows}
    for n, c in CONN.items():
        if n not in used: continue
        k = c["kind"]
        if k == "splice":
            spls.append({"id": sid(n), "label": n, "partId": SPART[n], "locationId": "bp_" + SPLOC[n][3:].lower(),
                         "schematicPosition": {"x": 900, "y": 0}, "layoutPosition": LP(*BPS[SPLOC[n]])}); continue
        if k == "ring":
            t = {"id": sid(n), "label": n, "type": "Ring", "partId": "tp_3240083", "schematicPosition": {"x": pos[n][0], "y": pos[n][1]}, "layoutPosition": LP(*LAY[n])}
            if (n, "R") in sig_origin: t["signal"] = sig_origin[(n, "R")]
            terms.append(t); continue
        cav = []
        for lab in c["labels"]:
            cv = {"id": cav_id(n, lab)}
            if n not in CPART: cv["designation"] = lab
            if (n, lab) in sig_origin and not sig_origin[(n, lab)].startswith("SIG_GND"): cv["signal"] = sig_origin[(n, lab)]
            if (n, lab) in sig_origin and sig_origin[(n, lab)] == "SIG_GND": cv.update(signal="SIG_GND", **{"global": True})
            if n == "X1" and (n, lab) not in wired and lab in ("F", "T"): pass          # 114017 from the configuration (plug rule)
            if n == "X2" and (n, lab) not in wired and lab in CONN["X2"]["size16"]: cv["cavityPlugPartId"] = "F6dRxdC4XlgPgmxZh_zyn"
            if k == "plug" and lab == "CC" and n != "U1-A" and n != "U1-B": cv["notConnected"] = True
            cav.append(cv)
        co = {"id": sid(n), "label": n, "schematicPosition": {"x": pos[n][0], "y": pos[n][1]}, "layoutPosition": LP(*LAY[n]), "cavities": cav}
        if n in CPART: co["partId"] = CPART[n]
        if n in ("X1", "X2"): co["width"] = 180
        conns.append(co)
    # signals that change name across a component get propagate: false where they start (input board, splices keep names)
    wires, tws, cables = [], [], []
    def ep(c, p):
        k = CONN[c]["kind"]
        if k == "splice": return {"id": sid(c), "handle": "Splice"}
        if k == "ring": return {"id": sid(c), "handle": "Terminal"}
        return {"id": sid(c), "handle": cav_id(c, str(p))}
    wpid = {v[1]: v[0] for v in WP.values()}
    groups = {}
    for r in rows:
        w = {"id": r["Wire ID"].lower(), "identLabel": r["Wire ID"], "source": ep(r["From connector"], r["From pin"]), "target": ep(r["To connector"], r["To pin"])}
        col = {v: k for k, v in CODE.items()}.get(r["Color"], r["Color"])
        w["color"] = col
        if r["Wire part number"] in wpid:
            w["partId"] = wpid[r["Wire part number"]]
        if r["Wire part number"].startswith("UL1571"): w["excludeFromBom"] = True
        tg = r["Twist/Shield group"]
        if tg: groups.setdefault(tg, []).append(w)
        else: wires.append(w)
    ymid = 0
    for tg, ws in groups.items():
        if tg.startswith("TP"):
            tws.append({"id": "tw_" + tg.lower(), "label": tg, "schematicPosition": {"x": 900, "y": 0}, "wires": ws})
        else:   # USB cable: cores
            cores = [{k: v for k, v in w.items() if k in ("id", "color", "source", "target")} for w in ws]
            for c, w in zip(cores, ws): c["identLabel"] = w["identLabel"]
            cables.append({"id": "cab_" + tg.lower(), "label": "USB " + tg, "schematicPosition": {"x": 0, "y": 0}, "cores": cores})
    # place middle-column items: splices / twisted pairs by X2 CAN rows; fan splices by FAN rows; cables between their ends
    x2y = pos["X2"][1]
    place = {"tw_tp1": (900, x2y + 30), "c_sp1": (1080, x2y + 30), "c_sp2": (1080, x2y + 90), "tw_tp2": (1290, pos["B-J6"][1]),
             "tw_tp3": (1290, pos["A1-J3"][1]), "tw_tp4": (1290, pos["A2-J3"][1]), "c_sp3": (1350, pos["FAN1"][1]), "c_sp4": (1350, pos["FAN2"][1] + 30)}
    for e in spls + tws:
        if e["id"] in place: e["schematicPosition"] = {"x": place[e["id"]][0], "y": place[e["id"]][1]}
    for cb in cables:
        a = cb["cores"][0]["source"]["id"]
        src = next(n for n in CONN if sid(n) == a)
        if src == "U1-A": cb["schematicPosition"] = {"x": 600, "y": pos["U1-A"][1]}
        else: cb["schematicPosition"] = {"x": 300, "y": pos[src][1]}
    # lane waypoints for direct box-connector -> right-column wires (interval colouring, 30 px lanes)
    def row_y(name, lab):
        c = next(x for x in conns + terms if x["id"] == sid(name))
        if "cavities" not in c: return c["schematicPosition"]["y"] + 15
        i = [cv["id"] for cv in c["cavities"]].index(cav_id(name, lab))
        return c["schematicPosition"]["y"] + 30 * (i + 1) + 15
    direct = []
    for w in wires:
        s, t = w["source"]["id"], w["target"]["id"]
        names = {sid(n): n for n in CONN}
        a, b = names[s], names[t]
        if (a in LEFT and b in RIGHT) or (b in LEFT and a in RIGHT):
            la, lb = (a, b) if a in LEFT else (b, a)
            pa = w["source"]["handle"] if a == la else w["target"]["handle"]
            pb = w["target"]["handle"] if a == la else w["source"]["handle"]
            ya = row_y(la, next(l for l in CONN[la]["labels"] if cav_id(la, l) == pa))
            yb = row_y(lb, "R" if CONN[lb]["kind"] == "ring" else next(l for l in CONN[lb]["labels"] if cav_id(lb, l) == pb))
            direct.append((min(ya, yb), max(ya, yb), w, ya, yb))
    lanes = []
    for lo, hi, w, ya, yb in sorted(direct, key=lambda d: (d[0], d[1])):
        for li, end in enumerate(lanes):
            if end + 30 <= lo: lanes[li] = hi; break
        else:
            li = len(lanes); lanes.append(hi)
        lx = 300 + 30 * li + 15
        if ya == yb: continue                       # straight run: no waypoint (the app drops collinear points)
        w["layoutPoints"] = [{"id": w["id"] + "_p1", "schematicPosition": {"x": lx - 15, "y": ya - 15}},
                             {"id": w["id"] + "_p2", "schematicPosition": {"x": lx - 15, "y": yb - 15}}]
    assert 300 + 30 * len(lanes) < 870, ("too many lanes for the gap", len(lanes))
    bps = [{"id": "bp_" + k[3:].lower(), "label": k[3:], "layoutPosition": LP(*v)} for k, v in BPS.items()]
    def nid(n): return "bp_" + n[3:].lower() if n.startswith("BP_") else sid(n)
    bundles = []
    for bid, a, b, L, lab in BUNDLES:
        bd = {"id": bid, "sourceId": nid(a), "targetId": nid(b)}
        if L: bd["length"] = {"value": L, "unit": "mm"}
        if lab: bd.update(label=lab, middleLabel=True)
        bundles.append(bd)
    notes = [{"id": "sn_1", "schematicPosition": {"x": 0, "y": -150}, "width": 360, "color": "Yellow",
              "text": "custom-pdm enclosure INSIDE harness. Source of truth: harness/enclosure-wire-list.xlsx (built by harness/src/enclosure_harness.py). "
                      "Box connectors left, boards / devices right. Board pads, fan leads and hub pads are device ends (no part)."}]
    lnotes = [{"id": "ln_1", "layoutPosition": {"x": 0, "y": -120}, "width": 360, "color": "Yellow",
               "text": "Top view of the box, north up, from enclosure/v2c build_v2c.py rev D (3 px = 1 mm). Bundle lengths = model routes (no loops); "
                       "unlabelled-length bundles are not in the model (TBD). Fan pass-through BP FAN: TBD (enclosure job)."}]
    doc.update({"wires": wires, "connectors": conns, "terminals": terms, "cables": cables, "twistedWires": tws, "splices": spls,
                "bundles": bundles, "branchPoints": bps, "schematicNotes": notes, "layoutNotes": lnotes})
    doc.update({k: v for k, v in P.items() if v})
    doc = {k: v for k, v in doc.items() if v != []}
    for f, d in ((LIBF, lib), (HARF, doc)):
        fd, tmp = tempfile.mkstemp(dir=HDIR, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh: json.dump(d, fh, indent=2, ensure_ascii=False); fh.write("\n")
        os.replace(tmp, f)
    print(f"wrote {LIBF} and {HARF}: {len(wires)} wires, {sum(len(t['wires']) for t in tws)} twisted, {sum(len(c['cores']) for c in cables)} cable cores, "
          f"{len(conns)} connectors, {len(terms)} terminals, {len(spls)} splices, {len(bundles)} bundles, {len(lanes)} lanes")

# ------------------------------------------------------------------------------------------------------------------
# Checks
# ------------------------------------------------------------------------------------------------------------------
AMP125 = {16: 30.0, 14: 40.0, 12: 50.0}   # 33 CFR 183.425 Table 5, 125 C insulation column (A)
AMB_90C = 0.61                            # AWC "Correction Factors for Various Ambient Temperatures", 125 C column, 90 C ambient
def bundle_factor(n):                     # 33 CFR 183.425 Table 5 note 2 (current-carrying conductors in a bundle)
    return 1.0 if n <= 2 else 0.70 if n == 3 else 0.60 if n <= 6 else 0.50 if n <= 24 else 0.40
SEAL = {("X1", 16): (2.54, 3.40), ("X1", 12): (3.40, 4.32), ("X2", 20): (1.02, 2.41), ("X2", 16): (1.35, 3.05)}   # TE HD30/HDP20 catalog p. 83
CONTACT_AWG = {"0462-201-1631": (20, 16), "0462-210-1231": (14, 12), "0462-201-20141": (20, 20), "43030-0007": (24, 20), "SSHL-002T-P0.2": (30, 26)}
SMALL_I = {20: 1.0, 28: 1.0}              # 20 AWG / 28 AWG carry <= 1 A here: checked against the contact / JST GH 1 A rating, not the table

def cmd_check():
    rows = read_xlsx(); doc = json.load(open(HARF, encoding="utf-8")); fails = []
    # 1. wire list <-> harness (every row is a conductor with the same ends, and nothing else is in the harness)
    names = {}
    for c in doc.get("connectors", []):
        labs = CONN[c["label"]]["labels"]
        for cv, lab in zip(c["cavities"], labs): names[(c["id"], cv["id"])] = (c["label"], lab)
    for t in doc.get("terminals", []): names[(t["id"], "Terminal")] = (t["label"], "R")
    for s in doc.get("splices", []): names[(s["id"], "Splice")] = (s["label"], "S")
    cond = {}
    for w in doc.get("wires", []): cond[w["id"]] = w
    for t in doc.get("twistedWires", []):
        for w in t["wires"]: cond[w["id"]] = dict(w, tw=t["label"])
    for c in doc.get("cables", []):
        for w in c["cores"]: cond[w["id"]] = dict(w, tw=c["label"].replace("USB ", ""))
    seen = set()
    for r in rows:
        w = cond.get(r["Wire ID"].lower())
        if not w: fails.append(f"{r['Wire ID']}: in the wire list, not in the harness"); continue
        seen.add(w["id"])
        a = names.get((w["source"]["id"], w["source"]["handle"])); b = names.get((w["target"]["id"], w["target"]["handle"]))
        want = ((r["From connector"], str(r["From pin"])), (r["To connector"], str(r["To pin"])))
        if (a, b) != want: fails.append(f"{r['Wire ID']}: ends {a} -> {b} in the harness, {want} in the list")
        if r["Twist/Shield group"] and w.get("tw") != r["Twist/Shield group"]: fails.append(f"{r['Wire ID']}: twist/cable group differs")
    for k in cond:
        if k not in seen: fails.append(f"{k}: in the harness, not in the wire list")
    # 2. gauge vs current (ampacity), 3. contact vs gauge, 4. seal vs OD
    from collections import Counter
    bundle_n = Counter(r["Signal group"] for r in rows if str(r["AWG"]) in ("16", "14", "12"))
    rep = []
    for r in rows:
        I = float(str(r["Notes"]).split("I = ")[1].split(" A")[0])
        awg = r["AWG"]
        if awg == "TBD": rep.append((r["Wire ID"], "USB core, bought cable, I %.2f A" % I)); continue
        awg = int(awg)
        if awg in AMP125:
            # every output wire meets the others at the X1 rear (worst case: the whole X1 bundle counts)
            n = sum(1 for x in rows if x["To connector"] == "X1") if r["To connector"] == "X1" else bundle_n[r["Signal group"]]
            amp = AMP125[awg] * AMB_90C * bundle_factor(n)
            ok = amp >= I
            rep.append((r["Wire ID"], f"{awg} AWG: {AMP125[awg]:.0f} A x {AMB_90C} x {bundle_factor(n)} ({n} in bundle) = {amp:.1f} A vs {I} A {'OK' if ok else 'FAIL'}"))
            if not ok: fails.append(f"{r['Wire ID']}: ampacity {amp:.1f} A < {I} A")
        else:
            ok = I <= SMALL_I[awg]
            if not ok: fails.append(f"{r['Wire ID']}: {awg} AWG carries {I} A > {SMALL_I[awg]} A")
        for side in ("From", "To"):
            c, p, t = r[f"{side} connector"], str(r[f"{side} pin"]), r[f"{side} terminal PN"]
            if t in CONTACT_AWG:
                lo, hi = CONTACT_AWG[t]
                if not (hi <= awg <= lo): fails.append(f"{r['Wire ID']} {side}: {awg} AWG outside contact {t} range {lo}-{hi} AWG")
            if t == "3240083" and not (2.6 <= {12: 3.31, 14: 2.08, 10: 5.26}[awg] <= 6.0): fails.append(f"{r['Wire ID']}: ring lug range")
            if c in ("X1", "X2"):
                size = 12 if (c == "X1" and p in CONN["X1"]["size12"]) else 16 if c == "X1" else (16 if p in CONN["X2"]["size16"] else 20)
                od = WP[PN2WP[r["Wire part number"]]][4]
                lo, hi = SEAL[(c, size)]
                if not (lo <= od <= hi): fails.append(f"{r['Wire ID']}: OD {od} outside {c} size {size} seal {lo}-{hi} mm")
            if t == "43030-0007":
                od = WP[PN2WP[r["Wire part number"]]][4]
                if od and od > 1.85: fails.append(f"{r['Wire ID']}: OD {od} > Micro-Fit 43030 insulation max 1.85 mm")
    # splice contents
    for s, maxside in (("SP1", 2), ("SP2", 2)):
        n = sum(1 for r in rows if s in (r["From connector"], r["To connector"]))
        if n > 2 * maxside: fails.append(f"{s}: {n} wires > {2 * maxside} (D-436-37 max 2 per side)")
    print(f"wire list rows {len(rows)}, harness conductors {len(cond)}")
    for wid, txt in rep:
        if "AWG:" in txt: print(" ", wid, txt)
    print("FAIL:\n  " + "\n  ".join(fails) if fails else "all checks pass")
    return 1 if fails else 0

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "wirelist": cmd_wirelist("--force" in sys.argv)
    elif cmd == "build": cmd_build()
    elif cmd == "check": sys.exit(cmd_check())
    else: sys.exit(__doc__)
