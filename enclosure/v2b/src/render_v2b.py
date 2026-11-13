"""Smooth-shaded renders for custom-pdm enclosure v2b (adapted from Grok's render_test2.py, same renderer and style).
Usage: $CAD_PY render_v2b.py F1|F2 [views...]   (RUN_DIR and RENDER_DIR from the environment)
Sections use tools/render/section.py cut_capped (closed, capped solids; open cuts are refused, AGENTS.md rule 15).
Cap faces are drawn in section.CAP_COLOR. No mesh lines."""
import os, json, glob, sys
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
import numpy as np, pyvista as pv
from build123d import import_brep, Compound
sys.path.insert(0, os.path.join(os.environ["CAD_HOME"], "tools", "render"))
import section as SEC
pv.OFF_SCREEN = True
VAR = sys.argv[1]; which = sys.argv[2:] or ["outbay", "iso", "iso_sw", "iso_ne", "iso_nw", "iso_open", "iso_open_nw", "lidT", "top", "front", "back", "left", "right", "sec_stack", "sec_stud", "under", "exploded"]
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(os.environ.get("RUN_DIR", os.path.join(ROOT, "runs", "latest")), VAR)
RD = os.environ.get("RENDER_DIR", os.path.join(OUT, "..", "renders")); os.makedirs(RD, exist_ok=True)
meta = json.load(open(os.path.join(OUT, "meta.json"))); col = meta["colors"]
S = {os.path.basename(f)[:-5]: import_brep(f) for f in sorted(glob.glob(os.path.join(OUT, "brep", "*.brep")))}
def bb(s):
    b = s.bounding_box(); return (b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z)
def mesh(s, tol=0.05):
    return SEC._tess(s.faces(), tol, 0.25)
skipped = []
def capped(so, o, n, keep):
    """section.cut_capped; when OCCT's split hands back a ShapeList (several pieces) cut_capped can't take it, so the
    same split + the same closed/valid/cap-face checks (section._is_closed, section.cap_faces) are applied to the pieces."""
    try:
        return SEC.cut_capped(so, o, n, keep)
    except AttributeError:
        from build123d import Plane, Keep
        pl = Plane(origin=tuple(o), z_dir=tuple(n))
        h = so.split(pl, keep=Keep.BOTTOM if keep == "below" else Keep.TOP)
        h = Compound(list(h)) if isinstance(h, list) else h
        if not h.solids(): raise SEC.OpenSectionError("nothing kept")
        for x in h.solids():
            if not x.is_valid or not SEC._is_closed(x): raise SEC.OpenSectionError("open/invalid cut")
        if not SEC.cap_faces(h, o, n): raise SEC.OpenSectionError("no cap face")
        return h
def halfcut(name, s, axis, val, keep):
    """keep 'lt' = side below val on axis, 'gt' = above. Returns (body, caps) face lists."""
    i = "xyz".index(axis); n = [0, 0, 0]; n[i] = 1; o = [0, 0, 0]; o[i] = val
    body, caps = [], []
    for so in s.solids():
        mn, mx = bb(so)
        if (keep == "lt" and mx[i] <= val) or (keep == "gt" and mn[i] >= val): body += so.faces(); continue
        if (keep == "lt" and mn[i] >= val) or (keep == "gt" and mx[i] <= val): continue
        try:
            h = capped(so, o, n, "below" if keep == "lt" else "above")
            cf = SEC.cap_faces(h, o, n); ids = {id(f.wrapped.TShape()) for f in cf}
            caps += cf; body += [f for f in h.faces() if id(f.wrapped.TShape()) not in ids]
        except Exception as e:
            skipped.append((name, str(e)[:60]))      # refused cut: the solid is left out, never drawn open
    return body, caps
def scene(shapes, cam, fn, title, parallel=False, zoom=1.0, size=(1800, 1150), opac=None):
    opac = opac or {}
    p = pv.Plotter(off_screen=True, window_size=size); p.set_background("white")
    for k, s in shapes.items():
        if s is None: continue
        c = col.get(k, (0.6, 0.6, 0.6))
        if isinstance(s, tuple):
            m = SEC._tess(s[0], 0.05, 0.25); mc = SEC._tess(s[1], 0.05, 0.25)
            if m is not None: p.add_mesh(m.compute_normals(split_vertices=True, feature_angle=35), color=c, smooth_shading=True, specular=0.3)
            if mc is not None: p.add_mesh(mc, color=SEC.CAP_COLOR, smooth_shading=False)
        else:
            m = mesh(s)
            if m is not None: p.add_mesh(m.compute_normals(split_vertices=True, feature_angle=35), color=c, smooth_shading=True, specular=0.3, opacity=opac.get(k, 1.0))
    p.camera_position = cam
    if parallel: p.enable_parallel_projection()
    p.camera.zoom(zoom); p.add_text(title, font_size=11, color="black")
    p.enable_anti_aliasing("ssaa"); p.screenshot(os.path.join(RD, f"{VAR}-{fn}.png")); p.close(); print("wrote", fn, flush=True)
lx0, lx1, ly0, ly1 = meta["footprint"]; cx, cy = (lx0 + lx1) / 2, (ly0 + ly1) / 2
T = f"custom-pdm enclosure v2b-{VAR}"
if "iso" in which:
    scene(S, [(cx + 330, cy - 420, 330), (cx, cy, 10), (0, 0, 1)], "iso", T + "  iso (south-east)", zoom=1.25)
if "iso_open" in which:
    scene({k: v for k, v in S.items() if k != "lid"}, [(cx + 330, cy - 420, 330), (cx, cy, 10), (0, 0, 1)], "iso-lid-off", T + "  iso, lid hidden", zoom=1.25)
