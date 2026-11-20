"""Hardware protection stage for board A and board B (ADR-2026-11-20-presim-findings items 1, 2, 4; job hwprotect).

  python   tools/hw_protect.py sch A|B                               (from the board folder, last schematic stage)
  python.exe (KiCad 9) tools/hw_protect.py pcb <board.kicad_pcb> <netlist.net> A|B   (last PCB stage)

Schematic (text edits, like the other sch_*.py stages; refs, footprints and nets of existing parts are not touched):
  * New parts, both boards:
      NRST  100 nF X7R 0402 (Samsung CL05B104KO5NNNC, LCSC C1525) NRST -> GND. ST AN4488 Rev 4 section 2.3.3 /
            Figure 6: no external reset circuit needed, a 100 nF NRST capacitor improves EMS.
      VDDA  1 uF X7R 0402 (CCTC TCC0402X7R105K100AT, LCSC C47325373) + 100 nF X7R 0402 (C1525) VDDA -> GND behind the
            ferrite FB1. AN4488 section 2.2: "The VDDA pin must be connected to two external decoupling capacitors
            (100 nF Ceramic + 1 uF Tantalum or Ceramic)". A local label VDDA on U4 pin 13 joins them: the net
            Net-(U4-VDDA) becomes /MCU/VDDA (name only).
      USB   one ESD diode per data line, Nexperia PESD5V0F1BL,315 (DFN1006-2 / SOD-882, bidirectional, 0.4 pF, VRWM
            5.5 V, IEC 61000-4-2, Tj -40..125 C; LCSC C45961): USB_D+ / USB_D- -> GND. (A USBLC6-2 array in SOT-23-6
            or SOT-666 has no top-side site on either board with room for its taps and GND via without moving parts.)
  * Board B only, 85 C parts -> 125 C grades in the same footprints (docs/system-verification.md section 6):
      Y1  8 MHz ABM3-8.000MHZ-D2Y-T (-40..85 C) -> ECS ECS-80-18-30Q-CES-TR (-40..125 C, AEC-Q200, 18 pF load like the
          ABM3, ESR 100 Ohm vs 140, 5.0 x 3.2 mm 2-pad); alternate ECS-80-18-30Q-VY-TR (-40..105 C, LCSC C6844210)
      C3  +12V 10 uF 35 V X5R -> TDK CGA4J1X7R1H475KT0Y0N 4.7 uF 50 V X7R AEC-Q200 (LCSC C694229): no 0805 10 uF
          X7R / X7S part >= 35 V exists at JLCPCB; the 50 V part keeps more capacitance at 12-16 V bias
      C4  +5VP 22 uF X5R -> Murata GRM21BZ71A226ME15L 22 uF 10 V X7R (LCSC C907991)
      C6  +3V3 10 uF X5R -> Samsung CL21B106KPQNNNE 10 uF 10 V X7R (LCSC C32635)
      C10 VCAP_1 and C15 +3V3 4.7 uF X5R -> Samsung CL21B475KAFNNNE 4.7 uF 25 V X7R (LCSC C98195)
    U13 TSR 1-2450 stays (-40..85 C): no 5 V converter rated above 85-90 C fits the SIP-3 TSR footprint or the two
    DNP converter footprints (Traco TSR 1 / TSR 1E 85 C, RECOM R-78K 90 C; docs/parts-audit.md section 11): needs a
    footprint change (reported, not done here).
  * Board B freewheel diodes D13 D15 D17 D19 D25-D28 (BYG23M, GND -> PF_OUT) stay fitted (FREEWHEEL_DNP False).
    Infineon BTS70012-1ESP / BTS7004-1EPP data sheets 8.4.1: "The reverse current through the output stage must be
    limited by the connected load": a diode from GND to OUT shorts a reversed battery. Removing them moves the A/C
    clutch / fan turn-off energy and all motor PWM into the switch clamp (verify_power / verify_switching
    --no-freewheel-b: A/C clutch 0.55-2.2 J vs EAS 0.15 J), so the fix needs another freewheel path (design choice).
PCB (KiCad 9 python), top side only, no other footprint / pad / zone moved (tools/board_semdiff.py proves it):
  * VDDA: the VDDA copper (U4 pin 13 -> FB1 pad 2) is walled in by the U4 fan-out: no via fits beside it (searched
    4 mm). A 0.7 / 0.3 mm via goes into FB1 pad 2 (filled + capped, like the other via-in-pad sites: fab-notes.md);
    other-net inner / bottom tracks it touches (board B: In2 B_IN6 / B_IN8) are ripped and re-routed by the grid
    router (tracks only, nets unchanged). The two VDDA capacitors sit at the nearest clean sites (SITES) and join it on
    B.Cu (grid router).
  * NRST capacitor at SITES["nrst"], one top track to the NRST via beside it.
  * USB ESD diodes: the first clean site near ESD_ANCHOR (nearest first) whose line pad reaches a D+ / D- via with a
    top track and whose GND pad gets a GND via: at the MCU end of the lines, beside the vias that take them from
    U4 down to In2 (the connector end has no room).
  * Every GND pad gets its own via to the In1 GND plane (0.8 / 0.4 mm, else 0.7 / 0.3) on a short top track, or a
    track to the nearest GND via; GND pads connect solid to the pour. Checks: exact courtyards, copper clearance
    CLR (board rule 8 mil + margin), drills, board edge, rule areas. Reference texts of the new parts are hidden.
  * Net rename from the schematic label (Net-(U4-VDDA) -> /MCU/VDDA) on every pad, track, via and zone; the
    freewheel diodes get the exclude-from-BOM / position-file attributes.
Idempotent: a new part already on the board is re-checked and its copper left as it is.
"""
import math
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------------------------------------ part data
# (Value, Footprint, LCSC, Digi-Key_PN, Manufacturer, MPN, Datasheet, Alternates)
C100N = ("100nF", "Capacitor_SMD:C_0402_1005Metric", "C1525", "1276-1043-1-ND", "Samsung Electro-Mechanics",
         "CL05B104KO5NNNC", "https://www.lcsc.com/datasheet/C1525.pdf",
         "YAGEO CC0402KRX7R7BB104 (X7R 16 V 0402)")
C1U = ("1uF", "Capacitor_SMD:C_0402_1005Metric", "C47325373", "", "CCTC", "TCC0402X7R105K100AT",
       "https://www.lcsc.com/datasheet/C47325373.pdf",
       "YAGEO CC0402KRX7R6BB105 (X7R 10 V 0402, LCSC C7500381)")
ESD = ("PESD5V0F1BL", "Diode_SMD:D_SOD-882", "C45961", "1727-3825-1-ND", "Nexperia", "PESD5V0F1BL,315",
       "https://assets.nexperia.com/documents/data-sheet/PESD5V0F1BL.pdf",
       "Nexperia PESD5V0F1BLZ (LCSC C6952437); BORN PESD5V0F1BL-N (LCSC C2929237)")
