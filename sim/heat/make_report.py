"""Turn results.json into the markdown tables and the two PNGs used in docs/heat-analysis.md.

Usage (WSL, sim venv python): python make_report.py <run_dir> <png_dir>
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pyvista as pv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as G
import convection as C

RUN, PNG = sys.argv[1], sys.argv[2]
R = json.load(open(os.path.join(RUN, "results.json")))
NAMES = {"passive_upper": "1a passive, Elenbaas (optimistic)", "passive_lower": "1b passive, envelope (conservative)",
         "fans": "2 two 30 mm fans"}
TIERS = (85.0, 95.0, 105.0)


def tier(t):
    for x in TIERS:
        if t <= x: return f"meets {x:.0f}"
    return "fails 105"


print("K_XY %.2f K_Z12 %.2f K_Z9 %.2f tets %d" % (R["K_XY"], R["K_Z12"], R["K_Z9"], R["mesh"]))
print("\n| Load | Air case | Pad k | h fins (W/m2K) | Sink base mean / max (C) | Sink vs 85/95/105 | Hottest chip (board top) | Tj est. (C) | Tj <= 150 |")
print("|---|---|---|---|---|---|---|---|---|")
for key, r in R["runs"].items():
    load, cs, k = key.split("|")
    hot = max(r["chips"].items(), key=lambda kv: kv[1]["tj_est"])
    tj = hot[1]["tj_est"]
    print(f"| {load} | {NAMES[cs]} | {k} | {r['h']['h_field']:.1f} | {r['sink_field_mean']:.1f} / {r['sink_max']:.1f} | "
          f"{tier(r['sink_field_mean'])} | {hot[0]} {hot[1]['type']} {hot[1]['board_max']:.1f} | {tj:.1f} | "
          f"{'PASS' if tj <= 150 else 'FAIL'} ({150 - tj:+.0f} K) |")

# per-chip table, worst load, k = 3
print("\n| Chip | Type | W | " + " | ".join(f"{NAMES[c].split(',')[0]} board / Tj" for c in NAMES) + " |")
print("|---|---|---|" + "---|" * len(NAMES))
for cid in R["runs"]["worst|fans|3"]["chips"]:
    t = R["runs"]["worst|fans|3"]["chips"][cid]["type"]
    cells = [f"{R['runs'][f'worst|{c}|3']['chips'][cid]['board_max']:.0f} / {R['runs'][f'worst|{c}|3']['chips'][cid]['tj_est']:.0f}" for c in NAMES]
    print(f"| {cid} | {t} | {G.LOSS['worst'][t]:.2f} | " + " | ".join(cells) + " |")

f = R["runs"]["worst|fans|3"]["h"]
print("\nfan:", {k: (round(v, 5) if isinstance(v, float) else v) for k, v in f.items()})
q, A = C.fan_point(65.0)
print("fan operating point (no bypass) %.2f CFM of %.1f free, channel area %.0f mm2" % (q / 0.000471947, C.Q_FREE / 0.000471947, A * 1e6))

# plot 1: hottest Tj per case and pad k, worst load
fig, ax = plt.subplots(figsize=(7.5, 3.6), dpi=110)
ks = ["1", "3", "6"]; w = 0.25
for i, cs in enumerate(NAMES):
    vals = [max(v["tj_est"] for v in R["runs"][f"worst|{cs}|{k}"]["chips"].values()) for k in ks]
    b = ax.bar(np.arange(3) + (i - 1) * w, vals, w, label=NAMES[cs])
    ax.bar_label(b, fmt="%.0f", fontsize=7)
ax.axhline(150, color="k", lw=1, ls="--"); ax.text(2.45, 151, "Tj max 150 C", ha="right", va="bottom", fontsize=7)
ax.set_xticks(range(3), [f"gap pad k = {k} W/mK" for k in ks]); ax.set_ylabel("hottest junction, est. (C)")
ax.set_title("Worst case 31.1 W, 60 C air: hottest driver junction", fontsize=9); ax.legend(fontsize=7, loc="upper right")
ax.set_ylim(60, 220); ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(PNG, "heat-hottest-junction.png")); plt.close(fig)

# plot 2: board-top temperature map, worst load, fans, k = 3
vt = sorted(x for x in os.listdir(os.path.join(RUN, "mesh")) if x.startswith("worst_fans_k3_t"))[-1]
m = pv.read(os.path.join(RUN, "mesh", vt)); sc = 1000.0 if m.bounds[1] < 5 else 1.0
P = m.points * sc; T = np.asarray(m.point_data["temperature"]); s = np.abs(P[:, 2] - G.Z_TOP) < 1e-4
fig, ax = plt.subplots(figsize=(7.5, 3.2), dpi=110)
tc = ax.tricontourf(P[s, 0], P[s, 1], T[s], levels=24, cmap="inferno")
for n in ("B", "A1", "A2"):
    ax.add_patch(plt.Rectangle((G.X0[n], -G.BOARD_D), G.BOARD_W[n], G.BOARD_D, fill=False, lw=0.8, ec="w"))
    ax.text(G.X0[n] + 3, -8, n, color="w", fontsize=8)
fig.colorbar(tc, ax=ax, label="board top (C)"); ax.set_aspect("equal"); ax.set_xlabel("X (mm)"); ax.set_ylabel("Y (mm)")
ax.set_title("Board top, worst case 31.1 W, two fans, gap pad k = 3 W/mK", fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(PNG, "heat-board-top-fans.png")); plt.close(fig)
print("PNGs written")
