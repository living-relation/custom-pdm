# Firmware pin map (boards A and B)

Status: first version, 2026-11-10 (job B, branch `feat/fw-pin-map`). No firmware code. Nothing here is a design decision: open points are in "Questions for Dan".

**Sources**
- Schematics at main `62d38fc`, netlists exported read-only with `kicad-cli sch export netlist` and read with `tools/netlist_pins.py` (commands at the end). The schematic is the truth, not the PCB.
- Stock firmware: dingoFW `d594cd7` (2026-10-22, MIT), boards `dingopdm_v7` (stock for board A) and `dingopdmmax_v1` (stock for board B): `board.h`, `port.h`, `port.cpp`, `port_pwm.h`, `hw_devices.cpp`, `cfg/mcuconf.h`.
- Chip: STM32F446RE, LQFP64, datasheet DS10693 Rev 11: Table 10 (pin definitions, pp. 46-56) and Table 11 (alternate functions, pp. 58-61). Cross-check of AF numbers: ST open pin data (`STM32_open_pin_data`, `STM32F446R(C-E)Tx` + `GPIO-STM32F446_gpio_v1_0_Modes.xml`). Page numbers are the footer markers of the extracted PDF text: spot-check before quoting.
- Words: "stock" = unmodified dingoFW for that board. "TBD" = not confirmed. PIN = LQFP64 pin number.

## 1. What matters most (read this first)

- **The PWM timer of an IN pin does not matter in stock dingoFW.** Output PWM is software: one timer per output (TIM3, 4, 5, 9, 10, 11, 12, 13) with period and compare interrupts that set and clear the IN pin as plain GPIO (`port_pwm.h`: `palSetLine` / `palClearLine`, channels `PWM_OUTPUT_DISABLED`). Pin alternate functions are never selected. Board A and board B (8 outputs each) reuse exactly the 8 timers of the stock `dingopdm_v7`; the stock Max `mcuconf.h` is identical to v7, so TIM10-13 are already enabled.
- Timer guesses checked (only matters if someone wants hardware PWM later): all four exist as written.

| Pin | PIN | Board B net | Your guess | Datasheet (Table 11, AF number from ST pin data) | Verdict |
|---|---|---|---|---|---|
| PA8 | 41 | PF_IN5 | TIM1_CH1 | TIM1_CH1 = AF1 | CONFIRMED. TIM1 is not used by stock FW. |
| PB10 | 29 | PF_IN6 | TIM2_CH3 | TIM2_CH3 = AF1 | CONFIRMED as AF, but TIM2 is the ChibiOS system tick in stock FW (`STM32_ST_USE_TIMER 2`): not usable for PWM without changing the OS timer. |
| PA15 | 50 | PF_IN7 | TIM2_CH1 | TIM2_CH1/ETR = AF1 | CONFIRMED as AF, same TIM2 problem, plus JTDI (see 2). |
| PC8 | 39 | PF_IN8 | TIM8_CH3 | TIM8_CH3 = AF3 (TIM3_CH3 = AF2 also exists) | CONFIRMED. TIM8 is not used by stock FW (TIM3 belongs to output 1). |

- No ADC clash: every analog pin below has its own ADC1 channel (table in section 5), 12 conversions on board B, 16 are possible.
- Conflicts and traps (details in section 2): PB2 is BOOT1 (board B B_IN5); PA15, PB3, PB4 are JTAG pins (SWD still works); stock `LINE_UNUSED` is PA15 (now a live pin on board B); stock debug lines E1-E3 are PC10, PC11, PC13 (now inputs); two digital inputs cannot share an EXTI line (sleep wake-up).

## 2. Flags for the new pins

