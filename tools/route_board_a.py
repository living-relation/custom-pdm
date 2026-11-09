"""Small grid A* router for a few signal nets on board A (KiCad 10 pcbnew Python + numpy).

usage: python route_board_a.py <board.kicad_pcb>   (or import it: setup(board, win), run_jobs(jobs))

Routes (pad/point -> pad/point) on F.Cu, In2.Cu and B.Cu with through vias. In1.Cu (GND plane) is left alone.
Obstacles: other-net tracks, vias, pads and holes, board edge. Zones are not obstacles: they refill around
new copper. Grid 0.1 mm; track 0.25 mm; clearance 0.2 mm + 0.05 mm grid margin; via 0.8/0.4 mm.
"""
import sys, heapq, math
import numpy as np
import pcbnew

mm, tomm = pcbnew.FromMM, pcbnew.ToMM
G = 0.1
TW, CL, MARGIN = 0.2, 0.2, 0.03
VIA_D, VIA_DRILL = 0.8, 0.4
VIA_COST = 30.0
WIN = (-24.0, -2.0, 24.0, 30.0)      # x0, y0, x1, y1 (mm) routing window

LAYERS = ["F.Cu", "In2.Cu", "B.Cu"]
LAYER_COST = {ly: 1.0 for ly in LAYERS}           # per-step cost multiplier per layer


def setup(board, win=WIN, layer_cost=None, layers=None):
    """Bind the router to a loaded board and a routing window (x0, y0, x1, y1) in mm.
    layers: routing layers (default F.Cu, In2.Cu, B.Cu; a 2-layer board passes ["F.Cu", "B.Cu"])."""
    global b, L, fps, TRACKS, x0, y0, x1, y1, NX, NY, XS, YS, GX, GY, LAYER_COST, LAYERS
    b = board
    if layers:
        LAYERS[:] = list(layers)
    L = {ly: b.GetLayerID(ly) for ly in LAYERS}
    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}
    TRACKS = list(b.GetTracks())
    LAYER_COST = dict(layer_cost or {ly: 1.0 for ly in LAYERS})
    x0, y0, x1, y1 = win
    NX, NY = int(round((x1 - x0) / G)) + 1, int(round((y1 - y0) / G)) + 1
    XS = x0 + np.arange(NX) * G
    YS = y0 + np.arange(NY) * G
    GX, GY = np.meshgrid(XS, YS, indexing="xy")      # shape (NY, NX)


def refresh():
    """New copper becomes an obstacle for the next net."""
    global TRACKS, fps
    TRACKS = list(b.GetTracks())
    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}


def seg_dist(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return np.hypot(px - ax, py - ay)
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def paint(dist, shape_fn, bbox, pad):
    """dist[layer] = min(dist, distance-to-shape) inside bbox grown by pad."""
    bx0, by0, bx1, by1 = bbox
    i0 = max(0, int((bx0 - pad - x0) / G)); i1 = min(NX, int((bx1 + pad - x0) / G) + 2)
    j0 = max(0, int((by0 - pad - y0) / G)); j1 = min(NY, int((by1 + pad - y0) / G) + 2)
    if i0 >= i1 or j0 >= j1:
        return
    sub = shape_fn(GX[j0:j1, i0:i1], GY[j0:j1, i0:i1])
    np.minimum(dist[j0:j1, i0:i1], sub, out=dist[j0:j1, i0:i1])


def build_dist(net):
    """distance from each cell centre to nearest foreign copper, per layer (and 'hole' for drills)."""
    D = {ly: np.full((NY, NX), 99.0) for ly in LAYERS + ["In1.Cu"]}   # In1: obstacles for vias only
    H = np.full((NY, NX), 99.0)
    R = 3.0
    for t in TRACKS:
        if t.GetNetname() == net:
            continue
        if t.GetClass() == "PCB_VIA":
            cx, cy = tomm(t.GetPosition().x), tomm(t.GetPosition().y)
            r = tomm(t.GetWidth(pcbnew.F_Cu)) / 2
            for ly in D:
                paint(D[ly], lambda X, Y: np.hypot(X - cx, Y - cy) - r, (cx, cy, cx, cy), r + R)
            dr = tomm(t.GetDrillValue()) / 2
            paint(H, lambda X, Y: np.hypot(X - cx, Y - cy) - dr, (cx, cy, cx, cy), dr + R)
        else:
            ly = t.GetLayerName()
            if ly not in D:
                continue
            ax, ay = tomm(t.GetStart().x), tomm(t.GetStart().y)
            bx, by = tomm(t.GetEnd().x), tomm(t.GetEnd().y)
            hw = tomm(t.GetWidth()) / 2
            paint(D[ly], lambda X, Y: seg_dist(ax, ay, bx, by, X, Y) - hw,
                  (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)), hw + R)
    for fp in fps.values():
        for pad in fp.Pads():
            if pad.GetNetname() == net and net:
                continue
            bb = pad.GetBoundingBox()
            bx0, by0, bx1, by1 = tomm(bb.GetLeft()), tomm(bb.GetTop()), tomm(bb.GetRight()), tomm(bb.GetBottom())
            def rect(X, Y, bx0=bx0, by0=by0, bx1=bx1, by1=by1):
                dx = np.maximum(np.maximum(bx0 - X, X - bx1), 0)
                dy = np.maximum(np.maximum(by0 - Y, Y - by1), 0)
                return np.hypot(dx, dy)
            for ly in D:
                if pad.IsOnLayer(L[ly] if ly in L else b.GetLayerID(ly)):
                    paint(D[ly], rect, (bx0, by0, bx1, by1), R)
            if pad.HasHole():
                c = pad.GetPosition()
                cx, cy = tomm(c.x), tomm(c.y)
                dr = tomm(max(pad.GetDrillSize().x, pad.GetDrillSize().y)) / 2
                paint(H, lambda X, Y: np.hypot(X - cx, Y - cy) - dr, (cx, cy, cx, cy), dr + R)
    # board edge: keep 0.5 mm away
    for d in b.GetDrawings():
        if d.GetLayerName() == "Edge.Cuts" and d.GetClass() == "PCB_SHAPE":
            # approximate any edge shape by its polygon outline (rects are not start-end diagonals!)
            segs = []
            try:
                poly = pcbnew.SHAPE_POLY_SET()
                d.TransformShapeToPolygon(poly, d.GetLayer(), 0, mm(0.01), pcbnew.ERROR_INSIDE)
                for oi in range(poly.OutlineCount()):
                    ol = poly.Outline(oi)
                    n = ol.PointCount()
                    for pi in range(n):
                        p, q = ol.CPoint(pi), ol.CPoint((pi + 1) % n)
                        segs.append((tomm(p.x), tomm(p.y), tomm(q.x), tomm(q.y)))
            except Exception as e:
                print("edge shape skipped:", e)
            for ax, ay, bx, by in segs:
                for ly in LAYERS:
                    paint(D[ly], lambda X, Y, ax=ax, ay=ay, bx=bx, by=by: seg_dist(ax, ay, bx, by, X, Y) - 0.3,
                          (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)), 1.0)
    return D, H


