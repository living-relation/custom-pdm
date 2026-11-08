"""Board A PCB update for the U8 dual swap (KiCad 10 pcbnew Python).

usage: python pcb_swap_board_a.py <board.kicad_pcb> <netlist.xml>

U8 keeps its place and its support parts (and their tracks). Changes:
1. Pad nets set from the schematic netlist; tracks follow their pads' new net names.
2. U9's group, U8's C24/D8, and copper that only served them are deleted.
3. R20 is turned 180 deg so its MCU-side track lands on its MCU-side pad.
4. The old PF_OUT1 output zone is split: PF_OUT1 (OUT0, left pads -> J3 pin 8) and PF_OUT2 (OUT1, right pads -> pin 7).
5. Old INPUT1 copper touching J3 pin 8 is removed (pin 8 is now an output).
Remaining connections (U8 pins 5/6 to R20/R19, INPUT1 from J3 pin 12) are routed by route_board_a.py.
KiCad 10 swig loses object types after BOARD.Remove(), so removals happen last.
"""
import sys
import xml.etree.ElementTree as ET
import pcbnew

PCB, NET = sys.argv[1], sys.argv[2]
mm, tomm = pcbnew.FromMM, pcbnew.ToMM
DELETE = "U9 R21 R22 R23 R24 C26 C27 C28 C29 D10 D11 C24 D8".split()
U9_SIDE = set(DELETE) | {"R19", "R20"}
J3_PIN8 = (6.67, 4.56)

b = pcbnew.LoadBoard(PCB)
fps = {fp.GetReference(): fp for fp in b.GetFootprints()}
TRACKS = list(b.GetTracks())
ZONES = list(b.Zones())

pinnet = {}
for net in ET.parse(NET).getroot().find("nets"):
    for node in net.findall("node"):
        pinnet[(node.get("ref"), node.get("pin"))] = net.get("name")


def netinfo(name):
    ni = b.FindNet(name)
    if ni is None:
        ni = pcbnew.NETINFO_ITEM(b, name)
        b.Add(ni)
    return ni


# ---- snapshot old nets
old_pads = {}
for r, fp in fps.items():
    for pad in fp.Pads():
        old_pads.setdefault(pad.GetNetname(), []).append((r, pad.GetNumber()))

# nets that only served the U9 side (U9 group + chip side of R19/R20): their copper goes
u9_local = set()
for n, ps in old_pads.items():
    if not n or n in ("GND", "+12V", "+3V3"):
        continue
    if all(r in U9_SIDE for r, _ in ps) and not any((r, p) in (("R19", "2"), ("R20", "2")) for r, p in ps):
        u9_local.add(n)
u9_local.add("PF_OUT2")            # old left output zone and vias
print("u9-side nets removed:", sorted(u9_local))

# ---- 1. R20: turn 180 deg so pad 1 (MCU side, PF_DSEL1_2) sits where pad 2 (old PF_DEN2) was
r20 = fps["R20"]
r20.SetOrientationDegrees(r20.GetOrientationDegrees() + 180)

# ---- 2. pad nets from netlist
changed = 0
for r, fp in fps.items():
    if r in DELETE:
        continue
    for pad in fp.Pads():
        key = (r, pad.GetNumber())
        if key in pinnet and pad.GetNetname() != pinnet[key]:
            pad.SetNet(netinfo(pinnet[key]))
            changed += 1
print("pad nets changed:", changed)

# ---- 3. old net -> new net for tracks (by the pads that keep their place; R20 by its turned pads)
r20_swap = {"1": "2", "2": "1"}
rename = {}
for n, ps in old_pads.items():
    if not n or n in u9_local:
        continue
    cands = set()
    for r, p in ps:
        if r in DELETE:
            continue
        if r == "R20":
            p = r20_swap[p]          # old pad p now sits where the other pad number is
            key = ("R20", p)
            # track that touched old pad 2 position now touches pad 1 -> its new net
        new = pinnet.get((r, p))
        if new:
            cands.add(new)
    if len(cands) == 1:
        new = cands.pop()
        if new != n:
            rename[n] = new
    elif len(cands) > 1:
        print("CONFLICT", n, cands)
print("track net renames:", dict(sorted(rename.items())))

# ---- 4. output zone split
out1_zone = [z for z in ZONES if z.GetNetname() == "PF_OUT1"]
assert len(out1_zone) == 1, "expected one PF_OUT1 zone"
oz = out1_zone[0]
layer = oz.GetLayer()
prio = oz.GetAssignedPriority()


