"""Enclosure (inside-the-box) wire harness for the custom PDM: CSV wire list -> harness.design files + wiring diagram -> checks.

Usage (repo root, Python 3, standard library only; openpyxl only for `xlsx`):
  python harness/src/enclosure_harness.py build      # CSVs -> enclosure.harnesslib + enclosure.harness
  python harness/src/enclosure_harness.py diagram    # CSVs -> enclosure-wiring-diagram.svg / -sheet2.svg / -sheet3.svg / .pdf (11 x 17 in)
  python harness/src/enclosure_harness.py check      # CSVs <-> .harness <-> diagram, schema, gauge vs current, contact vs gauge, seal vs OD
  python harness/src/enclosure_harness.py xlsx [out] # optional Excel copy of the three CSVs (generated, git-ignored, never read back)

The three CSV files are the master (Dan 2026-11-21; harness-design skill: "fix the list first, then the drawing"):
  enclosure-wire-list.csv   one row per wire (harness-design skill column order)
  enclosure-connectors.csv  one row per connector / end: part numbers, kind, cavity labels and contact sizes
  enclosure-key.csv         colour codes, wire families, label and length rules
Everything else in harness/ is generated from them. Wire parts, contact data and the harness.design layout stay in this
script. Geometry (bundle lengths, layout positions) comes from the enclosure model, enclosure/v2c/src/build_v2c.py rev D
(branch chore/cad-models-fusion, meta.json of the 2026-11-20 revD build); the numbers used are copied into ROUTE below
with the model coordinates they came from. The wire lengths in the CSV were first filled from the same routes
(route + 20 mm X1 / X2 fan-out + 2 x 15 mm service loop, rounded up to 5 mm); the CSV now owns them.
"""
import csv, json, math, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HDIR = os.path.dirname(HERE)
CSVF = os.path.join(HDIR, "enclosure-wire-list.csv")
CONF = os.path.join(HDIR, "enclosure-connectors.csv")
KEYF = os.path.join(HDIR, "enclosure-key.csv")
XLSX = os.path.join(HDIR, "enclosure-wire-list.generated.xlsx")
LIBF = os.path.join(HDIR, "enclosure.harnesslib")
HARF = os.path.join(HDIR, "enclosure.harness")

COLS = ["Wire ID", "Signal", "Description", "Signal group", "Twist/Shield group", "Color", "AWG", "Wire part number",
        "Length (mm)", "From device", "From connector", "From pin", "From terminal PN", "From seal PN", "From strip (mm)",
        "From label", "To device", "To connector", "To pin", "To terminal PN", "To seal PN", "To strip (mm)", "To label",
        "Net", "Notes"]
CCOLS = ["Connector", "Device", "Part number", "Mating part number", "Kind", "Cavities", "Contact size", "Other-size cavities", "Description"]
KCOLS = ["Kind", "Code", "Name", "Used for"]
# kind: box = TE box receptacle, pads = solder pads on a board, housing = crimp housing, ring = ring lug on a terminal,
# splice, leads = a device's factory leads, plug = USB plug (bought cable)
KINDS = ("box", "pads", "housing", "ring", "splice", "leads", "plug")

# ------------------------------------------------------------------------------------------------------------------
# The master: three CSV files (read only here; nothing in this script writes them)
# ------------------------------------------------------------------------------------------------------------------
def _csv(path, cols):
    with open(path, newline="", encoding="utf-8") as fh: rows = [r for r in csv.reader(fh) if any(c.strip() for c in r)]
    assert rows and rows[0] == cols, (os.path.basename(path) + ": columns changed", rows[:1])
    for r in rows[1:]: assert len(r) == len(cols), (os.path.basename(path) + ": wrong number of cells", r)
    return [dict(zip(cols, r)) for r in rows[1:]]

def read_connectors():
    conn = {}
    for d in _csv(CONF, CCOLS):
        n = d["Connector"]
        assert n not in conn, ("connector listed twice", n)
        assert d["Kind"] in KINDS, ("unknown connector kind", n, d["Kind"])
        c = dict(device=d["Device"], pn=d["Part number"], mate=d["Mating part number"], kind=d["Kind"], labels=d["Cavities"].split(), desc=d["Description"],
                 size=int(d["Contact size"]) if d["Contact size"] else None, other={})
        assert c["labels"] and len(set(c["labels"])) == len(c["labels"]), ("cavity labels missing or repeated", n)
        if d["Other-size cavities"]:
            sz, _, cavs = d["Other-size cavities"].partition(":")
            for lab in cavs.split():
                assert lab in c["labels"], ("other-size cavity is not a cavity", n, lab)
                c["other"][lab] = int(sz)
        conn[n] = c
    return conn