def cell(x, y):
    i, j = int(round((x - x0) / G)), int(round((y - y0) / G))
    if not (0 <= i < NX and 0 <= j < NY):
        raise ValueError(f"point ({x:.2f}, {y:.2f}) is outside the routing window {(x0, y0, x1, y1)}")
    return i, j


def route(net, start, goal):
    """start/goal: (x, y, layers) in mm. Returns list of (x, y, layer) points or None."""
    D, H = build_dist(net)
    free = {ly: D[ly] >= TW / 2 + CL + MARGIN for ly in LAYERS}
    via_ok = np.ones((NY, NX), bool)
    for ly in LAYERS + ["In1.Cu"]:
        via_ok &= D[ly] >= VIA_D / 2 + CL + MARGIN
    via_ok &= H >= VIA_D / 2 + 0.25 + MARGIN
    # also stay clear of In1 plane holes: fine (plane refills)
    sx, sy, sl = start
    gx, gy, gl = goal
    si, sj = cell(sx, sy)
    gi, gj = cell(gx, gy)
    # open a small escape region around endpoints (inside own pad the foreign-copper map is fine,
    # but neighbouring pads of the same part may block the exit): allow 0.35 mm radius
    for (ci, cj, lys) in ((si, sj, sl), (gi, gj, gl)):
        for ly in lys:
            r = 3
            sub = free[ly][max(0, cj - r):cj + r + 1, max(0, ci - r):ci + r + 1]
            dsub = D[ly][max(0, cj - r):cj + r + 1, max(0, ci - r):ci + r + 1]
            sub |= dsub >= TW / 2 + 0.05
    nbr = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
           (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    li = {ly: k for k, ly in enumerate(LAYERS)}
    def h(i, j):
        return math.hypot(i - gi, j - gj)
    openq = []
    best = {}
    prev = {}
    for ly in sl:
        s = (si, sj, li[ly])
        best[s] = 0.0
        heapq.heappush(openq, (h(si, sj), 0.0, s, None))
    goal_layers = {li[ly] for ly in gl}
    while openq:
        f, g, s, d = heapq.heappop(openq)
        if g > best.get(s, 1e18):
            continue
        i, j, k = s
        if i == gi and j == gj and k in goal_layers:
            path = [s]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            path.reverse()
            return [(x0 + i * G, y0 + j * G, LAYERS[k]) for i, j, k in path]
        ly = LAYERS[k]
        for di, dj, c in nbr:
            ni, nj = i + di, j + dj
            if not (0 <= ni < NX and 0 <= nj < NY) or not free[ly][nj, ni]:
                continue
            turn = 0.0 if d is None or d == (di, dj) else 0.3
            ns = (ni, nj, k)
            ng = g + c * LAYER_COST[ly] + turn
            if ng < best.get(ns, 1e18):
                best[ns] = ng
                prev[ns] = s
                heapq.heappush(openq, (ng + h(ni, nj), ng, ns, (di, dj)))
        if via_ok[j, i]:
            for k2 in range(len(LAYERS)):
                if k2 != k and free[LAYERS[k2]][j, i]:
                    ns = (i, j, k2)
                    ng = g + VIA_COST
                    if ng < best.get(ns, 1e18):
                        best[ns] = ng
                        prev[ns] = s
                        heapq.heappush(openq, (ng + h(i, j), ng, ns, None))
    if "--debug" in sys.argv:
        import zlib, struct
        img = np.zeros((NY, NX * 3 + 20, 3), np.uint8)
        for k, ly in enumerate(LAYERS):
            sl_ = img[:, k * (NX + 10):k * (NX + 10) + NX]
            sl_[free[ly]] = (230, 230, 230)
            sl_[~free[ly]] = (180, 40, 40)
            for (i, j, kk) in best:
                if kk == k:
                    sl_[j, i] = (60, 160, 60)
            sl_[max(0, sj - 3):sj + 4, max(0, si - 3):si + 4] = (0, 0, 255)
            sl_[max(0, gj - 3):gj + 4, max(0, gi - 3):gi + 4] = (255, 160, 0)
        raw = b"".join(b"\x00" + img[r].tobytes() for r in range(img.shape[0]))
        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", img.shape[1], img.shape[0], 8, 2, 0, 0, 0)) \
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
        open(f"route-debug-{net.replace('/', '_').replace('(', '').replace(')', '')}.png", "wb").write(png)
    print(f"  {net}: expanded {len(best)} states; start free "
          f"{[bool(free[ly][sj, si]) for ly in sl]} goal free {[bool(free[ly][gj, gi]) for ly in gl]}; "
          f"start D {[round(float(D[ly][sj, si]), 2) for ly in sl]} goal D {[round(float(D[ly][gj, gi]), 2) for ly in gl]}")
    return None


def emit(net, pts, start_xy, goal_xy):
    ni = b.FindNet(net)
    # simplify: keep points where direction or layer changes
    simp = [pts[0]]
    for a, c in zip(pts[1:], pts[2:] + [None]):
        p = simp[-1]
        if c is None:
            simp.append(a)
            break
        if a[2] != p[2] or c[2] != a[2]:
            simp.append(a)
            continue
        d1 = (round((a[0] - p[0]) / G), round((a[1] - p[1]) / G))
        d2 = (round((c[0] - a[0]) / G), round((c[1] - a[1]) / G))
        n1 = (np.sign(d1[0]), np.sign(d1[1])); n2 = (np.sign(d2[0]), np.sign(d2[1]))
        if n1 != n2:
            simp.append(a)
    # exact endpoints
    pts2 = [(start_xy[0], start_xy[1], simp[0][2])] + simp + [(goal_xy[0], goal_xy[1], simp[-1][2])]
    n_t = n_v = 0
    for p, q in zip(pts2, pts2[1:]):
        if p[2] != q[2]:
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(pcbnew.VECTOR2I(mm(p[0]), mm(p[1])))
            v.SetWidth(mm(VIA_D))
            v.SetDrill(mm(VIA_DRILL))
            v.SetNet(ni)
            b.Add(v)
            n_v += 1
            continue
        if abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6:
            continue
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(mm(p[0]), mm(p[1])))
        t.SetEnd(pcbnew.VECTOR2I(mm(q[0]), mm(q[1])))
        t.SetWidth(mm(TW))
        t.SetLayer(L[p[2]])
        t.SetNet(ni)
        b.Add(t)
        n_t += 1
    return n_t, n_v


