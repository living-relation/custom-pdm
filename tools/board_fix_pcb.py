"""Board-fix PCB helpers shared by board A and board B (KiCad 9 python). Import only; nothing runs on import.

read_netlist(path)            -> {ref: comp dict} from a KiCad s-expression netlist (.net)
sync_fields(b, comps)         -> footprints follow the schematic: value, DNP, Digi-Key_PN / LCSC / Manufacturer / MPN
add_part(b, comp, padnet, anchor, ...)
                              -> load a new part's footprint from the KiCad library, link it to its symbol, give its pads
                                 their nets and put it on the nearest free spot to `anchor` (exact shapes, not a grid)
Decisions: DECISIONS.md 2026-11-11 (C6c fields, C7b terminator, B4-b(b) BOOT1 pull-down).
"""
import math
import os
import re

import pcbnew

mm, tomm = pcbnew.FromMM, pcbnew.ToMM
KFP = os.path.join(os.environ["LOCALAPPDATA"], r"Programs\KiCad\9.0\share\kicad\footprints")
FIELDS = ("Digi-Key_PN", "LCSC", "Manufacturer", "MPN")
V = lambda x, y: pcbnew.VECTOR2I(mm(x), mm(y))


def read_netlist(path):
    text = open(path, encoding="utf-8").read()
    text = text.split("(libparts")[0]                       # library defaults are not part of any component
    comps = {}
    for blk in re.split(r'\(comp\s+\(ref\s+"', text)[1:]:
        ref = blk[:blk.index('"')]
        c = {"ref": ref,
             "value": re.search(r'\(value\s+"([^"]*)"\)', blk).group(1),
             "footprint": (re.search(r'\(footprint\s+"([^"]*)"\)', blk) or [None, ""])[1],
             "fields": dict(re.findall(r'\(field\s+\(name\s+"([^"]+)"\)\s+"([^"]*)"\)', blk)),
             "props": dict(re.findall(r'\(property\s+\(name\s+"([^"]+)"\)\s+\(value\s+"([^"]*)"\)\s*\)', blk)),
             "dnp": re.search(r'\(property\s+\(name\s+"dnp"\)', blk) is not None}
        m = re.search(r'\(sheetpath\s+\(names\s+"([^"]*)"\)\s+\(tstamps\s+"([^"]*)"\)\s*\)\s*\(tstamps\s+"([^"]*)"\)', blk)
        if m:
            c["sheetnames"], c["sheet_ts"], c["ts"] = m.groups()
        comps[ref] = c
    return comps


def _field(fp, name):
    return next((f for f in fp.GetFields() if f.GetName() == name), None)


def sync_fields(b, comps):
    """Returns a list of the changes made."""
    log = []
    for fp in b.GetFootprints():
        c = comps.get(fp.GetReference())
        if not c:
            continue
        if fp.GetValue() != c["value"]:
            log.append(f"{fp.GetReference()} value {fp.GetValue()} -> {c['value']}")
            fp.SetValue(c["value"])
        if fp.IsDNP() != c["dnp"]:
            fp.SetDNP(c["dnp"])
            log.append(f"{fp.GetReference()} DNP -> {c['dnp']}")
        for name in FIELDS:
            want = c["fields"].get(name)
            if not want:
                continue
            f = _field(fp, name)
            if f is None:
                f = pcbnew.PCB_FIELD(fp, fp.GetNextFieldId(), name)
                f.SetText(want)                              # text first: AddField keeps a copy, not this object
                f.SetVisible(False)
                f.SetLayer(pcbnew.F_Fab)
                f.SetPosition(fp.GetPosition())
                f.thisown = False
                fp.AddField(f)
                log.append(f"{fp.GetReference()} {name} added {want!r}")
                f = _field(fp, name)
            if f.GetText() != want:
                log.append(f"{fp.GetReference()} {name} {f.GetText()!r} -> {want!r}")
                f.SetText(want)
    return log


def _copper_items(b, skip):
    out = [t for t in b.GetTracks()]
    out += [p for f in b.GetFootprints() if f.GetReference() not in skip for p in f.Pads()]
    return out


