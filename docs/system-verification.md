# System verification before the PCB order (presim campaign)

Job presim, 2026-11-20 (ADR-2026-11-20-presim: run every check that needs no hardware before ordering boards).
Every row below comes from a re-runnable script (`automation.yml`, `presim-*` and `firmware-sim`); each script prints
its full table with sources. Board-level checks from PR #109 / #114 stay in `docs/pcb-verification.md`.
Design state checked: main 8ad2d20 (TLV9004 sense buffers, PDZ5.1B IS zeners, board B +12 V copper fix) plus the
firmware fixes of this branch. Not repeated here: the D2 supply TVS (job d2tvs).

## For Dan (plain English)

1. **Safe:** every one of the 24 outputs measures its current within about 6 % and trips within 6-8 % of its limit
   at -40..105 C; CAN timing, pin wiring (firmware vs board, 90 pins), clocks, FRAM life, bus load (27 % worst) and
   unplugging / re-plugging a board all check out; the placement files are right on all three boards.
2. **Fixed today (firmware):** the chip's temperature and voltage-reference readings were sampled 6 x too briefly
   (every current and voltage reading leans on that reference); the chip temperature read 5 C off when the 3.3 V
   rail is 1.5 % off. Both fixed and proven in the simulator (s0 50/50, s1 88/88, s3 110/110, Renode 35/35).
3. **Real problems for a decision (not changed by me):** (a) board B's own temperature sensor would read 96-110 C
   in normal hot-day use, above the 80 C "critical" setting, so board B would switch its outputs off (now 98 / 104 C, fwsafety); (b) board B's
   8 protection diodes short the battery if it is ever connected the wrong way round, and they also overheat if a
   fan or pump is PWM-driven faster than about 30 Hz; (c) the processor has no brown-out reset set (the firmware now
   sets it itself, fwsafety); (d) a horn (or a big solenoid) on a board A output may overload that switch when it turns off.
4. **Small hardware items (stock dingoPDM too):** no capacitor on the processor's analog supply (VDDA) and its reset
   pin, no watchdog (built since, fwsafety), no USB surge protection, the regulator / crystal / some capacitors are 85 C parts in a box that
   can run hotter.
5. **Needs real hardware (bench list):** load inductances (horn, solenoids, fan motor), the board temperatures at the
   sensors, sleep current, start-up at 6 V, the ADC full-scale with a forced PROFET fault, the CAN sample point of the
   Link ECU.

## Tools (all new on this branch unless noted)

| Item | Script | Model / method | Run |
|---|---|---|---|
| 1 Tolerance | `tools/verify_tolerance.py` | Monte Carlo (20 000 per case) + hard corners, -40 / 25 / 85 / 105 C, firmware conversion with constants read from `firmware/boards/custompdm_*` | `python tools/verify_tolerance.py` |
| 2 Power | `tools/verify_power.py` | rail chain vs battery (data-sheet limits stacked), BOR, reverse battery, ISO 7637-2 / ISO 16750-2 on input wires, L-R turn-off energy into the PROFET clamp / freewheel diode | `python tools/verify_power.py` |
| 3 Switching | `tools/verify_switching.py` | PWM edge loss from the data-sheet slew (checked against EON / EOFF), freewheel-diode average current, minimum on-time, inrush vs presets (`PdmPresets.cs`) and IL(OVL0), short-circuit retry, parallel pair | `python tools/verify_switching.py` |
| 4 MCU | `tools/verify_mcu.py` | board.h LINE_* -> ST pin data (STM32_open_pin_data, BSD-3) -> PCB U4 pad nets; AF / ADC / boot / JTAG / NRST; PLL; CAN bit timing (ISO 11898-1 tolerance); IWDG; FRAM; sleep budget | KiCad 9 python |
| 5 CAN system | `firmware/sim/s4_can_system.py` | response-time analysis (Davis et al. 2007, worst stuffing) + host sim: 3 boards + dummy ECU / CSB3 / lambda traffic, unplug / replug | `python3 firmware/sim/s4_can_system.py <simout>` |
| 6 Thermal | `tools/verify_thermal_box.py` (+ `tools/thermal_board_b.py`, hwfix, now also reports the U6 MCP9808 reading) | board B finite-volume model with sink (hwfix) + lid-air node + sink transient + part ratings | KiCad 9 python, about 8 min |
| 7 EMC / SI | `tools/verify_si.py` | 2-D finite-difference field solver (self-check vs Hammerstad-Jensen), PWM spectrum envelope, decoupling loops | KiCad 9 python |
| 8 DFM | `tools/verify_dfm.py`, `tools/verify_cpl.py` (fixed) | via-in-pad, edge, silk, drills, BOM shortages, footprint geometry vs the v2c clash build; JLC footprint overlay | KiCad 9 python |

