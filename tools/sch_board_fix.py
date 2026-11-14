"""Board-fix schematic edits shared by board A and board B (text edits, like the other sch_*.py scripts).

usage (from the board folder, after that board's other schematic scripts):  python sch_board_fix.py A|B

Decisions: DECISIONS.md 2026-11-11 (B4-b(b), C1b, C2b, C3d, C6c, C7b) and docs/parts-audit.md (P1, P2, P9).
  * C3d  U3 CAN chip -> Microchip MCP2562FD-E/SN (same SOIC-8 pads; pin 5 = VIO on +3V3, pin 8 = STBY from the MCU).
         The embedded symbol keeps its library name; pins 5 / 8 are renamed VIO (power in) / STBY.
  * C2b  U5 FRAM -> MB85RC64TA (order code MB85RC64TAPNF-G-AWERE2, SOP-8 3.90 x 4.90 mm body, 1.27 mm pitch).
  * C1b  one 5 V converter per board: the Traco TSR 1-2450 (A: U15, B: U13) is fitted; the other two are DNP.
  * P9   capacitors on +12V that were 25 V parts -> 35 V / 50 V parts (10 uF and 47 nF).
  * C7b  120 ohm CAN terminator in series with an open solder jumper between CAN_H and CAN_L (bridge it on the board
         at the end of the bus).
  * B4-b(b) board B only: 10k from PB2 (BOOT1) to GND, so a DFU start always boots the system bootloader.
  * C6c  Manufacturer + MPN fields: on every part touched here and on the safety parts (TVS, switches, sense resistors).
  * P11 (p1a)  +5V OR-ing Schottky (A: D18, B: D4; +5VP -> +5V) -> Nexperia PMEG2010AEH, SOD123F footprint
         Diode_SMD:D_SOD-123F (290 mV max at 100 mA). The PCB footprint swap is board_fix_pcb.swap_footprint.
Digi-Key numbers that could not be confirmed are written as "TBD"; tools/sch_digikey.py fills in the confirmed ones.
"""
import glob
import os
import re
import subprocess
import sys
import uuid

BOARD = sys.argv[1].upper()
ROOT = {"A": "DingoPDM.kicad_sch", "B": "dingoPDM-Max.kicad_sch"}[BOARD]
DNP = {"A": ("U1", "U14"), "B": ("U1", "U12")}[BOARD]
FITTED = {"A": "U15", "B": "U13"}[BOARD]
CLI = os.path.join(os.environ["LOCALAPPDATA"], r"Programs\KiCad\10.0\bin\kicad-cli.exe")
KSYM = os.path.join(os.environ["LOCALAPPDATA"], r"Programs\KiCad\10.0\share\kicad\symbols")
NETLIST = os.path.join(os.environ.get("TEMP", "."), f"board{BOARD.lower()}_fix_pre.net")

# part data: (value or None, LCSC, Digi-Key, Manufacturer, MPN). Sources: docs/parts-audit.md and the PR text.
CAN = ("MCP2562FD-E/SN", "C124016", "TBD", "Microchip", "MCP2562FD-E/SN")
FRAM = ("MB85RC64TA", "C43379785", "TBD", "RAMXEED (Fujitsu)", "MB85RC64TAPNF-G-AWERE2")
REG = {"VXO78": ("CUI", "VXO7805-500-M-TR"), "OKI-78SR": ("Murata", "OKI-78SR-5/1.5-W36H-C"), "TSR": ("Traco", "TSR 1-2450")}
CAP_12V = {"C15850": (None, "C162422", "TBD", "Murata", "GRM21BR6YA106KE43L"),          # 10 uF 35 V X5R 0805
           "C520039": (None, "C3879816", "TBD", "KEMET", "C0805C473K5RAC7800")}          # 47 nF 50 V X7R 0805
SAFETY = {"C2150060": ("Infineon", "BTS70082EPAXUMA1"), "C534830": ("Infineon", "BTS70082EPAXUMA1"),
          "C3232444": ("Infineon", "BTS700121ESPXUMA1"), "C152086": ("BORN", "SMCJ20CA"),
          "C2933520": ("FOJAN", "FRC0805J122")}
