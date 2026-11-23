"""Write sim/heat/loads_revF.json: the heat inputs of the whole-box Elmer model (HEAT_GEOM=revF) from the board models.

usage (any python 3, repo root):
    python sim/heat/make_loads.py <board A JSON> <board B JSON>
      board A JSON: tools/thermal_a.py --air fans --case rating feed150a car --json ...
      board B JSON: tools/thermal_board_b.py --air fans --res 0.3 --case feed150 car rating --json ...

Per load case: every driver's loss (W) by chip id (B-U8, A1-U8, A2-U8, ...; sim/heat/geometry.py chips()), each board's
other heat (copper I2R + bolted joints + 5 V module; for board B also the bars / joints / contacts estimate of
docs/heat-analysis.md 3, 3.2 W x (I / 150 A)^2, as thermal_board_b p_ext) spread over its slab, and the heat that goes
into the lid air (X1 / X2 contacts + internal harness, tools/verify_thermal_box.py contacts_harness, for the lid-air node).
Loads:
  rating    every output at its rating (304 A; above the 150 A feed limit: upper bound, INFO)
  feed150   150 A on board B (thermal_board_b feed150), A boards idle (5 V module only): the hottest board B case
  feed150a  both A boards at rating (120 A) + 30 A on B: the hottest board A case the feed limit allows
  car       docs/car-loads.dummy.md loads (B 118.1 A, A1 20.35 A, A2 3.53 A)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
P_5V = 0.2          # tools/thermal_board_b.py P_5V (ASSUMED)


def contacts_harness(a1, a2, b15):
    """X1 / X2 contacts + internal harness into the lid air, W (tools/verify_thermal_box.py contacts_harness values:
    size 16 at 2 mOhm + 16 AWG 3.3 mOhm per A output, size 12 at 1 mOhm + 12 AWG 0.78 mOhm per board B OUT5-8;
    OUT1-4 leave on their own lugs)."""
    return sum(i * i * (2e-3 + 3.3e-3) for i in list(a1) + list(a2)) + sum(i * i * (1e-3 + 0.78e-3) for i in b15)


def main():
    a = {r["case"]: r for r in json.load(open(sys.argv[1]))}
    b = {r["case"]: r for r in json.load(open(sys.argv[2]))}
    for r in list(a.values()) + list(b.values()):
        if r.get("ordered") is not True or r.get("air") != "fans":
            raise SystemExit(f"{r['case']}: not an ordered-copper fans-on run")
    out = {"_source": f"sim/heat/make_loads.py from {os.path.basename(sys.argv[1])}, {os.path.basename(sys.argv[2])}"}

    def b_part(rb, scale=1.0):
        chips = {f"B-{c['ref']}": c["P"] * scale ** 2 for c in rb["chips"]}
        i_b = rb["I_B"] * scale
        return chips, (rb["p_copper"] + rb["p_joints"] - P_5V) * scale ** 2 + P_5V, i_b, \
            [c["I"] * scale for c in rb["chips"] if c["type"] == "BTS7004"]

    def a_part(ra):
        chips = {f"A1-{c['ref']}": c["P"] for c in ra["chips"]}
        chips.update({f"A2-{c['ref']}": c["P"] for c in ra["chips_other_a"]})
        return chips, ra["p_copper"] + ra["p_joints"], ra["p_copper_other_a"] + P_5V

    def case(chips, w_b, w_a1, w_a2, i_tot, a1, a2, b15, air, sens=False):
        return dict(chips={k: round(v, 4) for k, v in chips.items()},
                    board_w=dict(B=round(w_b + 3.2 * (i_tot / 150.0) ** 2, 4), A1=round(w_a1, 4), A2=round(w_a2, 4)),
                    lid_air_w=round(contacts_harness(a1, a2, b15), 3), I_total=round(i_tot, 1), air=air,
                    pad_sensitivity=sens)

    # A currents per output (thermal_a.case_currents): from the chips' I0 / I1 is not in the JSON; use the case
    A_CUR = {"rating": ([7.5] * 8, [7.5] * 8), "feed150a": ([7.5] * 8, [7.5] * 8),
             "car": ([2.0, 2.5, 0.5, 0.2, 5.0, 0.15, 5.0, 5.0], [0.2, 0.13, 0.2, 3.0, 0, 0, 0, 0])}
    # rating
    cb, wb, ib, b15 = b_part(b["rating"])
    ca, wa1, wa2 = a_part(a["rating"])
    out["rating"] = case({**cb, **ca}, wb, wa1, wa2, ib + 120.0, *A_CUR["rating"], b15, ["fans"])
    # feed150: B only
    cb, wb, ib, b15 = b_part(b["feed150"])
    out["feed150"] = case(cb, wb, P_5V, P_5V, ib, [0] * 8, [0] * 8, b15, ["fans", "passive_upper", "passive_lower"],
                          sens=True)
    # feed150a: A boards at rating + B 30 A (B's rating case scaled by 30 / 184)
    cb, wb, ib, b15 = b_part(b["rating"], 30.0 / 184.0)
    ca, wa1, wa2 = a_part(a["feed150a"])
    out["feed150a"] = case({**cb, **ca}, wb, wa1, wa2, ib + 120.0, *A_CUR["feed150a"], b15, ["fans"])
    # car
    cb, wb, ib, b15 = b_part(b["car"])
    ca, wa1, wa2 = a_part(a["car"])
    out["car"] = case({**cb, **ca}, wb, wa1, wa2, ib + a["car"]["I_A1"] + a["car"]["I_A2"], *A_CUR["car"], b15,
                      ["fans", "passive_upper", "passive_lower"])
    for k, v in out.items():
        if not k.startswith("_"):
            print(f"{k:9} chips {sum(v['chips'].values()):5.1f} W + boards {sum(v['board_w'].values()):5.1f} W "
                  f"({v['board_w']}) ; lid air {v['lid_air_w']} W; {v['I_total']} A")
    json.dump(out, open(os.path.join(HERE, "loads_revF.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