NEW = [  # role, sheet, part, pin 1 net label (None: power GND), pin 2 net label
    ("nrst", "MCU.kicad_sch", C100N),
    ("vdda1", "MCU.kicad_sch", C1U),
    ("vdda2", "MCU.kicad_sch", C100N),
    ("esd_p", "Connectors.kicad_sch", ESD),
    ("esd_n", "Connectors.kicad_sch", ESD),
]
# board B part swaps: ref -> (sheet, old LCSC, new part (Value, LCSC, Digi-Key, Manufacturer, MPN, Datasheet, Alternates))
SWAPS_B = {
    "Y1": ("MCU.kicad_sch", "C144380", ("8MHz", "", "50-ECS-80-18-30Q-CES-TRCT-ND", "ECS Inc.", "ECS-80-18-30Q-CES-TR",
           "https://ecsxtal.com/store/pdf/ECS-30Q-CES.pdf",
           "ECS ECS-80-18-30Q-VY-TR (-40..105 C, LCSC C6844210)")),
    "C3": ("Power.kicad_sch", "C162422", ("4.7uF", "C694229", "445-CGA4J1X7R1H475KT0Y0NCT-ND", "TDK",
           "CGA4J1X7R1H475KT0Y0N", "https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=CGA4J1X7R1H475KT0Y0N",
           "HRE CGA0805X7R475K500MT (4.7 uF 50 V X7R 0805, LCSC C6119944)")),
    "C4": ("Power.kicad_sch", "C45783", ("22uF", "C907991", "490-10750-1-ND", "Murata", "GRM21BZ71A226ME15L",
           "https://www.murata.com/en-us/products/productdetail?partno=GRM21BZ71A226ME15L",
           "CCTC TCC0805X7R226M100FT (22 uF 10 V X7R 0805, LCSC C53133025)")),
    "C6": ("Power.kicad_sch", "C15850", ("10uF", "C32635", "1276-2891-1-ND", "Samsung Electro-Mechanics",
           "CL21B106KPQNNNE", "https://www.lcsc.com/datasheet/C32635.pdf", "")),
    "C10": ("MCU.kicad_sch", "C1779", ("4.7uF", "C98195", "1276-2399-1-ND", "Samsung Electro-Mechanics",
            "CL21B475KAFNNNE", "https://www.lcsc.com/datasheet/C98195.pdf", "")),
    "C15": ("MCU.kicad_sch", "C1779", ("4.7uF", "C98195", "1276-2399-1-ND", "Samsung Electro-Mechanics",
            "CL21B475KAFNNNE", "https://www.lcsc.com/datasheet/C98195.pdf", "")),
}
FREEWHEEL_B = {"D13", "D15", "D17", "D19", "D25", "D26", "D27", "D28"}
FREEWHEEL_LCSC = "C141573"                       # Vishay BYG23M-E3/TR
# Kept FITTED (False): without them the A/C clutch (L 50-200 mH ASSUMED) turns off into the BTS7004 clamp at 0.55-2.2 J
# vs EAS 0.15 J, and fan PWM above a few Hz overheats the BTS70012 clamp (tools/verify_power.py / verify_switching.py
# --no-freewheel-b). Removing them is only safe with another freewheel path: a design choice (report / BACKLOG).
FREEWHEEL_DNP = False
ROOTS = {"A": "DingoPDM.kicad_sch", "B": "dingoPDM-Max.kicad_sch"}
USB_CONN = {"A": "J5", "B": "J2"}
OLD_VBUS = {"A": "Net-(D15-A)", "B": "Net-(D6-A)"}
NEW_NETS = {"VDDA": "/MCU/VDDA", "VBUS": "/Connectors/VBUS"}
NS = uuid.UUID("6b1d6c2e-58a4-4c55-9a59-0d1e5ea0c0de")


# ------------------------------------------------------------------------------------------------ schematic
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


def get_prop(b, name):
    m = re.search(r'\n\t\t\(property "%s" "([^"]*)"' % re.escape(name), b)
    return m.group(1) if m else None


def set_prop(b, name, value, hide=True):
    pat = re.compile(r'(\n\t\t\(property "%s" ")[^"]*(")' % re.escape(name))
    if pat.search(b):
        return pat.sub(lambda m: m.group(1) + value.replace('"', '\\"') + m.group(2), b, count=1)
    x, y = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", b).groups()
    prop = (f'\n\t\t(property "{name}" "{value}"\n\t\t\t(at {x} {y} 0)\n' + ("\t\t\t(hide yes)\n" if hide else "")
            + '\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n'
            '\t\t\t\t)\n\t\t\t)\n\t\t)')
    k = b.index("\n\t\t(pin ") if "\n\t\t(pin " in b else b.index("\n\t\t(instances")
    return b[:k] + prop + b[k:]


def set_flag(b, name, value):
    b, n = re.subn(r"\n\t\t\(%s (yes|no)\)" % name, f"\n\t\t({name} {value})", b, count=1)
    if n != 1:
        raise SystemExit(f"no ({name} ...) line")
    return b


def symbol_by_ref(t, ref):
    hits = [(s, e) for s, e in top_blocks(t, "symbol") if f'(reference "{ref}")' in t[s:e]]
    if len(hits) != 1:
        raise SystemExit(f"{ref}: {len(hits)} symbols")
    return hits[0]


def lib_block(t, lib_id):
    k = t.index(f'\n\t\t(symbol "{lib_id}"') + 1
    return t[k:block_end(t, k + 2)]


def pin_end(t, ref, num):
    """Sheet coordinates of pin `num` of the (rotation 0, not mirrored) symbol `ref`."""
    s, e = symbol_by_ref(t, ref)
    b = t[s:e]
    X, Y, rot = map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+) (\d+)\)", b).groups())
    if rot != 0 or "(mirror" in b[:400]:
        raise SystemExit(f"{ref}: rotated / mirrored symbol: pin math not handled")
    lib = lib_block(t, re.search(r'\(lib_id "([^"]+)"\)', b).group(1))
    for px, py, n in re.findall(r'\(pin \w+ \w+\s*\(at ([\d.\-]+) ([\d.\-]+) \d+\)[\s\S]*?\(number "([^"]+)"', lib):
        if n == num:
            return round(X + float(px), 4), round(Y - float(py), 4)
    raise SystemExit(f"{ref}: no pin {num}")


def pin_ends(lib, x, y):
    return {n: (round(x + float(px), 4), round(y - float(py), 4))
            for px, py, n in re.findall(r'\(pin \w+ \w+\s*\(at ([\d.\-]+) ([\d.\-]+) \d+\)[\s\S]*?\(number "([^"]+)"', lib)}


def move_block(b, x, y):
    m0 = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)(?: (\d+))?\)", b)
    dx, dy = x - float(m0.group(1)), y - float(m0.group(2))
    return re.sub(r"\(at ([\d.\-]+) ([\d.\-]+)(?: (\d+))?\)",
                  lambda q: f"(at {fmt(float(q.group(1)) + dx)} {fmt(float(q.group(2)) + dy)}"
                            + (f" {q.group(3)})" if q.group(3) else ")"), b)


def renew_uuids(b):
    return re.sub(r'\(uuid "[^"]+"\)', lambda m: f'(uuid "{u()}")', b)


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


def embed(t, lib_id, sym):
    if f'\n\t\t(symbol "{lib_id}"' in t:
        return t
    sym = sym.replace(f'(symbol "{lib_id.split(":")[1]}"', f'(symbol "{lib_id}"', 1)
    sym = "\n".join(("\t" + ln) if ln else ln for ln in sym.split("\n"))
    k = t.index("(lib_symbols") + len("(lib_symbols")
    return t[:k] + "\n\t\t" + sym.lstrip("\t") + t[k:]


def free_box(t, w, h, margin=7.62):
    pts = [(float(a), float(b)) for a, b in re.findall(r"\((?:at|xy) ([\d.\-]+) ([\d.\-]+)", t)]
    wires = [tuple(map(float, m)) for m in
             re.findall(r"\(wire\s*\(pts\s*\(xy ([\d.\-]+) ([\d.\-]+)\)\s*\(xy ([\d.\-]+) ([\d.\-]+)\)", t)]
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


def label(name, x, y, ang=0):
    just = "right bottom" if ang == 180 else "left bottom"
    return (f'(label "{name}"\n\t\t(at {fmt(x)} {fmt(y)} {ang})\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t)\n\t\t\t(justify {just})\n\t\t)\n\t\t(uuid "{u()}")\n\t)')


def text(s, x, y):
    s = s.replace('"', '\\"').replace("\n", "\\n")
    return (f'(text "{s}"\n\t\t(exclude_from_sim no)\n\t\t(at {fmt(x)} {fmt(y)} 0)\n\t\t(effects\n\t\t\t(font\n'
            f'\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "{u()}")\n\t)')


