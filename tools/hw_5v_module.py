"""125 C 5 V converter for board A and board B, in the TSR 1-2450 spot (job hw5v; reopens the U13 item of
ADR-2026-11-20-hwprotect; coordinator default 2026-11-21: least board redesign, no enclosure change).

  python   tools/hw_5v_module.py lib                                          (footprint into dingoPDM.pretty)
  python   tools/hw_5v_module.py sch A|B                                      (from the board folder, last schematic stage)
  python.exe (KiCad 9) tools/hw_5v_module.py pcb <board.kicad_pcb> <netlist.net> A|B    (last PCB stage)

Why: the u13 heat check puts board B's +5 V module U13 (Traco TSR 1-2450, -40..85 C, derated 2.4 %/K above 60 C,
https://tracopower.com/tsr1-datasheet) on 89.5 C of board in normal hot-day car use and up to 112 C (150 A, fans off);
board A's U15 is the same part. No SIP-3 5 V module rated >= 105 C exists (docs/parts-audit.md sections 11, 15.1).

Part: TI LMZM23601V5SILR (LCSC C2868357), 1 A fixed 5 V power module with the inductor inside. TI SNVSAQ4C (rev C,
March 2023): VIN 4-36 V (abs max 40 V), TJ -40..125 C, uSiP SIL0010A 3.8 x 3.0 x 1.578 mm max, 28 uA no-load supply.
Load: <= 0.22 A (MCP2562FD 70 mA + all of +3V3 through U2). The pin-to-pin 0.5 A LMZM23600V5 (LCSC C2681748) fits
the same footprint but is NOT an alternate: its low-side current limit (0.5 A min, SNVSB53C 7.5) is close to the
soft-start charge current of the ~157 uF on +5VP / +5V / +3V3 plus the load (tools/verify_spice.py 'startup').
Fixed-output circuit (data sheet 8.2, Figure 8-1):
  EN -> VIN (pin 4 'can be connected to VIN'), MODE/SYNC -> GND (auto PFM: light-load efficiency), FB -> VOUT
  ('connect this pin to ... the VOUT node'), PGOOD open (8.2.2.5: 'can be left floating'), DNC 8-10 open.
  Input: 2 x 4.7 uF 50 V X7R 0805 (8.2.2.2: 'a parallel combination of 2 x 4.7-uF, 0805 ... X5R or X7R'; 50 V for the
  35 V clamped load dump), TDK CGA4J1X7R1H475KT0Y0N (board B C3's part), right at VIN / GND.
  Output: 22 uF 10 V X7R 0805 Murata GRM21BZ71A226ME15L (board B C4's part) (Table 8-3, 5 V: min 15 / recommended
  22 / max 220 uF). With C4 22 uF, +5V 2 x 47 uF behind D4 / D18 and +3V3 about 18.6 uF the total is about 157 uF.
Footprint: TI's example board layout for SIL0010A (data sheet page 43, 4222635/D): ten 0.65 x 0.3 mm pads, 0.6 mm
pitch, rows 3.05 mm apart; exposed pad 0.7 x 2.9 mm, 0.175 mm off centre; stencil 3 x 0.7 x 0.833 mm (86 %).
Board (both boards, same stock dingoPDM spot; nothing else moves, the enclosure is untouched):
  * the TSR footprint goes; the module sits inside its old outline at MOD_AT, input row toward the +12P track, output
    row toward the +5VP track (both tracks stay: they still join the DNP alternates U1 / U12 (B) / U14 (A)).
  * C_in x 2 sit on the +12P track (pad 1 on it) with pad 2 on the two GND vias that were under the TSR body;
    C_out sits on the +5VP track with a GND via beside pad 2; 3 thermal vias (0.7 / 0.3 mm) in the exposed pad
    (TI 'thermal vias', data sheet 8.5.1 / Figure 8-49; filled + capped like every via in a pad, hardware/fab notes).
  * every new track / via is checked against other-net copper (board rule + margin) and drills.
Idempotent: a board that already has the module is left as it is.
"""
import math
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hw_protect as H  # noqa: E402

