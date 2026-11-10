"""Draw the connector maps (SVG): board pins, enclosure connectors and studs, and how the boards connect.

Illustrations only, NOT a source of truth: the KiCad schematics and docs/box-connectors.md are. Update the tables in
this script by hand when those change.   usage: python tools/gen_connector_maps.py [out_dir]   (default docs/diagrams)
"""
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "diagrams")
os.makedirs(OUT, exist_ok=True)

F = 'font-family="Segoe UI, Arial, sans-serif"'
INK, MUTE = "#1a1a1a", "#555"
C = {  # group: (fill, stroke)
    "out30": ("#fecaca", "#991b1b"), "out15": ("#bfdbfe", "#1e40af"), "a1": ("#bbf7d0", "#166534"),
    "a2": ("#fde68a", "#92400e"), "b": ("#ddd6fe", "#6d28d9"), "can": ("#fbcfe8", "#9d174d"),
    "gnd": ("#d1d5db", "#374151"), "pwr": ("#fecaca", "#991b1b"), "spare": ("#ffffff", "#9ca3af"),
    "pend": ("#fff7ed", "#ea580c"), "in": ("#bbf7d0", "#166534"), "v33": ("#fed7aa", "#9a3412"),
}


def t(x, y, s, size=13, w=400, fill=INK, anchor="start"):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}">{s}</text>'


def cell(x, y, w, h, num, label, grp):
    f, s = C[grp]
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{f}" stroke="{s}" stroke-width="2"/>'
            + t(x + w / 2, y + 17, num, 13, 700, INK, "middle") + t(x + w / 2, y + 34, label, 11, 600, s, "middle"))


def grid(x, y, rows, cw=74, ch=42, gap=4):
    out = []
    for r, row in enumerate(rows):
        for c, (num, label, grp) in enumerate(row):
            out.append(cell(x + c * (cw + gap), y + r * (ch + gap), cw, ch, num, label, grp))
    return "".join(out)


def card(x, y, w, h, title, sub=""):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#f9fafb" stroke="#d1d5db"/>'
            + t(x + 16, y + 28, title, 17, 700) + (t(x + 16, y + 47, sub, 12, 400, MUTE) if sub else ""))


