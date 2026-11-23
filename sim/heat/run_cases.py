"""Run every heat case in Elmer and collect results.json (docs/heat-analysis.md).

Usage (WSL, sim venv python for pyvista):  python run_cases.py <run_dir> [quick | <case> ...]
<run_dir> must hold mesh.msh + groups.json from mesh_heat.py. Needs ElmerGrid / ElmerSolver on PATH.

HEAT_GEOM unset / v2b-*: the 2026-11-11 / 11-12 cases: loads worst / typical (driver losses only, sim/heat/geometry.py
LOSS), air cases passive_upper, passive_lower, fans, pad k 1 / 3 / 6.
HEAT_GEOM=revF (the current enclosure, docs/heat-analysis.md 2026-11-23): loads from sim/heat/loads_revF.json
(make_loads.py: per-driver losses and per-board copper / joint / 5 V module heat from tools/thermal_a.py and
tools/thermal_board_b.py), the board heat as a uniform heat source in each board's slab; pad = TGP 3000, k 3 (k 1.5 as
the contact-resistance sensitivity, case "<load>|fans|1.5"); air cases fans for every load, passive_upper (fans off,
on a wall, fins vertical) and passive_lower (fans off, flat, fins down) for the fans-off reference loads.
h is iterated (h depends on the sink temperature) at the first pad k, then reused.
"""
import json, os, subprocess, sys
import numpy as np
import pyvista as pv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as G
import convection as C

RUN = os.path.abspath(sys.argv[1]); ARGS = sys.argv[2:]; QUICK = ARGS == ["quick"]
INFO = json.load(open(os.path.join(RUN, "groups.json")))
A_FIELD, A_EDGE = INFO["fin_field_area_mm2"] * 1e-6, INFO["edge_area_mm2"] * 1e-6
T_AMB = 60.0
REVF = G.HEAT_GEOM == "revF"
# materials (ASSUMED unless noted; see doc section 3)
K_AL = 167.0                       # 6061-T6 handbook value; 6063 would be higher
K_FR4 = 0.30                       # FR4 through-plane
# copper, mm, 4 layers: revF = the ORDERED copper, 1 oz outer + 1 oz inner on A and B (tools/copper_order.py);
# before: the KiCad stackup 43 / 17 / 17 / 43 um
CU_T = 4 * 0.035 if REVF else 2 * 0.04318 + 2 * 0.017272
CU_COVER = 0.5                     # ASSUMED average copper coverage of each layer
K_XY = (385.0 * CU_T * CU_COVER + K_FR4 * (G.T_PCB - CU_T * CU_COVER)) / G.T_PCB
PLATING = 0.020                    # ASSUMED via plating, mm (fab TBD)
A_BARREL = np.pi / 4 * (0.4 ** 2 - (0.4 - 2 * PLATING) ** 2)
RHO_PCB = 1900.0
LOADS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "loads_revF.json"))) if REVF else None


def k_patch(t):
    wx, wy, nv = G.EP[t]; fr = nv * A_BARREL / (wx * wy)
    return 385.0 * fr + K_FR4 * (1 - fr)


K_Z12, K_Z9 = k_patch("BTS7008"), k_patch("BTS70012")
if subprocess.run(["test", "-d", os.path.join(RUN, "mesh")]).returncode:
    subprocess.run(["ElmerGrid", "14", "2", "mesh.msh", "-autoclean", "-out", "mesh"], cwd=RUN, check=True,
                   stdout=subprocess.DEVNULL)
BOARD_BODY = {3: "B", 6: "A1", 7: "A2"}


def chip_w(load, c):
    return LOADS[load]["chips"].get(c["id"], 0.0) if REVF else G.LOSS[load][c["type"]]


