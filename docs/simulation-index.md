# Simulation and check index

Every simulation and check of the custom PDM in one list: what it simulates, how, when it last ran, what it found and
where it lives. Job drivecycle, 2026-11-23, branch `test/drive-cycle` on `main` 19479b5. Every row marked 2026-11-23
was run in this job on DansPC from own scratch copies (WSL `/home/daniel/scratch/drivecycle`, `%TEMP%\drivecycle`).
Nothing on the boards was changed. Counts are PASS / WARN / FAIL (INFO not counted) as each tool prints them.

## 1. All simulations and checks

| Tool | What it simulates / checks | Method | Last run | Result | File |
|---|---|---|---|---|---|
| s0 board audit | each board alone: reset states, every output and input, current reading, temperatures, BOR, watchdog, sleep | real dingoFW logic built as a host shared object (`sim_core.cpp`), hardware modelled from the pin map | 2026-11-23 | 76 of 76 | `firmware/sim/s0_board_audit.py` |
| s1 system | the three boards as one PDM: commissioning, link loss, thermal and fans, sensor failures, wake set, per-output link loss | same host sim, three boards + ECU + PC tool on one CAN bus | 2026-11-23 | 91 of 91 | `firmware/sim/s1_system.py` |
| s2 boot blip | a "default ON at loss" output pulses at power-up | host sim | 2026-11-14 (finding kept) | 1 finding | `firmware/sim/s2_boot_blip.py` |
| s3 features | pro-PDM feature parity (logic, timers, flashers, wipers, PWM, keypads, protection, tables) | host sim, one board A per scenario | 2026-11-23 | 111 of 111, 0 XFAIL | `firmware/sim/s3_features.py` |
| s4 CAN system | whole car bus: response-time analysis and the real boards with the dummy car traffic, unplug / replug | Davis et al. 2007 RTA + host sim | 2026-11-23 | 10 of 10 | `firmware/sim/s4_can_system.py` |
| **s5 drive cycle (new)** | a day in the car on all three boards with the ST185 starter (section 2) | host sim, three boards + dummy ECU / keypad / car traffic + PC tool, load models, 1 ms pin checks | 2026-11-23 | 35 of 35, 1 XFAIL; 12 of 12 mutants RED | `firmware/sim/s5_drive_cycle.py` |
| Renode bench | the real ARM binaries of A1, A2, B on an emulated STM32F446 (CAN, ADC, I2C, FRAM, IWDG, option bytes) | Renode 1.17.0 + Robot tests | 2026-11-23 | see section 3 | `firmware/sim/renode/` |
| UI tests | the PC app (dingoConfig copy): one-PDM view, Write All, presets, faults, live tests against the sim | xUnit; live tests drive the host sim through `ui/tests/sim_bridge.py` | 2026-11-23 | see section 3 | `ui/tests/CustomPdm.Tests` |
| Starter export (new) | the ST185 starter as the wire values the app writes, for s5 | xUnit test that writes / checks the file | 2026-11-23 | PASS | `ui/tests/CustomPdm.Tests/StarterParamsExportTests.cs`, `firmware/sim/data/st185-starter.params.dummy.tsv` |
| verify_spice | current sense, input board, TVS surges, 3V3 start-up, CAN termination | ngspice circuit simulation (WSL user-level ngspice) | 2026-11-23 | 101 / 5 / 0, RESULT PASS | `tools/verify_spice.py` |
| verify_tolerance | every reading chain at -40 / 25 / 85 / 105 C | Monte Carlo (20 000) + hard corners | 2026-11-23 | 23 / 5 / 0 | `tools/verify_tolerance.py` |
| verify_power | rails vs battery, BOR, reverse battery, ISO 7637-2 / 16750-2, turn-off energy | data-sheet limits stacked, L-R energy | 2026-11-23 | 29 / 3 / 2 | `tools/verify_power.py` |
| verify_switching | PWM loss, freewheel diodes, minimum on-time, inrush vs presets, short circuit, parallel pair | data-sheet slew / EON / EOFF model | 2026-11-23 | 17 / 7 / 4 | `tools/verify_switching.py` |
| verify_mcu | firmware pins vs ST pin data vs PCB pads, clocks, CAN timing, IWDG, FRAM, sleep current | KiCad 9 pcbnew + ST open pin data | 2026-11-23 | 18 / 2 / 0 | `tools/verify_mcu.py` |
| verify_si | CAN / USB pair impedance, PWM spectrum, decoupling loops | 2-D field solver + loop inductance | 2026-11-23 | 3 / 2 / 0 | `tools/verify_si.py` |
| verify_dfm | via-in-pad, edge, silk, drills, BOM, footprint geometry vs the enclosure build | KiCad 9 pcbnew | 2026-11-23 | 7 / 7 / 0 | `tools/verify_dfm.py` |
| verify_cpl | every placement on its pads (JLC footprint overlay) | EasyEDA footprints vs our pads | 2026-11-23 | RESULT PASS (A 129, B 194 with 1 "check" Y1, IN 48) | `tools/verify_cpl.py` |
| verify_layout | crystal, I2C rise time, decoupling distance, mask dams, USB / CAN length | KiCad 9 pcbnew geometry | 2026-11-23 | RESULT PASS, 8 WARN | `tools/verify_layout.py` |
| verify_copper | +12 V feed drop and copper self-heating at every output at rating (184 A), no sink | finite-difference current flow on the real copper | 2026-11-23 | RESULT FAIL (2) | `tools/verify_copper.py` |
| verify_thermal_box | whole box: sink, lid air, board B FEA, fans on / failed, part ratings, board B limits | runs `thermal_board_b.py` (finite volume, 0.3 mm grid) + box nodes | 2026-11-23 | 27 / 4 / 5 on 19479b5; 20 / 9 / 7 on main bc32eca (new current-dependent model, job thermal) | `tools/verify_thermal_box.py`, `tools/thermal_board_b.py` |
| heat-sim (enclosure) | the enclosure and sink in air (R_sys fans on / off) | Gmsh + Elmer FEA | before 2026-11-20 (presim uses its R_sys); not run in this job | R_sys 0.47 / 0.98 K/W | `sim/heat/` |
| KiCad DRC / ERC / parity | board rules, schematic vs PCB | kicad-cli | 2026-11-22 (finalcheck) | known stock-pattern errors only | `docs/order-readiness.md` section 3 |
| gen_fab_jlcpcb hole check + JLC DRC | fab outputs, co-located holes, JLC limits | KiCad 9 python | 2026-11-22 (finalcheck) | PASS | `tools/gen_fab_jlcpcb.py` |
| copper_order --check | ordered copper = fab notes = stackups | table check | 2026-11-22 (orderprep) | PASS | `tools/copper_order.py` |
| enclosure build checks | overlaps, clearances, lugs, BOM / part files, CNC | handbuilt-CAD build | 2026-11-22 (revF) | PASS | `enclosure/v2c/src/build_check_all.sh` |
| DbcGen --check | DBC files vs the firmware messages | dotnet tool | not run in this job (no firmware message change) | - | `ui/tools/DbcGen` |

