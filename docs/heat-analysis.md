# Heat analysis - boards on the base-plate sink (STATE "Next" item 2)

Status: first steady-state model, 2026-11-11, branch `feat/heat-analysis`. Results, not decisions.
Tool: Elmer 26.2 (HeatSolve), Gmsh 4.14, WSL Ubuntu, handbuilt-cad sim stack (`sim-stack` skill). No Fusion.
Marks: **ASSUMED** = my modelling choice, **TBD** = not confirmed (product or fab not chosen).

## 1. Answer in short

- **Passive (no fans) does not meet the targets at worst case.** Even the optimistic natural-convection number puts the sink at about 90 C (target 85 fails, 95 passes); the conservative one puts it at 136 C (fails 105), and junctions go over 150 C.
- **With the two 30 mm fans the sink sits at about 71 C (max 75 C): meets the 85 C target at worst case**, and every junction stays under 150 C for any pad k from 1 to 6 W/mK (k = 1 leaves only 5 K).
- **The weak link is not the sink, it is the path through the board.** With fans, the sink is 71-75 C but the BTS70012 spots on board B reach about 119 C (k = 3). Of those ~45 K, the gap pad takes about 10 K (k = 3) and the board about 35 K: the 9 plain 0.4 mm vias under each BTS70012 pad are the bottleneck (hand check: about 21 K/W for 9 barrels with 20 um plating, x 2.37 W).
- **Fan temperature flag:** the fans pull air, so they sit in the exhaust. Worst-case exhaust is about 74 C; the Sunon fan is rated -10 to +70 C (spec D03033580G-01). At typical load it is about 68 C. Pushing instead of pulling would keep them at cabin air (60 C).
- Pad k matters a lot for junctions (about 20 K from k = 1 to 3, 6 K more to k = 6) and not at all for the sink.

## 2. Results (mesh m2, 829k tetrahedra; per-chip losses from `docs/enclosure-layout.md` 4.3)

Sink base = mean of the mesh nodes on the plate top (Z = 0) / sink max (on the pedestal tops). Sink targets 85 / 95 / 105 C are from `docs/enclosure-layout.md` 4.3. Tj est. = hottest board-top point under the chip's exposed pad + chip loss x RthJC max (data sheet). Limit Tj 150 C (data sheets, all three parts).

| Load | Air case | Pad k (W/mK) | h on fins (W/m2K) | Sink base mean / max (C) | Sink target | Hottest chip, board top (C) | Tj est. (C) | Tj <= 150 |
|---|---|---|---|---|---|---|---|---|
| worst 31.1 W | 1a passive, optimistic | 1 | 3.5 | 89.7 / 92.0 | 95 PASS, 85 FAIL | B-U11 BTS70012 160.6 | 162 | FAIL |
| worst | 1a passive, optimistic | 3 | 3.5 | 89.7 / 92.1 | 95 PASS, 85 FAIL | B-U11 140.4 | 142 | PASS (+8 K) |
| worst | 1a passive, optimistic | 6 | 3.5 | 89.7 / 92.2 | 95 PASS, 85 FAIL | B-U11 134.6 | 136 | PASS (+14 K) |
| worst | 1b passive, conservative | 1 | 1.4 | 136.0 / 138.3 | FAIL 105 | B-U11 206.9 | 209 | FAIL |
| worst | 1b passive, conservative | 3 | 1.4 | 136.0 / 138.4 | FAIL 105 | B-U11 186.7 | 188 | FAIL |
| worst | 1b passive, conservative | 6 | 1.4 | 136.0 / 138.5 | FAIL 105 | B-U11 180.9 | 183 | FAIL |
| worst | 2 two fans | 1 | 28.6 | 70.9 / 74.5 | 85 PASS | A2-U10 BTS7008 142.3 | 145 | PASS (+5 K) |
| worst | 2 two fans | 3 | 28.6 | 70.9 / 74.6 | 85 PASS | B-U11 BTS70012 119.3 | 121 | PASS (+29 K) |
| worst | 2 two fans | 6 | 28.6 | 70.9 / 74.7 | 85 PASS | B-U11 113.5 | 115 | PASS (+35 K) |
| typical 17.4 W | 1a passive, optimistic | 1 / 3 / 6 | 2.7 | 81.4 / 82.8 | 85 PASS | B-U11 121.6 / 110.2 / 106.9 | 123 / 111 / 108 | PASS |
| typical | 1b passive, conservative | 1 / 3 / 6 | 1.2 | 107.3 / 108.7 | FAIL 105 | B-U11 147.5 / 136.1 / 132.8 | 149 / 137 / 134 | PASS (k = 1: +2 K only) |
| typical | 2 two fans | 1 / 3 / 6 | 28.6 | 66.1 / 68.2 | 85 PASS | 106.3 (A2-U10) / 93.6 / 90.3 | 108 / 95 / 91 | PASS |

