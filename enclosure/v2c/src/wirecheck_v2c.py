"""Harness check (revE): every wire / cable solid of CPDM-HAR-200 against every other part of the build, and against the other wires.
Rule (cad.md): an insulated wire may TOUCH plastic and other wires; it may not pass THROUGH anything (board, screw, standoff,
bar, lid, connector body ...). FAILS (exit 1) on a wire-vs-part overlap volume above TOL that is not in ALLOWED.
ALLOWED: the four fan leads inside the cord grip (the maker model is solid: it grips them).
Wire-vs-wire overlaps are listed in the report (fan-out zones behind X1 / X2), they do not fail the check.
Usage: $CAD_PY wirecheck_v2c.py F1   (RUN_DIR; WIRE_PRE=<runs dir> = check the table against another run's breps
before a build: the table is then made from that run's meta.json)  -> <run>/<VAR>/wirecheck.json"""
import os, sys, json, glob, itertools
from multiprocessing import Pool
from build123d import import_brep
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
import harness_paths_v2c as HP
VAR = sys.argv[1]; PRE = os.environ.get("WIRE_PRE"); RUN = PRE or os.environ["RUN_DIR"]; OUT = os.path.join(RUN, VAR)
TOL = 0.05                                               # mm3
ALLOWED = {(w, "fan-lead-gland") for w in ("W061", "W062", "W063", "W064")}
SKIP = ("harness-", "wire-ribbons", "usb-cables", "vendor-plug")
def bb(s): b = s.bounding_box(); return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)
def hit(a, b, g=0.0): return not (a[3] + g < b[0] or b[3] + g < a[0] or a[4] + g < b[1] or b[4] + g < a[1] or a[5] + g < b[2] or b[5] + g < a[2])
def vol(a, b):
    c = BRepAlgoAPI_Common(a.wrapped, b.wrapped); c.Build()
    if not c.IsDone(): return -1.0
    p = GProp_GProps(); BRepGProp.VolumeProperties_s(c.Shape(), p); return p.Mass()
def table():
    f = os.path.join(OUT, "harness_paths.json")
    if os.path.exists(f) and not PRE: return json.load(open(f))
    m = json.load(open(os.path.join(OUT, "meta.json")))
    ends = m.get("harness_ends") or dict(REAR={k: bb(import_brep(glob.glob(os.path.join(OUT, "brep", f"vendor-{k}-*.brep"))[0]))[4] for k in ("X1", "X2")},
                                         USB_REAR=bb(import_brep(os.path.join(OUT, "brep", "usbc-bulkhead-LP-16-C05SX-02-101.brep")))[4])
    return HP.table(HP.G_from_meta(m, ends["REAR"], ends["USB_REAR"]))
T = W = P = None
def load():
    global T, W, P
    T = table(); W = {}
    for w, d in T.items(): s = HP.solid(d); W[w] = (s, bb(s))
    P = {}
    for f in sorted(glob.glob(os.path.join(OUT, "brep", "*.brep"))):
        nm = os.path.basename(f)[:-5]
        if nm.startswith(SKIP): continue
        P[nm] = [(so, bb(so)) for so in import_brep(f).solids()]
def work(w):
    s, b = W[w]; res = []
    for nm, sols in P.items():
        v = sum(max(vol(s, so), 0.0) for so, sb in sols if hit(b, sb))
        if v > TOL: res.append((w, nm, round(v, 2)))
    ww = [(w, o, round(v, 2)) for o in W if o > w and hit(b, W[o][1]) for v in [vol(s, W[o][0])] if v > TOL]
    return res, ww
if __name__ == "__main__":
    import multiprocessing                                # spawn: a forked OCC process can hang on a lock taken before the fork
    T = table()
    with multiprocessing.get_context("spawn").Pool(int(os.environ.get("NPROC", "12")), initializer=load) as pool: out = pool.map(work, sorted(T), chunksize=2)
    parts = [x for r, _ in out for x in r]; wires = [x for _, r in out for x in r]
    fails = [x for x in parts if (x[0], x[1]) not in ALLOWED]
    rep = dict(solids=len(T), rows=sum(len(d["rows"]) for d in T.values()), wire_part_overlaps=parts, fails=fails, wire_wire_overlaps=wires,
               min_r_over_od={w: d["r_over_od"] for w, d in T.items() if d["r_over_od"] < 3.0}, total_length_mm=round(sum(d["length"] for d in T.values()), 0))
    json.dump(rep, open(os.path.join(OUT, "wirecheck.json"), "w"), indent=1)
    for x in fails: print("FAIL wire through part", x)
    by = {}
    for w, nm, v in fails: by.setdefault(nm, []).append(w)
    for nm, ws in sorted(by.items()): print("  ", nm, len(ws), " ".join(ws))
    print("wire-wire overlaps:", len(wires), " ".join(f"{a}/{b}:{v:g}" for a, b, v in wires[:60]))
    print("solids", rep["solids"], "rows", rep["rows"], "allowed", len(parts) - len(fails), "bend < 3 x OD:", rep["min_r_over_od"], "fails:", len(fails))
    sys.exit(1 if fails else 0)
