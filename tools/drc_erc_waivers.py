"""DRC / ERC review stage (job drcclean, 2026-11-23): every KiCad DRC / ERC item on board A, board B and the
input board is either fixed or waived here with a written reason; nothing is waived by severity alone.

Last stage of tools/build_board_a.ps1 / build_board_b.ps1 / build_input_board.ps1; also run on its own:

    python tools/drc_erc_waivers.py A|B|IN [--check]

What it writes (no footprint, pad, track, zone or net changes; the .kicad_pcb is never written):
  1. schematic: the 'Datasheet' field of the symbols in PARITY_DS gets '~' (the PCB footprints carry '~';
     stock dingoPDM / dingoPDM-Max left '' in the symbol): schematic parity 4 -> 0 on A and B.
  2. <board>.kicad_dru: the block between the BEGIN / END lines below: custom rules for maker land patterns and
     stock layout items (each rule names the parts and the reason). Rules with (severity exclusion) keep the item
     visible as excluded (kicad-cli --severity-exclusions / --severity-all) with the rule name as the reason.
  3. <board>.kicad_pro: drc_exclusions / erc_exclusions rebuilt from a fresh kicad-cli 10 run, one per item that
     matches a WAIVER row, with that row's reason as the exclusion comment. Old exclusions are replaced.
Then it re-runs DRC + ERC and prints the counts. Exit 1 if any DRC / ERC error, any parity item or any
unconnected item is left that is not waived. Warnings listed in OPEN (real items waiting for a decision) are
reported, not waived. --check writes nothing and fails if the files would change or an unwaived item exists.

Docs: docs/drc-erc-review.md (groups, KiCad rule per group, why each is safe).
Needs: kicad-cli 10 (schematics are KiCad 10 format; the PCB stays KiCad 9 format, kicad-cli only reads it).
"""
import json, os, re, subprocess, sys, tempfile, shutil, collections, uuid

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\bin\kicad-cli.exe")
BOARDS = {
    "A": ("hardware/board-a", "DingoPDM"),
    "B": ("hardware/board-b-max", "dingoPDM-Max"),
    "IN": ("hardware/input-board", "input-board"),
}
NULL = "00000000-0000-0000-0000-000000000000"
BEGIN = "# >>> custom-pdm tools/drc_erc_waivers.py (generated; edit the tool, not this block)"
END = "# <<< custom-pdm tools/drc_erc_waivers.py"

# symbols whose schematic Datasheet '' is set to '~' (= the footprint's value) -> schematic parity 0
PARITY_DS = {"A": ["C41", "C42", "JP1", "SW1"], "B": ["C39", "C40", "JP1", "SW1"], "IN": []}

# sheet file that keeps its UUIDs when another sheet file holds copies of them (the stock original)
DEDUP_KEEP = {"B": "BTS700n_1EPP.kicad_sch"}

# parts that must be DNP for the "alternate footprint" waivers to hold (checked on every run)
MUST_BE_DNP = {"A": ["U1", "U14"], "B": ["U1", "U12"], "IN": []}

ENV_LIB = ("ENV: DansPC KiCad 9 / 10 have no global symbol / footprint library table; the schematic embeds every "
           "symbol (lib_symbols) and the board embeds every footprint, so nothing is missing from the design")

