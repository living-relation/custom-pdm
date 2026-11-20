"""Order fields for every fitted part: Manufacturer, MPN, LCSC, Digi-Key_PN, Alternates (text edit, like sch_digikey.py).

usage (from the board folder, last schematic stage of the board build):  python sch_bom_fields.py A|B|IN

One table (PARTS) for boards A, B and the input board. A symbol is matched by its LCSC field (the old number or the
new one, so the script is safe to re-run) or, for parts that had no LCSC number, by footprint (+ value). Only these
fields change (and Value where a row says so): no symbol, pin, net or footprint change. Every placed symbol of the
board's hierarchy must match a row or be a non-part (NOT_PARTS: holes, logos, jumpers, wire pads, Tag-Connect pads);
anything else stops the script, so no fitted part can be left without order fields.
Rules (DECISIONS.md 2026-11-11 C6c, 2026-11-14 s9a, Dan 2026-11-14 / 2026-11-16):
  * MPN = the maker part the LCSC number resolves to (JLCPCB assembles from the LCSC column; C6c).
  * Parts are chosen by design need and cost, not stock: where LCSC / JLCPCB stock is short the part stays and the
    Alternates field names approved alternates (same footprint, same or better rating) for the assembler.
  * Digi-Key_PN None = keep the number already in the schematic (inherited from stock dingoPDM / earlier jobs;
    tools/sch_digikey.py). A Digi-Key number for an alternate part is named in Alternates.
Data: LCSC product pages + JLCPCB part pages read 2026-11-16 (stock / basic-extended in docs/parts-audit.md section 13);
Digi-Key product pages read 2026-11-16 for the new numbers. The PCB side is tools/pcb_bom_fields.py.
"""
import glob
import os
import re
import sys

KEEP = None   # Digi-Key_PN: keep what the schematic has

