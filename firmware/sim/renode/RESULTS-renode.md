# Renode bench: results (2026-11-11)

Firmware built from `main` @ 05d1d91 (`firmware/` identical to d319ad3). Renode 1.17.0, Robot Framework 6.1,
arm-none-eabi-gcc 14.2.1, WSL Ubuntu on DansPC. Run: see `README.md`. Nothing flashed, nothing pushed.

**18 of 18 tests pass** (one suite, 287 s wall).

Update 2026-11-14 (branch `feat/fw-thermal`, thermal protection + fans, `docs/firmware-thermal-plan.md` section 7): **22 of 22 pass** (about 660 s of test time). Default config written at first start is now 4372 / 4396 bytes. New tests:

| # | Test | Evidence from the run |
|---|---|---|
| 5 (new) | Factory defaults: fan output, temperature limits | only global output 10 (A2 OUT2) high at every 200 ms sample for 2 s, status On; warn / critical / recovery 55 / 80 / 6 read back from all three |
| 19 | Board and die temperature on CAN | A1 board 47.5 / die 63.0 C -> 475 / 668; A2 52.0 / 41.0 C -> 520 / 456 (die value = sensor model + ADC + `GetTemperature()`) |
| 20 | Above warn (56 C) | A1 outputs 1, 2, 4 stay on; state 0 -> 2 -> 0; last message E / State_Overtemp / 560 |
| 21 | At critical (80 C) | A1 all off after 20 ms (sensor read phase), state 2, message E / Overtemp / 800 / 800, other boards untouched; still off at 79.5 / 80 / 77 / 74.0 C; back on 160 ms after 73.5 C; no fatal error |

Update 2026-11-14 (branch `feat/fw-sleep`, sleep fix + MCP9808 reads + critical-exempt fan): **25 of 25 pass**. Test 5 now also reads device param 8 (critical-exempt mask: A1 0, A2 2, B 0). New tests (run after the manual ID / bit-rate test; named, not numbered, because the numbers shifted with later tests):

| Name | Test | Evidence from the run |
|---|---|---|
| Sleep (new) | Sleep request on A1 (alone on the bus) | before: DEN high on all 4 pairs, output 3 on, status LED on, sensor converting with alert on; after: every IN / DEN / DSEL low, both LEDs off, sensor in shutdown with alert off (1 shutdown write, 0 rejected), status frames stop |
| Wake-up (new) | Wake-up (MCU reset, no sensor power-on reset) | DEN high at the first status frame; sensor back to continuous, alert on, not locked; msg 0 shows only 0 (no reading yet) then 41.5 C, never the 33.0 C held from before sleep |
| MCP9808 read failures (new) | MCP9808 NAKs | A1 at 80 C: all off; 2 s of NAKs while it cools to 40 C: still all off, state 2, msg 0 keeps 80.0 C, message E / TempSensor (14) / 4 / I2C flags; reads back: outputs on and state Run |

Model changes (`models/PdmI2C.cs`): the MCP9808 stand-in now follows DS25095A Register 5-2 for the lock bits (sticky until `PowerOnReset`; SHDN cannot be set while locked; locked fields and limit registers keep their value), shutdown (ambient register frozen), tCONV 30 ms after start or after SHDN clears (ambient register holds the old value meanwhile; 0 C after power-on), `Nak` (no address acknowledge, the controller reports AF). `machine Reset` is now an MCU reset only for the sensor; the bench's power cycle calls `PowerOnReset` first.

STOP mode is not emulated: in Renode SysTick keeps running and ends the WFI at once (seen in a debug run: the board reset and restarted 620 ms after the sleep request). The sleep test therefore halts the CPU at `EnterStopMode()` (address from `arm-none-eabi-nm`, a file-local LTO symbol), and the wake-up test does the MCU reset the firmware does after STOP. EXTI wake-up from STOP stays untested here.

Update 2026-11-14 (branch `feat/fw-fan-warn` @ 503f201, thermal flags + critical soon + temperature-switched fans + params at 0x7F00): **28 of 28 pass** (about 470 s). Test 5 now expects the fan OFF at 30 C (no output high at any 200 ms sample for 2 s, A2 OUT2 status Off) and reads warn / critical / recovery / exempt mask / critical-soon margin from block 0x7F00 sub 0-4: A1 and B (55, 80, 6, 0, 5), A2 (55, 80, 6, 2, 5). New tests:

| # | Test | Condition checked |
|---|---|---|
| 6 (new) | Fan on A2's own sensor, 30 -> 46 -> 42 -> 39 C (800 ms per step) | global output 10 off, on, on, off |
| 7 (new) | Fan when only a remote board is hot (A2 at 30 C) | A1 47 -> on, 41 -> on, 39 -> off; B 46 -> on, 30 -> off (temperatures reach A2 in A1 / B msg 0 over the CAN hub) |
| Thermal flags (new, after the critical test) | Thermal flags + critical-soon message on A1 | msg 3 byte 7 sampled every 100 ms for 1 s at 30 / 56 / 76 / 81 / 30 C = 0 / 1 / 3 / 5 / 0 in every sample, 9-11 msg 3 frames per second; last message on A1's base ID after 76 C = R / Overtemp (9) / 760 / 800 |

One-line mutations, each a full bench run on a mutated `git archive` copy, all RED: R1 msg 3 byte 7 = 0 (the thermal-flags test fails: flags 0 in every sample); R2 critical-soon message on any over-temperature (the above-warn, at-critical and thermal-flags tests fail: an R message replaces the expected last message); R3 fan source A2 only (test 7 fails: fan never on); R4 fan latch without its self-hold (tests 6 and 7 fail: fan off at 42 / 41 C). After a mutation run the bench `fw` folder holds mutated binaries: run with `--build`.

Update 2026-11-14 (branch `feat/fw-dingofw-dev` @ aca0c62, firmware on dingoFW `development` @ 14084e9, s15a): **28 of 28 pass** (439 s suite). No model change was needed: the FRAM model takes upstream's 32-byte chunked writes (each its own transaction with its own address), the sleep path (CAN stopped, TX pin as GPIO, pending EXTI / NVIC cleared) runs up to the `EnterStopMode()` hook, and the param thread answers within the bench's reply time-out. Test edits: IDs, status msg and version from `pdmsim.py` (0x500 / 0x540 / 0x580, msg 37, 0.6.2). Evidence that changed: default config 4812 bytes (A) / 4840 (B) written at first start; 322 writes in 0.12 s with 0 retries (each run used to need one resend); cross-board rule on after 40 ms; link-loss changes at 1020 ms; outputs back 620 ms after a restart; overcurrent pulses at 20 / 2020 / 4020 ms, 1000-1020 ms long. RAM: .bss 59.9 kB (A) / 60.2 kB (B) of 128 kB, heap 68.6-69.0 kB left; flash .text 107 kB. Linker RWX warning only.

Update 2026-11-14 (branch `feat/fw-wake` @ 54ea06a, wake-up set as a config setting, Dan B2): **30 of 30 pass** (449 s suite). New tests at the end (config side only: STOP mode is not emulated, so which pins actually wake the MCU is checked in the host sim, `s0` / `s1` S6, against its EXTI model; EXTI wake-up from STOP stays untested here):

| # | Test | Evidence from the run |
|---|---|---|
| 29 (new) | Wake-up set: default and a valid mask over CAN | param 0x7F00 sub 5 = 0 on A1, A2, B; Write 0x073 (A1) / 0x1FE (B) answered with the same value, read back 0x073 / 0x1FE |
| 30 (new) | Wake-up set: refused masks | A1 0x005 (IN_1 + IN_3, line 10), A1 0x008 (IN_4 = USB D- line), B 0x101 (IN_1 + B_IN9), B 0x200 (B_IN10): no Write reply after 3 tries, one warning per try on the base ID (R, src Config 10, refused mask, bad inputs, kept mask), read back = the mask from test 29; reset to 0 afterwards |

One-line mutations, each a full bench run on a mutated `git archive` copy, both RED with only the targeted test failing: R1 board A factory wake mask 0x73 (test 29 fails: A1 / A2 read 115); R2 the WriteParam check removed (test 30 fails: every mask is answered and taken, no warning). Stock dingopdm_v7 .bin byte-identical to a fresh build of pristine `14084e9` (md5 fbe414ba); bench `fw` rebuilt with `--build` afterwards.

Numbering below is the old 18-test list (the new test 5 shifts the later ones by one; 19-21 run before the manual ID test).

## What each test showed

