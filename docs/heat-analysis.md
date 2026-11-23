# Heat analysis - the current design (enclosure revF, boards with the 5 V module, 1 oz inner copper)

Status: re-run 2026-11-23 (job thermal3, branch `feat/thermal-current`) on the current geometry. Results, not decisions.
The 2026-11-11 / 11-12 results (older v2b sink, fans pulling, no copper heat) are kept at the end as history (section 8).
Tools: Elmer 26.2 + Gmsh 4.14 in WSL (whole box), finite-volume board models on the real KiCad copper (KiCad 9 python).
Marks: **ASSUMED** = my modelling choice, **TBD** = not confirmed. All at a 60 C cabin.

Order of work (Dan, 2026-11-23): each board alone first (A, B, input board: sink, fans on, TGP 3000 pad), then the whole
assembly.

## 1. Answer in short

| Board / item | Worst case the firmware allows (fans on) | Limit | Verdict |
|---|---|---|---|
| Board A alone (A1 at 60 A, `feed150a`) | Tj 119.7 C (U13), laminate 117.2 C, MCU board 89.3 C, FRAM board 93.7 C, 5 V module board 110.5 C | 150 / 130 / 105 / 105 / 121 C | PASS |
| Board B alone (150 A on B, worst split `feed150lo`) | Tj 121.6 C (U23), laminate 120.6 C (at the 5 V module U27), FRAM board 109.3 C, U6 sensor 108.2 C | 150 / 130 / 105 C | PASS for Tj and laminate; FRAM over 105 C at a steady 150 A, but the board's 104 C cut comes first (section 4) |
| Input board alone (all 8 inputs at 16 V, pull-downs on) | DIP switch 64.9 C, board max 77.6 C (in 60 C air) | 70 / 130 C | PASS (5 K margin; see the radiation assumption) |
| Whole box, sink (fans on) | 75.9 C max at 150 A on B; pedestals under B 74.4 C | - | (input for the boards) |
| Whole box, lid air -> input-board **DIP switch** (Omron A6S, -20..+70 C) | 79.8 C at the car loads, 80.1 C at 150 A on B, 91.4 C at 150 A with the A boards loaded | 70 C | **FAIL by 10-21 K** (known: `docs/parts-audit.md` 10 lists no 105 C DIP switch) |
| Fans (Sunon, -10..+70 C) | intake = 60 C cabin air (they push); their wall on the sink 66-71 C | 70 C | PASS for the air; frame contact WARN (71 C at `feed150a`) |
| Board A firmware limits (stock 55 / 80 C) | U6 reads 79.4 C at the car loads, fans on | must not cut in normal use | **FAIL** (1 K under the stock 80 C cut, sensor +-1 C): proposed warn 86 / critical 97 C (section 5) |
| Board B firmware limits (98 / 104 C) | at a 104 C reading the FRAM board can sit at 107.3 C, the 5 V module at 122 C (+4 K own heat = 126 C TJ) | 105 / 125 C | WARN: 2.3 K over on the FRAM, 1 K on the module (section 5) |

- **Nothing on the power path exceeds a rating** with the fans on at any load the firmware allows (150 A feed). Every
  output at its rating at once (304 A, twice the feed) is an upper bound only: there board B's laminate reaches 148.5 C
  and board A's 135.2 C (INFO, the feed limit prevents it).
- **The fans now push west**, so the warm exhaust leaves under board B (the board with the most heat). The sink under
  B runs 0.54 K/W of box heat (was 0.47 K/W in the 11-12 model with the fans pulling); under the A boards 0.41 K/W.
- **New hot spot: the 5 V module (LMZM23601V5)** is the hottest laminate point on both boards at most loads (board B
  119-121 C at 150 A, board A 102-110 C). It sits in the logic corner, far from the pedestals, and its loss (0.2 W
  ASSUMED) moves it a lot: 0.1 W -> 0.4 W moves it from 106 to 140 C on B (section 6). Bench item: measure the 5 V load.
- **Fans off** (failed): on a wall the sink reaches 92 C at 150 A (1.21 K/W, was 0.98); flat (fins down) 129 C.
  The boards' own temperature cut is the protection, as before.

