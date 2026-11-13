# Firmware thermal protection + fan control: plan (2026-11-13)

Status: research and plan only, no firmware changes. Decisions it serves: e3c (fans fitted, temperature-triggered, limit set in software), "heat targets are guides, firmware thermal protection to plan" (2026-11-12), z1a (three CAN nodes), b2a (F1, two 30 mm Sunon fans), b3a (gap pad k >= 3). Source of truth for state: `STATE.md`; decisions: `DECISIONS.md`.

## 1. What temperature information exists today

| Source | Where | How dingoFW uses it today (this repo, `firmware/`) |
|---|---|---|
| **MCP9808 board sensor** (U6, I2C) | Board A and board B, both at PCB (-23.2, 16.4): about 23 mm from board A's nearest BTS7008 (U11) and 14 mm from board B's U9 BTS70012 (`hardware/*/` PCBs). Input board: no temperature sensor. | Read every 250 ms in a slow thread (`core/device.cpp:90-111`). Value `fTempSensor` is in the variable map (`core/device.cpp` InitVarMap, right after ALWAYS_TRUE / fState), so any condition / virtual input / output can use it. Sent on CAN in cyclic msg 0, `data16[3]` = temp x 10 (`boards/custompdm_a/msg.cpp:24`, same on B). |
| Warn / crit limits | `core/device_config.h:18-19`: `BOARD_TEMP_WARN 55`, `BOARD_TEMP_CRIT 80` deg C, **compile-time** | Written into the MCP9808 at boot and **locked** (Tcrit lock, window lock, 1.5 C hysteresis: `hardware/mcp9808.cpp:4-25, 90-110`). Above WARN: state OverTemp, LEDs blink, CAN error msg (`core/device.cpp:186-188, 212-220`; `comms/infomsg.cpp:44`) - **no output action**. At CRIT: **all outputs off + fatal error, latched until power cycle** (`core/device.cpp:171-181`). |
| STM32F446 internal sensor | ADC channel 16/18 sampled (`boards/custompdm_a/port.cpp:95, 112, 145-148`) | `GetTemperature()` exists but **nothing calls it** on custompdm_a / _b. Not sent, not used. |
| PROFET over-temperature | Inside each BTS7008 / BTS70012 / BTS7004 | Chip protects itself: absolute Tj limit 150/175/200 C (min/typ/max) with 30 K hysteresis, plus a dynamic (delta-T 80 K typ) limit; after 2 retry cycles the channel **latches off**; de-latch by IN low longer than tDELAY(CR) or a DEN pulse; IS reports I_IS(FAULT) 4.4-10 mA (BTS7008-2EPA data sheet ch. 8.1, 8.3.1, 9.2.2, tables 14-16, 21: https://cdn.sparkfun.com/assets/3/9/f/f/1/BTS7008-2EPA_datesheet.pdf). dingoFW sees it only as "IS raw > 30000" -> output state **Fault, permanent until power cycle** (`functions/profet.cpp:40-44, 132-137`). No junction temperature is measured. |
| NTC / thermistor | none on boards A, B or the input board (schematic search) | - |

**Key finding 1 (stock limits would shut the PDM down):** the v2b heat model (worst load 31.1 W, 60 C air, fans on, pad k 3; `docs/diagrams/heat-v2b-F1-board-top-fans.png`) puts the board-top background at about **91-100 C** where the MCP9808 sits. Stock CRIT 80 C would turn **every output off and latch** at sustained worst load, and WARN 55 C would be active almost always in 60 C air. The limits must move and become settable.

**Key finding 2 (MCU temperature grade):** the same background (about 92-99 C) is above the STM32F446RE**T6** rating (-40 to 85 C ambient, `docs/parts-audit.md` P8). Decision C4a said to look at **RET7** (105 C grade) if board air exceeds about 75 C - that trigger is now met. Also check the other parts near it at about 100 C (FRAM, TSR 1-2450, MCP2562FD).

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
1. Swap MCU to STM32F446RET7 if r2 = a (parts audit + schematic field, no layout change: same package).
2. Fan power per r3; fan-fail detection per r4.
3. Firmware option B: WARN / CRIT as params with new defaults, CRIT auto-recover, STM32 die temp on CAN; fan latch + shedding delivered as a **default config** (no code).
4. Sim + Renode tests above, then bench calibration.

## 6. Open questions (answers go to DECISIONS.md)
r2 MCU grade, r3 fan power, r4 fan-fail detection, r5 protection approach, r6 default limits (details in PR #? report).
