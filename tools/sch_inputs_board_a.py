"""Board A schematic edit: input expansion connector J6 (JST GH 12-pin) on the MCU sheet.

Run from hardware/board-a after sch_swap_board_a.py / sch_repin_board_a.py. Edits files in place.

J6 pinout (to the input daughter board):
  1-5  IN_3..IN_7 -> PC10, PC11, PB4, PC13, PB3 (5 new inputs: the most that escape U4 without disturbing dingo's
       own signals). PC10/PC11/PC13 were dingo's expansion test points E1-E3 (TP8-TP10, removed); PB3 was SWO
       (trace output, not needed to program/debug; the Tag-Connect pin is left unused); PB4 was no-connect.
  6-8  not connected (kept so one input board design also fits board B, which has more spare pins)
  9    PF2_IS (PC2, spare analog; R12 set DNP so the unused IS2 buffer no longer drives it)
  10   +3V3 (pull-up supply for the input board DIP switches)
  11-12 GND
"""
import os, re, sys, uuid

KICAD10_SYM = r"C:\Users\danie\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols\Connector_Generic.kicad_sym"
LIB = "Connector_Generic:Conn_01x12"
FOOTPRINT = "Connector_JST:JST_GH_SM12B-GHS-TB_1x12-1MP_P1.25mm_Horizontal"
REF = "J6"
J_AT = (220.98, 60.96)          # symbol origin; pin n end = (215.9, 48.26 + 2.54 (n-1))
# How each input gets its net name on the MCU sheet:
#   ("nc", (x, y), name, side)   no-connect flag at a U4 pin end -> label ('R' = pin points right -> angle 0)
#   ("tp", ref, name)            test point symbol -> label at its pin (the wire to U4 stays)
#   ("relabel", (x, y), name)    existing local label renamed
MCU_PINS = [
    ("tp", "TP8", "IN_3"),                        # PC10 pin 51 (was E1)
    ("tp", "TP9", "IN_4"),                        # PC11 pin 52 (was E2)
    ("nc", (127.0, 90.805), "IN_5", "R"),         # PB4  pin 56
    ("tp", "TP10", "IN_6"),                       # PC13 pin 2 (was E3)
    ("relabel", (138.43, 88.265), "IN_7"),        # PB3  pin 55 (was SWO)
]
N_IN = len(MCU_PINS)                              # J6 pins 1..N_IN carry IN_3..; the rest up to 8 are not connected
SWO_TAG_SIDE = (38.1, 172.72)                     # SWO label at the Tag-Connect (J4) -> renamed SWO_UNUSED
TESTPOINT_LIB = "Connector:TestPoint"             # every test point on every sheet is removed (Dan, 2026-11-08)
PWR_REFS = ["#PWR122", "#PWR123", "#PWR124"]


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


def u():
    return str(uuid.uuid4())


def instance(t, ref):
    i = t.index(f'"Reference" "{ref}"')
    s = t.rfind("\n\t(symbol", 0, i) + 2
    return s, block_end(t, s)