def svg(w, h, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" {F}><rect width="{w}" height="{h}" fill="#fff"/>{body}</svg>'


# ------------------------------------------------------------------ boards
b = [t(24, 36, "Board connectors - pin map", 22, 700),
     t(24, 58, "Illustration only: the schematics and docs/box-connectors.md are the source of truth. Board layouts for B are not done yet.", 13, 400, MUTE)]

# Board A
b.append(card(20, 76, 700, 450, "Board A (x2: A1 and A2)", "dingoPDM v7.5 based - 8 outputs at 7.5 A"))
b.append(t(36, 150, "J3 - Deutsch DT 12-pin (outputs, CAN, 2 inputs)", 14, 700))
a_top = [("1", "CAN_L", "can"), ("2", "CAN_H", "can"), ("3", "OUT8", "out15"), ("4", "OUT7", "out15"), ("5", "OUT6", "out15"), ("6", "OUT5", "out15")]
a_bot = [("12", "IN1", "in"), ("11", "IN2", "in"), ("10", "OUT3", "out15"), ("9", "OUT4", "out15"), ("8", "OUT1", "out15"), ("7", "OUT2", "out15")]
b.append(grid(36, 162, [a_top, a_bot]))
b.append(t(36, 286, "J6 - JST GH 12-pin (to its input board)", 14, 700))
a6 = [("1", "IN3", "in"), ("2", "IN4", "in"), ("3", "IN5", "in"), ("4", "IN6", "in"), ("5", "IN7", "in"), ("6", "-", "spare"),
      ("7", "-", "spare"), ("8", "-", "spare"), ("9", "ANALOG", "in"), ("10", "+3V3", "v33"), ("11", "GND", "gnd"), ("12", "GND", "gnd")]
b.append(grid(36, 298, [a6], cw=50))
b.append(t(36, 380, "Power terminals (bolt-down)", 14, 700))
b.append(grid(36, 392, [[("J1", "+12 V in", "pwr"), ("J2", "GND", "gnd")]], cw=110))

# Board B
b.append(card(740, 76, 700, 450, "Board B (x1)", "dingoPDM-Max based - 4 outputs at 31 A + 4 at 15 A"))
b.append(t(756, 150, "OUT1-8 - bolt-down terminals (Wuerth REDCUBE M4), one wire each", 14, 700))
b.append(grid(756, 162, [[(f"T{n}", f"OUT{n} 31 A", "out30") for n in range(1, 5)],
                         [(f"T{n}", f"OUT{n} 15 A", "out15") for n in range(5, 9)]], cw=110))
b.append(t(756, 286, "J6 - Molex Micro-Fit 2x2 (CAN and the 2 stock inputs)", 14, 700))
b.append(grid(756, 298, [[("1", "CAN_L", "can"), ("2", "CAN_H", "can"), ("3", "IN2", "in"), ("4", "IN1", "in")]]))
b.append(t(756, 372, "J7 - JST GH 12-pin, top entry (to its input board)", 14, 700))
b7 = [(str(n), f"IN{n + 2}", "in") for n in range(1, 9)] + [("9", "ANALOG", "in"), ("10", "+3V3", "v33"), ("11", "GND", "gnd"), ("12", "GND", "gnd")]
b.append(grid(756, 384, [b7], cw=50))
b.append(t(756, 458, "Power terminals (bolt-down)", 14, 700))
b.append(grid(756, 470, [[("J1", "+12 V in", "pwr"), ("J3", "GND", "gnd")]], cw=110))

# Input board
b.append(card(20, 542, 1420, 196, "Input board (x3: one per main board)", "protects the inputs and holds the pull-up / pull-down switches"))
b.append(t(36, 616, "J1 - JST GH 12-pin (to the main board)", 14, 700))
i1 = [(str(n), f"ch {n}", "in") for n in range(1, 9)] + [("9", "ANALOG", "in"), ("10", "+3V3", "v33"), ("11", "GND", "gnd"), ("12", "GND", "gnd")]
b.append(grid(36, 628, [i1], cw=50))
b.append(t(756, 616, "J2 - Molex Micro-Fit 2x6 (wires to enclosure connector X2)", 14, 700))
i2a = [(str(n), f"ch {n} wire", "in") for n in range(1, 7)]
i2b = [("7", "ch 7 wire", "in"), ("8", "ch 8 wire", "in"), ("9", "ANALOG", "in"), ("10", "GND", "gnd"), ("11", "GND", "gnd"), ("12", "GND", "gnd")]
b.append(grid(756, 628, [i2a, i2b], cw=80, ch=42))
b.append(t(36, 710, "Board A uses channels 1-5 (its IN3-IN7). Board B uses all 8 (its IN3-IN10).", 12, 400, MUTE))
open(os.path.join(OUT, "board-connectors.svg"), "w", encoding="utf-8").write(svg(1460, 758, "".join(b)))


# ------------------------------------------------------------------ enclosure
def cav(x, y, r, top, bot, grp, fs=13):
    f, s = C[grp]
    o = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{f}" stroke="{s}" stroke-width="2.5"/>'
    if bot:
        o += t(f"{x:.1f}", f"{y - 2:.1f}", top, fs, 700, INK, "middle") + t(f"{x:.1f}", f"{y + fs - 2:.1f}", bot, fs - 3, 700, s, "middle")
    else:
        o += t(f"{x:.1f}", f"{y + fs * 0.36:.1f}", top, fs, 700, INK, "middle")
    return o


def leg(x, y, grp, text):
    f, s = C[grp]
    return f'<rect x="{x}" y="{y - 13}" width="18" height="18" rx="4" fill="{f}" stroke="{s}" stroke-width="2"/>' + t(x + 26, y + 1, text, 13)


e = [t(24, 36, "Enclosure wall - connectors and studs", 22, 700),
     t(24, 58, "Illustration only (source of truth: docs/box-connectors.md). Rear view, the side the wires go in. One pin per output.", 13, 400, MUTE)]

# X1 24-21
e.append(card(20, 76, 470, 600, "X1 - all connector outputs", "HD34-24-21SN: 16 x 7.5 A (boards A) + 4 x 15 A (board B), one pin each"))
P21 = {"H": (322, 112), "J": (425, 132), "K": (507, 200), "L": (553, 295), "M": (553, 398), "N": (507, 490), "P": (425, 555),
       "R": (322, 580), "S": (222, 555), "T": (135, 490), "U": (90, 398), "V": (90, 295), "W": (135, 200), "X": (222, 132),
       "G": (262, 242), "B": (372, 242), "E": (262, 448), "D": (385, 448), "F": (197, 345), "A": (322, 345), "C": (452, 345)}
SIG21 = {}
for i, k in enumerate("HJKLMNPR"):
    SIG21[k] = (f"A1-{i + 1}", "a1")
for i, k in enumerate("STUVWXAC"):
    SIG21[k] = (f"A2-{i + 1}", "a2")
for i, k in enumerate("BDEG"):
    SIG21[k] = (f"B-{i + 5}", "b")
ox, oy, sc = 255, 372, 0.66
e.append(f'<circle cx="{ox}" cy="{oy}" r="{300 * sc + 6:.0f}" fill="#f3f4f6" stroke="#374151" stroke-width="3"/>')
for k, (px, py) in P21.items():
    x, y = ox + (px - 322) * sc, oy + (py - 345) * sc
    big = k in "GBED"
    lab, grp = SIG21.get(k, ("spare", "spare"))
    e.append(cav(x, y, 32 if big else 25, k, lab, grp, 13))
e.append(leg(40, 612, "a1", "A1-1 ... A1-8 = board A1 OUT1-8"))
e.append(leg(40, 636, "a2", "A2-1 ... A2-8 = board A2 OUT1-8"))
e.append(leg(40, 660, "b", "B-5 ... B-8 = board B OUT5-8 (15 A on 25 A pins); F spare"))

# X2 24-47
e.append(card(506, 76, 560, 600, "X2 - inputs, analog, CAN", "HDP24-24-47SE, small size-20 pins (big ones 1, 4, 5, 6, 34 are spare)"))
W = [(898.2, 505.3), (914.3, 515.2), (915.4, 533.3), (898.2, 543.2), (881.1, 533.3), (882.1, 515.2), (898.2, 490.4), (912.5, 500.2),
     (926.7, 505.3), (928.5, 520.7), (932.8, 538.2), (914.3, 551.3), (898.2, 561.2), (882.1, 551.3), (863.7, 538.2), (868.0, 520.7),
     (869.7, 505.3), (884.0, 500.2), (911.2, 482.4), (923.9, 490.4), (939.1, 496.5), (940.5, 511.7), (942.4, 526.6), (929.3, 553.0),
     (912.5, 566.3), (884.0, 566.3), (867.1, 553.0), (854.1, 526.6), (856.0, 511.7), (857.4, 496.5), (872.5, 490.4), (885.3, 482.4),
     (898.2, 469.1), (923.5, 473.6), (936.4, 481.7), (954.4, 517.5), (953.4, 536.9), (943.8, 548.6), (927.5, 568.0), (898.2, 576.4),
     (869.0, 568.0), (852.7, 548.6), (843.0, 536.9), (842.1, 517.5), (860.1, 481.7), (873.0, 473.6)]
pos47 = {1: (898.2, 522.8)}
for i, p in enumerate(W):
    pos47[i + 2] = p


def grp47(n):
    if n in (1, 4, 5, 6, 34) or n >= 39:
        return "spare"
    if n in (2, 3):
        return "can"
    if n <= 14:
        return "a1"
    if n <= 22:
        return "a2"
    if n <= 33:
        return "b"
    return "gnd"


ox, oy, sc = 786, 338, 3.0
e.append(f'<circle cx="{ox}" cy="{oy}" r="{64 * sc:.0f}" fill="#f3f4f6" stroke="#374151" stroke-width="3"/>')
for n, (px, py) in pos47.items():
    big = n in (1, 4, 5, 6, 34)
    e.append(cav(ox + (px - 898.2) * sc, oy + (py - 522.8) * sc, (8.1 if big else 5.94) * sc - 1.5, str(n), "", grp47(n), 13))
rows = [("can", "2 = CAN_H, 3 = CAN_L"), ("a1", "A1: 7-8 = IN1-2, 9-13 = IN3-7, 14 = analog"),
        ("a2", "A2: 15-16 = IN1-2, 17-21 = IN3-7, 22 = analog"), ("b", "B: 23-24 = IN1-2, 25-32 = IN3-10, 33 = analog"),
        ("gnd", "35-38 = signal ground"), ("spare", "spare: 39-47 (small); 1, 4, 5, 6, 34 (big)")]
e.append("".join(leg(526, 556 + 21 * i, g, s2) for i, (g, s2) in enumerate(rows)))

# studs (X3 removed: Dan 2026-11-09)
def stud(x, y, label, sub, grp):
    f, s = C[grp]
    return (f'<circle cx="{x}" cy="{y}" r="30" fill="{f}" stroke="{s}" stroke-width="3"/>'
            f'<polygon points="{x - 13},{y - 7.5} {x},{y - 15} {x + 13},{y - 7.5} {x + 13},{y + 7.5} {x},{y + 15} {x - 13},{y + 7.5}" fill="#fff" stroke="{s}" stroke-width="2"/>'
            + t(x + 44, y - 3, label, 15, 700) + t(x + 44, y + 16, sub, 12, 400, MUTE))


e.append(card(1082, 76, 470, 600, "Studs", "power in, and board B's four big outputs"))
e.append(stud(1140, 170, "BATT +12 V", "150 A feed from the battery", "pwr"))
e.append(stud(1140, 250, "GND", "chassis ground", "gnd"))
for i in range(4):
    e.append(stud(1140, 350 + 80 * i, f"OUT{i + 1}", "board B, 31 A - needs a rubber boot", "out30"))
e.append(t(1102, 652, "X3 (HDP 24-9) is no longer needed.", 13, 700, "#166534"))
open(os.path.join(OUT, "enclosure-connectors.svg"), "w", encoding="utf-8").write(svg(1572, 696, "".join(e)))

# ------------------------------------------------------------------ system wiring
def box(x, y, w, h, title, sub, fill="#ffffff", stroke="#374151"):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>'
            + t(x + w / 2, y + 26, title, 16, 700, INK, "middle") + t(x + w / 2, y + 45, sub, 12, 400, MUTE, "middle"))