Last known counts before this job (docs/order-readiness.md): power 3 W 2 F, switching 7 W 4 F, thermal_box 4 W 5 F,
dfm 7 W, tolerance 5 W: the same today on 19479b5; on main bc32eca (merged here) verify_thermal_box gives 9 W 7 F with the new heat model.

## 2. Part 1: the drive cycle (s5)

**Result: PASS.** All 24 output pins of A1, A2 and B followed the starter's logic every 1 ms through the whole
210 s cycle, every change inside its timing window, with one known gap (XFAIL, below). No watchdog reset, no
unplanned MCU reset, no CAN overrun. 12 of 12 one-line config mutations turned the run RED.

How it works, in plain words:
- The ST185 starter (`ui/examples/st185-starter.json`, a dummy) is turned into the exact values the app writes
  (`StarterParamsExportTests`, which also fails if the file and the starter ever differ). s5 reads each board's own
  param table, checks it is the same list, writes it with Write All + Burn like the app, reads it back, and restarts
  the boards from their FRAM.
- On top of the starter, s5 adds one thing the starter lacks: a battery load shed (A/C clutch off after 2 s at
  <= 11.5 V, back at >= 12.5 V), the recipe proven in s3 F9.
- Loads: steady current, inrush and kind from `tools/presim_parts.py` CAR_LOADS (the same table as the thermal and
  switching checks): motors (fans, pump, wiper) start at 4 x and settle, LED / electronic loads have a short
  capacitor inrush, coils (horn, A/C clutch) rise with L / R. Switchboard 2 A, cluster 1.5 A and LED turn lamps
  0.2 A are ASSUMED. A wiper motor with a park cam drives B IN4.
- A separate logic model of the car, written from the starter's own words (README, the /pdm trigger texts), says
  what every output should do; it is not taken from the firmware.

The day, step by step (all PASS):