# ---- DRC custom rules (.kicad_dru). KiCad: the LAST matching rule wins, so this block goes at the end. ----
def dru_rules(board):
    usb = {"A": "J5", "B": "J2"}.get(board)
    r = []
    if usb:
        r.append(f'''# USB-C {usb} (GCT USB4085 maker land pattern, stock dingoPDM): 0.85 mm pin pitch leaves 0.15 mm pad gap and
# 0.15 mm ring. JLCPCB limits (min ring 0.13 mm, min gap 0.1 mm) pass: tools/gen_fab_jlcpcb.py JLC-limit DRC.
(rule "custom-pdm: USB-C {usb} maker land pattern"
	(condition "A.memberOfFootprint('{usb}') && B.memberOfFootprint('{usb}')")
	(constraint clearance (min 0.15mm))
	(constraint hole_clearance (min 0.1mm)))
(rule "custom-pdm: USB-C {usb} maker ring"
	(condition "A.memberOfFootprint('{usb}')")
	(constraint annular_width (min 0.15mm)))
# The {usb} silk outline is drawn to the board edge (the receptacle sits on the edge); the fab clips it.
(rule "custom-pdm: USB-C {usb} silk at board edge (cosmetic, clipped by the fab)"
	(severity exclusion)
	(condition "(A.memberOfFootprint('{usb}') || B.memberOfFootprint('{usb}')) && (A.Layer == 'Edge.Cuts' || B.Layer == 'Edge.Cuts')")
	(constraint silk_clearance (min 0mm)))''')
    if board == "A":
        pairs = [("U14", "U21"), ("U14", "C55"), ("U14", "C56"), ("U14", "C57"), ("U14", "C4"),
                 ("J1", "H1"), ("JP1", "U2")]
        silk = ["Y1", "SW1"]
    elif board == "B":
        pairs = [("U12", "U27"), ("U12", "C66"), ("U12", "C67"), ("U12", "C68"), ("U12", "C4"),
                 ("J1", "H1"), ("JP1", "U2"),
                 ("T1", "U8"), ("T2", "U9"), ("U10", "T3"), ("U11", "T4"), ("T1", "T3"), ("T2", "T4")]
        silk = ["Y1", "SW1", "R38"]
    else:
        pairs, silk = [], []
    if pairs:
        cond = " || ".join(f"(A.Reference == '{a}' && B.Reference == '{b}') || (A.Reference == '{b}' && B.Reference == '{a}')"
                           for a, b in pairs)
        r.append(f'''# Courtyard overlaps, no copper or body clash (DRC copper clearance is clean for every pair):
#  U{"14" if board == "A" else "12"} (OKI-78SR, DNP alternate 5 V footprint, kept from stock) vs the fitted LMZM23601V5 module + caps (hw5v);
#  J1 / H1 (12 V terminal beside its mounting hole), JP1 / U2: stock dingoPDM patterns;
#  board B T1-T4 terminals vs U8-U11 and T1/T3, T2/T4: courtyard margins only, bodies 2.3 mm apart (docs/pcb-verification.md).
(rule "custom-pdm: courtyard overlap without body or copper clash"
	(severity exclusion)
	(condition "{cond}")
	(constraint courtyard_clearance (min 0mm)))''')
    if silk:
        cond = " || ".join(f"A.memberOfFootprint('{s}') || B.memberOfFootprint('{s}')" for s in silk)
        r.append(f'''# Silk lines / text of {", ".join(silk)} run over pad openings: the fab removes silk from the mask openings
# (cosmetic: the line is printed shorter; no solderability effect).
(rule "custom-pdm: silk clipped by solder mask (cosmetic)"
	(severity exclusion)
	(condition "({cond}) && (A.Type == 'pad' || B.Type == 'pad')")
	(constraint silk_clearance (min 0mm)))''')
    if board == "B":
        r.append('''# The stock dingoPDM-Max rules above ask 8 mil (0.2032 mm) for tracks and spacing; the stock and our routing use
# 0.2 mm. JLCPCB 4-layer limit is 0.09 mm / 0.09 mm (tools/gen_fab_jlcpcb.py JLC-limit DRC: no violations).
# Zones keep the stock 8 mil (the rule skips them), so a refill gives the same copper as before.
(rule "custom-pdm: 0.2 mm design minimum track width"
	(condition "A.Type == 'track'")
	(constraint track_width (min 0.2mm)))
(rule "custom-pdm: 0.2 mm design minimum track spacing"
	(condition "A.Type == 'track' && B.Type != 'zone'")
	(constraint clearance (min 0.2mm)))
# U4 (STM32 LQFP-64, 0.5 mm pitch): the GND track that leaves VSS pin 63 passes 0.11-0.17 mm from pins 62 / 64,
# as in stock dingoPDM-Max (JLCPCB min 0.09 mm).
(rule "custom-pdm: U4 LQFP VSS fan-out"
	(condition "A.Type == 'track' && A.NetName == 'GND' && B.memberOfFootprint('U4')")
	(constraint clearance (min 0.1mm)))
# SW1 'BOOT' value text 1.0 mm / 0.15 mm vs the stock board minimum 1.016 / 0.1524 mm (cosmetic label;
# JLCPCB prints legend from 0.8 mm high).
(rule "custom-pdm: SW1 BOOT label size (cosmetic)"
	(severity exclusion)
	(condition "A.memberOfFootprint('SW1')")
	(constraint text_height (min 1.016mm))
	(constraint text_thickness (min 0.1524mm)))''')
    return "\n".join(r)