def read_wires():
    rows = _csv(CSVF, COLS); ids = set(); used = {}
    for r in rows:
        assert r["Wire ID"] not in ids, ("wire ID used twice", r["Wire ID"]); ids.add(r["Wire ID"])
        for side in ("From", "To"):
            c, p = r[side + " connector"], r[side + " pin"]
            assert c in CONN, (r["Wire ID"], "connector not in enclosure-connectors.csv", c)
            assert p in CONN[c]["labels"], (r["Wire ID"], "pin is not a cavity of", c, p)
            if CONN[c]["kind"] != "splice":
                assert (c, p) not in used, (r["Wire ID"], "cavity already used by", used[(c, p)], c, p)
                used[(c, p)] = r["Wire ID"]
        assert r["Color"] in CODE.values(), (r["Wire ID"], "colour code not in enclosure-key.csv", r["Color"])
    return rows

def read_key(): return _csv(KEYF, KCOLS)
def cav_size(c, p): return CONN[c]["other"].get(p, CONN[c]["size"])   # contact size of a box-connector cavity
def file_hash(path):
    """sha256 of a text file with CRLF read as LF (a Windows checkout and the git blob give the same hash)"""
    import hashlib
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
def source_hashes(): return [(os.path.basename(f), file_hash(f)) for f in (CSVF, CONF, KEYF)]

# ------------------------------------------------------------------------------------------------------------------
# Model routes (bundle lengths in the layout view). The wire lengths in the CSV were first filled from these (length rule in
# harness/circuit-list.md and enclosure-key.csv).
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
PN2WP = {v[1]: k for k, v in WP.items()}
CODE = {r["Name"]: r["Code"] for r in read_key() if r["Kind"] == "colour"}     # harness.design colour name -> code in the wire list
CONN = read_connectors()