## 2. Whole box (assembly) - Elmer model of revF

Box heat per load case (`sim/heat/loads_revF.json`, from the board models; `sim/heat/make_loads.py`):

| Load | What | Drivers (W) | Boards: copper + joints + 5 V modules + bars (W) | Box (W) | Lid air heat (contacts + harness, W) |
|---|---|---|---|---|---|
| `feed150` | 150 A on board B (A boards idle) | 11.1 | 15.5 | 26.6 | 1.1 |
| `feed150a` | 2 x 60 A on the A boards + 30 A on B | 14.8 | 11.8 | 26.7 | 4.8 |
| `car` | car loads (`docs/car-loads.dummy.md`, dummy copy), 142 A | 10.6 | 10.8 | 21.4 | 1.2 |
| `rating` | every output at its rating, 304 A (INFO) | 31.1 | 40.1 | 71.2 | 6.4 |

Results (mesh m2, 828k tetrahedra; sink = plate + fins + pedestals + bosses; R_sys = (sink max - 60 C) / box heat):

| Load | Air | Box (W) | Sink mean / max (C) | Pedestal max under B / A1 / A2 (C) | Fan end of the fins (C) | Lid air (C) | DIP switch (C) |
|---|---|---|---|---|---|---|---|
| feed150 | fans on | 26.6 | 69.0 / 75.9 | 74.4 / 68.1 / 66.1 | 66.0 | 75.2 | 80.1 |
| feed150 | fans on, pad k 1.5 | 26.6 | 69.0 / 76.3 | 74.3 / 68.1 / 66.1 | 66.0 | 75.2 | 80.1 |
| feed150a | fans on | 26.7 | 69.0 / 71.0 | 70.1 / 71.0 / 70.8 | 70.8 | 86.5 | 91.4 |
| car | fans on | 21.4 | 67.2 / 72.4 | 71.5 / 67.1 / 65.1 | 65.0 | 74.9 | 79.8 |
| rating (INFO) | fans on | 71.2 | 84.0 / 97.6 | 94.2 / 84.4 / 80.9 | 80.7 | 97.3 | 102.2 |
| feed150 | fans off, wall (fins vertical) | 26.6 | 86.1 / 92.1 | 90.7 / 85.6 / 84.2 | 84.1 | 80.6 | 85.5 |
| feed150 | fans off, flat (fins down) | 26.6 | 122.7 / 128.7 | 127.4 / 122.1 / 120.7 | 120.7 | 92.3 | 97.2 |
| car | fans off, wall | 21.4 | 83.1 / 87.4 | 86.7 / 83.3 / 81.9 | 81.8 | 79.9 | 84.8 |
| car | fans off, flat | 21.4 | 112.4 / 116.8 | 116.0 / 112.6 / 111.1 | 111.1 | 89.3 | 94.2 |

Heat maps (sink top with the pedestals, and the fin tips): `docs/diagrams/heat-revF-box-fans-feed150.png` (worst case
for the sink, fans on), `docs/diagrams/heat-revF-box-fans-feed150a.png` (A boards loaded),
`docs/diagrams/heat-revF-box-fansoff-wall-feed150.png` (fans-off reference).

Checks: heat out = heat in within 0.001 W in every run (Elmer boundary integrals); CG + ILU0 to 1e-10. Mesh: sink max
75.67 / 75.93 / 75.82 C on m1 (254k) / m2 (828k) / m3 (2.32M) tetrahedra (fans, feed150), 91.79 / 92.05 / 91.93 C fans
off: converged to 0.3 K. The box model's chip spots are NOT converged (112.1 / 114.2 / 116.2 C) and its boards are
uniform slabs, so the box gives the sink, pedestal and lid-air temperatures only; chip, laminate and part temperatures
come from the board models (sections 3, 4), which take the pedestal temperature from this run.

What changed against the 11-12 model (`HEAT_GEOM=revF`, `sim/heat/geometry.py`, from `enclosure/v2c/src/build_v2c.py`
and the revF release in the models folder):
- Pedestals 3.14 mm (were 3.0) and the Bergquist GAP PAD TGP 3000, 0.040 in (1.016 mm) squeezed 15 % to 0.86 mm, k 3.0
  W/mK (Henkel TDS, ASTM D5470); board bottom still at Z 4.0.
