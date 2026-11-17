# Feature parity with pro PDMs (ECUMaster PMU, MoTeC PDM, Link PDM)

Goal (Dan, 2026-11-16, `DECISIONS.md` "product goal"): an open-source, affordable PDM that does every common car
job a pro PDM does. This page says, feature by feature, what our firmware (dingoFW `development` @ 14084e9 + the
custom-pdm changes, main d1026b7) can do today, which host-sim check proves it, and what is missing.

- Proof: `firmware/sim/s3_features.py` (S3, new; real firmware logic, run like `s1_system.py`), plus the older
  `s0_board_audit.py` (S0) and `s1_system.py` (S1) checks where they already cover a feature. Results: `firmware/sim/RESULTS.md`.
- "yes" = a built-in block does it; "partly" = it works by combining blocks (each combination is proven in S3) or
  only part of the vendor feature exists; "no" = not possible today.
- The four gaps proposed here (P1 P2 P3 T1) are built (job fwgaps, branch `feat/fw-gaps`, custom option
  `PRO_FEATURES`); their S3 XFAIL checks are now real checks (S3 has 0 XFAIL). "built (Pn)" in the last column.
- Vendor columns come from the manuals read on 2026-11-16 (page numbers in brackets). "n/f" = not found in the part
  of the manual read; it may still exist.
  - ECUMaster PMU manual: <https://www.ecumaster.com/files/PMU/PMU_Manual.pdf> (E)
  - MoTeC PDM user manual: <https://www.motec.com.au/hessian/uploads/PDM_User_Manual_3a926f869d.pdf> (M)
  - Link PDM knowledge base: <https://kb.linkecu.com/pdm-kb/latest/configuration> and its sub-pages `gp-logic`,
    `math-blocks`, `timers`, `gp-functions`, `wipers`, `can-setup` (L)

Counts per board (A and B): 16 virtual inputs (VI, 3 terms each), 32 conditions, 8 math blocks, 8 timers,
4 counters, 4 flashers, 32 CAN inputs, 32 CAN outputs, 2 keypads, 1 wiper, 1 starter block. Three boards = three times that.

## Matrix