def cmd_xlsx(out):
    """Excel copy of the three CSVs for people who want a spreadsheet (and for the harness.design Excel import). Generated, never read back."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Wires"
    for name, path in (("Wires", CSVF), ("Connectors", CONF), ("Key", KEYF)):
        s = ws if name == "Wires" else wb.create_sheet(name)
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.reader(fh): s.append(r)
    for s in wb.worksheets:
        for c in s[1]: c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
        s.freeze_panes = "B2"
        for col in s.columns:
            w = max(len(str(c.value or "")) for c in col)
            s.column_dimensions[col[0].column_letter].width = min(60, max(8, w + 2))
    wb.worksheets[2].insert_rows(1); wb.worksheets[2]["A1"] = "GENERATED COPY of harness/enclosure-*.csv (the CSV files are the master). Do not edit; changes here are never read."
    tmp = out + ".tmp"; wb.save(tmp); os.replace(tmp, out)
    print(f"wrote {out} (generated copy; the CSV files are the master)")

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

def built_harness(rows, want_stats=False):
    """the two harness.design files as bytes, from the wire-list rows"""
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
            if n == "X2" and (n, lab) not in wired and CONN["X2"]["other"].get(lab) == 16: cv["cavityPlugPartId"] = "F6dRxdC4XlgPgmxZh_zyn"
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
              "text": "custom-pdm enclosure INSIDE harness. Source of truth: harness/enclosure-wire-list.csv (built by harness/src/enclosure_harness.py). "
                      "Box connectors left, boards / devices right. Board pads, fan leads and hub pads are device ends (no part)."}]
    lnotes = [{"id": "ln_1", "layoutPosition": {"x": 0, "y": -120}, "width": 360, "color": "Yellow",
               "text": "Top view of the box, north up, from enclosure/v2c build_v2c.py rev D (3 px = 1 mm). Bundle lengths = model routes (no loops); "
                       "unlabelled-length bundles are not in the model (TBD). Fan pass-through BP FAN: TBD (enclosure job)."}]
    doc.update({"wires": wires, "connectors": conns, "terminals": terms, "cables": cables, "twistedWires": tws, "splices": spls,
                "bundles": bundles, "branchPoints": bps, "schematicNotes": notes, "layoutNotes": lnotes})
    doc.update({k: v for k, v in P.items() if v})
    doc = {k: v for k, v in doc.items() if v != []}
    out = {f: (json.dumps(d, indent=2, ensure_ascii=False) + "\n").encode("utf-8") for f, d in ((LIBF, lib), (HARF, doc))}
    stats = (len(wires), sum(len(t['wires']) for t in tws), sum(len(c['cores']) for c in cables), len(conns), len(terms), len(spls), len(bundles), len(lanes))
    return (out, stats) if want_stats else out

def cmd_build():
    out, st = built_harness(read_wires(), want_stats=True)
    for f, data in out.items():
        fd, tmp = tempfile.mkstemp(dir=HDIR, suffix=".tmp")
        with os.fdopen(fd, "wb") as fh: fh.write(data)
        os.replace(tmp, f)
    wires, tws, cables, conns, terms, spls, bundles, lanes = st
    print(f"wrote {LIBF} and {HARF}: {wires} wires, {tws} twisted, {cables} cable cores, {conns} connectors, {terms} terminals, {spls} splices, {bundles} bundles, {lanes} lanes")

# ------------------------------------------------------------------------------------------------------------------
# Checks
# ------------------------------------------------------------------------------------------------------------------
# harness.design v1.3 top-level keys (docs.harness.design/feature/local-files/json-format and the MCP editing guide "document-format", read 2026-11-21)
HD_SETTINGS = {"version", "currency", "lengthUnit", "gaugeUnit", "readOnly", "idNumbers", "schematic", "formboard"}
HD_COMPONENTS = {"wires", "connectors", "terminals", "cables", "twistedWires", "diodes", "resistors", "splices", "bundles", "branchPoints", "mates", "groups",
                 "schematicNotes", "layoutNotes", "schematicImages", "layoutImages"}
HD_PARTS = {"wireParts", "connectorParts", "terminalParts", "spliceParts", "contactParts", "cableParts", "coveringParts", "diodeParts", "resistorParts", "groupParts",
            "lockParts", "dustCoverParts", "backshellParts", "bootParts", "cavitySealParts", "cavityPlugParts", "mountParts"}
AMP125 = {16: 30.0, 14: 40.0, 12: 50.0}   # 33 CFR 183.425 Table 5, 125 C insulation column (A)
AMB_90C = 0.61                            # AWC "Correction Factors for Various Ambient Temperatures", 125 C column, 90 C ambient
def bundle_factor(n):                     # 33 CFR 183.425 Table 5 note 2 (current-carrying conductors in a bundle)
    return 1.0 if n <= 2 else 0.70 if n == 3 else 0.60 if n <= 6 else 0.50 if n <= 24 else 0.40
SEAL = {("X1", 16): (2.54, 3.40), ("X1", 12): (3.40, 4.32), ("X2", 20): (1.02, 2.41), ("X2", 16): (1.35, 3.05)}   # TE HD30/HDP20 catalog p. 83
CONTACT_AWG = {"0462-201-1631": (20, 16), "0462-210-1231": (14, 12), "0462-201-20141": (20, 20), "43030-0007": (24, 20), "SSHL-002T-P0.2": (30, 26)}
SMALL_I = {20: 1.0, 28: 1.0}              # 20 AWG / 28 AWG carry <= 1 A here: checked against the contact / JST GH 1 A rating, not the table

def cmd_check():
    rows = read_wires(); doc = json.load(open(HARF, encoding="utf-8")); fails = []
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
                size = cav_size(c, p)
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
    # 5. the .harness / .harnesslib still have the documented v1.3 shape (docs.harness.design /feature/local-files/json-format, read 2026-11-21)
    lib = json.load(open(LIBF, encoding="utf-8"))
    for name, d, allowed in (("enclosure.harness", doc, HD_SETTINGS | HD_COMPONENTS | HD_PARTS), ("enclosure.harnesslib", lib, {"version", "kind", "currency"} | HD_PARTS)):
        if d.get("version") != 1.3: fails.append(f"{name}: version {d.get('version')} is not 1.3")
        for k in d:
            if k not in allowed: fails.append(f"{name}: top-level key '{k}' is not in the harness.design v1.3 format")
            if isinstance(d[k], list) and not d[k]: fails.append(f"{name}: empty array '{k}' (the format wants it left out)")
    if lib.get("kind") != "library" or "kind" in doc: fails.append("kind: must be 'library' in the .harnesslib and absent in the .harness")
    allids = [e["id"] for k in HD_COMPONENTS | HD_PARTS for e in doc.get(k, [])]
    if len(allids) != len(set(allids)): fails.append("enclosure.harness: element / part ids are not unique")
    for k in ("connectors", "terminals", "splices", "twistedWires", "cables", "schematicNotes"):
        for e in doc.get(k, []):
            for pk in ("schematicPosition", "layoutPosition"):
                if pk in e and (e[pk]["x"] % 30 or e[pk]["y"] % 30): fails.append(f"{e['id']}: {pk} is not on the 30 grid")
    # 6. the built files are what `build` / `diagram` write from the CSVs now (nothing stale, nothing hand-edited)
    def same(path, data):
        try: old = open(path, "rb").read()
        except OSError: return False
        return old.replace(b"\r\n", b"\n") == data.replace(b"\r\n", b"\n")
    for f, data in built_harness(rows).items():
        if not same(f, data): fails.append(f"{os.path.basename(f)}: differs from a fresh build of the CSVs (run build)")
    date = diagram_date()
    if not date: fails.append("enclosure-wiring-diagram.svg: missing or has no date (run diagram)")
    else:
        files, drep = diagram_files(date); fails += drep["fails"]
        for f, data in files.items():
            if not same(f, data): fails.append(f"{os.path.basename(f)}: differs from a fresh build of the CSVs (run diagram)")
        import wiring_diagram
        svgs = [open(f, encoding="utf-8").read() for f in sorted(files) if f.endswith(".svg")]
        fails += wiring_diagram.coverage(svgs, [r["Wire ID"] for r in rows])     # every wire exactly once in the lines and in the schedule
        for name, h in source_hashes():
            if any(h not in s for s in svgs) or h.encode() not in open(DIAG + ".pdf", "rb").read(): fails.append(f"diagram title block: hash of {name} is not the current one")
        print(f"diagram: {drep['lines']} lines, {drep['sheets']} sheets, {drep['crossings']} crossings, every wire once in the lines and once in the schedule" if not fails else "diagram: see FAIL")
    print(f"wire list rows {len(rows)}, harness conductors {len(cond)}")
    for wid, txt in rep:
        if "AWG:" in txt: print(" ", wid, txt)
    print("FAIL:\n  " + "\n  ".join(fails) if fails else "all checks pass")
    return 1 if fails else 0

# ------------------------------------------------------------------------------------------------------------------
# Wiring block diagram (harness/src/wiring_diagram.py draws it; this writes the files)
# ------------------------------------------------------------------------------------------------------------------
DIAG = os.path.join(HDIR, "enclosure-wiring-diagram")
def diagram_files(date):
    import wiring_diagram
    svgs, pdf, rep = wiring_diagram.make(read_wires(), CONN, read_key(), source_hashes(), date)
    files = {DIAG + suf + ".svg": s.encode("utf-8") for suf, s in svgs}; files[DIAG + ".pdf"] = pdf
    return files, rep

def diagram_date():
    """date in the committed drawing (so `check` can rebuild the same bytes), else None"""
    import re
    try: m = re.search(r"<!-- date (\d{4}-\d\d-\d\d) ", open(DIAG + ".svg", encoding="utf-8").read(2000))
    except OSError: return None
    return m.group(1) if m else None

def cmd_diagram():
    import datetime
    date = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--date=")), None)
    if not date:   # keep the date while the sources are unchanged, so a rebuild writes the same bytes
        try: old = open(DIAG + ".svg", encoding="utf-8").read(2000)
        except OSError: old = ""
        date = diagram_date() if all(h in old for _, h in source_hashes()) and diagram_date() else datetime.date.today().isoformat()
    files, rep = diagram_files(date)
    if rep["fails"] and "--draft" not in sys.argv:
        sys.exit("diagram NOT written, drawing checks failed:\n  " + "\n  ".join(rep["fails"]))
    for f, data in files.items():
        fd, tmp = tempfile.mkstemp(dir=HDIR, suffix=".tmp")
        with os.fdopen(fd, "wb") as fh: fh.write(data)
        os.replace(tmp, f)
    for x in rep["fails"]: print("DRAFT, check failed:", x)
    print(f"wrote {DIAG}.svg (+ sheets 2-{rep['sheets']}) and .pdf: {rep['lines']} lines for {len(read_wires())} wires, {rep['sheets']} sheets, "
          f"{rep['crossings']} line crossings (all at 90 degrees), date {date}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build": cmd_build()
    elif cmd == "diagram": cmd_diagram()
    elif cmd == "check": sys.exit(cmd_check())
    elif cmd == "xlsx": cmd_xlsx(sys.argv[2] if len(sys.argv) > 2 else XLSX)
    else: sys.exit(__doc__)
