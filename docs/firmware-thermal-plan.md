# Firmware thermal protection + fan control: plan (2026-11-13)

Status: option B implemented 2026-11-14 on custom boards only (r5a, r7a, r6c, s10b, s11c, s12a, s13a; section 7): settable limits, self-recovering critical, die temperature on CAN, steady thermal flags + critical-soon warning, temperature-switched fan output (replaces r3c "always on"), load-shed example shipped disabled. Sections 1-6 are the research as written on 2026-11-13. Decisions it serves: e3c (fans fitted, temperature-triggered, limit set in software), "heat targets are guides, firmware thermal protection to plan" (2026-11-12), z1a (three CAN nodes), b2a (F1, two 30 mm Sunon fans), b3a (gap pad k >= 3). Source of truth for state: `STATE.md`; decisions: `DECISIONS.md`.

## 1. What temperature information exists today

| Source | Where | How dingoFW uses it today (this repo, `firmware/`) |
|---|---|---|
| **MCP9808 board sensor** (U6, I2C) | Board A and board B, both at PCB (-23.2, 16.4): about 23 mm from board A's nearest BTS7008 (U11) and 14 mm from board B's U9 BTS70012 (`hardware/*/` PCBs). Input board: no temperature sensor. | Read every 250 ms in a slow thread (`core/device.cpp:90-111`). Value `fTempSensor` is in the variable map (`core/device.cpp` InitVarMap, right after ALWAYS_TRUE / fState), so any condition / virtual input / output can use it. Sent on CAN in cyclic msg 0, `data16[3]` = temp x 10 (`boards/custompdm_a/msg.cpp:24`, same on B). |
| Warn / crit limits | `core/device_config.h:18-19`: `BOARD_TEMP_WARN 55`, `BOARD_TEMP_CRIT 80` deg C, **compile-time** | Written into the MCP9808 at boot and **locked** (Tcrit lock, window lock, 1.5 C hysteresis: `hardware/mcp9808.cpp:4-25, 90-110`). Above WARN: state OverTemp, LEDs blink, CAN error msg (`core/device.cpp:186-188, 212-220`; `comms/infomsg.cpp:44`) - **no output action**. At CRIT: **all outputs off + fatal error, latched until power cycle** (`core/device.cpp:171-181`). |
| STM32F446 internal sensor | ADC channel 16/18 sampled (`boards/custompdm_a/port.cpp:95, 112, 145-148`) | `GetTemperature()` exists but **nothing calls it** on custompdm_a / _b. Not sent, not used. |
| PROFET over-temperature | Inside each BTS7008 / BTS70012 / BTS7004 | Chip protects itself: absolute Tj limit 150/175/200 C (min/typ/max) with 30 K hysteresis, plus a dynamic (delta-T 80 K typ) limit; after 2 retry cycles the channel **latches off**; de-latch by IN low longer than tDELAY(CR) or a DEN pulse; IS reports I_IS(FAULT) 4.4-10 mA (BTS7008-2EPA data sheet ch. 8.1, 8.3.1, 9.2.2, tables 14-16, 21: https://cdn.sparkfun.com/assets/3/9/f/f/1/BTS7008-2EPA_datesheet.pdf). dingoFW sees it only as "IS raw > 30000" -> output state **Fault, permanent until power cycle** (`functions/profet.cpp:40-44, 132-137`). No junction temperature is measured. |
| NTC / thermistor | none on boards A, B or the input board (schematic search) | - |

**Key finding 1 (stock limits would shut the PDM down):** the v2b heat model (worst load 31.1 W, 60 C air, fans on, pad k 3; `docs/diagrams/heat-v2b-F1-board-top-fans.png`) puts the board-top background at about **91-100 C** where the MCP9808 sits. Stock CRIT 80 C would turn **every output off and latch** at sustained worst load, and WARN 55 C would be active almost always in 60 C air. The limits must move and become settable.

**Key finding 2 (MCU temperature grade):** the same background (about 92-99 C) is above the STM32F446RE**T6** rating (-40 to 85 C ambient, `docs/parts-audit.md` P8). Decision C4a said to look at **RET7** (105 C grade) if board air exceeds about 75 C - that trigger was met; RET7 is fitted since PR #54 (r2a), RET6 possibly as an alternate (s9), so limits must suit the fitted chip. Also check the other parts near it at about 100 C (FRAM, TSR 1-2450, MCP2562FD).

## 2. Fans: how they are driven

- Sunon **MF30101V1-1000U-A99**: 12 V DC, 64 mA max, 0.66 W, **2-wire** (no tach, no PWM wire). The -G99 variant is the same fan with a 3-wire tach lead (Digi-Key A99: https://www.digikey.com/en/products/detail/sunon-fans/MF30101V1-1000U-A99/10441405 ; RS: https://uk.rs-online.com/web/p/axial-fans/2025393 ; Digi-Key G99: https://www.digikey.ie/en/products/detail/sunon-fans/MF30101V1-1000U-G99/9950100). Two fans = about 0.13 A.
- **No spare driver exists**: every PROFET channel on A1, A2 and B goes to X1 or the studs (`docs/box-connectors.md`), and no MCU pin drives a load besides them.
- Options: (a) **give up one output** (e.g. an A-board BTS7008 channel, 7.5 A rated) and wire it inside to both fans in parallel. On/off or software PWM through the existing output PWM params (`core/param_defs.h:40-44`, duty can even follow a variable); its X1 cavity becomes a spare. (b) Add a small fan MOSFET driver on a board (board change, needs a free MCU pin). (c) Fans always on while the PDM is awake (no control, louder).
- Fan-fail detection: current sense at 0.13 A on a 7.5 A channel is near the bottom of the IS range (current = IS raw x VDDA/4095 / 1.2 k x kILIS, `functions/profet.cpp:266-267`; low-current accuracy not characterised) - usable only as an "open circuit" check. A tach needs the -G99 fan **and** new firmware (dingoFW has no frequency input). A **thermal plausibility check** (fan commanded on but board temperature still rising past a second limit) needs no new hardware.

## 3. Design options

### 3a. Fan control (e3c) - can be done with existing config, no new code
- Condition C1: `BoardTemp >= T_fan_on`; condition C2: `BoardTemp <= T_fan_off`.
- Virtual input VI_fan = (C1 OR VI_fan) AND NOT C2 - a set/reset latch = hysteresis, using `functions/virtual_input.cpp` (3 vars, 2 operators, NOT per var) with VI_fan reading its own value from the variable map. `T_fan_on` / `T_fan_off` are condition `fArg` params (`core/param_defs.h:99-105`), so they are **set in software** from the PC tool.
- Fan output input = VI_fan (optionally OR'd with a remote board's VI via CAN so all fans run when any board is hot).
- Min-on time: not in stock; the hysteresis gap does the same job in practice.

### 3b. Thermal protection
| Option | What | Effort | Tradeoff |
|---|---|---|---|
| A. Config only | Shed lower-priority outputs with the same latch trick: each sheddable output's input = user logic AND NOT VI_hot; remote boards' temperatures come in as CAN inputs (msg 0 data16[3]) so shedding can be system-wide | none in firmware | Uses 2 conditions + 1 VI per threshold per board (32 / 16 available); but stock CRIT 80 still kills everything (finding 1) |
| **B. Config + small firmware change (recommended)** | A, plus: make WARN / CRIT config params (read before `tempSensor.Init`, which runs after `InitConfig`, `core/device.cpp:139-149`) with new defaults; CRIT becomes "all off, auto-recover after cooling by a hysteresis" instead of fatal latch; send the STM32 die temperature on CAN as a second sensor; optional: PROFET fault de-latch retry (IN low > tDELAY(CR)) as a config choice | small, contained (device.cpp, device_config.h, param_defs.h, mcp9808.cpp, msg.cpp) | Keeps upstream structure; needs new sim / Renode tests |
| C. New thermal module | Derate curves, per-output priority table, system-wide arbitration over CAN | large | Most capable, most code and test burden, diverges from upstream |

**Controlling sensor:** the MCP9808 (only real board sensor). It reads the board background, not the hot spots: model offset to the hottest chip board-top spot is about 20-25 K at worst load (background about 95 C vs B-U11 119 C, junction est. 121 C). Limits are set on the MCP9808 value with that offset in mind; the PROFETs' own 150 C+ protection stays the last line.

**Fan failure:** both fans sit in one sink and serve all three boards (F1), so a fan failure raises every board. Plan: the plausibility check (VI_fanfail = fan on AND BoardTemp >= T_fan_fail) sends a CAN warning and lowers the shed threshold.

## 4. Test plan
- **Host sim** (`firmware/sim/s1_system.py`, real firmware logic): add a settable board temperature per board; tests: fan latch on/off with hysteresis, no chatter at the threshold; shed order; CRIT all-off and recovery (option B); remote temperature via CAN drives another board's fans / shedding; fan-fail plausibility warning.
- **Renode bench** (18 Robot tests now; `firmware/sim/renode/`): the MCP9808 model already has a settable `Temperature` and sets the crit / upper flags (`models/PdmI2C.cs:271-333`). New Robot cases: (1) CAN msg 0 data16[3] tracks the set temperature x 10; (2) fan output follows the configured latch across a 30 -> 50 -> 42 -> 38 C ramp; (3) above WARN: OverTemp state + error msg, outputs unchanged (stock) / shed (configured); (4) above CRIT: all outputs off, then recovery below CRIT minus hysteresis (option B); (5) three-node case: board B hot -> A1 / A2 shed via CAN input.
- Bench after hardware: thermocouples on the MCP9808 spot and one BTS70012 to calibrate the 20-25 K offset.

## 5. Recommended plan (needs Dan's answers)
1. MCU grade: done (r2a, PR #54: boards now STM32F446RET7, 105 C; RET6, 85 C, may become an approved alternate, Dan s9). The bench limits (r6c) must suit whichever chip is fitted.
2. Fan power per r3; fan-fail detection per r4.
3. Firmware option B: WARN / CRIT as params with new defaults, CRIT auto-recover, STM32 die temp on CAN; fan latch + shedding delivered as a **default config** (no code).
4. Sim + Renode tests above, then bench calibration.

## 6. Open questions (answers go to DECISIONS.md)
r2 MCU grade, r3 fan power, r4 fan-fail detection, r5 protection approach, r6 default limits (details in the PR description).

## 7. What was built (2026-11-14)
Only builds whose `port.h` sets `THERMAL_LIMIT_PARAMS` (custompdm_a / _b, from `firmware/tools_custom/port_boards.py`) change; stock boards build as before.

| Item | How | Where |
|---|---|---|
| Limits as config | Own parameter block `0x7F00` (upstream dingoFW `development` / dingoConfig 0.5.0 use device `0x0000` sub 4-9 for other settings): sub 0 warn, 1 critical, 2 recovery hysteresis (deg C, whole degrees, 0-125 / 1-30), 3 critical-exempt mask, 4 critical-soon margin. Factory defaults 55 / 80 / 6 (stock values until the bench, r6c). Config version 0x0108 (0x0107: params at `0x0000` sub 5-8, no margin). | `core/config.h`, `core/param_defs.h` (`THERMAL_PARAM_BASE`) |
| Critical-exempt outputs (s10b) | Param `0x7F00` sub 3, bit i = output i keeps following its input during critical. Factory default: the fan output only (A2 = 0x0002, A1 / B = 0). | `core/device.cpp` `CyclicUpdate`, `port_boards.py` (`DEFAULT_CRIT_EXEMPT_MASK`) |
| Decision | Every 250 ms from the MCP9808 reading: warn when T > warn, clears below warn - 1.5; critical when T >= critical, clears below critical - hysteresis (same rules as the chip's flags). A limit written over CAN acts at once. | `core/device.cpp` `UpdateBoardTempLimits` |
| MCP9808 limits | The chip gets the limits at every start (power-up or wake-up), after the config is read, and only drives its alert LED with them (D5 board A, D10 board B; Tcrit only). Not locked since the sleep fix: the data sheet (DS25095A Register 5-2 bit 8, section 5.2.1) says SHDN cannot be set while a lock bit is set, and lock bits clear only at power-on reset. A board last run with the locked firmware keeps its old chip limits (alert LED only) until its next power-off. Firmware decisions do not use the chip flags. | `hardware/mcp9808.cpp` `Init` |
| Sensor reading | A failed I2C read is "no reading": last valid temperature (msg 0) and warn / critical state kept, so it never trips or clears critical. 4 failures in a row (1 s) = one CAN error message, src TempSensor (14), data: count, I2C flags; sent again after a recovery. After a time-out the I2C driver is restarted. Readings in the first 100 ms after start are skipped (after a wake-up the chip still holds its pre-sleep reading until the first conversion, tCONV 30 ms typ). | `core/device.cpp` `UpdateBoardTemp`, `hardware/mcp9808.cpp` `ReadTemp` |
| Sleep | Before STOP mode: alert output off, then shutdown (0.1 uA typ vs 200 uA, DS25095A Table 1-1). The wake-up reset puts it back to continuous conversion. | `core/sleep.cpp` `EnterLowPower` |
| Warn | Stock: state OverTemp (2), both LEDs blink, CAN error message once on entry (State_Overtemp, temp x10); outputs unchanged. | `core/device.cpp`, `comms/infomsg.cpp` |
| Thermal flags (s11c) | Steady: cyclic msg 3 (base + 5, every 100 ms, always sent) byte 7 (stock 0, no DBC signal): bit 0 over warn (> warn, clears < warn - 1.5), bit 1 critical soon, bit 2 critical (>= critical, clears < critical - hysteresis); bits 3-7 0. Msg 0 byte 1 (state + PDM type) stays stock. | `core/device.cpp` `GetThermalFlags`, `port_boards.py` (`msg`) |
| Critical soon (s11c) | Set when T >= critical - margin and not critical; clears below critical - margin - 1.5 C or when critical is reached. Margin param `0x7F00` sub 4, whole deg C 0-30, default 5 (0 = off). One CAN message on entry: type Warning ('R'), src Overtemp (9), temp x10, critical x10, margin. | `core/device.cpp`, `comms/infomsg.cpp` |
| Critical | Every output not in the exempt mask held off (no fatal error, no latch, state OverTemp); one CAN error message (src Overtemp = 9, temp x10, limit x10); outputs follow their inputs again below critical - hysteresis. | `core/device.cpp` `CyclicUpdate`, `comms/infomsg.cpp` |
| Die temperature | STM32 internal sensor, deg C x10 signed, msg 27 (base + 29) bytes 6-7 (was 0). | `boards/custompdm_*/msg.cpp` |
| Fans | Factory default: board A unit 2 OUT2 (index 1) enabled, limits 1 A / 2 A inrush, exempt from critical (s10b, row above), input = a set / reset latch (section 3a) on stock conditions, CAN inputs and virtual inputs: OFF at power-up, ON when the hottest of A2 (own MCP9808), A1 and B (their msg 0 bytes 6-7 over CAN) is >= 45 C, OFF when all three are <= 40 C (Dan s12a / s13a; `FAN_ON_C`, `FAN_OFF_C`, `FAN_REMOTE_TEMPS` in `port_boards.py`). Slots (0-based): conditions 26-27, virtual inputs 11-13, CAN inputs 24-27 (A1 hot / cool, B hot / cool; 1 s time-out). A lost remote reading (time-out, or before its first frame) reads 0 on both its CAN inputs: it can neither turn the fans on nor let them go off; A2's own sensor always counts. The thresholds sit in 6 params (cond 26 / 27 `fArg`, CAN inputs 24-27 `fOperand`). Why OUT2 on A2: A2 is the board at the F1 fan bay end (east, `enclosure/v2b/src/build_v2b.py` X0 + bay at LX1); its J3 pad 7 (O2) is in the east-most pad column (x +11.11, tied with O5) and its driver U8 is the east-most PROFET (x 11.14 vs U10 8.96). X1 cavity T becomes spare (`docs/box-connectors.md`). | `port_boards.py` (`FAN_OUTPUT`) |
| Load-shed example | Prefilled, disabled. Level 0: condition 29 (temp >= 70), 30 (temp <= 65), virtual input 15 = (29 OR 15) AND NOT 30. Level 1: conditions 31 (>= 75), 32 (<= 70), virtual input 16. Numbers count from 1; firmware / parameter index = number - 1 (conditions 0x1500 + 28..31, virtual inputs 0x1400 + 14..15). Example temperatures only. | `port_boards.py` (`SHED_*`) |

How to turn shedding on (per board): enable the level's two conditions and its virtual input (sub 0 = 1). For each output to shed, take a free virtual input V: var 0 = the output's present input, operator 0 = AND, var 1 = the level's latch virtual input with NOT, var 2 = none; enable V and set the output's input to V. Lower-priority outputs go on level 0, higher on level 1. To shed on another board's temperature, add a CAN input on that board's msg 0 bytes 6-7 (x 0.1) and point the conditions at it. Tested in `firmware/sim/s1_system.py` S4.

Warn before critical (2026-11-14, s11c): the event messages stay one-shot on entry (warn State_Overtemp, critical-soon Warning / Overtemp, critical Error / Overtemp); the steady state is in msg 3 byte 7 in every 100 ms frame, and the board temperature in msg 0 bytes 6-7 (x10). Tested on a 50-80 C ramp: warn at 55.5 C, critical 14.8 s later.

dingoConfig (stock PC tool) view, checked from code only: the `0x7F00` block (warn, critical, hysteresis, exempt mask, margin) and msg 3 byte 7 are unknown to it (needs a new device-settings page and a status decode); the fan latch uses only stock conditions, CAN inputs and virtual inputs, so they show and edit as ordinary items, but the latch reads its own virtual input as one of its inputs: needs a dingoConfig check that its variable list offers / keeps that self-reference.