Software: nothing installed on DansPC. The cloud session's ngspice 42, KiCad 9.0.9 (pcbnew), g++ and numpy / scipy
ran items 1-8; DansPC WSL ran the Renode bench (Renode 1.17.0, arm-none-eabi-gcc 14.2.1, both already installed in
`~/renode-pdm`, used read-only from an own scratch HOME `/home/daniel/scratch/presim/home`).

## 1. Tolerance / worst case (23 PASS, 5 WARN, 0 FAIL)

| Chain | Result | Verdict |
|---|---|---|
| IS chain, BTS7008 (15 outputs, 7.5 A limit) | reads -5.8 .. +5.5 %; trips at true 7.03-8.05 A | PASS |
| IS chain, BTS7008 fan output A2 OUT2 (1 A) | reads +-17.7 % (kILIS +-13.5 % at 1 A); trips 0.81-1.22 A vs a 0.13 A fan load | PASS |
| IS chain, BTS7004 (B OUT5-8, 15 A) | reads -7.1 .. +6.4 %; trips 13.9-16.3 A | PASS |
| IS chain, BTS70012 (B OUT1-4, 31 A) | reads -6.7 .. +6.3 %; trips 28.9-33.5 A | PASS |
| Full-scale fault rule (3071 counts) | starts at >= 10.5 A (A), 38 A (B 15 A), 64 A (B 31 A): never below a limit; a PROFET fault reads 4095 | PASS |
| Low current (open-load flag) | reliable from 0.5 A (BTS7008), 2 A (BTS7004, BTS70012); below that the reading can be 0 | INFO |
| Battery sense 9-16 V | -0.55 .. +0.32 V (PDZ3.3B D1 leakage at its 5 uA data-sheet bound); -1.2 V if the zener knee is extrapolated | WARN |
| Input board digital, remote ground +1 V | pin 1.00 V vs VIL 0.98 V tested / 1.10 V design | WARN |
| Input board analog 0.5 / 2.5 / 4.5 / 4.9 V | +-12 / 38 / 66 / 142 mV (1 % resistors; above 4.9 V the clamp / VDDA clip) | PASS / PASS / WARN / WARN |
| MCP9808 vs fan 45 / 40 C and critical 80 C | +-0.5 C sensor, 5 K / 6 K bands | PASS |
| STM32 die sensor at VDDA +-1.5 % | was +5.2 / -5.0 C off, now 0 (fixed) | PASS |
| ADC sampling of TS / VREFINT | was 1.7 us (needs 10 us), now 12.4 us; DSEL settle 80 us >= 72.8 us needed | PASS (fixed) |

## 2. Power (24 PASS, 7 WARN, 3 FAIL)

| Check | Result | Verdict |
|---|---|---|
| CAN works from | 5.85 V battery (worst); at -40 C +5V is 4.54 V (LMZM23601V5 accuracy holds over TJ -40..125 C; hw5v, was 6.35 V / 4.44 V with the TSR) | PASS |
| +3V3 regulated from / >= 2.7 V from | 4.6 V / 4.25 V battery (module dropout 0.93 x VIN - 0.61 Ohm x I, SNVSAQ4C 6.5; hw5v) | PASS |
| 6 V crank | +5VP 4.92, +5V 4.63, +3V3 3.25 V: CAN, outputs and MCU stay (hw5v; was 4.45 / 4.16 V with the TSR) | PASS |
| 16 V / 24 V jump start | 5 V module, LDO, PROFET inside their ratings; clamped surges 33.8 V at the module (36 V recommended, 40 V abs max; verify_spice module5v) | PASS |
| Brown-out | firmware sets no BOR level; factory option byte = BOR off: 1.7-2.7 V unprotected at 144 MHz / 4 wait states | **FAIL** -> fixed (fwsafety): the firmware writes BOR level 3 once at its first start (>= 10 V battery), host sim s0 + Renode |
| Reverse battery: logic, PROFETs, inputs, CAN | blocked / data-sheet setup / 2.9 mA / -58 V rating | PASS |
| Reverse battery: board B freewheel diodes D13-D28 | forward across the reversed battery through the PROFET (stock Max the same); kept fitted by hwprotect (removing them fails the A/C clutch turn-off, see below) | **FAIL** (design choice) |
| ISO 7637-2 on an input wire | pulses 1 / 2a / 3b fine; 3a puts 216 V over a 0603 4.7k (150 V overload rating, 0.1 us) | PASS / WARN |
| Load dump on inputs | 9.9 mA per battery-switched input into +3V3 (LDO cannot sink): up to 4 per board | WARN |
| USB | PESD5V0F1BL ESD diode on USB_D+ and USB_D- (both main boards, hwprotect) | PASS |
| Turn-off energy, board B loads (BYG23M freewheel) | 0.01-0.58 A2s vs 4.5 A2s | PASS |
| Turn-off energy, board A: horn pair (5 A, L 5-30 mH ASSUMED) | 105-633 mJ vs EAS 75 / EAR 25 mJ | **FAIL** (needs the bench L) |
| Turn-off energy, board A: solenoid 1.5 A, 10-50 mH | 19-95 mJ | WARN |