| Pin | PIN | Used as | ADC (Table 10) | Reserved / shared function | Flag |
|---|---|---|---|---|---|
| PB2 | 28 | A: PF_DEN1 (DEN1_2). B: B_IN5 | none | Table 10 prints "PB2-BOOT1" (p. 49) | Board A: output, same as stock v7. Board B: input, its level at reset selects the boot target when BOOT0 is high (SW1 closed, DFU): see Q1. |
| PB3 | 55 | A: IN_7. B: SWO (J5.6), unused as input | none | JTDO / TRACESWO, AF0 (p. 55, 59) | Board A drops SWO (Dan 2026-11-08). Board B keeps SWO on J5.6, so PB3 must stay an SWO/AF0 pin there. |
| PB4 | 56 | A: IN_5. B: B_IN7 | none | NJTRST, AF0 (p. 56, 59) | JTAG reset pin. Only SWD is usable on these boards (stock already sets PB4 to plain input). |
| PA15 | 50 | B: PF_IN7 | none | JTDI, AF0 (p. 53, 58) | Board B drives an output IN pin from a JTAG pin: firmware must set it to output at start. After reset PA15 is JTDI with a pull-up (reset-state detail: RM0390, TBD, not read). Stock `LINE_UNUSED = PA15`: see section 7. |
| PC13 | 2 | A: IN_6 | none (TAMP_1/WKUP1) | RTC-domain pad | Fine as an input. Weak-drive pad when used as output (RM0390, TBD, not read): not an issue here. Stock uses it as debug output E3. |
| PC14, PC15 | 3, 4 | B: B_IN3, B_IN4 | none (OSC32_IN/OUT) | LSE crystal pins | Fine as inputs because stock has no LSE (`STM32_LSECLK 0`). Board B has no 32 kHz crystal. |
| PC10, PC11 | 51, 52 | A: IN_3, IN_4. B: B_IN9, B_IN10 | none | USART3/UART4/SPI3 alternates, unused | Stock debug outputs E1, E2 (PC11 is written in `profet.cpp` every loop): see section 7. EXTI10 and EXTI11 clash: see 6. |
| PA8 | 41 | B: PF_IN5 | none | MCO1, TIM1_CH1 | none |
| PB10 | 29 | B: PF_IN6 | none | TIM2_CH3, I2C2_SCL, USART3_TX | none (as GPIO) |
| PC8 | 39 | B: PF_IN8 | none | TRACED0 (AF0), TIM3_CH3, TIM8_CH3 | none |
| PB12 | 33 | B: DEN5_6 | none | CAN2_RX (AF9) | none: CAN2 not enabled in stock |
| PB15 | 36 | B: DEN7_8 | none | RTC_REFIN; supplied by VDDUSB (Table 10 footnote) | none (VDDUSB is VDD on LQFP64) |
| PC7 | 38 | A: DSEL1_2 (was DEN2) | none | TIM3_CH2, TIM8_CH2 | none |
| PD2 | 54 | B: B_IN6 | none | TIM3_ETR, UART5_RX | EXTI2 clash with PB2: see 6 |
| PB5 | 57 | B: B_IN8 | none | CAN2_RX, TIM3_CH2 | none |
| PA2 | 16 | B: IS5 | ADC123_IN2 | USART2_TX, TIM2_CH3, TIM5_CH3, TIM9_CH1 | none (analog mode) |
| PA4 | 20 | B: IS6 | ADC12_IN4 | also DAC_OUT1 | keep the DAC off |
| PA7 | 23 | B: IS7 | ADC12_IN7 | TIM1_CH1N, TIM3_CH2, TIM14_CH1 | none |
| PC4 | 24 | B: IS8 | ADC12_IN14 | none | none |
| PB1 | 27 | B: B_AN | ADC12_IN9 | TIM3_CH4 | none |

(Pins that stock already uses for the same job are not repeated.)

## 3. Board A (`hardware/board-a`, MCU U4)

Eight outputs, 7.5 A each: four BTS7008-2EPA duals. Pairs: OUT1+2 on U8 (NEW: was two singles), OUT3+4 on U11, OUT5+6 on U10, OUT7+8 on U13. Each pair has one DEN, one DSEL, one IS. The IS signal goes through an LM324 buffer to the MCU.

**Outputs** (all pins verified in the netlist; "stock v7" column = `LINE_` in dingoFW `board.h`)

