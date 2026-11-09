"""Board B schematic edit (dingoPDM-Max base): 4 new 15 A channels (BTS7004-1EPP) + input expansion connector.

Run from hardware/board-b-max on the unmodified baseline (git checkout the baseline first). Edits files in place.

Decisions (Dan, 2026-11-09): board B = 2 x 30 A + 6 x 15 A outputs; the 4 extra channels and ~9 extra inputs use the
MCU's own spare pins (F1a, no add-on ADC).

What it adds
  * BTS7004_1EPP.kicad_sch  - one 15 A channel, copied from dingoPDM v7.5 (MIT) BTS700n_1EPP sheet
                              (TSDSO-14, RSENSE 1.2k: BTS7004 kILIS = 20000 -> 0.9 V at 15 A).
  * HighCurrentDrivers2.kicad_sch - copy of the Max's HighCurrentDrivers page (4 channel sheets + LM324 IS buffer),
                              pointed at BTS7004_1EPP and renamed to channels 5-8. Channels 5+6 and 7+8 share a DEN pin.
  * MCU pins (were no-connect):
        PF_IN5 PA8 (TIM1_CH1)   PF_IN6 PB10 (TIM2_CH3)   PF_IN7 PA15 (TIM2_CH1)   PF_IN8 PC8 (TIM8_CH3)
        PF_DEN5_6 PB12          PF_DEN7_8 PB15
        PF_IS5 PA2 (ADC_IN2)    PF_IS6 PA4 (ADC_IN4)     PF_IS7 PA7 (ADC_IN7)     PF_IS8 PC4 (ADC_IN14)
        B_IN3..B_IN10 = PC14 PC15 PB2 PD2 PB4 PB5 PC10 PC11        B_AN = PB1 (ADC_IN9)
  * Connectors sheet: J6 = Deutsch DT15-12PA (same as J4): pins 1-2 OUT5, 3-4 OUT6, 5-6 OUT7, 7-8 OUT8, 9-12 NC.
                      J7 = JST GH 12 to input board #3: 1-8 B_IN3..10, 9 B_AN, 10 +3V3, 11-12 GND.
  * All test points removed (Dan: no test points).
"""
import glob
import os
import re
import subprocess
import uuid

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASE_1EPP = "542b3b9:hardware/board-a/BTS700n_1EPP.kicad_sch"     # dingoPDM v7.5 baseline (MIT)
PROJECT = "dingoPDM-Max"
ROOT = "dingoPDM-Max.kicad_sch"
NETLIST = os.path.join(os.environ.get("TEMP", "."), "boardb_base.net")
GH12 = "Connector_JST:JST_GH_SM12B-GHS-TB_1x12-1MP_P1.25mm_Horizontal"

OUT_PINS = {  # net: (U4 pin name, shape)
    "PF_IN5": ("PA8", "output"), "PF_IN6": ("PB10", "output"), "PF_IN7": ("PA15", "output"), "PF_IN8": ("PC8", "output"),
    "PF_DEN5_6": ("PB12", "output"), "PF_DEN7_8": ("PB15", "output"),
    "PF_IS5": ("PA2", "input"), "PF_IS6": ("PA4", "input"), "PF_IS7": ("PA7", "input"), "PF_IS8": ("PC4", "input"),
}
IN_PINS = {"B_IN3": "PC14", "B_IN4": "PC15", "B_IN5": "PB2", "B_IN6": "PD2", "B_IN7": "PB4", "B_IN8": "PB5",
           "B_IN9": "PC10", "B_IN10": "PC11", "B_AN": "PB1"}