- Fans: 2 x Sunon at the east end PUSH west: cabin air enters at the A2 end and leaves warm under board B (11-12: pulled).
- Fins stop at the 6 mm fan wall and are cut back by the four foot keep-outs (9 of 20 fins shorter); 14 aluminium M3
  board bosses (dia 6) from the plate to the board bottoms are now heat paths.
- Heat: the copper I2R of every board (from the board models), bolted joints and bars, and the 5 V modules (0.2 W each)
  are in now; 11-12 had the driver losses only (and called the rest "left out, optimistic").
- Board copper 1 oz outer + 1 oz inner (35 / 35 um, `tools/copper_order.py`) in the slab's in-plane k (15.5 W/mK).
Not modelled (as before): the fan wall itself (conservative: less fin area), corner radii, radiation, conduction into
wires and the car (conservative); the plate top inside the lid is adiabatic. The USB hub move changes nothing here (0.1 W
ASSUMED into the lid air).

Lid air (one node, as `tools/verify_thermal_box.py`; all **ASSUMED** there): lid 0.12 m2 x 1.8 W/m2K to the cabin, open
sink top 0.010 m2 x 3, board tops 0.024 m2 x 3 at the sink mean + 15 K; heat in = X1 / X2 contacts + harness + 3 input
boards at their worst case (0.49 W each) + USB hub 0.1 W.

## 3. Board A (new detailed model, `tools/thermal_a.py`)