def add_part(b, comp, padnet, anchor, max_r=12.0, rots=(0, 90, 180, 270), clearance=0.25, keep_out=()):
    """Place a new part from the netlist at the free spot nearest to `anchor` (x, y mm) on the top side.
    keep_out: extra (x0, y0, x1, y1) boxes the part must stay out of (e.g. room for a fan-out). Returns the footprint."""
    lib, name = comp["footprint"].split(":", 1)
    fp = pcbnew.FootprintLoad(os.path.join(KFP, lib + ".pretty"), name)
    if fp is None:
        raise SystemExit(f"footprint {comp['footprint']} not found")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(comp["ref"])
    fp.SetValue(comp["value"])
    fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(1.02), mm(1.02)))     # board rule: silk text >= 1.016 mm high
    fp.Reference().SetTextThickness(mm(0.16))
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
            ni = b.FindNet(n)
            if ni is None:
                ni = pcbnew.NETINFO_ITEM(b, n)
                ni.thisown = False
                b.Add(ni)
            p.SetNet(ni)
        else:
            p.SetNetCode(0)
    b.Add(fp)
    sync_fields(b, {comp["ref"]: comp})

    edge = b.GetBoardEdgesBoundingBox()
    edge.Inflate(-mm(0.6))
    others = [f for f in b.GetFootprints() if f.GetReference() != comp["ref"] and not f.IsFlipped()]
    yards = [f.GetCourtyard(pcbnew.F_CrtYd) for f in others if f.GetCourtyard(pcbnew.F_CrtYd).OutlineCount()]
    copper = [it for it in _copper_items(b, {comp["ref"]}) if it.IsOnLayer(pcbnew.F_Cu)]
    rules = [z for z in b.Zones() if z.GetIsRuleArea() and z.IsOnLayer(pcbnew.F_Cu)]
    holes = [(t.GetPosition(), t.GetDrillValue() / 2) for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    holes += [(p.GetPosition(), max(p.GetDrillSize().x, p.GetDrillSize().y) / 2) for f in others for p in f.Pads() if p.HasHole()]
    cl = mm(clearance)

    def ok():
        fp.BuildCourtyardCaches()
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = fp.GetBoundingBox(False, False)
        if not edge.Contains(bb):
            return False
        if any(x0 <= tomm(bb.GetRight()) and tomm(bb.GetLeft()) <= x1 and y0 <= tomm(bb.GetBottom()) and tomm(bb.GetTop()) <= y1
               for x0, y0, x1, y1 in keep_out):
            return False
        cbox = cy.BBox()
        if any(y.BBox().Intersects(cbox) for y in yards):      # courtyards compared as boxes (conservative)
            return False
        for p in fp.Pads():
            s = p.GetEffectiveShape(pcbnew.F_Cu)
            pb = p.GetBoundingBox()
            pb.Inflate(cl)
            for it in copper:
                if it.GetBoundingBox().Intersects(pb) and it.GetEffectiveShape(pcbnew.F_Cu).Collide(s, cl):
                    return False
            for z in rules:
                if z.Outline().Collide(s, 0):
                    return False
            for c, r in holes:
                if math.hypot(c.x - p.GetPosition().x, c.y - p.GetPosition().y) < r + mm(0.25) + max(p.GetSize().x, p.GetSize().y) / 2:
                    return False
        return True

    ax, ay = anchor
    for k in range(0, int(max_r / 0.25) + 1):
        r = k * 0.25
        steps = [0] if r == 0 else range(0, 360, max(5, int(360 / (2 * math.pi * r / 0.25))))
        for a in steps:
            x, y = ax + r * math.cos(math.radians(a)), ay + r * math.sin(math.radians(a))
            x, y = round(x / 0.05) * 0.05, round(y / 0.05) * 0.05
            for rot in rots:
                fp.SetPosition(V(x, y))
                fp.SetOrientationDegrees(rot)
                if ok():
                    print(f"{comp['ref']} placed at ({x:.2f}, {y:.2f}) rot {rot} ({r:.2f} mm from the anchor)")
                    return fp
    raise SystemExit(f"{comp['ref']}: no free spot within {max_r} mm of {anchor}")


def pad(b, ref, num):
    return next(p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == num)


def xy(p):
    return tomm(p.GetPosition().x), tomm(p.GetPosition().y)


def mid(b, ref, a, c):
    (x1, y1), (x2, y2) = xy(pad(b, ref, a)), xy(pad(b, ref, c))
    return (x1 + x2) / 2, (y1 + y2) / 2