def apply_part(b, part):
    value, fp, lcsc, dk, maker, mpn, ds, alt = part
    for name, v in (("Value", value), ("Footprint", fp), ("LCSC", lcsc), ("Digi-Key_PN", dk), ("Manufacturer", maker),
                    ("MPN", mpn), ("Datasheet", ds), ("Alternates", alt)):
        if v or get_prop(b, name) not in (None, ""):
            b = set_prop(b, name, v or "")
    return b


def used_refs():
    out = set()
    for f in os.listdir("."):
        if f.endswith(".kicad_sch"):
            out |= set(re.findall(r'\(reference "([^"]+)"\)', rd(f)))
    return out


def next_ref(used, prefix):
    nums = [int(r[len(prefix):]) for r in used if r.startswith(prefix) and r[len(prefix):].isdigit()]
    r = f"{prefix}{max(nums) + 1}"
    used.add(r)
    return r


def gnd_symbol(t, x, y, ref, project, path):
    g0, g1 = next((a, z) for a, z in top_blocks(t, "symbol") if '(lib_id "power:GND")' in t[a:z])
    g = move_block(t[g0:g1], x, y)
    g = set_instances(set_prop(g, "Reference", ref), project, path, ref)
    return renew_uuids(g)


def new_symbol(tpl, lib_id, x, y, ref, part, pins, project, path):
    """A symbol instance built on a template instance of the same sheet: header flags kept, properties / pins new."""
    head = tpl[:tpl.index("\n\t\t(property")]
    head = re.sub(r'\(lib_id "[^"]+"\)', f'(lib_id "{lib_id}")', head, count=1)
    head = re.sub(r"\(at [\d.\-]+ [\d.\-]+ \d+\)", f"(at {fmt(x)} {fmt(y)} 0)", head, count=1)
    head = re.sub(r"\n\t\t\(fields_autoplaced yes\)", "", head)
    for flag, v in (("in_bom", "yes"), ("on_board", "yes"), ("dnp", "no")):
        head = set_flag(head + "\n\t\t(property", flag, v)[:-len("\n\t\t(property")]
    props = []
    for k, (name, v) in enumerate((("Reference", ref), ("Value", part[0]), ("Footprint", part[1]), ("Datasheet", part[6]),
                                   ("Description", ""))):
        props.append(f'\t\t(property "{name}" "{v}"\n\t\t\t(at {fmt(x + 2.54)} {fmt(y - 1.27 + 2.54 * k)} 0)\n'
                     + ("" if k < 2 else "\t\t\t(hide yes)\n")
                     + "\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n"
                     "\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n" + ("\t\t\t\t(justify left)\n" if k < 2 else "") + "\t\t\t)\n\t\t)")
    pin_txt = [f'\t\t(pin "{p}"\n\t\t\t(uuid "{u()}")\n\t\t)' for p in pins]
    b = head + "\n" + "\n".join(props) + "\n" + "\n".join(pin_txt) + "\n\t\t(instances\n\t\t)\n\t)"
    b = set_instances(b, project, path, ref)
    b = apply_part(b, part)
    return renew_uuids(b)


def sch(board):
    root = ROOTS[board]
    if not os.path.exists(root):
        raise SystemExit("run from the board folder")
    t_mcu = rd("MCU.kicad_sch")
    if '(label "VDDA"' in t_mcu:
        print("hw_protect sch: already applied")
        return
    used = used_refs()
    # ---------------------------------------------------------------- MCU sheet: NRST + VDDA capacitors
    s, e = symbol_by_ref(t_mcu, "U4")
    u4 = t_mcu[s:e]
    project = re.search(r'\(project "([^"]+)"', u4).group(1)
    mcu_path = re.search(r'\(path "([^"]+)"', u4).group(1)
    c_tpl = next(t_mcu[a:z] for a, z in top_blocks(t_mcu, "symbol")
                 if '(lib_id "Device:C_Small")' in t_mcu[a:z] and get_prop(t_mcu[a:z], "Value") == "100nF")
    c_lib = lib_block(t_mcu, "Device:C_Small")
    ox, oy = free_box(t_mcu, 45.72, 20.32)
    items, made = [], {}
    vdda_pin = pin_end(t_mcu, "U4", "13")
    items.append(label("VDDA", *vdda_pin, 180))
    for k, (role, sheet, part) in enumerate(n for n in NEW if n[1] == "MCU.kicad_sch"):
        ref = next_ref(used, "C")
        x, y = ox + 7.62 + 15.24 * k, oy + 10.16
        c = new_symbol(c_tpl, "Device:C_Small", x, y, ref, part, ["1", "2"], project, mcu_path)
        pe = pin_ends(c_lib, x, y)
        items += [c, label("NRST" if role == "nrst" else "VDDA", *pe["1"]),
                  gnd_symbol(t_mcu, *pe["2"], next_ref(used, "#PWR0"), project, mcu_path)]
        made[role] = ref
    items.append(text(f"hwprotect (ADR-2026-11-20-presim-findings 4): {made['nrst']} NRST 100 nF (ST AN4488 2.3.3); "
                      f"{made['vdda1']} 1 uF + {made['vdda2']} 100 nF on VDDA behind FB1 (AN4488 2.2).", ox, oy))
    wr("MCU.kicad_sch", insert_items(t_mcu, items))
    # ---------------------------------------------------------------- Connectors sheet: USB ESD diodes
    t = rd("Connectors.kicad_sch")
    s, e = symbol_by_ref(t, USB_CONN[board])
    jb = t[s:e]
    c_path = re.search(r'\(path "([^"]+)"', jb).group(1)
    ksym = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\KiCad\10.0\share\kicad\symbols", "Device.kicad_sym")
    lt = rd(ksym)
    k = lt.index('\n\t(symbol "D_TVS"') + 1
    tvs_lib = lt[k:block_end(lt, k + 1)]
    if "(extends" in tvs_lib:
        raise SystemExit("Device:D_TVS extends another symbol: not handled")
    t = embed(t, "Device:D_TVS", tvs_lib)
    gl = next(t[a_:z_] for a_, z_ in top_blocks(t, "global_label") if '"USB_D+"' in t[a_:z_])
    ox, oy = free_box(t, 38.1, 20.32)
    pe0 = pin_ends(lib_block(t, "Device:D_TVS"), 0, 0)
    items = []

    def glabel(name, px, py, ang):
        g = move_block(gl.replace('"USB_D+"', f'"{name}"', 1), px, py)
        g = re.sub(r"\(at ([\d.\-]+) ([\d.\-]+) \d+\)", lambda q: f"(at {q.group(1)} {q.group(2)} {ang})", g, count=1)
        g = g.replace("(justify left)", "(justify right)") if ang == 180 else g.replace("(justify right)", "(justify left)")
        return renew_uuids(g)
    for k, (role, net) in enumerate((("esd_p", "USB_D+"), ("esd_n", "USB_D-"))):
        ref = next_ref(used, "D")
        x, y = ox + 12.7 + 15.24 * k, oy + 10.16
        items.append(new_symbol(jb, "Device:D_TVS", x, y, ref, ESD, ["1", "2"], project, c_path))
        pe = {n: (round(x + px, 4), round(y + py, 4)) for n, (px, py) in pe0.items()}
        left, right = sorted(pe, key=lambda n: pe[n][0])
        items += [glabel(net, *pe[left], 180), gnd_symbol(t, *pe[right], next_ref(used, "#PWR0"), project, c_path)]
        made[role] = ref
    items.append(text(f"hwprotect: {made['esd_p']} / {made['esd_n']} USB data-line ESD diodes (IEC 61000-4-2, 0.4 pF).", ox, oy))
    wr("Connectors.kicad_sch", insert_items(t, items))
    # ---------------------------------------------------------------- board B: 125 C parts, freewheel diodes DNP
    if board == "B":
        for r, (sheet, old, part) in SWAPS_B.items():
            t = rd(sheet)
            s, e = symbol_by_ref(t, r)
            b = t[s:e]
            if get_prop(b, "LCSC") not in (old, part[1] or "-"):
                raise SystemExit(f"{r}: LCSC {get_prop(b, 'LCSC')}, expected {old}")
            value, lcsc, dk, maker, mpn, ds, alt = part
            for name, v in (("Value", value), ("LCSC", lcsc), ("Digi-Key_PN", dk), ("Manufacturer", maker), ("MPN", mpn),
                            ("Datasheet", ds), ("Alternates", alt)):
                if v or get_prop(b, name) is not None:      # no empty new property (PCB parity)
                    b = set_prop(b, name, v)
            wr(sheet, t[:s] + b + t[e:])
            print(f"  {r}: {mpn}")
        seen = set(FREEWHEEL_B) if not FREEWHEEL_DNP else set()
        for f in (sorted(os.listdir(".")) if FREEWHEEL_DNP else []):
            if not f.endswith(".kicad_sch"):
                continue
            t = rd(f)
            out, pos = [], 0
            for s, e in top_blocks(t, "symbol"):
                b = t[s:e]
                refs = set(re.findall(r'\(reference "([^"]+)"\)', b))
                if not refs or not refs & FREEWHEEL_B or get_prop(b, "LCSC") != FREEWHEEL_LCSC:
                    continue
                seen |= refs & FREEWHEEL_B
                b = set_flag(set_flag(set_flag(b, "dnp", "yes"), "in_bom", "no"), "in_pos_files", "no")
                out += [t[pos:s], b]
                pos = e
            if out:
                wr(f, "".join(out) + t[pos:])
        if seen != FREEWHEEL_B:
            raise SystemExit(f"freewheel diodes found {sorted(seen)}, expected {sorted(FREEWHEEL_B)}")
        if FREEWHEEL_DNP:
            print("  freewheel diodes do not fit:", ", ".join(sorted(FREEWHEEL_B, key=lambda r: int(r[1:]))))
    print("hw_protect sch:", made)