if "top" in which:
    scene(S, [(cx, cy, 900), (cx, cy, 0), (0, 1, 0)], "top", T + "  top (north up)", parallel=True, zoom=1.5)
if "front" in which:
    scene(S, [(cx, cy - 900, 25), (cx, cy, 25), (0, 0, 1)], "front", T + "  front (south) elevation: X1, X2, USB-C", parallel=True, zoom=1.5)
if "back" in which:
    scene(S, [(cx, cy + 900, 25), (cx, cy, 25), (0, 0, 1)], "back", T + "  back (north) elevation", parallel=True, zoom=1.5)
if "left" in which:
    scene(S, [(cx - 900, cy, 25), (cx, cy, 25), (0, 0, 1)], "left", T + "  left (west) end", parallel=True, zoom=1.9)
if "right" in which:
    scene(S, [(cx + 900, cy, 25), (cx, cy, 25), (0, 0, 1)], "right", T + "  right (east) end", parallel=True, zoom=1.9)
if "outbay" in which:                                # OUT1-4 bay + wire-way close-ups (Dan 2026-11-12 wire-way fix)
    bx = (meta["OUTT"]["OUT1"][0] + meta["OUTT"]["OUT2"][0]) / 2 - 12; by = (meta["OUTT"]["OUT1"][1] + meta["OUTT"]["OUT3"][1]) / 2
    scene(S, [(bx - 150, by - 170, 170), (bx, by, 22), (0, 0, 1)], "outbay-sw", T + "  OUT1-4 bay + wire-way to the west edge (from south-west)", zoom=1.0)
    scene(S, [(bx - 150, by + 170, 150), (bx, by, 22), (0, 0, 1)], "outbay-nw", T + "  OUT1-4 bay + wire-way (from north-west)", zoom=1.0)
if "iso_sw" in which:
    scene(S, [(cx - 330, cy - 420, 330), (cx, cy, 10), (0, 0, 1)], "iso-sw", T + "  iso (south-west)", zoom=1.25)
if "iso_ne" in which:
    scene(S, [(cx + 330, cy + 420, 330), (cx, cy, 10), (0, 0, 1)], "iso-ne", T + "  iso (north-east)", zoom=1.25)
if "iso_nw" in which:
    scene(S, [(cx - 330, cy + 420, 330), (cx, cy, 10), (0, 0, 1)], "iso-nw", T + "  iso (north-west)", zoom=1.25)
if "iso_open_nw" in which:
    scene({k: v for k, v in S.items() if k != "lid"}, [(cx - 330, cy + 420, 330), (cx, cy, 10), (0, 0, 1)], "iso-lid-off-nw", T + "  iso NW, lid hidden", zoom=1.25)
if "lidT" in which:
    scene(S, [(cx + 330, cy - 420, 330), (cx, cy, 10), (0, 0, 1)], "lid-transparent-se", T + "  lid transparent, iso SE", zoom=1.25, opac={"lid": 0.28})
    scene(S, [(cx - 330, cy + 420, 330), (cx, cy, 10), (0, 0, 1)], "lid-transparent-nw", T + "  lid transparent, iso NW", zoom=1.25, opac={"lid": 0.28})
if "exploded" in which:
    ex = {}
    for k, v in S.items():
        dz = 150 if k.startswith(("lid", "heat-set", "vendor-X", "vendor-plug", "panel-nuts", "usbc-")) else 100 if k.startswith(("input", "screws_SSH-M3")) and k != "input-deck" else 100 if k == "input-deck" else 0
        if k.startswith(("heat-sink", "fans", "vendor-fan", "tie", "hub-standoffs")): dz = -60
        ex[k] = v.translate((0, 0, dz)) if dz else v
    scene(ex, [(cx + 380, cy - 480, 330), (cx, cy, 30), (0, 0, 1)], "exploded", T + "  exploded: lid + connectors up, deck + input boards, sink down", zoom=1.0)
if "under" in which:
    scene(S, [(cx - 300, cy - 380, -330), (cx, cy, -10), (0, 0, 1)], "under", T + "  underside: fins, feet, fan(s)", zoom=1.25)
if "sec_stack" in which:
    X = meta["X0"]["A1"] + 37.846 + 6.0
    sh = {k: halfcut(k, v, "x", X, "lt") for k, v in S.items() if bb(v)[0][0] < X}
    scene(sh, [(X + 600, cy, 20), (X, cy, 20), (0, 0, 1)], "section-sink-board-stack",
          T + f"  capped section X={X:.1f} through A1 pedestals (looking west)", parallel=True, zoom=2.2)
if "sec_stud" in which:
    X, Y = meta["FEED"]["BATT+"]
    sh = {k: halfcut(k, v, "y", Y, "gt") for k, v in S.items() if bb(v)[1][1] > Y}
    scene(sh, [(X + 40, Y - 600, 20), (X + 40, Y, 20), (0, 0, 1)], "section-BATT-stud",
          T + f"  capped section Y={Y:.2f} through BATT+ terminal, copper bar and boss (looking north)", parallel=True, zoom=3.2)
    X, Y = meta["OUTT"]["OUT1"]
    sh = {k: halfcut(k, v, "y", Y, "gt") for k, v in S.items() if bb(v)[1][1] > Y}
    scene(sh, [(X - 10, Y - 600, 20), (X - 10, Y, 20), (0, 0, 1)], "section-OUT-bay",
          T + f"  capped section Y={Y:.2f} through OUT1/OUT2 copper bosses and terminal bay (looking north)", parallel=True, zoom=3.6)
from collections import Counter
print("section cuts refused (solid left out):", dict(Counter(k for k, _ in skipped)))
json.dump(skipped, open(os.path.join(RD, f"{VAR}-section-refused.json"), "w"), indent=0)