RENAME_HCD2 = {"PF_IN1": "PF_IN5", "PF_IN2": "PF_IN6", "PF_IN3": "PF_IN7", "PF_IN4": "PF_IN8",
               "PF_DEN1": "PF_DEN5_6", "PF_DEN2": "PF_DEN5_6", "PF_DEN3": "PF_DEN7_8", "PF_DEN4": "PF_DEN7_8",
               "PF_IS1": "PF_IS5", "PF_IS2": "PF_IS6", "PF_IS3": "PF_IS7", "PF_IS4": "PF_IS8",
               "PF_OUT1": "PF_OUT5", "PF_OUT2": "PF_OUT6", "PF_OUT3": "PF_OUT7", "PF_OUT4": "PF_OUT8"}
HCD2_AT = (231.14, 50.8)        # root sheet block position
J6_AT = (167.64, 56.515)        # Connectors sheet
J7_AT = (220.98, 56.515)        # right of J6 (the lower right holds the Deutsch connector picture)


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
    """(start, end) of every top-level block '\n\t(<head>' in a schematic file."""
    out = []
    for m in re.finditer(r"\n\t\(%s[\s(]" % re.escape(head), t):
        s = m.start() + 2
        out.append((s, block_end(t, s)))
    return out


def symbol_by_ref(t, ref):
    for s, e in top_blocks(t, "symbol"):
        b = t[s:e]
        if f'"Reference" "{ref}"' in b or f'(reference "{ref}")' in b:
            return s, e
    raise KeyError(ref)


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


def ensure_libsym(t, lib_id, src):
    if f'\n\t\t(symbol "{lib_id}"' in t:
        return t
    s = src.index(f'\n\t\t(symbol "{lib_id}"') + 1
    sym = src[s:block_end(src, s + 2)]
    k = t.index("(lib_symbols") + len("(lib_symbols")
    return t[:k] + "\n" + sym + t[k:]


def set_instances(b, paths_refs):
    """Replace a symbol's (instances ...) block with one project and the given [(path, ref)]."""
    i = b.index("(instances")
    s = b.rfind("\n", 0, i) + 1
    e = block_end(b, i)
    unit = re.search(r"\n\t\t\(unit (\d+)\)", b).group(1)
    ind = b[s:i]
    lines = [f"{ind}(instances", f'{ind}\t(project "{PROJECT}"']
    for path, ref in paths_refs:
        lines += [f'{ind}\t\t(path "{path}"', f'{ind}\t\t\t(reference "{ref}")', f"{ind}\t\t\t(unit {unit})", f"{ind}\t\t)"]
    lines += [f"{ind}\t)", f"{ind})"]
    return b[:s] + "\n".join(lines) + b[e:]


def set_ref_prop(b, ref):
    return re.sub(r'\(property "Reference" "[^"]+"', f'(property "Reference" "{ref}"', b, count=1)


def renew_uuids(b):
    return re.sub(r'\(uuid "[^"]+"\)', lambda m: f'(uuid "{u()}")', b)


def move_block(b, x, y, ang=None):
    """Move a symbol/label block so its first (at) is (x, y); shift every other (at) by the same amount."""
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


class Refs:
    def __init__(self, used):
        self.next = {}
        for r in used:
            m = re.match(r"(#?[A-Za-z_]+)(\d+)$", r)
            if m:
                self.next[m.group(1)] = max(self.next.get(m.group(1), 1), int(m.group(2)) + 1)

    def new(self, prefix):
        n = self.next.get(prefix, 1)
        self.next[prefix] = n + 1
        w = 3 if prefix == "#PWR" else 0
        return f"{prefix}{n:0{w}d}"


def prefix(ref):
    return re.match(r"(#?[A-Za-z_]+)", ref).group(1)


# ---------------------------------------------------------------- setup
if os.path.exists("BTS7004_1EPP.kicad_sch") or os.path.exists("HighCurrentDrivers2.kicad_sch"):
    raise SystemExit("board B edits already applied (start from the baseline)")