Per chip, worst case, k = 3 (board top / Tj est., C):

| Chips | W each | 1a passive | 1b passive | 2 fans |
|---|---|---|---|---|
| B: BTS70012 U8-U11 | 2.37 | 139-140 / 141-142 | 186-187 / 187-188 | 119 / 120-121 |
| B: BTS7004 U23-U26 | 1.80 | 125-127 / 129-132 | 171-174 / 175-178 | 105-107 / 109-112 |
| A1: BTS7008 U8, U10, U11, U13 | 1.80 | 131-132 / 134-135 | 177-178 / 180-181 | 113-114 / 116 |
| A2: BTS7008 U8, U10, U11, U13 | 1.80 | 131-132 / 133-134 | 177-178 / 180-181 | 114-115 / 117-118 |

Plots: `docs/diagrams/heat-hottest-junction.png` (hottest Tj per case and pad k), `docs/diagrams/heat-board-top-fans.png` (board-top map, fans, k = 3).

Checks:
- Energy balance: heat out through the air-side faces = heat in (31.08 W, 17.44 W) within 0.01 W in every run (Elmer boundary integrals).
- Linear solver (CG + ILU0) converged to 1e-10 relative residual in every run.
- Mesh: hottest chip, worst case 1a k = 3: 138.0 C (m1, 246k tets), 140.4 C (m2, 829k), 141.6 C (m3, 2.33M). Steps halve, so m2 reads about 2-3 K low on chip spots; sink temperatures change by less than 0.2 K. Case 1b on m3: 188.0 / 182.0 C (k 3 / 6), m2 186.7 / 180.9. The peak is at the middle of a uniform-flux pad, not a corner or a fixed node, so it is not a singularity.

## 3. Model

Geometry follows Grok's TEST 2 pack (read-only copy; `handoff/HANDOFF.md` sections 3-4, `test2/src/build_test2.py`), variant b sink (no J3 pocket), same world frame:

| Part | Model | Source |
|---|---|---|
| Sink plate | 280.17 x 119.25 x 8 mm, aluminium, no corner radii, holes, bosses or feet (simplified) | pack, variant b |
| Fins | 17 fins down, 30 deep x 2 thick, 6 pitch (4 mm gaps), east-west, about 244 mm long | pack |
| Pedestals | 3 mm high, footprint = bottom-mask window hull + 1.5 mm: 2 per A board, 3 on B (two BTS70012 pairs, one BTS7004 rail) | pack / `docs/enclosure-layout.md` 4.2 |
| Gap pad | 1 mm, only on the pedestals, k = 1 / 3 / 6 W/mK, isotropic. Product TBD | task |
| Boards | B, A1, A2 side by side, 2 mm gaps, 1.77 mm thick, bottom at Z 4.0 | pack, KiCad board setup |
| Heat input | each chip's loss as a uniform flux on its exposed-pad (EP) outline on the board top | losses from `docs/enclosure-layout.md` 4.3 |

**Board = one equivalent layered slab (simplification).** Real copper patterns are not modelled:
- In-plane k = 13.4 W/mK: 4 copper layers (43.18 / 17.27 / 17.27 / 43.18 um, board stackup) at **50 % average coverage (ASSUMED)**, rest FR4.
- Through-plane k = 0.30 W/mK (FR4, **ASSUMED** handbook value), except under each EP: a "via patch" the size of the EP with the vias counted in the board files (0.8 / 0.4 mm vias): 12 under each BTS7008 and BTS7004 EP (4.00 x 2.65 mm) -> k_z 10.7 W/mK; 9 under each BTS70012 EP (6.40 x 2.77 mm) -> k_z 4.96 W/mK. Via plating **20 um ASSUMED** (fab TBD), vias unfilled.
- So the model spreads heat through the whole board thickness instead of mainly the top copper, and ignores solder mask between the board and the pad outside the bare windows (slightly optimistic), and pad contact resistance (optimistic).

**Left out (all make the result conservative):** heat into wires, terminals and connectors; heat from the board top and the lid; radiation (sink finish TBD; black anodising could add roughly 0.5 W/K to case 1b); conduction through the M3 bosses and screws. The plate top inside the lid is adiabatic.

**Materials:** aluminium k = 167 W/mK (6061-T6 handbook value; alloy ASSUMED, 6063 would be better). Air properties: Incropera & DeWitt, Table A.4, at film temperature.

