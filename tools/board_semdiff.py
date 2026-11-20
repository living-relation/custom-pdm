"""Semantic diff of two .kicad_pcb files (KiCad 9 python): what really changed after a rebuild.

usage: python tools/board_semdiff.py <old.kicad_pcb> <new.kicad_pcb>

A board rebuild is not byte-identical (uuids, item order), so a text diff cannot say whether a part moved. This
compares by content: footprints (reference -> footprint, position, rotation, side, pads with position / size / net,
fields), tracks and vias (layer, ends, width, drill, net), zone outlines (net, layers, priority, corners) and the
filled copper area per zone and layer. Prints every difference; exit 0 always (the caller judges).
"""
import sys

import pcbnew

T = pcbnew.ToMM


def rd(path):
    b = pcbnew.LoadBoard(path)
    fps = {}
    for f in b.GetFootprints():
        pads = sorted((p.GetNumber(), round(T(p.GetPosition().x), 3), round(T(p.GetPosition().y), 3),
                       round(T(p.GetSize().x), 3), round(T(p.GetSize().y), 3), p.GetNetname()) for p in f.Pads())
        fields = {fl.GetName(): fl.GetText() for fl in f.GetFields()}
        fps[f.GetReference()] = dict(fp=str(f.GetFPID().GetLibItemName()), pos=(round(T(f.GetPosition().x), 3),
                                     round(T(f.GetPosition().y), 3)), rot=f.GetOrientationDegrees(),
                                     side=f.GetLayerName(), pads=pads, fields=fields)
    tr = set()
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            v = t.Cast()
            tr.add(("via", round(T(v.GetPosition().x), 3), round(T(v.GetPosition().y), 3),
                    round(T(v.GetWidth(pcbnew.F_Cu)), 3), round(T(v.GetDrillValue()), 3), t.GetNetname()))
        else:
            tr.add((t.GetClass(), t.GetLayerName(), round(T(t.GetStart().x), 3), round(T(t.GetStart().y), 3),
                    round(T(t.GetEnd().x), 3), round(T(t.GetEnd().y), 3), round(T(t.GetWidth()), 3), t.GetNetname()))
    zs = {}
    for z in b.Zones():
        o = z.Outline()
        pts = tuple((round(T(o.CVertex(i).x), 2), round(T(o.CVertex(i).y), 2)) for i in range(o.TotalVertices()))
        key = (z.GetNetname(), tuple(b.GetLayerName(l) for l in z.GetLayerSet().Seq()), z.GetAssignedPriority(),
               z.GetIsRuleArea(), z.GetZoneName())
        area = {b.GetLayerName(l): round(z.GetFilledPolysList(l).Area() / 1e12, 1)
                for l in z.GetLayerSet().Seq() if pcbnew.IsCopperLayer(l) and not z.GetIsRuleArea()}
        zs.setdefault(key, []).append((pts, area))
    return fps, tr, zs


def main(a, b):
    fa, ta, za = rd(a)
    fb, tb, zb = rd(b)
    n = 0
    for r in sorted(set(fa) | set(fb)):
        if r not in fa or r not in fb:
            print("footprint", r, "only in", "new" if r in fb else "old")
            n += 1
            continue
        x, y = fa[r], fb[r]
        for k in ("fp", "pos", "rot", "side", "pads"):
            if x[k] != y[k]:
                print(f"footprint {r} {k}: {x[k] if k != 'pads' else '...'} -> {y[k] if k != 'pads' else '...'}")
                n += 1
        for k in sorted(set(x["fields"]) | set(y["fields"])):
            if x["fields"].get(k) != y["fields"].get(k):
                print(f"field {r}.{k}: {x['fields'].get(k)!r} -> {y['fields'].get(k)!r}")
    add, rem = tb - ta, ta - tb
    print(f"tracks / vias: {len(add)} added, {len(rem)} removed")
    for s, lab in ((add, "+"), (rem, "-")):
        kinds = {}
        for t in s:
            kinds.setdefault((t[0], t[-1]), 0)
            kinds[(t[0], t[-1])] += 1
        for k, c in sorted(kinds.items()):
            print(f"  {lab} {c} {k[0]} {k[1]}")
    for k in sorted(set(za) | set(zb), key=str):
        if za.get(k) != zb.get(k):
            print("zone", k, "\n   old", za.get(k), "\n   new", zb.get(k))
    print(f"footprint geometry differences: {n}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
