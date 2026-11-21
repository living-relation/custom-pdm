"""Fastener solids for custom-pdm test2 (build123d port), built from the screw tool's dimension table
(screw_dimensions.csv copied beside this file; family 'SHCS ISO 4762', EN ISO 4762:2004 Table 1) with the
screw tool's HEAD_SEAT convention (origin on the bearing face under the head).
Plain shank at nominal diameter (cosmetic thread, like the Fusion screw library). Also a generic hex M-F standoff
(NOT from the screw tool: generic shape, part number TBD)."""
import csv, os, math
from build123d import *
CSV = os.environ.get("SCREW_CSV", os.path.join(os.path.dirname(os.path.abspath(__file__)), "screw_dimensions.csv"))
_ROWS = list(csv.DictReader(open(CSV)))
def row(family, size):
    for r in _ROWS:
        if r["family"] == family and r["size"] == size: return r
    raise KeyError((family, size))
def _hexprism(af, h, z0=0.0):
    return extrude(Pos(0, 0, z0) * RegularPolygon(af / 2 / math.cos(math.pi / 6), 6), amount=h).solid()
def shcs(size, L, at, down=True):
    r = row("SHCS ISO 4762", size)
    d = float(size[1:]); dk = float(r["dk_max"]); k = float(r["k_max"]); s = float(r["s_hex"]); t = float(r["t_socket_min"])
    lengths = [float(v) for v in r["lengths"].split()]
    assert L in lengths, f"{size} x {L} not a stock length in the screw tool table: {lengths}"
    head = Solid.make_cylinder(dk / 2, k)
    head = head.fillet(min(0.08 * d, 0.5), head.edges().sort_by(Axis.Z)[-1:])
    head = head.cut(_hexprism(s, t + 0.01, k - t)).solid()
    shank = Solid.make_cylinder(d / 2, L, Plane(origin=(0, 0, 0), z_dir=(0, 0, -1)))
    shank = shank.chamfer(min(0.1 * d, 0.5), None, shank.edges().sort_by(Axis.Z)[:1])
    sc = head.fuse(shank).solid()
    if not down: sc = sc.rotate(Axis.X, 180)
    return sc.translate(Vector(*at))
def bhcs(size, L, at):
    """button head hex-drive screw ISO 7380-1 (screw_dimensions.csv family 'Button ISO 7380-1'), HEAD_SEAT origin, head up.
    Dome drawn as a cylinder dk x k with a 0.8 k top fillet (simplified; SR Fasteners draws the real dome in Fusion)."""
    r = row("Button ISO 7380-1", size)
    d = float(size[1:]); dk = float(r["dk_max"]); k = float(r["k_max"]); s = float(r["s_hex"]); t = float(r["t_socket_min"])
    lengths = [float(v) for v in r["lengths"].split()]
    assert L in lengths, f"{size} x {L} not a stock ISO 7380-1 length in the screw tool table: {lengths}"
    head = Solid.make_cylinder(dk / 2, k)
    head = head.fillet(0.8 * k, head.edges().sort_by(Axis.Z)[-1:])
    head = head.cut(_hexprism(s, t + 0.01, k - t)).solid()
    shank = Solid.make_cylinder(d / 2, L, Plane(origin=(0, 0, 0), z_dir=(0, 0, -1)))
    shank = shank.chamfer(min(0.1 * d, 0.5), None, shank.edges().sort_by(Axis.Z)[:1])
    return head.fuse(shank).solid().translate(Vector(*at))
def standoff_mf(af, L, d, male_len, female_depth, at):
    """Generic male-female hex standoff: body L from at[2] upward, male thread (nominal dia) below."""
    body = _hexprism(af, L).cut(Solid.make_cylinder(d * 0.42, female_depth + 0.1, Plane(origin=(0, 0, L - female_depth))))
    male = Solid.make_cylinder(d / 2, male_len, Plane(origin=(0, 0, 0), z_dir=(0, 0, -1)))
    return body.fuse(male).solid().translate(Vector(*at))