LIB = os.path.normpath(os.path.join(HERE, "..", "hardware", "board-a", "libraries", "dingoPDM.pretty"))
NAME = "Texas_SIL0010A_MicroSiP-10-1EP_3.8x3mm_P0.6mm_EP0.7x2.9mm_TI"
MOD_FP = "dingoPDM:" + NAME
MODEL = "${KICAD9_3DMODEL_DIR}/Package_LGA.3dshapes/Texas_SIL0010A_MicroSiP-10-1EP_3.8x3mm_P0.6mm_EP0.7x2.9mm.step"
NS = uuid.UUID("5b0c1f7e-2d4a-4c1e-9f55-7a1e0c0de5a5")
OLD = {"A": "U15", "B": "U13"}                     # the TSR 1-2450 that goes
OLD_COUT = "C4"                                     # the +5VP 22 uF that stays (both boards)
# (Value, Footprint, LCSC, Digi-Key_PN, Manufacturer, MPN, Datasheet, Alternates)
MODULE = ("LMZM23601V5", MOD_FP, "C2868357", "296-LMZM23601V5SILRCT-ND", "Texas Instruments", "LMZM23601V5SILR",
          "https://www.ti.com/lit/ds/symlink/lmzm23601.pdf",
          "TI LMZM23601V5SILT (same part, 250 reel, LCSC C2876787)")
CIN = ("4.7uF", "Capacitor_SMD:C_0805_2012Metric", "C694229", "", "TDK", "CGA4J1X7R1H475KT0Y0N",
       "https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=CGA4J1X7R1H475KT0Y0N",
       "HRE CGA0805X7R475K500MT (4.7 uF 50 V X7R 0805, LCSC C6119944)")
COUT = ("22uF", "Capacitor_SMD:C_0805_2012Metric", "C907991", "", "Murata", "GRM21BZ71A226ME15L",
        "https://www.murata.com/en-us/products/productdetail?partno=GRM21BZ71A226ME15L",
        "CCTC TCC0805X7R226M100FT (22 uF 10 V X7R 0805, LCSC C53133025)")
SYM_BASE, SYM = "LMZM23601", "LMZM23601V5"         # KiCad 9 library: LMZM23601V5 extends LMZM23601 (same pins)
LIB_ID = "Regulator_Switching:" + SYM
KSYM9 = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\KiCad\9.0\share\kicad\symbols", "Regulator_Switching.kicad_sym")

# ------------------------------------------------------------------ footprint (TI SIL0010A example board layout)
PADS = [(str(n), -1.525, -1.2 + 0.6 * (n - 1)) for n in range(1, 6)] + \
       [(str(n), 1.525, 1.2 - 0.6 * (n - 6)) for n in range(6, 11)]
EP = (-0.175, 0.0, 0.7, 2.9)
EP_PASTE = [(-0.175, y, 0.7, 0.833) for y in (-1.03, 0.0, 1.03)]
CRTYD = (-2.15, -1.8, 2.15, 1.8)                    # pads (x +-1.85) / body (3.9 x 3.1 max) + 0.25


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(map(str, parts))))


