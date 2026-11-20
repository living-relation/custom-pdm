"""Load-dump TVS D2 on board A and board B: DO-218 footprint in a new spot + its clamp copper
(ADR-2026-11-20-tvs-loaddump, ADR-2026-11-20-d2-move).

  python   tools/d2_tvs.py lib                          write the footprint into the dingoPDM library (+ nothing else)
  python   tools/d2_tvs.py sch <Power.kicad_sch>        D2 symbol: footprint -> dingoPDM:D_DO-218AB_Vishay_SM8S
  python.exe (KiCad 9) tools/d2_tvs.py pcb <board.kicad_pcb> A|B   move D2 to its new spot, clamp copper (last PCB stage)

Part: Vishay SM8S24CAHM3/I (bidirectional, VBR 26.7-29.5 V, VC 38.9 V at IPPM 170 A, 6.6 kW 10/1000 us, 5.2 kW
10/10000 us; Vishay doc 98229 rev 23-Jan-2026). Order fields: tools/sch_bom_fields.py (C152086 row). Approved
alternates in the same DO-218 land pattern: Bourns SM8S24CA-Q (data sheet "Recommended Footprint": tab 9.0 x 10.0,
lead 2.0 x 2.7, 14.5 overall: inside this pattern), Panjit SM8H24CAS-AU (DO-218AB, body 9.7-10.3 / 8.7-9.3 / 4.7-5.0
mm: the same body as Vishay's).

Footprint (lib): Vishay doc 98229 page 5 "Mounting Pad Layout" (IPC-7351): heat-sink pad 9.80 x 10.70 mm, lead pad
2.15 x 2.60 mm, 3.35 mm between them, 15.30 mm overall. Origin = middle of the 15.30 mm pattern; pad 1 = lead
("Lead 1", +x), pad 2 = heat-sink tab ("Lead 2 / Metal Heatsink"). The symbol's pins keep their nets: pin 1 +12V,
pin 2 GND (so the tab, the part's heat path, sits on the GND planes). Paste on the tab: 2 x 2 windows (78 %).
Body (page 5, max): 16.0 overall, plastic 13.7 x 10.5 x 5.0 mm. Courtyard 16.5 x 11.2 mm (body / pads + 0.25).
3D model: Models/D_DO-218AB_Vishay_SM8S.step (drawn from the page-5 maximum dimensions; the maker's CAD sits behind the
Ultra Librarian login).

Placement (pcb): D2 alone moves; every other footprint, pad, hole and terminal stays (tools/board_semdiff.py proves
it). The old spot (-33.66, 30.59, next to J1 / C2) has 7.6 mm free across, the pattern needs 16.5 x 11.2. Sites
(a fine search of every clean spot: no other courtyard, no drill or other-net top copper under the pads, 0.5 mm
inside the board edge; the one nearest the +12V feed J1 that keeps >= 1.25 mm to the next courtyard):
  A (-19.75, 5.25) rot 270: lead pad 16.1 mm from J1's centre, tab towards the board centre. +12V reaches it on the
    bottom-layer +12V pour (the feed plane of board A), GND on the In1 plane and the top GND pour.
  B (36.25, -12.25) rot 180: lead towards J1 (66 mm from its centre), tab edge 0.16 mm clear of R57's label, 0.5 mm
    to the next courtyard. +12V on the In2 +12V plane (feed-in2, whole board) and the bottom pour; GND on In1 and
    the top pour.
Clamp copper (both boards):
  * +12V: a top-layer +12V pour (priority 11, solid pad connection) over the lead pad and the strip under the body
    between the pads, stitched to the +12V planes below with 0.8 / 0.4 mm vias (the board's +12V via) on a 1.2 mm
    grid; no via in a pad (no solder wicking, no filled-via process).
  * GND: a top-layer GND pour (priority 10, solid connection: the board's main GND pour uses thermal spokes) over the
    tab and a 2 mm ring, stitched to In1 GND with the same vias in the ring.
  Vias are placed only where they keep the pour clearance (0.254 mm) from every other-net track, pad, via and pour
  cut-out on every layer, >= 0.6 mm drill-to-drill, outside other courtyards and rule areas, >= 1 mm from the edge.
  Current: load dump B (Ri 0.5 Ohm) puts about 10 A through D2 for 400 ms, ISO 7637-2 pulse 2a about 38 A for 50 us
  (tools/verify_spice.py). One 0.4 mm via (20 um wall, 0.025 mm2 = 50 cmil) fuses at about 11 A for 0.4 s
  (Onderdonk, 85 C start); >= 8 vias per net keep each under 1.3 A (> 8 x margin).
The old D2 tracks (+12V J1 -> D2 pad 1 stub, GND D2 pad 2 -> stitching-via stub) go; the stitching via stays.
Idempotent: zones named d2-12v / d2-gnd and the via group d2-clamp are removed and redone; a D2 that already has the
new footprint is moved / re-checked in place.
"""
import math
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, "..", "hardware", "board-a", "libraries", "dingoPDM.pretty"))
NAME = "D_DO-218AB_Vishay_SM8S"
FPID = "dingoPDM:" + NAME
MODEL = "${KIPRJMOD}/Models/" + NAME + ".step"
NS = uuid.UUID("2c5f4d0e-8a51-4b8e-b0a4-d2d2d2d20218")
TAB = (-2.75, 0.0, 9.80, 10.70)        # pad 2: centre x, y, width, height (local, mm)
LEAD = (6.575, 0.0, 2.15, 2.60)        # pad 1
BODY = (-7.75, -5.25, 5.75, 5.25)      # plastic body (max), lead to x 7.75 (16.0 overall, max)
CRTYD = (-8.25, -5.6, 8.25, 5.6)
SITES = {"A": (-19.75, 5.25, 270.0), "B": (36.25, -12.25, 180.0)}
OLD = (-33.655, 30.586)                # D2 before the move (both boards)
Z12, ZGND, GROUP = "d2-12v", "d2-gnd", "d2-clamp"
VIA_D, VIA_DRILL, PITCH, CLR = 0.8, 0.4, 1.2, 0.254
# local regions (footprint frame) for the clamp copper and its vias
R12 = (2.75, -4.9, 8.4, 4.9)           # +12V pour: from 0.6 mm past the tab to 0.75 mm past the lead pad (further
                                       # out it cut board A's U6 GND pad off the top GND pour)