def line(pts, col, w=4, dash=""):
    d = "M" + " L".join(f"{x} {y}" for x, y in pts)
    return f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w}" stroke-linejoin="round" {("stroke-dasharray=" + chr(34) + dash + chr(34)) if dash else ""}/>'


def note(x, y, s2, col=INK, anchor="start", size=12, w=600):
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{col}" text-anchor="{anchor}" '
            f'stroke="#fff" stroke-width="4" paint-order="stroke">{s2}</text>')


RED, GRY, PNK, GRN, BLU, DRD = "#dc2626", "#4b5563", "#be185d", "#15803d", "#1d4ed8", "#991b1b"
w3 = [t(24, 36, "How the boards connect inside the box", 22, 700),
      t(24, 58, "Illustration only (source of truth: schematics + docs/box-connectors.md). Thick lines are power.", 13, 400, MUTE),
      '<rect x="20" y="76" width="1560" height="800" rx="14" fill="#f9fafb" stroke="#9ca3af" stroke-width="2" stroke-dasharray="8 6"/>',
      t(40, 100, "enclosure", 12, 600, "#6b7280")]
rows3 = [("A1", 190, "Board A1", "8 x 7.5 A", "Input board 1", "5 inputs + analog"),
         ("A2", 420, "Board A2", "8 x 7.5 A", "Input board 2", "5 inputs + analog"),
         ("B", 650, "Board B", "4 x 31 A + 4 x 15 A", "Input board 3", "8 inputs + analog")]