| Step | What happens | Checked (measured) |
|---|---|---|
| Write All | starter onto three fresh boards, burn, restart | table = file on all three, CRC, read-back |
| Key on, ECU prime | IN15 on, ECU sends pump on for 2 s | CAN-Lambda 25 ms, switchboard / cluster over CAN <= 140 ms |
| Crank | 6.0 V for 80 ms, 9.6 V for 1.2 s, then 14.2 V | no reset, nothing switches, shed never set |
| Lights | low, high (needs low), low off, back | 25-27 ms (20 ms debounce) |
| Turn signals, hazard | L, R, hazard | first flash 28-29 ms, 352 / 352 ms on / off, hazard in step |
| Horn | IN5 to ground (inverted) | 26-27 ms |
| Wipers | slow 3.3 s, fast 2 s, intermittent 9.5 s | parks in the cam zone every time; intermittent wipes 4.006 s apart |
| Coolant 80 -> 105 -> 85 C | radiator fan from the CAN value, condenser fan from the ECU byte | on at 92, off at 88; 1 s soft start ramps the duty |
| A/C | keypad 0x1A8 button 1 | <= 110 ms |
| Hot day | boards to the thermal model's temperatures (B 93.4 C, A 84.6 C) and back | A1 / A2 cut at 80 C (box fan kept), back below 74 C; B runs on |
| ECU frames lost 3 s | ECU silent | pump off 1005.9 ms after the last frame, back 3.9 ms after the first |
| Board B unplugged 3 s | B's CAN off | A1 switchboard off at 961 ms, cluster kept by its off-delay, all back |
| Overcurrent | 0.25 Ohm short on the low beams | cut in 6 ms, 4 retries 1102 ms apart, latched, Reset faults: on again in 55 ms |
| Low battery | 11.2 V | A/C off after 2205 ms, back at 12.6 V |
| Key off | IN15 off, ECU stops 2 s later | switchboard 110 ms, cluster 5.0 s later |
| Sleep | the app's sleep request to each board | all three asleep, no frame on the bus, none woke the others |
| Wake | key on, ECU frames | all three wake on the first frame, outputs follow again |

Firmware current readings matched the load model within 0.3 % on every steady load of 2 A or more.

Board power for the thermal job: `firmware/sim/data/s5_board_power.csv` (switch conduction loss per board and mean
current per output, every 0.5 s; run with `--proposals` so the CAN-Lambda runs as intended). Over the 210 s cycle:
A1 32 J (mostly the short), A2 under 0.1 J, B 267 J (1.27 W mean, 2.9 W peak over 0.5 s). RDS(ON) is interpolated
between the data-sheet 25 C and 150 C values at the board temperature + 15 K (ASSUMED). The full 10 ms current trace
(model and firmware reading per output) is written to the run's output folder.

What the drive cycle found (for decisions; none changes a board):

1. **XFAIL - CAN-Lambda trips at key-on.** B OUT5 has limit 10 A and inrush limit 10 A / 100 ms (the "Module" preset
   is 5 A with 2 x inrush; the limit was raised to 10 A, the inrush was not). The CAR_LOADS lambda starts at
   8.1 A x 1.5 = 12.2 A for 100 ms, so it trips at every key-on above about 11.1 V and latches after 5 tries.
   Proposal (proven: `--proposals` turns it into a pass with everything else still passing): inrush 20 A / 200 ms on
   B OUT5 in the starter, and the UI keeps inrush = 2 x limit when a Module limit is edited.
2. **Hot day: board A cuts its lamps.** With the thermal model's board A estimate (sink 69.6 C + 15 K ASSUMED =
   84.6 C, 60 C cabin, car loads, fans on) both A boards pass their 80 C critical: low beams, switchboard, cluster and
   turn signals go off until they cool below 74 C. Board A has no FEA sensor map yet (BACKLOG, ADR-2026-11-20-fwsafety
   c), so the 15 K is a guess.
3. **Radiator fan goes off when ECU frames are lost.** The coolant CAN value times out to 0, which reads as "88 C or
   less". The condenser fan goes on at loss, the radiator fan does not.
4. **Condenser fan runs after key off.** Its "on at loss" does not look at the ignition, so when the ECU stops at key
   off the fan comes on (30 A preset) until the PDM sleeps, and the starter never sleeps by itself (auto sleep off on
   all three boards).
5. Board B unplugged while driving stops the fuel pump after 1 s (the chosen "pump off at loss" policy) and drops
   A1's switchboard (its ignition comes from B over CAN): as designed, listed so it is known.
6. The A/C clutch follows keypad button 1 as a momentary input: on only while the button bit is set (config reading;
   s5 holds the button).