cli = os.path.join(os.environ["LOCALAPPDATA"], r"Programs\KiCad\10.0\bin\kicad-cli.exe")
subprocess.run([cli, "sch", "export", "netlist", ROOT, "-o", NETLIST], check=True, capture_output=True)
used = set(re.findall(r'\(ref\s+"([^"]+)"\)', rd(NETLIST)))
for f in glob.glob("*.kicad_sch"):                         # power symbols are not in the netlist
    used |= set(re.findall(r'\(reference "([^"]+)"\)', rd(f)))
refs = Refs(used)

root = rd(ROOT)
root_uuid = re.search(r'\n\t\(uuid "([^"]+)"\)', root).group(1)
hcd_s, hcd_e = next((s, e) for s, e in top_blocks(root, "sheet") if '"HighCurrentDrivers.kicad_sch"' in root[s:e])
hcd_uuid = re.search(r'\(uuid "([^"]+)"\)', root[hcd_s:hcd_e]).group(1)
hcd2_uuid = u()
HCD2_PATH = f"/{root_uuid}/{hcd2_uuid}"

# ---------------------------------------------------------------- HighCurrentDrivers2 page
t = rd("HighCurrentDrivers.kicad_sch")
t = re.sub(r'(\n\t\(uuid ")[^"]+', lambda m: m.group(1) + u(), t, count=1)       # file uuid
sheets = top_blocks(t, "sheet")
# channel number follows the page's labels (OUT1 top .. OUT4 bottom), i.e. the sheets' y order, not file order
order = sorted(range(len(sheets)), key=lambda i: float(re.search(r"\(at [\d.\-]+ ([\d.\-]+)", t[sheets[i][0]:sheets[i][1]]).group(1)))
rank = {i: order.index(i) for i in range(len(sheets))}
child_paths = [None] * len(sheets)
out, pos = [], 0
for i, (s, e) in enumerate(sheets):
    n = rank[i]
    b = t[s:e]
    cu = u()
    b = re.sub(r'\(uuid "[^"]+"\)', f'(uuid "{cu}")', b, count=1)
    b = re.sub(r'(\(pin "[^"]+" \w+[\s\S]*?\(uuid ")[^"]+', lambda m: m.group(1) + u(), b)
    b = b.replace('"Sheetfile" "BTS700n_1EPP.kicad_sch"', '"Sheetfile" "BTS7004_1EPP.kicad_sch"')
    b = re.sub(r'"Sheetname" "[^"]+"', f'"Sheetname" "CH{5 + n}"', b)
    b = re.sub(r'\(path "[^"]+"\s*\(page "\d+"\)', f'(path "{HCD2_PATH}"\n\t\t\t\t\t(page "{15 + n}")', b)
    child_paths[n] = f"{HCD2_PATH}/{cu}"
    out += [t[pos:s], b]
    pos = e
out.append(t[pos:])
t = "".join(out)
if len(child_paths) != 4:
    raise SystemExit(f"expected 4 channel sheets, found {len(child_paths)}")
# symbols on the page: new refs (LM324 units share one ref), new uuids, new instance path
ref_map = {}
out, pos = [], 0
for s, e in top_blocks(t, "symbol"):
    b = t[s:e]
    old = re.search(r'\(reference "([^"]+)"\)', b).group(1)
    if old not in ref_map:
        ref_map[old] = refs.new(prefix(old))
    b = set_ref_prop(b, ref_map[old])
    b = set_instances(b, [(HCD2_PATH, ref_map[old])])
    b = renew_uuids(b)
    out += [t[pos:s], b]
    pos = e
out.append(t[pos:])
t = "".join(out)
for head in ("wire", "junction", "no_connect", "text", "polyline"):
    t = re.sub(r"(\n\t\(%s[\s\S]*?\(uuid \")[^\"]+" % head, lambda m: m.group(1) + u(), t)


def rename_global(m):
    return f'(global_label "{RENAME_HCD2.get(m.group(1), m.group(1))}"'