def footprint_text():
    import d2_tvs as D
    out = [f'(footprint "{NAME}"\n\t(version 20241229)\n\t(generator "pcbnew")\n\t(generator_version "9.0")\n\t(layer "F.Cu")\n',
           '\t(descr "TI uSiP SIL0010A (MicroSiP-10, 3.8 x 3.0 x 1.578 mm max), TI example board layout 4222635/D '
           '(LMZM23600 / LMZM23601 data sheet page 43): pads 0.65 x 0.3 mm, pitch 0.6, rows 3.05 apart, exposed pad '
           '0.7 x 2.9 mm 0.175 mm off centre, stencil 3 x 0.7 x 0.833 mm (86 %)")\n',
           '\t(tags "LMZM23600 LMZM23601 SIL0010A MicroSiP uSiP power module")\n',
           D._txt("property", "Reference", "REF**", 0, -2.5, "F.SilkS", False, "ref", 1.0, 0.15).replace(D.uid("ref"), uid("ref")),
           D._txt("property", "Value", "LMZM23601V5", 0, 2.6, "F.Fab", False, "val").replace(D.uid("val"), uid("val")),
           D._txt("property", "Datasheet", "https://www.ti.com/lit/ds/symlink/lmzm23601.pdf", 0, 0, "F.Fab", True, "ds").replace(D.uid("ds"), uid("ds")),
           D._txt("property", "Description", "", 0, 0, "F.Fab", True, "desc").replace(D.uid("desc"), uid("desc")),
           '\t(attr smd)\n']

    def fix(s, key):
        return re.sub(r'\(uuid "[^"]+"\)', f'(uuid "{uid(key)}")', s)
    # silkscreen (0.15 mm lines: JLCPCB minimum, verify_dfm): top / bottom body edges between the pad rows
    # (>= 0.2 mm off copper) + pin 1 mark left of pad 1
    out += [fix(D._line(-0.95, -1.62, 0.95, -1.62, "F.SilkS", 0.15, "x"), "s1"),
            fix(D._line(-0.95, 1.62, 0.95, 1.62, "F.SilkS", 0.15, "x"), "s2"),
            fix(D._line(-2.3, -1.2, -2.2, -1.2, "F.SilkS", 0.2, "x"), "s3"),
            fix(D._rect(-1.9, -1.5, 1.9, 1.5, "F.Fab", 0.1, "x"), "fab"),
            fix(D._line(-1.9, -1.0, -1.4, -1.5, "F.Fab", 0.1, "x"), "fab1"),
            fix(D._rect(*CRTYD, "F.CrtYd", 0.05, "x"), "crt")]
    for num, x, y in PADS:
        out.append(f'\t(pad "{num}" smd roundrect\n\t\t(at {x:g} {y:g})\n\t\t(size 0.65 0.3)\n'
                   f'\t\t(layers "F.Cu" "F.Paste" "F.Mask")\n\t\t(roundrect_rratio 0.166667)\n\t\t(uuid "{uid("p", num)}")\n\t)\n')
    ex, ey, ew, eh = EP
    out.append(f'\t(pad "11" smd rect\n\t\t(at {ex:g} {ey:g})\n\t\t(size {ew:g} {eh:g})\n\t\t(layers "F.Cu" "F.Mask")\n'
               f'\t\t(uuid "{uid("p", 11)}")\n\t)\n')
    for k, (x, y, w, h) in enumerate(EP_PASTE):
        out.append(f'\t(pad "" smd rect\n\t\t(at {x:g} {y:g})\n\t\t(size {w:g} {h:g})\n\t\t(layers "F.Paste")\n'
                   f'\t\t(uuid "{uid("paste", k)}")\n\t)\n')
    out.append(f'\t(embedded_fonts no)\n\t(model "{MODEL}"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t\t(scale\n'
               '\t\t\t(xyz 1 1 1)\n\t\t)\n\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)\n)\n')
    return "".join(out)


