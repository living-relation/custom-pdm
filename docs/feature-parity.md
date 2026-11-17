# Feature parity with pro PDMs (ECUMaster PMU, MoTeC PDM, Link PDM)

Goal (Dan, 2026-11-16, `DECISIONS.md` "product goal"): an open-source, affordable PDM that does every common car
job a pro PDM does. This page says, feature by feature, what our firmware (dingoFW `development` @ 14084e9 + the
custom-pdm changes, main d1026b7) can do today, which host-sim check proves it, and what is missing.

- Proof: `firmware/sim/s3_features.py` (S3, new; real firmware logic, run like `s1_system.py`), plus the older
  `s0_board_audit.py` (S0) and `s1_system.py` (S1) checks where they already cover a feature. Results: `firmware/sim/RESULTS.md`.
- "yes" = a built-in block does it; "partly" = it works by combining blocks (each combination is proven in S3) or
  only part of the vendor feature exists; "no" = not possible today.
- Gaps marked **proposal** have a design below and an XFAIL check in S3 that must stay failing until it is built.
  Nothing in the firmware was changed for this page (Dan approves firmware design changes).
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
| 14 | Lookup table 1D / 2D (fan duty from coolant temperature) | 2D / 3D tables up to 21 x 21 (E p.111-112) | n/f | n/f | **no** multi-point table; **partly**: a 2-point linear map with clamps (3 math blocks) | S3 F6 "fan PWM from coolant temperature (linear)"; XFAIL "gap T1" | **proposal T1** |
| 15 | PWM: frequency, fixed duty, duty from a channel, minimum duty | 4-400 Hz, duty fixed or channel (E p.9, 76) | n/f in the part read | Freq / Duty param (L gp-functions) | **yes**: output sub 8-16, 1-400 Hz | S3 F7 "fixed duty", "variable duty" | none |
| 16 | Soft start | yes (E p.9, 78) | n/f | n/f | **yes**: output sub 9 / 14 (ramp ms) | S3 F7 "soft start" | none |
| 17 | Wiper: slow / fast / park / intermittent / wash | yes, modes #0-#7, delay (E p.79-80) | 5 wiring methods, park logic (M p.6-10) | yes, Duration, mist count (L wipers) | **yes**: wiper 0x1900, DigIn / IntIn / MixIn modes, 6 delays, wash cycles, swipe | S3 F8 (4 checks) | motor brake (M output 9, L tri-state): **no**, needs a low-side path (hardware), out of scope |
| 18 | Starter interlock / shed loads while cranking | n/f | starter on a 20 A output (M p.11) | n/f | **yes**: starter block 0x1800, one input, per-output disable | S3 F9 "starter interlock" | none |
| 19 | Master shutdown / safety override | n/f | Master Shutdown (M p.18, 24) | Safety Override (L configuration) | **partly**: the starter block works as one master shutdown; thermal critical shutdown with exempt mask (0x7F00 sub 3) | S3 F9; S1 S4 critical checks | none |
| 20 | Master retry (clear faults without a power cycle) | n/f | Master Retry (M p.18) | latched "until a setting changes or power cycle" (L configuration) | **no**: a latched Fault clears only on a power cycle (or a sleep / wake, which resets the MCU) | S3 F12 "Fault stays latched"; XFAIL "gap P3" | **proposal P3** |
| 21 | Load shedding on battery voltage | n/f | via logic (M p.2) | Safety Override on a parameter (L) | **yes** (logic): battery voltage is var 4; condition + on-delay timer + latch VI | S3 F9 "battery load shed" | none |
| 22 | CAN input: bit mask, scaling, signed, byte order, 29-bit IDs | bit masking, 100 messages (E p.10, 87) | byte offset, bit mask, divisor (M p.20) | CAN Function (L can-setup) | **yes**: 32 per board, 0x1300 (start bit, length, factor, offset, LE / BE, signed, operator) | S3 F10 "CAN input decode", "one-byte big-endian command" | note: big-endian start bit = the MSB (DBC Motorola), see "Found" below |
| 23 | CAN input timeout, default / hold value | default before first frame, keep last or set value (E p.90) | hold previous or fixed value, initial value (M p.20-21) | n/f | **partly**: timeout -> 0; hold = timeout off; "on" via one VI | S1 link-loss matrix | job w1 (link-loss on / off / hold, start-up hold-off); not repeated here |
| 24 | CAN output streams | Cycle / Conditional / Triggered, 1-100 Hz (E p.91-95) | 4 user messages x 8 channels, condition (M p.17, 21-22) | IO Status stream (L can-setup) | **yes**: 32 signals per board packed into frames by ID, 0x2000, interval per signal; plus 38 fixed status frames | S3 F10 "CAN output stream" | conditional / triggered send: no (not needed by the car) |
| 25 | CAN keypads | 2 keypads: ECUMaster, MoTeC, Grayhill, LifeRacing (E p.9, 104) | 4 keypads, LEDs (M p.18, 29) | Keypad 1 / 2 (L can-setup) | **yes**: 2 per board (6 per PDM), Blink Marine 1-15 keys, Grayhill 6-20, LED colours / blink from vars | S3 F11 "keypad button 1" | none |
| 26 | Inrush limit + time | yes (E p.76) | filtered load tolerates inrush (M p.23) | Inrush Limit + Trip Time + Duration (L) | **yes**: output sub 3 / 4 | S3 F12 "inrush window" | none |
| 27 | Overcurrent shutdown | Max current (E p.76) | 1 A steps (M p.2, 35) | Overcurrent Limit (L) | **yes**: output sub 2; trips on one 2 ms sample above the limit | S0 overcurrent; S3 F12 | see #28 |
| 28 | Trip delay / I2t / thermal model | n/f | filtered Output Load, 20-50 s time constant (M p.23, 26-28) | Trip Time (L configuration) | **no**: a 20 ms spike above the limit trips at once | S3 F12 XFAIL "gap P1" | **proposal P1** |
| 29 | Retry count / delay / forever | Retry count, Retry every, Retry forever (E p.76) | Number of Retries, Retry Delay (M p.24) | Retry Limit + Delay, Fuse Mode (L) | **yes**: output sub 5 / 6 / 7 (None / Count / Endless) | S0 retry; S3 F12 "stuck 8 A load", "endless retry" | wording: our reset limit 3 = 3 trips in all (2 retries); MoTeC "3 retries" = 3 after the first trip. Say so in the UI |
| 30 | Retry count reset when the input cycles | n/f | yes (M p.24) | n/f | **yes** | S3 F12 "switching the input off between trips" | none |
| 31 | Undercurrent / open load | Min current -> UNDERCURRENT, output keeps running (E p.76, 100) | n/f | n/f | **no** | S3 F12 XFAIL "gap P2" | **proposal P2** |
| 32 | Short circuit / driver fault | yes (E p.29) | yes (M p.23) | Latch Off Fast above 60 A (L) | **partly**: the PROFET protects itself; the firmware sees the saturated sense pin as a very high current and trips at once, then retries per the output's settings | S3 F12 "driver fault" | see "Found" (dead `nIS > 30000` check) |
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