| Out | IN pin (PIN) | DEN pin | DSEL pin | IS pin, ADC1 channel | Driver | Enclosure pin | Stock v7 | Diff |
|---|---|---|---|---|---|---|---|---|
| 1 | PB10 (29) PF_IN1 | PB2 (28) PF_DEN1 | PC7 (38) PF_DSEL1_2 | PA0 (14) PF_IS1, IN0 | U8 ch0 | J3.8 | single BTS7002, DEN1 = PB2 | now dual CH1. DEN is shared with out 2. DSEL is NEW (on the old DEN2 pin PC7). IS shared with out 2. |
| 2 | PC8 (39) PF_IN2 | PB2 (28), shared | PC7 (38), shared | PA0 (14), shared | U8 ch1 | J3.7 | single, DEN2 = PC7, IS2 = PC2 | now dual CH2. Old IS2 (PC2) no longer a current sense. |
| 3 | PC6 (37) PF_IN3 | PB15 (36) PF_DEN3_4 | PB14 (35) PF_DSEL3_4 | PC3 (11) PF_IS3_4, IN13 | U11 ch0 | J3.10 | same | none |
| 4 | PB12 (33) PF_IN4 | PB15 (36) | PB14 (35) | PC3 (11) | U11 ch1 | J3.9 | same | none |
| 5 | PB1 (27) PF_IN5 | PB0 (26) PF_DEN5_6 | PC5 (25) PF_DSEL5_6 | PA1 (15) PF_IS5_6, IN1 | U10 ch0 | J3.6 | same | none |
| 6 | PC4 (24) PF_IN6 | PB0 (26) | PC5 (25) | PA1 (15) | U10 ch1 | J3.5 | same | none |
| 7 | PA7 (23) PF_IN7 | PA6 (22) PF_DEN7_8 | PA5 (21) PF_DSEL7_8 | PA2 (16) PF_IS7_8, IN2 | U13 ch0 | J3.4 | same | none |
| 8 | PA4 (20) PF_IN8 | PA6 (22) | PA5 (21) | PA2 (16) | U13 ch1 | J3.3 | same | none |

Dual pairs rely on the stock rule: DSEL low = channel 0, high = channel 1, wait 60 us, then read IS (`profet.cpp` `HandleDsel`).

**Inputs**

| Name | MCU pin (PIN) | Goes to | Type | Stock v7 | Diff |
|---|---|---|---|---|---|
| IN_1 (DI1) | PA10 (43) | J3.12 (INPUT1), 4.7k + BAT54S + 10 nF on board | digital | same | none |
| IN_2 (DI2) | PC9 (40) | J3.11 (INPUT2) | digital | same | none |
| IN_3 | PC10 (51) | J6.1 -> input board ch 1 | digital | debug output E1 | NEW |
| IN_4 | PC11 (52) | J6.2 -> ch 2 | digital | debug output E2 | NEW |
| IN_5 | PB4 (56) | J6.3 -> ch 3 | digital | unused (input, pull-up) | NEW |
| IN_6 | PC13 (2) | J6.4 -> ch 4 | digital | debug output E3 | NEW |
| IN_7 | PB3 (55) | J6.5 -> ch 5 | digital | SWO | NEW (SWO dropped) |
| (J6.6-8) | none | not connected | | | board A has 5 channels, not 8 |
| AIN | PC2 (10), ADC1_IN12 | J6.9 -> input board analog (0-5 V divider) | analog | PF2_IS | NEW use of the old IS2 pin. R12 (to the old buffer) is DNP. |

**System pins** (same as stock v7)

| Function | MCU pin (PIN) | Note |
|---|---|---|
| CAN1 RX / TX | PB8 (61) / PB9 (62) | AF9. Transceiver U3 (PCA82C250, 5 V, 3.3 V Vref). |
| CAN standby (Rs) | PC12 (53) | GPIO output. |
| I2C1 SCL / SDA | PB6 (58) / PB7 (59) | AF4. FRAM U5 MB85RC256V, temp sensor U6 MCP9808, pull-ups R6, R7. |
| Battery sense | PA3 (17), ADC1_IN3 | 47k / 4.7k divider. |
| USB D- / D+ / VBUS | PA11 (44) / PA12 (45) / PA9 (42) | AF10 for D-, D+. |
| LEDs | PC0 (8) red (error), PC1 (9) green (status) | via 120 R. |
| SWD | PA13 (46) SWDIO, PA14 (49) SWCLK, NRST (7) | J4 Tag-Connect. J4.6 (SWO) is not connected. |
| BOOT0 | pin 60 | via R4 and switch SW1. |
| HSE | PH0 (5), PH1 (6) | crystal nets `Net-(U4-PH0/PH1)`. |
| Not connected (free) | PC14, PC15, PB13, PB5, PD2, PA8, PA15 | board A: all unrouted. |