RGND = (-9.75, -7.4, 2.15, 7.4)        # GND pour: the tab + a 2.05 mm ring (3 sides)
MIN_VIAS = 8


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(map(str, parts))))


# ------------------------------------------------------------------ footprint library
def _txt(kind, name, val, x, y, layer, hide, key, size=1.0, thick=0.15):
    head = f'\t(property "{name}" "{val}"' if kind == "property" else f'\t(fp_text user "{val}"'
    return (f'{head}\n\t\t(at {x:g} {y:g} 0)\n\t\t(unlocked yes)\n\t\t(layer "{layer}")\n'
            + ("\t\t(hide yes)\n" if hide else "")
            + f'\t\t(uuid "{uid(key)}")\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {size:g} {size:g})\n'
            f'\t\t\t\t(thickness {thick:g})\n\t\t\t)\n\t\t)\n\t)\n')


def _line(x0, y0, x1, y1, layer, w, key):
    return (f'\t(fp_line\n\t\t(start {x0:g} {y0:g})\n\t\t(end {x1:g} {y1:g})\n\t\t(stroke\n\t\t\t(width {w:g})\n'
            f'\t\t\t(type solid)\n\t\t)\n\t\t(layer "{layer}")\n\t\t(uuid "{uid(key)}")\n\t)\n')


def _rect(x0, y0, x1, y1, layer, w, key):
    return (f'\t(fp_rect\n\t\t(start {x0:g} {y0:g})\n\t\t(end {x1:g} {y1:g})\n\t\t(stroke\n\t\t\t(width {w:g})\n'
            f'\t\t\t(type solid)\n\t\t)\n\t\t(fill no)\n\t\t(layer "{layer}")\n\t\t(uuid "{uid(key)}")\n\t)\n')


def _pad(num, x, y, w, h, layers, key):
    return (f'\t(pad "{num}" smd rect\n\t\t(at {x:g} {y:g})\n\t\t(size {w:g} {h:g})\n\t\t(layers {layers})\n'
            f'\t\t(uuid "{uid(key)}")\n\t)\n')