Counts (43 rows): **yes 25**, **partly 10**, **no 8**. Of the 8 "no": 4 are proposals below (rows 14, 20, 28, 31),
4 are out of scope (35 H-bridge, 39 logging, 42 PID, 43 password).

## Found while testing (no firmware change made)

- Big-endian CAN inputs use the DBC (Motorola) start bit: the MSB of the field. A one-byte command in byte n needs
  start bit `n x 8 + 7`; `n x 8` reads the wrong bits (S3 F10 check: start 56 reads 128 for a 1 in byte 7).
  `docs/car-can-dummy/ecu-pdm-control-plan.dummy.md` says "BigEndian ... single bytes make it moot" and "start bit =
  byte x 8": with BigEndian that is wrong; use LittleEndian with start = byte x 8, or BigEndian with byte x 8 + 7.
- `Profet::Update` checks `nIS > 30000` for a hard driver fault, but the ADC is 12 bit (0-4095, `ADC1_BUF_DEPTH 1`),
  so that branch never runs (upstream code). A PROFET fault still cuts the output: its saturated sense pin reads as
  about 16 A (board A) / 96 A (board B), above the inrush limit, so it trips at once and then follows the retry
  settings instead of latching at once.
- The condition bit test (`BitwiseAnd`) returns the masked value (e.g. 4), not 1. Every consumer treats non-zero as
  true, so it works; a condition "Equal 1" on it would not.
- Reset limit wording, see row 29.
- CAN output scaling follows the DBC rule raw = (value - offset) / factor (factor 0.1 sends amps x 10).
- One CAN transmit time-out is counted when a keypad is enabled (start-up burst of keypad frames); none after.
- `AGENTS.md` asked for `s1` "65 of 65"; it is 66 since PR #89 (fixed in this PR).

## Proposals (not built; Dan approves)

