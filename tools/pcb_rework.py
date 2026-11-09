"""Rip-up and reconnect helpers for board A (KiCad 9 python), used with route_board_a's router.

ripup(b, nets, box)  - remove tracks/vias of `nets` that touch `box` (x0, y0, x1, y1 mm)
islands(b, net)      - the net's copper split into connected groups (pads, tracks, vias)
reconnect(R, b, net) - route between islands (closest anchor points, minimum spanning tree) until one group
Zone-only connections (planes) are not modelled: don't rip plane nets (GND, +3V3, +12V) with these helpers.
"""
import math
import pcbnew

mm, tomm = pcbnew.FromMM, pcbnew.ToMM
CU = {"F.Cu": pcbnew.F_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu}


def ripup(b, nets, box):
    """Tracks/vias of `nets` touching `box`. Returns them; nothing is removed yet (see remove_and_reload)."""
    x0, y0, x1, y1 = box
    rect = pcbnew.SHAPE_RECT(pcbnew.VECTOR2I(mm(x0), mm(y0)), mm(x1 - x0), mm(y1 - y0))
    doomed = []
    for t in b.GetTracks():
        if t.GetNetname() not in nets:
            continue
        ly = pcbnew.F_Cu if t.GetClass() == "PCB_VIA" else t.GetLayer()
        if t.GetEffectiveShape(ly).Collide(rect, 0):
            doomed.append(t)
    return doomed


def remove_and_reload(b, items, path):
    """KiCad 9 swig: after BOARD.Remove() the board's item lists stop iterating. Remove everything in one go,
    save, and hand back a freshly loaded board."""
    for t in items:
        b.Remove(t)
    b.Save(path)
    return pcbnew.LoadBoard(path)


def _items(b, net):
    out = [t for t in b.GetTracks() if t.GetNetname() == net]
    out += [p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
    return out


def _layers(it):
    return [ly for ly, lid in CU.items() if it.IsOnLayer(lid)]


def _anchors(it):
    """Points a new route may start/end at: (x, y, [layers])."""
    lys = [ly for ly in _layers(it) if ly != "In1.Cu"]
    if it.GetClass() == "PCB_TRACK":
        return [(tomm(p.x), tomm(p.y), lys) for p in (it.GetStart(), it.GetEnd())]
    p = it.GetPosition()
    return [(tomm(p.x), tomm(p.y), lys)]


def islands(b, net):
    items = _items(b, net)
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    lys = [_layers(it) for it in items]
    for i in range(n):
        for j in range(i + 1, n):
            common = set(lys[i]) & set(lys[j])
            if not common or find(i) == find(j):
                continue
            bi, bj = items[i].GetBoundingBox(), items[j].GetBoundingBox()
            if not bi.Intersects(bj):
                continue
            for ly in common:
                if items[i].GetEffectiveShape(CU[ly]).Collide(items[j].GetEffectiveShape(CU[ly]), 0):
                    parent[find(i)] = find(j)
                    break
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i])
    return list(groups.values())


def reconnect(R, b, net, max_rounds=8):
    """Join a net's islands with the router. Returns True when the net is one group."""
    for _ in range(max_rounds):
        groups = islands(b, net)
        if len(groups) <= 1:
            return True
        anchors = [[a for it in g for a in _anchors(it)] for g in groups]
        # closest pair between group 0 and any other group (grow from group 0 = Prim's MST)
        best = None
        for k in range(1, len(anchors)):
            for a in anchors[0]:
                for c in anchors[k]:
                    if not a[2] or not c[2]:
                        continue
                    d = math.hypot(a[0] - c[0], a[1] - c[1])
                    if best is None or d < best[0]:
                        best = (d, a, c)
        if best is None:
            return False
        _, a, c = best
        if not R.run_jobs([(net, a, c)]):
            return False
    return len(islands(b, net)) <= 1


def net_groups(b, net):
    """Connected groups of a net's copper INCLUDING zone fill islands (per layer).
    Returns a list of groups, biggest first; each group is a list of (kind, item) with kind in
    PCB_TRACK / PCB_VIA / PAD / ZONE (item is the pad/track/via, or (layer, SHAPE_POLY_SET) for a fill island)."""
    cu = [CU[k] for k in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")]
    items = []
    for x in b.GetTracks():
        if x.GetNetname() == net:
            items.append((x.GetClass(), x, [l for l in cu if x.IsOnLayer(l)], x.GetBoundingBox()))
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() == net:
                items.append(("PAD", p, [l for l in cu if p.IsOnLayer(l)], p.GetBoundingBox()))
    for z in b.Zones():
        if z.GetNetname() != net or z.GetIsRuleArea():
            continue
        for l in cu:
            if not z.IsOnLayer(l):
                continue
            polys = z.GetFilledPolysList(l)
            for i in range(polys.OutlineCount()):
                sp = pcbnew.SHAPE_POLY_SET()
                sp.AddOutline(polys.Outline(i))
                for h in range(polys.HoleCount(i)):
                    sp.AddHole(polys.Hole(i, h))
                items.append(("ZONE", (l, sp), [l], sp.BBox()))
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def shp(it, l):
        return it[1][1] if it[0] == "ZONE" else it[1].GetEffectiveShape(l)

    def overlap(a, c):
        return a.GetLeft() <= c.GetRight() and c.GetLeft() <= a.GetRight() and a.GetTop() <= c.GetBottom() and c.GetTop() <= a.GetBottom()
    for i in range(n):
        for j in range(i + 1, n):
            common = set(items[i][2]) & set(items[j][2])
            if not common or find(i) == find(j) or not overlap(items[i][3], items[j][3]):
                continue
            if items[i][0] == "ZONE" and items[j][0] == "ZONE":
                continue
            a, c = (items[j], items[i]) if items[i][0] == "ZONE" else (items[i], items[j])
            for l in common:
                if shp(c, l).Collide(shp(a, l), 0):
                    parent[find(i)] = find(j)
                    break
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append((items[i][0], items[i][1]))
    return sorted(groups.values(), key=len, reverse=True)