def footprint_text():
    tx, ty, tw, th = TAB
    lx, ly, lw, lh = LEAD
    bx0, by0, bx1, by1 = BODY
    out = [f'(footprint "{NAME}"\n\t(version 20241229)\n\t(generator "pcbnew")\n\t(generator_version "9.0")\n\t(layer "F.Cu")\n',
           '\t(descr "DO-218AB / DO-218AC (SMPC-like) TVS, Vishay SM8S land pattern, doc 98229 page 5 (IPC-7351): '
           'heat-sink pad 9.80 x 10.70, lead pad 2.15 x 2.60, 15.30 overall. Also Bourns SM8S-Q, Panjit SM8H-AU.")\n',
           '\t(tags "DO-218AB DO-218AC TVS load dump SM8S")\n',
           _txt("property", "Reference", "REF**", 4.1, 0, "F.SilkS", False, "ref", 1.016, 0.1524),
           _txt("property", "Value", "SM8S24CA", 0, 6.6, "F.Fab", False, "val"),
           _txt("property", "Datasheet", "https://www.vishay.com/docs/98229/sm8s10cathrusm8s85ca.pdf", 0, 0, "F.Fab", True, "ds"),
           _txt("property", "Description", "", 0, 0, "F.Fab", True, "desc"),
           '\t(attr smd)\n']
    # silkscreen: body outline outside the pads (0.2 mm clear of copper)
    # (the two long sides only, stopping 1.35 mm short of the tab end: board B's R57 label sits just past it)
    ys = 5.55
    out += [_line(bx0 + 1.35, -ys, bx1, -ys, "F.SilkS", 0.12, "s1"), _line(bx0 + 1.35, ys, bx1, ys, "F.SilkS", 0.12, "s2")]
    out += [_rect(bx0, by0, bx1, by1, "F.Fab", 0.1, "fab"), _rect(bx1, -1.5, 7.75, 1.5, "F.Fab", 0.1, "fablead"),
            _rect(*CRTYD, "F.CrtYd", 0.05, "crt")]
    out.append(_pad("1", lx, ly, lw, lh, '"F.Cu" "F.Paste" "F.Mask"', "p1"))
    out.append(_pad("2", tx, ty, tw, th, '"F.Cu" "F.Mask"', "p2"))
    # paste windows on the tab: 2 x 2, 0.2 mm in from the edge, 0.8 mm apart
    pw, ph = (tw - 0.4 - 0.8) / 2, (th - 0.4 - 0.8) / 2
    for i, sx in enumerate((-1, 1)):
        for j, sy in enumerate((-1, 1)):
            out.append(_pad("", round(tx + sx * (pw / 2 + 0.4), 3), round(ty + sy * (ph / 2 + 0.4), 3),
                            round(pw, 3), round(ph, 3), '"F.Paste"', f"paste{i}{j}"))
    out.append(f'\t(embedded_fonts no)\n\t(model "{MODEL}"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t\t(scale\n'
               '\t\t\t(xyz 1 1 1)\n\t\t)\n\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)\n)\n')
    return "".join(out)