Same finite-volume model as board B's (`tools/thermal_board_b.py` Thermal class): every copper layer's real copper of all
nets from `hardware/board-a/DingoPDM.kicad_pcb` at the ORDERED 35 / 35 um, FR-4 between, via / hole barrels, TGP 3000 on
the two pedestals, 4 mm air gap under the board, lid air over it. Heat: the four BTS7008-2EPA on their exposed pads (16
mOhm per channel = 1.80 W per chip at 2 x 7.5 A), the copper I2R of +12V and every loaded output (solved on the real
copper, `tools/verify_copper.py`), J1 joint + half the BATT bars, the 5 V module U21 (0.2 W ASSUMED). The pedestals sit at
the hottest A pedestal of the box model (0.41 K/W fans on, 1.09 K/W fans off on a wall). Tests: `tools/test_thermal_models.py`
(EP = the footprint's pad 15, chips over the pedestals, ordered copper, isothermal with no heat, energy balance; 13 tests).

| Case | Sink | Tj max (chip) | Laminate max (where) | MCU U4 / FRAM U5 / 5 V module U21 board | U6 sensor | Verdict |
|---|---|---|---|---|---|---|
| feed150a, fans on (A1 60 A) | 70.9 | 119.7 (U13) | 117.2 (next to U13) | 89.3 / 93.7 / 110.5 | 97.5 | PASS |
| car, fans on (A1 20.4 A) | 68.9 | 89.0 (U13) | 102.0 (U21) | 76.2 / 80.5 / 102.0 | 79.4 | PASS |
| rating, fans on (INFO) | 88.7 | 137.7 | 135.2 | 107.5 / 112.0 / 128.5 | 116.1 | over 130 laminate (upper bound only) |
| feed150a, fans off (wall) | 89.4 | 138.4 | 135.9 | 108.3 / 112.7 / 129.3 | 116.8 | over: the temperature cut must act |
| car, fans off (wall) | 83.7 | 103.9 | 116.9 | 91.1 / 95.3 / 116.9 | 94.3 | PASS heat; above the stock 80 C cut |

Heat maps: `docs/diagrams/thermal-board-a-feed150a-fans.png` (F.Cu, B.Cu, copper-I2R rise), `-car-fans`, `-rating-fans`.

## 4. Board B (`tools/thermal_board_b.py`, re-run on the current files)

Changes in the model: gap pad 0.86 mm (was 1.0 mm), 5 V module U27 0.2 W added, pedestals at 0.54 K/W fans on / 1.25 K/W
fans off (revF box, was 0.47 / 0.98), logic parts reported (MCU, FRAM, 5 V module, crystal). Grid 0.3 mm.

| Case | Sink | Tj max (chip) | Laminate max (where) | MCU U4 / FRAM U5 / 5 V module U27 board | U6 sensor | Verdict |
|---|---|---|---|---|---|---|
| feed150, fans on | 74.2 | 109.1 (U9) | 119.3 (U27) | 97.1 / 108.0 / 119.3 | 107.6 | PASS heat; U6 over 104: board B cuts |
| feed150hi, fans on | 73.4 | 119.0 (U9) | 119.0 (feed corner, B.Cu) | 95.3 / 107.3 / 118.5 | 108.4 | as above |
| feed150lo, fans on | 75.3 | 121.6 (U23) | 120.6 (U27) | 99.3 / 109.3 / 120.6 | 108.2 | as above |
| car, fans on | 71.1 | 114.4 (U25) | 111.6 (U27) | 88.2 / 96.7 / 111.6 | 94.5 | PASS (under the 98 C warn) |
| rating, fans on (INFO) | 81.7 | 134.5 | 148.5 | 115.2 / 130.8 / 134.5 | 130.4 | upper bound only |
| feed150, fans off (wall) | 93.6 | 129.3 (U9) | 139.4 (U27) | 117.4 / 128.8 / 139.4 | 128.4 | over 130 laminate: the 104 C cut must act (as 11-22) |
| feed150lo, fans off | 96.3 | 142.7 (U23) | 142.3 (U27) | 121.3 / 131.8 / 142.3 | 130.6 | as above |
| car, fans off | 86.1 | 129.5 (U25) | 126.9 (U27) | 103.6 / 112.4 / 126.9 | 110.1 | PASS heat; board B cuts (110 > 104) |

Heat maps: `docs/diagrams/thermal-board-b-<case>-fans.png` / `-nofan.png` (F.Cu, B.Cu, copper-I2R rise).
Against the 2026-11-22 run (`docs/system-verification.md` 6): about +2 K everywhere from the warmer pedestals (the fans
now push the exhaust under B), and the 5 V module is the new laminate hot spot (it was not in the model).

## 5. Firmware temperature limits (proposals; the coordinator decides, nothing changed in firmware)

Map sensor -> hot spot (U6 MCP9808 reading vs the part, all modelled cases fans on / off), + 1 C MCP9808 error
(DS20005095B), limits: laminate 130 C, Tj 150 C, MCU / FRAM 105 C ambient, 5 V module 125 C TJ less 4 K own heat
(PsiJB 20 K/W x 0.2 W; TI SNVSAQ4C table 6.4: RthJA 45, PsiJB 20 K/W).

| Board | Largest offset over U6 | Critical needed for it | Binding |
|---|---|---|---|
| A | laminate +22.6 K (at U21, car); Tj +22.2 K; FRAM +1.1 K; 5 V module board +22.6 K | <= 106 / 126 / 102 / **97** C | 5 V module |
| B | laminate +20.0 K (rating, fans off); Tj +19.9 K (car); FRAM +2.3 K (car, fans off); 5 V module board +17.1 K (car) | <= 109 / 129 / **101** / **102** C | FRAM, 5 V module |

- **Board A: propose warn 86 C, critical 97 C, recovery 6 C** (stock 55 / 80 cuts at the car loads: U6 79.4 C with
  the fans on, 94.3 C fans off). Warn = 6.6 K over the car reading and below critical-soon (92 C).
- **Board B: the current 98 / 104 C leaves the FRAM 2.3 K and the 5 V module about 1 K over their ratings at the cut**
  (worst case with the +1 C sensor error). Holding them would need critical 101 C (critical-soon 96 C), but U6 reads
  94.5 C at the car loads with the fans on, so the warn would sit 0.5-1.5 K over normal use and a 65 C cabin would cut.
  A real design choice, not a model fix (open question; a 125 C FRAM would move the binding part to the 5 V module, 102 C).

## 6. Assumptions that move a result by more than 5 K (all **ASSUMED**)

| Assumption | Base | Changed to | Effect |
|---|---|---|---|
| 5 V module loss (each board) | 0.2 W | 0.1 / 0.4 W | B U27 spot 98.6 / 133.2 C (car, base 111.6); A U21 91.3 / 127.4 C (car, base 102.0); A feed150a laminate 136.2 C at 0.4 W (FAIL) |
| Gap-pad contact (TGP 3000 k 3) | k 3 | k 1.5 (contact resistance doubling the pad) | B feed150 Tj 107 -> 119 C, laminate 117 -> 122 C; A feed150a Tj 121 -> 134 C, laminate 119 -> 131 C (1 K over) |
| BATT bar far ends | sink + 15 K | sink + 5 K | A car U6 81 -> 76 C, U21 103 -> 98 C; B feed150 U6 106 -> 101 C |
| Input board h (radiation) | 9 W/m2K (3 + 6 radiation) | 3 (no radiation) | DIP rise 4.9 -> 17.4 K (alone in 60 C air: 64.9 -> 77.4 C, PASS -> FAIL) |
| Fans push vs the 11-12 pull | revF push | (11-12 pull) | pedestals under B +3.5 K at 26 W against the old R_sys |

Sensitivity runs were made at the first R_sys (0.47 K/W); the differences hold. Other assumptions as before (section 8):
via plating 20 um, FR-4 k 0.3, aluminium 6061 k 167, fan straight-line curve, 50 % fin bypass, joint 20 uOhm.

## 7. Re-run

Board models (Windows, KiCad 9 python; about 4 min A, 8 min B):
```
python tools/test_thermal_models.py
python tools/thermal_a.py --air fans --plots docs/diagrams --json a_fans.json     (and --air nofan)
python tools/thermal_board_b.py --res 0.3 --case feed150 feed150hi feed150lo car rating --air fans --plots docs/diagrams --json b_fans.json
python tools/thermal_input.py --plots docs/diagrams
python sim/heat/make_loads.py a_fans.json b_fans.json      (writes sim/heat/loads_revF.json)
```
Whole box (WSL, `HEAT_GEOM=revF`; runs in `~/cad-parts/custom-pdm-thermal3/runs/20261123/m1|m2|m3`):
```
python3 -I sim/heat/mesh_heat.py <run>/m2 0.6
~/.venvs/handbuilt-cad/bin/python -I sim/heat/run_cases.py <run>/m2            (all loads, about 15 min)
~/.venvs/handbuilt-cad/bin/python -I sim/heat/report_revf.py <run>/m2 docs/diagrams <run>/m1 <run>/m3
```
If the box result moves, update `R_SYS` in `tools/thermal_board_b.py` (B) and `R_SYS_A` in `tools/thermal_a.py` from the
report's "pedestal-top max" lines, then re-run the board models.

## 8. History: the 2026-11-11 / 11-12 model (v2b sink, fans pulling, driver losses only) - superseded

Status: first steady-state model, 2026-11-11, branch `feat/heat-analysis`. Results, not decisions.
Tool: Elmer 26.2 (HeatSolve), Gmsh 4.14, WSL Ubuntu, handbuilt-cad sim stack (`sim-stack` skill). No Fusion.
Marks: **ASSUMED** = my modelling choice, **TBD** = not confirmed (product or fab not chosen).

### 1. Answer in short

- **Passive (no fans) does not meet the targets at worst case.** Even the optimistic natural-convection number puts the sink at about 90 C (target 85 fails, 95 passes); the conservative one puts it at 136 C (fails 105), and junctions go over 150 C.
- **With the two 30 mm fans the sink sits at about 71 C (max 75 C): meets the 85 C target at worst case**, and every junction stays under 150 C for any pad k from 1 to 6 W/mK (k = 1 leaves only 5 K).
- **The weak link is not the sink, it is the path through the board.** With fans, the sink is 71-75 C but the BTS70012 spots on board B reach about 119 C (k = 3). Of those ~45 K, the gap pad takes about 10 K (k = 3) and the board about 35 K: the 9 plain 0.4 mm vias under each BTS70012 pad are the bottleneck (hand check: about 21 K/W for 9 barrels with 20 um plating, x 2.37 W).
- **Fan temperature flag:** the fans pull air, so they sit in the exhaust. Worst-case exhaust is about 74 C; the Sunon fan is rated -10 to +70 C (spec D03033580G-01). At typical load it is about 68 C. Pushing instead of pulling would keep them at cabin air (60 C).
- Pad k matters a lot for junctions (about 20 K from k = 1 to 3, 6 K more to k = 6) and not at all for the sink.

### 2. Results (mesh m2, 829k tetrahedra; per-chip losses from `docs/enclosure-layout.md` 4.3)

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

### 3. Model

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

**Left out, conservative (extra ways OUT for the heat):** heat into wires, terminals and connectors; heat from the board top and the lid; radiation (sink finish TBD; black anodising could add roughly 0.5 W/K to case 1b); conduction through the M3 bosses and screws. The plate top inside the lid is adiabatic.

**Left out, OPTIMISTIC (extra heat IN that the model does not have; corrected 2026-11-16, it was listed as conservative):** I2R heat made inside the box outside the chips. Estimate (worst case for the copper: 150 A feed with 120 A going on to A1 + A2, 60 A each; Cu C110 at 80 C, rho 2.13e-8 ohm m; bar lengths from the v2c build, B -> A1 113.4 mm, A1 -> A2 74.4 mm):

| Source | Path of the heat | Estimate |
|---|---|---|
| BATT bar 20 x 5 / GND bar 15 x 5 | bars -> board M6 terminals -> boards -> sink | 0.40 W / 0.54 W (upper bound with the full 150 A over the full length: 0.90 W / 1.20 W; the "about 2.2 W per bar" quoted before does not reproduce) |
| Bolted joints on the feed (lug-boss, boss-bar, bar-terminal at B / A1 / A2), 20 uOhm each ASSUMED | same | 1.1 W per net, 2.1 W both |
| OUT1-4 joints (lug-seat, riser foot-REDCUBE), 31 A | risers -> board B -> sink | 0.15 W |
| X1 / X2 contacts (16 x 7.5 A size 16 at 2 mOhm, 4 x 15 A size 12 at 1 mOhm, ASSUMED; TE max values to check) | connector -> harness and lid | about 2.7 W |
| Internal harness to X1 (16 x 7.5 A, 16 AWG about 0.25 m; 4 x 15 A, 12 AWG about 0.15 m) | wires -> air inside the lid | about 3.7 W |

Effect (scaling the fans-on result, sink max rise 14.5 K for 31.1 W = 0.47 K/W): the 3.2 W (up to 4.5 W) that reaches the sink through the copper raises the sink and every chip by about 1.5 K (up to 2.1 K): worst case k = 3 hottest Tj about 123 C (was 121), k = 1 about 147 C (margin 3 K, was 5 K). Fans off, wall-mounted (v2b / v2c F1 table, `docs/enclosure-v2c.md` section 4: 1.0 K/W): about +3 K (k = 3 board top about 142 C, still under 150). The 6 W or so in the connectors and harness goes into the air under the PA12 lid, which this model does not have (lid and air not modelled); if most of it had to leave through the 3 mm lid (about 0.12 m2, about 1.8 W/m2K overall) the air inside would sit tens of K above cabin air, so the board-top parts' air temperature is the open question, not the sink. Next step: add the lid, the internal air and these sources to the model (`sim/heat`), or measure on the bench.

**Materials:** aluminium k = 167 W/mK (6061-T6 handbook value; alloy ASSUMED, 6063 would be better). Air properties: Incropera & DeWitt, Table A.4, at film temperature.

**Data-sheet values used (read 2026-11-11, Infineon, Table 6 / Table 5):** RthJC max (simulated at the exposed pad) BTS7008-2EPA 1.4 K/W, BTS70012-1ESP 0.7 K/W, BTS7004-1EPP 2.4 K/W; Tj max 150 C for all three. Links in `docs/enclosure-layout.md` 4.3.

#### Air side (all at 60 C cabin air)
h depends on the sink temperature, so it is iterated (damped) at k = 3 until the mean air-side temperature moves less than 0.3 K; k = 1 and 6 reuse that h.

| Case | Faces | h | Correlation and inputs |
|---|---|---|---|
| 1a passive, optimistic | fins + plate underside | 3.5 W/m2K (worst), 2.7 (typical) | Elenbaas (1942) isothermal vertical parallel plates, Nu_S = Ra*/24 [1 - exp(-35/Ra*)]^0.75 (Bar-Cohen & Rohsenow 1984), S = 4 mm, L = 30 mm. Optimistic: it assumes channels open top and bottom, but here the plate closes the top of every channel (fins down). |
|  | plate outer edges | about 7 W/m2K | Churchill & Chu, vertical plate, L = 38 mm |
| 1b passive, conservative | all air-side faces | 1.4 W/m2K (worst), 1.2 (typical) | Envelope method: the finned block counts only as its outer box. Bottom 280 x 119 mm = hot plate facing down, Nu = 0.27 Ra^1/4 (Incropera eq. 9.32, L = area / perimeter); four sides = Churchill & Chu, L = 38 mm. Total hA spread evenly over the meshed faces (sink is near isothermal). |
| 2 two fans | fins + plate underside | 28.6 W/m2K | Laminar, simultaneously developing flow between parallel plates, mean Nu, Stephan correlation (Shah & London 1978): Nu = 7.84 at Re 444, x* 0.098, Dh = 8 mm. Air temperature rises linearly along the fins from 60 C (west inlet) to 74.2 C (worst) / 68.0 C (typical) at the fans (all the heat goes into the fan air). |
|  | plate outer edges | 6.6 W/m2K | natural, as 1a |

Fan flow (case 2): 2 x Sunon MF30101V1-1000U-A99 in parallel, 5.5 CFM and 0.25 inH2O each (spec D03033580G-01, in the pack). The P-Q curve on spec page 5 is a picture only, so a **straight-line fan curve is ASSUMED**. Against the 16 channels (laminar friction, f Re = 96, plus entry and exit K = 1.5, **ASSUMED**) the operating point is 8.9 CFM of 11 CFM free air. **Only half of it is ASSUMED to pass through the fin channels** (open fin tips, pod leakage): 4.45 CFM, 1.09 m/s in the channels.

### 4. What is TBD or ASSUMED (affects the numbers)
- Gap pad product (k, real thickness after compression, contact resistance): TBD. Run covers k 1-6.
- Via plating thickness and whether vias are filled: TBD (fab). Filled or more vias under the BTS70012 pads would cut the biggest resistance in the chain.
- Copper coverage per layer (50 % ASSUMED); FR4 k (0.30 ASSUMED); aluminium alloy (6061 ASSUMED).
- Fan curve shape (straight line ASSUMED), bypass share (50 % ASSUMED), fan placement (pull, as in the pack).
- Natural convection of a fins-down sink: no correlation fits it well; 1a and 1b bracket it. A bench test of the real sink would settle it.
- Radiation and sink surface finish: TBD (left out).
- The 31.1 W worst case is itself an upper bound (every channel at rated current = 304 A, twice the 150 A feed).

### 5. Re-run

Scripts: `sim/heat/` (`geometry.py` stack and chip data, `mesh_heat.py` Gmsh model, `convection.py` h correlations, `run_cases.py` Elmer cases + post, `make_report.py` tables + plots, `example_worst_fans_k3.sif` one generated Elmer input). In WSL, from the repo checkout:

```bash
python3 -I sim/heat/mesh_heat.py ~/scratch/heat/runs/m2 0.6            # system python3 (gmsh module); 0.6 = mesh size factor
~/.venvs/handbuilt-cad/bin/python -I sim/heat/run_cases.py ~/scratch/heat/runs/m2        # all 18 cases, about 15 min
~/.venvs/handbuilt-cad/bin/python -I sim/heat/make_report.py ~/scratch/heat/runs/m2 docs/diagrams
```

`run_cases.py` is resumable (finished identical cases are only re-read). Add `quick` to run one case (worst, 1a, k = 3).
Meshes and results are not in git. WSL scratch on DansPC: `/home/daniel/scratch/heat/` (`runs/m1` 246k tets, `runs/m2` 829k tets = reported, `runs/m3` 2.33M tets = mesh check, partial; `pack/` = extracted copy of the TEST 2 pack).