def make_zone(net, pts):
    z = pcbnew.ZONE(b)
    z.SetLayerSet(oz.GetLayerSet())
    z.SetNet(netinfo(net))
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(oz.GetLocalClearance())
    z.SetMinThickness(oz.GetMinThickness())
    z.SetPadConnection(oz.GetPadConnection())
    z.SetIsFilled(False)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(x), mm(y))
    b.Add(z)
    return z


ZA = [(4.78, 0.05), (9.75, 0.05), (9.75, 7.3), (10.85, 7.3), (10.85, 10.67), (4.78, 10.67)]   # PF_OUT1, OUT0
ZB = [(10.25, 0.05), (22.35, 0.05), (22.35, 10.67), (11.45, 10.67), (11.45, 7.3), (10.25, 7.3)]  # PF_OUT2, OUT1
make_zone("PF_OUT1", ZA)
make_zone("PF_OUT2", ZB)


def inside(pts, x, y):
    c = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


# ---- 5. decide fate of every old track/via
remove = []
for t in TRACKS:
    n = t.GetNetname()
    if n in u9_local:
        remove.append(t)
        continue
    if n == "PF_OUT1" and t.GetClass() == "PCB_VIA":
        x, y = tomm(t.GetPosition().x), tomm(t.GetPosition().y)
        if inside(ZA, x, y):
            pass                                   # stays PF_OUT1
        elif inside(ZB, x, y):
            t.SetNet(netinfo("PF_OUT2"))
        else:
            remove.append(t)
        continue
    if n == "INPUT1":
        pts = [(tomm(t.GetStart().x), tomm(t.GetStart().y)), (tomm(t.GetEnd().x), tomm(t.GetEnd().y))]
        if any(abs(px - J3_PIN8[0]) < 0.05 and abs(py - J3_PIN8[1]) < 0.05 for px, py in pts):
            other = pts[1] if abs(pts[0][0] - J3_PIN8[0]) < 0.05 and abs(pts[0][1] - J3_PIN8[1]) < 0.05 else pts[0]
            print(f"INPUT1 stub removed on {t.GetLayerName()}; open end now at {other[0]:.3f},{other[1]:.3f}")
            remove.append(t)
        continue
    if n in rename:
        t.SetNet(netinfo(rename[n]))

# ---- 6. silkscreen pinout text
for d in b.GetDrawings():
    if d.GetClass() == "PCB_TEXT":
        s = d.GetText()
        if "8-IN1" in s:
            d.SetText(s.replace("7-OUT1", "7-OUT2").replace("8-IN1", "8-OUT1").replace("12-OUT2", "12-IN1"))
            print("silk text updated")

# ---- 6b. U8 value/fields copied from an existing BTS7008-2EPA footprint (U10)
u8, u10 = fps["U8"], fps["U10"]
u8.SetValue(u10.GetValue())
for f in u10.GetFields():
    name = f.GetName()
    if name in ("Reference", "Value", "Footprint"):
        continue
    tgt = next((g for g in u8.GetFields() if g.GetName() == name), None)
    if tgt is not None and tgt.GetText() != f.GetText():
        tgt.SetText(f.GetText())
        print(f"U8 field {name} -> {f.GetText()}")

# ---- 6c. U9's +12V thermal vias/tracks under its old exposed pad (now dangling)
U9_EP = (-13.6, 9.3, -6.0, 16.1)   # x0, y0, x1, y1 mm around old U9
def in_u9(x, y):
    return U9_EP[0] <= x <= U9_EP[2] and U9_EP[1] <= y <= U9_EP[3]
for t in TRACKS:
    if t.GetNetname() != "+12V" or t in remove:
        continue
    if t.GetClass() == "PCB_VIA":
        p = t.GetPosition()
        if in_u9(tomm(p.x), tomm(p.y)):
            remove.append(t)
    else:
        s, e = t.GetStart(), t.GetEnd()
        if in_u9(tomm(s.x), tomm(s.y)) or in_u9(tomm(e.x), tomm(e.y)):
            remove.append(t)

# ---- 7. removals last
for t in remove:
    b.Remove(t)
b.Remove(oz)
for z in ZONES:
    if z.GetNetname() in u9_local:
        b.Remove(z)
        print("removed old zone", z.GetNetname())
for r in DELETE:
    b.Remove(fps[r])
print(f"removed {len(remove)} tracks/vias, 1 zone, {len(DELETE)} footprints")

pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(PCB)
print("saved")