def write_lib():
    p = os.path.join(LIB, NAME + ".kicad_mod")
    with open(p, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(footprint_text())
    print("wrote", p)


# ------------------------------------------------------------------ schematic
def lib_symbol():
    """LMZM23601V5 flattened (KiCad 9 library: it extends LMZM23601) as a lib_symbols entry."""
    lt = H.rd(KSYM9)
    k = lt.index(f'\n\t(symbol "{SYM_BASE}"') + 1
    base = lt[k:H.block_end(lt, k + 1)]
    k = lt.index(f'\n\t(symbol "{SYM}"') + 1
    child = lt[k:H.block_end(lt, k + 1)]
    if f'(extends "{SYM_BASE}")' not in child:
        raise SystemExit(f"{SYM}: expected to extend {SYM_BASE}")
    sym = base.replace(f'(symbol "{SYM_BASE}"', f'(symbol "{SYM}"', 1)
    sym = sym.replace(f'(symbol "{SYM_BASE}_', f'(symbol "{SYM}_')
    for name in ("Value", "Footprint", "Datasheet", "Description"):
        m = re.search(r'\(property "%s" "([^"]*)"' % name, child)
        if m:
            sym = re.sub(r'(\(property "%s" ")[^"]*(")' % name, lambda q: q.group(1) + m.group(1) + q.group(2), sym, count=1)
    return sym


def wire_blocks(t):
    out = []
    for s, e in H.top_blocks(t, "wire"):
        m = re.search(r"\(xy ([\d.\-]+) ([\d.\-]+)\)\s*\(xy ([\d.\-]+) ([\d.\-]+)\)", t[s:e])
        out.append((s, e, tuple(map(float, m.groups()))))
    return out


def same(a, c):
    return abs(a[0] - c[0]) < 0.005 and abs(a[1] - c[1]) < 0.005


def wire(a, c):
    return (f'(wire\n\t\t(pts\n\t\t\t(xy {H.fmt(a[0])} {H.fmt(a[1])}) (xy {H.fmt(c[0])} {H.fmt(c[1])})\n\t\t)\n'
            f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{H.u()}")\n\t)')


def no_connect(x, y):
    return f'(no_connect\n\t\t(at {H.fmt(x)} {H.fmt(y)})\n\t\t(uuid "{H.u()}")\n\t)'


def power_symbol(t, lib_id, x, y, ref, project, path):
    g0, g1 = next((a, z) for a, z in H.top_blocks(t, "symbol") if f'(lib_id "{lib_id}")' in t[a:z])
    g = H.move_block(t[g0:g1], x, y)
    g = H.set_instances(H.set_prop(g, "Reference", ref), project, path, ref)
    return H.renew_uuids(g)


def sch(board):
    if not os.path.exists(H.ROOTS[board]):
        raise SystemExit("run from the board folder")
    sheet = "Power.kicad_sch"
    t = H.rd(sheet)
    if f'(lib_id "{LIB_ID}")' in t:
        print("hw_5v_module sch: already applied")
        return
    used = H.used_refs()
    s, e = H.symbol_by_ref(t, OLD[board])
    tsr = t[s:e]
    if '(lib_id "Regulator_Switching:TSR_1-2450")' not in tsr:
        raise SystemExit(f"{OLD[board]} is not the TSR 1-2450")
    X, Y = map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+) 0\)", tsr).groups())
    project = re.search(r'\(project "([^"]+)"', tsr).group(1)
    path = re.search(r'\(path "([^"]+)"', tsr).group(1)
    vin_end, gnd_end, vout_end = (X - 10.16, Y - 2.54), (X, Y + 5.08), (X + 10.16, Y - 2.54)
    wires = wire_blocks(t)
    w_in = [w for w in wires if same(w[2][:2], vin_end) or same(w[2][2:], vin_end)]
    w_out = [w for w in wires if same(w[2][:2], vout_end) or same(w[2][2:], vout_end)]
    if len(w_in) != 1 or len(w_out) != 1:
        raise SystemExit(f"TSR pin wires: {len(w_in)} at Vin, {len(w_out)} at Vout (expected 1 / 1)")
    a_in = w_in[0][2][2:] if same(w_in[0][2][:2], vin_end) else w_in[0][2][:2]
    a_out = w_out[0][2][2:] if same(w_out[0][2][:2], vout_end) else w_out[0][2][:2]
    gsym = [(a, z) for a, z in H.top_blocks(t, "symbol") if '(lib_id "power:GND")' in t[a:z]
            and re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", t[a:z]) and
            same(tuple(map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", t[a:z]).groups())), gnd_end)]
    if len(gsym) != 1:
        raise SystemExit(f"TSR GND pin: {len(gsym)} GND symbols")
    gnd_block = t[gsym[0][0]:gsym[0][1]]
    gnd_ref = re.search(r'\(reference "([^"]+)"\)', gnd_block).group(1)
    tsr_tpl = tsr
    for a, z in sorted([(s, e), gsym[0], w_in[0][:2], w_out[0][:2]], reverse=True):
        t = t[:a] + t[z:]                               # leaves "\n\t" + "\n\t(next": folded below
    t = re.sub(r"\n\t(?=\n\t\()", "", t)
    # new module: VIN pin end on the old Vin wire's far end, VOUT on the same row
    cx, cy = a_in[0] + 12.7, a_in[1] + 5.08
    pe = {"3": a_in, "2": (cx - 12.7, cy), "4": (cx - 12.7, cy + 5.08), "1": (cx, cy + 10.16),
          "6": (cx + 12.7, cy - 5.08), "7": (cx + 12.7, cy), "5": (cx + 12.7, cy + 5.08)}
    if not (pe["6"][0] < a_out[0] - 1.0 and abs(pe["6"][1] - a_out[1]) < 0.005):
        raise SystemExit(f"VOUT end {pe['6']} cannot reach {a_out} on one row")
    # the area the new symbol + its stubs use must be empty (nothing else is moved)
    x0, x1, y0, y1 = a_in[0] - 10.5, a_out[0] - 0.5, a_in[1] + 0.5, cy + 11.5
    pts = [(float(p), float(q)) for p, q in re.findall(r"\((?:at|xy) ([\d.\-]+) ([\d.\-]+)", t)]
    hits = [p for p in pts if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
    crossing = [w for w in wire_blocks(t) if max(w[2][0], w[2][2]) >= x0 and min(w[2][0], w[2][2]) <= x1
                and max(w[2][1], w[2][3]) >= y0 and min(w[2][1], w[2][3]) <= y1]
    if hits or crossing:
        raise SystemExit(f"sheet area for the module not free: {hits[:6]} {len(crossing)} wires")
    t = H.embed(t, LIB_ID, lib_symbol())
    mref = H.next_ref(used, "U")
    items = [H.new_symbol(tsr_tpl, LIB_ID, cx, cy, mref, MODULE, [str(n) for n in range(1, 12)], project, path)]
    items.append(wire(pe["6"], a_out))                                   # VOUT -> the +5VP wire
    items.append(wire(pe["7"], pe["6"]))                                 # FB -> VOUT (fixed 5 V option)
    items.append(no_connect(*pe["5"]))                                   # PGOOD open (8.2.2.5)
    gm = (pe["2"][0] - 2.54, pe["2"][1])
    items += [wire(pe["2"], gm), power_symbol(t, "power:GND", *gm, H.next_ref(used, "#PWR0"), project, path)]  # MODE -> GND
    en = (pe["4"][0] - 7.62, pe["4"][1])
    items += [wire(pe["4"], en), power_symbol(t, "power:+12P", *en, H.next_ref(used, "#PWR0"), project, path)]  # EN -> VIN
    g = H.set_instances(H.move_block(gnd_block, *pe["1"]), project, path, gnd_ref)
    items.append(H.renew_uuids(g))                                       # GND (pins 1 + 11): the TSR's GND symbol
    t = H.insert_items(t, items)
    # capacitors in a free box: C_in x 2 (+12P), C_out (+5VP)
    c_tpl = next(t[a:z] for a, z in H.top_blocks(t, "symbol") if '(lib_id "Device:C_Small")' in t[a:z])
    c_lib = H.lib_block(t, "Device:C_Small")
    ox, oy = H.free_box(t, 50.8, 20.32)
    items = []
    made = {"module": mref}
    for k, (role, part, top) in enumerate((("cin1", CIN, "power:+12P"), ("cin2", CIN, "power:+12P"), ("cout", COUT, "power:+5VP"))):
        ref = H.next_ref(used, "C")
        x, y = ox + 10.16 + 15.24 * k, oy + 10.16
        items.append(H.new_symbol(c_tpl, "Device:C_Small", x, y, ref, part, ["1", "2"], project, path))
        cp = H.pin_ends(c_lib, x, y)
        p1, p2 = sorted(cp.values(), key=lambda q: q[1])
        items += [power_symbol(t, top, *p1, H.next_ref(used, "#PWR0"), project, path),
                  power_symbol(t, "power:GND", *p2, H.next_ref(used, "#PWR0"), project, path)]
        made[role] = ref
    items.append(H.text(f"hw5v: {mref} TI LMZM23601V5 (125 C) in place of the TSR 1-2450 {OLD[board]}; "
                        f"{made['cin1']} / {made['cin2']} 2 x 4.7 uF 50 V input, {made['cout']} 22 uF output "
                        f"(TI SNVSAQ4C 8.2.2).", ox, oy))
    H.wr(sheet, H.insert_items(t, items))
    print("hw_5v_module sch:", made)


# ------------------------------------------------------------------ PCB
MOD_AT = (-26.9, 42.164)                            # inside the TSR outline (x -28.97..-20.78, y 36.03..48.32)
CIN_AT = [(-24.1, 41.0), (-22.12, 41.0)]            # pad 1 on the +12P track, pad 2 on the old GND vias
COUT_AT = (-25.2, 46.05)                            # pad 1 on the +5VP track
COUT_VIA = (-23.7, 47.0)
EP_VIAS = (-1.0, 0.0, 1.0)                          # along the exposed pad
VIP_D, VIP_DRILL = 0.7, 0.3
FREED = (-28.97, 36.02, -20.77, 48.33)              # the TSR courtyard: every new courtyard stays inside
OLD_PADS = {"1": (-26.67, 39.624), "3": (-26.67, 44.704)}   # TSR pad 1 (+12P) / pad 3 (+5VP): rail track ends (A and B)


def roles_of(comps, padnet):
    out = {}
    for r, c in comps.items():
        nets = sorted({n for (rr, p), n in padnet.items() if rr == r})
        if c["footprint"] == MOD_FP:
            out["module"] = r
        elif c["footprint"] == CIN[1] and nets == ["+12P", "GND"]:
            out.setdefault("cin", []).append(r)
        elif c["footprint"] == COUT[1] and nets == ["+5VP", "GND"] and r != OLD_COUT and c["value"] == COUT[0]:
            out["cout"] = r
    if "cin" in out:
        out["cin"] = sorted(out["cin"], key=lambda r: int(r[1:]))
    return out


def later_refs(netfile):
    """Refs this stage places (earlier PCB stages skip them in their 'every part placed' checks)."""
    import netlist_pins
    nl = netlist_pins.parse(netfile)
    padnet = {(r, p): n for r, rows in nl.items() for p, fn, n in rows}
    text = open(netfile, encoding="utf-8").read().split("(libparts")[0]
    comps = {}
    for blk in re.split(r'\(comp\s+\(ref\s+"', text)[1:]:
        ref = blk[:blk.index('"')]
        fp = re.search(r'\(footprint\s+"([^"]*)"\)', blk)
        comps[ref] = {"footprint": fp.group(1) if fp else "", "value": re.search(r'\(value\s+"([^"]*)"\)', blk).group(1)}
    ro = roles_of(comps, padnet)
    return {ro[k] for k in ("module", "cout") if k in ro} | set(ro.get("cin", []))


class _Lib:
    """board_fix_pcb stand-in for hw_protect.new_footprint: footprints from dingoPDM.pretty."""
    def __init__(self, F, kfp):
        self.KFP, self.sync_fields = kfp, F.sync_fields


def pcb(path, netfile, board):
    import pcbnew
    import board_fix_pcb as F
    import netlist_pins
    import pcb_rework
    mm, tomm = pcbnew.FromMM, pcbnew.ToMM

    def V(x, y):
        return pcbnew.VECTOR2I(mm(x), mm(y))

    def xy(it):
        p = it.GetPosition()
        return round(tomm(p.x), 4), round(tomm(p.y), 4)

    comps = F.read_netlist(netfile)
    nl = netlist_pins.parse(netfile)
    padnet = {(r, p): n for r, rows in nl.items() for p, fn, n in rows}
    ro = roles_of(comps, padnet)
    if sorted(ro) != ["cin", "cout", "module"] or len(ro["cin"]) != 2:
        raise SystemExit(f"hw_5v_module pcb: netlist roles {ro} (run 'hw_5v_module.py sch {board}')")
    b = pcbnew.LoadBoard(path)
    if b.FindFootprintByReference(ro["module"]) is not None:
        print("hw_5v_module pcb: already applied")
        return

    def netinfo(name):
        ni = b.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(b, name)
            ni.thisown = False
            b.Add(ni)
        return ni
    # ---------------------------------------------------------------- 1. the TSR goes (its pad spots: track ends)
    if OLD[board] in comps:
        raise SystemExit(f"{OLD[board]} is still in the netlist")
    old = b.FindFootprintByReference(OLD[board])
    if old is not None:
        if "TRACO_TSR-1" not in old.GetFPIDAsString():
            raise SystemExit(f"{OLD[board]}: not the TSR footprint")
        opad = {p.GetNumber(): (xy(p), p.GetNetname()) for p in old.Pads()}
        if {n: opad[n] for n in "13"} != {n: (OLD_PADS[n], net) for n, net in (("1", "+12P"), ("3", "+5VP"))}:
            raise SystemExit(f"{OLD[board]} pads: {opad}, expected {OLD_PADS}")
    vin_end, vout_end = OLD_PADS["1"], OLD_PADS["3"]
    for n, pt, net in (("1", vin_end, "+12P"), ("3", vout_end, "+5VP")):
        if not any(t.GetClass() == "PCB_TRACK" and t.GetNetname() == net and (same(xy_s(t, tomm), pt) or same(xy_e(t, tomm), pt))
                   for t in b.GetTracks()):
            raise SystemExit(f"no {net} track ends at the old TSR pad {n} {pt}")
    if old is not None:
        b = pcb_rework.remove_and_reload(b, [old], path)
    # ---------------------------------------------------------------- 2. parts
    edge = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(edge)
    L = _Lib(F, os.path.dirname(LIB))
    mod = H.new_footprint(b, L, pcbnew, comps[ro["module"]], padnet, netinfo)
    mod.SetPosition(V(*MOD_AT))
    for rot in (-90, 90, 0, 180):
        mod.SetOrientationDegrees(rot)
        P = {p.GetNumber(): xy(p) for p in mod.Pads()}
        if P["3"][1] < MOD_AT[1] - 1 and P["6"][1] > MOD_AT[1] + 1 and P["6"][0] < P["1"][0]:
            break
    else:
        raise SystemExit("no module rotation puts VIN toward +12P and VOUT left")
    added = [mod]
    for (x, y), ref, part in ((CIN_AT[0], ro["cin"][0], CIN), (CIN_AT[1], ro["cin"][1], CIN), (COUT_AT, ro["cout"], COUT)):
        fp = H.new_footprint(b, F, pcbnew, comps[ref], padnet, netinfo)
        fp.SetPosition(V(x, y))
        for rot in (90, 270):
            fp.SetOrientationDegrees(rot)
            q = {p.GetNumber(): xy(p) for p in fp.Pads()}
            if q["1"][1] < q["2"][1] - 1.0:
                break
        else:
            raise SystemExit(f"{ref}: no rotation with pad 1 on top")
        added.append(fp)
    for fp in added:                                    # every schematic field on the footprint (parity), as hw_protect
        for name, v in comps[fp.GetReference()]["fields"].items():
            if name in ("Reference", "Value", "Footprint"):
                continue
            f = next((x for x in fp.GetFields() if x.GetName() == name), None)
            if f is None and v:
                f = pcbnew.PCB_FIELD(fp, fp.GetNextFieldId(), name)
                f.SetText(v)
                f.SetVisible(False)
                f.SetLayer(pcbnew.F_Fab)
                f.SetPosition(fp.GetPosition())
                f.thisown = False
                fp.AddField(f)
            elif f is not None and v and f.GetText() != v:
                f.SetText(v)
    for fp in added:
        fp.BuildCourtyardCaches()
        fp.Reference().SetVisible(False)
        for p in fp.Pads():
            if p.GetNetname() == "GND":
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    # courtyards: inside the freed TSR outline, clear of every fitted part (the DNP alternates U1 / U12 / U14 cover it)
    for fp in added:
        cb = fp.GetCourtyard(pcbnew.F_Cu).BBox()
        box = (tomm(cb.GetLeft()), tomm(cb.GetTop()), tomm(cb.GetRight()), tomm(cb.GetBottom()))
        if not (FREED[0] <= box[0] and FREED[1] <= box[1] and box[2] <= FREED[2] and box[3] <= FREED[3]):
            raise SystemExit(f"{fp.GetReference()} courtyard {box} leaves the TSR outline {FREED}")
        for o in b.GetFootprints():
            if o.GetReference() == fp.GetReference() or o.IsDNP():
                continue
            oc = o.GetCourtyard(pcbnew.F_Cu)
            if oc.OutlineCount() and fp.GetCourtyard(pcbnew.F_Cu).Collide(oc.Outline(0)):
                raise SystemExit(f"{fp.GetReference()} courtyard overlaps {o.GetReference()}")
    # ---------------------------------------------------------------- 3. copper
    K = H.Copper(b, pcbnew, mm, tomm, V, edge)
    P = {p.GetNumber(): xy(p) for p in mod.Pads()}
    ep = P["11"]
    cin = [{p.GetNumber(): xy(p) for p in b.FindFootprintByReference(r).Pads()} for r in ro["cin"]]
    cout = {p.GetNumber(): xy(p) for p in b.FindFootprintByReference(ro["cout"]).Pads()}
    log = []

    def track(net, pts, w):
        for a, c in zip(pts, pts[1:]):
            seg = pcbnew.SHAPE_SEGMENT(V(*a), V(*c), mm(w))
            if not K.clear(net, lambda Ly: seg, ["F.Cu"]):
                raise SystemExit(f"{net} track {a} -> {c} (w {w}) too close to other copper")
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(V(*a))
            t.SetEnd(V(*c))
            t.SetWidth(mm(w))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNet(b.FindNet(net))
            b.Add(t)
        log.append(f"{net} {pts[0]}->{pts[-1]} w {w}")

    def via(net, pt, d, drill):
        ring = pcbnew.SHAPE_CIRCLE(V(*pt), mm(d / 2))
        if not K.clear(net, lambda Ly: ring, list(K.cu), (pt[0], pt[1], drill / 2)):
            raise SystemExit(f"{net} via at {pt} too close to other copper / drills")
        if not edge.Contains(V(*pt)):
            raise SystemExit(f"via {pt} off the board")
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(V(*pt))
        v.SetWidth(mm(d))
        v.SetDrill(mm(drill))
        v.SetNet(b.FindNet(net))
        b.Add(v)
        log.append(f"via {net} {pt} {d}/{drill}")
    track("+12P", [P["3"], (P["3"][0], vin_end[1]), vin_end], 0.3)            # VIN to the +12P track (old pad 1 spot)
    track("+12P", [P["4"], P["3"]], 0.25)                                    # EN -> VIN
    track("GND", [P["2"], P["1"]], 0.25)                                     # MODE -> GND (auto PFM)
    track("GND", [P["1"], (P["1"][0], ep[1])], 0.25)                         # GND pin 1 -> exposed pad
    track("+5VP", [P["7"], P["6"]], 0.25)                                    # FB -> VOUT
    track("+5VP", [P["6"], (P["6"][0], vout_end[1]), vout_end], 0.4)         # VOUT to the +5VP track (old pad 3 spot)
    track("GND", [(ep[0] + 1.2, ep[1]), cin[0]["2"], cin[1]["2"]], 0.4)      # input loop: C_in GND -> exposed pad
    for dx in EP_VIAS:
        via("GND", (round(ep[0] + dx, 4), ep[1]), VIP_D, VIP_DRILL)
    track("GND", [cout["2"], COUT_VIA], 0.4)
    via("GND", COUT_VIA, H.VIA_D, H.VIA_DRILL)
    # capacitor pad 1 must sit on its rail track
    for ref, net in ((ro["cin"][0], "+12P"), (ro["cin"][1], "+12P"), (ro["cout"], "+5VP")):
        p1 = next(p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == "1")
        if not any(t.GetNetname() == net and t.GetClass() == "PCB_TRACK" and t.IsOnLayer(pcbnew.F_Cu)
                   and t.GetEffectiveShape(pcbnew.F_Cu).Collide(p1.GetEffectiveShape(pcbnew.F_Cu), 0) for t in b.GetTracks()):
            raise SystemExit(f"{ref} pad 1 does not touch a {net} track")
    for z in b.Zones():
        z.UnFill()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(path)
    for fp in added:
        print(f"  {fp.GetReference()} {fp.GetValue()} at {xy(fp)} rot {fp.GetOrientationDegrees():.0f}")
    for line in log:
        print("  copper:", line)
    print(f"hw_5v_module pcb: {OLD[board]} TSR removed, module {ro['module']} placed")


def xy_s(t, tomm):
    return tomm(t.GetStart().x), tomm(t.GetStart().y)


def xy_e(t, tomm):
    return tomm(t.GetEnd().x), tomm(t.GetEnd().y)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "lib":
        write_lib()
    elif cmd == "sch" and len(sys.argv) == 3:
        sch(sys.argv[2])
    elif cmd == "pcb" and len(sys.argv) == 5:
        pcb(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(__doc__)