MX, MW, IX, IW, H = 700, 260, 330, 220, 150
# studs and power buses
w3.append(stud(800, 122, "BATT +12 V stud", "150 A from the battery", "pwr"))
w3.append(stud(1130, 122, "GND stud", "chassis ground", "gnd"))
w3.append(line([(800, 152), (800, 166), (1010, 166), (1010, 675)], RED, 7))
w3.append(line([(1130, 152), (1130, 172), (1040, 172), (1040, 695)], GRY, 7))
for key, y, *_ in rows3:
    w3.append(line([(1010, y + 25), (MX + MW, y + 25)], RED, 7))
    w3.append(line([(1040, y + 45), (MX + MW, y + 45)], GRY, 7))
w3.append(note(1056, 440, "+12 V and ground to every board", GRY))
w3.append(note(1056, 458, "(board A: J1, J2 - board B: J1, J3)", GRY, w=400))
# X2 on the left wall
w3.append(box(40, 150, 150, 690, "X2", "47-pin", "#eef2ff", "#3730a3"))
w3.append(t(115, 215, "inputs", 12, 400, MUTE, "middle") + t(115, 231, "analog", 12, 400, MUTE, "middle") + t(115, 247, "CAN", 12, 400, MUTE, "middle"))
# CAN daisy chain
w3.append(line([(190, 168), (760, 168), (760, 190)], PNK, 4))
w3.append(line([(760, 340), (760, 420)], PNK, 4))
w3.append(line([(760, 570), (760, 650)], PNK, 4))
w3.append(note(200, 160, "CAN_H / CAN_L (twisted pair) to X2 pins 2, 3 - then to the Link ECU", PNK))
w3.append(note(772, 384, "CAN: A1 J3 pins 2, 1", PNK))
w3.append(note(772, 400, "to A2 J3 pins 2, 1", PNK))
w3.append(note(772, 614, "CAN: A2 J3 pins 2, 1", PNK))
w3.append(note(772, 630, "to B J6 pins 2, 1", PNK))
x2pins = {"A1": ("9-14", "7, 8"), "A2": ("17-22", "15, 16"), "B": ("25-33", "23, 24")}
for key, y, name, sub, iname, isub in rows3:
    w3.append(box(MX, y, MW, H, name, sub, "#ffffff"))
    w3.append(box(IX, y, IW, 100, iname, isub, "#f0fdf4", "#166534"))
    # input board <-> main board
    w3.append(line([(IX + IW, y + 75), (MX, y + 75)], GRN, 4))
    w3.append(note((IX + IW + MX) / 2, y + 68, "GH 12-pin cable", GRN, "middle"))
    w3.append(note((IX + IW + MX) / 2, y + 93, f"J1 to {'J7' if key == 'B' else 'J6'}", GRN, "middle", w=400))
    # input board -> X2
    w3.append(line([(IX, y + 60), (190, y + 60)], GRN, 4))
    w3.append(note(260, y + 53, f"J2 to X2 pins {x2pins[key][0]}", GRN, "middle"))
    w3.append(note(260, y + 78, "+ ground 35-38", GRN, "middle", w=400))
    # stock inputs IN1-2 -> X2
    w3.append(line([(MX, y + 128), (190, y + 128)], GRN, 3, "7 5"))
    src = "J6 pins 4, 3" if key == "B" else "J3 pins 12, 11"
    w3.append(note(445, y + 121, f"IN1, IN2: {src} to X2 pins {x2pins[key][1]}", GRN, "middle"))