def sif(name, k_pad, load, h):
    tens = lambda kz: "Heat Conductivity(3,3) = %g 0 0 0 %g 0 0 0 %g" % (K_XY, K_XY, kz)
    s = f"""Header
  Mesh DB "." "mesh"
End
Simulation
  Coordinate System = Cartesian
  Coordinate Scaling = 0.001
  Simulation Type = Steady state
  Steady State Max Iterations = 1
  Output Intervals = 1
End
"""
    mat = {1: f"Heat Conductivity = {K_AL}\n  Density = 2700.0", 2: f"Heat Conductivity = {k_pad}\n  Density = 3000.0",
           4: f"{tens(K_Z12)}\n  Density = {RHO_PCB}", 5: f"{tens(K_Z9)}\n  Density = {RHO_PCB}"}
    for b in (3, 6, 7):
        mat[b] = f"{tens(K_FR4)}\n  Density = {RHO_PCB}"
    nbf = 0
    for b in INFO.get("bodies", [1, 2, 3, 4, 5]):
        bf = ""
        if REVF and b in BOARD_BODY:
            n = BOARD_BODY[b]; w = LOADS[load]["board_w"][n]; v = INFO["board_vol_mm3"][n] * 1e-9
            nbf += 1
            bf = f"  Body Force = {nbf}\n"
            s += f"Body Force {nbf}\n  Heat Source = {w / (RHO_PCB * v)}\nEnd\n"
        s += f"Body {b}\n  Target Bodies(1) = {b}\n  Equation = 1\n  Material = {b}\n{bf}End\n"
        s += f"Material {b}\n  {mat[b]}\nEnd\n"
    s += f"""Equation 1
  Active Solvers(3) = 1 2 3
End
Solver 1
  Equation = Heat Equation
  Procedure = "HeatSolve" "HeatSolver"
  Variable = Temperature
  Linear System Solver = Iterative
  Linear System Iterative Method = CG
  Linear System Preconditioning = ILU0
  Linear System Max Iterations = 5000
  Linear System Convergence Tolerance = 1.0e-10
  Linear System Residual Output = 100
  Steady State Convergence Tolerance = 1.0e-6
End
Solver 2
  Exec Solver = After Simulation
  Equation = ResultOutput
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = "{name}"
  Output Format = vtu
  Save Geometry Ids = True
End
Solver 3
  Exec Solver = After Simulation
  Equation = SaveScalars
  Procedure = "SaveData" "SaveScalars"
  Filename = "{name}_scalars.dat"
  Variable 1 = Temperature
  Operator 1 = boundary int
  Operator 2 = area
End
"""
    if h["t_air"]:
        t0, dT = h["t_air"]; x0, x1 = (v / 1000.0 for v in G.fin_span())
        if G.AIR_IN_EAST:      # fans push west: cabin air enters at the east end
            text = f'Variable Coordinate 1\n    Real MATC "{t0} + {dT}*(({x1})-tx)/({x1 - x0})"'
        else:
            text = f'Variable Coordinate 1\n    Real MATC "{t0} + {dT}*(tx-({x0}))/({x1 - x0})"'
    else:
        text = f"{T_AMB}"
    s += f"""Boundary Condition 1
  Target Boundaries(1) = 1
  Save Scalars = True
  Heat Transfer Coefficient = {h['h_field']}
  External Temperature = {text}
End
Boundary Condition 2
  Target Boundaries(1) = 2
  Save Scalars = True
  Heat Transfer Coefficient = {h['h_edge']}
  External Temperature = {T_AMB}
End
"""
    for i, c in enumerate(INFO["chips"]):
        x0, x1, y0, y1 = c["rect"]; q = chip_w(load, c) / ((x1 - x0) * (y1 - y0) * 1e-6)
        s += f"Boundary Condition {3 + i}\n  Target Boundaries(1) = {INFO['chip_boundary'][c['id']]}\n  Heat Flux = {q}\nEnd\n"
    return s


def post(vtu, h, load):
    m = pv.read(vtu); sc = 1000.0 if m.bounds[1] < 5 else 1.0
    P = m.points * sc; T = m.point_data["temperature"]
    gid = m.cell_data["GeometryIds"]
    res = {"chips": {}, "boards": {}}
    on_top = np.abs(P[:, 2] - G.Z_TOP) < 1e-4
    for c in INFO["chips"]:
        x0, x1, y0, y1 = c["rect"]
        sel = on_top & (P[:, 0] >= x0 - 1e-4) & (P[:, 0] <= x1 + 1e-4) & (P[:, 1] >= y0 - 1e-4) & (P[:, 1] <= y1 + 1e-4)
        tb = float(T[sel].max()); pw = chip_w(load, c)
        res["chips"][c["id"]] = dict(type=c["type"], P=pw, board_max=tb, tj_est=tb + pw * G.RTHJC_MAX[c["type"]])
    for n in ("B", "A1", "A2"):
        sel = on_top & (P[:, 0] >= G.X0[n] - 1e-4) & (P[:, 0] <= G.X0[n] + G.BOARD_W[n] + 1e-4)
        res["boards"][n] = dict(top_max=float(T[sel].max()), top_mean=float(T[sel].mean()))
    sink = m.extract_cells(np.where(gid == 1)[0])
    ps = sink.points * sc
    res["sink_max"] = float(sink.point_data["temperature"].max())
    res["sink_min"] = float(sink.point_data["temperature"].min())
    top = np.abs(ps[:, 2]) < 1e-4
    res["sink_field_mean"] = float(sink.point_data["temperature"][top].mean())
    v = [float(x) for x in open(vtu.replace(os.sep + "mesh" + os.sep, os.sep).rsplit("_t", 1)[0] + "_scalars.dat").read().split()]
    iT1, iT2, a1, a2 = v[:4]
    if h["t_air"]:
        surf = sink.extract_surface(algorithm="dataset_surface").compute_cell_sizes(length=False, volume=False)
        cc = surf.cell_centers().points * sc; Ac = surf.cell_data["Area"]
        field = cc[:, 2] <= -G.PLATE_T + 1e-3
        t0, dT = h["t_air"]; x0, x1 = G.fin_span()
        xbar = float((cc[field, 0] * Ac[field]).sum() / Ac[field].sum())   # Text is linear in x
        text = t0 + dT * ((x1 - xbar) if G.AIR_IN_EAST else (xbar - x0)) / (x1 - x0)
    else:
        text = T_AMB
    res["airside_mean"] = iT1 / a1
    res["q_out"] = h["h_field"] * (iT1 - text * a1) + h["h_edge"] * (iT2 - T_AMB * a2)
    return res


