"""Build the simplified 3D heat model with Gmsh (OCC) and write mesh.msh (msh2) + groups.json.

Usage: python3 mesh_heat.py <out_dir> [size_factor]   (size_factor 1.0 = base mesh, 0.6 = refined)
Bodies (physical volume tags): 1 sink (plate + fins + pedestals, Al), 2 gap pads, 3 board slab
(layered-board equivalent), 4 via patch, 12 vias (BTS7008 / BTS7004 EP), 5 via patch, 9 vias (BTS70012 EP).
Boundaries (physical surface tags): 1 fin field (fins + plate underside), 2 plate outer edges,
3.. one per chip EP top face (heat flux in). Every other face is adiabatic (inside the lid).
Simplifications: no corner radii, holes, bosses, feet, screws or lid; boards are uniform slabs.
"""
import json, os, sys
import gmsh
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as G

out = sys.argv[1]; f = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
os.makedirs(out, exist_ok=True)
gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
gmsh.model.add("pdm_heat"); occ = gmsh.model.occ
box = lambda x0, x1, y0, y1, z0, z1: occ.addBox(x0, y0, z0, x1 - x0, y1 - y0, z1 - z0)

ents = []
ents.append(box(G.LX0, G.LX1, G.LY0, G.LY1, -G.PLATE_T, 0.0))
for (x0, x1, y0, y1) in G.fins():
    ents.append(box(x0, x1, y0, y1, -G.PLATE_T - G.FIN_H, -G.PLATE_T))
for (x0, x1, y0, y1) in G.pedestals():
    ents.append(box(x0, x1, y0, y1, 0.0, G.PED_H))
    ents.append(box(x0, x1, y0, y1, G.PED_H, G.Z_BOT))
for n in ("B", "A1", "A2"):
    ents.append(box(G.X0[n], G.X0[n] + G.BOARD_W[n], -G.BOARD_D, 0.0, G.Z_BOT, G.Z_TOP))
CH = G.chips()
for c in CH:
    x0, x1, y0, y1 = c["rect"]; ents.append(box(x0, x1, y0, y1, G.Z_BOT, G.Z_TOP))
occ.fragment([(3, t) for t in ents], [])
occ.synchronize()

eps = 1e-3
def bb(d, t): return gmsh.model.getBoundingBox(d, t)
def inrect(b, r): return abs(b[0] - r[0]) < eps and abs(b[3] - r[1]) < eps and abs(b[1] - r[2]) < eps and abs(b[4] - r[3]) < eps

vol = {1: [], 2: [], 3: [], 4: [], 5: []}
for (_, t) in gmsh.model.getEntities(3):
    b = bb(3, t)
    if b[5] <= G.PED_H + eps:
        vol[1].append(t)
    elif b[2] >= G.PED_H - eps and b[5] <= G.Z_BOT + eps:
        vol[2].append(t)
    else:
        hit = [c for c in CH if inrect(b, c["rect"])]
        vol[(5 if hit[0]["type"] == "BTS70012" else 4) if hit else 3].append(t)
assert len(vol[4]) + len(vol[5]) == len(CH), (len(vol[4]), len(vol[5]))

sink_faces = set()
for t in vol[1]:
    sink_faces |= {abs(s[1]) for s in gmsh.model.getBoundary([(3, t)], oriented=False)}
fin_field, edges = [], []
for s in sink_faces:
    b = bb(2, s)
    if b[5] <= -G.PLATE_T + eps:
        fin_field.append(s)
    elif b[2] >= -G.PLATE_T - eps and b[5] <= eps and (abs(b[0] - b[3]) < eps or abs(b[1] - b[4]) < eps) and \
            (abs(b[0] - G.LX0) < eps or abs(b[3] - G.LX1) < eps or abs(b[1] - G.LY0) < eps or abs(b[4] - G.LY1) < eps):
        edges.append(s)
chip_face = []
for c in CH:
    fs = [s for (_, s) in gmsh.model.getEntities(2) if abs(bb(2, s)[2] - G.Z_TOP) < eps and abs(bb(2, s)[5] - G.Z_TOP) < eps and inrect(bb(2, s), c["rect"])]
    assert len(fs) == 1, (c["id"], fs); chip_face.append(fs[0])

for tag, ts in vol.items():
    gmsh.model.addPhysicalGroup(3, ts, tag)
gmsh.model.addPhysicalGroup(2, fin_field, 1); gmsh.model.addPhysicalGroup(2, edges, 2)
for i, s in enumerate(chip_face):
    gmsh.model.addPhysicalGroup(2, [s], 3 + i)

def size(tags, lc):
    pts = gmsh.model.getBoundary([(3, t) for t in tags], combined=False, recursive=True)
    gmsh.model.mesh.setSize(pts, lc)
size(vol[1], 4.0 * f)
size(vol[3], 2.0 * f)
size(vol[2], 1.2 * f)
size(vol[4] + vol[5], 0.7 * f)
gmsh.option.setNumber("Mesh.Algorithm3D", 10)   # HXT
gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
gmsh.model.mesh.generate(3)
gmsh.write(os.path.join(out, "mesh.msh"))
ne = sum(len(e) for e in gmsh.model.mesh.getElements(3)[1])
area = lambda ss: sum(gmsh.model.occ.getMass(2, s) for s in ss)
info = dict(size_factor=f, n_tets=int(ne), chips=CH, fin_field_area_mm2=area(fin_field), edge_area_mm2=area(edges),
            chip_boundary={c["id"]: 3 + i for i, c in enumerate(CH)}, n_fins=len(G.fins()))
json.dump(info, open(os.path.join(out, "groups.json"), "w"), indent=1)
print("tets", ne, "fin field mm2 %.0f edges mm2 %.0f" % (info["fin_field_area_mm2"], info["edge_area_mm2"]))
gmsh.finalize()