# ------------------------------------------------------------------------------------------------ PCB
# Sites (top side; board A and board B share the MCU / USB layout, checked per board): (x, y, rotation)
SITES = {
    "nrst": (-4.2, 48.2, 270),
    "vdda1": (-1.9, 52.2, 270),
    "vdda2": (3.9, 51.9, 90),
}
VIA_D, VIA_DRILL = 0.8, 0.4
CLR, TW = 0.215, 0.2032                         # board rules: 8 mil track / 8 mil clearance (+ margin)
VIP_D, VIP_DRILL = 0.7, 0.3
ESD_R = 3.0
# USB ESD diodes sit at the MCU end of the data lines, beside the D+ / D- vias at (0.51, 32.13) / (1.65, 31.37) that take
# the lines from U4 (F.Cu) down to In2: the connector end has no free top-side room on either board without moving
# parts (searched: 4 mm around the In2 pair beside U2; every GND via spot there hits the In1 / In2 USB lines)
ESD_ANCHOR = {"USB_D+": (0.2, 30.8), "USB_D-": (1.8, 30.2)}                       # via in FB1's pad (filled + capped)


def find_roles(comps, padnet):
    """{role: ref} of the parts this stage adds (found in the netlist by footprint + nets)."""
    roles = {}
    for r, c in comps.items():
        nets = {p: n for (rr, p), n in padnet.items() if rr == r}
        if c["footprint"] == ESD[1] and "USB_D+" in nets.values():
            roles["esd_p"] = r
        elif c["footprint"] == ESD[1] and "USB_D-" in nets.values():
            roles["esd_n"] = r
        elif c["footprint"] == C100N[1] and nets.get("1") == "/MCU/NRST":
            roles["nrst"] = r
        elif c["footprint"] == C1U[1] and nets.get("1") == NEW_NETS["VDDA"]:
            roles["vdda1" if c["value"] == "1uF" else "vdda2"] = r
    return roles


def later_refs(netfile):
    """Refs this (last) stage places: earlier PCB stages skip them in their 'every part placed' checks."""
    sys.path.insert(0, HERE)
    import netlist_pins
    nl = netlist_pins.parse(netfile)
    padnet = {(r, p): n for r, rows in nl.items() for p, fn, n in rows}
    text = open(netfile, encoding="utf-8").read().split("(libparts")[0]
    comps = {}
    for blk in re.split(r'\(comp\s+\(ref\s+"', text)[1:]:
        ref = blk[:blk.index('"')]
        fp = re.search(r'\(footprint\s+"([^"]*)"\)', blk)
        comps[ref] = {"footprint": fp.group(1) if fp else "", "value": re.search(r'\(value\s+"([^"]*)"\)', blk).group(1)}
    return set(find_roles(comps, padnet).values())