def solve(name, k_pad, load, h):
    fs, fl, md = os.path.join(RUN, name + ".sif"), os.path.join(RUN, name + ".log"), os.path.join(RUN, "mesh")
    text = sif(name, k_pad, load, h)
    done = os.path.exists(fs) and open(fs).read() == text and os.path.exists(fl) and "ALL DONE" in open(fl).read()
    if not done:   # resumable: an identical case that already finished is only post-processed
        open(fs, "w").write(text)
        lg = subprocess.run(["ElmerSolver", name + ".sif"], cwd=RUN, capture_output=True, text=True)
        open(fl, "w").write(lg.stdout + lg.stderr)
        assert "ALL DONE" in lg.stdout, name
    vt = [f for f in os.listdir(md) if f.startswith(name + "_t") and f.endswith(".vtu")]
    return post(os.path.join(md, sorted(vt)[-1]), h, load)


CASES = {"passive_upper": C.passive_upper, "passive_lower": C.passive_lower, "fans": C.forced}
if REVF:
    plan = []
    for load, spec in LOADS.items():
        if load.startswith("_"):
            continue
        for cs in spec["air"]:
            plan.append((load, cs, [3.0] + ([1.5] if cs == "fans" and spec.get("pad_sensitivity") else [])))
    if ARGS and not QUICK:
        plan = [p for p in plan if p[0] in ARGS]
    if QUICK:
        plan = [p for p in plan if p[1] == "fans"][:1]
else:
    loads = ["worst"] if QUICK else ["worst", "typical"]
    plan = [(ld, cs, [3.0] if QUICK else [1.0, 3.0, 6.0]) for ld in loads for cs in (["passive_upper"] if QUICK else list(CASES))]
    plan = [(ld, cs, [3.0] + [k for k in ks if k != 3.0]) for ld, cs, ks in plan]
out = {"K_XY": K_XY, "K_Z12": K_Z12, "K_Z9": K_Z9, "mesh": INFO["n_tets"], "heat_geom": G.HEAT_GEOM, "runs": {}}
prev = os.path.join(RUN, "results.json")
if os.path.exists(prev) and json.load(open(prev)).get("heat_geom") == G.HEAT_GEOM:
    out["runs"] = json.load(open(prev))["runs"]          # keep runs of other loads (a run of only some loads)
for load, cs, kpads in plan:
    if not REVF:
        G.LOSS_CUR = G.LOSS[load]
    p_tot = sum(chip_w(load, c) for c in INFO["chips"]) + (sum(LOADS[load]["board_w"].values()) if REVF else 0.0)
    ts = T_AMB + 30.0
    k0 = kpads[0]
    for it in range(8):
        fn = CASES[cs]
        h = fn(ts, T_AMB, A_FIELD, A_EDGE, p_tot) if cs == "fans" else fn(ts, T_AMB, A_FIELD, A_EDGE)
        r = solve(f"{load}_{cs}_k{k0:g}", k0, load, h)
        print(load, cs, "iter", it, "h %.2f" % h["h_field"], "airside %.2f" % r["airside_mean"], flush=True)
        if abs(r["airside_mean"] - ts) < 0.3 or (cs == "fans" and it >= 1): break   # fan h does not depend on T_sink
        ts = 0.5 * (ts + r["airside_mean"])   # damped fixed point (plain update oscillates)
    for k in kpads:
        rr = r if k == k0 else solve(f"{load}_{cs}_k{k:g}", k, load, h)
        rr["h"] = {a: b for a, b in h.items() if not isinstance(b, tuple)}
        rr["p_total"] = p_tot
        out["runs"][f"{load}|{cs}|{k:g}"] = rr
        print(load, cs, k, "sink_max %.1f" % rr["sink_max"], "hottest %.1f" % max(v["board_max"] for v in rr["chips"].values()),
              "q_out %.2f of %.2f" % (rr["q_out"], p_tot), flush=True)
json.dump(out, open(os.path.join(RUN, "results.json"), "w"), indent=1)
print("WROTE", os.path.join(RUN, "results.json"))