# ---- exclusions: (board set, kind, type, regex on "desc1 | desc2", reason) ----
OUT_SAME = r"Symbol (U\d+) Pin \d+ \[(OUT\d*), Output, Line\] \| Symbol \1 Pin \d+ \[\2, Output, Line\]"
# Library-link checks only (not design checks): set to 'ignore' in the project (ENV_LIB). The generators own every
# symbol / footprint; the stock project already ignores lib_footprint_mismatch for the same reason.
IGNORE_DRC = ["lib_footprint_issues"]
IGNORE_ERC = ["lib_symbol_issues", "footprint_link_issues"]
SHEETLESS = {"endpoint_off_grid", "isolated_pin_label"}  # ERC types whose exclusion key has no sheet paths (found by test, kicad-cli 10.0.7)
WAIVERS = [
    ("A B IN", "erc", "endpoint_off_grid", r".",
     "COSMETIC: wire end / pin off the 1.27 mm connection grid (stock sheets + generated parts); connectivity is "
     "proven: 0 unconnected-pin / dangling-wire errors, schematic parity 0, netlist checks"),
    ("A", "erc", "pin_to_pin", OUT_SAME,
     "FALSE ALARM: BTS7008-2EPA pins of the same output (OUT0 or OUT1) joined as the data sheet requires; "
     "the symbol types them Output"),
    ("B", "erc", "pin_to_pin", r"Symbol (U(?:8|9|10|11|23|24|25|26)) Pin \d+ \[OUT\d+, Output, Line\] \| Symbol \1 Pin \d+ \[OUT\d+, Output",
     "FALSE ALARM: single-channel PROFET (BTS70012-1ESP / BTS7004-1EPP): all OUT pins are one output and must be "
     "joined (data sheet); the symbol types them Output"),
    ("A B", "erc", "pin_to_pin", r"Symbol U2 Pin 2 \[VOUT, Power output, Line\] \| Symbol U2 Pin 4 \[VOUT",
     "FALSE ALARM: TLV1117LV SOT-223 tab (pin 4) is the same VOUT as pin 2"),
    ("A", "erc", "pin_to_pin", r"Symbol (U1|U14|U21) Pin \d+ \[V?OUT, Power output, Line\] \| Symbol (U1|U14|U21) Pin",
     "FALSE ALARM: +5VP has three 5 V module footprints; only U21 (LMZM23601V5) is fitted, U1 / U14 are DNP alternates"),
    ("B", "erc", "pin_to_pin", r"Symbol (U1|U12|U27) Pin \d+ \[V?OUT, Power output, Line\] \| Symbol (U1|U12|U27) Pin",
     "FALSE ALARM: +5VP has three 5 V module footprints; only U27 (LMZM23601V5) is fitted, U1 / U12 are DNP alternates"),
    ("A B", "erc", "power_pin_not_driven", r"Symbol #PWR0[12] Hidden pin 1 \[(\+12V|GND), Power input",
     "FALSE ALARM: +12V and GND enter through the J1 / BATT terminals (passive pins); no PWR_FLAG on the sheet"),
    ("A B", "erc", "power_pin_not_driven", r"Symbol #PWR0(94|92) Pin 1 \[Power input",
     "FALSE ALARM: +12P (protected 12 V) is fed from +12V through the reverse-battery path (passive pins)"),
    ("A B", "erc", "power_pin_not_driven", r"Symbol #PWR012 Hidden pin 1 \[\+5V, Power input",
     "FALSE ALARM: +5V is fed from +5VP / USB VBUS through the OR diodes (passive pins)"),
    ("A B", "erc", "power_pin_not_driven", r"Symbol U4 Pin 13 \[VDDA, Power input",
     "FALSE ALARM: VDDA is fed from +3V3 through ferrite FB1 (passive), as ST AN4206 recommends"),
    ("A B", "erc", "power_pin_not_driven", r"Symbol U\d+ Pin [14] \[GND, Power input",
     "FALSE ALARM: PROFET GND pin goes to GND through RGND (data-sheet ground resistor) + cap, by design"),
    ("A", "erc", "pin_not_driven", r"Symbol J4 Pin 6 \[SWO, Input",
     "INTENTIONAL: debug header J4 SWO pin left unused (label SWO_UNUSED); SWD needs only SWDIO / SWCLK"),
    ("A", "erc", "isolated_pin_label", r"SWO_UNUSED",
     "INTENTIONAL: label naming the unused J4 SWO pin"),
    ("A B", "drc", "footprint_type_mismatch", r"Footprint U1\b",
     "FALSE ALARM: U1 VXO7805 alternate footprint (DNP) is marked SMD but has through-hole pads (stock)"),
    ("A B", "drc", "starved_thermal", r"GND",
     "OK: 1 of 2 thermal spokes on a small GND pad (neighbouring tracks block the 2nd); the pad still joins the "
     "GND pour, carries mA only, and 1 spoke solders easier; same as stock"),
]
# real items that stay visible until Dan / the coordinator decides (warnings, not waived)
OPEN = [
    ("A", "erc", "missing_unit", r"Symbol (U7|U12) "),
    ("A", "erc", "missing_input_pin", r"Symbol (U7|U12) "),
]


