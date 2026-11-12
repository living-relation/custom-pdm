"""Smooth-shaded renders and capped sections of the low-profile build (handbuilt-cad tools/render).
Usage: $CAD_PY render_lowpro.py [views...]   (env RUN_DIR as build_lowpro.py; RENDER_DIR = PNG folder)
Sections use handbuilt-cad tools/render/section.py cut_capped (closed, capped solids only; a solid whose cut is
refused is left out and listed in RENDER_DIR/enclosure-lowpro-section-refused.json)."""
import os, json, glob, sys
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
import pyvista as pv
from build123d import import_brep, Compound, Plane, Keep
sys.path.insert(0, os.path.join(os.environ.get("CAD_HOME", os.path.expanduser("~/projects/handbuilt-cad")), "tools", "render"))
import section as SEC
pv.OFF_SCREEN = True
RUN = os.environ.get("RUN_DIR", os.path.expanduser("~/scratch/encl-lowpro/runs/v1"))
RD = os.environ.get("RENDER_DIR", os.path.join(RUN, "renders")); os.makedirs(RD, exist_ok=True)
which = sys.argv[1:] or ["iso", "iso_open", "top", "front", "side", "under", "sec_stack", "sec_stud", "sec_out"]
meta = json.load(open(os.path.join(RUN, "meta.json"))); col = meta["colors"]
S = {os.path.basename(f)[:-5]: import_brep(f) for f in sorted(glob.glob(os.path.join(RUN, "brep", "*.brep")))}
def bb(s):
    b = s.bounding_box(); return (b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z)
skipped = []
def capped(so, o, n, keep):
    try:
        return SEC.cut_capped(so, o, n, keep)
    except AttributeError:
        h = so.split(Plane(origin=tuple(o), z_dir=tuple(n)), keep=Keep.BOTTOM if keep == "below" else Keep.TOP)
        h = Compound(list(h)) if isinstance(h, list) else h
        if not h.solids(): raise SEC.OpenSectionError("nothing kept")
        for x in h.solids():
            if not x.is_valid or not SEC._is_closed(x): raise SEC.OpenSectionError("open/invalid cut")
        if not SEC.cap_faces(h, o, n): raise SEC.OpenSectionError("no cap face")
        return h
def halfcut(name, s, axis, val, keep):
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
            skipped.append((name, str(e)[:60]))
    return body, caps
def scene(shapes, cam, fn, title, parallel=False, zoom=1.0, size=(1800, 1150)):
    p = pv.Plotter(off_screen=True, window_size=size); p.set_background("white")
    for k, s in shapes.items():
        if s is None: continue
        c = col.get(k, (0.6, 0.6, 0.6))
        if isinstance(s, tuple):
            m = SEC._tess(s[0], 0.05, 0.25); mc = SEC._tess(s[1], 0.05, 0.25)
            if m is not None: p.add_mesh(m.compute_normals(split_vertices=True, feature_angle=35), color=c, smooth_shading=True, specular=0.3)
            if mc is not None: p.add_mesh(mc, color=SEC.CAP_COLOR, smooth_shading=False)
        else:
            m = SEC._tess(s.faces(), 0.05, 0.25)
            if m is not None: p.add_mesh(m.compute_normals(split_vertices=True, feature_angle=35), color=c, smooth_shading=True, specular=0.3)
    p.camera_position = cam
    if parallel: p.enable_parallel_projection()
    p.camera.zoom(zoom); p.add_text(title, font_size=11, color="black")
    p.enable_anti_aliasing("ssaa"); p.screenshot(os.path.join(RD, f"enclosure-lowpro-{fn}.png")); p.close(); print("wrote", fn, flush=True)
bx0, bx1, by0, by1, bz0, bz1 = meta["base"]; cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
T = "custom-pdm enclosure low-profile v1"
noLid = {k: v for k, v in S.items() if k != "lid"}
if "iso" in which:
    scene(S, [(cx + 330, cy - 480, 330), (cx, cy, 5), (0, 0, 1)], "trimetric", T + "  trimetric (front-right)", zoom=1.3)
if "iso_open" in which:
    scene(noLid, [(cx + 330, cy - 480, 330), (cx, cy, 5), (0, 0, 1)], "trimetric-lid-off", T + "  trimetric, lid hidden", zoom=1.3)
if "top" in which:
    scene(noLid, [(cx, cy, 900), (cx, cy, 0), (0, 1, 0)], "top-lid-off", T + "  top, lid hidden (back edge up)", parallel=True, zoom=1.45)
if "front" in which:
    scene(S, [(cx, cy - 900, 10), (cx, cy, 10), (0, 0, 1)], "front", T + "  front elevation (X1, X2, USB-C)", parallel=True, zoom=1.45)
if "side" in which:
    scene(S, [(cx + 900, cy, 10), (cx, cy, 10), (0, 0, 1)], "side-right", T + "  right-end elevation (OUT studs, duct exit)", parallel=True, zoom=1.6)
if "under" in which:
    scene({k: v for k, v in S.items() if k != "duct-cover"}, [(cx - 300, cy - 420, -330), (cx, cy, -15), (0, 0, 1)], "underside",
          T + "  underside, duct cover hidden: fins, fan, feet", zoom=1.3)
if "sec_stack" in which:
    X = meta["TX"]["A2"] - 1.0     # through the A2 pedestals (chips near board x 0..11)
    sh = {k: halfcut(k, v, "x", X, "lt") for k, v in S.items() if bb(v)[0][0] < X}
    scene(sh, [(X + 600, cy, 15), (X, cy, 15), (0, 0, 1)], "section-board-sink-stack",
          T + f"  capped section X={X:.1f} through board A2 + pedestals (looking -X)", parallel=True, zoom=1.9)
if "sec_stud" in which:
    X, Y = meta["STUD"]["BATT"]
    sh = {k: halfcut(k, v, "y", Y, "gt") for k, v in S.items() if bb(v)[1][1] > Y}
    scene(sh, [(X + 60, Y - 600, 15), (X + 60, Y, 15), (0, 0, 1)], "section-BATT-stud-bar",
          T + f"  capped section Y={Y:.1f} through the BATT stud, bar and board M6 terminals (looking +Y)", parallel=True, zoom=2.6)
if "sec_out" in which:
    X, Y = meta["OUTS"]["Tm+"]
    sh = {k: halfcut(k, v, "y", Y - 2.0, "gt") for k, v in S.items() if bb(v)[1][1] > Y - 2.0}
    scene(sh, [(X - 40, Y - 600, 15), (X - 40, Y, 15), (0, 0, 1)], "section-OUT-stud-strap",
          T + f"  capped section Y={Y - 2:.1f} through an OUT stud, strap and board B (looking +Y)", parallel=True, zoom=3.0)
from collections import Counter
print("section cuts refused (solid left out):", dict(Counter(k for k, _ in skipped)))
json.dump(skipped, open(os.path.join(RD, "enclosure-lowpro-section-refused.json"), "w"), indent=0)