# match: LCSC number ("C123") or ("fp", footprint, value or None)
# (match, Manufacturer, MPN, LCSC, Digi-Key_PN, Alternates, new Value or None)
PARTS = [
    # ---- capacitors
    ("C49678", "YAGEO", "CC0805KRX7R9BB104", "C49678", KEEP, "", None),                       # 100nF 50V X7R
    ("C162422", "Murata", "GRM21BR6YA106KE43L", "C162422", KEEP, "", None),                   # 10uF 35V X5R (+12V)
    ("C45783", "Samsung Electro-Mechanics", "CL21A226MAQNNNE", "C45783", KEEP, "", None),     # 22uF 25V X5R
    ("C15850", "Samsung Electro-Mechanics", "CL21A106KAYNNNE", "C15850", KEEP, "", None),     # 10uF 25V X5R
    ("C1808", "FH (Guangdong Fenghua)", "0805CG270J500NT", "C1808", KEEP, "", None),          # 27pF 50V C0G
    ("C3879816", "KEMET", "C0805C473K5RAC7800", "C3879816", "399-C0805C473K5RACTUCT-ND",
     "KEMET C0805C473K5RACTU (same part, other reel code; DK 399-C0805C473K5RACTUCT-ND)", None),   # 47nF 50V X7R
    ("C1779", "Samsung Electro-Mechanics", "CL21A475KAQNNNE", "C1779", KEEP, "", None),       # 4.7uF 25V X5R
    ("C28323", "Samsung Electro-Mechanics", "CL21B105KBFNNNE", "C28323", KEEP, "", None),     # 1uF 50V X7R
    ("C1710", "Samsung Electro-Mechanics", "CL21B103KBANNNC", "C1710", KEEP, "", None),       # 10nF 50V X7R
    ("C576920", "YAGEO", "CC0805GRNPO0BN221", "C576920", KEEP, "", None),                     # 220pF 100V NP0
    ("C22388555", "PSA", "FS55X476K250LRG", "C22388555", KEEP, "", None),                     # 47uF 25V X7R 2220
    # ---- diodes, LEDs, ferrite
    ("C426855", "Nexperia", "PDZ3.3B,115", "C426855", KEEP, "", None),                        # 3.3 V zener SOD-323
    # TVS D2 across the +12 V feed: was BORN SMCJ20CA (LCSC C152086, 20 V stand-off: conducts at a 24 V jump start
    # and absorbs a 35 V suppressed load dump it cannot survive). 24 V stand-off, 5 kW, same DO-214AB footprint;
    # clamps fast ISO 7637-2 pulses under the switches' 35 V load-dump rating. Reasoning + sources:
    # docs/parts-audit.md section 13.
    ("C152086", "DOWO", "5.0SMDJ24CA", "C284111", "F5634CT-ND",
     "Littelfuse 5.0SMDJ24CA (DK F5634CT-ND)", "5.0SMDJ24CA"),
    ("C2976509", "DOWO", "NUP2105LT1G", "C2976509", KEEP, "onsemi NUP2105LT1G (DK NUP2105LT1GOSCT-ND)", None),
    ("C2899997", "OSRAM", "LS R976-NR-1-0-20-R18", "C2899997", KEEP, "", None),               # red LED 0805
    ("C2899888", "OSRAM", "LG R971-KN-1-0-20-R18", "C2899888", KEEP, "", None),               # green LED 0805
    ("C47546", "Nexperia", "BAT54S,215", "C47546", "BAT54SLT1GOSCT-ND",
     "onsemi BAT54SLT1G (DK BAT54SLT1GOSCT-ND)", None),                                       # same as the input-board row
    ("C179426", "Nexperia", "PMEG10010ELRX", "C179426", KEEP, "", None),                      # 100 V 1 A, SOD123W
    ("C110921", "Nexperia", "PMEG2010AEH,115", "C110921", KEEP, "", None),
    ("C141573", "Vishay", "BYG23M-E3/TR", "C141573", KEEP, "", None),
    ("C85840", "Murata", "BLM21PG221SN1D", "C85840", KEEP, "", None),
    # ---- resistors
    ("C327035", "YAGEO", "RT0805DRD0747KL", "C327035", KEEP,
     "UNI-ROYAL 0805W8F4702T5E (1 %, LCSC C17713, basic)", None),                             # 47k 0.5 % battery divider
    ("C17673", "UNI-ROYAL", "0805W8F4701T5E", "C17673", KEEP, "", None),
    ("C17414", "UNI-ROYAL", "0805W8F1002T5E", "C17414", KEEP, "", None),
    ("C17513", "UNI-ROYAL", "0805W8F1001T5E", "C17513", KEEP, "", None),
    # 120R: was YAGEO AC0805JR-07120RL (5 %, extended, LCSC C229076): 1 % basic part, same footprint (design + cost)
    ("C229076", "UNI-ROYAL", "0805W8F1200T5E", "C17437", "311-120CRCT-ND",
     "YAGEO RC0805FR-07120RL (DK 311-120CRCT-ND)", None),
    ("C17437", "UNI-ROYAL", "0805W8F1200T5E", "C17437", "311-120CRCT-ND",
     "YAGEO RC0805FR-07120RL (DK 311-120CRCT-ND)", None),
    # 1.2k sense: was FOJAN FRC0805J122 (5 %, extended, LCSC C2933520; P10): 1 % basic part = the Digi-Key column's
    # 1 % YAGEO part (311-1.20KCRCT-ND), same footprint
    ("C2933520", "UNI-ROYAL", "0805W8F1201T5E", "C17379", KEEP, "YAGEO RC0805FR-071K2L (DK 311-1.20KCRCT-ND)", None),
    ("C2907508", "FOJAN", "FRC1206J470 TS", "C2907508", KEEP, "", None),                      # 47R 1206
    ("C218638", "Viking", "ARG05FTC5101", "C218638", KEEP, "", None),                         # 5.1k USB CC
    # ---- ICs, modules, crystal
    ("C124016", "Microchip", "MCP2562FD-E/SN", "C124016", KEEP, "", None),
    ("C1343794", "STMicroelectronics", "STM32F446RET7", "C1343794", KEEP,
     "STMicroelectronics STM32F446RET6 (s9a; LCSC C69336)", None),
    ("C43379785", "RAMXEED (Fujitsu)", "MB85RC64TAPNF-G-AWERE2", "C43379785", KEEP,
     "RAMXEED MB85RC64TAPNF-G-BDERE1 (same chip, other packing; Mouser)", None),
    ("C129490", "Microchip", "MCP9808T-E/MS", "C129490", KEEP, "", None),
    # IS sense buffers (A U7 / U12, B U7 / U22): ADR-2026-11-20-is-buffer, rail-to-rail on 3.3 V (sch_board_power.py)
    ("C2058050", "Texas Instruments", "TLV9004IPWR", "C2058050", "296-51827-1-ND",
     "Microchip MCP6004T-E/ST (RRIO, -40 to 125 C, same TSSOP-14 pinout, DS20001733)", None),
    ("C15578", "Texas Instruments", "TLV1117LV33DCYR", "C15578", KEEP, "", None),
    ("C2150060", "Infineon", "BTS70082EPAXUMA1", "C2150060", KEEP,
     "Infineon BTS7008-2EPA (same chip, LCSC C534830)", None),
    ("C3232444", "Infineon", "BTS700121ESPXUMA1", "C3232444", KEEP,
     "Infineon BTS700121ESPXUMA2 (DK 448-BTS700121ESPXUMA2CT-ND)", None),
    ("C534825", "Infineon", "BTS70041EPPXUMA1", "C534825", KEEP, "", None),
    ("C6886877", "Traco Power", "TSR 1-2450", "C6886877", KEEP, "", None),
    ("C5137464", "CUI", "VXO7805-500-M-TR", "C5137464", KEEP, "", None),                      # DNP
    ("C266374", "Murata", "OKI-78SR-5/1.5-W36H-C", "C266374", KEEP, "", None),                # DNP
    ("C144380", "Abracon", "ABM3-8.000MHZ-D2Y-T", "C144380", KEEP, "", None),
    # ---- connectors, terminals, switches
    ("C7095263", "GCT", "USB4085-GF-A", "C7095263", KEEP, "", None),
    ("C6828431", "Wurth Elektronik", "7461084", "C6828431", KEEP, "", None),                  # M6 press-fit feed
    ("C2921631", "Nidec Components", "CJS-1200TB1", "C2921631", KEEP, "", None),              # BOOT switch
    (("fp", "Wuerth_REDCUBE-THR_WP-THRBU_74650074_THR", "74650074R"), "Wurth Elektronik", "74650074R", "",
     "732-74650074RCT-ND", "", None),                                                         # B T1-T8 (no LCSC listing)
    (("fp", "JST_GH_SM12B-GHS-TB_1x12-1MP_P1.25mm_Horizontal", None), "JST", "SM12B-GHS-TB(LF)(SN)", "C265421",
     "455-1574-1-ND", "", None),                                                              # A J6, input J1
    (("fp", "JST_GH_BM12B-GHS-TBT_1x12-1MP_P1.25mm_Vertical", None), "JST", "BM12B-GHS-TBT", "C20089173",
     "455-BM12B-GHS-TBTCT-ND", "", None),                                                     # B J7
    # ---- input board (had no supplier fields; JLCPCB basic parts for the passives)
    (("fp", "C_0603_1608Metric", "10nF"), "FH (Guangdong Fenghua)", "0603B103K500NT", "C57112", "311-1085-1-ND",
     "YAGEO CC0603KRX7R9BB103 (DK 311-1085-1-ND)", None),                                     # 10nF 50V X7R
    (("fp", "R_0603_1608Metric", "4.7k"), "UNI-ROYAL", "0603WAF4701T5E", "C23162", "311-4.70KHRCT-ND",
     "YAGEO RC0603FR-074K7L (DK 311-4.70KHRCT-ND)", None),
    (("fp", "R_0603_1608Metric", "10k"), "UNI-ROYAL", "0603WAF1002T5E", "C25804", "311-10.0KHRCT-ND",
     "YAGEO RC0603FR-0710KL (DK 311-10.0KHRCT-ND)", None),
    (("fp", "R_0603_1608Metric", "20k"), "UNI-ROYAL", "0603WAF2002T5E", "C4184", "311-20.0KHRCT-ND",
     "YAGEO RC0603FR-0720KL (DK 311-20.0KHRCT-ND)", None),                                    # 1 % analog divider
    (("fp", "SOT-23", "BAT54S"), "Nexperia", "BAT54S,215", "C47546", "BAT54SLT1GOSCT-ND",
     "onsemi BAT54SLT1G (DK BAT54SLT1GOSCT-ND)", None),                                       # input board clamps
    (("fp", "Molex_Micro-Fit_3.0_43045-1200_2x06_P3.00mm_Horizontal", None), "Molex", "0430451200", "C277636",
     "WM1818-ND", "", None),                                                                  # input J2
    (("fp", "SW_DIP_SPSTx08_Slide_Omron_A6S-810x_W8.9mm_P2.54mm", None), "Omron", "A6S-8104-H", "C231310",
     "39-A6S-8104-H-ND", "", None),                                                           # input SW1, SW2
]
# footprints that are not parts to buy (no order fields): holes, logos, solder jumpers, wire pads, Tag-Connect pads
NOT_PARTS = re.compile(r"MountingHole|DingoFace|SolderJumper|WirePads|Tag-Connect")
ROOTS = {"A": "DingoPDM.kicad_sch", "B": "dingoPDM-Max.kicad_sch", "IN": "input-board.kicad_sch"}
FIELDS = ("Manufacturer", "MPN", "LCSC", "Digi-Key_PN", "Alternates")