# outputs to X1 and the studs
w3.append(box(1400, 190, 150, 570, "X1", "21-pin", "#eff6ff", "#1e40af"))
w3.append(t(1475, 255, "20 outputs", 12, 400, MUTE, "middle") + t(1475, 271, "one pin each", 12, 400, MUTE, "middle"))
w3.append(line([(MX + MW, 300), (1400, 300)], BLU, 5))
w3.append(note(1225, 293, "8 wires: J3 pins 3-10", BLU, "middle"))
w3.append(note(1225, 318, "to X1  H J K L M N P R", BLU, "middle", w=400))
w3.append(line([(MX + MW, 530), (1400, 530)], BLU, 5))
w3.append(note(1225, 523, "8 wires: J3 pins 3-10", BLU, "middle"))
w3.append(note(1225, 548, "to X1  S T U V W X A C", BLU, "middle", w=400))
w3.append(line([(MX + MW, 735), (1400, 735)], BLU, 5))
w3.append(note(1225, 728, "OUT5-8 (15 A): terminals T5-T8", BLU, "middle"))
w3.append(note(1225, 753, "to X1  B D E G", BLU, "middle", w=400))
w3.append(line([(MX + MW, 785), (1320, 785), (1320, 822), (1380, 822)], DRD, 7))
w3.append(stud(1410, 822, "4 output studs", "OUT1-4, 31 A each", "out30"))
w3.append(note(1140, 777, "OUT1-4: terminals T1-T4, one wire each", DRD, "middle"))
open(os.path.join(OUT, "system-wiring.svg"), "w", encoding="utf-8").write(svg(1600, 896, "".join(w3)))
print("ok")