**Data-sheet values used (read 2026-11-11, Infineon, Table 6 / Table 5):** RthJC max (simulated at the exposed pad) BTS7008-2EPA 1.4 K/W, BTS70012-1ESP 0.7 K/W, BTS7004-1EPP 2.4 K/W; Tj max 150 C for all three. Links in `docs/enclosure-layout.md` 4.3.

### Air side (all at 60 C cabin air)
h depends on the sink temperature, so it is iterated (damped) at k = 3 until the mean air-side temperature moves less than 0.3 K; k = 1 and 6 reuse that h.

| Case | Faces | h | Correlation and inputs |
|---|---|---|---|
| 1a passive, optimistic | fins + plate underside | 3.5 W/m2K (worst), 2.7 (typical) | Elenbaas (1942) isothermal vertical parallel plates, Nu_S = Ra*/24 [1 - exp(-35/Ra*)]^0.75 (Bar-Cohen & Rohsenow 1984), S = 4 mm, L = 30 mm. Optimistic: it assumes channels open top and bottom, but here the plate closes the top of every channel (fins down). |
|  | plate outer edges | about 7 W/m2K | Churchill & Chu, vertical plate, L = 38 mm |
| 1b passive, conservative | all air-side faces | 1.4 W/m2K (worst), 1.2 (typical) | Envelope method: the finned block counts only as its outer box. Bottom 280 x 119 mm = hot plate facing down, Nu = 0.27 Ra^1/4 (Incropera eq. 9.32, L = area / perimeter); four sides = Churchill & Chu, L = 38 mm. Total hA spread evenly over the meshed faces (sink is near isothermal). |
| 2 two fans | fins + plate underside | 28.6 W/m2K | Laminar, simultaneously developing flow between parallel plates, mean Nu, Stephan correlation (Shah & London 1978): Nu = 7.84 at Re 444, x* 0.098, Dh = 8 mm. Air temperature rises linearly along the fins from 60 C (west inlet) to 74.2 C (worst) / 68.0 C (typical) at the fans (all the heat goes into the fan air). |
|  | plate outer edges | 6.6 W/m2K | natural, as 1a |

Fan flow (case 2): 2 x Sunon MF30101V1-1000U-A99 in parallel, 5.5 CFM and 0.25 inH2O each (spec D03033580G-01, in the pack). The P-Q curve on spec page 5 is a picture only, so a **straight-line fan curve is ASSUMED**. Against the 16 channels (laminar friction, f Re = 96, plus entry and exit K = 1.5, **ASSUMED**) the operating point is 8.9 CFM of 11 CFM free air. **Only half of it is ASSUMED to pass through the fin channels** (open fin tips, pod leakage): 4.45 CFM, 1.09 m/s in the channels.

## 4. What is TBD or ASSUMED (affects the numbers)
- Gap pad product (k, real thickness after compression, contact resistance): TBD. Run covers k 1-6.
- Via plating thickness and whether vias are filled: TBD (fab). Filled or more vias under the BTS70012 pads would cut the biggest resistance in the chain.
- Copper coverage per layer (50 % ASSUMED); FR4 k (0.30 ASSUMED); aluminium alloy (6061 ASSUMED).
- Fan curve shape (straight line ASSUMED), bypass share (50 % ASSUMED), fan placement (pull, as in the pack).
- Natural convection of a fins-down sink: no correlation fits it well; 1a and 1b bracket it. A bench test of the real sink would settle it.
- Radiation and sink surface finish: TBD (left out).
- The 31.1 W worst case is itself an upper bound (every channel at rated current = 304 A, twice the 150 A feed).

## 5. Re-run

Scripts: `sim/heat/` (`geometry.py` stack and chip data, `mesh_heat.py` Gmsh model, `convection.py` h correlations, `run_cases.py` Elmer cases + post, `make_report.py` tables + plots, `example_worst_fans_k3.sif` one generated Elmer input). In WSL, from the repo checkout:

```bash
python3 -I sim/heat/mesh_heat.py ~/scratch/heat/runs/m2 0.6            # system python3 (gmsh module); 0.6 = mesh size factor
~/.venvs/handbuilt-cad/bin/python -I sim/heat/run_cases.py ~/scratch/heat/runs/m2        # all 18 cases, about 15 min
~/.venvs/handbuilt-cad/bin/python -I sim/heat/make_report.py ~/scratch/heat/runs/m2 docs/diagrams
```

`run_cases.py` is resumable (finished identical cases are only re-read). Add `quick` to run one case (worst, 1a, k = 3).
Meshes and results are not in git. WSL scratch on DansPC: `/home/daniel/scratch/heat/` (`runs/m1` 246k tets, `runs/m2` 829k tets = reported, `runs/m3` 2.33M tets = mesh check, partial; `pack/` = extracted copy of the TEST 2 pack).