| # | Test | Evidence from the run |
|---|---|---|
| 1 | Three fresh boards at 1 Mbit/s, each answers on its own ID | bit timing written by the firmware = 1 000 000 on all three; version 0.5.9 from 0x500, 0x520, 0x540 (since the `development` port: 0.6.2 from 0x500, 0x540, 0x580) |
| 2 | No fatal error, battery voltage reported | status LED on, error LED off; 13.8 V in all three status frames |
| 3 | Default config written to FRAM at first start | 4368 bytes (A boards), 4392 bytes (B) over the emulated I2C bus |
| 4 | Power cycle keeps IDs and config | same IDs and bit rate; no new FRAM bytes written, so the stored config and CRC were read back as valid |
| 5 | Config as one 24-output PDM written over CAN and saved | 322 parameter writes acknowledged (same count as the host simulation), 1.02 s; saved on all three |
| 6 | Walking one ECU bit through 23 outputs | every step: exactly that output's IN pin high, and the status frames agree |
| 7 | Cross-board rule (board B input to output 5 on A1) | on after 110 ms (10 ms steps), off after release |
| 8 | One total-current number | 35 A shown for 36.0 A of load (CAN sends whole amps) |
| 9 | ECU quiet, outputs on | hold stays on; off drops at 1000 ms (A1 and B); on stays on; all follow the ECU again |
| 10 | ECU quiet, outputs off | hold stays off; on turns on at 1020 ms (A1 and B); all follow again |
| 11 | Board A1 unplugged | A1: hold on, off off, on on; B unchanged; A1 status 2.5 s old, others under 100 ms |
| 12 | Board B unplugged | mirror of 11 |
| 13 | Cross-board rule when its source board is lost | output 5 drops after 1000 ms, returns with the board |
| 14 | Restart with no ECU on the bus | hold off, off off, default-on output on 620 ms after the restart; follows the ECU when it returns |
| 15 | Restart while the ECU is talking | outputs back 620 ms after the restart; config still valid |
| 16 | Overcurrent (10 A on a 7.5 A output) | three ON pulses of 1000 to 1020 ms, 1 s apart, then Fault; stays Fault with a normal load; works again after a power cycle |
| 17 | Temperature from the I2C sensor | 30.0 then 60.0 in the status frame; device state 0 to 2 (over-temperature) and back |
| 18 | Manual ID and bit-rate change | ID 0x6A0 and 500 kbit/s timing kept after a restart; then restored |

Time steps: pin states are sampled every 20 ms (10 ms in test 7), so times are rounded to that.

## Differences from the host simulation (`../RESULTS.md`)

- Output back on after power-up: 620 ms here, 506 to 516 ms there. The host simulation reads the FRAM in no time;
  here the config read took about 98 ms at 400 kbit/s (9 bit times per byte) for the 4364-byte config of 2026-11-11
  (the config is larger since the dingoFW `development` port: update above).
- Saving the config (burn) answers after about 100 ms for the same reason; a 100 ms reply time-out is too short for it.
- Before the dingoFW `development` port, one of the 322 parameter writes in each run got no reply within 100 ms and
  was sent a second time. Fixed upstream: since the port all 322 writes are answered with 0 retries (update above).

## Renode model problems found (all worked around in `models/`, none in the firmware)

- `ICSR.RETTOBASE` wrong inside nested interrupts: ChibiOS crashes without the correction (`PdmNvicFix.cs`).
- No DMA in the I2C model, no circular mode in the DMA model, fixed 100 us ADC conversions, no F446 platform.
- GPIO: a value written to ODR at board init shows up in IDR of input pins. USB VBUS (PA9) read high, and the
  firmware then waits 1.5 s before starting USB. The bench drives VBUS and all digital inputs low 10 ms after
  every start (read back as high before that on all three boards).
- `CAN_BTR` reads 0 outside initialization mode (as on the real part); the tests use the value the firmware wrote.

## Not covered or stubbed

- CAN: no bit timing, arbitration, ACK, error frames or bus-off. A 500 kbit/s board still "hears" a 1 Mbit/s node,
  so test 18 proves the stored timing, not that the bus works at that rate. No receive-overrun or
  transmit-time-out counters (the host simulation has them).
- USB: no model. The firmware sees "not connected". Config over USB is not tested.
- STOP mode and EXTI wake-up, brown-out, boot pins, watchdog: not tested (the sleep steps before STOP and the restart after it are: the sleep and wake-up tests).
- PWM outputs and soft start: not tested (all outputs are plain on/off, as in `s1_system.py`).
- Analog: ideal ADC, no noise or settling; sense clamp 3.3 V assumed (as in the host simulation); die temperature
  channel returns a fixed plausible value; analog input and digital-input pull settings not tested.
- Interrupt and thread timing follow Renode's instruction counting, not the real MCU's cycle timing.
- MCP9808 stand-in: lock, shutdown and tCONV behaviour checked against DS25095A (Register 5-2, section 5.2.1,
  Tables 1-1 / 5-3) on 2026-11-14; hysteresis and the alert pin itself not modelled.
- FRAM: plain array, no write-protect pin, no device-ID read (the firmware skips it).
- No planted-error run was made on this bench (the host simulation has one). The pin tables are shared with it.
- The CAN-filter option, the total of bus load and the latency numbers of `s1_system.py` are not repeated.
- The tests share one emulation and depend on their order.
