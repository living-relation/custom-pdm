# Heat analysis - the current design (enclosure revF, boards with the 5 V module, 1 oz inner copper)

Status: re-run 2026-11-23 (job thermal3, branch `feat/thermal-current`) on the current geometry; fixes and re-run the
same day (job hwtemp, branch `fix/thermal-revF`: section 0; sections 1-6 show the numbers after the fixes, the PR #139
numbers are in the "before" column of section 0). Results, not decisions.
The 2026-11-11 / 11-12 results (older v2b sink, fans pulling, no copper heat) are kept at the end as history (section 8).
Tools: Elmer 26.2 + Gmsh 4.14 in WSL (whole box), finite-volume board models on the real KiCad copper (KiCad 9 python).
Marks: **ASSUMED** = my modelling choice, **TBD** = not confirmed. All at a 60 C cabin.

Order of work (Dan, 2026-11-23): each board alone first (A, B, input board: sink, fans on, TGP 3000 pad), then the whole
assembly.

## 0. Fixes (job hwtemp, 2026-11-23): before / after

Coordinator defaults a-e (technical, test-first; DECISIONS proposal in the PR). Same 60 C cabin, same models; "before"
= PR #139 (5 V module 0.2 W ASSUMED), "after" = this branch.

| # | Item | Before (PR #139) | Change | After | Verdict |
|---|---|---|---|---|---|
| a | 5 V module loss (A U21, B U27) | 0.2 W ASSUMED; spot moved 99 -> 133 C over 0.1-0.4 W | TI SNVSAQ4C Figure 8-46 at the real load 0.22 A (CAN 70 mA dominant + +3V3 155 mA) and 13.5 V in: 0.116 W at 25 C, + hot conduction share (I^2 x 0.61 Ohm x 50 %, ASSUMED) = **0.131 W** (`thermal_board_b.p5v_loss`) | B U27 board: feed150 fans 119.3 -> 111.3 C, car 111.6 -> 103.7 C; A U21: car 102.0 -> 93.8 C, feed150a 110.5 -> 102.2 C; module board limit 121 -> 122.4 C (TJ 125 - 20 K/W x 0.131 W) | PASS (assumption replaced by maker data) |
| b | Board B FRAM at its 104 C cut | MB85RC64TA (105 C): 107.3 C, 2.3 K over | U5 = Infineon CY15B064J-SXE on A and B (Automotive-E 125 C, same SOIC-8 / pins / address 0x50 / 2 address bytes / no page limit; firmware driver unchanged; `docs/parts-audit.md` 17) | FRAM offset over U6 +2.1 K: at 104 + 1 C it sits at 107.1 C vs 125 C (allows critical 121.9 C) | PASS |
| c | Board A firmware limits | stock 55 / 80 C; U6 79.4 C at the car loads (1 K from the cut) | factory warn 98 / critical 104 / recovery 6 C (`port_boards.py` FAN_A; UI `PdmFactoryDefaults` / `PdmThermal` board A offset 21 K) from the board A part map (section 5) | U6 79.2 C at the car loads, 70.7 C on the s5 drive cycle: 18.8 K under warn; at critical 104 C every part inside its rating (binding 5 V module allows 105.2 C) | PASS |
| d | Input-board DIP switch (Omron A6S, 70 C) in the lid air | 79.8 / 80.1 / 91.4 C (car / feed150 / feed150a) | no SMD DIP switch >= 105 C exists: 16 solder jumpers JP1-JP16 in the same board area (set by hand, table in `docs/order-checklist.md`); connectors, holes and outline unchanged | jumpers 79.4 / 79.7 / 91.0 C, board max 87.7 / 88.0 / 99.3 C vs the 130 C laminate (input board alone in 60 C air: jumpers 64.5 C, max 72.8 C; was DIP 64.9 / max 77.6 C) | PASS |
| e | Fans (Sunon, -10..+70 C) | intake 60 C cabin air; frame on the 66-71 C fin wall | no 30 x 30 x 10 mm fan rated >= 80 C found (`docs/parts-audit.md` 17) | unchanged: fin wall 66.0-70.7 C | WARN kept (bearing life; the critical cut covers a dead fan) |
| - | Board B limits (98 / 104 C) | WARN (FRAM 2.3 K, module about 1 K over) | (a) + (b) | part map allows critical 106.7 C (5 V module), MCU 107.1 C; 104 C kept (fwsafety MCU rule) | PASS |
| - | s5 drive cycle as a load case (`drive`, PR #140 `firmware/sim/data/s5_board_power.csv`) | - | RMS current per output over the coolant / fan phase (B 62.9 A, A1 5.8 A), held steady | B: Tj 80.9 C, laminate 89.8 C (U27), U6 75.1 C; A1: Tj 65.7 C, laminate 86.8 C (U21), U6 70.7 C; box 6.5 W, sink 63.8 C, lid air 69.8 C | PASS |

## 1. Answer in short

| Board / item | Worst case the firmware allows (fans on) | Limit | Verdict |
|---|---|---|---|
| Board A alone (A1 at 60 A, `feed150a`) | Tj 119.6 C (U13), laminate 117.1 C, MCU board 88.9 C, FRAM board 93.2 C, 5 V module board 102.2 C | 150 / 130 / 105 / 125 / 122.4 C | PASS |
| Board B alone (150 A on B, worst split `feed150lo`) | Tj 121.5 C (U23), laminate 118.0 C (feed corner, B.Cu), FRAM board 109.0 C, 5 V module board 112.6 C, U6 sensor 108.1 C | 150 / 130 / 125 / 122.4 C | PASS (the board's 104 C cut acts at a steady 150 A, section 4) |
| Input board alone (all 8 inputs at 16 V, pull-downs on) | solder jumpers 64.5 C, board max 72.8 C (in 60 C air) | 130 C | PASS (h 3, no radiation: 76.9 / 85.9 C) |
| Whole box, sink (fans on) | 75.9 C max at 150 A on B; pedestals under B 74.4 C | - | (input for the boards) |
| Whole box, lid air -> input-board **solder jumpers** (were the 70 C DIP switches) | 79.4 C at the car loads, 79.7 C at 150 A on B, 91.0 C at 150 A with the A boards loaded (board max 87.7 / 88.0 / 99.3 C) | 130 C laminate | PASS (hwtemp d) |
| Fans (Sunon, -10..+70 C) | intake = 60 C cabin air (they push); their wall on the sink 66-71 C | 70 C | PASS for the air; frame contact WARN (71 C at `feed150a`): no 80 C 30 mm fan exists (hwtemp e) |
| Board A firmware limits (98 / 104 C since hwtemp; were the stock 55 / 80) | U6 reads 79.2 C at the car loads, 70.7 C on the drive cycle, fans on | must not cut in normal use | PASS (section 5) |
| Board B firmware limits (98 / 104 C) | at a 104 C reading (+1 C error): FRAM board 107.1 C, 5 V module board 119.7 C | 125 / 122.4 C | PASS (FRAM now 125 C, module loss from TI data; section 5) |

- **Nothing on the power path exceeds a rating** with the fans on at any load the firmware allows (150 A feed). Every
  output at its rating at once (304 A, twice the feed) is an upper bound only: there board B's laminate reaches 148.5 C
  and board A's 135.2 C (INFO, the feed limit prevents it).
- **The fans now push west**, so the warm exhaust leaves under board B (the board with the most heat). The sink under
  B runs 0.54 K/W of box heat (was 0.47 K/W in the 11-12 model with the fans pulling); under the A boards 0.41 K/W.
- **The 5 V module (LMZM23601V5)** is the hottest laminate point at light loads (car / drive cycle on A, drive cycle
  on B). Its loss is now TI's (0.131 W at 0.22 A, 13.5 V; was 0.2 W ASSUMED): board B 110-113 C at 150 A, board A
  94-102 C. Bench item: measure the 5 V load and the module case temperature.
- **Fans off** (failed): on a wall the sink reaches 92 C at 150 A (1.21 K/W, was 0.98); flat (fins down) 129 C.
  The boards' own temperature cut is the protection, as before.

## 2. Whole box (assembly) - Elmer model of revF

Box heat per load case (`sim/heat/loads_revF.json`, from the board models; `sim/heat/make_loads.py`):

| Load | What | Drivers (W) | Boards: copper + joints + 5 V modules + bars (W) | Box (W) | Lid air heat (contacts + harness, W) |
|---|---|---|---|---|---|
| `feed150` | 150 A on board B (A boards idle) | 11.1 | 15.5 | 26.6 | 1.1 |
| `feed150a` | 2 x 60 A on the A boards + 30 A on B | 14.8 | 11.8 | 26.7 | 4.8 |
| `car` | pre-07:44 load set (worst case): car loads (`docs/car-loads.dummy.md`, dummy copy; the car config is now `carfull`, ADR-2026-11-23-ecu-loads), 142 A | 10.6 | 10.8 | 21.4 | 1.2 |
| `rating` | every output at its rating, 304 A (INFO) | 31.1 | 40.1 | 71.2 | 6.4 |

Results (mesh m2, 828k tetrahedra; sink = plate + fins + pedestals + bosses; R_sys = (sink max - 60 C) / box heat):

After the hwtemp fixes (5 V modules 0.131 W, s5 drive-cycle load added; `~/scratch/hwtemp/heat/m2`, 2026-11-23):

| Load | Air | Box (W) | Sink mean / max (C) | Pedestal max under B / A1 / A2 (C) | Fan end of the fins (C) | Lid air (C) | Input-board jumpers / board max (C) |
|---|---|---|---|---|---|---|---|
| feed150 | fans on | 26.4 | 68.9 / 75.9 | 74.3 / 68.0 / 66.0 | 66.0 | 75.2 | 79.7 / 88.0 |
| feed150 | fans on, pad k 1.5 | 26.4 | 68.9 / 76.2 | 74.2 / 68.0 / 66.1 | 66.0 | 75.2 | 79.7 / 88.0 |
| feed150a | fans on | 26.4 | 68.9 / 70.9 | 70.0 / 70.9 / 70.7 | 70.7 | 86.5 | 91.0 / 99.3 |
| car | fans on | 21.2 | 67.1 / 72.3 | 71.5 / 67.1 / 65.0 | 65.0 | 74.9 | 79.4 / 87.7 |
| drive (s5, new) | fans on | 6.5 | 62.2 / 63.8 | 63.6 / 62.1 / 61.5 | 61.5 | 69.8 | 74.3 / 82.6 |
| rating (INFO) | fans on | 71.0 | 84.0 / 97.6 | 94.1 / 84.4 / 80.8 | 80.6 | 97.3 | 101.8 / 110.1 |
| feed150 | fans off, wall (fins vertical) | 26.4 | 86.0 / 92.0 | 90.6 / 85.5 / 84.1 | 84.0 | 80.6 | 85.1 / 93.4 |
| feed150 | fans off, flat (fins down) | 26.4 | 122.4 / 128.5 | 127.1 / 121.8 / 120.4 | 120.4 | 92.2 | 96.7 / 105.0 |
| car | fans off, wall | 21.2 | 83.0 / 87.3 | 86.6 / 83.2 / 81.7 | 81.7 | 79.9 | 84.4 / 92.7 |
| car | fans off, flat | 21.2 | 112.0 / 116.4 | 115.7 / 112.3 / 110.8 | 110.7 | 89.2 | 93.7 / 102.0 |

R_sys for the board models is unchanged to 0.01 K/W (B 0.542 / 1.253, A 0.412 / 1.096 K/W fans on / off): `R_SYS`
0.54 / 1.25 and `R_SYS_A` 0.41 / 1.09 kept. PR #139 (0.2 W modules) had 26.6 / 26.7 / 21.4 / 71.2 W and the same
temperatures within 0.2 K; its "DIP switch" column (lid air + 4.9 K) was 80.1 / 91.4 / 79.8 C against the A6S 70 C.

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
copper, `tools/verify_copper.py`), J1 joint + half the BATT bars, the 5 V module U21 (0.131 W, TI SNVSAQ4C Figure 8-46;
was 0.2 W ASSUMED). The pedestals sit at
the hottest A pedestal of the box model (0.41 K/W fans on, 1.09 K/W fans off on a wall). Tests: `tools/test_thermal_models.py`
(EP = the footprint's pad 15, chips over the pedestals, ordered copper, isothermal with no heat, energy balance; 13 tests).

After hwtemp (5 V module 0.131 W; case `drive` = the s5 drive cycle; FRAM CY15B064J 125 C):

| Case | A1 (A) | Sink | Tj max (chip) | Laminate max (where) | MCU U4 / FRAM U5 / 5 V module U21 board | U6 sensor | Verdict |
|---|---|---|---|---|---|---|---|
| feed150a, fans on (A1 60 A) | 60.0 | 70.8 | 119.6 (U13) | 117.1 (next to U13) | 88.9 / 93.2 / 102.2 | 97.3 | PASS |
| car, fans on | 20.4 | 68.8 | 88.9 (U13) | 93.8 (U21) | 75.7 / 80.0 / 93.8 | 79.2 | PASS (under the 98 C warn) |
| drive, fans on | 5.8 | 62.6 | 65.7 (U13) | 86.8 (U21) | 68.5 / 72.7 / 86.8 | 70.7 | PASS |
| rating, fans on (INFO) | 60.0 | 88.6 | 137.6 | 135.1 | 107.1 / 111.6 / 120.3 | 115.9 | over 130 laminate (upper bound only) |
| feed150a, fans off (wall) | 60.0 | 89.2 | 138.2 | 135.7 | 107.7 / 112.1 / 120.8 | 116.5 | over: the 104 C cut acts (U6 116.5) |
| car, fans off (wall) | 20.4 | 83.5 | 103.6 | 108.5 (U21) | 90.4 / 94.7 / 108.5 | 94.0 | PASS heat; warn not reached (98) |
| drive, fans off (wall) | 5.8 | 67.0 | 70.0 | 91.2 (U21) | 72.8 / 77.1 / 91.2 | 75.0 | PASS |
| rating, fans off (INFO) | 60.0 | 137.3 | 186.8 | 184.3 | 156.8 / 161.6 / 169.6 | 166.6 | upper bound only; the cut acts |

PR #139 (0.2 W): feed150a fans 119.7 / 117.2 / U21 110.5 / U6 97.5 C; car fans 89.0 / 102.0 (U21) / U6 79.4 C; car fans
off U21 116.9, U6 94.3 C.

Heat maps: `docs/diagrams/thermal-board-a-<case>-fans.png` / `-nofan.png` (F.Cu, B.Cu, copper-I2R rise; cases rating,
feed150a, car, drive).

## 4. Board B (`tools/thermal_board_b.py`, re-run on the current files)

Changes in the model: gap pad 0.86 mm (was 1.0 mm), 5 V module U27 0.131 W (TI data, hwtemp; PR #139: 0.2 W), pedestals at 0.54 K/W fans on / 1.25 K/W
fans off (revF box, was 0.47 / 0.98), logic parts reported (MCU, FRAM, 5 V module, crystal). Grid 0.3 mm.

After hwtemp:

| Case | B (A) | Sink | Tj max (chip) | Laminate max (where) | MCU U4 / FRAM U5 / 5 V module U27 board | U6 sensor | Verdict |
|---|---|---|---|---|---|---|---|
| feed150, fans on | 150 | 74.1 | 109.1 (U9) | 117.6 (feed corner, B.Cu) | 96.8 / 107.7 / 111.3 | 107.5 | PASS heat; U6 over 104: board B cuts |
| feed150hi, fans on | 150 | 73.4 | 118.9 (U9) | 118.9 (feed corner, B.Cu) | 95.0 / 107.1 / 110.5 | 108.3 | as above |
| feed150lo, fans on | 150 | 75.2 | 121.5 (U23) | 118.0 (feed corner, B.Cu) | 98.9 / 109.0 / 112.6 | 108.1 | as above |
| car, fans on | 118.1 | 71.1 | 114.4 (U25) | 110.1 (F.Cu at U25) | 87.9 / 96.5 / 103.7 | 94.4 | PASS (under the 98 C warn) |
| drive, fans on | 62.9 | 63.3 | 80.9 (U8) | 89.8 (U27) | 72.0 / 76.6 / 89.8 | 75.1 | PASS |
| rating, fans on (INFO) | 184 | 81.7 | 134.4 | 148.4 | 114.9 / 130.5 / 126.5 | 130.2 | upper bound only |
| feed150, fans off (wall) | 150 | 93.5 | 129.2 (U9) | 139.0 (B.Cu) | 117.1 / 128.4 / 131.4 | 128.2 | over 130 laminate: the 104 C cut must act (as 11-22) |
| feed150hi, fans off | 150 | 91.7 | 137.9 (U9) | 139.1 (B.Cu) | 114.0 / 126.5 / 129.4 | 127.8 | as above |
| feed150lo, fans off | 150 | 96.2 | 142.6 (U23) | 141.2 (B.Cu) | 120.9 / 131.4 / 134.3 | 130.4 | as above |
| car, fans off | 118.1 | 86.0 | 129.4 (U25) | 125.1 (F.Cu) | 103.2 / 112.0 / 118.9 | 109.9 | PASS heat; board B cuts (110 > 104) |
| drive, fans off | 62.9 | 67.6 | 85.2 (U8) | 94.1 (U27) | 76.4 / 81.0 / 94.1 | 79.5 | PASS |
| rating, fans off (INFO) | 184 | 112.1 | 166.6 | 183.7 | 147.4 / 164.1 / 158.5 | 163.7 | upper bound only |

PR #139 (0.2 W): feed150 fans laminate 119.3 (U27), FRAM 108.0, U6 107.6 C; car fans U27 111.6, U6 94.5 C; car fans
off U27 126.9 C.

Heat maps: `docs/diagrams/thermal-board-b-<case>-fans.png` / `-nofan.png` (F.Cu, B.Cu, copper-I2R rise).
Against the 2026-11-22 run (`docs/system-verification.md` 6): about +2 K everywhere from the warmer pedestals (the fans
now push the exhaust under B), and the 5 V module is the new laminate hot spot (it was not in the model).

## 5. Firmware temperature limits (set by job hwtemp, 2026-11-23)

Map sensor -> part (U6 MCP9808 reading vs the part, every modelled case fans on / off, `drive` included), + 1 C MCP9808
error (DS20005095B). Limits: laminate 130 C, Tj 150 C, MCU 105 C ambient (STM32F446RET7), FRAM 125 C (CY15B064J-SXE
since hwtemp), 5 V module 125 C TJ less its own heat (PsiJB 20 K/W x 0.131 W = 2.6 K: 122.4 C at the board; TI
SNVSAQ4C table 6.4). Checked by `tools/verify_thermal_box.py --afans --anofan` ("part map" rows).

| Board | Largest offset over U6 (critical it allows) | Binding | Factory limits |
|---|---|---|---|
| A | laminate +19.8 K (109.2 C, feed150a); Tj +22.3 K (126.7 C); MCU -2.2 K (106.2 C); FRAM +2.1 K (121.9 C); 5 V module board +16.2 K (105.2 C, drive fans off) | 5 V module | warn 98, critical 104, recovery 6 C (were the stock 55 / 80 C) |
| B | laminate +20.0 K (109.0 C, rating fans off); Tj +20.0 K (129.0 C, car); MCU -3.1 K (107.1 C); FRAM +2.1 K (121.9 C); 5 V module board +14.7 K (106.7 C, drive) | 5 V module | warn 98, critical 104, recovery 6 C (unchanged) |

- **Board A: warn 98 / critical 104 / recovery 6 C.** Critical 104 C is board B's and the ADR-2026-11-20-fwsafety
  rule (MCU at the sensor + 1 C <= 105 C); it sits inside every part limit above (the 5 V module allows 105.2 C). The
  PR #139 proposal (warn 86 / critical 97 C) was bound by the 5 V module at the assumed 0.2 W; with TI's 0.131 W the
  module allows 105.2 C. Board A's laminate offset (19.8 K + 1 = 21 K, rounded up) equals board B's (20.0 + 1 = 21 K),
  so the one PDM hot-spot set of the UI (119 / 125 C) gives both boards 98 / 104 C: board A takes B's warn too, 18.8 K
  over its car-loads reading (79.2 C) and 27 K over the drive cycle (70.7 C): no warning in normal use. Fans failed at
  the car loads A reads 94.0 C (no warning); board B warns and cuts first (109.9 C).
- **Board B: 98 / 104 / 6 C kept.** The FRAM (2.3 K over 105 C before) is a 125 C part now and the 5 V module allows
  106.7 C with TI's loss: nothing over its rating at the cut. U6 reads 94.4 C at the car loads (3.6 K under warn).
- If the MB85RC64TA alternate (105 C) is fitted: FRAM offset +2.1 K needs critical <= 101 C on that board.
- UI (`ui/dingoConfig/domain/CustomPdm/PdmThermal.cs`): `BoardBLaminateOffsetK` 20.0 (was 19.6), `BoardALaminateOffsetK`
  19.8 (new): sensor limit = hot spot - 21 K on both boards; sensor critical maximum 104 C on both.

## 6. Assumptions that move a result by more than 5 K (all **ASSUMED**)

| Assumption | Base | Changed to | Effect |
|---|---|---|---|
| 5 V module loss (each board) | 0.2 W ASSUMED (PR #139; 0.131 W TI data since hwtemp) | 0.1 / 0.4 W | B U27 spot 98.6 / 133.2 C (car, base 111.6 at 0.2 W; 103.7 at 0.131 W); A U21 91.3 / 127.4 C (car, base 102.0 at 0.2 W; 93.8 at 0.131 W); A feed150a laminate 136.2 C at 0.4 W (FAIL). The 0.4 W case needs about 0.6 A of 5 V load: not this circuit (0.22 A worst) |
| Gap-pad contact (TGP 3000 k 3) | k 3 | k 1.5 (contact resistance doubling the pad) | B feed150 Tj 107 -> 119 C, laminate 117 -> 122 C; A feed150a Tj 121 -> 134 C, laminate 119 -> 131 C (1 K over) |
| BATT bar far ends | sink + 15 K | sink + 5 K | A car U6 81 -> 76 C, U21 103 -> 98 C; B feed150 U6 106 -> 101 C |
| Input board h (radiation) | 9 W/m2K (3 + 6 radiation) | 3 (no radiation) | jumper rise 4.5 -> 16.9 K, board max 12.8 -> 25.9 K (alone in 60 C air: 76.9 / 85.9 C; PASS against the 130 C laminate; was the DIP switch 64.9 -> 77.4 C, PASS -> FAIL at 70 C) |
| Fans push vs the 11-12 pull | revF push | (11-12 pull) | pedestals under B +3.5 K at 26 W against the old R_sys |

Sensitivity runs were made at the first R_sys (0.47 K/W); the differences hold. Other assumptions as before (section 8):
via plating 20 um, FR-4 k 0.3, aluminium 6061 k 167, fan straight-line curve, 50 % fin bypass, joint 20 uOhm.

## 7. Re-run

Board models (Windows, KiCad 9 python; about 4 min A, 8 min B):
```
python tools/test_thermal_models.py
python tools/thermal_a.py --air fans --plots docs/diagrams --json a_fans.json     (and --air nofan)
python tools/thermal_board_b.py --res 0.3 --air fans --plots docs/diagrams --json b_fans.json   (all 6 cases incl. drive; and --air nofan)
python tools/thermal_input.py --plots docs/diagrams
python tools/verify_thermal_box.py --fans b_fans.json --nofan b_nofan.json --afans a_fans.json --anofan a_nofan.json
python sim/heat/make_loads.py a_fans.json b_fans.json      (writes sim/heat/loads_revF.json)
(hwtemp: run the two thermal_a.py runs one after the other with python -u; two at once sat idle at 0 % CPU on DansPC)
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
