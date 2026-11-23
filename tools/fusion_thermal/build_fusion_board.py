"""Build the Fusion "Thermal" study geometry for one exported board case (runs INSIDE Fusion, Fusion MCP script).

usage (Fusion MCP script tool):
    ns = {}; exec(open(r"<repo>/tools/fusion_thermal/build_fusion_board.py").read(), ns)
    print(ns["build"](r"<export json>", "<doc name>", ["custom-pdm", "electronics-2026-11-23b", "thermal"]))
Input: tools/fusion_thermal/export_board.py JSON (mm, KiCad board axes, y down). Fusion: cm, y up (y -> -y).

"Lite" model (a first, tiled model with one body per conductivity bin stalled Fusion's automatic contact search for
over 15 min on the 16-body input board, 2026-11-23, so every board is now a few simple bodies):
  z = 0 board bottom. Main boards: bottom sheet [0, ts], core [ts, ts + tc], top sheet [ts + tc, t] (ts 0.3 mm):
  * each sheet ONE conductivity = the board's mean in-plane copper conductance of its two layers / ts (+ FR-4);
  * core: FR-4 + all barrels outside the driver pads spread evenly; a via patch body under each driver's exposed pad
    with that pad's own barrels; a copper J1 block through the board (press-fit terminal);
  * heat: ONE internal-heat load (total W) on the multi-lump body "heat"; every lump's volume is P / q, so the uniform
    volumetric heat gives each lump its own P: driver lumps on the top sheet over the exposed pad (copper, they ARE
    the chips' board-side temperature), copper I2R + joints + 5 V module per 10 mm tile as 0.5 mm lumps on the top or
    bottom sheet surface (bottom = In2 / B.Cu heat, moved to the other side where a gap pad / chip is), J1 lump on
    the block;
  * gap pads (k 3, 0.86 mm) under the pedestal areas; the rest of the underside an "air" slab k = h_bot x 0.86 mm;
    over the top an "air" slab k = h_top x 1.5 mm; copper plates outside both; applied temperature t_sink on the
    bottom-plate bottom and the top-plate top (one load); the BATT bar stub's top face at t_bar (second load).
  Input board: one sheet (mean conductance of both layers + FR-4), part lumps on top, air slabs (h 9) both sides.
"""
import json
import math

import adsk.core
import adsk.fusion

MM = 0.1
MAXL = 30


def _box(tbm, x0, y0, z0, x1, y1, z1):
    c = adsk.core.Point3D.create((x0 + x1) / 2 * MM, -(y0 + y1) / 2 * MM, (z0 + z1) / 2 * MM)
    obb = adsk.core.OrientedBoundingBox3D.create(c, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(0, 1, 0),
                                                 abs(x1 - x0) * MM, abs(y1 - y0) * MM, abs(z1 - z0) * MM)
    return tbm.createBox(obb)


def _union(tbm, bodies):
    out = None
    for b in bodies:
        if out is None:
            out = b
        else:
            tbm.booleanOperation(out, b, adsk.fusion.BooleanTypes.UnionBooleanType)
    return out


def _cut(tbm, target, rects, z0, z1):
    for r in rects:
        tbm.booleanOperation(target, _box(tbm, r[0], r[1], z0, r[2], r[3], z1),
                             adsk.fusion.BooleanTypes.DifferenceBooleanType)
    return target


def _ov(r, s, gap=0.0):
    return r[0] < s[2] + gap and s[0] < r[2] + gap and r[1] < s[3] + gap and s[1] < r[3] + gap


def _merge(items):
    """[(rect, P)] -> the same with every group of overlapping rects replaced by its bounding rect and summed P."""
    items = [(list(r), P) for r, P in items]
    changed = True
    while changed:
        changed = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i][0], items[j][0]
                if _ov(a, b, 0.05):
                    items[i] = ([min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])],
                                items[i][1] + items[j][1])
                    del items[j]
                    changed = True
                    break
            if changed:
                break
    return items


def _rect(x, y, w, h):
    return [x - w / 2, y - h / 2, x + w / 2, y + h / 2]