Not modelled: the PROFET's own current limit / thermal restarts in a short (the firmware side is), real CAN error
frames, STOP mode itself (a wake is modelled as the MCU reset that follows it), load inductance at turn-off.

## 3. Part 2: every check re-run, and every FAIL / WARN

Firmware and UI on `main` 19479b5 (host sim .so built from an LF `git archive`): s0 76 of 76, s1 91 of 91, s3 111 of
111, s4 10 of 10, s5 35 of 35 + 1 XFAIL. Renode bench 39 of 39 (binaries built from main 63053b9, own scratch HOME;
no firmware change between that and bc32eca). UI tests 467 of 467 with the live sim on this branch merged with main
bc32eca (first run before the merge: 458 of 459, the wall-clock test `WriteAllSpeedTests` A1 8.8 s vs 8.5 s while
Renode and s5 ran beside it; 4 of 4 alone). s5 re-run on the merged branch: same result.

Each FAIL / WARN, what it means, and what covers it ("NOT COVERED" = no ADR or accepted disposition found):

| Check | Verdict | What it means (plain words) | Covered by |
|---|---|---|---|
| tolerance: battery sense 9-16 V | WARN x 2 | the battery reading can be up to 0.55 V off (1.2 V if the zener leaks more than its data sheet says), most at 16 V | bench list (order-readiness: "battery sense near the top"); no ADR |
| tolerance: digital input, remote ground +1 V | WARN | a switch-to-ground input whose ground is 1 V off sits at the edge of "low" | bench list ("+1 V ground offset"); no ADR |
| tolerance: analog input 4.5 / 4.9 V | WARN x 2 | the 0-5 V input reads 66-142 mV off at the top | bench list; Dan 2026-11-08: analog sensors come in through the ECU |
| power: reverse battery, board B freewheel diodes | FAIL | a reversed battery shorts through D13-D28 | ADR-2026-11-21-reverse-battery (accepted: not protected) |
| power: horn turn-off energy (A1 OUT5) | FAIL | with an assumed 5-30 mH the horn's turn-off energy is over the BTS7008 clamp rating; the starter uses A1 OUT5 for the horn | ADR-2026-11-20-presim-findings (6): bench-measure L |
| power: ISO 7637-2 pulse 3a on an input | WARN | a 0.1 us -220 V pulse puts 216 V across a 0603 resistor | order-readiness "Accept for a first board spin" |
| power: load dump on inputs | WARN | battery-switched inputs push current into +3V3 | accept list (pcb-verification Left 4) |
| power: solenoid turn-off energy (A2 OUT5) | WARN | a big solenoid without a diode may exceed EAR; A2 OUT5 is a spare | bench list (load inductance) |
| switching: motor PWM heat, BTS7004 / BTS70012 | FAIL x 2 | hard-switched motors at 100-400 Hz heat the switch more than DC | ADR-2026-11-20-fwsafety (d): motor presets 22 / 64 / 60 Hz |
| switching: fan PWM vs BYG23M | FAIL x 2 | PWM above about 32 / 50 Hz overloads board B's freewheel diodes | ADR-2026-11-20-fwsafety (d) (fans 22 Hz; s5 runs them at 22 Hz) |
| switching: PWM loss, lamp / motor on BTS7008 and lamps on BTS7004 / BTS70012 | WARN x 4 | at 100 Hz PWM a lamp may draw only 6.8 / 12.5 / 23.8 A before the PWM heat beats DC | **NOT COVERED** (no preset or UI limit for lamp PWM) |
| switching: 65 W halogen on board A | WARN | its cold start (69 A) is above the PROFET's self-limit (65 A hot): it restarts itself | **NOT COVERED** (the starter uses LED lamps) |
| switching: radiator fan inrush | WARN | a hard 5 x start (150 A) is at the BTS70012 limit (146 A hot) | partly: the fan preset soft start (s5 shows the ramp); bench (fan L / inrush) |
| switching: parallel pair B OUT3 + OUT4 | WARN | a pair trips at 52 A, not 62 A | ADR-2026-11-20-fwsafety (d) |
| mcu: PA15 JTAG pull-up on B OUT7 | WARN | for a few us after reset the wiper output's IN pin may float high; far shorter than the PROFET turn-on delay | order-readiness section 3 table (known); no ADR |
| mcu: sleep current | WARN | 3.3 mA (25 C) / 11.2 mA (85 C) for the whole PDM asleep | accept list |
| si: VDDA decoupling 7.1 nH, A and B | WARN x 2 | the new VDDA caps sit 7 mm from pin 13 | ADR-2026-11-20-hwprotect (b) (bench item) |
| dfm: via-in-pad A / B / IN | WARN x 3 | vias inside pads | ADR-2026-11-20-presim-findings (5) / hwprotect (c): ordered filled + capped |
| dfm: thin silk A / B / IN | WARN x 3 | cosmetic | accept list (pcb-verification Left 5) |
| dfm: 3D clash baseline | WARN | the tool compares with old board STEPs (94adcc4) | enclosure re-checked on the current boards (order-readiness section 5, revF); tool baseline stale |
| layout: crystal ground, I2C rise 304-306 ns, U3 +5V cap 69-71 mm (A and B) | WARN x 8 | stock dingoPDM layout items | accept list (pcb-verification Left 5) |
| copper: self-heating A (10.0 K) and B (47.3 K) | FAIL x 2 | at every output at rating with no sink the copper heats past the screen line | ADR-2026-11-22-copper (worst cases, not blockers) + ADR-2026-11-20-boardb-feed (150 A cap) |
| thermal_box: 150 A on B, fans failed (3 splits) | FAIL x 3 | laminate 131.7-133.1 C over 130 C | ADR-2026-11-20-boardb-feed + fwsafety (c): board B cuts at 104 C first (transient PASS) |
| thermal_box: FRAM / MCU at 150 A, fans failed | FAIL x 2 | 121 C local, over the 105 C rating | same: the 104 C cut comes first |
| thermal_box: FRAM / MCU at 150 A, fans on | WARN x 2 | 106 C local vs 105 C | ADR-2026-11-20-fwsafety (c) (binding limit) |
| thermal_box: input-board DIP switches at 150 A | WARN x 2 (main bc32eca: WARN 75 C + FAIL 81 C) | lid air 74 C (fans on) / 79 C (failed) vs the Omron A6S 70 C rating (car loads: 69.3 C) | **NOT COVERED** (parts-audit 10 lists options, no decision) |
| thermal_box (main bc32eca): UI hot-spot offset | FAIL | the new heat map's largest laminate offset is 20.0 K, the UI constant `PdmThermal.BoardBLaminateOffsetK` is 19.6 K | **NOT COVERED** (new with the merged thermal model: set the constant to 20.0 K and re-run the UI thermal tests) |
| thermal_box (main bc32eca): 150 A fans failed, part ratings | FAIL x 5, WARN x 6 | the new model runs hotter with the fans failed (board B sensor 128-131 C, laminate 139-142 C; 5 V module, crystals, X7R caps 128 C) | as above: board B cuts at its sensor's 104 C first (fwsafety c, boardb-feed); re-check the transient with the new model |
| spice: ISO 7637-2 pulse 1 | WARN x 2 | -29 to -32 V on +12 V | accept list (BACKLOG hwfix) |
| spice: 8 inputs at 14.4 V into +3V3 | WARN | 27 mA pushed into +3V3 | accept list (pcb-verification Left 4) |
| spice: analog 5 V at 125 C | WARN | reads 3 % low | bench list; analog via ECU (Dan 2026-11-08) |
| spice: three 120R on the bus | WARN | a closed PDM termination jumper weakens CAN | Dan 2026-11-08 (termination install-specific) + order-checklist: JP1 open |
| s5: CAN-Lambda inrush (XFAIL) | XFAIL | trips at key-on, latches | **NOT COVERED** (proposal above) |
| s5: hot day board A cut | finding | lamps / cluster off at the estimated 84.6 C | partly: fwsafety (c) / BACKLOG board A model; the consequence is new |
| s5: radiator fan off at ECU loss | finding | fan off while the engine may be hot | **NOT COVERED** |
| s5: condenser fan after key off, no auto sleep | finding | 30 A fan on with the key off | **NOT COVERED** |
| s5: A/C momentary on the keypad | finding | A/C only while the button is held | **NOT COVERED** |

## 4. How to run

- s5: `python3 firmware/sim/s5_drive_cycle.py <sim out dir> [--out dir] [--json file]`; `--mutants` runs the 12
  mutations (each in its own process and .so copy, expect 12 of 12 RED); `--proposals` applies the XFAIL fixes
  (expect every XFAIL to XPASS); `--hot-a C` sets board A's hot-day temperature. About 25 s.
- Starter values: `dotnet test ui\tests\CustomPdm.Tests --filter StarterParamsExportTests` checks the file; with
  `CUSTOMPDM_WRITE_STARTER_PARAMS=1` it writes it (after the starter changes).
- The rest: `AGENTS.md` "Commands" and `automation.yml`.