All four would go behind one new custom option (`PRO_FEATURES`, set by `port_boards.py` for custompdm_a / _b only),
so stock dingoFW builds stay byte-identical (dingopdm_v7 .bin md5 fbe414ba). New params use custom blocks
(0x7D00, 0x7E00, 0x7F00) that upstream does not use, and new var-map entries go at the END of the var map, so every
existing var index (and dingoConfig's var pickers) stays the same. One CONFIG_VERSION bump for all of them:
0x020A -> 0x030A (high byte = our layout revision). A board with a saved config falls back to factory defaults on
first boot after the update (as with every earlier layout change), so the PC tool must Write All again.
Config today: A 4812 bytes, B 4840 bytes of 8192 (64 Kbit FRAM); all four add about 340 bytes.

### T1: 1D lookup tables (fan duty from coolant temperature, any curve)

- Why: fans, pumps and dimmers want a curve, not a line (ECUMaster 2D / 3D tables). Today only a 2-point linear map
  works (3 math blocks, S3 F6).
- Design: 4 tables per board, block 0x7E00 + n. `struct Config_Table { bool bEnabled; uint8_t nPoints; uint16_t
  nInput; float fX[8]; float fY[8]; }` (68 bytes, 272 for 4). Sub 0 enable, 1 input var, 2 points (2-8), 3-10 x,
  11-18 y. x must rise; a write that breaks the order is refused (as the wake mask). Output = linear interpolation,
  held at the end values outside the x range. Updated right after the math blocks (a table can read a math result,
  a condition / PWM can read the table).
- Var map: + 4 (table outputs), at the end (A 264 -> 268).
- Test: S3 F6 XFAIL "gap T1" (5 points, 82.5 / 92.5 / 97 C -> 15 / 55 / 82 %).
- UI: dingoConfig has no tables; needs a table page (8 x / y cells) and the 4 new vars in its var list.

### P1: overcurrent trip time (simple I2t)

- Why: motors, fans and pumps draw short peaks after the inrush window; noise on one sample trips today. Link has a
  trip time, MoTeC filters the load over 20-50 s.
- Design: block 0x7D00 + output, sub 0 `nTripTime` ms (0 = today's behaviour, max 10000). In `Profet::Update` state
  On: above the current limit (after inrush) the output trips only when the current has stayed above it for
  `nTripTime`; above the inrush limit it still trips at once (hard short). The time restarts when the current falls
  below the limit. (A real I2t / thermal model can replace the timer later in the same block.)
- Size: `struct Config_OutputExt { uint16_t nTripTime; uint16_t nMinCurrentTime; float fMinCurrent; }` = 8 bytes x 8
  = 64 bytes per board (shared with P2).
- Test: S3 F12 XFAIL "gap P1" (20 ms spike to 8 A on a 5 A output with trip time 50 ms: rides through; 200 ms trips).
- UI: a "trip time" column on the outputs list.

### P2: open-load / undercurrent flag

- Why: lamp-out warning (turn signals, brake lights), a disconnected fuel pump or fan (ECUMaster UNDERCURRENT).
- Design: same block 0x7D00 + output, sub 1 `fMinCurrent` A (0 = off), sub 2 `nMinCurrentTime` ms (default 500).
  While the output is On and not PWM-off, current below the minimum for that time sets the output's undercurrent
  flag; the output keeps running; the flag clears when the current returns or the output turns off. One var per
  output at the end of the var map (after the T1 vars: A 268 -> 276), so logic, keypad LEDs and CAN outputs can use it;
  also a bit in a spare status byte.
- Limit: the sense noise floor is 0.2 A (BTS7008, board A) / 1.0 A (BTS70012) / 0.5 A (BTS7004), so a single LED
  DRL (0.24 A) cannot be told from an open wire on board A.
- Test: S3 F12 XFAIL "gap P2".
- UI: "min current" column, the flag shown on `/pdm`.

### P3: master retry (clear latched faults without a power cycle)

- Why: today a latched Fault needs a power cycle of a PDM that sits on the battery (or a sleep / wake). MoTeC has
  Master Retry; Link clears on a setting change.
- Design: `Config_Device` + `uint16_t nMasterRetryInput` (var index, 0 = off), param 0x7F00 sub 6. On its rising edge
  every output in Overcurrent or Fault goes to Off with its trip count cleared, then follows its input again (a
  still-shorted load trips again at once). Edge only, so a stuck input cannot hammer a short. 2 bytes.
- Test: S3 F12 XFAIL "gap P3".
- UI: a var picker in the PDM settings panel (e.g. a keypad button or an ECU CAN bit).

## Not proposed

PID (the ECU closes loops), logging (no storage on this hardware), H-bridge / wiper brake (high-side hardware
only), password, conditional CAN transmit, native XOR / hysteresis / SR-latch operators (all composable today,
proven in S3).