class Builder:
    def __init__(self, des):
        self.des, self.root = des, des.rootComponent
        self.tbm = adsk.fusion.TemporaryBRepManager.get()
        self.lib = adsk.core.Application.get().materialLibraries.itemByName("Fusion Material Library")
        self.bodies = []

    def mat(self, k):
        name = f"fusion2-k{k:.5g}"
        m = self.des.materials.itemByName(name)
        if m is None:
            m = self.des.materials.addByCopy(self.lib.materials.itemByName("Copper"), name)
            for pid in ("structural_Thermal_conductivity", "thermal_Thermal_conductivity"):
                for sfx in ("", "_X", "_Y", "_Z"):
                    p = m.materialProperties.itemById(pid + sfx)
                    if p is not None:
                        p.value = float(k)
        return m

    def add(self, tb, name, k):
        # one component per body: Fusion's automatic contacts found no contact between bodies of one component here
        occ = self.root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        occ.component.name = name
        b = occ.component.bRepBodies.add(tb)
        b.name = name
        b.material = self.mat(k)
        self.bodies.append((name, round(k, 5)))
        return b


def _place_lumps(recs, q, th, inner, top_block, bot_block, gap=0.3):
    """recs [(x, y, P, side)] -> [(side, rect, P)]: square lumps th mm high, none overlapping a blocked rect or another
    lump; tries the tile centre then four offsets, its own side first, then the other side."""
    placed = {"top": [], "bot": []}
    out, moved = [], 0
    for x, y, P, side in sorted(recs, key=lambda r: -r[2]):
        s = math.sqrt(P / (q * th * 1e-3)) * 1e3
        offs = sorted(((dx * 1.5, dy * 1.5) for dx in range(-6, 7) for dy in range(-6, 7)),
                      key=lambda o: o[0] ** 2 + o[1] ** 2)          # nearest free spot within +-9 mm, own side first
        tries = [(sd, _rect(x + dx, y + dy, s, s)) for sd in (side, "bot" if side == "top" else "top")
                 for dx, dy in offs]
        for sd, r in tries:
            if r[0] < inner[0] or r[1] < inner[1] or r[2] > inner[2] or r[3] > inner[3]:
                continue
            blk = top_block if sd == "top" else bot_block
            if any(_ov(r, b, gap) for b in blk) or any(_ov(r, o, gap) for o in placed[sd]):
                continue
            placed[sd].append(r)
            out.append((sd, r, P))
            moved += sd != side
            break
        else:
            raise RuntimeError(f"no place for a {P:.3f} W lump at {x}, {y}")
    return out, moved


def _save(app, doc, doc_name, folder_path):
    proj = [p for p in app.data.dataProjects if p.name == folder_path[0]][0]
    f = proj.rootFolder
    for name in folder_path[1:]:
        f = f.dataFolders.itemByName(name) or f.dataFolders.add(name)
    doc.saveAs(doc_name, f, "fusion2 thermal cross-check model (tools/fusion_thermal/build_fusion_board.py)", "")