def write_lib():
    p = os.path.join(LIB, NAME + ".kicad_mod")
    with open(p, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(footprint_text())
    print("wrote", p)


# ------------------------------------------------------------------ schematic
def block_end(t, s):
    depth, in_str, i = 0, False, s
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


def sch(path):
    raw = open(path, "rb").read().decode("utf-8")
    hits = [m.start() for m in re.finditer(r'\(reference "D2"\)', raw)]
    if len(hits) != 1:
        raise SystemExit(f"{path}: {len(hits)} D2 instances")
    s = raw.rindex("\n\t(symbol", 0, hits[0]) + 1
    e = block_end(raw, s)
    blk = raw[s:e]
    old = re.search(r'\(property "Footprint" "([^"]*)"', blk).group(1)
    if old == FPID:
        print(f"D2 symbol: footprint already {FPID}")
        return
    new = blk.replace(f'(property "Footprint" "{old}"', f'(property "Footprint" "{FPID}"', 1)
    open(path, "wb").write((raw[:s] + new + raw[e:]).encode("utf-8"))
    print(f"D2 symbol: footprint {old} -> {FPID}")


# ------------------------------------------------------------------ PCB
def pcb(path, board):
    import pcbnew
    sys.path.insert(0, HERE)
    import pcb_rework
    mm, tomm = pcbnew.FromMM, pcbnew.ToMM
    X, Y, ROT = SITES[board]

    def kr(x, y):           # local -> board (KiCad orientation: positive = counter-clockwise on screen, y down)
        c, s = math.cos(math.radians(ROT)), math.sin(math.radians(ROT))
        return X + x * c + y * s, Y - x * s + y * c

    def V(x, y):
        return pcbnew.VECTOR2I(mm(x), mm(y))

    def lpoly(x0, y0, x1, y1):
        return [kr(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]

    b = pcbnew.LoadBoard(path)
    # ---- 1. drop an earlier run's clamp copper
    old_items = [z for z in b.Zones() if z.GetZoneName() in (Z12, ZGND)]
    old_items += [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetParentGroup() is not None
                  and t.GetParentGroup().GetName() == GROUP]
    old_items += [g for g in b.Groups() if g.GetName() == GROUP]
    d2 = b.FindFootprintByReference("D2")
    if d2 is None or d2.IsFlipped():
        raise SystemExit("D2: not on the board or on the bottom side")
    swapped = d2.GetFPID().GetUniStringLibId() == FPID
    if not swapped:
        # ---- 2. new footprint in the new spot, same symbol link, nets by pad number, all fields kept
        if abs(tomm(d2.GetPosition().x) - OLD[0]) > 0.01 or abs(tomm(d2.GetPosition().y) - OLD[1]) > 0.01:
            raise SystemExit(f"D2 not at its old spot {OLD}: {tomm(d2.GetPosition().x)}, {tomm(d2.GetPosition().y)}")
        fp = pcbnew.FootprintLoad(LIB, NAME)
        if fp is None:
            raise SystemExit(f"{NAME}: not in {LIB} (run 'd2_tvs.py lib' first)")
        fp.SetFPID(pcbnew.LIB_ID("dingoPDM", NAME))
        fp.SetReference("D2")
        fp.SetValue(d2.GetValue())
        fp.SetPath(d2.GetPath())
        fp.SetSheetname(d2.GetSheetname())
        fp.SetSheetfile(d2.GetSheetfile())
        olds = {p.GetNumber(): p for p in d2.Pads() if p.GetNumber()}
        news = {p.GetNumber(): p for p in fp.Pads() if p.GetNumber()}
        if sorted(olds) != sorted(news):
            raise SystemExit(f"D2: numbered pads differ ({sorted(olds)} vs {sorted(news)})")
        if olds["1"].GetNetname() != "+12V" or olds["2"].GetNetname() != "GND":
            raise SystemExit("D2: expected pad 1 +12V, pad 2 GND")
        for n, p in news.items():
            p.SetNet(olds[n].GetNet())
            p.SetPinFunction(olds[n].GetPinFunction())
            p.SetPinType(olds[n].GetPinType())
        for f in d2.GetFields():
            if f.GetName() in ("Reference", "Value", "Footprint"):
                continue
            g = next((x for x in fp.GetFields() if x.GetName() == f.GetName()), None)
            if g is not None:
                g.SetText(f.GetText())
                continue
            nf = pcbnew.PCB_FIELD(fp, fp.GetNextFieldId(), f.GetName())
            nf.SetText(f.GetText())
            nf.SetVisible(False)
            nf.SetLayer(pcbnew.F_Fab)
            nf.SetPosition(fp.GetPosition())
            nf.thisown = False
            fp.AddField(nf)
        ot, nt = d2.Reference(), fp.Reference()            # reference label as the board had it (shown / hidden)
        nt.SetVisible(ot.IsVisible())
        fp.SetDNP(d2.IsDNP())
        fp.SetExcludedFromBOM(d2.IsExcludedFromBOM())
        fp.SetExcludedFromPosFiles(d2.IsExcludedFromPosFiles())
        b.Add(fp)
        # tracks that only served the old D2: those ending in its pads, then any stub left dangling
        pads = list(d2.Pads())
        gone = set()
        tracks = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() in ("+12V", "GND")
                  and math.hypot(tomm(t.GetStart().x) - OLD[0], tomm(t.GetStart().y) - OLD[1]) < 12]
        for t in tracks:
            if any(p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd()) for p in pads):
                gone.add(t.m_Uuid.AsString())
        anchors = [p for f in b.GetFootprints() if f.GetReference() != "D2" for p in f.Pads()]
        vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
        for _ in range(6):
            for t in tracks:
                if t.m_Uuid.AsString() in gone:
                    continue
                for end in (t.GetStart(), t.GetEnd()):
                    held = any(p.GetNetname() == t.GetNetname() and p.HitTest(end) for p in anchors)
                    held |= any(v.GetNetname() == t.GetNetname() and v.HitTest(end) for v in vias)
                    held |= any(o.m_Uuid.AsString() not in gone and o is not t and o.m_Uuid.AsString() != t.m_Uuid.AsString()
                                and (o.GetStart() == end or o.GetEnd() == end) for o in tracks)
                    if not held:
                        gone.add(t.m_Uuid.AsString())
                        break
        rm = [t for t in tracks if t.m_Uuid.AsString() in gone]
        for t in rm:
            print(f"  removed track {t.GetNetname()} {b.GetLayerName(t.GetLayer())} ({tomm(t.GetStart().x):.3f}, "
                  f"{tomm(t.GetStart().y):.3f}) - ({tomm(t.GetEnd().x):.3f}, {tomm(t.GetEnd().y):.3f}) w {tomm(t.GetWidth()):.3f}")
        old_items += [d2] + rm
    if old_items:
        b = pcb_rework.remove_and_reload(b, old_items, path)
    d2 = b.FindFootprintByReference("D2")
    d2.SetPosition(V(X, Y))
    d2.SetOrientationDegrees(ROT)
    p1 = next(p for p in d2.Pads() if p.GetNumber() == "1")
    want = kr(LEAD[0], LEAD[1])
    if math.hypot(tomm(p1.GetPosition().x) - want[0], tomm(p1.GetPosition().y) - want[1]) > 0.01:
        raise SystemExit(f"orientation: pad 1 at {tomm(p1.GetPosition().x)}, {tomm(p1.GetPosition().y)}, expected {want}")
    # courtyard check: D2's courtyard must not touch another footprint's
    d2.BuildCourtyardCaches()
    cy = d2.GetCourtyard(pcbnew.F_CrtYd)
    for f in b.GetFootprints():
        if f.GetReference() == "D2":
            continue
        c = f.GetCourtyard(pcbnew.F_CrtYd)
        if c.OutlineCount():
            t = pcbnew.SHAPE_POLY_SET(cy)
            t.BooleanIntersection(c)
            if t.OutlineCount():
                raise SystemExit(f"D2 courtyard overlaps {f.GetReference()}")
    # labels of other parts that D2's pads would clip (board B: R68's reference sits 0.75 mm into the tab): the
    # label (text only; its footprint, pads and fields stay) steps the shortest way out to 0.1 mm clear of D2's
    # pads (0.15 mm of its silk), onto a spot clear of every pad and every other silk label
    def box(item, grow=0.0):
        bb = item.GetBoundingBox()
        return (tomm(bb.GetX()) - grow, tomm(bb.GetY()) - grow, tomm(bb.GetRight()) + grow, tomm(bb.GetBottom()) + grow)

    def hit(a, c):
        return a[0] < c[2] and c[0] < a[2] and a[1] < c[3] and c[1] < a[3]

    board_edge = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(board_edge)

    def edge_in(x, y):
        return board_edge.Contains(V(x, y))

    keep_out = [box(p, 0.1) for p in d2.Pads() if p.GetNumber()]
    keep_out += [box(g, 0.15) for g in d2.GraphicalItems() if g.GetLayer() == pcbnew.F_SilkS]
    all_pads = [box(p, 0.1) for f in b.GetFootprints() if f.GetReference() != "D2" for p in f.Pads()
                if p.IsOnLayer(pcbnew.F_Cu)]
    labels = [f.Reference() for f in b.GetFootprints() if f.GetReference() != "D2" and f.Reference().IsVisible()
              and f.Reference().GetLayer() == pcbnew.F_SilkS]
    for t in labels:
        tb = box(t)
        if not any(hit(tb, k) for k in keep_out):
            continue
        others = [box(o, 0.15) for o in labels if o.GetParentFootprint().GetReference() != t.GetParentFootprint().GetReference()]
        # the nearest clear spot (0.1 mm grid, within 4 mm of the label's own footprint; as it is or turned 90 deg)
        fpos = t.GetParentFootprint().GetPosition()
        fx, fy = tomm(fpos.x), tomm(fpos.y)
        cx, cy0 = (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2
        w, h = tb[2] - tb[0], tb[3] - tb[1]
        best = None
        for turn, (bw, bh) in ((0, (w, h)), (90, (h, w))):
            for i in range(-40, 41):
                for j in range(-40, 41):
                    nx, ny = fx + i * 0.1, fy + j * 0.1
                    nb = (nx - bw / 2, ny - bh / 2, nx + bw / 2, ny + bh / 2)
                    d = math.hypot(nx - cx, ny - cy0) + (0.5 if turn else 0)
                    if best is not None and d >= best[0]:
                        continue
                    if any(hit(nb, k) for k in keep_out + all_pads + others):
                        continue
                    if not all(edge_in(x, y) for x, y in ((nb[0], nb[1]), (nb[2], nb[3]))):
                        continue
                    best = (d, nx - cx, ny - cy0, turn)
        if best is None:
            raise SystemExit(f"label of {t.GetParentFootprint().GetReference()} under D2: no clear spot")
        _, dx, dy, turn = best
        p = t.GetPosition()
        if turn:
            t.SetTextAngleDegrees((t.GetTextAngleDegrees() + 90) % 180)
        t.SetPosition(V(tomm(p.x) + dx, tomm(p.y) + dy))
        print(f"  label {t.GetParentFootprint().GetReference()} moved ({dx:+.2f}, {dy:+.2f}) mm"
              + (", turned 90 deg" if turn else "") + " off D2")
    # ---- 3. clamp pours on the top layer
    zgnd_like = next(z for z in b.Zones() if z.GetNetname() == "GND" and not z.GetIsRuleArea()
                     and z.GetLayerSet().Contains(pcbnew.F_Cu))

    # the clamp pours never reach into another net's pour outline (PF_OUT*, +3V3 ...): those keep every mm2
    others = [z.Outline() for z in b.Zones() if not z.GetIsRuleArea() and z.GetLayerSet().Contains(pcbnew.F_Cu)
              and z.GetNetname() not in ("GND", "+12V")]

    def add_zone(name, net, prio, poly):
        z = pcbnew.ZONE(b)
        z.SetZoneName(name)
        z.SetLayer(pcbnew.F_Cu)
        z.SetNet(b.FindNet(net))
        z.SetAssignedPriority(prio)
        z.SetLocalClearance(mm(CLR))
        z.SetMinThickness(zgnd_like.GetMinThickness())
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        ch = pcbnew.SHAPE_LINE_CHAIN()
        for x, y in poly:
            ch.Append(mm(x), mm(y))
        ch.SetClosed(True)
        s = pcbnew.SHAPE_POLY_SET()
        s.AddOutline(ch)
        for o in others:
            s.BooleanSubtract(o)
        if s.OutlineCount() == 0:
            raise SystemExit(f"{name}: nothing left after other-net pours")
        o = z.Outline()                                 # copy into the zone's own outline (SetOutline would hand a
        for i in range(s.OutlineCount()):               # python-owned pointer to C++: access violation on Fill)
            o.AddOutline(s.COutline(i))
            for j in range(s.HoleCount(i)):
                o.AddHole(s.CHole(i, j), i)
        b.Add(z)
        return z

    add_zone(Z12, "+12V", 11, lpoly(*R12))
    add_zone(ZGND, "GND", 10, lpoly(*RGND))
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    # ---- 4. stitching vias
    cu = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    drills, shapes = [], {L: [] for L in cu}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            drills.append((tomm(p.x), tomm(p.y), tomm(t.Cast().GetDrillValue()) / 2))
        for L in cu:
            if t.IsOnLayer(L):
                shapes[L].append((t.GetNetname(), t.GetEffectiveShape(L)))
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetDrillSize().x > 0:
                q = p.GetPosition()
                drills.append((tomm(q.x), tomm(q.y), tomm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2))
            for L in cu:
                if p.IsOnLayer(L) or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    shapes[L].append((p.GetNetname(), p.GetEffectiveShape(L)))
    fills = {}                                          # (layer, net) -> filled polys of every pour of that net
    for z in b.Zones():
        if z.GetIsRuleArea():
            continue
        for L in cu:
            if z.GetLayerSet().Contains(L):
                fills.setdefault((L, z.GetNetname()), []).append(z.GetFilledPolysList(L))
    yards = [f.GetCourtyard(s) for f in b.GetFootprints() if f.GetReference() != "D2"
             for s in (pcbnew.F_CrtYd, pcbnew.B_CrtYd) if f.GetCourtyard(s).OutlineCount()]
    rules = [z for z in b.Zones() if z.GetIsRuleArea()]
    edge = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(edge)
    d2pads = [p.GetEffectiveShape(pcbnew.F_Cu) for p in d2.Pads() if p.GetNumber()]

    def inside_fill(L, net, x, y, r):
        """the whole via pad (centre and 4 rim points) sits on filled copper of `net` on layer L"""
        return all(any(f.Contains(V(x + dx, y + dy)) for f in fills.get((L, net), []))
                   for dx, dy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r)))

    group = pcbnew.PCB_GROUP(b)
    group.SetName(GROUP)
    b.Add(group)
    placed = {}
    for net, (x0, y0, x1, y1), planes in (("+12V", R12, [L for L in (pcbnew.In2_Cu, pcbnew.B_Cu)]),
                                           ("GND", RGND, [pcbnew.In1_Cu])):
        n = 0
        lx = x0 + 0.6
        while lx <= x1 - 0.6 + 1e-9:
            ly = y0 + 0.6
            while ly <= y1 - 0.6 + 1e-9:
                x, y = kr(lx, ly)
                ly += PITCH
                c = V(x, y)
                ring = pcbnew.SHAPE_CIRCLE(c, mm(VIA_D / 2))
                if not inside_fill(pcbnew.F_Cu, net, x, y, VIA_D / 2):      # on the clamp pour (top)
                    continue
                if not any(inside_fill(L, net, x, y, VIA_D / 2) for L in planes):   # and on a plane of its net
                    continue
                if any(s.Collide(ring, mm(0.05)) for s in d2pads):          # no via in a pad
                    continue
                if not edge.Contains(c) or min(math.hypot(x - tomm(edge.CVertex(k).x), y - tomm(edge.CVertex(k).y))
                                               for k in range(edge.TotalVertices())) < 1.0:
                    continue
                if any(math.hypot(x - dx, y - dy) < VIA_DRILL / 2 + dr + 0.6 for dx, dy, dr in drills):
                    continue
                if any(yd.Contains(c) for yd in yards) or any(z.Outline().Contains(c) for z in rules):
                    continue
                if any(nn != net and s.Collide(ring, mm(CLR)) for L in cu for nn, s in shapes[L]):
                    continue
                v = pcbnew.PCB_VIA(b)
                v.SetPosition(c)
                v.SetWidth(mm(VIA_D))
                v.SetDrill(mm(VIA_DRILL))
                v.SetNet(b.FindNet(net))
                b.Add(v)
                group.AddItem(v)
                drills.append((x, y, VIA_DRILL / 2))
                for L in cu:
                    shapes[L].append((net, v.GetEffectiveShape(L)))
                n += 1
            lx += PITCH
        placed[net] = n
    for net, n in placed.items():
        if n < MIN_VIAS:
            raise SystemExit(f"D2 clamp: only {n} {net} vias fit (need {MIN_VIAS})")
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(path)
    p1 = next(p for p in d2.Pads() if p.GetNumber() == "1")
    print(f"D2 ({board}): {FPID} at ({X}, {Y}) rot {ROT:g}, lead (+12V) pad at ({tomm(p1.GetPosition().x):.3f}, "
          f"{tomm(p1.GetPosition().y):.3f}); clamp vias +12V {placed['+12V']}, GND {placed['GND']}"
          + ("" if swapped else "; footprint swapped from the old spot"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "lib":
        write_lib()
    elif cmd == "sch":
        sch(sys.argv[2])
    elif cmd == "pcb":
        pcb(sys.argv[2], sys.argv[3].upper())
    else:
        raise SystemExit(__doc__)