def run_cli(args):
    p = subprocess.run([CLI] + args, capture_output=True, text=True)
    if p.returncode not in (0, 5):
        raise SystemExit(f"kicad-cli failed: {' '.join(args)}\n{p.stdout}\n{p.stderr}")


def drc(pcb, out):
    run_cli(["pcb", "drc", "--schematic-parity", "--refill-zones", "--all-track-errors", "--severity-all",
             "--units", "mm", "--format", "json", "-o", out, pcb])
    return json.load(open(out, encoding="utf-8"))


def erc(sch, out):
    run_cli(["sch", "erc", "--severity-all", "--units", "mm", "--format", "json", "-o", out, sch])
    return json.load(open(out, encoding="utf-8"))


def read(p):
    return open(p, "rb").read()


def text_of(b):
    bom = b.startswith(b"\xef\xbb\xbf")
    t = b.decode("utf-8-sig")
    crlf = "\r\n" in t
    return t.replace("\r\n", "\n"), bom, crlf


def bytes_of(t, bom, crlf):
    if crlf:
        t = t.replace("\n", "\r\n")
    return (b"\xef\xbb\xbf" if bom else b"") + t.encode("utf-8")


def sheet_map(folder, root):
    """human sheet path ('/Power/') -> KIID path ('/<root uuid>/<sheet uuid>')"""
    acc, files = {}, {}

    def walk(fname, human, kiid):
        t = text_of(read(os.path.join(folder, fname)))[0]
        acc[human] = kiid
        files[human] = fname
        for m in re.finditer(r"\n\t\(sheet\n(.*?)\n\t\)", t, re.S):
            b = m.group(1)
            name = re.search(r'\(property "Sheet ?name" "([^"]+)"', b).group(1)
            f = re.search(r'\(property "Sheet ?file" "([^"]+)"', b).group(1)
            u = re.search(r'\n\t\t\(uuid "?([0-9a-f-]+)"?\)', b).group(1)
            walk(f, human + name + "/", kiid + "/" + u)
    rt = text_of(read(os.path.join(folder, root + ".kicad_sch")))[0]
    walk(root + ".kicad_sch", "/", "/" + re.search(r'\n\t\(uuid "?([0-9a-f-]+)"?\)', rt).group(1))
    return acc, files


def desc(v):
    return " | ".join(i["description"] for i in v["items"])


def match(board, kind, v, table):
    for row in table:
        if board in row[0].split() and row[1] == kind and row[2] == v["type"] and re.search(row[3], desc(v)):
            return row
    return None


def nm(x):  # pcb IU = 1 nm
    return int(round(x * 1e6))


def sch_iu(x):  # schematic IU = 100 nm
    return int(round(x * 1e4))


def sch_symbols(folder):
    """yield (file, start, end, block text) for every placed symbol in every sheet file"""
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".kicad_sch"):
            continue
        t = text_of(read(os.path.join(folder, f)))[0]
        for m in re.finditer(r"\n\t\(symbol\n\t\t\(lib_id .*?\n\t\)", t, re.S):
            yield f, m.start(), m.end(), m.group(0)