SAFETY_BY_VALUE = {"BTS7004-1EPP": ("Infineon", "BTS70041EPPXUMA1", "C534825")}   # had no supplier fields (P13)
R120 = ("120R", "C17437", "TBD", "UNI-ROYAL", "0805W8F1200T5E")
R10K = ("10K", "C17414", "311-10.0KCRDKR-ND", "UNI-ROYAL", "0805W8F1002T5E")
OR5V = {"A": "D18", "B": "D4"}[BOARD]                                          # P11: +5VP -> +5V Schottky
SCHOTTKY_5V = ("PMEG2010AEH", "C110921", "1727-PMEG2010AEH,115CT-ND", "Nexperia", "PMEG2010AEH,115")
SCHOTTKY_5V_FP = "Diode_SMD:D_SOD-123F"
JP_LIB, JP_FP = "Jumper:SolderJumper_2_Open", "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"


def rd(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def wr(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def u():
    return str(uuid.uuid4())


def fmt(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


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


def top_blocks(t, head):
    out = []
    for m in re.finditer(r"\n\t\(%s[\s(]" % re.escape(head), t):
        s = m.start() + 2
        out.append((s, block_end(t, s)))
    return out


def refs_of(b):
    return set(re.findall(r'\(reference "([^"]+)"\)', b)) | set(re.findall(r'\(property "Reference" "([^"]+)"', b))


def symbol_by_ref(t, ref):
    for s, e in top_blocks(t, "symbol"):
        if ref in refs_of(t[s:e]):
            return s, e
    raise KeyError(ref)


def get_prop(b, name):
    m = re.search(r'\n\t\t\(property "%s" "([^"]*)"' % re.escape(name), b)
    return m.group(1) if m else None


def set_prop(b, name, value):
    """Set a symbol property; add it (hidden, at the symbol origin) when missing."""
    if value is None:
        return b
    pat = re.compile(r'(\n\t\t\(property "%s" ")[^"]*(")' % re.escape(name))
    if pat.search(b):
        return pat.sub(lambda m: m.group(1) + value.replace('"', '\\"') + m.group(2), b, count=1)
    x, y = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", b).groups()
    prop = (f'\n\t\t(property "{name}" "{value}"\n\t\t\t(at {x} {y} 0)\n\t\t\t(hide yes)\n\t\t\t(show_name no)\n'
            f'\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)')
    k = b.index("\n\t\t(pin ") if "\n\t\t(pin " in b else b.index("\n\t\t(instances")
    return b[:k] + prop + b[k:]


def apply_part(b, part):
    value, lcsc, dk, maker, mpn = part
    if value:
        b = set_prop(b, "Value", value)
    b = set_prop(b, "LCSC", lcsc)
    b = set_prop(b, "Digi-Key_PN", dk)
    b = set_prop(b, "Manufacturer", maker)
    return set_prop(b, "MPN", mpn)


def edit_symbol(fname, ref, fn):
    t = rd(fname)
    s, e = symbol_by_ref(t, ref)
    t = t[:s] + fn(t[s:e]) + t[e:]
    wr(fname, t)


def renew_uuids(b):
    return re.sub(r'\(uuid "[^"]+"\)', lambda m: f'(uuid "{u()}")', b)


def move_block(b, x, y, ang=None):
    """Move a block so its first (at) is (x, y); every other (at) moves by the same amount."""
    m0 = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)(?: (\d+))?\)", b)
    dx, dy = x - float(m0.group(1)), y - float(m0.group(2))
    first = [True]

    def rep(q):
        if first[0]:
            first[0] = False
            a = q.group(3) if ang is None else str(ang)
            return f"(at {fmt(x)} {fmt(y)}" + (f" {a})" if a is not None else ")")
        return f"(at {fmt(float(q.group(1)) + dx)} {fmt(float(q.group(2)) + dy)}" + (f" {q.group(3)})" if q.group(3) else ")")
    return re.sub(r"\(at ([\d.\-]+) ([\d.\-]+)(?: (\d+))?\)", rep, b)


def set_instances(b, project, path, ref):
    i = b.index("(instances")
    s = b.rfind("\n", 0, i) + 1
    e = block_end(b, i)
    ind = b[s:i]
    lines = [f"{ind}(instances", f'{ind}\t(project "{project}"', f'{ind}\t\t(path "{path}"',
             f'{ind}\t\t\t(reference "{ref}")', f"{ind}\t\t\t(unit 1)", f"{ind}\t\t)", f"{ind}\t)", f"{ind})"]
    return b[:s] + "\n".join(lines) + b[e:]


def insert_items(t, items):
    for marker in ("\n\t(sheet_instances", "\n\t(embedded_fonts"):
        if marker in t:
            k = t.index(marker)
            break
    else:
        k = t.rstrip().rindex(")")
        while t[k - 1] in "\r\n\t ":
            k -= 1
    return t[:k] + "".join("\n\t" + it for it in items) + t[k:]


def lib_symbol(lib_file, name):
    lt = rd(os.path.join(KSYM, lib_file))
    s = lt.index(f'\n\t(symbol "{name}"') + 2
    sym = lt[s:block_end(lt, s)]
    if "(extends" in sym:
        raise SystemExit(f"{name} extends another symbol: not handled")
    return sym


def embed(t, lib_id, sym):
    if f'\n\t\t(symbol "{lib_id}"' in t:
        return t
    sym = sym.replace(f'(symbol "{lib_id.split(":")[1]}"', f'(symbol "{lib_id}"', 1)
    sym = "\n".join(("\t" + ln) if ln else ln for ln in sym.split("\n"))
    k = t.index("(lib_symbols") + len("(lib_symbols")
    return t[:k] + "\n\t\t" + sym.lstrip("\t") + t[k:]


def pin_ends(sym, x, y):
    """{pin number: (x, y)} for a symbol placed at (x, y), rotation 0, not mirrored."""
    out = {}
    for px, py, num in re.findall(r'\(pin \w+ \w+\s*\(at ([\d.\-]+) ([\d.\-]+) \d+\)[\s\S]*?\(number "([^"]+)"', sym):
        out[num] = (round(x + float(px), 4), round(y - float(py), 4))
    return out


def free_box(t, w, h, margin=7.62):
    """Top-left corner (2.54 mm grid) of a w x h mm area of the sheet with no item point and no wire in it."""
    pts = [(float(a), float(b)) for a, b in re.findall(r"\((?:at|xy) ([\d.\-]+) ([\d.\-]+)", t)]
    wires = [tuple(map(float, m)) for m in re.findall(r"\(wire\s*\(pts\s*\(xy ([\d.\-]+) ([\d.\-]+)\)\s*\(xy ([\d.\-]+) ([\d.\-]+)\)", t)]
    paper = {"USLetter": (279.4, 215.9), "A4": (297, 210), "A3": (420, 297)}[re.search(r'\(paper "(\w+)"', t).group(1)]
    for oy in [2.54 * k for k in range(4, int((paper[1] - h - 10) / 2.54))]:
        for ox in [2.54 * k for k in range(4, int((paper[0] - w - 10) / 2.54))]:
            x0, y0, x1, y1 = ox - margin, oy - margin, ox + w + margin, oy + h + margin
            if any(x0 <= a <= x1 and y0 <= b <= y1 for a, b in pts):
                continue
            if any(max(a, c) >= x0 and min(a, c) <= x1 and max(b, d) >= y0 and min(b, d) <= y1 for a, b, c, d in wires):
                continue
            return ox, oy
    raise SystemExit("no free area on the sheet")


def text(s, x, y):
    s = s.replace('"', '\\"').replace("\n", "\\n")
    return (f'(text "{s}"\n\t\t(exclude_from_sim no)\n\t\t(at {fmt(x)} {fmt(y)} 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t)\n\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "{u()}")\n\t)')


def label(name, x, y, ang=0):
    just = "right bottom" if ang == 180 else "left bottom"
    return (f'(label "{name}"\n\t\t(at {fmt(x)} {fmt(y)} {ang})\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
            f'\t\t\t(justify {just})\n\t\t)\n\t\t(uuid "{u()}")\n\t)')


# ---------------------------------------------------------------- setup
if "CAN_TERM" in rd("MCU.kicad_sch"):
    raise SystemExit("board-fix edits already applied (start from the baseline)")
subprocess.run([CLI, "sch", "export", "netlist", ROOT, "-o", NETLIST], check=True, capture_output=True)
net_text = rd(NETLIST)
on_12v = set()
for blk in re.split(r"\(net\s+\(code\s+", net_text)[1:]:
    if re.search(r'\(name\s+"\+12V"\)', blk):
        on_12v |= set(re.findall(r'\(node\s+\(ref\s+"([^"]+)"\)', blk))
used = set(re.findall(r'\(ref\s+"([^"]+)"\)', net_text))
sheet_of = {}                                   # ref -> sheet path (uuids below the root) in the netlist
for blk in re.split(r"\(comp\s+\(ref\s+", net_text)[1:]:
    sheet_of[blk[1:blk.index('"', 1)]] = re.search(r'\(sheetpath\s+\(names "[^"]*"\)\s+\(tstamps "([^"]*)"\)', blk).group(1)


def live_refs(b):
    """Refs of a symbol's instances that exist in the netlist (sheets used more than once, stale paths ignored)."""
    out = set()
    for path, ref in re.findall(r'\(path "([^"]+)"\s*\(reference "([^"]+)"\)', b):
        parts = path.strip("/").split("/")[1:]
        if sheet_of.get(ref) == "/" + "".join(x + "/" for x in parts):
            out.add(ref)
    return sorted(out)
for f in glob.glob("*.kicad_sch"):
    used |= set(re.findall(r'\(reference "([^"]+)"\)', rd(f)))


def new_ref(prefix):
    n = 1
    while f"{prefix}{n}" in used or f"{prefix}{n:03d}" in used:
        n += 1
    r = f"{prefix}{n:03d}" if prefix == "#PWR" else f"{prefix}{n}"
    used.add(r)
    return r


# ---------------------------------------------------------------- C3d CAN chip (MCU sheet)
t = rd("MCU.kicad_sch")
s, e = symbol_by_ref(t, "U3")
u3 = t[s:e]
lib = re.search(r'\(lib_id "([^"]+)"\)', u3).group(1)
ls = t.index(f'\n\t\t(symbol "{lib}"')
le = block_end(t, ls + 3)
lsym = t[ls:le]
for num, old, new, kind in (("5", "Vref", "VIO", "power_in"), ("8", "Rs", "STBY", "input")):
    m = re.search(r'\(pin \w+ (\w+)(\s*\(at [^)]*\)\s*\(length [^)]*\)\s*\(name ")%s("[\s\S]*?\(number "%s")' % (old, num), lsym)
    if not m:
        raise SystemExit(f"U3 symbol pin {num} {old} not found")
    lsym = lsym[:m.start()] + f"(pin {kind} {m.group(1)}{m.group(2)}{new}{m.group(3)}" + lsym[m.end():]
t = t[:ls] + lsym + t[le:]
s, e = symbol_by_ref(t, "U3")
t = t[:s] + apply_part(t[s:e], CAN) + t[e:]
project = re.search(r'\(project "([^"]+)"', u3).group(1)
mcu_path = re.search(r'\(path "([^"]+)"', u3).group(1)
wr("MCU.kicad_sch", t)

# ---------------------------------------------------------------- C2b FRAM
edit_symbol("I2C.kicad_sch", "U5", lambda b: apply_part(b, FRAM))

# ---------------------------------------------------------------- C1b one 5 V converter
for ref in DNP + (FITTED,):
    def reg(b, ref=ref):
        v = get_prop(b, "Value")
        key = next(k for k in REG if v.upper().startswith(k.upper()))
        b = set_prop(b, "Manufacturer", REG[key][0])
        b = set_prop(b, "MPN", REG[key][1])
        if ref in DNP:
            b, n = re.subn(r"\n\t\t\(dnp no\)", "\n\t\t(dnp yes)", b, count=1)
            if n != 1:
                raise SystemExit(f"{ref}: no (dnp no) line")
        return b
    edit_symbol("Power.kicad_sch", ref, reg)


# ---------------------------------------------------------------- P11 (p1a) lower-drop Schottky on the +5V feed
def or5v(b):
    if get_prop(b, "LCSC") != "C179426" or get_prop(b, "Footprint") != "Diode_SMD:D_SOD-123":
        raise SystemExit(f"{OR5V}: not the expected PMEG10010ELR (C179426) on D_SOD-123")
    return set_prop(apply_part(b, SCHOTTKY_5V), "Footprint", SCHOTTKY_5V_FP)
edit_symbol("Power.kicad_sch", OR5V, or5v)
print(f"P11: {OR5V} -> {SCHOTTKY_5V[4]} ({SCHOTTKY_5V_FP})")

# ---------------------------------------------------------------- P9 + C6c over every sheet
changed_caps, tagged = [], []
for f in sorted(glob.glob("*.kicad_sch")):
    t = rd(f)
    out, pos = [], 0
    for s, e in top_blocks(t, "symbol"):
        b = t[s:e]
        lcsc, value = get_prop(b, "LCSC"), get_prop(b, "Value")
        refs = live_refs(b)
        if lcsc in CAP_12V and refs and all(r in on_12v for r in refs):
            b = apply_part(b, CAP_12V[lcsc])
            changed_caps += refs
        elif lcsc in CAP_12V and any(r in on_12v for r in refs):
            raise SystemExit(f"{refs}: symbol shared between +12V and other nets")
        maker = SAFETY.get(lcsc) or SAFETY_BY_VALUE.get(value)
        if maker:
            b = set_prop(set_prop(b, "Manufacturer", maker[0]), "MPN", maker[1])
            if len(maker) > 2 and not lcsc:
                b = set_prop(b, "LCSC", maker[2])
            tagged += refs
        out += [t[pos:s], b]
        pos = e
    out.append(t[pos:])
    wr(f, "".join(out))
print("P9 +12V caps re-specified:", sorted(changed_caps))
print("C6c MPN on safety parts:", len(tagged), "symbols")

# ---------------------------------------------------------------- C7b terminator (+ B4-b(b) BOOT1 pull-down on B)
t = rd("MCU.kicad_sch")
r_tpl = next(t[a:z] for a, z in top_blocks(t, "symbol")          # a 10K R_Small_US on this sheet: resistor template
             if '(lib_id "Device:R_Small_US")' in t[a:z] and get_prop(t[a:z], "Value") == "10K")
r_lib = t[t.index('\n\t\t(symbol "Device:R_Small_US"'):]
r_lib = r_lib[:block_end(r_lib, 3)]
jp_sym = lib_symbol("Jumper.kicad_sym", "SolderJumper_2_Open")
t = embed(t, JP_LIB, jp_sym)
hl = next(t[a:z] for a, z in top_blocks(t, "hierarchical_label") if '"CAN_L"' in t[a:z])


def hlabel(name, x, y, ang):
    b = hl.replace('"CAN_L"', f'"{name}"', 1)
    b = move_block(b, x, y, ang)
    b = b.replace("(justify left)", "(justify right)") if ang == 180 else b.replace("(justify right)", "(justify left)")
    return renew_uuids(b)


def resistor(ref, x, y, part):
    b = set_prop(move_block(r_tpl, x, y), "Reference", ref)
    b = set_instances(apply_part(b, part), project, mcu_path, ref)
    return renew_uuids(b)


items = []
W, H = (38.1, 27.94) if BOARD == "B" else (38.1, 15.24)
ox, oy = free_box(t, W, H)
jp_ref, rt_ref = new_ref("JP"), new_ref("R")
jx, jy = ox + 7.62, oy + 7.62
jp = resistor(jp_ref, jx, jy, (None, None, None, None, None))
jp = jp.replace('(lib_id "Device:R_Small_US")', f'(lib_id "{JP_LIB}")')
jp = set_prop(set_prop(jp, "Value", "CAN_TERM"), "Footprint", JP_FP)
for prop in ("Digi-Key_PN", "LCSC"):
    m = re.search(r'\n\t\t\(property "%s"' % prop, jp)
    if m:
        jp = jp[:m.start()] + jp[block_end(jp, m.start() + 3):]
jp = jp.replace("\n\t\t(in_bom yes)", "\n\t\t(in_bom no)", 1)          # a solder jumper is not a part to buy
jpe = pin_ends(jp_sym, jx, jy)
items += [jp, hlabel("CAN_H", *jpe["1"], 180), label("CAN_TERM", *jpe["2"])]
rx, ry = ox + 25.4, oy + 7.62
rpe = pin_ends(r_lib, rx, ry)
items += [resistor(rt_ref, rx, ry, R120), label("CAN_TERM", *rpe["1"]), hlabel("CAN_L", *rpe["2"], 0)]
items.append(text(f"CAN termination (C7b): bridge {jp_ref} only on the board at the end of the bus.", ox, oy))
made = {"jumper": jp_ref, "terminator": rt_ref}

if BOARD == "B":
    # PB2 (BOOT1) pin end of U4: drop its no-connect flag, put a local label there
    s, e = symbol_by_ref(t, "U4")
    u4 = t[s:e]
    X, Y, rot = map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+) (\d+)\)", u4).groups())
    if rot != 0 or "(mirror" in u4[:300]:
        raise SystemExit("U4 rotated/mirrored: pin math not handled")
    lib4 = re.search(r'\(lib_id "([^"]+)"\)', u4).group(1)
    l4 = t[t.index(f'\n\t\t(symbol "{lib4}"'):]
    l4 = l4[:block_end(l4, 3)]
    px, py = next((round(X + float(a), 4), round(Y - float(c), 4)) for a, c, n in
                  re.findall(r'\(pin \w+ \w+\s*\(at ([\d.\-]+) ([\d.\-]+) \d+\)[\s\S]*?\(name "([^"]+)"', l4)
                  if n == "PB2" or n.startswith("PB2-") or n.startswith("PB2/"))
    pat = re.compile(r"\n\t\(no_connect\s*\(at %s %s\)\s*\(uuid \"[^\"]+\"\)\s*\)" % (re.escape(fmt(px)), re.escape(fmt(py))))
    t, n = pat.subn("", t)
    if n != 1:
        raise SystemExit(f"PB2 no-connect at {px},{py}: {n} matches")
    items.append(label("BOOT1", px, py, 0 if px > X else 180))
    bx, by = ox + 7.62, oy + 20.32
    bpe = pin_ends(r_lib, bx, by)
    b_ref = new_ref("R")
    items += [resistor(b_ref, bx, by, R10K), label("BOOT1", *bpe["1"])]
    g0, g1 = next((a, z) for a, z in top_blocks(t, "symbol") if '(lib_id "power:GND")' in t[a:z])
    pr = new_ref("#PWR")
    g = move_block(t[g0:g1], *bpe["2"], 0)
    g = set_instances(set_prop(g, "Reference", pr), project, mcu_path, pr)
    items.append(renew_uuids(g))
    items.append(text(f"{b_ref}: holds PB2 (BOOT1) low so DFU starts the system bootloader (B4-b(b)).", bx + 5.08, by))
    made["boot1"] = b_ref
t = insert_items(t, items)
wr("MCU.kicad_sch", t)
print("new parts:", made, "at sheet area", (ox, oy))
print("board-fix schematic edits OK")
