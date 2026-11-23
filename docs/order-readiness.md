# Order readiness - PCB order (job finalcheck, 2026-11-22)

Checked: `main` 743d816 (ADR-2026-11-20-presim: run every simulation and test before ordering). Every row below was
run in this job on DansPC, from own scratch copies (WSL `~/scratch/finalcheck`, `%TEMP%\finalcheck`, worktree
`.claude\worktrees\finalcheck`); nothing was fixed here. "Known" = already accepted in DECISIONS / docs (cited).

## Verdict

**READY to order (updated 2026-11-22, job orderprep).** The one open choice is made: Dan chose a) board B with
**1 oz outer + 1 oz inner copper** (2026-11-22, c1 = a), and the coordinator set the same for board A (Dan delegated
the copper recommendation; reason in the board A row below). How to place the three orders, field by field:
`docs/order-checklist.md`.

What job orderprep changed after this report (PR "chore: order prep"), and what it proved:

| Item | Result |
|---|---|
| Ordered copper, one table (`tools/copper_order.py`) | A 1 oz / 1 oz, B 1 oz / 1 oz, input 1 oz (JLCPCB default); fab notes, KiCad stackups and the table agree (`copper_order.py --check` PASS); the copper and heat checks now run at the ordered copper by default, another thickness is a labelled what-if run |
| Board B heat at the ordered copper (`thermal_board_b.py --res 0.3`, fans on, 60 C cabin) | 150 A: 116.5 / 118.2 / 116.7 C (limit 130 C) PASS; car loads 109.5 C PASS; every output at rating (184 A) 146.8 C FAIL as before (the 150 A cap stays) |
| Board B, fans failed | 150 A: 131.7 / 132.5 / 133.1 C (was 135.9-137.3 C at the KiCad copper); car loads 120.2 C. The 104 C cut still comes first |
| Board B `verify_copper.py` at the ordered copper | +12V 95.2 mV / 12.8 W at 184 A (limit 100 mV) ok; the no-sink screen still FAILs (47 K), as before: the sink model above is the judge |
| Board A `verify_copper.py` at the ordered copper (35 / 35 um) | every drop ok (outputs <= 2.8 mV, +12V 51.6 mV, 2.79 W); the no-sink hot-spot screen reads **10.02 K against the 10 K limit** (peak 30.2 K, board mean 20.2 K): over by 0.02 K, so the tool still prints FAIL. At JLCPCB's default 0.5 oz inner it read 11.9 K, which is why board A is ordered with 1 oz inner too (coordinator, 2026-11-22). The screen has no heat sink; board A sits on the sink and keeps its 55 / 80 C limits |
| Board B sensor map and firmware limits | laminate = U6 + 10.1 .. 19.6 K (was 9.6 .. 19.0); warn 98 / critical 104 / recovery 6 C **unchanged** (at 104 + 1 C: laminate 124.6 C, Tj 125.4 C; the binding limit is still the 105 C MCU / FRAM rating); UI hot-spot offset 20 -> 21 K |
| Board A 85 C parts (section 7 "worth a look") | done: Y1, C3, C4, C6, C14, C38 now carry board B's 125 C crystal and X7R parts (fields only, same footprints) |
| No-LCSC parts | A: Y1; B: Y1, T1-T8: marked for global sourcing in the BOMs and fab notes; thin-stock table in each `fab-notes.md` |
| Stale tool rows | `verify_mcu.py` watchdog row now reads the real IWDG start (18 PASS, 2 WARN); `verify_thermal_box.py` reads the part grades from the BOMs (27 PASS, 4 WARN, 5 FAIL: 3 x fans-failed 150 A laminate, FRAM / MCU at fans-failed 150 A) |
| Board checks vs this report | KiCad DRC / parity / ERC counts identical (A 89 errors, B 209, IN 0; ERC 29 / 80 / 0); JLC-limit DRC no violations; no new FAIL in any `verify_*` tool |

Still to do at order time (no design change): section 7 list, now written out step by step in `docs/order-checklist.md`.

The text below is the finalcheck record of 2026-11-22 as it was before these changes (its copper question is answered above).

## 1. Firmware (LF `git archive main`, own scratch HOME, WSL)