t = re.sub(r'\(global_label "([^"]+)"', rename_global, t)
t = re.sub(r'(\n\t\(global_label[\s\S]*?\n\t\t\(uuid ")[^"]+', lambda m: m.group(1) + u(), t)
t = re.sub(r'\(title "[^"]*"\)', '(title "15 A channels 5-8 (BTS7004-1EPP)")', t)
wr("HighCurrentDrivers2.kicad_sch", t)
print("HighCurrentDrivers2: refs", ref_map)

# ---------------------------------------------------------------- BTS7004 channel sheet (from dingoPDM, MIT)
t = subprocess.run(["git", "-C", REPO, "show", BASE_1EPP], check=True, capture_output=True).stdout.decode("utf-8")
t = t.replace("\r\n", "\n")
t = re.sub(r'(\n\t\(uuid ")[^"]+', lambda m: m.group(1) + u(), t, count=1)
out, pos, made = [], 0, {}
for s, e in top_blocks(t, "symbol"):
    b = t[s:e]
    old = re.search(r'"Reference" "([^"]+)"', b).group(1)
    new = [refs.new(prefix(old)) for _ in child_paths]
    made[old] = new
    b = set_ref_prop(b, new[0])
    b = set_instances(b, list(zip(child_paths, new)))
    if '(lib_id "Profet:BTS700n-1EPP")' in b:
        b = b.replace('"Value" "BTS700n-1EPP"', '"Value" "BTS7004-1EPP"')
        for prop in ("Digi-Key_PN", "LCSC"):
            m = re.search(r'\n\t\t\(property "%s"' % prop, b)
            if m:
                b = b[:m.start()] + b[block_end(b, m.start() + 3):]
    out += [t[pos:s], b]
    pos = e
out.append(t[pos:])
t = "".join(out)
t = re.sub(r'\(title "[^"]*"\)', '(title "15 A channel (BTS7004-1EPP) - from dingoPDM v7.5, MIT")', t)
wr("BTS7004_1EPP.kicad_sch", t)
print("BTS7004 sheet: U refs", made.get("U8"))

# ---------------------------------------------------------------- root: add the page
b = root[hcd_s:hcd_e]
b = re.sub(r'\(uuid "[^"]+"\)', f'(uuid "{hcd2_uuid}")', b, count=1)
b = re.sub(r'(\(pin "[^"]+" \w+[\s\S]*?\(uuid ")[^"]+', lambda m: m.group(1) + u(), b)
b = b.replace('"HighCurrentDrivers.kicad_sch"', '"HighCurrentDrivers2.kicad_sch"')
b = re.sub(r'"Sheetname" "[^"]+"', '"Sheetname" "HighCurrentDrivers2"', b)
b = re.sub(r'\(page "\d+"\)', '(page "14")', b)
b = move_block(b, *HCD2_AT)
root = insert_items(root, [b])
wr(ROOT, root)

# ---------------------------------------------------------------- MCU sheet: labels on U4 pins, test points out
t = rd("MCU.kicad_sch")
s, e = symbol_by_ref(t, "U4")
u4 = t[s:e]
lib = re.search(r'\(lib_id "([^"]+)"\)', u4).group(1)
X, Y, R = map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+) (\d+)\)", u4).groups())
if R != 0 or "(mirror" in u4[:300]:
    raise SystemExit("U4 rotated/mirrored: pin math not handled")
ls = t.index(f'\n\t\t(symbol "{lib}"')
lsym = t[ls:block_end(t, ls + 3)]
pin_end = {}
for px, py, name in re.findall(r'\(pin \w+ \w+\s*\(at ([\d.\-]+) ([\d.\-]+) \d+\)[\s\S]*?\(name "([^"]+)"', lsym):
    pin_end.setdefault(name, (round(X + float(px), 4), round(Y - float(py), 4)))


def pin_at(name):
    return next(v for k, v in pin_end.items() if k == name or k.startswith(name + "/") or k.startswith(name + "-"))