## 3. Output switching (15 PASS, 7 WARN, 4 FAIL)

| Check | Result | Verdict |
|---|---|---|
| PWM heat <= DC heat, lamp loads | 100 Hz: 6.8 / 12.5 / 23.8 A; 400 Hz: 5.2 / 7.7 / 12.0 A (BTS7008 / 7004 / 70012) | WARN |
| PWM heat <= DC heat, motors (hard switching) | 100 Hz: 5.6 / 8.9 / 14.6 A; 400 Hz: 2.8 / 3.3 / 4.6 A | FAIL (7004, 70012) |
| PWM of fans on board B (BYG23M average current) | radiator fan 25 A, 1 mH: 4.6 A at 100 Hz vs 1.5 A rated; safe up to about 32 Hz | **FAIL** (also condenser fan; hardware) -> presets hold board B motor PWM at the diode limit (fwsafety: fans 22 Hz at their 30 A limit, pump 64, motor 60 Hz) until the diodes change |
| Minimum duty | 4.4-8.4 % at 400 Hz | PASS |
| Lamp inrush | 55 W halogen 58 A < IL(OVL0) 65 A hot; 65 W 69 A (PROFET retries) | PASS / WARN |
| Motor inrush 5 x | radiator fan 150 A vs 146 A min hot on BTS70012 | WARN |
| Short circuit | PROFET trips 65-238 A, up to 7 restarts, then latch; firmware retries 1 s apart | PASS |
| Parallel pair B OUT3 + OUT4 | one switch takes 60 % with +-20 % RDS (ASSUMED): pair trips at 52 A, not 62 A | WARN -> the UI rates a pair 52 A and its presets use it (fwsafety) |

## 4. MCU / firmware (15 PASS, 5 WARN, 0 FAIL)

Pins: 42 / 42 (A) and 48 / 48 (B) firmware pins land on their PCB nets; CAN1 AF9, I2C1 AF4, OTG FS AF10, SWD AF0
match ST's table; all 8 / 12 ADC slots read their own nets; PA4 / PA5 (TC, not 5 V tolerant) carry only on-board
signals; BOOT0 / BOOT1 fine. WARN: board B PA15 (JTDI pull-up at reset) drives PROFET IN7 (glitch << tON(DELAY));
NRST has no capacitor (both boards, stock). Clocks: VCO 288 MHz, SYSCLK 144, USB 48.00, APB1 36 MHz: PASS. CAN
1 Mbit/s: 18 tq, sample point 88.9 %, SJW 1, oscillator tolerance +-2778 ppm vs about +-110 ppm crystal, bus up to
about 40 m: PASS. Watchdog: none (stock): WARN -> built (fwsafety): IWDG 1.00 / 1.47 / 2.77 s at LSI 47 / 32 / 17 kHz, refreshed only when all five essential threads ran (longest gap 251 ms host sim, 362 ms Renode), RTC-refreshed in sleep. FRAM: written only on a config save: PASS.
Sleep: 3.3 mA (25 C) / 11.2 mA (85 C) for the whole PDM (battery dividers, op-amps; the 5 V module draws 32 uA, the TSR drew 1 mA x 3; hw5v): WARN.
CPU load: not measurable without a cycle model: bench.

## 5. CAN system (S4: 10 of 10)

