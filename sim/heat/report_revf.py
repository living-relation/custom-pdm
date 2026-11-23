"""Whole-box (assembly) report for HEAT_GEOM=revF: tables, the lid-air node, R_sys for the board models, heat maps.

Usage (WSL, sim venv python): HEAT_GEOM=revF python report_revf.py <run_dir> <png_dir> [<m1 run> <m3 run>]
Reads <run_dir>/results.json (run_cases.py) and sim/heat/loads_revF.json; optional coarser / finer runs for the mesh check.
Lid air: one node as tools/verify_thermal_box.py (lid 0.12 m2 x 1.8 W/m2K to the cabin, open sink top 0.010 m2 x 3,
board tops 0.024 m2 x 3; heat in = X1 / X2 contacts + harness (loads_revF lid_air_w) +
3 input boards at their worst-case own loss (tools/thermal_input.py, 0.49 W each) + USB hub 0.1 W ASSUMED; board tops
taken at the sink mean + 15 K, as verify_thermal_box DT_BOARD_A). DIP switch
= lid air + the input board's own DIP rise (thermal_input.py, 4.9 K at h 9). All ASSUMED as in those tools.
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pyvista as pv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as G

RUN, PNG = sys.argv[1], sys.argv[2]
EXTRA = sys.argv[3:]
R = json.load(open(os.path.join(RUN, "results.json")))
L = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "loads_revF.json")))
T_CAB = 60.0
G_LID, G_SINK_AIR, G_BOARD_AIR = 0.12 * 1.8, 0.010 * 3.0, 0.024 * 3.0
P_INPUT, P_HUB, DIP_RISE = 3 * 0.488, 0.1, 4.9
NAMES = {"fans": "fans on", "passive_upper": "fans off, wall (fins vertical)", "passive_lower": "fans off, flat (fins down)"}


def lid_air(r, load):
    tb = r["sink_field_mean"] + 15.0     # board tops = sink + 15 K (ASSUMED, verify_thermal_box DT_BOARD_A; the slab boards
    #                                      here spread their copper heat evenly and read too hot away from the pedestals)
    p = L[load]["lid_air_w"] + P_INPUT + P_HUB
    return (p + G_LID * T_CAB + G_SINK_AIR * r["sink_max"] + G_BOARD_AIR * tb) / (G_LID + G_SINK_AIR + G_BOARD_AIR)


def pedestal_max(key):
    """hottest pedestal top (Z = PED_H) under each board: the gap-pad cold side the board models need (C)."""
    load, cs, k = key.split("|")
    vt = sorted(x for x in os.listdir(os.path.join(RUN, "mesh")) if x.startswith(f"{load}_{cs}_k{k}_t"))[-1]
    m = pv.read(os.path.join(RUN, "mesh", vt)); sc = 1000.0 if m.bounds[1] < 5 else 1.0
    gid = np.asarray(m.cell_data["GeometryIds"])
    sink = m.extract_cells(np.where(gid == 1)[0]); ps = sink.points * sc; ts = np.asarray(sink.point_data["temperature"])
    top = np.abs(ps[:, 2] - G.PED_H) < 1e-3
    out = {}
    for n in ("B", "A1", "A2"):
        s = top & (ps[:, 0] >= G.X0[n]) & (ps[:, 0] <= G.X0[n] + G.BOARD_W[n])
        out[n] = float(ts[s].max())
    # the east end of the fins, where the 6 mm fan wall (not modelled) carries the two fans: the fans' frame temperature
    out["fan_end"] = float(ts[ps[:, 0] >= G.fin_span()[1] - 3.0].max())
    return out


for key in R["runs"]:
    R["runs"][key]["ped_max"] = pedestal_max(key)
print("K_XY %.2f K_Z12 %.2f K_Z9 %.2f tets %d" % (R["K_XY"], R["K_Z12"], R["K_Z9"], R["mesh"]))
print("\nPedestal-top max under each board (C) and R_sys per board = (that - 60 C) / box heat (K/W):")
for key, r in R["runs"].items():
    print(f"  {key}: " + ", ".join(f"{n} {t:.1f} ({(t - T_CAB) / r['p_total']:.3f})" for n, t in r["ped_max"].items()))
print("\n| Load | Air | Pad k | Box heat (W) | Sink mean / max (C) | R_sys (K/W) | Lid air (C) | DIP switch (C) | Hottest chip, "
      "board top / Tj est. (C) (slab model) | Slab board tops max B / A1 / A2 (C) (indicative) |")
print("|---|---|---|---|---|---|---|---|---|---|")
rsys = {}
for key, r in R["runs"].items():
    load, cs, k = key.split("|")
    hot = max(r["chips"].items(), key=lambda kv: kv[1]["tj_est"])
    la = lid_air(r, load)
    rs = (r["sink_max"] - T_CAB) / r["p_total"]
    rsys[key] = rs
    r["lid_air"], r["dip"], r["r_sys"] = la, la + DIP_RISE, rs
    print(f"| {load} | {NAMES[cs]} | {k} | {r['p_total']:.1f} | {r['sink_field_mean']:.1f} / {r['sink_max']:.1f} | {rs:.3f} | "
          f"{la:.1f} | {la + DIP_RISE:.1f} | {hot[0]} {hot[1]['board_max']:.1f} / {hot[1]['tj_est']:.1f} | "
          + " / ".join(f"{r['boards'][n]['top_max']:.1f}" for n in ("B", "A1", "A2")) + " |")
print("\nenergy balance:", {k: round(r["q_out"] - r["p_total"], 3) for k, r in R["runs"].items()})
for key in R["runs"]:
    if key.endswith("|3"):
        print("h", key, {a: (round(b, 4) if isinstance(b, float) else b) for a, b in R["runs"][key]["h"].items()})
json.dump({k: dict(r_sys=v, lid_air=R["runs"][k]["lid_air"], dip=R["runs"][k]["dip"], ped_max=R["runs"][k]["ped_max"],
                   r_sys_board={n: (t - T_CAB) / R["runs"][k]["p_total"] for n, t in R["runs"][k]["ped_max"].items()},
                   sink_max=R["runs"][k]["sink_max"], p_total=R["runs"][k]["p_total"],
                   boards=R["runs"][k]["boards"], hottest=max(R["runs"][k]["chips"].items(), key=lambda kv: kv[1]["tj_est"]))
           for k, v in rsys.items()},
          open(os.path.join(RUN, "summary_revf.json"), "w"), indent=1)
# mesh check
for d in EXTRA:
    Q = json.load(open(os.path.join(d, "results.json")))
    for key in ("feed150|fans|3", "feed150|passive_upper|3"):
        if key in Q["runs"] and key in R["runs"]:
            a, b = Q["runs"][key], R["runs"][key]
            ha = max(v["board_max"] for v in a["chips"].values()); hb = max(v["board_max"] for v in b["chips"].values())
            print(f"mesh {Q['mesh']} vs {R['mesh']} {key}: sink max {a['sink_max']:.2f} / {b['sink_max']:.2f}, "
                  f"hottest chip {ha:.2f} / {hb:.2f}")


def board_map(key, fname, title):
    load, cs, k = key.split("|")
    vt = sorted(x for x in os.listdir(os.path.join(RUN, "mesh")) if x.startswith(f"{load}_{cs}_k{k}_t"))[-1]
    m = pv.read(os.path.join(RUN, "mesh", vt)); sc = 1000.0 if m.bounds[1] < 5 else 1.0
    P = m.points * sc; T = np.asarray(m.point_data["temperature"]); s = np.abs(P[:, 2] - G.Z_TOP) < 1e-4
    gid = np.asarray(m.cell_data["GeometryIds"])
    sink = m.extract_cells(np.where(gid == 1)[0]); ps = sink.points * sc; ts = np.asarray(sink.point_data["temperature"])
    bot = np.abs(ps[:, 2] + G.PLATE_T + G.FIN_H) < 1e-3
    # top panel: the sink's top (plate field Z 0 + pedestal tops): what the gap pads and the board models sit on. The
    # board slabs of this model carry their copper heat spread evenly (no real copper), so their own top temperature is
    # not shown here: board temperatures come from tools/thermal_a.py / thermal_board_b.py
    stop = (np.abs(ps[:, 2]) < 1e-3) | (np.abs(ps[:, 2] - G.PED_H) < 1e-3)
    fig, ax = plt.subplots(2, 1, figsize=(9, 7.6), dpi=110)
    tc = ax[0].tricontourf(ps[stop, 0], ps[stop, 1], ts[stop], levels=24, cmap="inferno")
    for n in ("B", "A1", "A2"):
        ax[0].add_patch(plt.Rectangle((G.X0[n], -G.BOARD_D), G.BOARD_W[n], G.BOARD_D, fill=False, lw=0.8, ec="w"))
        ax[0].text(G.X0[n] + 3, -8, n, color="w", fontsize=8)
    for cid, c in R["runs"][key]["chips"].items():
        x0, x1, y0, y1 = next(ch["rect"] for ch in json.load(open(os.path.join(RUN, "groups.json")))["chips"] if ch["id"] == cid)
        ax[0].add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=0.5, ec="c"))
    for (x0, x1, y0, y1) in G.pedestals():
        ax[0].add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=0.6, ec="w", ls="--"))
    fig.colorbar(tc, ax=ax[0], label="sink top: plate + pedestals (C)"); ax[0].set_aspect("equal"); ax[0].set_ylabel("Y (mm)")
    ax[0].set_title(title, fontsize=9)
    tc2 = ax[1].tricontourf(ps[bot, 0], ps[bot, 1], ts[bot], levels=24, cmap="viridis")
    fig.colorbar(tc2, ax=ax[1], label="fin tips (C)"); ax[1].set_aspect("equal")
    ax[1].set_xlabel("X (mm, east ->; fans at the east end push west)" if G.AIR_IN_EAST else "X (mm)"); ax[1].set_ylabel("Y (mm)")
    ax[1].set_title("heat sink, fin tips (looking down through the box)", fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(PNG, fname)); plt.close(fig)


os.makedirs(PNG, exist_ok=True)
for key, fname in (("feed150|fans|3", "heat-revF-box-fans-feed150.png"), ("feed150a|fans|3", "heat-revF-box-fans-feed150a.png"),
                   ("feed150|passive_upper|3", "heat-revF-box-fansoff-wall-feed150.png")):
    if key in R["runs"]:
        r = R["runs"][key]; hot = max(r["chips"].items(), key=lambda kv: kv[1]["tj_est"])
        load, cs, _ = key.split("|")
        board_map(key, fname, f"revF box, {load} ({L[load]['I_total']:.0f} A, {r['p_total']:.1f} W), {NAMES[cs]}, TGP 3000 k 3, "
                  f"60 C cabin\nsink max {r['sink_max']:.1f} C; pedestal tops max B / A1 / A2 " +
                  " / ".join(f"{r['ped_max'][n]:.1f}" for n in ("B", "A1", "A2")) + f" C; lid air {r['lid_air']:.1f} C")
print("PNGs written")