def rd(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def wr(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def block_end(t, start):
    depth, i, in_str = 0, start, False
    while i < len(t):
        c = t[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced")


def get_prop(b, name):
    m = re.search(r'\n\t\t\(property "%s" "([^"]*)"' % re.escape(name), b)
    return m.group(1) if m else None


def set_prop(b, name, value):
    """Set a symbol property; add it (hidden, at the symbol origin) when missing."""
    pat = re.compile(r'(\n\t\t\(property "%s" ")[^"]*(")' % re.escape(name))
    if pat.search(b):
        return pat.sub(lambda m: m.group(1) + value.replace('"', '\\"') + m.group(2), b, count=1)
    x, y = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", b).groups()
    nl = "\r\n" if "\r\n" in b else "\n"
    prop = (f'\n\t\t(property "{name}" "{value}"\n\t\t\t(at {x} {y} 0)\n\t\t\t(hide yes)\n\t\t\t(show_name no)\n'
            f'\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)')
    prop = prop.replace("\n", nl)
    k = b.index("\n\t\t(pin ") if "\n\t\t(pin " in b else b.index("\n\t\t(instances")
    if nl == "\r\n" and b[k - 1] == "\r":
        k -= 1
    return b[:k] + prop + b[k:]


def hierarchy(root):
    """Sheet files used by the board (the root and every sheet below it)."""
    files, todo = [], [root]
    while todo:
        f = todo.pop()
        if f in files:
            continue
        files.append(f)
        todo += re.findall(r'\(property "Sheetfile" "([^"]+)"', rd(f))
    return files


def find_row(lcsc, fp, value):
    """Row for a symbol: its LCSC number as a row key, else as a row's new LCSC number (re-run), else footprint."""
    if lcsc:
        for key in (0, 3):
            for row in PARTS:
                if isinstance(row[0], str) and row[key] == lcsc:
                    return row
    for row in PARTS:
        m = row[0]
        if not isinstance(m, str) and fp.split(":")[-1] == m[1] and (m[2] is None or value == m[2]):
            return row
    return None


def main():
    board = (sys.argv[1] if len(sys.argv) > 1 else "").upper()
    if board not in ROOTS or not os.path.exists(ROOTS.get(board, "")):
        raise SystemExit("usage: run from the board folder: python sch_bom_fields.py A|B|IN")
    changed, unmatched, parts = [], [], {}
    for fname in hierarchy(ROOTS[board]):
        t = rd(fname)
        out, pos = [], 0
        for m in re.finditer(r"\n\t\(symbol[\s(]", t):
            s = m.start() + 2
            e = block_end(t, s)
            b = t[s:e]
            lib = re.search(r'^\(symbol\s*\(lib_id "([^"]+)"\)', b)
            if lib is None:                          # a library symbol embedded at this indent (input board)
                continue
            lib = lib.group(1)
            refs = ",".join(sorted(set(re.findall(r'\(reference "([^"]+)"\)', b))))
            fp = get_prop(b, "Footprint") or ""
            if lib.startswith("power:") or refs.startswith("#"):
                continue
            if NOT_PARTS.search(fp):
                continue
            row = find_row(get_prop(b, "LCSC"), fp, get_prop(b, "Value"))
            if row is None:
                unmatched.append(f"{fname} {refs} {get_prop(b, 'Value')} {fp} LCSC={get_prop(b, 'LCSC')}")
                continue
            _, mf, mpn, lcsc, dk, alt, value = row
            new = b
            for name, v in (("Manufacturer", mf), ("MPN", mpn), ("LCSC", lcsc), ("Digi-Key_PN", dk),
                            ("Alternates", alt), ("Value", value)):
                if v is None or (v == "" and get_prop(new, name) in (None, "")):
                    continue
                if get_prop(new, name) != v:
                    new = set_prop(new, name, v)
            if new != b:
                changed.append(f"{refs}: {mpn}")
            for r in refs.split(","):
                parts[r] = mpn
            out += [t[pos:s], new]
            pos = e
        out.append(t[pos:])
        nt = "".join(out)
        if nt != t:
            wr(fname, nt)
    if unmatched:
        raise SystemExit("parts with no row in PARTS (add one):\n  " + "\n  ".join(unmatched))
    for line in changed:
        print("  bom:", line)
    print(f"board {board} BOM-field stage: {len(parts)} parts covered, "
          f"{len(changed)} symbols changed" if changed else f"board {board} BOM-field stage: {len(parts)} parts covered, nothing to change")


if __name__ == "__main__":
    main()