def refs_of(block):
    return set(re.findall(r'\(reference "([^"]+)"\)', block)) | set(re.findall(r'\(property "Reference" "([^"]+)"', block))


def main():
    board = sys.argv[1].upper()
    check = "--check" in sys.argv
    rel, name = BOARDS[board]
    folder = os.path.join(REPO, rel)
    pcb, sch = os.path.join(folder, name + ".kicad_pcb"), os.path.join(folder, name + ".kicad_sch")
    dru_p, pro_p = os.path.join(folder, name + ".kicad_dru"), os.path.join(folder, name + ".kicad_pro")
    new = {}  # path -> bytes

    # DNP guard for the alternate-footprint waivers
    dnp = {}
    for f, s, e, b in sch_symbols(folder):
        for r in refs_of(b):
            dnp[r] = "(dnp yes)" in b
    bad = [r for r in MUST_BE_DNP[board] if not dnp.get(r)]
    if bad:
        raise SystemExit(f"{board}: {bad} must be DNP for the alternate-footprint waivers; fix the waiver table first")

    # 0. duplicate UUIDs between sheet files (board B: tools/sch_board_b.py copies the stock BTS700n-1EPP sheet into
    #    BTS7004_1EPP.kicad_sch with its wire / junction / label / pin UUIDs). KiCad gives the duplicates new random
    #    UUIDs on every load, so ERC markers (and exclusions) on them are not stable. New UUIDs here are uuid5 of
    #    (file, old UUID): stable across runs. Symbol and sheet UUIDs are kept: the PCB footprint paths use them.
    #    (raw bytes kept everywhere: the sheet files mix CRLF stock lines with LF generated lines)
    files = {}
    owner = {}
    for f in sorted(os.listdir(folder), key=lambda f: (f != DEDUP_KEEP.get(board), f)):
        if not f.endswith(".kicad_sch"):
            continue
        p = os.path.join(folder, f)
        t = read(p).decode("utf-8")
        mine = set()

        def renew(m, f=f):
            old = m.group(2)
            if old in owner and owner[old] != f:
                return m.group(1) + str(uuid.uuid5(uuid.NAMESPACE_URL, f"custom-pdm/{f}/{old}")) + m.group(3)
            mine.add(old)
            return m.group(0)
        # top-level non-symbol items (depth 2 uuid) and symbol pin uuids (depth 3, inside "(pin ...")
        t2 = re.sub(r'(\r?\n\t\((?:wire|junction|no_connect|label|global_label|hierarchical_label|text|polyline|bus|bus_entry)\b'
                    r'(?:(?!\r?\n\t\)).)*?\r?\n\t\t\(uuid ")([0-9a-f-]+)(")', renew, t, flags=re.S)
        t2 = re.sub(r'(\r?\n\t\t\(pin "[^"]+"\r?\n\t\t\t\(uuid ")([0-9a-f-]+)(")', renew, t2)
        for o in mine:
            owner.setdefault(o, f)
        if t2 != t:
            files[p] = t2
            print(f"  {f}: duplicate UUIDs renewed")
    # 1. schematic Datasheet '' -> '~' for PARITY_DS
    for ref in PARITY_DS[board]:
        hit = 0
        for f in sorted(os.listdir(folder)):
            if not f.endswith(".kicad_sch"):
                continue
            p = os.path.join(folder, f)
            t = files.get(p) or read(p).decode("utf-8")
            out, pos = [], 0
            for m in re.finditer(r"\r?\n\t\(symbol\r?\n\t\t\(lib_id .*?\r?\n\t\)", t, re.S):
                b = m.group(0)
                if ref in refs_of(b) and len(refs_of(b)) == 1:
                    b2 = b.replace('(property "Datasheet" ""', '(property "Datasheet" "~"', 1)
                    hit += 1
                    print(f"  {ref}: Datasheet '' -> '~' in {f}" if b2 != b else f"  {ref}: Datasheet already '~' ({f})")
                    out.append(t[pos:m.start()]); out.append(b2); pos = m.end()
            out.append(t[pos:])
            files[p] = "".join(out)
        if hit != 1:
            raise SystemExit(f"{board}: {ref}: expected one schematic symbol, found {hit}")
    for p, t in files.items():
        b = t.encode("utf-8")
        if b != read(p):
            new[p] = b

    # 2. .kicad_dru block
    rules = dru_rules(board)
    if os.path.exists(dru_p):
        t, bom, crlf = text_of(read(dru_p))
    else:
        t, bom, crlf = "", False, False
    t = re.sub(r"\n*" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "\n", t, flags=re.S).rstrip("\n")
    if rules:
        if not t.strip():
            t = "(version 1)"
        t = t + "\n\n" + BEGIN + "\n" + rules + "\n" + END + "\n"
    elif t:
        t += "\n"
    if (os.path.exists(dru_p) or t) and bytes_of(t, bom, crlf) != (read(dru_p) if os.path.exists(dru_p) else b""):
        new[dru_p] = bytes_of(t, bom, crlf)

    # 3. exclusions from a fresh run on a scratch copy (sch / dru as written above, exclusions cleared)
    tmp = tempfile.mkdtemp(prefix="drcwaive-")
    try:
        work = os.path.join(tmp, "b")
        shutil.copytree(folder, work, ignore=shutil.ignore_patterns("*.kicad_prl", "*-backups", "fp-info-cache"))
        for p, b in new.items():
            open(os.path.join(work, os.path.relpath(p, folder)), "wb").write(b)
        wpro = os.path.join(work, name + ".kicad_pro")
        pt, pbom, pcrlf = text_of(read(pro_p))
        pro = json.loads(pt)
        pro["board"]["design_settings"]["drc_exclusions"] = []
        pro["erc"]["erc_exclusions"] = []
        for k in IGNORE_DRC:
            pro["board"]["design_settings"]["rule_severities"][k] = "ignore"
        for k in IGNORE_ERC:
            pro["erc"]["rule_severities"][k] = "ignore"
        open(wpro, "wb").write(bytes_of(json.dumps(pro, indent=2, ensure_ascii=False) + "\n", pbom, pcrlf))
        wpcb, wsch = os.path.join(work, name + ".kicad_pcb"), os.path.join(work, name + ".kicad_sch")
        d = drc(wpcb, os.path.join(tmp, "drc.json"))
        e = erc(wsch, os.path.join(tmp, "erc.json"))
        smap, sfile = sheet_map(work, name)
        sheet_text = {h: text_of(read(os.path.join(work, f)))[0] for h, f in sfile.items()}

        dex = []
        for v in d["violations"]:
            if v.get("excluded"):
                continue  # excluded by a (severity exclusion) rule
            row = match(board, "drc", v, WAIVERS)
            if not row:
                continue
            it = v["items"]
            if v["type"] == "starved_thermal":
                layer = re.search(r"\(layer ([^;]+);", v["description"]).group(1)
                pad = it[1]
                key = f'starved_thermal|{nm(pad["pos"]["x"])}|{nm(pad["pos"]["y"])}|{it[0]["uuid"]}|{pad["uuid"]}|{layer}'
            elif len(it) == 1:
                key = f'{v["type"]}|{nm(it[0]["pos"]["x"])}|{nm(it[0]["pos"]["y"])}|{it[0]["uuid"]}|{NULL}'
            else:
                raise SystemExit(f"{board}: two-item DRC waiver needs a .kicad_dru rule, not an exclusion: {v['type']} {desc(v)}")
            dex.append([key, row[4]])
        eex = []
        for s in e["sheets"]:
            S = smap[s["path"]]
            for v in s["violations"]:
                row = match(board, "erc", v, WAIVERS)
                if not row:
                    continue
                it = v["items"]
                aux, A = (it[1]["uuid"], S) if len(it) > 1 else (NULL, "")
                pts = [(sch_iu(it[0]["pos"]["x"]), sch_iu(it[0]["pos"]["y"]))]
                if v["type"] == "endpoint_off_grid" and " Wire, length" in it[0]["description"]:
                    # the marker sits on the off-grid END of the wire; the report gives the wire start
                    # (kicad-cli lists sheet-less items under '/', so look in every sheet file)
                    w = None
                    for st in sheet_text.values():
                        i = st.find(it[0]["uuid"])
                        if i > 0:
                            w = re.search(r"\(wire\s+\(pts\s+\(xy ([-\d.]+) ([-\d.]+)\)\s+\(xy ([-\d.]+) ([-\d.]+)\)", st[st.rfind("(wire", 0, i):i], re.S)
                            break
                    if not w:
                        raise SystemExit(f"{board}: wire {it[0]['uuid']} not found in the sheet files")
                    ends = [(sch_iu(float(w.group(1))), sch_iu(float(w.group(2)))), (sch_iu(float(w.group(3))), sch_iu(float(w.group(4))))]
                    pts = [p for p in ends if p[0] % 12700 or p[1] % 12700][:1] or pts  # one marker: first off-grid end
                for x, y in pts:
                    # KiCad 10 SCH_MARKER key: type|x|y|main|aux[|sheet-specific path|main-item path|aux-item path]
                    key = f'{v["type"]}|{x}|{y}|{it[0]["uuid"]}|{aux}'
                    if v["type"] == "isolated_pin_label":  # listed under '/', keyed by the label's own sheet only
                        homes = [h for h, f in sfile.items() if it[0]["uuid"] in sheet_text[h]]
                        if len(homes) != 1:
                            raise SystemExit(f"{board}: label {it[0]['uuid']} in {len(homes)} sheet instances")
                        key += f"|{smap[homes[0]]}||"
                    elif v["type"] not in SHEETLESS:
                        key += f"|{S}|{S}|{A}"
                    eex.append([key, row[4]])
        dex = sorted({k: c for k, c in dex}.items())
        eex = sorted({k: c for k, c in eex}.items())
        pro["board"]["design_settings"]["drc_exclusions"] = [list(x) for x in dex]
        pro["erc"]["erc_exclusions"] = [list(x) for x in eex]
        pb = bytes_of(json.dumps(pro, indent=2, ensure_ascii=False) + "\n", pbom, pcrlf)
        if pb != read(pro_p):
            new[pro_p] = pb
        open(wpro, "wb").write(pb)

        # 4. verify on the scratch copy
        n_d = len(d["violations"]); n_e = sum(len(s["violations"]) for s in e["sheets"])
        d = drc(wpcb, os.path.join(tmp, "drc2.json"))
        e = erc(wsch, os.path.join(tmp, "erc2.json"))
        left, opened = [], []
        n_d2 = len(d["violations"]); n_e2 = sum(len(s["violations"]) for s in e["sheets"])
        if (n_d, n_e) != (n_d2, n_e2):  # an exclusion key that matches nothing shows up as an extra excluded marker
            left.append(("TOOL", {"severity": "error", "type": "exclusion_key_mismatch", "items": [],
                                  "description": f"item count changed by the exclusions: DRC {n_d} -> {n_d2}, ERC {n_e} -> {n_e2}"}))
        cnt = collections.Counter()
        for v in d["violations"] + d.get("unconnected_items", []) + d.get("schematic_parity", []):
            cnt[("DRC", "excluded" if v.get("excluded") else v["severity"])] += 1
            if not v.get("excluded"):
                left.append(("DRC", v))
        for s in e["sheets"]:
            for v in s["violations"]:
                cnt[("ERC", "excluded" if v.get("excluded") else v["severity"])] += 1
                if not v.get("excluded"):
                    (opened if match(board, "erc", v, [r + ("",) for r in OPEN]) else left).append(("ERC", v))
        print(f"{board}: DRC errors {cnt[('DRC', 'error')]} warnings {cnt[('DRC', 'warning')]} excluded {cnt[('DRC', 'excluded')]}"
              f" | unconnected {len(d.get('unconnected_items', []))} parity {len(d.get('schematic_parity', []))}"
              f" | ERC errors {cnt[('ERC', 'error')]} warnings {cnt[('ERC', 'warning')]} excluded {cnt[('ERC', 'excluded')]}")
        for k, v in opened:
            print(f"  OPEN (real, not waived) {k} {v['type']}: {desc(v)}")
        for k, v in left:
            print(f"  NOT WAIVED {k} {v['severity']} {v['type']}: {v['description']} :: {desc(v)}")
    finally:
        if "--keep" in sys.argv:
            print(f"  scratch copy kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    if check:
        for p in new:
            print(f"  WOULD CHANGE {os.path.relpath(p, REPO)}")
        sys.exit(1 if (left or new) else 0)
    for p, b in new.items():
        open(p, "wb").write(b)
        print(f"  wrote {os.path.relpath(p, REPO)}")
    sys.exit(1 if left else 0)


if __name__ == "__main__":
    main()
