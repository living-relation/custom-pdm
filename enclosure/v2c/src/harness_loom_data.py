"""custom-pdm enclosure v2c revF: the loom's hand data (read by harness_comb_v2c.py).
hand(G) = wires with a path written out by hand; order(G) = the order in which the builder places the other wires.
World frame = build_v2c.py (X east, Y north, Z up, mm). Free lanes were read off section pictures of the draft build
(board front edge y -95.6, parts on the boards <= z 9.5 near the front; BATT bar y -74..-54 z 19.2..24.2; input deck z 30.8..33.8
from y -84; Micro-Fit housings y > -89.6, z 40.5..47.5; X1 body y < -111.3, z 14.5..51.5; X2 body y < -107.4, z 17.5..54)."""
import harness_paths_v2c as HP
PT = -86.9            # plane of the T5-T8 wires behind X1: the last plane a 12 AWG wire can use south of the deck rail (edge at y -85.1)

def hand(G):
    """T5-T8 (12 AWG, X1's four centre cavities B D E G; bend radius 10.95): the cavities are surrounded by the 16 AWG ring, so
    these wires stay straight the longest and turn in the deepest plane PT. D and E drop on 45 deg ramps (22.7 long: two full
    bends fit) to lanes at lug height; B runs west above them and drops at x 82; lanes run north over board B and turn 30 / 35 deg
    into the lugs. G (T8, 18 mm behind X1 and 27 mm lower: no direct path fits two bends) goes round: ramp down east of the
    cavities, south under the X1 stubs, west, north into the lug."""
    cy = G["CAVY"]["X1"]; H = {}
    def cav(c): return HP.cav(G, "X1", c)
    def lane(k, x):                                               # lug mouth -> the lane's corner point at x
        A, u = HP.t58_mouth(G, k); s = (A[0] - x) / -u[0]; return A, (x, A[1] + s * u[1], A[2])
    zb = G["TTOP"] + 2.8
    xb, zB = cav("B"); A, C = lane("T5", 82.0);  H["W016"] = [A, C, (82.0, PT, zb), (82.0, PT, zB), (xb, PT, zB), (xb, cy, zB)]
    xd, zD = cav("D"); xl = xd - 15.3; A, C = lane("T6", xl); H["W017"] = [A, C, (xl, PT, zb), (xd, PT, zD), (xd, cy, zD)]
    xe, zE = cav("E"); xl = xe - 15.3; A, C = lane("T7", xl); H["W018"] = [A, C, (xl, PT, zb), (xe, PT, zE), (xe, cy, zE)]
    xg, zG = cav("G"); A, u = HP.t58_mouth(G, "T8"); C = HP.add(A, u, 3.0)
    H["W019"] = [A, C, (C[0], -108.85, zb), (125.0, -108.85, zb), (125.0, PT, zb), (xg, PT, zG), (xg, cy, zG)]
    return H

def order(G):
    """X1 16 AWG wires: board A2's first (their cavities are X1's east side: nearest plane), each group from the east; then the X2 wires, highest cavity
    first; then the splice-to-pad wires."""
    rows = HP.read_rows(); x1 = []; x2 = []; sp = []
    for r in rows:
        e = {r["From connector"]: r["From pin"], r["To connector"]: r["To pin"]}
        if any(k in ("SP1", "SP2") for k in e) and "X2" not in e: sp.append(r["Wire ID"])
        if "X1" in e and r["AWG"] == "16": x1.append((0 if any(k.startswith("A2") for k in e) else 1, -HP.CAV["X1"][e["X1"]]["x"], r["Wire ID"]))
        if "X2" in e: x2.append((0 if any(k.endswith("-J2") for k in e) else 1, -HP.CAV["X2"][e["X2"]]["y"], r["Wire ID"]))
    return sp + [t[-1] for t in sorted(x1)] + [t[-1] for t in sorted(x2)]