| Check | Expected | Got | Verdict |
|---|---|---|---|
| 4 builds (`build_wsl.sh`: custompdm_a unit 1 / 2, custompdm_b, dingopdm_v7) | 4 OK, only the linker RWX warning | 4 OK, 1 warning each: "LOAD segment with RWX permissions" | PASS |
| Stock `dingopdm_v7.bin` md5 | fbe414ba... | fbe414ba90f541c714e8fd7e99589691 | PASS |
| Host sim S0 board audit | 76 of 76 | 76 of 76 | PASS |
| Host sim S4 CAN system | 10 of 10 | 10 of 10 | PASS |
| Host sim S1 system | 91 of 91 | 91 of 91 | PASS |
| Host sim S3 features | 111 of 111, 0 XFAIL, exit 0 | 111 of 111, 0 expected failures, exit 0 | PASS |
| Renode bench (`run_bench.sh --build`, firmware built from 743d816) | 39 of 39 | 39 of 39, "Tests finished successfully" | PASS |

Note: S4 also needs `docs/car-can-dummy` beside `firmware/` in the archive (`git archive main firmware` alone stops with
FileNotFoundError); the AGENTS.md command line does not say so.

## 2. UI

| Check | Expected | Got | Verdict |
|---|---|---|---|
| `dotnet build ui\dingoConfig\dingoConfig.sln` | builds | 0 errors, 2 warnings | PASS |
| `dotnet test ui\tests\CustomPdm.Tests` with a sim `.so` built from main in the scratch | 435 passed | 435 passed, 0 failed, 0 skipped (1 m 3 s) | PASS |
| `DbcGen -- --check` | committed DBC / dummy files = generator | all "same", exit 0 | PASS |
| Launcher `Start-PdmUi.ps1 -SelfTest` | passes, starts nothing | 14 ok, "Self-test passed." | PASS |
| Dan's play app | untouched | still listening on 5000 and 3333 after the run | PASS |

## 3. Boards

### 3.1 Regenerate from the generator stages (detached worktree, `build_board_a.ps1`, `build_input_board.ps1`, `build_board_b.ps1`)

| Check | Expected | Got | Verdict |
|---|---|---|---|
| Three builds | exit 0 | A, IN, B exit 0 | PASS |
| Text diff vs committed | ID / order churn only (hardware.md) | 13 files differ as text | expected |
| Netlist (kicad-cli 10 export, compared by net -> pins and part -> value / footprint / fields / DNP) | equal | A 139 nets / 145 parts, B 190 / 209, IN 36 / 50: all identical | PASS |
| `board_semdiff.py` board A, input board | no difference | 0 tracks / vias changed, 0 footprint geometry differences | PASS |
| `board_semdiff.py` board B | only router variance | 0 footprint differences; 13 track segments of B_IN6 / B_IN8 routed differently (the hwprotect re-route on In2, docs/pcb-verification.md "hwprotect"); one mask-zone list in another order | PASS (known variance: BACKLOG hwfix 2026-11-20 "differs run to run") |
| DRC + parity and ERC of the rebuilt boards vs committed (kicad-cli 10, all severities, counts by type) | equal | equal for all three boards, DRC and ERC | PASS |
| Fab outputs from the rebuilt boards vs committed (Gerber compared as a set of drawn shapes) | same image | drills, BOM, CPL, notes, JLC DRC text identical; 27 of 31 Gerber layers the same image; B In2 (18 segments + 1 fill), B F.Cu, IN F.Cu, IN B.Cu (1 fill outline each) differ | PASS (same variance; fill outlines) |

### 3.2 Rule checks on the committed boards