## 4. Board B (`hardware/board-b-max`, MCU U4)

Outputs 1-4: four BTS70012-1ESP singles (stock Max, 31 A). Outputs 5-8: four BTS7004-1EPP singles (NEW, 15 A). No dual devices, so no DSEL. The IS signals go through LM324 buffers: U7 for 1-4, a second LM324 (U22, NEW) for 5-8.

**Outputs** (the pins for outputs 1-4 are identical to the stock Max netlist: compared pin by pin)

| Out | IN pin (PIN) | DEN pin | IS pin, ADC1 channel | Driver | Terminal | Stock Max | Diff |
|---|---|---|---|---|---|---|---|
| 1 | PB14 (35) PF_IN1 | PB13 (34) PF_DEN1 | PC3 (11) PF_IS1, IN13 | U8 | T1 | same | none |
| 2 | PC7 (38) PF_IN2 | PC6 (37) PF_DEN2 | PC2 (10) PF_IS2, IN12 | U9 | T2 | same | none |
| 3 | PB0 (26) PF_IN3 | PC5 (25) PF_DEN3 | PA0 (14) PF_IS3, IN0 | U10 | T3 | same | none |
| 4 | PA6 (22) PF_IN4 | PA5 (21) PF_DEN4 | PA1 (15) PF_IS4, IN1 | U11 | T4 | same | none |
| 5 | PA8 (41) PF_IN5 | PB12 (33) PF_DEN5_6, shared with 6 | PA2 (16) PF_IS5, IN2 | U23 | T5 | not in stock | NEW (one 4.7k per driver DEN, 2 drivers per MCU DEN pin) |
| 6 | PB10 (29) PF_IN6 | PB12 (33), shared | PA4 (20) PF_IS6, IN4 | U24 | T6 | not in stock | NEW |
| 7 | PA15 (50) PF_IN7 | PB15 (36) PF_DEN7_8, shared with 8 | PA7 (23) PF_IS7, IN7 | U25 | T7 | not in stock | NEW |
| 8 | PC8 (39) PF_IN8 | PB15 (36), shared | PC4 (24) PF_IS8, IN14 | U26 | T8 | not in stock | NEW |

The IS to channel link was traced through the buffers: CH5 -> U22C -> PF_IS5, CH6 -> U22D -> PF_IS6, CH7 -> U22B -> PF_IS7, CH8 -> U22A -> PF_IS8. Outputs 1-4: U8 -> U7C -> IS1, U9 -> U7D -> IS2, U10 -> U7B -> IS3, U11 -> U7A -> IS4.

**Inputs**

| Name | MCU pin (PIN) | Goes to | Type | Diff |
|---|---|---|---|---|
| IN_1 (DI1) | PA10 (43) | J6.4 (INPUT1) | digital | none |
| IN_2 (DI2) | PC9 (40) | J6.3 (INPUT2) | digital | none |
| B_IN3 | PC14 (3) | J7.1 -> input board ch 1 | digital | NEW |
| B_IN4 | PC15 (4) | J7.2 -> ch 2 | digital | NEW |
| B_IN5 | PB2 (28) | J7.3 -> ch 3 | digital | NEW (BOOT1: Q1) |
| B_IN6 | PD2 (54) | J7.4 -> ch 4 | digital | NEW |
| B_IN7 | PB4 (56) | J7.5 -> ch 5 | digital | NEW |
| B_IN8 | PB5 (57) | J7.6 -> ch 6 | digital | NEW |
| B_IN9 | PC10 (51) | J7.7 -> ch 7 | digital | NEW |
| B_IN10 | PC11 (52) | J7.8 -> ch 8 | digital | NEW |
| B_AN | PB1 (27), ADC1_IN9 | J7.9 -> input board analog | analog | NEW |

PC13 (pin 2) is a free pin on board B. The numbering B_IN3..B_IN10 is the schematic net name; the input board calls the same wires ch 1..8 (section 8).

