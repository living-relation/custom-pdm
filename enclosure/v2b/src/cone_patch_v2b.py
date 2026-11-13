"""F2 flow-cone patch (Dan 2026-11-13 16:05): replace the convex paraboloid flow cone in an existing F2 build with the
"reverse velocity stack" concave flare, without a full rebuild (the full build needs the git-ignored PACK and VENDOR
folders; the same change is in build_v2b.py for the next full build).
Reads RUN_DIR/F2/brep + meta.json, rewrites flow-cone-PA12, heat-sink (M3 clearance + 90 deg countersink), the cone
screw (SSH M3 x 12 from below -> CSK M3 x 12 from the plate top), parts STEPs, assembly STEPs and meta.json.
Usage: $CAD_PY cone_patch_v2b.py   (RUN_DIR from the environment)"""
import os, json, glob, math
from build123d import *
OUT = os.path.join(os.environ["RUN_DIR"], "F2")
meta = json.load(open(os.path.join(OUT, "meta.json")))
B = lambda n: os.path.join(OUT, "brep", n + ".brep")
P = meta["P"]; pt = P["plate_t"]
fi = meta.get("fan_info") or meta.get("fan") or {}
FCX, FCY = (fi.get("c") or (150.0, -52.0))
z_top = fi.get("z_top", -pt - P["fin_h"] + 18.0)
def cyl(d, p0, L): return Solid.make_cylinder(d / 2, L, Plane(origin=p0))
# --- new cone (same formula as build_v2b.py)
z_apex = z_top + 1.5; Hc = -pt - z_apex; Rc = 29.0; rt = 1.0
prof = [(Rc - (Rc - rt) * math.cos(ph), z_apex + Hc * math.sin(ph)) for ph in [math.pi / 2 * i / 24 for i in range(25)]]
sp = Spline(*[Vector(FCX + r_, FCY, z_) for (r_, z_) in prof])
wr = Wire([Line((FCX, FCY, z_apex), (FCX + rt, FCY, z_apex)), sp,
           Line((FCX + Rc, FCY, -pt), (FCX, FCY, -pt)), Line((FCX, FCY, -pt), (FCX, FCY, z_apex))])
cone = revolve(Face(wr), Axis((FCX, FCY, 0), (0, 0, 1)), 360).solid()
try:
    cone = cone.fillet(0.9, cone.faces().sort_by(Axis.Z)[0].edges())
except Exception as e:
    print("tip fillet skipped:", e)
cone = cone.cut(cyl(4.0, (FCX, FCY, -pt - 4.2), 4.3))
# --- sink: through clearance + countersink
sink = import_brep(B("heat-sink"))
sink = sink.cut(cyl(3.4, (FCX, FCY, -pt - 0.1), pt + 0.2)).cut(Solid.make_cone(3.4 / 2, 6.6 / 2, 1.6, Plane(origin=(FCX, FCY, -1.6))))
# --- screws: drop the old cone screw (near the fan axis), add the countersunk one
old = import_brep(B("screws_SSH-M3-0.5_x_12"))
keep = [s for s in old.solids() if math.hypot(s.center().X - FCX, s.center().Y - FCY) > 3.0]
dropped = len(old.solids()) - len(keep)
csk = Solid.make_cone(1.5, 3.0, 1.5, Plane(origin=(FCX, FCY, -1.5))).fuse(cyl(3.0, (FCX, FCY, -12.0), 10.5))
new = {"flow-cone-PA12": cone, "heat-sink": sink, "screws_CSK-M3-0.5_x_12_(ISO_10642)": csk}
if keep: new["screws_SSH-M3-0.5_x_12"] = Compound(keep)
else:
    for ext in ("brep", "parts"):
        for f in glob.glob(os.path.join(OUT, ext, "screws_SSH-M3-0.5_x_12.*")): os.remove(f)
for nm, s in new.items():
    export_brep(s, B(nm)); export_step(s, os.path.join(OUT, "parts", nm + ".step"))
col = meta["colors"]; col.setdefault("screws_CSK-M3-0.5_x_12_(ISO_10642)", col.get("screws_SSH-M3-0.5_x_12", [0.3, 0.3, 0.32]))
lab = meta.get("labels", {})
if isinstance(lab, dict):
    lab["flow-cone-PA12"] = "MJF PA12 reverse-velocity-stack flow cone (concave quarter-ellipse flare, base R29 tangent to the plate, tip R1 1.5 above the Noctua hub), M3 x 12 CSK from the plate top into a heat-set insert (Dan 2026-11-13)"
kids = []
for f in sorted(glob.glob(os.path.join(OUT, "brep", "*.brep"))):
    nm = os.path.basename(f)[:-5]; s = import_brep(f); s.label = nm
    c = col.get(nm)
    if c: s.color = Color(*c[:3])
    kids.append(s)
export_step(Compound(children=kids, label="custom-pdm-enclosure-v2b-F2"), os.path.join(OUT, "custom-pdm-enclosure-v2b-F2-assembly.step"))
export_step(Compound(children=[k for k in kids if not k.label.startswith(("board", "input-board"))], label="noboards"), os.path.join(OUT, "v2b-F2-noboards.step"))
info = dict(profile="reverse velocity stack, quarter-ellipse concave flare", R=Rc, tip_r=rt, H=round(Hc, 2), apex_gap=1.5,
            z_apex=round(z_apex, 2), mount="M3 x 12 countersunk (ISO 10642) from the plate top into an M3 heat-set insert (4 long)")
for k in ("fan_info", "fan"):
    if isinstance(meta.get(k), dict): meta[k]["cone"] = info
meta["cone_patch"] = info
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1, default=str)
vol = cone.volume
print("cone patched: R", Rc, "H", round(Hc, 2), "apex z", round(z_apex, 2), "vol cm3", round(vol / 1000, 2), "mass g (PA12 1.01)", round(vol / 1000 * 1.01, 1), "old screws dropped", dropped)