def padpos(ref, num):
    for pad in fps[ref].Pads():
        if pad.GetNumber() == num:
            p = pad.GetPosition()
            return tomm(p.x), tomm(p.y)
    raise KeyError((ref, num))


def run_jobs(jobs):
    """jobs: [(net, start, goal)] with start/goal = (x, y, layers). Returns True if all routed."""
    ok = True
    for net, s, g in jobs:
        pts = route(net, s, g)
        if pts is None:
            print(f"FAILED {net}")
            ok = False
            continue
        nt, nv = emit(net, pts, s[:2], g[:2])
        refresh()
        layers = sorted({p[2] for p in pts})
        print(f"routed {net}: {nt} segments, {nv} vias, layers {layers}, length ~{len(pts) * G:.1f} mm")
    return ok


def main(pcb):
    setup(pcbnew.LoadBoard(pcb))
    jobs = [
        ("Net-(U8-IN1)", padpos("R19", "1") + (["F.Cu"],), padpos("U8", "6") + (["F.Cu"],)),
        ("Net-(U8-DSEL)", padpos("R20", "2") + (["F.Cu"],), padpos("U8", "5") + (["F.Cu"],)),
        ("INPUT1", padpos("J3", "12") + (LAYERS,), (6.67, 15.306, ["In2.Cu"])),
    ]
    if run_jobs(jobs):
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        b.Save(pcb)
        print("saved")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1])