def pcb(path, netfile, board):
    import pcbnew
    sys.path.insert(0, HERE)
    import board_fix_pcb as F
    import netlist_pins
    import route_board_a as R
    import pcb_rework
    mm, tomm = pcbnew.FromMM, pcbnew.ToMM
    R.TW, R.CL = TW, CLR                                  # the grid router's track / clearance follow the board rules

    def V(x, y):
        return pcbnew.VECTOR2I(mm(x), mm(y))

    def xy(it):
        p = it.GetPosition()
        return tomm(p.x), tomm(p.y)

    comps = F.read_netlist(netfile)
    nl = netlist_pins.parse(netfile)
    padnet = {(r, p): n for r, rows in nl.items() for p, fn, n in rows}
    b = pcbnew.LoadBoard(path)

    def netinfo(name):
        ni = b.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(b, name)
            ni.thisown = False
            b.Add(ni)
        return ni

    # ---------------------------------------------------------------- 1. net renames from the new labels
    renames = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            want = padnet.get((f.GetReference(), p.GetNumber()))
            have = p.GetNetname()
            if want and have and want != have:
                if renames.get(have, want) != want:
                    raise SystemExit(f"net {have}: renamed to both {renames[have]} and {want}")
                renames[have] = want
    allowed = {"Net-(U4-VDDA)": NEW_NETS["VDDA"], OLD_VBUS[board]: NEW_NETS["VBUS"]}
    for old, new in renames.items():
        if allowed.get(old) != new:
            raise SystemExit(f"unexpected net change {old} -> {new} (only {allowed} are intended)")
    if renames:
        items = [p for f in b.GetFootprints() for p in f.Pads()] + list(b.GetTracks()) + list(b.Zones())
        n = 0
        for it in items:
            if it.GetNetname() in renames:
                it.SetNet(netinfo(renames[it.GetNetname()]))
                n += 1
        print(f"  nets renamed: {renames} ({n} items)")
    # ---------------------------------------------------------------- 2. board B: freewheel diodes out of BOM / CPL
    if board == "B" and FREEWHEEL_DNP:
        for r in sorted(FREEWHEEL_B):
            fp = b.FindFootprintByReference(r)
            if not comps[r]["dnp"]:
                raise SystemExit(f"{r}: not do-not-fit in the schematic (run hw_protect.py sch B)")
            fp.SetDNP(True)
            fp.SetExcludedFromBOM(True)
            fp.SetExcludedFromPosFiles(True)
        print("  freewheel diodes: do not fit, excluded from BOM and position files")
    # ---------------------------------------------------------------- 2b. VDDA via in FB1's VDDA pad
    # The VDDA copper (U4 pin 13 -> FB1 pad 2) is walled in by the U4 fan-out on the top layer: no via fits beside it
    # (searched 4 mm around). The via goes into FB1 pad 2 (0.6 / 0.3 mm, filled + capped like the other via-in-pad
    # sites: hardware/fab/*/fab-notes.md); inner / bottom tracks of other nets it would touch (board B: In2 B_IN6 /
    # B_IN8) are ripped and re-routed around it by the grid router (track change only, nets unchanged).
    fb_pad = next(p for p in b.FindFootprintByReference("FB1").Pads() if p.GetNumber() == "2")
    fb_xy = xy(fb_pad)
    if fb_pad.GetNetname() != NEW_NETS["VDDA"]:
        raise SystemExit(f"FB1 pad 2 is on {fb_pad.GetNetname()}, expected {NEW_NETS['VDDA']}")
    have = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == NEW_NETS["VDDA"]
            and math.hypot(xy(t)[0] - fb_xy[0], xy(t)[1] - fb_xy[1]) < 0.01]
    if not have:
        ring = pcbnew.SHAPE_CIRCLE(V(*fb_xy), mm(VIP_D / 2))
        rip = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetLayer() != pcbnew.F_Cu
               and t.GetNetname() != NEW_NETS["VDDA"] and t.GetEffectiveShape(t.GetLayer()).Collide(ring, mm(CLR))]
        if any(t.GetNetname() in ("GND", "+12V", "+3V3", "+5V") for t in rip):
            raise SystemExit("VDDA via-in-pad: would cut a power track")
        ripped = sorted({t.GetNetname() for t in rip})
        b = pcb_rework.remove_and_reload(b, rip, path)
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(V(*fb_xy))
        v.SetWidth(mm(VIP_D))
        v.SetDrill(mm(VIP_DRILL))
        v.SetNet(b.FindNet(NEW_NETS["VDDA"]))
        b.Add(v)
        if ripped:
            R.setup(b, (-24.0, 26.0, 30.0, 61.5))
            for n in ripped:
                if not pcb_rework.reconnect(R, b, n):
                    raise SystemExit(f"{n}: re-route around the VDDA via failed")
            print(f"  VDDA via in FB1 pad 2 at {fb_xy}; re-routed around it: {ripped}")
        else:
            print(f"  VDDA via in FB1 pad 2 at {fb_xy}")
    # ---------------------------------------------------------------- 3. new parts
    roles = find_roles(comps, padnet)
    if sorted(roles) != sorted(list(SITES) + ["esd_n", "esd_p"]):
        raise SystemExit(f"new parts in the netlist: {roles}, expected roles {sorted(SITES)} + esd_p / esd_n")
    edge = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(edge)
    added = []
    for role, (x, y, rot) in SITES.items():
        ref = roles[role]
        fp = b.FindFootprintByReference(ref)
        if fp is None:
            fp = new_footprint(b, F, pcbnew, comps[ref], padnet, netinfo)
            fp.SetPosition(V(x, y))
            fp.SetOrientationDegrees(rot)
            added.append(ref)
        site_check(b, fp, pcbnew, tomm, edge)
        fp.Reference().SetVisible(False)
    # USB ESD diodes: the first clean site (0.1 mm grid, nearest first, rotations 0 / 90 / 180 / 270) within 4 mm of the
    # line's In2 track from which its pad joins a via ON that track (top track) and its GND pad gets a GND via
    if not os.environ.get("HWP_PLACE_ONLY"):
        K0 = Copper(b, pcbnew, mm, tomm, V, edge)
        for role, net, anchor in (("esd_p", "USB_D+", ESD_ANCHOR["USB_D+"]), ("esd_n", "USB_D-", ESD_ANCHOR["USB_D-"])):
            ref = roles[role]
            if b.FindFootprintByReference(ref) is not None:
                continue
            fp = new_footprint(b, F, pcbnew, comps[ref], padnet, netinfo)
            added.append(ref)
            place_esd(b, fp, net, anchor, K0, pcbnew, mm, tomm, V, edge)
            fp.Reference().SetVisible(False)
    # exact courtyard check (add_part compares boxes; this proves no courtyard overlap at all)
    for ref in roles.values():
        fp = b.FindFootprintByReference(ref)
        fp.BuildCourtyardCaches()
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        for o in b.GetFootprints():
            if o.GetReference() == ref or o.IsFlipped():
                continue
            c = o.GetCourtyard(pcbnew.F_CrtYd)
            if c.OutlineCount():
                t = pcbnew.SHAPE_POLY_SET(cy)
                t.BooleanIntersection(c)
                if t.OutlineCount():
                    raise SystemExit(f"{ref}: courtyard overlaps {o.GetReference()}")
    # ---------------------------------------------------------------- 3b. fields of the swapped and the new parts follow the schematic
    net_text = open(netfile, encoding="utf-8").read().split("(libparts")[0]
    sheet_ds = {}
    for blk in re.split(r'\(comp\s+\(ref\s+"', net_text)[1:]:
        m = re.search(r'\(datasheet\s+"([^"]*)"\)', blk)
        sheet_ds[blk[:blk.index('"')]] = m.group(1) if m else ""
    sync = list(roles.values()) + (list(SWAPS_B) if board == "B" else [])
    nf = 0
    for ref in sync:
        fp = b.FindFootprintByReference(ref)
        c = comps[ref]
        want = {k: c["fields"].get(k, "") for k in ("Manufacturer", "MPN", "LCSC", "Digi-Key_PN", "Alternates")}
        want["Datasheet"] = sheet_ds.get(ref, "")
        if fp.GetValue() != c["value"]:
            fp.SetValue(c["value"])
            nf += 1
        for name, v in want.items():
            f = next((x for x in fp.GetFields() if x.GetName() == name), None)
            if f is None and not v:
                continue
            if f is None:                               # text set before AddField (KiCad 9 stores a copy)
                f = pcbnew.PCB_FIELD(fp, fp.GetNextFieldId(), name)
                f.SetText(v)
                f.SetVisible(False)
                f.SetLayer(pcbnew.F_Fab)
                f.SetPosition(fp.GetPosition())
                f.thisown = False
                fp.AddField(f)
                nf += 1
                continue
            if f.GetText() != v:
                f.SetText(v)
                nf += 1
    print(f"  fields synced on {len(sync)} parts ({nf} changes)")
    # ---------------------------------------------------------------- 4. connections
    if added and not os.environ.get("HWP_PLACE_ONLY"):
        K = Copper(b, pcbnew, mm, tomm, V, edge)

        def pad(ref, num):
            return next(p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == num)
        nrst, v1, v2 = roles["nrst"], roles["vdda1"], roles["vdda2"]
        # GND: one via per GND pad, as close as it fits, on a short top track
        for role in ("nrst", "vdda1", "vdda2"):
            ref = roles[role]
            for p in b.FindFootprintByReference(ref).Pads():
                if p.GetNetname() == "GND":
                    try:
                        drop_gnd_via(b, p, pcbnew, mm, tomm, V, edge)
                    except SystemExit:                  # no room for a new via: tie to the nearest GND via
                        gv = K.nearest_via("GND", xy(p))
                        if math.hypot(gv[0] - xy(p)[0], gv[1] - xy(p)[1]) > 2.5:
                            raise
                        K.stub("GND", xy(p), gv)
        # NRST: the cap's pin 1 to the NRST via beside it (top track)
        K.stub("/MCU/NRST", xy(pad(nrst, "1")), K.nearest_via("/MCU/NRST", xy(pad(nrst, "1"))))
        # USB ESD diodes: found by search (below), already connected there
        # VBUS (pin 5) and VDDA: a via beside the pin, a via on the far copper, joined on B.Cu by the grid router
        jobs = []
        fb = xy(pad("FB1", "2"))                         # the via in FB1 pad 2 (step 2b)
        for ref in (v1, v2):
            cv = K.via_near(NEW_NETS["VDDA"], xy(pad(ref, "1")))
            K.stub(NEW_NETS["VDDA"], xy(pad(ref, "1")), cv)
            jobs.append((NEW_NETS["VDDA"], cv, fb))
        for net, s0, g0 in jobs:
            for pt in (s0, g0):
                K.add_via(net, pt)
        R.setup(b, (-24.0, 26.0, 24.0, 61.5), layers=["B.Cu"])
        if not R.run_jobs([(net, (*s0, ["B.Cu"]), (*g0, ["B.Cu"])) for net, s0, g0 in jobs]):
            raise SystemExit("B.Cu routing of VDDA failed")
        R.LAYERS[:] = ["F.Cu", "In2.Cu", "B.Cu"]
    for z in b.Zones():
        z.UnFill()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(path)
    for role, ref in roles.items():
        fp = b.FindFootprintByReference(ref)
        print(f"  {role}: {ref} {fp.GetValue()} at ({tomm(fp.GetPosition().x):.2f}, {tomm(fp.GetPosition().y):.2f}) "
              f"rot {fp.GetOrientationDegrees():.0f}" + (" (placed)" if ref in added else " (already placed)"))
    print("hw_protect pcb: done")


