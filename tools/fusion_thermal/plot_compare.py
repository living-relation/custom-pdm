"""Fusion vs board-model hot spots, one PNG per board (fusion2).

usage (repo root): python tools/fusion_thermal/plot_compare.py [docs/fusion-check/thermal-compare.json] [docs/diagrams]
Writes docs/diagrams/fusion-thermal-A.png, -B.png, -IN.png: per case a dot row per hot spot with three markers
(real copper model = the Elmer-chain reference, the same model on the Fusion "lite" board, Fusion), and prints the
Fusion - real and Fusion - lite differences.
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SERIES = [("our model, real copper (reference)", "#2a78d6", "o"),
          ("our model, Fusion's simplified board", "#eb6834", "s"),
          ("Fusion", "#1baf7a", "D")]
INK, MUTED, GRID = "#2b2b2a", "#6b6a64", "#e4e3de"


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "docs/fusion-check/thermal-compare.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "docs/diagrams"
    d = json.load(open(src))
    for board in ("A", "B", "IN"):
        cases = [c for c in d["cases"] if c["board"] == board]
        hs = [len(c["spots"]) for c in cases]
        fig, axes = plt.subplots(1, len(cases), figsize=(6.2 * len(cases), 0.42 * max(hs) + 1.9), squeeze=False)
        for ax, c in zip(axes[0], cases):
            names = [s[0] for s in c["spots"]][::-1]
            for k, (lab, col, mk) in enumerate(SERIES):
                xs = [s[1 + k] for s in c["spots"]][::-1]
                ys = [i + (k - 1) * 0.18 for i in range(len(names))]
                pts = [(x, y) for x, y in zip(xs, ys) if x is not None]
                if pts:
                    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=46, c=col, marker=mk, label=lab,
                               edgecolors="white", linewidths=1.2, zorder=3)
            for i, s in enumerate(c["spots"][::-1]):
                if s[3] is not None:
                    dv = s[3] - s[1]
                    ax.annotate(f"{dv:+.0f} K", (max(v for v in s[1:] if v is not None), i), xytext=(8, -4),
                                textcoords="offset points", fontsize=8, color=MUTED)
            ax.set_yticks(range(len(names)))
            ax.set_yticklabels(names, fontsize=9, color=INK)
            ax.set_xlabel("board-side temperature (C)", fontsize=9, color=MUTED)
            ax.set_title(c["label"], fontsize=10, color=INK, loc="left")
            ax.grid(axis="x", color=GRID, linewidth=0.8)
            ax.set_axisbelow(True)
            for sp in ("top", "right", "left"):
                ax.spines[sp].set_visible(False)
            ax.spines["bottom"].set_color(GRID)
            ax.tick_params(colors=MUTED, length=0)
            lo = min(v for s in c["spots"] for v in s[1:] if v is not None)
            hi = max(v for s in c["spots"] for v in s[1:] if v is not None)
            ax.set_xlim(lo - 3, hi + 8)
            print(f"{board} {c['case']}: " + "; ".join(
                f"{s[0]} F-real {s[3] - s[1]:+.1f}" + (f" F-lite {s[3] - s[2]:+.1f}" if s[2] is not None else "")
                for s in c["spots"] if s[3] is not None))
        h, lab = axes[0][0].get_legend_handles_labels()
        fig.legend(h, lab, loc="lower center", ncol=3, frameon=False, fontsize=9)
        fig.text(0.01, 0.995, "label = Fusion minus real-copper model", fontsize=8, color=MUTED, va="top")
        fig.tight_layout(rect=(0, 0.07, 1, 0.97))
        p = os.path.join(out, f"fusion-thermal-{board}.png")
        fig.savefig(p, dpi=130, facecolor="#fcfcfb")
        plt.close(fig)
        print("wrote", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