def fmt(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


def label(name, x, y, ang):
    just = "left bottom" if ang == 0 else "right bottom"
    return (f'(label "{name}"\n\t\t(at {fmt(x)} {fmt(y)} {ang})\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t)\n\t\t\t(justify {just})\n\t\t)\n\t\t(uuid "{u()}")\n\t)')


def renew_uuids(b):
    return re.sub(r'\(uuid "[^"]+"\)', lambda m: f'(uuid "{u()}")', b)


def _shift_props(b, ox, oy, x, y):
    """Shift every (at ...) after the first (the symbol origin) by the move (ox, oy) -> (x, y)."""
    out, first = [], True
    pos = 0
    for q in re.finditer(r"\(at ([\d.\-]+) ([\d.\-]+) (\d+)\)", b):
        out.append(b[pos:q.start()])
        if first:
            out.append(q.group(0))
            first = False
        else:
            out.append(f"(at {fmt(float(q.group(1)) - ox + x)} {fmt(float(q.group(2)) - oy + y)} {q.group(3)})")
        pos = q.end()
    out.append(b[pos:])
    return "".join(out)


def set_ref(b, old, new):
    return b.replace(f'"Reference" "{old}"', f'"Reference" "{new}"').replace(f'(reference "{old}")', f'(reference "{new}")')


# ---------- MCU.kicad_sch ----------
p = "MCU.kicad_sch"
t = rd(p)
if f'"Reference" "{REF}"' in t:
    raise SystemExit(f"{REF} already present (script already run?)")

# 1. library symbol
if f'(symbol "{LIB}"' not in t:
    lt = rd(KICAD10_SYM)
    s = lt.index('\n\t(symbol "Conn_01x12"') + 2
    sym = lt[s:block_end(lt, s)]
    if "(extends" in sym:
        raise SystemExit("Conn_01x12 extends another symbol; embed not handled")
    sym = sym.replace('(symbol "Conn_01x12"', f'(symbol "{LIB}"', 1)
    sym = "\n".join(("\t" + ln) if ln else ln for ln in sym.split("\n"))
    k = t.index("(lib_symbols") + len("(lib_symbols")
    t = t[:k] + "\n\t\t" + sym.lstrip("\t") + t[k:]

items = []


def relabel(t, at, new):
    pat = re.compile(r'\(label "[^"]+"(\s*\(at %s %s \d+\))' % (re.escape(fmt(at[0])), re.escape(fmt(at[1]))))
    t, n = pat.subn(lambda m: f'(label "{new}"' + m.group(1), t)
    if n != 1:
        raise SystemExit(f"label at {at}: {n} matches")
    return t


# 2. MCU pins -> labels
tp_at = {}
for kind, *rest in MCU_PINS:
    if kind == "nc":
        (x, y), name, side = rest
        pat = re.compile(r"\n\t\(no_connect\s*\(at %s %s\)\s*\(uuid \"[^\"]+\"\)\s*\)" % (re.escape(fmt(x)), re.escape(fmt(y))))
        t, n = pat.subn("", t)
        if n != 1:
            raise SystemExit(f"no_connect at {x},{y}: {n} matches")
        items.append(label(name, x, y, 0 if side == "R" else 180))
    elif kind == "tp":
        ref, name = rest
        s, e = instance(t, ref)
        m = re.search(r"\(at ([\d.\-]+) ([\d.\-]+) (\d+)\)", t[s:e])
        tp_at[ref] = (float(m.group(1)), float(m.group(2)))
        items.append(label(name, *tp_at[ref], 0))
    else:
        at, name = rest
        t = relabel(t, at, name)
t = relabel(t, SWO_TAG_SIDE, "SWO_UNUSED")

# 3. J6 pins
jx, jy = J_AT
pin_end = lambda n: (jx - 5.08, jy - 12.7 + 2.54 * (n - 1))
for n in range(1, 9):
    if n <= N_IN:
        items.append(label(f"IN_{n + 2}", *pin_end(n), 180))
    else:
        items.append(f'(no_connect\n\t\t(at {fmt(pin_end(n)[0])} {fmt(pin_end(n)[1])})\n\t\t(uuid "{u()}")\n\t)')
x9, y9 = pin_end(9)
items.append(f'(hierarchical_label "PF2_IS"\n\t\t(shape input)\n\t\t(at {fmt(x9)} {fmt(y9)} 180)\n\t\t(effects\n\t\t\t(font\n'
             f'\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify right)\n\t\t)\n\t\t(uuid "{u()}")\n\t)')

# power symbols cloned from existing instances on this sheet
s, e = instance(t, "#PWR022")                       # +3V3
p3 = t[s:e]
gnd_ref = next(r for r in re.findall(r'"Reference" "(#PWR\d+)"', t)
               if 'lib_id "power:GND"' in t[instance(t, r)[0]:instance(t, r)[1]])
s, e = instance(t, gnd_ref)
pg = t[s:e]
b = renew_uuids(set_ref(_shift_props(p3, *map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", p3).groups()), *pin_end(10)), "#PWR022", PWR_REFS[0]))
b = re.sub(r"\(at [\d.\-]+ [\d.\-]+ \d+\)", f"(at {fmt(pin_end(10)[0])} {fmt(pin_end(10)[1])} 90)", b, count=1)
items.append(b)
for k, n in ((1, 11), (2, 12)):
    g0 = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", pg)
    b = renew_uuids(set_ref(_shift_props(pg, float(g0.group(1)), float(g0.group(2)), *pin_end(n)), gnd_ref, PWR_REFS[k]))
    b = re.sub(r"\(at [\d.\-]+ [\d.\-]+ \d+\)", f"(at {fmt(pin_end(n)[0])} {fmt(pin_end(n)[1])} 270)", b, count=1)
    items.append(b)

# J6 instance, built from the R4 instance layout
s, e = instance(t, "R4")
r4 = t[s:e]
r0 = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", r4)
j = _shift_props(r4, float(r0.group(1)), float(r0.group(2)), jx, jy)
j = re.sub(r"\(at [\d.\-]+ [\d.\-]+ \d+\)", f"(at {fmt(jx)} {fmt(jy)} 0)", j, count=1)
j = j.replace('(lib_id "Device:R_Small_US")', f'(lib_id "{LIB}")')
j = set_ref(j, "R4", REF)
j = j.replace('"Value" "10K"', '"Value" "INPUTS IN3-IN10"')
j = j.replace('"Footprint" "Resistor_SMD:R_0805_2012Metric"', f'"Footprint" "{FOOTPRINT}"')
# reference/value text beside the body (rotation 0)
j = re.sub(r'(\(property "Reference" "J6"\s*\(at )[\d.\-]+ [\d.\-]+ \d+', rf"\g<1>{fmt(jx)} {fmt(jy - 17.78)} 0", j)
j = re.sub(r'(\(property "Value" "[^"]+"\s*\(at )[\d.\-]+ [\d.\-]+ \d+', rf"\g<1>{fmt(jx)} {fmt(jy + 17.78)} 0", j)
for prop in ("Digi-Key_PN", "LCSC"):
    m = re.search(r'\n\t\t\(property "%s"' % prop, j)
    if m:
        j = j[:m.start()] + j[block_end(j, m.start() + 3):]
j = re.sub(r'\n\t\t\(pin "1"[\s\S]*?\(pin "2"\s*\(uuid "[^"]+"\)\s*\)', "\n\t\t" + "\n\t\t".join(
    f'(pin "{n}"\n\t\t\t(uuid "{u()}")\n\t\t)' for n in range(1, 13)), j, count=1)
j = renew_uuids(j)
items.append(j)
items.append(f'(text "Input expansion J6 -> input daughter board (JST GH 12p).\\nIN_3..IN_7 = PC10 PC11 PB4 PC13 PB3; pins 6-8 NC.\\n'
             f'Pin 9 = PC2 spare analog (R12 DNP). Protection + pull DIPs live on the input board."\n\t\t(exclude_from_sim no)\n'
             f'\t\t(at {fmt(jx - 30.48)} {fmt(jy - 25.4)} 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
             f'\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "{u()}")\n\t)')

for marker in ("\n\t(sheet_instances", "\n\t(embedded_fonts"):
    if marker in t:
        k = t.index(marker)
        break
else:
    k = t.rstrip().rindex(")")           # sub-sheet: append before the file's closing paren
    while t[k - 1] in "\r\n\t ":
        k -= 1
t = t[:k] + "".join("\n\t" + it for it in items) + t[k:]
wr(p, t)

# ---------- HighCurrentDrivers.kicad_sch: R12 DNP ----------
p = "HighCurrentDrivers.kicad_sch"
t = rd(p)
s, e = instance(t, "R12")
b = t[s:e]
if "(dnp no)" not in b:
    raise SystemExit("R12 dnp flag not found")
t = t[:s] + b.replace("(dnp no)", "(dnp yes)", 1) + t[e:]
wr(p, t)
# ---------- all sheets: remove test point symbols ----------
import glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sch_tp_orphans import remove_orphans, testpoint_pins  # noqa: E402
removed, orphans = [], []
for f in sorted(glob.glob("*.kicad_sch")):
    x = rd(f)
    out, pos, hit = [], 0, False
    for m in re.finditer(r'\n\t\(symbol\s*\(lib_id "%s"\)' % re.escape(TESTPOINT_LIB), x):
        s = m.start() + 2
        e = block_end(x, s)
        out.append(x[pos:m.start()])
        removed.append(f + ":" + re.search(r'"Reference" "([^"]+)"', x[s:e]).group(1))
        pos, hit = e, True
    if hit:
        out.append(x[pos:])
        # labels / power symbols that only touched a removed test point's pin (ERC: tools/sch_tp_orphans.py)
        new, gone = remove_orphans("".join(out), set(testpoint_pins(x)))
        orphans += [f"{f}: {g}" for g in gone]
        wr(f, new)
print("test points removed:", removed)
print("test-point orphans removed:", orphans)

# ---------- DingoPDM.kicad_sch: remove the DRT logo G1 (J6 sits where it was; Dan, 2026-11-09) ----------
p = "DingoPDM.kicad_sch"
t = rd(p)
s, e = instance(t, "G1")
t = t[:s - 2] + t[e:]                      # also eat the newline + tab before the block
wr(p, t)
print("logo G1 removed")
print("input header schematic edits OK:", REF, "labels", len(MCU_PINS), "power", len(PWR_REFS), "R12 DNP")