**System pins**: same as board A (section 3) for CAN1 (PB8, PB9; connector J6.1 CAN_L, J6.2 CAN_H), CAN standby PC12, I2C1 (PB6, PB7; U5, U6; R12, R13), battery sense PA3, USB (PA11, PA12, PA9), LEDs PC0 red (D7) and PC1 green (D8), SWD PA13/PA14 and NRST (J5 Tag-Connect). Differences: J5.6 = SWO is wired to PB3 (55); BOOT0 via R10 and SW1. Not connected (free): PC13 only.

## 5. ADC channels and PWM timers

All analog inputs are on ADC1 (stock FW uses ADC1 only, continuous scan, 15-cycle sampling, DMA by ChibiOS). Channel numbers: Table 10 "Additional functions" (pp. 47-49) and ST pin data.

| Sequence slot | Board A | ADC1 ch | Board B | ADC1 ch |
|---|---|---|---|---|
| IS out 1 (1+2 on A) | PA0 | IN0 | PC3 | IN13 |
| IS out 2 | (shared with 1) | | PC2 | IN12 |
| IS out 3 (3+4 on A) | PC3 | IN13 | PA0 | IN0 |
| IS out 4 | (shared) | | PA1 | IN1 |
| IS out 5 (5+6 on A) | PA1 | IN1 | PA2 | IN2 |
| IS out 6 | (shared) | | PA4 | IN4 |
| IS out 7 (7+8 on A) | PA2 | IN2 | PA7 | IN7 |
| IS out 8 | (shared) | | PC4 | IN14 |
| Battery | PA3 | IN3 | PA3 | IN3 |
| Analog input | PC2 (J6.9) | IN12 | PB1 | IN9 |
| Temperature sensor, VrefInt | internal | IN18, IN17 | internal | IN18, IN17 |
| Conversions in the scan | 8 | | 12 | |

No two signals share a channel. The scan allows 16 conversions. Stock sample-time macros cover only the channels it uses: add IN2, IN4, IN7, IN9, IN14 on board B (IN4/7/9 in SMPR2, IN14 in SMPR1). Board A needs no new channel number (IN12 stays in the scan as the analog input).

**PWM timers** (software PWM, one per output; ISR timers only)

| Output | Stock v7 timer | Board A | Board B |
|---|---|---|---|
| 1 | TIM3 | TIM3 | TIM3 |
| 2 | TIM4 | TIM4 | TIM4 |
| 3 | TIM5 | TIM5 | TIM5 |
| 4 | TIM9 | TIM9 | TIM9 |
| 5 | TIM10 | TIM10 | TIM10 |
| 6 | TIM11 | TIM11 | TIM11 |
| 7 | TIM12 | TIM12 | TIM12 |
| 8 | TIM13 | TIM13 | TIM13 |

Not used by stock: TIM1, TIM8, TIM14 (free). TIM2 = system tick. TIM6/7 are not PWM-capable.

## 6. Wake-up lines (EXTI) clash on the new digital inputs

Stock `core/sleep.cpp` arms every digital input pin (both edges), CAN RX (PB8), USB D- (PA11) and D+ (PA12) as wake-up sources before stop mode. An EXTI line number (0-15) can serve only one port, so two pins with the same pin number cannot both wake the chip. Sleep is compiled in (`CAN_SLEEP TRUE`) and switched by the `bSleepEnabled` device setting.

| EXTI line | Pins that want it | Board |
|---|---|---|
| 10 | PA10 (IN_1) and PC10 (A: IN_3, B: B_IN9) | A, B |
| 11 | PA11 (USB D-) and PC11 (A: IN_4, B: B_IN10) | A, B |
| 2 | PB2 (B_IN5) and PD2 (B_IN6) | B |

No clash: PC9 (9), PB8 (8, CAN RX), PA12 (12), PB3, PB4, PB5, PC13, PC14, PC15 (3, 4, 5, 13, 14, 15). What ChibiOS does on the second `palEnableLineEvent` of the same line (probably re-points the line and drops the first wake-up source): TBD, not read.

## 7. What differs from stock dingoFW (work list for later, no code here)

