"""Run every heat case in Elmer and collect results.json (docs/heat-analysis.md).

Usage (WSL, sim venv python for pyvista):  python run_cases.py <run_dir> [quick]
<run_dir> must hold mesh.msh + groups.json from mesh_heat.py. Needs ElmerGrid / ElmerSolver on PATH.
For each load (worst, typical) and air case (passive_upper, passive_lower, fans): h is iterated
(h depends on the sink temperature) at pad k = 3 W/mK, then the same h is used for k = 1 and 6.
"""
import json, os, subprocess, sys
import numpy as np
import pyvista as pv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as G
import convection as C

RUN = os.path.abspath(sys.argv[1]); QUICK = len(sys.argv) > 2
INFO = json.load(open(os.path.join(RUN, "groups.json")))
A_FIELD, A_EDGE = INFO["fin_field_area_mm2"] * 1e-6, INFO["edge_area_mm2"] * 1e-6
T_AMB = 60.0
# materials (ASSUMED unless noted; see doc section 2)
K_AL = 167.0                       # 6061-T6 handbook value; 6063 would be higher
K_FR4 = 0.30                       # FR4 through-plane
CU_T = 2 * 0.04318 + 2 * 0.017272  # copper, mm, 4 layers (board stackup)
CU_COVER = 0.5                     # ASSUMED average copper coverage of each layer
K_XY = (385.0 * CU_T * CU_COVER + K_FR4 * (G.T_PCB - CU_T * CU_COVER)) / G.T_PCB
PLATING = 0.020                    # ASSUMED via plating, mm (fab TBD)
A_BARREL = np.pi / 4 * (0.4 ** 2 - (0.4 - 2 * PLATING) ** 2)


def k_patch(t):
    wx, wy, nv = G.EP[t]; fr = nv * A_BARREL / (wx * wy)
    return 385.0 * fr + K_FR4 * (1 - fr)


K_Z12, K_Z9 = k_patch("BTS7008"), k_patch("BTS70012")
if subprocess.run(["test", "-d", os.path.join(RUN, "mesh")]).returncode:
    subprocess.run(["ElmerGrid", "14", "2", "mesh.msh", "-autoclean", "-out", "mesh"], cwd=RUN, check=True,
                   stdout=subprocess.DEVNULL)


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
Body 1
  Target Bodies(1) = 1
  Equation = 1
  Material = 1
End
Body 2
  Target Bodies(1) = 2
  Equation = 1
  Material = 2
End
Body 3
  Target Bodies(1) = 3
  Equation = 1
  Material = 3
End
Body 4
  Target Bodies(1) = 4
  Equation = 1
  Material = 4
End
Body 5
  Target Bodies(1) = 5
  Equation = 1
  Material = 5
End
Material 1
  Heat Conductivity = {K_AL}
  Density = 2700.0
End
Material 2
  Heat Conductivity = {k_pad}
  Density = 3000.0
End
Material 3
  {tens(K_FR4)}
  Density = 1900.0
End
Material 4
  {tens(K_Z12)}
  Density = 1900.0
End
Material 5
  {tens(K_Z9)}
  Density = 1900.0
End
Equation 1
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
        t0, dT = h["t_air"]; x0, x1 = G.fins()[2][0] / 1000.0, G.fins()[2][1] / 1000.0
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
        x0, x1, y0, y1 = c["rect"]; q = G.LOSS[load][c["type"]] / ((x1 - x0) * (y1 - y0) * 1e-6)
        s += f"Boundary Condition {3 + i}\n  Target Boundaries(1) = {INFO['chip_boundary'][c['id']]}\n  Heat Flux = {q}\nEnd\n"
    return s