| Check | Expected (docs/pcb-verification.md) | Got | Verdict |
|---|---|---|---|
| KiCad DRC board A | 0 unconnected; stock-pattern errors only (56 clearance, 20 annular, courtyard, 6 starved thermal) | 0 unconnected; 89 errors: clearance 56, annular 20, courtyard 7, starved thermal 6; 136 warnings (129 library path) | PASS, known (courtyard 7 vs 4 in the doc: D2 / new parts, BACKLOG 2026-11-19 "Small, hardware") |
| KiCad DRC board B | 0 unconnected; 101 track width, 56 hole clearance, 20 annular, 7 clearance, 10 courtyard, 10 starved | 0 unconnected; 209 errors: same counts, courtyard 13, text 2 | PASS, known (courtyard 13 vs 10: same BACKLOG line) |
| KiCad DRC input board | 0 errors | 0 errors, 50 library-path warnings | PASS |
| Schematic parity | 4 'Datasheet' field notes on A and B, 0 on IN | 4 / 4 / 0 | PASS |
| KiCad ERC | A 30, B 81 pin-type errors (minus 1 each after hwprotect); IN 0 | A 29, B 80, IN 0 | PASS, known |
| `gen_fab_jlcpcb.py` JLC-limit DRC + hole check | no violations, no co-located holes, refill 0.000 % | no violations on all three; holes on the same spot: none; refill 0.000 % | PASS |
| `gen_fab_jlcpcb.py` re-run on the committed boards | `git diff --exit-code hardware/fab` = 0 | exit 0 (identical content) | PASS |
| `verify_cpl.py` | every placement on its pads | A 129 (125 ok + 4 symmetric), B 194 (177 ok + 16 symmetric + 1 "check": Y1 has no LCSC number, 2-pad crystal), IN 48 ok; RESULT PASS | PASS (docs still say 126 / 191: counts grew with the 5 V module parts) |
| `verify_dfm.py` | 8 PASS, 6 WARN | 7 PASS, 7 WARN, 0 FAIL: via-in-pad 58 / 151 / 27 (ordered filled + capped), thin silk lines 358 / 611 / 168, 3D clash "15 / 16 footprint changes since 94adcc4" | PASS; WARNs known (ADR-2026-11-20-presim-findings 5; enclosure re-checked since: section 5) |
| `verify_layout.py` | PASS with WARN: crystal keep-out, I2C 10k, no cap at U3 VDD | RESULT PASS; 8 WARN: exactly those on A and B (I2C rise 304-306 ns, U3 +5V cap 69-71 mm away) | PASS, known (pcb-verification "Left 5") |
| `verify_copper.py A B` (stackup copper) | A PASS; B 99.4 mV / 13.6 W at 184 A, no-sink screen FAIL (the sink model is the judge) | same: B +12V 99.4 mV, 13.62 W; 1 FAIL = the no-sink self-heating screen (59 K) | known FAIL (pcb-verification board B "+12V feed") |
| `verify_copper.py A B --outer-um 35 --inner-um 17.5` (JLCPCB default) | A "marginal" | 3 FAIL: A hot spot 11.9 K (limit 10 K), B drop 116.2 mV / 15.8 W, B no-sink screen 74 K | see section 3.3 (NEW for board B) |
| `verify_mcu.py` | 15 PASS, 5 WARN | 17 PASS, 3 WARN, 0 FAIL: pins 42 of 42 (A) and 48 of 48 (B); WARN PA15 pull-up on B IN7, sleep current 3.3 / 11.2 mA, "no watchdog" | PASS; the watchdog WARN is a stale tool check (it reads the ChibiOS HAL flags; the IWDG is driven directly in `boards/stm32f446/mcu_safety.cpp` and proven in S0 / Renode) - NEW, tool only |
| `verify_si.py` | 5 PASS, 2 WARN | 3 PASS, 2 WARN, 5 INFO: VDDA pin 13 to its new cap 7.0 mm, about 7.1 nH (limit 5 nH) on A and B | known (ADR-2026-11-20-hwprotect b: caps 11-15 mm away, bench item); docs/system-verification.md 7 still says PASS for it |
| `verify_power.py` | 24 PASS, 7 WARN, 3 FAIL | 29 PASS, 3 WARN, 2 FAIL: reverse battery through board B freewheel diodes; horn pair turn-off energy (L assumed) | known FAILs (ADR-2026-11-21-reverse-battery; ADR-2026-11-20-presim-findings 6: bench) |
| `verify_switching.py` | 15 PASS, 7 WARN, 4 FAIL | 17 PASS, 7 WARN, 4 FAIL: hard-switched motor PWM heat on BTS7004 / BTS70012, radiator / condenser fan PWM vs BYG23M | known FAILs (ADR-2026-11-20-fwsafety d: presets hold board B motor PWM at 22 / 64 / 60 Hz) |
| `verify_tolerance.py` | 23 PASS, 5 WARN, 0 FAIL | 23 PASS, 5 WARN, 0 FAIL | PASS |
| `verify_spice.py --ngspice` (WSL user-level ngspice) | RESULT PASS; WARN pulse 1, input current into +3V3, analog at 125 C, third 120R | RESULT PASS, 102 PASS lines, those WARNs only | PASS, known. Needs `SPICE_SCRIPTS` / `SPICE_LIB_DIR` set to the user-level install, else "can't find spinit" and no simulation runs (not in automation.yml) |
| `thermal_board_b.py` (stackup copper, fans on, res 0.3) | 150 A: 122.7 / 124.3 / 122.9 C; car 109.9 C; rating 157.5 C FAIL | 122.7 / 124.3 / 122.9 C; car 109.9 C; rating (184 A) 157.6 C FAIL | PASS at the feed limit; rating FAIL known (ADR-2026-11-20-boardb-feed: 150 A cap) |
| `verify_thermal_box.py` | fans-failed 150 A FAIL (136 C); board B limits PASS | 14 PASS, 6 WARN, 10 FAIL: 3 x fans-failed 150 A laminate 135.9-137.3 C; 5 part-rating rows at fans-failed or 150 A; 2 x "ABM3 crystal / X5R caps 85 C" | fans-failed FAILs known (pcb-verification Left 1: thermal limit cuts at U6 104 C). The crystal / X5R rows are stale for board B (now ECS 125 C crystal and X7R caps, ADR-2026-11-20-hwprotect a) - NEW, tool only; they still apply to board A (section 7) |