class Copper:
    """Exact-shape clearance checks and simple copper adds (tracks 0.2 mm, vias 0.8 / 0.4 mm)."""
    TW = TW

    def __init__(self, b, pcbnew, mm, tomm, V, edge):
        self.b, self.k, self.mm, self.tomm, self.V, self.edge = b, pcbnew, mm, tomm, V, edge
        self.cu = {"F.Cu": pcbnew.F_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu}
        self.rules = [z for z in b.Zones() if z.GetIsRuleArea()]

    def items(self):
        n = len(list(self.b.GetTracks()))
        if getattr(self, "_n", None) != n:              # rebuilt whenever copper was added
            self._n = n
            self._items = [(t, t.GetNetname(), t.GetClass() == "PCB_VIA", t.GetBoundingBox()) for t in self.b.GetTracks()]
            self._items += [(p, p.GetNetname(), p.HasHole(), p.GetBoundingBox()) for f in self.b.GetFootprints() for p in f.Pads()]
        return self._items

    def clear(self, net, shape_fn, layers, drill=None):
        """shape_fn(layer) -> SHAPE: clear of other-net copper on `layers` by CLR, and (drill = (x, y, r)) of drills."""
        k, tomm = self.k, self.tomm
        for n, sh in getattr(self, "extra", []):        # caller-supplied obstacles (site search only)
            if n != net and sh.Collide(shape_fn(self.k.F_Cu), self.mm(CLR)):
                return False
        probe = shape_fn(self.cu[layers[0]]).BBox()
        probe.Inflate(self.mm(CLR + 1.0))
        for it, n, hole, bb in self.items():
            if not bb.Intersects(probe):
                continue
            for ly in layers:
                L = self.cu[ly]
                if not (it.IsOnLayer(L) or hole):
                    continue
                if n == net and n:
                    continue
                if it.GetEffectiveShape(L).Collide(shape_fn(L), self.mm(CLR)):
                    return False
            if drill and hole:
                q = it.GetPosition()
                r = tomm(it.GetDrillValue()) / 2 if it.GetClass() == "PCB_VIA" else tomm(max(it.GetDrillSize().x, it.GetDrillSize().y)) / 2
                if math.hypot(tomm(q.x) - drill[0], tomm(q.y) - drill[1]) < r + drill[2] + 0.25:
                    return False
        return True

    def via_ok(self, net, x, y):
        k, mm = self.k, self.mm
        c = self.V(x, y)
        if not self.edge.Contains(c) or any(z.Outline().Contains(c) for z in self.rules):
            return False
        ring = k.SHAPE_CIRCLE(c, mm(VIA_D / 2))
        if not self.clear(net, lambda L: ring, list(self.cu), (x, y, VIA_DRILL / 2)):
            return False
        for f in self.b.GetFootprints():                 # never in a pad (no via-in-pad), same net or not
            for p in f.Pads():
                gap = 0 if p.GetNetname() == net else mm(0.1)
                if p.IsOnLayer(k.F_Cu) and p.GetEffectiveShape(k.F_Cu).Collide(ring, gap):
                    return False
        return True

    def seg_ok(self, net, a, c, ly):
        seg = self.k.SHAPE_SEGMENT(self.V(*a), self.V(*c), self.mm(self.TW))
        return self.clear(net, lambda L: seg, [ly])

    def add_track(self, net, a, c, ly):
        t = self.k.PCB_TRACK(self.b)
        t.SetStart(self.V(*a))
        t.SetEnd(self.V(*c))
        t.SetWidth(self.mm(self.TW))
        t.SetLayer(self.cu[ly])
        t.SetNet(self.b.FindNet(net))
        self.b.Add(t)

    def add_via(self, net, pt):
        for t in self.b.GetTracks():
            if t.GetClass() == "PCB_VIA" and t.GetNetname() == net and math.hypot(self.tomm(t.GetPosition().x) - pt[0], self.tomm(t.GetPosition().y) - pt[1]) < 0.01:
                return
        v = self.k.PCB_VIA(self.b)
        v.SetPosition(self.V(*pt))
        v.SetWidth(self.mm(VIA_D))
        v.SetDrill(self.mm(VIA_DRILL))
        v.SetNet(self.b.FindNet(net))
        self.b.Add(v)

    def paths(self, a, c):
        (ax, ay), (cx, cy) = a, c
        dx, dy = cx - ax, cy - ay
        yield [a, c]
        for m in ((cx, ay), (ax, cy)):
            yield [a, m, c]
        d = min(abs(dx), abs(dy))                        # 45-degree leg then straight, both orders
        m1 = (ax + math.copysign(d, dx), ay + math.copysign(d, dy))
        m2 = (cx - math.copysign(d, dx), cy - math.copysign(d, dy))
        yield [a, m1, c]
        yield [a, m2, c]

    def stub(self, net, a, c, ly="F.Cu"):
        for path in self.paths(a, c):
            if all(self.seg_ok(net, p, q, ly) for p, q in zip(path, path[1:]) if math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-6):
                for p, q in zip(path, path[1:]):
                    if math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-6:
                        self.add_track(net, p, q, ly)
                print(f"  {net}: top track {a} -> {c} ({len(path) - 1} segments)")
                return
        raise SystemExit(f"{net}: no clean top track {a} -> {c}")

    def stub_from_any(self, net, starts, c):
        for a in starts:
            try:
                self.stub(net, a, c)
            except SystemExit:
                continue
            self.add_via(net, c)
            return
        raise SystemExit(f"{net}: no clean top track to the via at {c}")

    def nearest_via(self, net, frm):
        vs = [t for t in self.b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == net]
        v = min(vs, key=lambda t: math.hypot(self.tomm(t.GetPosition().x) - frm[0], self.tomm(t.GetPosition().y) - frm[1]))
        return round(self.tomm(v.GetPosition().x), 4), round(self.tomm(v.GetPosition().y), 4)

    def via_near(self, net, frm, rmin=0.6, rmax=2.5):
        best = None
        for i in range(-50, 51):
            for j in range(-50, 51):
                x, y = round(frm[0] + i * 0.05, 3), round(frm[1] + j * 0.05, 3)
                d = math.hypot(x - frm[0], y - frm[1])
                if d < rmin or d > rmax or (best and d >= best[0]):
                    continue
                if self.via_ok(net, x, y) and any(all(self.seg_ok(net, p, q, "F.Cu") for p, q in zip(path, path[1:])
                                                      if math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-6)
                                                  for path in self.paths(frm, (x, y))):
                    best = (d, (x, y))
        if best is None:
            raise SystemExit(f"{net}: no via spot within {rmax} mm of {frm}")
        return best[1]

    def via_on_track(self, net, ly, near, rmax, stub=True):
        """a via spot ON a track of `net` on layer `ly` (so it joins it), nearest to any point in `near`"""
        L = self.cu[ly]
        cands = []
        for t in self.b.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetNetname() != net or t.GetLayer() != L:
                continue
            ax, ay, bx, by = (self.tomm(t.GetStart().x), self.tomm(t.GetStart().y), self.tomm(t.GetEnd().x), self.tomm(t.GetEnd().y))
            n = max(1, int(math.hypot(bx - ax, by - ay) / 0.05))
            for k in range(n + 1):
                x, y = round(ax + (bx - ax) * k / n, 3), round(ay + (by - ay) * k / n, 3)
                d = min(math.hypot(x - p[0], y - p[1]) for p in near)
                if d <= rmax:
                    cands.append((d, (x, y)))
        for t in self.b.GetTracks():                    # an existing via of the net is a tap point too
            if t.GetClass() == "PCB_VIA" and t.GetNetname() == net:
                pt = (round(self.tomm(t.GetPosition().x), 4), round(self.tomm(t.GetPosition().y), 4))
                d = min(math.hypot(pt[0] - p[0], pt[1] - p[1]) for p in near)
                if d <= rmax:
                    cands.append((d - 0.5, pt))         # preferred: no new hole
        for d, pt in sorted(cands):
            existing = any(t.GetClass() == "PCB_VIA" and t.GetNetname() == net
                           and math.hypot(self.tomm(t.GetPosition().x) - pt[0], self.tomm(t.GetPosition().y) - pt[1]) < 0.01
                           for t in self.b.GetTracks())
            if not existing and (d < 0.6 or not self.via_ok(net, *pt)):
                continue
            if not stub or any(all(self.seg_ok(net, p, q, "F.Cu") for p, q in zip(path, path[1:])
                                   if math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-6)
                               for a in near for path in self.paths(a, pt)):
                return pt
        raise SystemExit(f"{net}: no via spot on its {ly} track within {rmax} mm of {near}")