# global label templates: one right of U4 (angle 0), one left (angle 180)
glabels = {re.search(r'\(global_label "([^"]+)"', t[s2:e2]).group(1): t[s2:e2] for s2, e2 in top_blocks(t, "global_label")}
if not glabels:
    glabels = {re.search(r'\(global_label "([^"]+)"', root[s2:e2]).group(1): root[s2:e2] for s2, e2 in top_blocks(root, "global_label")}
tpl_r = next(v for v in glabels.values() if re.search(r"\(at [\d.\-]+ [\d.\-]+ 0\)", v))
tpl_l = next(v for v in glabels.values() if re.search(r"\(at [\d.\-]+ [\d.\-]+ 180\)", v))


def glabel(name, x, y, side_right, shape):
    b = tpl_r if side_right else tpl_l
    b = re.sub(r'\(global_label "[^"]+"', f'(global_label "{name}"', b, count=1)
    b = re.sub(r"\(shape \w+\)", f"(shape {shape})", b, count=1)
    return renew_uuids(move_block(b, x, y))


def drop_nc(t, x, y):
    pat = re.compile(r"\n\t\(no_connect\s*\(at %s %s\)\s*\(uuid \"[^\"]+\"\)\s*\)" % (re.escape(fmt(x)), re.escape(fmt(y))))
    t, n = pat.subn("", t)
    if n != 1:
        raise SystemExit(f"no_connect at {x},{y}: {n} matches")
    return t


items = []
for net, (pin, shape) in OUT_PINS.items():
    x, y = pin_at(pin)
    t = drop_nc(t, x, y)
    items.append(glabel(net, x, y, x > X, shape))