RTA with worst stuffing, every dummy car frame + 3 x 38 PDM frames: every frame meets its period; worst PDM burst
18.1 ms, worst car frame 0x642 (CSB3) 18.6 ms (period 50 ms), ECU -> PDM 0x3F4 1.75 ms; worst utilisation 27.3 %.
bxCAN auto bus-off recovery (ABOM) in every bit-rate config, no NART: recovery 1.41 ms. Host sim with the real
firmware: 14.3 % load, car frames <= 0.19 ms queueing, every board's msg 0 exactly 100 ms apart, board B unplugged
3 s: A1 / A2 unaffected, B back 2.2 ms after the replug and answering the tool. Not modelled: error frames on the wire
(the sim bus has none).

## 6. Thermal, whole box (60 C cabin; fans on / failed)

Re-run 2026-11-22 (job orderprep) at the copper that is ordered (`tools/copper_order.py`: board B 1 oz outer + 1 oz
inner = 35 / 35 um, Dan 2026-11-22), `verify_thermal_box.py` on the 0.3 mm grid: 26 PASS, 4 WARN, 6 FAIL before the
UI constant was updated (then 27 / 4 / 5). The first results (2026-11-20) used the KiCad file's 43 / 17 um copper.

| Case | Sink | Lid air | Board B Tj / laminate | Board B MCP9808 | Verdict |
|---|---|---|---|---|---|
| car loads (118 A on B), fans on | 69.6 C | 69.3 C | 114 / 110 C | 93.4 C | PASS (below board B's 98 C warn) |
| 150 A on B, fans on | 72.2 C | 74.1 C | 109 / 117 C (other splits 118 / 117 C) | 106.2 C | PASS heat; board B cuts at 104 C (150 A for a long time at a 60 C cabin is above normal use) |
| 150 A on B, fans failed | 85.9 C | 78.6 C | 123 / **132 C** (other splits 132.5 / 133.1 C) | 120.9 C | FAIL (laminate > 130 C); the 104 C cut comes first |
| car loads, fans failed | 80.2 C | 72.7 C | 125 / 120 C | 104.4 C | PASS heat; board B cuts (104 C) |
| every output at rating (184 A, above the feed limit) | 79-100 C | 92-99 C | up to 157 / 172 C | - | INFO (upper bound) |

Fan failure at 150 A: the sink climbs 72 -> 86 C with a 26 min time constant; the laminate passes 130 C after about
54 min, and board B's sensor is already over its 104 C critical limit at 150 A with the fans on. Part ratings at
150 A, fans on (board B logic area at its MCP9808 106 C, board A about 87 C ASSUMED): crystal and capacitors are
125 C parts on board A and board B (PASS; board A since job orderprep); 5 V module PASS; FRAM 105 C and MCU 105 C
WARN (106 C: above the 104 C cut); DIP switches 74 C vs 70 C WARN. At a 70 C cabin every case is 10 K hotter.

## 7. EMC / SI (3 PASS, 2 WARN, 5 INFO on 2026-11-22)

Field solver self-check 53.4 vs 51.3 Ohm (Hammerstad-Jensen, +4 %). CAN pairs: A 161 Ohm, B 115 Ohm differential
(IPC 128 / 90): both 20 mm long, electrically short at 1 Mbit/s, so impedance does not matter: PASS. USB pairs on
In2.Cu (stripline): short (43 mm vs 100 mm critical, `verify_layout.py`). PWM spectrum: corner 8.6-20 kHz, -40
dB/decade: 25 A at 100 Hz is 56 dBuA at 150 kHz, 34 dBuA at 530 kHz (chamber test for the CISPR 25 limits).
Decoupling: worst MCU loop 3.7 nH (PASS); VDDA 1 uF + 100 nF behind its ferrite since hwprotect (both boards; via in
FB1 pad 2, 11-15 mm on B.Cu to the capacitors: the U4 fan-out leaves no closer site): **WARN** in `verify_si.py`
(pin 13 to the capacitor 7.0 mm, about 7.1 nH, limit 5 nH, on A and B; accepted, bench item:
ADR-2026-11-20-hwprotect b). The two WARNs are this one on each board.

## 8. Manufacturing (7 PASS, 7 WARN, 5 INFO on 2026-11-22)

Via-in-pad: 58 (A), 151 (B), 27 (IN) vias in SMD pads (incl. the hwprotect VDDA via in FB1 and the 5 V module),
mostly the PROFET exposed-pad thermal vias: the fab notes ask JLCPCB for epoxy-filled + capped vias (table row +
order remark, `tools/gen_fab_jlcpcb.py`): WARN in the tool, fine once ordered so. Copper to edge: KiCad
edge_clearance 0.2 mm, no violations. Silk: 358 / 611 / 168 lines under 0.15 mm (KiCad library 0.12 mm, cosmetic):
WARN. Vias 0.3 mm smallest drill / 0.2 mm ring: PASS. BOM: 0 parts short at JLCPCB without an alternate except the
no-LCSC parts (global sourcing by MPN: Y1 on A and B, T1-T8 on B; `fab-notes.md`). Placement: `verify_cpl.py`
129 / 194 / 48 placements, RESULT PASS (Y1 on A and B "check": 2-pad crystal with no LCSC footprint to compare,
symmetric). 3D: WARN "15 / 16 footprint changes since 94adcc4" (the tool's old baseline); the enclosure was
re-checked on the current boards since (revF, docs/order-readiness.md section 5).

## Board B temperature limits (job fwsafety, ADR-2026-11-20-presim-findings item 1; re-derived 2026-11-22, job orderprep)

`tools/verify_thermal_box.py` reads board B's limits from `port_boards.py` and checks them against the sensor ->
hot-spot map of all 10 modelled cases (`thermal_board_b.py --case car feed150 feed150hi feed150lo rating`, fans on /
failed, 60 C cabin), now at the ordered copper (1 oz outer + 1 oz inner, 35 / 35 um) on the 0.3 mm grid:
laminate = U6 + 10.1 .. 19.6 K, Tj = U6 + 2.5 .. 20.4 K. (0.4 mm grid: + 8.3 .. 17.5 / + 4.2 .. 21.2 K; the first map,
2026-11-20, at 43 / 17 um copper on the 0.4 mm grid: + 9.6 .. 19.0 / + 1.7 .. 19.8 K.) A 0.25 mm grid run of three cases gives + 8.6 .. 18.4 K: the car case scatters 16.1 .. 18.4 K between the grids, so the map is used as an envelope (19.6 K covers all three grids). The largest laminate offset is
the 184 A fans-failed case; at the car loads it is 16.1 K.

| Check | Value | Limit | Verdict |
|---|---|---|---|
| Car loads, fans on: U6 vs warn 98 C | 93.4 C (a 70 C cabin: 103.4 C: warning and critical soon, no cut) | < 98 C | PASS |
| Laminate / Tj when U6 reaches critical 104 C (+1 C MCP9808, largest offset) | 124.6 / 125.4 C (126.2 C with the 0.4 mm grid's Tj offset) | <= 130 / 150 C | PASS |
| STM32F446RET7 / MB85RC64TA (105 C ambient) at U6 104 + 1 C | 105 C | <= 105 C | PASS (binding limit) |
| Crystal ECS-80-18-30Q-CES, X7R / C0G capacitors, 5 V module at U6 104 + 1 C | 105 C | <= 125 / 125 / 121 C | PASS (125 C grades on board B since hwprotect / hw5v, on board A since orderprep) |
| UI hot-spot offset (`PdmThermal.BoardBLaminateOffsetK`) vs the map | 19.6 K = 19.6 K (sensor limit = hot spot - 21 K) | map <= UI <= map + 1 K | PASS |
| Board A | no FEA sensor map; the presim estimate (sink + 15 K, ASSUMED) is about 85 C at the car loads, above its stock 80 C | - | open (needs a board A model or the bench) |

Result for the firmware defaults: warn 98 C, critical 104 C, recovery 6 C stay as set on 2026-11-20 (critical is bound
by the 105 C MCU / FRAM rating, not by the copper; warn is 4.6 K over the car-loads reading and below critical-soon
99 C). Result for the UI: the offset grows from 20 K (19.0 + 1) to 21 K (19.6 + 1, rounded up), so board B's factory
98 / 104 C shows as the hot-spot set 119 / 125 C.

## Fixes made (firmware, custom boards only; stock dingopdm_v7 .bin md5 identical to main: fbe414ba...)

- `firmware/tools_custom/port_boards.py`: TS / VREFINT sampling 15 -> 112 cycles (12.4 us at 9 MHz, DS Tables 80 /
  83); `GetTemperature()` scales the count by `GetVDDA() / STM32_CAL_VDDA`; board A `DSEL_SETTLE_US` 80 (BTS7008
  tsIS(CC) 20 us + RC + one 45.6 us ADC sequence); `functions/profet.h` keeps 60 us under `#ifndef` (stock boards).
- Sim: `sim_set_vdda` (sim_core.cpp, pdmsim.py) and the s0 check "die temperature and battery reading independent of
  VDDA" (red first: 625 -> 675, then green). s0 is now 50 checks (was 48). UI: no new setting, nothing for dingoConfig.
- `tools/thermal_board_b.py`: reports what U6 (MCP9808) reads (`t_sensor_u6`). `tools/verify_cpl.py`: user agent.

## Left for the coordinator (real problems / design choices; data above)

1. Board B MCP9808 at 96-110 C in normal use vs the stock 80 C critical (and 55 C warn): done in firmware (fwsafety:
   98 / 104 C, table above); the board B logic area: crystal and X5R caps now 125 C parts (hwprotect); the TSR is now a TJ 125 C TI LMZM23601V5 (hw5v, docs/parts-audit.md section 16).
2. Board B freewheel diodes BYG23M: reverse-battery short (FAIL) and PWM of fans above about 30 Hz (FAIL): remove /
   replace with a larger diode / reverse-polarity protection on the feed; the fan presets' 100 Hz soft start.
   hwprotect: kept fitted (removing them fails the A/C clutch turn-off); options below and parts-audit 15.4.
3. BOR level 3: done (fwsafety: the firmware writes it once at boot).
4. Horn / solenoids on board A outputs (no diode): measure L; move to board B or add a diode at the load.
5. Hardware adds (stock gaps): VDDA 100 nF + 1 uF, NRST 100 nF, USB ESD: done (hwprotect, below); +3V3 shunt for
   battery-switched inputs still open.
6. Watchdog: done (fwsafety; a reset turns all outputs off for about 0.6 s after the 1.0-2.8 s timeout).

## hwprotect follow-up (2026-11-20, branch `fix/hw-protect`; ADR-2026-11-20-presim-findings items 1, 2, 4, 5)

- **Item 4 (both boards):** NRST 100 nF, VDDA 1 uF + 100 nF, one PESD5V0F1BL ESD diode per USB data line
  (`tools/hw_protect.py`, last schematic + PCB stage; parts and sources: `docs/parts-audit.md` section 15). Placed on
  the top side in free space; no other part moved (`tools/board_semdiff.py`). USB ESD at the MCU end of the lines
  (the connector end has no free site).
- **Item 1 (board B):** crystal and the five X5R capacitors are 125 C parts in the same footprints. U13 (TSR 1-2450,
  85 C) stayed: every same-footprint 5 V converter found stops at 85-90 C; replaced 2026-11-21 by a TJ 125 C TI
  LMZM23601V5 inside the TSR outline (hw5v, docs/parts-audit.md section 16).
- **Item 2 (board B freewheel diodes): kept fitted, design choice open.** The PROFET data sheets (8.4.1) want the
  reverse current limited by the load, so the GND -> OUT diodes short a reversed battery. Without them every turn-off
  goes into the switch clamp: `python tools/verify_power.py --no-freewheel-b` gives A/C clutch (B OUT6, L 50-200 mH
  ASSUMED) 0.55-2.2 J vs BTS7004 EAS 0.15 J (FAIL), fans 0.07-0.53 J vs EAR 0.16 J (WARN); `verify_switching.py
  --no-freewheel-b`: fan / pump PWM only to 2-7 Hz. With the diodes (as built): fan PWM safe to about 30 Hz (BYG23M
  1.5 A). Options in `docs/parts-audit.md` 15.4.
- **Item 5:** fab notes ask for epoxy-filled + capped vias in SMD pads (all three boards).
- **D2:** Bourns SM8S24CA-Q is the MPN (ADR-2026-11-20-d2-mpn); Vishay / Panjit alternates. Its EasyEDA footprint
  (C1976790) made the placement checkable: CPL rotation +180 and centre offset 1.912 mm (`gen_fab_jlcpcb.py`).
- **Enclosure (item 7):** board STEPs re-exported from this branch (`enclosure/v2c/src/export_boards.ps1`, commit
  5a363e2) and from main 699a8b8; enclosure v2c F1 (main's sources) built twice and checked with
  `clearance_v2c.py`: all 144 part pairs, every pair with a board has the same minimum gap and overlap volume on both
  (to 0.01 mm / 0.05 mm3): the new 0402 / SOD-882 parts (0.5-0.6 mm tall, top side, MCU area) touch nothing. D2 did
  not move, so its gaps stay as measured by d2tvs (A 5.83 mm to the sink, B 2.61 mm to the carrier standoff).