def build(path, doc_name, folder_path):
    app = adsk.core.Application.get()
    d = json.load(open(path))
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    des = adsk.fusion.Design.cast(app.activeProduct)
    des.designType = adsk.fusion.DesignTypes.DirectDesignType
    B = Builder(des)
    tbm = B.tbm
    x0, y0, x1, y1 = d["outline"]
    t = d["thickness"]
    rep = dict(doc=doc_name, board=d["board"], case=d["case"])
    ha = 1.5
    if d["board"] == "IN":
        th = 0.5
        groups = _merge([(p["box"], p["P"]) for p in d["parts"]])
        q = max(P / ((bx[2] - bx[0]) * (bx[3] - bx[1]) * 1e-6 * th * 1e-3) for bx, P in groups)
        lumps, vol = [], 0.0
        for bx, P in groups:
            hh = P / (q * (bx[2] - bx[0]) * (bx[3] - bx[1]) * 1e-6) * 1e3
            lumps.append((bx, hh))
            vol += (bx[2] - bx[0]) * (bx[3] - bx[1]) * hh
        B.add(_box(tbm, x0, y0, 0.0, x1, y1, t), "sheet", d["lite"]["k_one"])
        for i, (bx, hh) in enumerate(lumps):
            B.add(_box(tbm, bx[0], bx[1], t, bx[2], bx[3], t + hh), f"heat-{i + 1:03d}", 401.0)
        top = _box(tbm, x0, y0, t, x1, y1, t + ha)
        for bx, hh in lumps:
            tbm.booleanOperation(top, _box(tbm, bx[0], bx[1], t, bx[2], bx[3], t + hh),
                                 adsk.fusion.BooleanTypes.DifferenceBooleanType)
        B.add(top, "air-top", d["h"] * ha * 1e-3)
        B.add(_box(tbm, x0, y0, -ha, x1, y1, 0.0), "air-bot", d["h"] * ha * 1e-3)
        B.add(_box(tbm, x0, y0, t + ha, x1, y1, t + ha + 0.5), "plate-top", 401.0)
        B.add(_box(tbm, x0, y0, -ha - 0.5, x1, y1, -ha), "plate-bot", 401.0)
        heat_w = sum(p["P"] for p in d["parts"])
        rep.update(q=q, heat_w=heat_w, p_from_volume=q * vol * 1e-9, t_fix=d["t_air"], top_z=t)
    else:
        lite = d["lite"]
        ts, tc = d["sheet_t"], d["core_t"]
        th = 0.5
        tile = d["heat"]["tile"]
        recs = [(h[0], h[1], h[2], "top") for h in d["heat"]["top"]] + \
               [(h[0], h[1], h[2], "bot") for h in d["heat"]["bot"]]
        pmax = max([r[2] for r in recs] + [1e-9])
        q = pmax / ((0.7 * tile * 1e-3) ** 2 * th * 1e-3)
        for c in d["chips"]:
            if c["P"] > 0:
                q = max(q, c["P"] / (c["ep"][0] * c["ep"][1] * 1e-6 * 1.2e-3))
        pmin = q * (0.6e-3) ** 2 * th * 1e-3                 # smallest lump 0.6 mm square
        # at most MAXL lumps per side (each lump is a body + component for the contact search): the largest tiles
        # stay, every other tile's heat goes to the nearest kept tile of its side (heat total exact)
        keep = []
        for side in ("top", "bot"):
            rs = sorted([r for r in recs if r[3] == side], key=lambda r: -r[2])
            kk = [list(r) for r in rs[:MAXL] if r[2] >= pmin] or [list(r) for r in rs[:1]]
            for r in rs:
                if any(r[0] == k_[0] and r[1] == k_[1] for k_ in kk):
                    continue
                n = min(kk, key=lambda k_: (k_[0] - r[0]) ** 2 + (k_[1] - r[1]) ** 2)
                n[2] += r[2]
            keep += [tuple(k_) for k_ in kk]
        pmax = max(r[2] for r in keep)
        q = max(q, pmax / ((0.7 * tile * 1e-3) ** 2 * th * 1e-3))
        jb = d["j1"]["box"]
        jcut = [jb[0] - 1.0, jb[1] - 1.0, jb[2] + 1.0, jb[3] + 1.0]
        chips = []
        for c in d["chips"]:
            if c["P"] <= 0:
                continue
            w, h = c["ep"]
            hh = c["P"] / (q * w * h * 1e-6) * 1e3
            if hh < 0.1:
                fct = math.sqrt(hh / 0.1)
                w, h, hh = w * fct, h * fct, 0.1
            chips.append((c["ref"], _rect(c["xy"][0], c["xy"][1], w, h), hh))
        inner = [x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5]
        lumps, moved = _place_lumps(keep, q, th, inner, [r for _, r, _ in chips] + [jcut], d["peds"] + [jcut])
        vol = sum((r[2] - r[0]) * (r[3] - r[1]) * th for _, r, _ in lumps) + \
            sum((r[2] - r[0]) * (r[3] - r[1]) * hh for _, r, hh in chips)
        pj = d["j1"]["P"]
        jl = math.sqrt(pj / (q * th * 1e-3)) * 1e3 if pj > 0 else 0.0
        vol += jl * jl * th
        jtop = t + 3.0
        B.add(_cut(tbm, _box(tbm, x0, y0, 0.0, x1, y1, ts), [jb], -1, t + 1), "sheet-bot", lite["k_bot"])
        B.add(_cut(tbm, _box(tbm, x0, y0, ts + tc, x1, y1, t), [jb], -1, t + 1), "sheet-top", lite["k_top"])
        B.add(_cut(tbm, _box(tbm, x0, y0, ts, x1, y1, ts + tc), [p["rect"] for p in lite["patches"]] + [jb], -1, t + 1),
              "core", lite["k_core"])
        for p in lite["patches"]:
            r = p["rect"]
            B.add(_box(tbm, r[0], r[1], ts, r[2], r[3], ts + tc), f"via-{p['ref']}", p["k"])
        parts = [_box(tbm, r[0], r[1], t, r[2], r[3], t + hh) for _, r, hh in chips]
        parts += [_box(tbm, r[0], r[1], t, r[2], r[3], t + th) if sd == "top" else
                  _box(tbm, r[0], r[1], -th, r[2], r[3], 0.0) for sd, r, _ in lumps]
        jr = [jb[0] + 0.5, jb[1] + 0.5, jb[0] + 0.5 + jl, jb[1] + 0.5 + jl]
        if jl > 0:
            parts.append(_box(tbm, jr[0], jr[1], jtop, jr[2], jr[3], jtop + th))
        for i, p in enumerate(parts):
            B.add(p, f"heat-{i + 1:03d}", 401.0)
        B.add(_box(tbm, jb[0], jb[1], 0.0, jb[2], jb[3], jtop), "J1-block", 401.0)
        bl = 20.0
        bxa = [(jr[2] if jl > 0 else jb[0]) + 0.5, jb[1] + 0.5, jb[2] - 0.5, jb[3] - 0.5]
        a_bar = (bxa[2] - bxa[0]) * (bxa[3] - bxa[1]) * 1e-6
        k_bar = d["j1"]["g_bar"] * bl * 1e-3 / a_bar
        B.add(_box(tbm, bxa[0], bxa[1], jtop, bxa[2], bxa[3], jtop + bl), "bar", k_bar)
        pt = d["pad"]["t"]
        for i, p in enumerate(d["peds"]):
            B.add(_box(tbm, p[0], p[1], -pt, p[2], p[3], 0.0), f"gap-pad-{i + 1}", d["pad"]["k"])
        bot_lumps = [r for sd, r, _ in lumps if sd == "bot"]
        top_lumps = [r for sd, r, _ in lumps if sd == "top"]
        B.add(_cut(tbm, _box(tbm, x0, y0, -pt, x1, y1, 0.0), d["peds"] + bot_lumps, -pt - 1, 1.0), "air-bot",
              d["h_bot"] * pt * 1e-3)
        B.add(_box(tbm, x0, y0, -pt - 1.0, x1, y1, -pt), "plate-bot", 401.0)
        at = _cut(tbm, _box(tbm, x0, y0, t, x1, y1, t + ha), [r for _, r, _ in chips] + top_lumps, t - 1, t + ha - 0.2)
        at = _cut(tbm, at, [jcut], t - 1, t + ha + 1)
        B.add(at, "air-top", d["h_top"] * ha * 1e-3)
        B.add(_cut(tbm, _box(tbm, x0, y0, t + ha, x1, y1, t + ha + 0.5), [jcut], t, t + ha + 1), "plate-top", 401.0)
        heat_w = d["totals"]["p_chips"] + d["totals"]["p_dist"] + d["totals"]["p_j1"]
        rep.update(q=q, heat_w=heat_w, p_from_volume=q * vol * 1e-9, k_bar=k_bar, t_fix=d["t_sink"],
                   t_bar=d["j1"]["t_bar"], lumps=len(lumps), lumps_moved_side=moved, kept_tiles=len(keep),
                   dropped_tiles=len(recs) - len(keep), top_z=t,
                   chips=[(r, [round(v, 2) for v in rr], round(hh, 3)) for r, rr, hh in chips])
    rep["bodies"] = B.bodies
    _save(app, doc, doc_name, folder_path)
    with open(path.replace(".json", "-rep.json"), "w") as f:     # the MCP script output is not always returned
        json.dump(rep, f, indent=1, default=str)
    return rep