# test points: PC10/PC11 points become input labels, every test point is removed
tp_at = {}
for s2, e2 in top_blocks(t, "symbol"):
    bb = t[s2:e2]
    if '(lib_id "Connector:TestPoint")' in bb:
        tp_at[re.search(r'"Reference" "([^"]+)"', bb).group(1)] = tuple(map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", bb).groups()))
for net, pin in IN_PINS.items():
    x, y = pin_at(pin)
    if pin in ("PC10", "PC11"):
        tp = {"PC10": "TP4", "PC11": "TP3"}[pin]
        tx, ty = tp_at[tp]
        items.append(glabel(net, tx, ty, False, "input"))
    else:
        t = drop_nc(t, x, y)
        items.append(glabel(net, x, y, x > X, "input"))
t = insert_items(t, items)
wr("MCU.kicad_sch", t)

removed, dropped_labels = [], []
KEEP = set(IN_PINS)                       # our new labels sit on the PC10/PC11 test point spots
for f in sorted(glob.glob("*.kicad_sch")):
    x = rd(f)
    spots = []
    out, pos, hit = [], 0, False
    for s2, e2 in top_blocks(x, "symbol"):
        if '(lib_id "Connector:TestPoint")' in x[s2:e2]:
            ref = re.search(r'"Reference" "([^"]+)"', x[s2:e2]).group(1)
            removed.append(ref)
            spots.append((ref, tuple(map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", x[s2:e2]).groups()))))
            out.append(x[pos:s2 - 2])
            pos, hit = e2, True
    if not hit:
        continue
    out.append(x[pos:])
    x = "".join(out)
    # labels that only marked a test point pin (CAN_TX/RX, I2C) would dangle: drop them
    for head in ("label", "global_label"):
        out, pos = [], 0
        for s2, e2 in top_blocks(x, head):
            name = re.search(r'\(%s "([^"]+)"' % head, x[s2:e2]).group(1)
            at = tuple(map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", x[s2:e2]).groups()))
            if name not in KEEP and any(abs(at[0] - p[0]) < .01 and abs(at[1] - p[1]) < .01 for _, p in spots):
                dropped_labels.append(name)
                out.append(x[pos:s2 - 2])
                pos = e2
        out.append(x[pos:])
        x = "".join(out)
    # power symbols that sat on a test point pin (TP1 GND) would float: drop them
    out, pos = [], 0
    for s2, e2 in top_blocks(x, "symbol"):
        bb = x[s2:e2]
        if '(lib_id "power:' in bb:
            at = tuple(map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", bb).groups()))
            if any(abs(at[0] - p[0]) < .01 and abs(at[1] - p[1]) < .01 for _, p in spots):
                dropped_labels.append(re.search(r'"Reference" "([^"]+)"', bb).group(1))
                out.append(x[pos:s2 - 2])
                pos = e2
    out.append(x[pos:])
    x = "".join(out)
    # PC13 (TP2): remove the wire run from the test point back to the U4 pin and flag the pin no-connect
    for r, p in spots:
        if r != "TP2" or f != "MCU.kicad_sch":
            continue
        ends = set(pin_end.values())
        cur, gone = p, []
        while True:
            hits = []
            for s2, e2 in top_blocks(x, "wire"):
                if (s2, e2) in gone:
                    continue
                q = tuple(map(float, re.search(r"\(xy ([\d.\-]+) ([\d.\-]+)\)\s*\(xy ([\d.\-]+) ([\d.\-]+)\)", x[s2:e2]).groups()))
                for a, b2 in (((q[0], q[1]), (q[2], q[3])), ((q[2], q[3]), (q[0], q[1]))):
                    if abs(a[0] - cur[0]) < .01 and abs(a[1] - cur[1]) < .01:
                        hits.append(((s2, e2), b2))
            if len(hits) != 1:
                raise SystemExit(f"PC13 wire walk: {len(hits)} wires at {cur}")
            gone.append(hits[0][0])
            cur = hits[0][1]
            if any(abs(cur[0] - a) < .01 and abs(cur[1] - b2) < .01 for a, b2 in ends):
                break
        for s2, e2 in sorted(gone, reverse=True):
            x = x[:s2 - 2] + x[e2:]
        x = insert_items(x, [f'(no_connect\n\t\t(at {fmt(cur[0])} {fmt(cur[1])})\n\t\t(uuid "{u()}")\n\t)'])
        print("PC13 test point wiring removed:", len(gone), "wires; pin flagged no-connect at", cur)
    wr(f, x)
print("test points removed:", removed, "labels dropped:", dropped_labels)

# ---------------------------------------------------------------- Connectors sheet: J6 outputs, J7 input board
t = rd("Connectors.kicad_sch")
s, e = symbol_by_ref(t, "J4")
j4 = t[s:e]
c_glab = {re.search(r'\(global_label "([^"]+)"', t[s2:e2]).group(1): t[s2:e2] for s2, e2 in top_blocks(t, "global_label")}
tpl = c_glab["PF_OUT1"]                         # angle 180, left of the connector pins


def jpin(at, n):
    return at[0] - 5.08, at[1] - 12.7 + 2.54 * (n - 1)


def conn(at, ref, value, footprint):
    b = move_block(j4, *at)
    b = set_ref_prop(b, ref)
    b = set_instances(b, [(re.search(r'\(path "([^"]+)"', j4).group(1), ref)])
    b = re.sub(r'"Value" "[^"]*"', f'"Value" "{value}"', b, count=1)
    b = re.sub(r'"Footprint" "[^"]*"', f'"Footprint" "{footprint}"', b, count=1)
    for prop in ("Digi-Key_PN", "LCSC"):
        if footprint != "Deutsch_DT:DT15-12PA":
            m = re.search(r'\n\t\t\(property "%s"' % prop, b)
            if m:
                b = b[:m.start()] + b[block_end(b, m.start() + 3):]
    return renew_uuids(b)


def clab(name, x, y, shape="output"):
    b = re.sub(r'\(global_label "[^"]+"', f'(global_label "{name}"', tpl, count=1)
    b = re.sub(r"\(shape \w+\)", f"(shape {shape})", b, count=1)
    return renew_uuids(move_block(b, x, y))


def nc(x, y):
    return f'(no_connect\n\t\t(at {fmt(x)} {fmt(y)})\n\t\t(uuid "{u()}")\n\t)'


# J4 re-pin (Dan G1a: no software current cap, gang connector pins for full current): BTS70012 = 31.3 A nominal,
# DT size 16 contact = 13 A, so OUT1-4 get 3 pins each (39 A); CAN and the 2 stock inputs move to J6 pins 9-12.
J4_AT = tuple(map(float, re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", j4).groups()))
J4_PINS = {1: "PF_OUT4", 2: "PF_OUT4", 3: "PF_OUT4", 4: "PF_OUT3", 5: "PF_OUT3", 6: "PF_OUT3",
           7: "PF_OUT1", 8: "PF_OUT1", 9: "PF_OUT1", 10: "PF_OUT2", 11: "PF_OUT2", 12: "PF_OUT2"}
J6_PINS = {1: "PF_OUT5", 2: "PF_OUT5", 3: "PF_OUT6", 4: "PF_OUT6", 5: "PF_OUT7", 6: "PF_OUT7", 7: "PF_OUT8", 8: "PF_OUT8",
           9: "CAN_H", 10: "CAN_L", 11: "INPUT1", 12: "INPUT2"}
SHAPE = {"CAN_H": "bidirectional", "CAN_L": "bidirectional", "INPUT1": "input", "INPUT2": "input"}
box = (J4_AT[0] - 8, J4_AT[1] - 15, J4_AT[0], J4_AT[1] + 16)   # J4's old pin wiring, left of its pins


def inbox(x, y):
    return box[0] <= x <= box[2] + .01 and box[1] <= y <= box[3]


for head in ("wire", "junction", "global_label"):
    out, pos = [], 0
    for s2, e2 in top_blocks(t, head):
        bb = t[s2:e2]
        pts = [tuple(map(float, q)) for q in re.findall(r"\((?:xy|at) ([\d.\-]+) ([\d.\-]+)", bb)[:2]]
        if head == "global_label":
            pts = pts[:1]
        if all(inbox(*p) for p in pts):
            out.append(t[pos:s2 - 2])
            pos = e2
    out.append(t[pos:])
    t = "".join(out)

items = []
for n, net in J4_PINS.items():
    items.append(clab(net, *jpin(J4_AT, n)))
j6, j7 = refs.new("J"), refs.new("J")
items.append(conn(J6_AT, j6, "OUTPUTS 5-8, CAN, IN1-2", "Deutsch_DT:DT15-12PA"))
for n, net in J6_PINS.items():
    items.append(clab(net, *jpin(J6_AT, n), SHAPE.get(net, "output")))
items.append(conn(J7_AT, j7, "INPUT BOARD B_IN3-10", GH12))
for n in range(1, 10):
    x, y = jpin(J7_AT, n)
    items.append(clab(f"B_IN{n + 2}" if n <= 8 else "B_AN", x, y, "input"))
# power pins 10-12 (templates cloned from other sheets)
hcd = rd("HighCurrentDrivers.kicad_sch")
t = ensure_libsym(t, "power:+3V3", hcd)
for lib_id, n, ang in (("power:+3V3", 10, 270), ("power:GND", 11, 90), ("power:GND", 12, 90)):
    src = hcd if lib_id == "power:+3V3" else t
    s2, e2 = next((a, z) for a, z in top_blocks(src, "symbol") if f'(lib_id "{lib_id}")' in src[a:z])
    b = src[s2:e2]
    x, y = jpin(J7_AT, n)
    r = refs.new("#PWR")
    b = move_block(b, x, y, ang)
    b = set_ref_prop(b, r)
    b = set_instances(b, [(re.search(r'\(path "([^"]+)"', j4).group(1), r)])
    items.append(renew_uuids(b))
t = insert_items(t, items)
wr("Connectors.kicad_sch", t)
print("connectors:", j6, "(outputs 5-8)", j7, "(input board)")
print("board B schematic edits OK")
