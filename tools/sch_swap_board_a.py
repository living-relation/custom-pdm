"""Board A schematic edit: replace U8 + U9 (2x BTS7002 sheets) with one BTS7008-2EPA dual sheet.

Run from hardware/board-a. Edits files in place (git tracks the diff). Files are written with LF endings.
"""
import re, uuid

ROOT = "/8948e307-9174-4227-9c28-3ff885e6e83d"
HC = ROOT + "/00000000-0000-0000-0000-00005f54b02a"          # HighCurrentDrivers sheet path
MED = ROOT + "/00000000-0000-0000-0000-00005f54bf48"         # MedCurrentDrivers sheet path
S1 = "00000000-0000-0000-0000-00005f5a40c0"                    # sheet instance that becomes the dual
S2 = "00000000-0000-0000-0000-00005f5a40c6"                    # sheet instance to delete (old U9)
NEW_PATH = HC + "/" + S1
TEMPLATE_TAIL = "/79a0dd8b-9c30-4339-961b-e86bb429e783"         # U10 instance path tail
REFMAP = {  # U10 instance ref -> new ref
    "U10": "U8", "R34": "R13", "R35": "R14", "R36": "R20", "R37": "R19",
    "C33": "C23", "C10": "C22", "R39": "R16", "R41": "R18", "C34": "C25",
    "R38": "R15", "R40": "R17", "D13": "D9",
    "#PWR074": "#PWR055", "#PWR072": "#PWR056", "#PWR075": "#PWR057", "#PWR076": "#PWR058",
}


def rd(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


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


def top_blocks(t, head):
    pat = re.compile(r"\n\t\(" + re.escape(head) + r"[\s\"]")
    return [(m.start() + 2, block_end(t, m.start() + 2)) for m in pat.finditer(t)]


def remove_block(t, pred, head):
    hits = [(s, e) for s, e in top_blocks(t, head) if pred(t[s:e])]
    if len(hits) != 1:
        raise SystemExit(f"expected 1 {head} match, got {len(hits)}")
    s, e = hits[0]
    return t[: s - 2] + t[e:]


def u():
    return str(uuid.uuid4())


# ---------- HighCurrentDrivers.kicad_sch ----------
p = "HighCurrentDrivers.kicad_sch"
t = rd(p)
t = remove_block(t, lambda b: f'(uuid "{S2}")' in b, "sheet")
t = remove_block(t, lambda b: "(xy 63.5 72.39) (xy 66.04 72.39)" in b, "wire")
t = remove_block(t, lambda b: '"Reference" "#PWR052"' in b, "symbol")


def move_label(t, name, new_at):
    blocks = [(s, e) for s, e in top_blocks(t, "global_label") if t[s:e].startswith(f'(global_label "{name}"')]
    if len(blocks) != 1:
        raise SystemExit(f"label {name}: {len(blocks)}")
    s, e = blocks[0]
    b2 = re.sub(r"\(at [\d.\-]+ [\d.\-]+ \d+\)", f"(at {new_at})", t[s:e], count=1)
    return t[:s] + b2 + t[e:]


t = move_label(t, "PF_IN2", "66.04 62.23 180")
t = move_label(t, "PF_DEN2", "66.04 58.42 180")
t = move_label(t, "PF_OUT2", "87.63 60.96 0")

# GND symbol to tie the now-unused IS2 buffer input (wire starts at 87.63 80.01)
s, e = [(s, e) for s, e in top_blocks(t, "symbol") if '"Reference" "#PWR054"' in t[s:e]][0]
g = t[s:e]
g = g.replace("(at 232.41 49.53 0)", "(at 87.63 80.01 0)")
g = re.sub(r"\(at 232\.41 ([\d.]+) 0\)", lambda m: f"(at 87.63 {float(m.group(1)) - 49.53 + 80.01:.4f} 0)", g)
g = g.replace("(at 232.537 53.9242 0)", "(at 87.757 84.4042 0)")
g = g.replace('"#PWR054"', '"#PWR061"')
g = re.sub(r'\(uuid "[^"]+"\)', lambda m: f'(uuid "{u()}")', g)
t = t[:e] + "\n\t" + g + t[e:]

# Convert sheet 1 to the dual sheet
s, e = [(s, e) for s, e in top_blocks(t, "sheet") if f'(uuid "{S1}")' in t[s:e]][0]
b = t[s:e]
for old, new in [("(size 21.59 13.97)", "(size 21.59 20.32)"),
                 ('"BTS700n_1EPP.kicad_sch"', '"BTS7008_2EPA.kicad_sch"'),
                 ("(at 66.04 59.0046 0)", "(at 66.04 65.3546 0)"),
                 ('(pin "IN" input', '(pin "IN0" input'),
                 ('(pin "OUT" output', '(pin "OUT0" output')]:
    if old not in b:
        raise SystemExit(f"sheet edit: {old} not found")
    b = b.replace(old, new)
pin_in = re.search(r'\(pin "DEN" input[\s\S]*?\n\t\t\)', b).group(0)
pin_out = re.search(r'\(pin "OUT0" output[\s\S]*?\n\t\t\)', b).group(0)


def mkpin(tmpl, old, new, old_at, new_at):
    x = tmpl.replace(f'(pin "{old}"', f'(pin "{new}"').replace(f"(at {old_at})", f"(at {new_at})")
    return re.sub(r'\(uuid "[^"]+"\)', f'(uuid "{u()}")', x, count=1)


new_pins = "\n\t\t".join([
    mkpin(pin_in, "DEN", "DSEL", "66.04 54.61 180", "66.04 58.42 180"),
    mkpin(pin_in, "DEN", "IN1", "66.04 54.61 180", "66.04 62.23 180"),
    mkpin(pin_out, "OUT0", "OUT1", "87.63 50.8 0", "87.63 60.96 0"),
])
k = b.index("\n\t\t(instances")
b = b[:k] + "\n\t\t" + new_pins + b[k:]
t = t[:s] + b + t[e:]
wr(p, t)

# ---------- rename PF_DEN2 -> PF_DSEL1_2 ----------
for f in ("HighCurrentDrivers.kicad_sch", "MCU.kicad_sch", "DingoPDM.kicad_sch"):
    x = rd(f)
    if x.count('"PF_DEN2"') == 0:
        raise SystemExit(f"no PF_DEN2 in {f}")
    wr(f, x.replace('"PF_DEN2"', '"PF_DSEL1_2"'))

# ---------- BTS7008_2EPA.kicad_sch: add instance refs for the new sheet path ----------
p = "BTS7008_2EPA.kicad_sch"
t = rd(p)
pat = re.compile(r'(\n(\t+)\(path "' + re.escape(MED + TEMPLATE_TAIL)
                 + r'"\n\t+\(reference "([^"]+)"\)\n\t+\(unit (\d+)\)\n\t+\))')
added = 0


def addinst(m):
    global added
    whole, ind, ref, unit = m.group(1), m.group(2), m.group(3), m.group(4)
    if ref not in REFMAP:
        raise SystemExit(f"no mapping for {ref}")
    added += 1
    return whole + f'\n{ind}(path "{NEW_PATH}"\n{ind}\t(reference "{REFMAP[ref]}")\n{ind}\t(unit {unit})\n{ind})'


t = pat.sub(addinst, t)
if added != len(REFMAP):
    raise SystemExit(f"added {added} instances, expected {len(REFMAP)}")
wr(p, t)
print("schematic edits OK; instances added:", added)