### 3.3 NEW: board B heat depends on the copper weight that is ordered

`thermal_board_b.py --case feed150 feed150hi feed150lo car --res 0.3`, fans on, 60 C cabin, limit laminate 130 C:

| Copper (outside / inside) | 150 A (three splits) | Car loads 118 A | Verdict |
|---|---|---|---|
| KiCad stackup 43.2 / 17.3 um (what every doc result uses) | 122.7 / 124.3 / 122.9 C | 109.9 C | PASS |
| JLCPCB default 1 oz / 0.5 oz (35 / 17.5 um) | 135.8 / 137.3 / 136.2 C | 112.7 C | **FAIL at 150 A**, PASS at the car loads |
| 1 oz / 1 oz (35 / 35 um) | 116.5 / 118.2 / 116.8 C | 109.7 C | PASS |
| 1 oz / 2 oz (35 / 70 um) | 102.8 / 112.6 / 113.9 C | 106.7 C | PASS |
| 2 oz / 1 oz (70 / 35 um) | 99.3 / 108.7 / 109.1 C | 103.2 C | PASS (check JLCPCB 2 oz track / gap limits first) |

With the fans failed at 150 A the JLCPCB default copper gives 153.6 / 154.1 / 155.4 C (stackup copper: 135.9-137.3 C).

Why it matters: `hardware/fab/*/fab-notes.md` says "Copper weight: Dan's choice (not set by this script)", and
JLCPCB's own 1 oz outer layer is 35 um finished, not the 43.2 um in the KiCad stackup. docs/pcb-verification.md does
run `verify_copper.py` at 35 / 17.5 um, but the heat model and the firmware's board B limits (98 / 104 C,
ADR-2026-11-20-fwsafety c) were only run with the stackup copper. Not checked here: the sensor-to-hot-spot offset at
1 oz / 0.5 oz (the 104 C cut-off may still protect the board, but the 19 K offset behind it was derived with thicker
copper). Board A at 1 oz / 0.5 oz: +12V hot spot 11.9 K over the board mean in the no-sink screen (limit 10 K;
pcb-verification already calls it "marginal"); board A has no sink model (BACKLOG fwsafety 2026-11-20).
ADR-2026-11-20-boardb-feed says copper weight goes to Dan when the model shows the layout alone does not meet the
limit: with JLCPCB's default copper that is the case, hence the question at the top.

## 4. Fab package review

Quantities for one PDM (hardware/fab/README.md; README.md "three boards"): **2 x board A, 1 x board B, 3 x input board**.

