# Confidence report - are the boards worth ordering?

Job confidence, 2026-11-23, on `main` a422adf. Written for Dan's go / no-go (c7 = a, ADR-2026-11-23-order-gates).
Question (Dan, 2026-11-23 09:01): "I'm not satisfied yet that we've proven it will work beyond reasonable doubt. How do
I know these boards are worth ordering at the cost and minimum order quantities required?"

Method: the design-harness rule "claim -> evidence -> gap" (living-relation/design-harness fork, `SKILL.md`: every
claim stands on traceable evidence; the human makes the call). Each row below says what we claim, what proves it,
and what is still not proven. Nothing here is new testing: every number is quoted from the doc or PR named next to it.
Marks: **ESTIMATE** = my own figure with no quote behind it; **TBD** = not known yet.

## The short answer

- Everything that can be checked without real boards has been checked, most of it twice, by different tools.
  No check found a wrong wire, pin, part outline or fab file (`docs/order-readiness.md` section 7).
- What is left can only be found on a real board: real heat, real noise, real coils, real parts.
  That is normal for a first build. No amount of more simulation removes it.
- The order is already small: JLCPCB makes bare boards in lots of 5 and assembles as few as you ask for
  ("Standard PCB Assembly, where there is no restriction on quantity", [JLCPCB FAQ](https://jlcpcb.com/help/article/pcb-assembly-faqs)).
  The full first order (one PDM: 2 x A, 1 x B, 3 x input board) is about **$650-1,100** (ESTIMATE, section 3).
- If something is wrong, the most likely fix is a setting in the PC tool, then a part swap. A new board ("respin")
  is the least likely fix; one board design re-made costs about **$280-600** (ESTIMATE).

## 1. What is proven, and how

Confidence: **high** = tested many ways, little left that a real board can change; **medium** = well modelled, but
the model rests on numbers a real board must confirm; **low** = only estimated.

| Risk area | Claim | Evidence (tool, count, PR) | What it can prove | What it cannot prove | Confidence |
|---|---|---|---|---|---|
| Power path (12 V in, copper, outputs) | The copper carries every output's current with a small voltage loss | `verify_copper.py` on the real copper at the ordered 1 oz / 1 oz: outputs 2.2-5.9 mV, +12 V feed 51.6 mV (A), 95.2 mV at 184 A (B); 3V3 start-up and 5 V module in SPICE; 6 V crank keeps CAN, outputs and MCU (`verify_power.py` 29 PASS / 3 WARN / 2 FAIL) | Copper sizes, voltage drop, rail start-up on paper, data-sheet limits stacked | Real solder joints, real terminal contact, the 5 V module's real start-up with all its capacitors (model ASSUMED loop) | Medium |
| Current sense | Each output reads its current within about 6-7 % and trips within 6-8 % of its limit | `verify_tolerance.py` Monte Carlo, 20 000 runs per case, -40..105 C: 23 PASS / 5 WARN / 0 FAIL; `verify_spice.py` 101 PASS / 5 WARN / 0 FAIL; firmware read-back within 0.3 % in s5; **CAN rounding fix PR #149**: stock firmware cut every CAN current down to the whole amp (up to 1 A low on real boards too), now rounded; RED first, then s1 92 / 92, Renode 39 / 39 | The whole chain from sense pin to the number on CAN, on the real firmware | The real spread of each PROFET's sense ratio (kILIS) and the real zener knee on the fault level (BACKLOG fwkilis) | High (logic), medium (analog) |
| Protection | Shorts and overloads are cut; the board protects itself from heat, brown-out and a stuck program | PROFET short trip 65-238 A then firmware retries (`verify_switching.py`); s3 111 / 111 (trip time, retries, latch); brown-out level 3 and a watchdog built and tested (fwsafety, s0 76 / 76, Renode 39 / 39, 12 of 12 mutants RED); load-dump TVS SM8S24CA in SPICE | Firmware reaction and timing; data-sheet margins | Coil turn-off energy (horn FAIL with an ASSUMED 5-30 mH; needs the real L); reverse battery is **not** protected (accepted, ADR-2026-11-21-reverse-battery); ISO pulse 1 WARN | Medium |
| Thermal (incl. PR #148) | No part goes over its rating at any load the firmware allows, fans on | Two separate models: Elmer whole-box FEA (mesh-checked to 0.3 K) and finite-volume board models on the real copper. **PR #148 (hwtemp)**: 125 C FRAM, TI 5 V module loss from TI data (0.131 W), board A limits 98 / 104 C, input-board solder jumpers for the 70 C DIP switches. Board B at 150 A: 116.5-118.2 C laminate (limit 130 C). Dan's car, everything on at night in rain (57 A total): B laminate 87-91 C, B sensor 72-75 C (critical 104 C) | Heat flow, part temperatures, firmware limits that cut before a part overheats | Real heat-transfer numbers (air on the board top, gap-pad squeeze, terminal path: ASSUMED in the model); fans failed at 150 A runs hot (the 104 C cut must act first); the Fusion heat cross-check is still open | Medium (high margin at Dan's real car loads) |
| CAN + firmware logic | The firmware does every PDM function right and keeps CAN timing | Real dingoFW code built for the host sim: s0 76 / 76, s1 92 / 92, s3 111 / 111 (pro-PDM feature parity, 0 XFAIL), s4 10 / 10 (bus timing, worst load 27 %); real ARM binaries in Renode 39 / 39; mutation tests (one-line bugs planted) caught every time; stock dingopdm_v7 binary unchanged (md5 fbe414ba) | Logic, timing, settings, saves, restarts, CAN timing on paper | Real CAN error frames, interrupt timing, the MCU's STOP sleep and wake (Renode cannot emulate STOP), the real crystal | High |
| Multi-board sync | Three boards act as one PDM; losing one board does not upset the others | s1 link-loss matrix; s4 board B unplugged 3 s (A1 / A2 unaffected, B back in 2.2 ms); s5 drive cycle 34 / 34 (all 24 outputs checked every 1 ms for 220 s, 16 of 16 mutants RED) | Message timing, link-loss reaction (about 1 s), restarts, sleep and wake on CAN | Real cable lengths, a real noisy bus | High (in sim) |
| UI (incl. one-PDM guards) | The PC tool sets all three boards as one PDM and blocks unsafe writes | `dotnet test` 486 / 486 with the live sim (carsim, PR #150); one-PDM guards (ADR-2026-11-23-onepdm-integrity): no writes to an overlapping CAN block, Write All / Burn off while bit rates differ, critical values need Unlock | Every screen action against the real firmware logic | A real USB-CAN adapter and real boards (only the simulator bridge so far) | High |
| Manufacturing | The fab files are right for JLCPCB | KiCad DRC 0, ERC 0, schematic-PCB parity 0 on all three boards, each waived item with its reason (`docs/drc-erc-review.md`); JLCPCB-limit DRC 0 and drilled-hole check (`gen_fab_jlcpcb.py`); every part lands on its pads in JLC's own footprints (`verify_cpl.py` PASS); Fusion import: same parts, nets, layers, outline; no new real defect (`docs/fusion-electronics-check.md`) | Rules, holes, placement, BOM / CPL match | JLCPCB's own DFM review, global-sourced parts (T1-T8, Y1), press-fit hole wall copper (they confirm at order) | High |
| Mechanical fit | The boards fit the enclosure with clearance | Enclosure revF build checks (overlaps, clearances, lugs, BOM / part files, CNC) PASS, release hash-checked 105 / 105; board STEPs exported from our own KiCad files | Fit and clearance in CAD | Real part heights; U8-U11 (BTS70012) have no 3D body in the board STEP (about 1 mm tall, under the carrier) | Medium-high |
| EMC (noise) | The boards will not upset the car and the car will not upset them | Estimates only: CAN / USB pair lengths short (PASS), PWM spectrum envelope, decoupling loops; VDDA caps 7 mm away (WARN, ADR-2026-11-20-hwprotect b) | Rough size of the problem | Any real emission or immunity number (CISPR 25, ESD gun) | Low |
| Connectors / wiring | Every wire goes to the right pin and each contact carries its load | Script trace box connector -> wire list -> board pad -> PROFET -> MCU pin -> firmware line: 52 wire ends, 23 outputs, 24 inputs, 3 analog, CAN: 0 mismatches (`docs/order-readiness.md` 6); `enclosure_harness.py check` PASS; per-contact rating rule (DECISIONS 2026-11-09) | Wiring on paper, end to end | Crimp quality, the real harness | Medium-high |
| Car integration (incl. ECU loads, ECU power hold) | The PDM runs Dan's ST185 safely | s5 car cycle 32 / 32 with the full car config, 13 of 13 mutants RED (`docs/simulation-index.md` 5); ECU loads stay on the ECU's own relays (ADR-2026-11-23-ecu-loads); ECU-held feeds follow the K-EFI hold signal, never PDM timers or sleep (ADR-2026-11-23-ecu-power-hold), shown in s5 car (37 s after-run, nothing cut); every PDM limit is at or under the OEM fuse it replaces (Toyota 1992 EWD power source page: HEAD 15 A, STOP 15 A, TAIL 15 A, TURN 10 A, WIPER 20 A, RTR 30 A, DEFOGGER 30 A, st185-celica-repair-manual) | That the config logic does what the car needs, with fuse-safe limits | The car config and Link CAN values are DUMMY (ADR-2026-11-23-link-can-dummy); real lamp / motor currents and the pop-up limit contacts are TO CHECK (BACKLOG carsim) | Medium |

Two things worth saying plainly:

- The firmware and the PC tool are the most proven parts: they run the real code against modelled hardware, and
  planted bugs are caught. The hardware is proven only on paper and in models.
- Dan's car uses far less than the PDM's limits: everything on at night in the rain is about 57 A in all, 41 A on
  board B (`docs/simulation-index.md` 5), against a 150 A board B feed limit. Heat is the biggest model risk, and
  Dan's car sits far inside it.

## 2. What only real hardware can prove

### 2.1 The bench list, ranked by what a failure would cost

Impact classes: **respin** = a new board order; **part swap** = a different part in the same spot (BOM change, the
boards can be reworked by hand); **config** = a setting or firmware change, no hardware change. "Likely fix" is the
cheapest fix that would work, from the doc named.

| Rank | Item to measure | If it fails | Likely fix | Where it comes from |
|---|---|---|---|---|
| 1 | 5 V module (TI LMZM23601V5, new on A and B) starts with all its capacitors and stays cool | Board logic has no power | Respin of A and B (worst case); first try: fewer / smaller output caps by hand | BACKLOG hw5v 2026-11-21 (model asks 0.45 A at soft start vs 1.0 A limit, loop ASSUMED) |
| 2 | Board B new +12 V feed copper and terminals at high current: U6 vs thermocouples at 40 / 80 / 150 A, fans on and off | Runs hotter than the model | Config first (lower the 150 A cap or the 98 / 104 C limits: the car needs about 41 A on B); respin only if it is far off | BACKLOG hwfix 2026-11-20, presim bench line |
| 3 | Press-fit terminal holes and REDCUBE T1-T8 joints | Loose terminal, hot joint | Bare-board respin with the same files (hole size / wall copper), or the fab fixes it | `docs/order-checklist.md` remark; BACKLOG "PCB order blockers" |
| 4 | Current-sense chain on real silicon: ADC raw with a forced PROFET fault and at 20 A on board A, cold and hot | Reads wrong or misses a fault | Config (kILIS, full-scale level 3071); part swap (zener) at worst | BACKLOG fwkilis 2026-11-20 |
| 5 | Coil turn-off energy: horn, solenoids, fan and pump inductance (LCR meter) | Horn on A1 OUT5 overloads the BTS7008 clamp at turn-off | Harness or config: move the horn to board B (freewheel diode) or add a diode at the horn | ADR-2026-11-20-presim-findings 6 |
| 6 | VDDA decoupling (7 mm away) and ADC noise; ESD gun; CISPR 25 | Noisy readings, or the car radio hears it | Config (filtering, PWM frequency) first; respin only if severe | ADR-2026-11-20-hwprotect b |
| 7 | Watchdog timeout per board (real LSI), longest refresh gap with every feature on; BOR level 3 write on first start | Resets in use, or no brown-out protection | Config (firmware timing) | BACKLOG fwsafety 2026-11-20 (1), (2) |
| 8 | Sleep current with RTC wake-ups; wake from STOP by input / CAN / USB | Battery drains over weeks, or no wake | Config (firmware) | BACKLOG fwsafety (3); model 3.3 mA at 25 C |
| 9 | CAN with the Link ECU on the real bus (sample point), main-loop time with every feature on | Lost frames | Config (bit timing) | BACKLOG presim bench line |
| 10 | 6 V crank start, +5 V at -40 C, ISO pulse 3a on an input, +1 V ground offset on an input | Reset in cranking, wrong input | Config or part swap (0603 resistor size) | BACKLOG presim, hw5v |
| 11 | Real car loads: lamp, pop-up motor, window, defogger currents; pop-up limit contacts | A limit set too low or too high | Config (preset limits) | BACKLOG carsim 2026-11-23 |

Only items 1-3 can force a new board, and item 2 has a cheap way out (a lower current cap still covers the car).

### 2.2 How much risk is inherited, and how much is ours

Our boards start from two published designs by Cory Grant: dingoPDM v7.5 (board A, MIT) and dingoPDM-Max (board B).
We hold no test reports or field data for them (TBD), so "inherited" means "built and used by its designer", not
"proven by us". The schematic netlists were compared part by part and pin by pin against the stock baselines in git
(542b3b9 board A, fe19c28 board B; `kicad-cli 10` netlist export, this job):

| Board | Stock parts | Ours | Same part and value | Added | Removed | Value / part changed |
|---|---|---|---|---|---|---|
| A (x 2) | 156 | 145 | 117 (81 %) | 12 | 23 | 16 |
| B | 140 | 209 | 116 (56 %) | 80 | 11 | 13 (0 stock parts re-wired) |
| Input board | none (new) | 48 | - | 48 | - | - |

Every changed circuit:

| # | Circuit | Board | What changed | Why | Proven by |
|---|---|---|---|---|---|
| 1 | Output stage | A | Two BTS700n singles (U8, U9) -> one BTS7008-2EPA dual at U8 (adds DSEL and IN1, J3 re-pinned); U9 and its sense / freewheel parts gone | 8 outputs per board (DECISIONS 2026-11-08) | Same TSDSO-14 footprint family; s0 / s3, SPICE, `verify_copper` |
| 2 | New 15 A output rail | B | Four BTS7004-1EPP (U23-U26) with their sense buffer U22, sense parts, freewheel diodes D25-D28, terminals T5-T8; copied from the stock BTS700n sheet | 8 outputs on board B (G1a / F1a) | ERC / DRC 0; SPICE sense chain; s0 / s1; copper and heat models |
| 3 | Output terminals | B | DT connector J4 -> eight Wurth REDCUBE T1-T8 | One wire per output (I1a, J1a) | Copper model; enclosure fit; bench item 3 |
| 4 | +12 V feed copper | B | In1 / In2 +12 V pours, 135 extra vias | Heat at 150 A (ADR-2026-11-20-boardb-feed) | `verify_copper`, `thermal_board_b`; bench item 2 |
| 5 | Current-sense buffer | A, B | LM324 -> TLV9004 (rail-to-rail); clamp zeners 3.3 V -> 5.1 V; board A's 3 unused channels tied off | Old buffer clipped at 8.2 A (ADR-2026-11-20-is-buffer); floating inputs (ADR-2026-11-23-tlv-unused) | SPICE -40..125 C, tolerance Monte Carlo; bench item 4 |
| 6 | 5 V supply | A, B | Traco TSR 1-2450 -> TI LMZM23601V5 module + 3 caps | 125 C part for the hot box (ADR-2026-11-21-5v-module) | SPICE (averaged model), heat model; bench item 1 |
| 7 | 3.3 V regulator | A, B | LD1117 -> TLV1117LV (same footprint), 10 uF -> 4.7 uF X7R, OR diode -> PMEG2010AEH | Low dropout at 6 V crank (parts-audit P11) | `verify_power`, SPICE start-up |
| 8 | CAN transceiver | A, B | PCA82C250 -> MCP2562FD; 120 R termination on an open solder jumper | 3.3 V logic, wake on bus (parts-audit C3, C7) | s4, SPICE termination, `verify_mcu`; bench item 9 |
| 9 | Config memory | A, B | MB85RC256V -> CY15B064J-SXE (125 C) | Heat (PR #148) | Same pins / address; s0 FRAM tests |
| 10 | Input surge diode D2 | A, B | SMCJ20CA -> SM8S24CA, new spot with new copper | Alternator load dump (ADR-2026-11-20-tvs-loaddump) | SPICE ISO 16750-2, enclosure clearance |
| 11 | Extra inputs | A, B + input board | MCU pins to a JST GH header (A J6, B J7) and a new input board (protection, pull jumpers) | More inputs (2026-11-08 / 11-09) | `verify_mcu` 42 / 42 and 48 / 48 pins, SPICE inputs, s0 inputs |
| 12 | Protection adds | A, B | NRST 100 nF, VDDA 1 uF + 100 nF, USB ESD diodes | Stock gaps (ADR-2026-11-20-hwprotect) | `verify_si` (VDDA WARN), DRC |
| 13 | MCU grade, crystal, caps | A, B | STM32F446RET7 (105 C grade), 125 C crystal, X7R caps (same footprints) | Heat (parts-audit C4, hwprotect a) | `verify_thermal_box` part rows |
| 14 | Removed | A, B | Test points, logo, SWO trace pin | Room for the inputs | parity / ERC 0 |
| 15 | Firmware | all | Generated custom board folders (pins, limits, safety, rounding), features behind custom options | - | s0-s5, Renode; stock binary byte-identical |

In plain words: board A is mostly the stock design with a few same-footprint part swaps and one new output chip.
Board B keeps every stock circuit wired as stock, and adds a lot (a whole 4-output rail, terminals, new feed copper).
Board B carries the most new risk. Circuits 5 and 6 are new on both main boards, so a fault there would hit both.

## 3. The cheapest way to get physical proof

### 3.1 What drives the cost

- Bare boards: JLCPCB makes them in lots of 5 per design (`docs/order-checklist.md`), so spares come free-ish.
- Assembly: you pick how many of the 5 get parts; Standard PCBA has no minimum
  ([JLCPCB FAQ](https://jlcpcb.com/help/article/pcb-assembly-faqs)).
- Each design pays its own fixed assembly fees once per order: setup $25.56, stencil $8.21, handling at least
  $14.93, hand-soldering labour $3.58, confirm placement $0.45, feeder loading $1.53
  ([JLCPCB assembly price](https://jlcpcb.com/help/article/pcb-assembly-price)). The page does not say clearly
  whether feeder loading is per part type; if it is, add about $80 per main board (about 52 part lines).
  So fixed fees are about **$55-130 per design** (ESTIMATE).
- Parts per assembled board, LCSC price at quantity 1 (`docs/parts-audit.csv`, 2026-11-10 prices, before some part
  swaps): board A about $72, board B about $103 plus the eight REDCUBE terminals (no LCSC price), input board about
  $8. Call it **A $80, B $140, input $9** (ESTIMATE).
- Bare 4-layer boards with ENIG, TG155, 1 oz inner copper and filled vias in pads: **$60-150 per design for 5**
  (ESTIMATE, no quote; the exact quote needs Dan's JLCPCB login). Input board (2-layer): $10-30.
- The exact quotes are the job of the assembly-options report (docs/assembly-options, ON HOLD list).

### 3.2 The options

| Option | What you get | Cost (ESTIMATE) | What it proves | What it does not prove |
|---|---|---|---|---|
| a. Bare boards only, all three designs | 5 x A, 5 x B, 5 x input, no parts | $155-370 | The fab can make them (filled vias, press-fit holes, outline); the boards fit the enclosure; terminals press in | Anything electrical |
| b. Board B only, 1 assembled | 5 bare B, 1 with parts | $280-460 | The riskiest board: 5 V module, MCU / CAN / USB / FRAM bring-up, all three sense chains it carries, the new 15 A rail, the new feed copper and terminals at high current, heat on the sink | Board A's dual output chip, three boards as one PDM, A2's fan output |
| c. Board B only, 2 assembled | as b, with a spare | $420-600 | As b, plus a spare to push to failure (heat, short) | as b |
| d. One full PDM (the planned order) | 5 bare of each; 2 x A, 1 x B, 3 x input assembled | $650-1,100 (the coordinator's quote-page figure was $650-850, `docs/pdm-vs-relays.md`) | Everything in b, plus board A, the input boards, three boards on one bus, the whole box on the bench and in the car | Nothing more is needed for the first car install |
| e. Bare boards + hand assembly of one board at Spark | 5 bare B + parts at small quantities; Spark fits them | about $220-320 plus Spark time (ESTIMATE) | As b, if the build is good | It also tests the hand build: the 5 V module (0.6 mm pitch with a centre pad), the PROFET exposed pads and the 0.5 mm MCU need a stencil and reflow. A bad joint looks like a design fault. The assembly-options report prices this with the reel / spool rule (c8) |
| f. SMT only (assembler fits the surface parts, Spark fits the through-hole parts) | as d or b, terminals fitted by hand | saves under $20 per design | Same as d or b | Saves almost nothing; only useful if JLCPCB cannot get T1-T8 (no LCSC number) |

What this means:

- The planned order is already close to the minimum. Option b saves about $300-600 compared with d, but it skips
  board A and the three-board system test, and if b passes you then pay a second set of fixed fees and shipping for
  A and the input boards, and wait a second order cycle.
- Option b is worth it only if you want the smallest money at risk before you trust the design. Option a is a cheap
  add-on to b if you want the enclosure fit proven at the same time.
- Shipping is extra on every option (TBD, shown on the quote page).

### 3.3 First power-up plan

Tools: a bench supply with a current limit (0-16 V, at least 5 A for steps 1-6; a battery or a 150 A supply and a
load bank only for step 9), a multimeter, a clamp meter, an IR thermometer or thermocouples, an LCR meter, a
USB-CAN adapter (SLCAN, for example a CANable: `docs/ui-setup-guide.md`) and two 120 R end resistors.
CANbench (research655/CANbench) fits here: in Receive mode it loads a DBC file (needs `cantools`) and decodes every
frame live, in Transmit mode it sends frames on a timer, and it records `.asc` / `.blf` logs. Load
`firmware/dbc/custompdm_PDM.dbc` (or `custompdm_B_0x580.dbc` for board B alone). Use the PC tool over the board's
own USB port on the bench (`docs/ui-setup-guide.md`: adapter type USB) and CANbench on the CANable at 1 Mbit/s.

| Step | Do | Measure | Pass |
|---|---|---|---|
| 0 | Board unpowered; input-board jumpers set per `docs/order-checklist.md` | Resistance +12 V to GND, +5 V to GND, +3V3 to GND | No short (more than about 1 kOhm, TBD exact value from the first good board) |
| 1 | Supply 0 -> 12.0 V slowly, limit 250 mA, no loads, no CAN | Supply current; +5VP, +5V, +3V3 | Current stays under the limit and settles (TBD, about 50-150 mA ESTIMATE from the 0.22 A 5 V load); +5 V 4.75-5.25 V; +3V3 3.20-3.40 V; no part warm to the touch / IR |
| 2 | Hold BOOT, plug USB, load the custom firmware (DFU), restart | First start at 12 V | One extra reset (the firmware writes the brown-out level once, at >= 10 V); after that no reset loop |
| 3 | CANbench Receive on the board's CAN pins with both 120 R ends | Frames on the bus | msg 0 at the board's base ID (A1 0x500, A2 0x540, B 0x580) every 100 ms; device type 14 (A) / 15 (B); bus load a few % |
| 4 | PC tool: Read All | Battery voltage, board and chip temperatures | Battery within 0.55 V of the multimeter (tolerance bound); temperatures near room |
| 5 | Each output in turn with a 1-3 A resistive load, /pdm output test (2 s), limit 4 A | Clamp meter vs CAN current; output voltage drop | CAN current within 8 % or 0.6 A of the clamp meter (6-7 % tolerance + rounding); only the chosen output turns on |
| 6 | Set one output's limit to 2 A, load 3 A | Trip and retries | Cuts within its trip time, retries as set, then latches Fault; Reset faults clears it |
| 7 | Each input to ground / to 12 V | Input bits in msg 37 (CANbench) | Right bit, no neighbour bit |
| 8 | Three boards on one bus (full set only), PDM termination jumpers open | Bus load, each board's frames; unplug B | Each board in its own ID block; A1 / A2 keep running; link-loss outputs act after about 1 s |
| 9 | Board B on its sink in the enclosure, fans on: 40 A, 80 A, then 150 A total, each until steady | U6 reading vs thermocouples at the feed corridor, J1, the 5 V module, U8-U11 | Laminate at or under the model (118 A case 109.5 C, 150 A 116.5-118.2 C, both at a 60 C cabin; scale to the room) and U6 within the 21 K offset the UI uses; if hotter, lower the cap (config) |
| 10 | Key off, wait 40 s | Whole-board supply current asleep | Under about 5 mA at room temperature (model 3.3 mA for the whole PDM at 25 C) |
| 11 | Supply step 12 -> 6 V for 80 ms, then 9.6 V for 1.2 s (if the supply can) | Resets, outputs | No reset, no output change (as s5) |
| 12 | LCR meter on the horn, solenoids, fan and pump | Inductance | Horn energy under the BTS7008 limit with the measured L; else move it (bench item 5) |

Stop at the first fail, write it down (BACKLOG), and fix before the next step. Steps 1-7 need only the bench supply
and take an evening per board (ESTIMATE).

## 4. Verdict (for the go / no-go)

The design has been checked as far as it can be without real boards: the firmware and the PC tool are proven in
depth (real code, many tests, planted bugs caught), the wiring is traced end to end with no mismatch, the fab files
pass every rule check, and the heat models show a large margin at the loads Dan's car really draws (about 57 A in
all). "Beyond reasonable doubt" is not reachable on paper: the remaining risk is the normal first-build kind, mostly
the new 5 V module, board B's new copper and terminals at high current, the real sense-chain spread, coil
inductance and noise, and most of it would be fixed by a setting or a part swap, not a new board. The order is
already near the minimum (5 bare boards and 1-2 assembled per design), about $650-1,100 for one PDM (ESTIMATE).
The worst plausible cost is one board respin, about $280-600 (ESTIMATE) and one more order cycle; the less likely
worst case, a fault in a circuit shared by A and B (the 5 V module, the sense buffer), means re-making both main
boards, about the price of the first order again. My recommendation is **go on the planned full order (option d) as
the proof build**, with steps 1-8 of the power-up plan before anything goes in the car, unless Dan wants the least
money at risk, in which case board B alone (option b, about $280-460) answers the biggest questions first. The final
call is Dan's (c7 = a), once the assembly-options report and the harness cost study are in.

## Sources

- In this repo: `docs/order-readiness.md`, `docs/system-verification.md`, `docs/simulation-index.md`,
  `docs/pcb-verification.md`, `docs/drc-erc-review.md`, `docs/fusion-electronics-check.md`, `docs/heat-analysis.md`,
  `docs/order-checklist.md`, `docs/pdm-vs-relays.md`, `docs/parts-audit.csv`, `docs/ui-setup-guide.md`,
  `firmware/sim/RESULTS.md`, `BACKLOG.md`, `DECISIONS.md` (ADRs named in the rows); PR #148 (hwtemp), PR #149
  (CAN current rounding), PR #150 (carsim).
- Stock baselines: git 542b3b9 (dingoPDM v7.5) and fe19c28 (dingoPDM-Max), netlists exported with kicad-cli 10.
- Read-only repos (Dan c9 = a): living-relation/design-harness (`plugins/design-harness/skills/design-harness/SKILL.md`),
  research655/CANbench (`canbench_m1/README.md`), living-relation/st185-celica-repair-manual
  (`electrical/circuits/ewd1992-power-source.pdf`, fuse values), living-relation/PowerTuneDigitalOfficial (Link ECU
  CAN at 250 / 500 / 1000 kbit/s in `connect.cpp`; its Link config is a binary PCLink `.lcs` file, so no CAN map
  was taken from it; the PDM's car config needs no ECU frame, ADR-2026-11-23-full-pdm-car).
- JLCPCB: [assembly price](https://jlcpcb.com/help/article/pcb-assembly-price),
  [assembly FAQ](https://jlcpcb.com/help/article/pcb-assembly-faqs) (read 2026-11-23).

Not checked here: live JLCPCB prices and stock (need Dan's login), shipping, lead time.
Noticed, not changed: `docs/st185-car-config.dummy.md` still says "DIP switches SW1 / SW2" for the input-board
pulls; since PR #148 they are solder jumpers JP1-JP16 (BACKLOG line added).