def post(vtu, h):
    m = pv.read(vtu); sc = 1000.0 if m.bounds[1] < 5 else 1.0
    P = m.points * sc; T = m.point_data["temperature"]
    gid = m.cell_data["GeometryIds"]
    res = {"chips": {}}
    on_top = np.abs(P[:, 2] - G.Z_TOP) < 1e-4
    for c in INFO["chips"]:
        x0, x1, y0, y1 = c["rect"]
        sel = on_top & (P[:, 0] >= x0 - 1e-4) & (P[:, 0] <= x1 + 1e-4) & (P[:, 1] >= y0 - 1e-4) & (P[:, 1] <= y1 + 1e-4)
        tb = float(T[sel].max()); pw = G.LOSS_CUR[c["type"]]
        res["chips"][c["id"]] = dict(type=c["type"], board_max=tb, tj_est=tb + pw * G.RTHJC_MAX[c["type"]])
    sink = m.extract_cells(np.where(gid == 1)[0])
    ps = sink.points * sc
    res["sink_max"] = float(sink.point_data["temperature"].max())
    top = np.abs(ps[:, 2]) < 1e-4
    res["sink_field_mean"] = float(sink.point_data["temperature"][top].mean())
    # air-side faces: area-weighted mean T and heat out (energy balance)
    surf = sink.extract_surface(algorithm="dataset_surface").compute_cell_sizes(length=False, volume=False)
    surf = surf.point_data_to_cell_data(pass_point_data=True)
    cc = surf.cell_centers().points * sc; Ac = surf.cell_data["Area"] * (1e-6 if sc == 1.0 else 1.0); Tc = surf.cell_data["temperature"]
    field = cc[:, 2] <= -G.PLATE_T + 1e-3
    # energy balance from Elmer's own boundary integrals (SaveScalars): int T dA and area, BC 1 and 2
    v = [float(x) for x in open(vtu.replace(os.sep + "mesh" + os.sep, os.sep).rsplit("_t", 1)[0] + "_scalars.dat").read().split()]
    iT1, iT2, a1, a2 = v[:4]
    if h["t_air"]:
        t0, dT = h["t_air"]; x0, x1 = G.fins()[2][0], G.fins()[2][1]
        xbar = float((cc[field, 0] * Ac[field]).sum() / Ac[field].sum())   # Text is linear in x
        text = t0 + dT * (xbar - x0) / (x1 - x0)
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
    # ResultOutputSolve writes into the mesh folder
    vt = [f for f in os.listdir(md) if f.startswith(name + "_t") and f.endswith(".vtu")]
    return post(os.path.join(md, sorted(vt)[-1]), h)


CASES = {"passive_upper": C.passive_upper, "passive_lower": C.passive_lower, "fans": C.forced}
if G.VARIANT == "lowpro":   # fans: flat and wall the same (forced flow does not care); fan off: flat (envelope) and wall (vertical ducts)
    CASES = {"passive_lower": C.passive_lower, "passive_wall": C.passive_wall, "fans": C.forced}
loads = ["worst"] if QUICK else ["worst", "typical"]
cases = ["passive_upper"] if QUICK else list(CASES)
kpads = [3.0] if QUICK else [1.0, 3.0, 6.0]
out = {"K_XY": K_XY, "K_Z12": K_Z12, "K_Z9": K_Z9, "mesh": INFO["n_tets"], "runs": {}}
for load in loads:
    G.LOSS_CUR = G.LOSS[load]
    p_tot = sum(G.LOSS[load][c["type"]] for c in INFO["chips"])
    for cs in cases:
        ts = T_AMB + 30.0
        for it in range(8):
            fn = CASES[cs]
            h = fn(ts, T_AMB, A_FIELD, A_EDGE, p_tot) if cs == "fans" else fn(ts, T_AMB, A_FIELD, A_EDGE)
            r = solve(f"{load}_{cs}_k3", 3.0, load, h)
            print(load, cs, "iter", it, "h %.2f" % h["h_field"], "airside %.2f" % r["airside_mean"], flush=True)
            if abs(r["airside_mean"] - ts) < 0.3 or (cs == "fans" and it >= 1): break   # fan h does not depend on T_sink
            ts = 0.5 * (ts + r["airside_mean"])   # damped fixed point (plain update oscillates)
        for k in kpads:
            rr = r if k == 3.0 else solve(f"{load}_{cs}_k{k:g}", k, load, h)
            rr["h"] = {a: b for a, b in h.items() if not isinstance(b, tuple)}
            rr["p_total"] = p_tot
            out["runs"][f"{load}|{cs}|{k:g}"] = rr
            print(load, cs, k, "sink_max %.1f" % rr["sink_max"], "hottest %.1f" % max(v["board_max"] for v in rr["chips"].values()),
                  "q_out %.2f of %.2f" % (rr["q_out"], p_tot), flush=True)
json.dump(out, open(os.path.join(RUN, "results.json"), "w"), indent=1)
print("WROTE", os.path.join(RUN, "results.json"))