| Check | Board A | Board B | Input board | Verdict |
|---|---|---|---|---|
| Gerbers: copper layers = board layers; mask, paste, silk both sides; Edge.Cuts | 4 of 4, all present (11 files) | 4 of 4, all present (11) | 2 of 2, all present (9) | PASS |
| Drill files: PTH + NPTH; hits = PCB holes | 380 = 55 pad holes + 325 vias; NPTH 3 = 3 | 759 = 81 + 678; NPTH 11 = 11 | 148 = 12 + 136; NPTH 4 = 4 | PASS |
| Outline: Gerber = PCB = fab notes; copper inside it | 72.4 x 95.3 mm | 111.4 x 95.3 mm | 66.1 x 64.1 mm | PASS |
| BOM (full) = fitted footprints on the PCB | 136 refs; not in the BOM: G2 logo, H1-H4 holes, J3 / J4 wire pads, JP1 (no part) | 200 refs; not in the BOM: G2, H1-H4, J5 / J6, JP1 | 48 = 48 | PASS |
| Every BOM line has maker + MPN | yes (51 lines) | yes (52 lines) | yes (9 lines) | PASS |
| LCSC number on every JLCPCB BOM line | yes | **no for T1-T8 (Wurth 74650074R) and Y1 (ECS-80-18-30Q-CES-TR)**: "global sourcing" by MPN | yes | order-time step (known: ADR-2026-11-20-hwprotect a; section 7) |
| DNP parts out of the JLCPCB BOM / CPL | D3, R3, R12, U1, U14 "do not fit": out | D5, R3, U1, U12: out | none | PASS |
| Press-fit terminals not assembled | J1, J2 out of BOM / CPL, "press in after delivery" | J1, J3 out | none | PASS |
| CPL = JLCPCB BOM refs; no duplicates; all Top; rotations (`verify_cpl.py`) | 129 = 129 | 194 = 194 | 48 = 48 | PASS |
| Fab notes: 1.6 mm, ENIG, green mask, white silk | yes | yes | yes | PASS |
| Fab notes: filled + capped vias in pads (POFV) with the count | 58 vias | 151 vias | 27 vias | PASS |
| Fab notes: press-fit remark (hole 1.475 +-0.05 mm, wall copper 25-60 um, "confirm before production") | J1, J2 | J1, J3 | not needed | PASS |
| Fab notes: stackup / copper weight | "Dan's choice", not stated | "Dan's choice", not stated | "Dan's choice" | **open: section 3.3** |

Stale text, no effect on the files: hardware/fab/README.md "Check results (2026-11-16)" still lists the overlapping
holes that were fixed since (the committed `jlcpcb-drc.txt` files say none).

Parts with thin stock (alternates from `*-bom-full.csv`; live look-ups 2026-11-22):