def place_esd(b, fp, net, anchor, K, pcbnew, mm, tomm, V, edge):
    line = next(p for p in fp.Pads() if p.GetNetname() == net)
    gpad = next(p for p in fp.Pads() if p.GetNetname() == "GND")
    cands = []
    n = int(ESD_R / 0.1)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, y = round(anchor[0] + i * 0.1, 2), round(anchor[1] + j * 0.1, 2)
            d = math.hypot(x - anchor[0], y - anchor[1])
            if d <= ESD_R:
                cands.append((d, x, y))
    tried = 0
    for d, x, y in sorted(cands):
        for rot in (0, 90, 180, 270):
            fp.SetPosition(V(x, y))
            fp.SetOrientationDegrees(rot)
            try:
                site_check(b, fp, pcbnew, tomm, edge, near=(anchor[0], anchor[1], 8.0))
            except SystemExit:
                continue
            tried += 1
            K._n = None                                  # pads moved: rebuild the item cache
            lp = (tomm(line.GetPosition().x), tomm(line.GetPosition().y))
            try:
                via = K.via_on_track(net, "In2.Cu", [lp], rmax=2.5)
            except SystemExit:
                continue
            tv = pcbnew.PCB_VIA(b)                       # planned tap: GND via must clear it (dry run first)
            tv.SetPosition(V(*via))
            tv.SetWidth(mm(VIA_D))
            tv.SetDrill(mm(VIA_DRILL))
            plan = [tv]
            for path in K.paths(lp, via):
                if all(K.seg_ok(net, p, q, "F.Cu") for p, q in zip(path, path[1:]) if math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-6):
                    for p, q in zip(path, path[1:]):
                        t = pcbnew.PCB_TRACK(b)
                        t.SetStart(V(*p))
                        t.SetEnd(V(*q))
                        t.SetWidth(mm(K.TW))
                        t.SetLayer(pcbnew.F_Cu)
                        plan.append(t)
                    break
            size = next(((d_, r_) for d_, r_ in ((VIA_D, VIA_DRILL), (VIP_D, VIP_DRILL))
                         if _drop_gnd_via(b, gpad, pcbnew, mm, tomm, V, edge, d_, r_, 1.6, plan, dry=True)), None)
            if size is None:
                if tried % 25 == 0:
                    print(f"    {fp.GetReference()}: {tried} clean sites tried, at ({x}, {y}) rot {rot}", flush=True)
                continue
            K.add_via(net, via)
            K.stub(net, lp, via)
            if not _drop_gnd_via(b, gpad, pcbnew, mm, tomm, V, edge, size[0], size[1], 1.6):
                raise SystemExit(f"{fp.GetReference()}: GND via dry run and add disagree")
            print(f"  {fp.GetReference()} ({net} ESD) at ({x}, {y}) rot {rot}, tap via {via} ({tried} clean sites tried)")
            return
    raise SystemExit(f"{fp.GetReference()}: no site for the {net} ESD diode within {ESD_R} mm of {anchor}")


def new_footprint(b, F, pcbnew, comp, padnet, netinfo):
    """The schematic's footprint from the KiCad library, linked to its symbol, pads on their nets (as board_fix_pcb.add_part,
    without its search)."""
    lib, name = comp["footprint"].split(":", 1)
    fp = pcbnew.FootprintLoad(os.path.join(F.KFP, lib + ".pretty"), name)
    if fp is None:
        raise SystemExit(f"footprint {comp['footprint']} not found")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(comp["ref"])
    fp.SetValue(comp["value"])
    for fld in fp.GetFields():
        if fld.GetName() == "Datasheet":
            fld.SetText("")
    if "ts" in comp:
        fp.SetPath(pcbnew.KIID_PATH(comp["sheet_ts"].rstrip("/") + "/" + comp["ts"]))
        fp.SetSheetname(comp["props"].get("Sheetname", ""))
        fp.SetSheetfile(comp["props"].get("Sheetfile", ""))
    for p in fp.Pads():
        n = padnet.get((comp["ref"], p.GetNumber()))
        if n:
            p.SetNet(netinfo(n))
        else:
            p.SetNetCode(0)
    for p in fp.Pads():                                  # solid to the GND pour: a 0.5 mm pad starves thermal spokes
        if p.GetNetname() == "GND":
            p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    b.Add(fp)
    F.sync_fields(b, {comp["ref"]: comp})
    return fp


def site_check(b, fp, pcbnew, tomm, edge, near=None):
    """The part's site is clean: courtyard inside the board and touching no other courtyard (exact polygons), every
    pad >= CLR from other-net top copper (tracks, vias, pads; pours refill) and touching no drill.
    near = (x, y, r): only items within r mm are looked at (a site search calls this many times)."""
    ref = fp.GetReference()
    fp.BuildCourtyardCaches()
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    out = pcbnew.SHAPE_POLY_SET(cy)
    out.BooleanSubtract(edge)
    if out.OutlineCount():
        raise SystemExit(f"{ref}: courtyard leaves the board")
    ctx = _site_ctx(b, fp, pcbnew, tomm, near)
    for oref, c in ctx["yards"]:
        if c.BBox().Intersects(cy.BBox()):
            t = pcbnew.SHAPE_POLY_SET(cy)
            t.BooleanIntersection(c)
            if t.OutlineCount():
                raise SystemExit(f"{ref}: courtyard overlaps {oref}")
    for p in fp.Pads():
        s = p.GetEffectiveShape(pcbnew.F_Cu)
        pb = p.GetBoundingBox()
        pb.Inflate(pcbnew.FromMM(1.0))
        for it, bb, net, hole in ctx["items"]:
            if not bb.Intersects(pb):
                continue
            same = net == p.GetNetname() and net
            if (not same and it.GetEffectiveShape(pcbnew.F_Cu).Collide(s, pcbnew.FromMM(CLR))) or \
                    (hole and same and it.GetEffectiveShape(pcbnew.F_Cu).Collide(s, 0)):
                raise SystemExit(f"{ref} pad {p.GetNumber()}: too close to {net or 'unconnected'} "
                                 f"{it.GetClass()} at ({tomm(it.GetPosition().x):.2f}, {tomm(it.GetPosition().y):.2f})")