**Board A** (base: `dingopdm_v7`)
- Outputs 1 and 2: model `BTS7008_2EPA_CH1` / `CH2` instead of two `BTS7002_1EPP`; DEN `PB2`, DSEL `PC7`, IS channel one shared `IS1_2` (PA0). New `LINE_PF1_2_DEN` and `LINE_PF1_2_DSEL`; `AnalogChannel` loses `IS2`, gains `IS1_2` and an analog-input slot for PC2.
- `NUM_DIG_INPUTS` 2 -> 7 (PA10, PC9, PC10, PC11, PB4, PC13, PB3). `NUM_ANALOG_INPUTS` 0 -> 1 (PC2). Both feed `VAR_MAP_SIZE`, the config blocks and the CAN status messages (`param_defs.h`, `status.cpp`, `msg.cpp`): TBD how much of this is generic in dingoFW.
- `board.h` pin setup: PC10, PC11, PC13 from output (E1-E3) to input; PB3 from AF0 (SWO) to input; PB4 stays input; PC7 stays output (now DSEL); remove `LINE_SWO`, `LINE_E1..E3`. `profet.cpp` drives `LINE_E2` (PC11) as a debug pin every update: remove it (PC11 is a real input now).
- `BTS7008_2EPA_KILIS` already exists in `port.h`.

**Board B** (base: `dingopdmmax_v1`, which has 4 outputs)
- `NUM_OUTPUTS` 4 -> 8; PWM configs for TIM10-13 and callbacks `pwmOut5..8` are copied from v7 `port_pwm.h`; timers already enabled in `mcuconf.h`.
- New `ProfetModel` for BTS7004-1EPP with its own kILIS constant: TBD (value from the Infineon datasheet, not read). The 1.2k sense resistor (R72-R75) is on the board; check the IS voltage range against the 3.3 V LM324 supply: TBD.
- DEN is shared per pair (PB12 for 5+6, PB15 for 7+8) but there is no DSEL: pass `LINE_UNUSED` for DSEL as stock Max does for singles. Stock `HandleDsel` only touches DSEL for the BTS7008 models, so it is never written for singles.
- Stock `LINE_UNUSED` is **PA15**, which is now `PF_IN7`. Not written today, but it is a trap: redefine it to the free pin PC13.
- `AnalogChannel`: IS1..IS4 as stock Max, add IS5..IS8 and one analog-input slot (PB1); `ADC1_NUM_CHANNELS` 7 -> 12 (IS x 8, battery, analog input, temperature, VrefInt).
- `NUM_DIG_INPUTS` 2 -> 10 (PA10, PC9, PC14, PC15, PB2, PD2, PB4, PB5, PC10, PC11), `NUM_ANALOG_INPUTS` 0 -> 1 (PB1).
- `board.h` pin setup: set the new IN pins PA8, PB10, PA15, PC8 and the DEN pins PB12, PB15 to push-pull outputs, low at reset (stock Max has them as input with pull-up); PC10, PC11, PC13 off the E1-E3 outputs; keep PB3 as SWO AF0; PA15, PB4 as plain GPIO (JTAG not available). Same `LINE_E2` debug write to remove.
- Sleep wake-up: see section 6.

**Both boards**
- CAN timing (`port.cpp`, 36 MHz APB1, 1 Mbps = BRP 1, TS1 14, TS2 1 in register values) is unchanged and matches the 1 Mbps decision.
- `HAS_NEOPIXELS FALSE` in both stock ports, so TIM1 stays free.

## 8. Input board (`hardware/input-board`) as far as it touches MCU pins

The board has no MCU. It passes 8 digital channels and 1 analog channel straight through. J1 (JST GH 12, to board A J6 or board B J7) pin n = channel n; J2 (Molex Micro-Fit 2x6) wires: 1-8 inputs, 9 analog, 10-12 GND. Each channel: 4.7k series, BAT54S clamp, 10 nF; 10k pull-up (SW1) and 10k pull-down (SW2) selectable per channel on the wire side. The MCU's own pull setting (stock `InputPull`) still applies.