| Part | Need (one PDM) | Stock found | Alternate |
|---|---|---|---|
| U21 / U27 TI LMZM23601V5SILR (LCSC C2868357) | 3 | [LCSC: 135 in stock](https://lcsc.com/product-detail/DC-DC-Power-Modules_Texas-Instruments-LMZM23601V5SILR_C2868357.html) (117 on 2026-11-21) | LMZM23601V5SILT C2876787: [out of stock at LCSC](https://lcsc.com/product-detail/DC-DC-Power-Modules_Texas-Instruments-LMZM23601V5SILT_C2876787.html); ADR-2026-11-21-5v-module: assembler global sourcing |
| D2 Bourns SM8S24CA-Q (LCSC C1976790) | 3 | [Digi-Key: 400, active](https://www.digikey.fi/en/products/detail/bourns-inc/SM8S24CA-Q/9920516) (the docs' 14,800 on 2026-11-20 is no longer shown) | Vishay SM8S24CAHM3/I, Panjit SM8H24CAS-AU (ADR-2026-11-20-d2-mpn) |
| U8-U11 Infineon BTS70012-1ESP | 4 | [LCSC BTS700121ESPXUMA1: 17](https://lcsc.com/product-detail/Power-Distribution-Switches_Infineon-Technologies-BTS700121ESPXUMA1_C3232444.html) (23 on 2026-11-10) | ...XUMA2 at Digi-Key / Mouser (docs/parts-audit.md P15) |
| Y1 board B ECS-80-18-30Q-CES-TR | 1 | no LCSC number: not looked up | ECS-80-18-30Q-VY-TR (105 C, LCSC C6844210) |
| T1-T8 Wurth 74650074R | 8 | no LCSC number: not looked up | none listed |

Not looked up: JLCPCB's own parts library (needs a login session); the other lines have no shortage note in
docs/parts-audit.md section 13.

## 5. Enclosure and harness

| Check | Expected | Got | Verdict |
|---|---|---|---|
| `python harness/src/enclosure_harness.py check` | all checks pass | "all checks pass", exit 0 | PASS |
| `deliverable_lock.py verify` | OK | "OK (22 locked file(s))" | PASS |
| Models release `custom-pdm-enclosure-revF\revF` MANIFEST.sha256 | every hash matches | 105 of 105 entries match; 105 files in the folder | PASS |
| Board STEPs in the release match main's boards | exported from the current boards | the enclosure cache STEPs were exported at dd90054 (`export.log`, 2026-11-21 09:37), after the last board commit 7b87706; `git diff dd90054 main -- hardware` is empty; MADE-WITH.md: "re-exported 21/11/26 (5 V module boards)" | PASS by commit; the release `Parts/CPDM-PCB-*.stp` are re-written with part numbers, so no byte compare is possible |

Note: the board B STEP export has no 3D body for U8-U11 (BTS70012: the footprint points at the upstream author's
own disk path), so the clearance model does not hold those four parts (about 1 mm tall, under the carrier).

## 6. Cross-checks

Traced by script from the committed files: docs/box-connectors.md -> harness/enclosure-wire-list.csv -> board pad net
-> PROFET channel -> U4 pad -> `firmware/boards/custompdm_*/board.h` line.

| Check | Sample | Got | Verdict |
|---|---|---|---|
| box-connectors.md vs harness CSV, every X1 / X2 wire end | 52 wire ends | 0 mismatches | PASS |
| Outputs: cavity / riser -> board pin -> PROFET -> MCU pin -> `LINE_PFn_IN` | 23 outputs: A1 OUT1-8, A2 OUT1 and OUT3-8 (X1), B OUT5-8 (X1 B / D / E / G via T5-T8), B OUT1-4 (risers T1-T4) | all 23 land on the firmware line with their own number (e.g. B OUT1: T1 -> U8 -> PB14 = PF1_IN; B OUT7: T7 -> U25 -> PA15 = PF7_IN) | PASS |
| A2 OUT2 (box fans) | not on X1 by design | fed inside the box (harness fan splices) | as designed |
| Digital inputs: X2 cavity -> (input board J2 -> J1 -> JST GH cable) -> board pin -> MCU pin -> `LINE_DIn` | all 24 | A1 / A2 IN1-7 -> DI1-7, B IN1-10 -> DI1-10, each with its own number | PASS |
| Analog inputs | 3 | A1_AN, A2_AN -> PC2 = AIN1; B_AN -> PB1 = AIN1 | PASS |
| CAN | A J3.1 / .2, B J6.1 / .2 | CAN_L / CAN_H on U3 pins 6 / 7; TXD -> PB9 = CAN_TX, RXD -> PB8 = CAN_RX on both boards; harness joins X2.2 / X2.3 to all three boards through SP1 / SP2 | PASS |
| Firmware pins vs PCB (`verify_mcu.py`) | every `LINE_*` | 42 of 42 (A), 48 of 48 (B); ADC slots 8 of 8 (A) | PASS |
| CONFIG_VERSION / param layout, firmware vs UI | consistent | firmware custom builds: 0x040A (`core/config.h`); the UI holds no version number, it talks by param index: the live tests that compare New PDM / the starter with fresh sim boards param by param pass on the sim built from main | PASS |
| ST185 starter loads and writes on a fresh sim | passes | `UiWalkLiveSimTests.TheStarterWritesToFreshBoards` passed; `UiWalkTests` starter tests (loads writable, critical settings = factory) passed | PASS |

## 7. Assumed or bench-only items

### Must fix before the order (design changes)

None. Reason: no check found a wrong net, pin, footprint, placement or fab file; every FAIL above is either accepted
with an ADR and held by firmware limits, or depends on an order option (copper), not on the design files.

### Must do at order time (no design change)

1. Choose board B's copper weight (question at the top; section 3.3).
2. Board B: T1-T8 (74650074R) and Y1 have no LCSC number: add them through the assembler's global sourcing / by MPN,
   or the BOM upload will leave 9 placements unmatched.
3. Tick filled + capped vias (POFV) and paste each board's order remark; JLCPCB to confirm the press-fit hole-wall
   copper (BACKLOG 2026-11-19 "PCB order blockers").
4. Check diode / LED polarity and D2 in JLCPCB's placement preview (same BACKLOG line; `verify_cpl.py` passes).
5. Ask about the B T1-T4 vs BTS70012 courtyard overlap at quote time (same BACKLOG line).
6. LMZM23601V5 (135 at LCSC today), BTS70012 (17 at LCSC): order soon or use the listed alternates.
7. Press the six 7461084 terminals in after delivery (fab notes); keep every CAN_TERM jumper open.

### Worth a look before the order (cheap, coordinator's call; not blocking)

- Board A still carries the 85 C crystal (ABM3) and X5R capacitors that board B swapped for 125 C grades
  (ADR-2026-11-20-hwprotect a covered board B only). Board A's 55 / 80 C limits protect them today, but the estimate
  for board A's sensor at the car loads is about 85 C (ASSUMED, BACKLOG fwsafety 2026-11-20), so raising its limit
  later would be blocked by these parts. Same footprints: a BOM-field change, no layout change.

### Accept for a first board spin (known, with its home)

- Not reverse-battery protected: board B freewheel diodes short a reversed battery (ADR-2026-11-21-reverse-battery).
- Board B motor PWM held to 22 / 64 / 60 Hz by presets; a paired output is rated 52 A (ADR-2026-11-20-fwsafety d).
- 150 A with the fans failed runs the laminate to 136-137 C; every output at rating (184 A) 158 C: the 150 A cap and
  the 98 / 104 C limits must stay (ADR-2026-11-20-boardb-feed, pcb-verification Left 1).
- Board A keeps the stock 55 / 80 C limits: no board A heat model (BACKLOG fwsafety 2026-11-20).
- ISO 7637-2 pulse 1 reaches -29 to -32 V on the supply (WARN, BACKLOG hwfix); pulse 3a puts 216 V on a 0603 input
  resistor (WARN).
- Inputs at battery voltage push up to 27 mA into +3V3 while a board sleeps (pcb-verification Left 4).
- Stock-inherited: no 100 nF at the CAN transceiver, I2C pull-ups 10k (rise 304-306 ns), no ground under the crystal,
  thin silk lines (pcb-verification Left 5); VDDA caps 11-15 mm away, USB ESD at the MCU end
  (ADR-2026-11-20-hwprotect b).
- Sleep current model 3.3 mA (25 C) / 11.2 mA (85 C) for the whole PDM; EXTI wake from STOP not tested in Renode.
- Enclosure revF: USB pigtail part numbers, some drawn best-guess connector bodies, the 10 mm stub behind X1 / X2
  (ADR-2026-11-22-enclosure-revF); harness-side contacts and plugs short at distributors (parts-audit P16).
- Fusion's own ERC / DRC was never run (KiCad + JLC-limit checks cover the same rules; pcb-verification item 5).

### Bench tests after the boards arrive (BACKLOG presim / fwsafety / hw5v / hwprotect / fwkilis lines)

- Loads: inductance of the horn, solenoids, radiator fan, pump (horn turn-off energy FAIL with assumed L; PWM limits).
- Heat: U6 vs thermocouples at the hot spots at the car loads and 150 A, fans on / off; board A temperatures; 5 V
  module case temperature; model assumptions (h top, J1 / BATT bar path).
- Supply: start-up and CAN at 6 V cranking; BOR level 3 sweep and the first-start option-byte write; 5 V module
  start-up; +5 V at -40 C.
- Watchdog: LSI timeout per board, longest refresh gap with every feature on, Write All and Burn.
- Sleep: current with the RTC wake-ups; wake from STOP by input / CAN / USB.
- Current sense: ADC raw with a forced PROFET fault and at 20 A on board A, cold and hot; battery sense near the top.
- Inputs: +1 V ground offset; analog accuracy near 5 V.
- CAN: Link ECU sample point; main-loop period with every feature on.
- EMC: ADC noise, ESD gun, CISPR 25 conducted / radiated; board B In1 +12V band under F.Cu signals.

## Not run / limits of this pass

- Fusion (ERC / DRC, linked design): not used, as instructed.
- Enclosure v2c full rebuild (`build_check_all.sh`): not re-run; the locked release and its manifest were verified.
- JLCPCB's own stock and placement preview: need the order session.
- Tool notes for the coordinator (no fix made): `verify_mcu.py` watchdog row and `verify_thermal_box.py` part list are
  stale; docs/system-verification.md and docs/pcb-verification.md section counts are older than today's tool output;
  `verify_spice.py` on DansPC needs the two SPICE_* variables; S4 needs `docs/car-can-dummy` in the archive.