_CTX = {}


def _site_ctx(b, fp, pcbnew, tomm, near):
    key = (fp.GetReference(), near, len(list(b.GetTracks())))
    if key in _CTX:
        return _CTX[key]

    def close(it):
        if near is None:
            return True
        q = it.GetPosition()
        return math.hypot(tomm(q.x) - near[0], tomm(q.y) - near[1]) < near[2]
    ref = fp.GetReference()
    yards = [(o.GetReference(), o.GetCourtyard(pcbnew.F_CrtYd)) for o in b.GetFootprints()
             if o.GetReference() != ref and not o.IsFlipped() and o.GetCourtyard(pcbnew.F_CrtYd).OutlineCount()
             and (near is None or o.GetCourtyard(pcbnew.F_CrtYd).BBox().Distance(pcbnew.VECTOR2I(pcbnew.FromMM(near[0]), pcbnew.FromMM(near[1]))) < pcbnew.FromMM(near[2]))]
    items = [(t, t.GetBoundingBox(), t.GetNetname(), t.GetClass() == "PCB_VIA") for t in b.GetTracks()
             if (t.IsOnLayer(pcbnew.F_Cu) or t.GetClass() == "PCB_VIA") and (near is None or t.GetClass() == "PCB_VIA" and close(t)
                                                                               or near is not None and t.GetClass() != "PCB_VIA")]
    items += [(p, p.GetBoundingBox(), p.GetNetname(), p.HasHole()) for o in b.GetFootprints() if o.GetReference() != ref
              for p in o.Pads() if (p.IsOnLayer(pcbnew.F_Cu) or p.HasHole()) and close(p)]
    _CTX.clear()
    _CTX[key] = {"yards": yards, "items": items}
    return _CTX[key]


def drop_gnd_via(b, pad, pcbnew, mm, tomm, V, edge):
    for vd, vdr, rmax in ((VIA_D, VIA_DRILL, 1.6), (VIP_D, VIP_DRILL, 1.6), (VIA_D, VIA_DRILL, 2.4), (VIP_D, VIP_DRILL, 2.4)):
        if _drop_gnd_via(b, pad, pcbnew, mm, tomm, V, edge, vd, vdr, rmax):
            return
    raise SystemExit(f"{pad.GetParentFootprint().GetReference()} pad {pad.GetNumber()}: no room for a GND via")


def _drop_gnd_via(b, pad, pcbnew, mm, tomm, V, edge, VIA_D, VIA_DRILL, RMAX, extra=(), dry=False):
    """A GND via (0.8 / 0.4 mm) within 1.6 mm of `pad` that clears every other-net item on every copper layer (In1 is
    the GND plane: its tracks still count), every drill by 0.25 mm and every other footprint's pads; joined to the pad
    by a 0.25 mm top track that clears other-net top copper by CLR."""
    px, py = tomm(pad.GetPosition().x), tomm(pad.GetPosition().y)
    cu = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    shapes, drills = {L: [] for L in cu}, []
    for t in b.GetTracks():
        bb = t.GetBoundingBox()
        if tomm(bb.GetLeft()) > px + RMAX + 3 or tomm(bb.GetRight()) < px - RMAX - 3 or \
                tomm(bb.GetTop()) > py + RMAX + 3 or tomm(bb.GetBottom()) < py - RMAX - 3:
            continue
        for L in cu:
            if t.IsOnLayer(L) and t.GetNetname() != "GND":
                shapes[L].append(t.GetEffectiveShape(L))
        if t.GetClass() == "PCB_VIA":
            drills.append((tomm(t.GetPosition().x), tomm(t.GetPosition().y), tomm(t.GetDrillValue()) / 2))
    for f in b.GetFootprints():
        for p in f.Pads():
            q = p.GetPosition()
            if abs(tomm(q.x) - px) > RMAX + 3 or abs(tomm(q.y) - py) > RMAX + 3:
                continue
            for L in cu:
                if (p.IsOnLayer(L) or p.HasHole()) and p.GetNetname() != "GND":
                    shapes[L].append(p.GetEffectiveShape(L))
            if p.HasHole():
                drills.append((tomm(q.x), tomm(q.y), tomm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2))
            elif p.GetNetname() == "GND" and p.IsOnLayer(pcbnew.F_Cu) and p.GetParentFootprint().GetReference() != pad.GetParentFootprint().GetReference():
                shapes[pcbnew.F_Cu].append(p.GetEffectiveShape(pcbnew.F_Cu))     # no via in another part's pad
    own = [p.GetEffectiveShape(pcbnew.F_Cu) for p in pad.GetParentFootprint().Pads()
           if p.GetNumber() and p.GetNumber() != pad.GetNumber() and p.IsOnLayer(pcbnew.F_Cu)]   # copper pads only (not paste windows)
    for it in extra:                                   # planned (not yet added) copper of other nets
        for L in cu:
            if it.IsOnLayer(L):
                shapes[L].append(it.GetEffectiveShape(L))
        if it.GetClass() == "PCB_VIA":
            drills.append((tomm(it.GetPosition().x), tomm(it.GetPosition().y), tomm(it.GetDrillValue()) / 2))
    rules = [z for z in b.Zones() if z.GetIsRuleArea()]
    clr = mm(CLR)
    sb = {L: [(sh, sh.BBox()) for sh in shapes[L]] for L in cu}
    best = None
    for i in range(-50, 51):
        for j in range(-50, 51):
            x, y = round(px + i * 0.05, 3), round(py + j * 0.05, 3)
            d = math.hypot(x - px, y - py)
            if d > RMAX or d < 0.55 or (best and d >= best[0]):
                continue
            c = V(x, y)
            ring = pcbnew.SHAPE_CIRCLE(c, mm(VIA_D / 2))
            if not edge.Contains(c) or any(z.Outline().Contains(c) for z in rules):
                continue
            if any(math.hypot(x - dx, y - dy) < VIA_DRILL / 2 + dr + 0.25 for dx, dy, dr in drills):
                continue
            rb = ring.BBox()
            rb.Inflate(clr)
            if any(bb.Intersects(rb) and s.Collide(ring, clr) for L in cu for s, bb in sb[L]) or \
                    any(s.Collide(ring, clr) for s in own):
                continue
            seg = pcbnew.SHAPE_SEGMENT(V(px, py), c, mm(0.25))
            sbb = seg.BBox()
            sbb.Inflate(clr)
            if any(bb.Intersects(sbb) and s.Collide(seg, clr) for s, bb in sb[pcbnew.F_Cu]) or any(s.Collide(seg, clr) for s in own):
                continue
            best = (d, x, y)
    if best is None:
        return False
    if dry:
        return True
    _, x, y = best
    gnd = b.FindNet("GND")
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(V(x, y))
    v.SetWidth(mm(VIA_D))
    v.SetDrill(mm(VIA_DRILL))
    v.SetNet(gnd)
    b.Add(v)
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pad.GetPosition())
    t.SetEnd(V(x, y))
    t.SetWidth(mm(0.25))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(gnd)
    b.Add(t)
    print(f"  GND via {VIA_D} / {VIA_DRILL} for {pad.GetParentFootprint().GetReference()}.{pad.GetNumber()} at ({x:.2f}, {y:.2f}), {best[0]:.2f} mm")
    return True


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sch":
        sch(sys.argv[2].upper())
    elif cmd == "pcb":
        pcb(sys.argv[2], sys.argv[3], sys.argv[4].upper())
    else:
        raise SystemExit(__doc__)