| J1 / J6 / J7 pin | Channel | Board A net, MCU pin | Board B net, MCU pin |
|---|---|---|---|
| 1 | ch 1 | IN_3, PC10 | B_IN3, PC14 |
| 2 | ch 2 | IN_4, PC11 | B_IN4, PC15 |
| 3 | ch 3 | IN_5, PB4 | B_IN5, PB2 |
| 4 | ch 4 | IN_6, PC13 | B_IN6, PD2 |
| 5 | ch 5 | IN_7, PB3 | B_IN7, PB4 |
| 6 | ch 6 | not connected | B_IN8, PB5 |
| 7 | ch 7 | not connected | B_IN9, PC10 |
| 8 | ch 8 | not connected | B_IN10, PC11 |
| 9 | analog (10k / 20k divider, 0-5 V) | PC2 (ADC1_IN12) | B_AN, PB1 (ADC1_IN9) |
| 10 | +3.3 V | +3V3 | +3V3 |
| 11, 12 | GND | GND | GND |

Same input board for both, so a board-A build only has 5 live channels. Firmware input index (which `digIn[]` slot is which channel) is a firmware choice: not decided here.

## 9. Questions for Dan

- **Q1. B_IN5 sits on PB2 = BOOT1 (board B).** If the input board holds channel 3 high (pull-up switch ON or a high signal) while the chip resets with BOOT0 high (USB DFU), it boots from SRAM instead of the system bootloader and DFU fails. Board A is not affected (PB2 is an output there, as in stock). Options: (A) keep it; rule: channel 3 pull-up OFF and signal low during DFU, or flash over SWD (J5); (B) move B_IN5 to the free PC13 on a later board B revision. Recommendation: A, write the rule into the harness notes.
- **Q2. Sleep wake-up (section 6).** Three EXTI clashes. Options: (A) only IN_1 and IN_2 (PA10, PC9) plus CAN wake the PDM; the new input-board channels never wake it (firmware arms only those two); (B) re-pin PC10 / PC11 / PD2 on a later revision. Recommendation: A. In a car with CAN-controlled switching the ECU wakes it over CAN anyway.
- **Q3. Hardware PWM (section 1).** Stock uses software PWM, so the IN pin timers are irrelevant. Options: (A) keep stock software PWM, no pin change; (B) hardware PWM on the IN pins later (PA8 TIM1_CH1 and PC8 TIM8_CH3 would work; PB10 and PA15 would need the system tick moved off TIM2). Recommendation: A.
- **Q4. `LINE_UNUSED` (board B).** Redefine from PA15 to the free PC13 so no code path can toggle output 7's IN pin. Firmware-only change. Recommendation: yes. (A) yes / (B) leave and rely on stock never writing it.

## 10. Spot-check against the netlist and regenerate

Regenerate (read-only on `hardware/`; netlists go to `%TEMP%`):

```
$k = 'C:\Users\danie\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe'
& $k sch export netlist --format kicadsexpr -o $env:TEMP\a.net hardware\board-a\DingoPDM.kicad_sch
& $k sch export netlist --format kicadsexpr -o $env:TEMP\b.net hardware\board-b-max\dingoPDM-Max.kicad_sch
& $k sch export netlist --format kicadsexpr -o $env:TEMP\i.net hardware\input-board\input-board.kicad_sch
python tools\netlist_pins.py $env:TEMP\a.net U4      # all MCU pins, board A
python tools\netlist_pins.py $env:TEMP\b.net U4      # board B
python tools\netlist_pins.py $env:TEMP\b.net J7      # board B to input board
```

Five quick checks:

| Board | MCU pin (PIN) | Net | Expected |
|---|---|---|---|
| A | PC7 (38) | PF_DSEL1_2 | U8 pin 5 DSEL via R20 |
| A | PB3 (55) | /MCU/IN_7 | J6 pin 5 (not SWO) |
| B | PA15 (50) | PF_IN7 | U25 IN via R58, output 7 |
| B | PB2 (28) | B_IN5 | J7 pin 3 |
| B | PC4 (24) | PF_IS8 | R53 -> U22A buffer <- CH8 (U26 sense) |

Not yet checked (TBD): RM0390 reset states of PA15 / PB3 / PB4 and drive limits of PC13-PC15; ChibiOS behaviour for a repeated EXTI line; BTS7004-1EPP kILIS; whether `NUM_DIG_INPUTS` / `NUM_ANALOG_INPUTS` can be raised in dingoFW without changes to the CAN message layout.