| # | Feature | ECUMaster PMU | MoTeC PDM | Link PDM | Our firmware (param block) | Sim proof | Gap action |
|---|---|---|---|---|---|---|---|
| 1 | AND / OR / NOT / NOR | yes, And / Or / is False (E p.10, 123) | yes, AND / OR / False (M p.2) | yes, `&`, `\|`, `!` (L gp-logic) | **yes**: VI 0x1400, 3 terms, NOT per term, And / Or / Nor | S3 F1 "logic on output pins" | none |
| 2 | NAND / XOR | Xor (E p.123) | n/f | Xor `^` (L math-blocks) | **partly**: NAND = NOT terms + OR (1 VI); XOR = 2 VIs | S3 F1 (same check) | none: composable |
| 3 | Compare =, !=, <, <=, >, >=, bit test | yes (E p.10) | yes (M p.2) | `cmp`, GP function operator (L) | **yes**: condition 0x1500, CAN input operator 0x1300 sub 11 | S3 F1 "conditions on a CAN number" | none (note: condition bit test returns the masked value, e.g. 4, not 1; true either way) |
| 4 | isTrue / channel as input | IsTrue (E p.10) | True (M p.2) | yes | **yes**: any var-map value drives an output, VI or timer | S3 F1, S1 S2 | none |
| 5 | Toggle (push on / push off) | Toggle (E p.126) | Toggle (M p.2) | n/f (L timers "Latch" mode) | **yes**: latching mode on digital input 0x1200 sub 1, CAN input sub 13, VI sub 9, keypad button | S3 F2 "toggle" x2 | none |
| 6 | Set / reset latch | SR latch (E p.125) | Set/Reset (M p.2) | timer Latch (L timers) | **partly**: one VI reading itself, (SET OR self) AND NOT RESET | S3 F2 "set / reset latch"; S1 fan latch | none |
| 7 | Edges, changed, pulse on edge | Changed, Pulse (E p.125-126) | Pulse (M p.2) | Pulse, Holdoff (L gp-functions) | **partly**: counter edges rising / falling / both; one-shot timer on a rising edge; falling edge via a NOT VI | S3 F2 "edge pulses", "edge counter" | none |
| 8 | Hysteresis | Hysteresis upper / lower (E p.126-127) | Hysteresis (M p.2) | ADIO high / low thresholds with time (L configuration) | **partly**: 2 conditions + 1 latch VI (3 blocks; the A2 fan uses this) | S3 F2 "hysteresis"; S1 fan checks | none now; a hysteresis field on conditions would save blocks (low priority) |
| 9 | On delay / off delay / pulse | Delay true / false (E p.124), timers (E p.110) | n/f | Holdoff, Pulse (L timers) | **yes**: timer 0x1A00, OnDelay / OffDelay / PulseRetrig / PulseOneShot, level reset input | S3 F3 (4 checks) | none |
| 10 | Flasher, turn signals, hazards | Blinker module: left / right / hazard (E p.81), Flash (E p.125) | Flash (M p.2) | Pulse mode (L timers) | **yes**: flasher 0x1700 + VIs; one shared flasher keeps both sides in step | S3 F4 "left signal", "hazard" x2 | none |
| 11 | Lane-change ("comfort") flash | n/f | n/f | n/f | **partly**: one-shot timer feeding the flasher (3 flashes per tap) | S3 F4 "lane-change tap" | none |
| 12 | Counters / multi-position switch | Counter / switch (E p.113) | counters (M p.22) | Count (L timers) | **yes**: counter 0x1600, edges, min / max, wrap, reset, hold-to-reset | S3 F5 (2 checks) | none |
| 13 | Math | Sums, divide, min, max, clamp, lookup2-5 (E p.114-117) | n/f | `+ - * /`, min, max, if (L math-blocks) | **yes**: math 0x1C00, + - x / min max average, factor / offset, divide by 0 = 0 | S3 F6 "math blocks" | none |
| 14 | Lookup table 1D / 2D (fan duty from coolant temperature) | 2D / 3D tables up to 21 x 21 (E p.111-112) | n/f | n/f | **yes** (1D): 4 tables x 8 points, 0x7E00 + n (T1); 2D / 3D: no | S3 F6 "T1: 1D lookup table (5 points, interpolated) drives the fan duty", "T1: linear interpolation", "T1: held at the end values", "T1: an 8-point table", "T1: an unsorted table", "T1: 1 or 0 points", "T1: a table output is a normal var", "T1 factory default" | built (T1) |
| 15 | PWM: frequency, fixed duty, duty from a channel, minimum duty | 4-400 Hz, duty fixed or channel (E p.9, 76) | n/f in the part read | Freq / Duty param (L gp-functions) | **yes**: output sub 8-16, 1-400 Hz | S3 F7 "fixed duty", "variable duty" | none |
| 16 | Soft start | yes (E p.9, 78) | n/f | n/f | **yes**: output sub 9 / 14 (ramp ms) | S3 F7 "soft start" | none |
| 17 | Wiper: slow / fast / park / intermittent / wash | yes, modes #0-#7, delay (E p.79-80) | 5 wiring methods, park logic (M p.6-10) | yes, Duration, mist count (L wipers) | **yes**: wiper 0x1900, DigIn / IntIn / MixIn modes, 6 delays, wash cycles, swipe | S3 F8 (4 checks) | motor brake (M output 9, L tri-state): **no**, needs a low-side path (hardware), out of scope |
| 18 | Starter interlock / shed loads while cranking | n/f | starter on a 20 A output (M p.11) | n/f | **yes**: starter block 0x1800, one input, per-output disable | S3 F9 "starter interlock" | none |
| 19 | Master shutdown / safety override | n/f | Master Shutdown (M p.18, 24) | Safety Override (L configuration) | **partly**: the starter block works as one master shutdown; thermal critical shutdown with exempt mask (0x7F00 sub 3) | S3 F9; S1 S4 critical checks | none |
| 20 | Master retry (clear faults without a power cycle) | n/f | Master Retry (M p.18) | latched "until a setting changes or power cycle" (L configuration) | **yes**: master retry var 0x7F00 sub 6 (P3; factory off): its rising edge clears Overcurrent / Fault on every output | S3 F12 "P3: setting the master retry var does not clear by itself", "P3: with a shorted load ... holding the master retry var high", "P3: one rising edge clears every output", "P3 factory default" | built (P3) |
| 21 | Load shedding on battery voltage | n/f | via logic (M p.2) | Safety Override on a parameter (L) | **yes** (logic): battery voltage is var 4; condition + on-delay timer + latch VI | S3 F9 "battery load shed" | none |
| 22 | CAN input: bit mask, scaling, signed, byte order, 29-bit IDs | bit masking, 100 messages (E p.10, 87) | byte offset, bit mask, divisor (M p.20) | CAN Function (L can-setup) | **yes**: 32 per board, 0x1300 (start bit, length, factor, offset, LE / BE, signed, operator) | S3 F10 "CAN input decode", "one-byte big-endian command" | note: big-endian start bit = the MSB (DBC Motorola), see "Found" below |
| 23 | CAN input timeout, default / hold value | default before first frame, keep last or set value (E p.90) | hold previous or fixed value, initial value (M p.20-21) | n/f | **partly**: timeout -> 0; hold = timeout off; "on" via one VI | S1 link-loss matrix | job w1 (link-loss on / off / hold, start-up hold-off); not repeated here |
| 24 | CAN output streams | Cycle / Conditional / Triggered, 1-100 Hz (E p.91-95) | 4 user messages x 8 channels, condition (M p.17, 21-22) | IO Status stream (L can-setup) | **yes**: 32 signals per board packed into frames by ID, 0x2000, interval per signal; plus 38 fixed status frames | S3 F10 "CAN output stream" | conditional / triggered send: no (not needed by the car) |
| 25 | CAN keypads | 2 keypads: ECUMaster, MoTeC, Grayhill, LifeRacing (E p.9, 104) | 4 keypads, LEDs (M p.18, 29) | Keypad 1 / 2 (L can-setup) | **yes**: 2 per board (6 per PDM), Blink Marine 1-15 keys, Grayhill 6-20, LED colours / blink from vars | S3 F11 "keypad button 1" | none |
| 26 | Inrush limit + time | yes (E p.76) | filtered load tolerates inrush (M p.23) | Inrush Limit + Trip Time + Duration (L) | **yes**: output sub 3 / 4 | S3 F12 "inrush window" | none |
| 27 | Overcurrent shutdown | Max current (E p.76) | 1 A steps (M p.2, 35) | Overcurrent Limit (L) | **yes**: output sub 2; trips after the trip time (#28) above the limit, at once above the inrush limit | S0 overcurrent; S3 F12 | see #28 |
| 28 | Trip delay / I2t / thermal model | n/f | filtered Output Load, 20-50 s time constant (M p.23, 26-28) | Trip Time (L configuration) | **yes** (trip time, no I2t): 0x7D00 + o sub 0 (P1), factory 50 ms, 0 = one sample | S3 F12 "P1: a 20 ms spike to 8 A ... is ridden through", "P1: five 40 ms spikes", "P1: 8 A held ... trips 50 ms", "P1: above the inrush limit ... trips at once", "P1: trip time 0 = stock", "P1: trip time 1000 ms", "P1 factory default"; Renode "Overcurrent Trip Time 50 ms" | built (P1) |
| 29 | Retry count / delay / forever | Retry count, Retry every, Retry forever (E p.76) | Number of Retries, Retry Delay (M p.24) | Retry Limit + Delay, Fuse Mode (L) | **yes**: output sub 5 / 6 / 7 (None / Count / Endless) | S0 retry; S3 F12 "stuck 8 A load", "endless retry" | wording: our reset limit 3 = 3 trips in all (2 retries); MoTeC "3 retries" = 3 after the first trip. dingoConfig shows "3 trips in all (first try + 2 retries)" (Output Protection panel) |
| 30 | Retry count reset when the input cycles | n/f | yes (M p.24) | n/f | **yes** | S3 F12 "switching the input off between trips" | none |
| 31 | Undercurrent / open load | Min current -> UNDERCURRENT, output keeps running (E p.76, 100) | n/f | n/f | **yes**: 0x7D00 + o sub 1 min current (factory 0 = off), sub 2 time (500 ms); flag var per output (P2) | S3 F12 "P2: open load ... the flag sets 500 ms", "P2: the flag clears as soon as the current is back", "P2: no flag while the output is off", "P2: a 300 ms dip", "P2: 0.3 A for 600 ms", "P2: flag time 100 ms", "P2: an output with min current 0", "P2 factory default" | built (P2) |
| 32 | Short circuit / driver fault | yes (E p.29) | yes (M p.23) | Latch Off Fast above 60 A (L) | **partly**: the PROFET protects itself (own retries, latches after 2 retry cycles); IS at the ADC full scale is a hard overcurrent: after the inrush window it trips at once (no trip time), then retries per the output's settings | S3 F12 "driver fault", "PROFET fault after the inrush window", "PROFET fault from switch-on", "factory reset time 1000 ms" | see "Found" (`nIS > 30000`) |
| 33 | Over-temperature per output | thermal shutdown status (E p.70) | thermal overload (M p.6, 23) | Over-Temp Limit per pin (L) | **partly**: PROFET internal shutdown (hardware); board temperature warn / critical / exempt mask (custom) | S1 S4 | per-pin temperature: hardware has none, out of scope |
| 34 | Output pairing (parallel channels) | up to 3 pins (E p.8, 30, 76) | same type, common channel (M p.6, 22-23) | n/f | **yes**: output sub 17 (primary); follower mirrors on / off / PWM, primary reports the summed current | S3 F13 "pairing" | none |
| 35 | H-bridge / low-side outputs | low-side outputs (E p.34, 82) | n/f | full / half bridge (L configuration) | **no**: high-side PROFETs only | none | out of scope (hardware) |
| 36 | Analog input as a switch / rotary switch | thresholds, calibrated maps (E p.73-74) | thresholds 3.5 / 4.2 V, trigger time (M p.19) | thresholds with time (L configuration) | **yes**: 0x2200 switch threshold (no hysteresis), rotary uniform / calibrated | S3 F14 "analog input as a switch" | hysteresis: use #8 |
| 37 | Frequency / duty input | n/f | n/f | Input PWM, ADIO 5-8 (L) | **yes**: digital input PWM mode 0x1200 sub 5 (on CAN for inputs 1-6, msgs 34-36) | S3 F14 "digital input PWM" | none |
| 38 | Sleep / wake (standby) | +12V SW on / off (E p.19-20), delayed turn off (E p.135) | standby after 5 s, wake on CAN / input / stay-alive (M p.34) | Global Enable: Ignition Switch (L) | **yes**: auto sleep (all outputs off, no CAN, no USB, 30 s), force-sleep input 0x0000 sub 8, wake on CAN / USB / masked inputs (0x7F00 sub 5) | S0 sleep, S1 S6 wake, S3 F15 "force-sleep input" | outputs are all off in sleep: constant loads (dome, alarm, memory) stay on plain fuses |
| 39 | Data logging | 256 MB, 500 Hz (DL models, E p.10, 127-134) | n/f | PDM Logging page (L) | **no** | none | out of scope for this hardware (8 KB FRAM holds the config); the ECU / RealDash log the PDM CAN frames |
| 40 | Per-output safe state | n/f | n/f | Safety per output (L) | **partly**: CAN-loss policy per output (S1, job w1); all off on a fatal error; critical-exempt mask | S1 | job w1 |
| 41 | Live diagnostics on CAN | yes | yes (M p.21, 50-57) | IO Status (L) | **yes**: 38 status frames (state, current, trip count, duty, inputs, temperatures, flags) | S0, S1 | none |
| 42 | PID control | yes (E p.109) | n/f | PID page (L) | **no** | none | not needed: the ECU closes loops (fan, boost); not proposed |
| 43 | Password / config lock | n/f | yes (M p.2, 31) | n/f | **no** | none | not proposed |

Counts (43 rows): **yes 29**, **partly 10**, **no 4**. Rows 14, 20, 28, 31 were "no" and are built (below); the 4 "no"
left are out of scope (35 H-bridge, 39 logging, 42 PID, 43 password).

## Found while testing

- Big-endian CAN inputs use the DBC (Motorola) start bit: the MSB of the field. A one-byte command in byte n needs
  start bit `n x 8 + 7`; `n x 8` reads the wrong bits (S3 F10 check: start 56 reads 128 for a 1 in byte 7).
  `docs/car-can-dummy/ecu-pdm-control-plan.dummy.md` says "BigEndian ... single bytes make it moot" and "start bit =
  byte x 8": with BigEndian that is wrong; use LittleEndian with start = byte x 8, or BigEndian with byte x 8 + 7.
- `Profet::Update` checks `nIS > 30000` for a hard driver fault, but the ADC is 12 bit (0-4095, `ADC1_BUF_DEPTH 1`),
  so that branch never runs (upstream code, left as it is). Decision (fwgaps, from the BTS7008-2EPA data sheet; the
  BTS70012 / BTS7004 are the same PROFET+2 family): a PROFET fault does **not** latch in the firmware. Its fault
  current IIS(FAULT) is 4.4 mA min (P_9.6.1.1) x 1.2 kOhm = 5.3 V, so the IS pin reads ADC full scale, but so does a
  real load current above 16.4 A (A) / 55 A (B 5-8) / 96 A (B 1-4), e.g. a lamp's inrush on board A; latching on full
  scale would latch good loads. The PROFET protects itself (overload / over-temperature shutdown, own restart, latches
  off after nRETRY(CYC) = 2 retry cycles, P_8.6.1.4) and de-latches when IN stays low longer than tDELAY(CR) = 100 ms
  max (P_8.6.1.6, section 8.3.1); our retry holds IN low for the reset time (factory 1000 ms), so each firmware retry
  is a real one, and Count mode latches Fault after 3 trips. Fix in `PRO_FEATURES`: IS at full scale
  (`PROFET_IS_FULL_SCALE`, 99 % of 4095) is a hard overcurrent: after the inrush window it trips at once, not after the
  trip time (P1). Inside the inrush window nothing changed (factory inrush limit 50 A is above board A's 16.4 A full
  scale, so the firmware cuts at the window's end; the PROFET protects itself until then). S3 F12 "PROFET fault ..." x2.
- The condition bit test (`BitwiseAnd`) returns the masked value (e.g. 4), not 1. Every consumer treats non-zero as
  true, so it works; a condition "Equal 1" on it would not.
- Reset limit wording, see row 29.
- CAN output scaling follows the DBC rule raw = (value - offset) / factor (factor 0.1 sends amps x 10).
- One CAN transmit time-out is counted when a keypad is enabled (start-up burst of keypad frames); none after.
- `AGENTS.md` asked for `s1` "65 of 65"; it is 66 since PR #89 (fixed in this PR).

## Built (custom option PRO_FEATURES, job fwgaps)

One custom option (`PRO_FEATURES`, set by `port_boards.py` for custompdm_a / _b only), so stock dingoFW builds stay
byte-identical (dingopdm_v7 .bin md5 fbe414ba, checked). Params use custom blocks (0x7D00, 0x7E00, 0x7F00) that
upstream does not use; new vars are at the END of the var map (every existing var index unchanged). One CONFIG_VERSION
bump: 0x020A -> 0x030A. A board with a saved config falls back to factory defaults on first boot after the update (as
with every earlier layout change): Write All again. Config: A 4812 -> 5148 bytes, B 4840 -> 5176 bytes of 8192
(static_assert in `core/config.h`). Var map: A 264 -> 276, B 273 -> 285.

| Gap | Params (index / sub) | Factory default (source) | Firmware |
|---|---|---|---|
| T1 lookup tables | 0x7E00 + n (n 0-3): 0 enable, 1 input var, 2 points (0-8), 3-10 x, 11-18 y; output var "Table n+1" | empty (all 0) | `functions/lookup_table.h`; updated right after the math blocks |
| P1 trip time | 0x7D00 + o sub 0, 0-10000 ms | 50 ms: ECUMaster / Link / MoTeC publish none; 50 ms is below the shortest ISO 8820-3 3-40 A blade-fuse opening time at 350 % (80 ms; 150 ms at 200 %, Littelfuse ATO data sheet), so the PDM still opens first, and spikes under 50 ms ride through | `Profet::TripTimeExpired`; above the inrush limit or IS at full scale: at once |
| P2 open load | 0x7D00 + o sub 1 min current A (0-100), sub 2 time ms (0-60000); flag var "Output n - Undercurrent" | off (0 A), 500 ms (proposal) | `Profet::UpdateUndercurrent`; counts only while On (and PWM duty not 0) |
| P3 master retry | 0x7F00 sub 6, var index | 0 = off | `device.cpp` CyclicUpdate before the outputs; rising edge only |

Changes from the proposal: T1 checks the x order at run time (an unsorted / short table outputs 0, like a disabled
math block) instead of refusing a write: Write All and ApplyTempParams write one value at a time, so a per-write check
would refuse a good table half-way through. P2 has no fixed status-frame bit (msg 37 is full, msg 3 byte 7 has 5 free
bits for 8 outputs): send the flag var with a CAN output stream (0x2000). The sense noise floor still limits P2:
0.2 A (BTS7008, board A) / 1.0 A (BTS70012) / 0.5 A (BTS7004), so a 0.24 A LED DRL cannot be told from an open wire
on board A.

UI (dingoConfig, per-board Configuration tab, device types 14 / 15; Read All / Write All carry every new param):
"Master Retry" card (var picker) next to the 0x7F00 cards; "Output Protection: Trip Time, Open Load" panel (trip time,
min current, min-current time per output, reset limit shown as "3 trips in all (first try + 2 retries)"); "Lookup
Tables" panel (enable, input var, points, 8 x / 8 y cells, a warning when the table would output 0). The 4 table
outputs and 8 undercurrent flags are in the var pickers. The one-PDM `/pdm` editor does not show them yet.

## Not proposed

PID (the ECU closes loops), logging (no storage on this hardware), H-bridge / wiper brake (high-side hardware
only), password, conditional CAN transmit, native XOR / hysteresis / SR-latch operators (all composable today,
proven in S3).
