# Sleep current + 3.3 V regulator / power LED / RET7 scope study

Research only, done 2026-11-13. Nothing on the boards, schematics or firmware is changed by this document.
Rule used: every number comes from a data sheet (section and link given) or from the schematic/netlist (file and ref/net given). Anything not confirmed is **TBD**.

## tl;dr

- **Sleep today: about 35 mA or more at 12 V** for the whole system (2 x board A + board B, typical, 25 C). Over a day that is about 0.85 Ah.
- **Biggest single drain: the PROFET switches are left in "standby" (DEN high) while the MCU sleeps.** The firmware sets DEN high once and never clears it (`firmware/functions/profet.h:62`, "Always on"). Each PROFET then draws 1.2 mA typ straight from 12 V. That is 4.8 mA per board on board A, and at least 4.8 mA on board B (BTS70012 value TBD).
- **Second biggest: LD1117 quiescent current (5 mA typ) plus the always-on green power LED (6.7 mA or more) on every board.**
- **After the board PR only (low-Iq regulator + power LED off):** about **20 mA** system (-44 %).
- **After the board PR + a small firmware change (DEN low in sleep):** about **5.4 mA** system (-85 %), about 0.13 Ah per day.
- **Recommended regulator: TI TLV1117LV33DCYR.** Same SOT-223 pinout as the LD1117 (true drop-in, no re-route), Iq 50 uA typ. TI's own LCSC part C15578 is **out of stock**. A JSMSEMI clone (C48937499) has 84,195 in stock, but its specs are not verified.
- **STM32F446RET7 (105 C grade): LCSC C1343794 is out of stock**, from $21.04.

---

## A. Power architecture per board

### Board A (x2): `hardware/board-a/DingoPDM.kicad_sch`

```
 +12V ──D19 (Schottky)──► +12P ──► U15 TSR 1-2450 (buck, fitted) ──► +5VP ──D18 PMEG2010AEH──► +5V
                                   (U1 VXO7805, U14 OKI-78SR: DNP alternatives)                     │
 USB J5 VBUS ──D15 (Schottky)──────────────────────────────────────────────────────────────────────┤
                                                                                                    │
            +5V loads: U3 MCP2562FD VDD (CAN driver)    U2 LD1117S33CTR (VIN pin 3) ──► +3V3
                                                                                                    │
 +3V3 loads: U4 STM32F446 (VBAT, VDD x4, VDDA via FB1) · U5 MB85RC64TA FRAM · U6 MCP9808 temp ·
             U7/U12 LM324 (V+ pin 4) · U3 VIO · J6 pin 10 (input board) · J4 Tag-Connect · SW1 BOOT ·
             D6/D7 BAT54S input clamps · R5/R6/R7 · LEDs: R3+JP1+D3 power (always on), R8+D5 alert,
             R52+D16 / R53+D17 status (GPIO PC0 / PC1)
 +12V direct: 4 x BTS7008-2EPA PROFET (VS from the 12 V supply)
```

### Board B (x1): `hardware/board-b-max/dingoPDM-Max.kicad_sch`

```
 +12V ──D3 (Schottky)──► +12P ──► U13 TSR 1-2450 ──► +5VP ──D4 PMEG2010AEH──► +5V ◄──D6── USB J2 VBUS
                                  (U1, U12: DNP alternatives)                    │
            +5V loads: U3 MCP2562FD VDD           U2 LD1117S33CTR ──► +3V3
 +3V3 loads: same set as board A (U4 MCU, U5 FRAM, U6 MCP9808, U7/U22 LM324, U3 VIO, input board),
             LEDs: R3+JP1+D5 power (always on), R8/D7, R9/D8, R14/D10
 +12V direct: 4 x BTS70012-1ESP (U8-U11) + 4 x BTS7004-1EPP (U23-U26)
```

### Input boards (x3)

Only +3V3 (J1 pin 10) and GND. Inputs: 4.7k series + BAT54S clamp to +3V3. DIP switches select 10k pull-up or pull-down. They draw current only when a pull-up is selected **and** the input is held low (3.3 V / 10k = 0.33 mA each); how many are set that way in the car is **TBD**.

### What the firmware does in sleep

- `firmware/core/sleep.cpp`: sleeps when no output is on, USB is off and CAN has been idle for SLEEP_TIMEOUT. Wake sources: digital inputs, CAN RX, USB.
- `firmware/boards/cortex-m4/mcu_utils.cpp:4-17`: STOP mode, low-power regulator, flash in deep power down (FPDS + LPDS). Wake ends in `NVIC_SystemReset()`.
- `core/device.cpp:234`: CAN STBY pin set high, so the MCP2562FD goes to standby.
- **Not done:** MCP9808 is never shut down (no shutdown code in `hardware/mcp9808.cpp`). PROFET DEN pins stay high (`functions/profet.h:62`). Status LED GPIO states are held through STOP, so a status LED that was on stays on (state at sleep entry: **TBD**).

---

## B. Sleep current budget at 12 V

### How 5 V-rail current is turned into 12 V current

`I(12 V) = I(5 V) x 5 / (12 x 0.94) + 1 mA`

- 0.94 is the TSR 1-2450 full-load efficiency ("94 % at Vin min"). The 1 mA is its no-load input current at 12 V in (typ). Source: [Traco TSR 1 data sheet](https://tracopower.com/tsr1-datasheet).
- Light-load efficiency is **TBD** (not in the data sheet). It is worse than 94 %, so the 12 V figures below are lower bounds.
- An LDO's input current equals its output current plus Iq, so 3.3 V loads count 1:1 on the 5 V rail.

### Board A, now (typical at 25 C)

| Part | Rail | Condition in sleep | Current typ (max) | Source |
|---|---|---|---|---|
| U4 STM32F446 | 3.3 V | STOP, LP regulator, flash deep power down | 0.121 mA (0.9 at 25 C; 6 at 85 C; 12 at 105 C) | [ST DS10693](https://www.st.com/resource/en/datasheet/stm32f446re.pdf) Table 27 |
| D3 green power LED + R3 120R | 3.3 V | always on (JP1 bridged) | 6.7 mA or more | (3.3 - 2.5 V) / 120 R; Vf 2.5 V is at 20 mA ([LG R971 data](https://elcodis.com/parts/1931330/LG_R971-KN-1_p11.html)). Vf is lower at 7 mA, so current is higher: exact **TBD** |
| U6 MCP9808 | 3.3 V | running (never shut down) | 0.200 mA (0.400) | [MCP9808 DS](https://cdn.sparkfun.com/assets/b/2/1/a/1/MCP9808.pdf), DC characteristics, IDD |
| U5 MB85RC64TA FRAM | 3.3 V | standby (I2C idle) | 0.008 mA (0.010) | [MB85RC64TA DS](https://mouser.com/datasheet/2/1113/MB85RC64TA_DS5v0_E-3538551.pdf), DC characteristics, ISB |
| U7 + U12 LM324 | 3.3 V | always powered | 1.4 mA (2.4) for both | [TI LM324 DS](https://www.ti.com/lit/ds/symlink/lm324.pdf) 6.7, ICC 0.7 (1.2) mA each |
| D16 / D17 status LEDs | 3.3 V | GPIO state held | 0, or 6.7 mA or more each if lit | **TBD** (state at sleep entry) |
| D5 alert LED | 3.3 V | MCP9808 ALERT not asserted | 0 | netlist (open drain) |
| Input pull-ups, R5/R6/R7 | 3.3 V | depends on wiring | **TBD** | netlist |
| **3.3 V subtotal (known)** | | | **8.43 mA (10.4)** | |
| U2 LD1117S33 | 5 V | quiescent | 5 mA (10) | [ST LD1117 DS](https://intranet.ee.ucl.ac.uk/facilities/teaching-lab/ld1117v_variable_regulator.pdf), Iq |
| U3 MCP2562FD | 5 V | standby (STBY high) | 0.005 mA (0.015) | [MCP2562FD DS](https://cdn.sparkfun.com/assets/3/d/9/c/d/20005284a.pdf) 2.3, IDDS (includes VIO) |
| **5 V subtotal** | | | **13.4 mA (20.4)** | |
| U15 TSR 1-2450 | 12 V | 5 V load above, plus no-load | **6.95 mA** (about 10) | formula above |
| 4 x BTS7008-2EPA | 12 V | IN low, **DEN high** = standby | 4 x 1.2 = **4.8 mA** (7.2) | [BTS7008-2EPA DS](https://cdn.sparkfun.com/assets/3/9/f/f/1/BTS7008-2EPA_datesheet.pdf) Table 10, P_6.5.1.5 IGND(STBY) |
| **Board A total** | **12 V** | | **about 11.8 mA** | |

### Board B, now

| Part | Rail | Current typ (max) | Source |
|---|---|---|---|
| 3.3 V loads (same set as A: MCU, power LED D5 = same LED C2899888 + R3 120R, MCP9808, FRAM, 2 x LM324 U7/U22) | 3.3 V | 8.43 mA (10.4) | as board A; netlist `dingoPDM-Max` |
| U2 LD1117S33 + U3 MCP2562FD | 5 V | 5.005 mA (10.0) | as board A |
| U13 TSR 1-2450 | 12 V | 6.95 mA | formula |
| 4 x BTS7004-1EPP (U23-U26), DEN high | 12 V | 4 x 1.2 = 4.8 mA (7.2) | [BTS7004-1EPP DS](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/73/BTS7004_2D00_1EPP-Datasheet.pdf) Table 10, P_6.5.21.5 IGND(OFF_D) |
| 4 x BTS70012-1ESP (U8-U11), DEN high | 12 V | **TBD** (data sheet table not reached) | Infineon BTS70012-1ESP data sheet |
| **Board B total** | **12 V** | **11.8 mA or more** (+ BTS70012) | |

### System totals at 12 V (typical, 25 C, known parts only)

| State | Per board A | Board B | System (2A + B) | Per day |
|---|---|---|---|---|
| **Now** | 11.8 mA | 11.8 mA + TBD | **35.3 mA + TBD** | 0.85 Ah |
| **After board PR** (TLV1117LV + power LED off) | 6.6 mA | 6.6 mA + TBD | **19.8 mA + TBD** | 0.48 Ah |
| **After board PR + firmware DEN low in sleep** | 1.8 mA | 1.8 mA | **5.4 mA** | 0.13 Ah |
| + MCP9808 shutdown (firmware) | 1.7 mA | 1.7 mA | 5.1 mA | 0.12 Ah |

How "after" is worked out (per board):
- 3.3 V: 0.121 (MCU) + 0.200 (MCP9808) + 0.008 (FRAM) + 1.4 (LM324) = 1.73 mA.
- 5 V: 1.73 + 0.050 (TLV1117LV Iq, [TI DS](https://www.ti.com/lit/ds/symlink/tlv1117lv.pdf) 6.5) + 0.005 (CAN) = 1.785 mA. At 12 V: 0.79 + 1 = 1.8 mA.
- PROFET with DEN low = sleep: BTS7008 0.03 uA typ (P_6.5.1.1), BTS7004 0.05 uA typ (P_6.5.21.1). Both at TJ 85 C or less; that is near zero.

What is left after both changes:
- 3 x 1 mA TSR no-load.
- LM324s, 0.62 mA at 12 V per board. They are always powered; switching them off is a bigger hardware change, not scoped here.

Not in these totals (all **TBD**): status LEDs left on, input pull-ups held low, BTS70012 standby current, TSR light-load efficiency, and MCU stop current when hot (up to 6 mA max at 85 C).

---

## C. Awake 3.3 V load budget (per board)

| Load | Typ | Worst case | Source |
|---|---|---|---|
| U4 STM32F446, 180 MHz, all peripherals on | 86 mA | 125 mA (max at 105 C) | DS10693 Table 24 (ART + prefetch on). Which mode the firmware uses: **TBD** |
| Power LED (removed after the PR) | 6.7 mA or more | same | as above |
| Two status LEDs, both lit | 13.4 mA or more | same | 2 x R 120R; same LED parts (C2899888 / C2899997; red Vf **TBD**) |
| Alert LED (only during alert) | 0 | 6.7 mA or more | |
| MCP9808 | 0.2 mA | 0.4 mA | DC characteristics |
| FRAM at 1 MHz I2C | 0.08 mA | 0.10 mA | DC characteristics (actual I2C clock **TBD**) |
| 2 x LM324 | 1.4 mA | 2.4 mA | 6.7 |
| MCP2562FD VIO | **TBD** (small) | **TBD** | VDD side is on 5 V: 45 mA dominant typ (70 max), 2.3 |
| Input board loads | **TBD** | **TBD** | |
| **Total (known)** | **about 108 mA** | **about 155 mA** | |

Take 155 mA as the design worst case. That works out as follows:
- Regulator heat at 5.0 V in: (5.0 - 3.3) x 0.155 = **0.26 W**. 5.0 V in is the worst case (USB, or no PMEG drop).
- Rated output needed: 300 mA or more, to leave margin.

---

## D. Low-Iq 3.3 V regulator candidates

Conditions used:
- Board at 95-100 C.
- Input is +5V: TSR 5 V or USB, through a Schottky.
- Load up to 155 mA.
- Today's part is the LD1117 in SOT-223 (pin 1 GND, pin 2 + tab OUT, pin 3 IN; netlist U2).

| | **TI TLV1117LV33DCYR** | onsemi NCP1117LPST33T3G | Diodes AP2112K-3.3TRG1 | TI TLV75533PDBVR | LD1117S33CTR (today) |
|---|---|---|---|---|---|
| Iq typ (max) | **50 uA (100)** | 550 uA (700) | 55 uA (**unverified**) | 25 uA (40 at 125 C) | 5 mA (10) |
| Vin range / abs max | 2-5.5 V / 6 V | up to 18 V | TBD | 1.45-5.5 V / 6 V | up to 15 V |
| Output current | 1 A | above 1 A | 600 mA | 500 mA | 800 mA |
| Dropout | 90 mV at 200 mA; 230 mV at 500 mA | 1.3 V at 1 A (low current: TBD) | TBD | 150 mV typ at 500 mA | 1.1 V at 800 mA |
| Temp rating | TJ -40 to 125 C | **TJ 0 to 125 C** (not rated below 0 C) | **Ta -40 to 85 C (fails)** | TJ -40 to 125 C | TJ -40 to 125 C (C version) |
| Thermal, 0.26 W at 100 C board | RθJA 62.9 C/W: about **116 C, OK** (9 C margin) | SOT-223: similar, about 116 C | n/a | RθJA 231 C/W: about **160 C, fails** | same as TLV1117LV |
| Output cap | 1 uF or more ceramic (effective above 0.5 uF), stable at 0 Ω ESR | 4.7-10 uF, ESR 20 mΩ-20 Ω (ceramic may be too low ESR) | TBD | 0.47 uF or more, 1-200 uF recommended | |
| Footprint / pinout vs SOT-223 LD1117 | **Same SOT-223, same pins: drop-in** | Same SOT-223, same pins: drop-in | SOT-25: new footprint + re-route | SOT-23-5 (1 IN, 2 GND, 3 EN, 5 OUT): new footprint + re-route | |
| LCSC / stock | TI C15578: **out of stock** ($0.21). JSMSEMI clone C48937499: **84,195** ($0.11), specs unverified | C146799: **8,855**, from $0.145 | C51118: 31,145, from $0.08 | C404027: **75,415**, from $0.066 | C35879: 17,135 |
| Source | [TI DS](https://www.ti.com/lit/ds/symlink/tlv1117lv.pdf) 5, 6.5; LCSC | [onsemi DS](https://www.onsemi.com/download/data-sheet/pdf/ncp1117lp-d.pdf); [LCSC](https://www.lcsc.com/product-detail/C146799.html) | LCSC listing (data sheet fetch blocked) | [TI DS](https://www.ti.com/lit/ds/symlink/tlv755p.pdf); [LCSC](https://www.lcsc.com/product-detail/C404027.html) | ST DS; parts-audit.csv |

The existing caps around U2 are fine for the TLV1117LV:
- +3V3 (out): C6 10 uF, C14 4.7 uF, C16/C18 1 uF, 9 x 100 nF, all ceramic 0805. That meets the "1 uF or more ceramic" rule.
- +5V (in): C5 100 nF and C41/C42 47 uF.
- TLV1117LV maximum output capacitance: **TBD**. Check it in the TI data sheet before ordering, against about 18 uF nominal on +3V3.

**Recommendation: TLV1117LV33DCYR.**
- It is the only candidate that is low-Iq, drop-in (no footprint or route change), and rated for -40 to 125 C TJ, with thermal margin at 100 C.
- Watch-outs:
  - The 6 V abs max is 1 V above the 5 V rail. That is fine for TSR and USB sources (both regulated).
  - Sourcing: TI's part is out of stock at LCSC, and the clone is unverified (question s5).

NCP1117LP is the in-stock genuine fallback. It is still a drop-in, but it costs about 0.5 mA more per board and is not rated below 0 C.

---

## E. STM32F446RET7 facts and stock

- Same die and package as RET6 (LQFP-64). The only difference is the temperature range: "6 = -40 to 85 C", "7 = -40 to 105 C" (DS10693 ordering information; Table 50 uses the same split for flash endurance). Junction -40 to +125 C (Table 2). LQFP64 ΘJA 46 C/W (Table 117).
- Electrical figures used above are the same for both; the 105 C max columns apply to RET7. The STOP max is 12 mA at 105 C vs 6 mA at 85 C, but a sleeping car is not at 105 C.
- No firmware, pin or footprint change: same part family code, same linker/memory map.
- **Stock:**
  - LCSC C1343794 is **out of stock**, "from $21.0444" ([LCSC](https://www.lcsc.com/product-detail/C1343794.html)).
  - RET7TR (tape and reel) is listed at TME and others; its LCSC stock is **TBD**.
  - RET6 C69336 is 79 in stock at $11.61 (`docs/parts-audit.csv`).

---

## F. Change scope for one board A/B PR

**Important:** `tools/build_board_a.ps1` and `tools/build_board_b.ps1` rebuild the schematics from the dingoPDM baseline. A hand edit in the `.kicad_sch` is lost at the next rebuild. Part changes therefore belong in **`tools/sch_board_fix.py`**, which already does this for the CAN chip and PMEG diode (part tuples + `apply_part`).

| Item | Board A | Board B | How |
|---|---|---|---|
| 3.3 V regulator | U2: value LD1117S33CTR to TLV1117LV33DCYR; LCSC, Digi-Key (**TBD**), MPN, Datasheet fields. Footprint `dingoPDM:SOT-223` unchanged | U2: same; footprint `digikey-footprints:SOT-223` unchanged | new `REG3V3` part tuple in `sch_board_fix.py`; symbol pins already match (1 GND, 2/4 OUT, 3 IN) |
| Power LED off | JP1 (bridged solder jumper): swap to the open variant `Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm`, or mark R3 + D3 DNP | JP1 the same, or R3 + D5 DNP | `sch_board_fix.py`; a JP1 footprint swap also needs `pcb_fix_board_a.py` / `pcb_board_b.py` (same pads, no re-route). DNP needs no PCB change |
| MCU grade (if chosen) | U4 MPN STM32F446RET6 to RET7, LCSC C1343794 | U4 the same | `sch_board_fix.py`; value stays `STM32F446RETx` |
| Parts list | rows U2, U4 (and R3/D3 if DNP) | rows U2, U4 (R3/D5) | re-run `tools/gen_parts_audit_csv.py`; update `docs/parts-audit.md` BOM table, P8 and P11 |
| Other docs | `docs/firmware-thermal-plan.md` step 1 (RET7) | | |
| Re-route | none | none | |
| Checks | ERC/DRC/parity count equal to main | the same | `tools/drc_diff.py`, `tools/check_board_b.py`, netlist with no net changes, `.github/state-check.sh` |

Effects outside the boards:
- **Enclosure:** none. Same SOT-223 height. The status LEDs on the south edge stay; only the green power LED goes dark (`docs/enclosure-layout.md:34`).
- **Firmware:** none for this PR.
- **Optional firmware PR**, done separately: in `EnterSleep()`, set all PROFET DEN low, shut down the MCP9808 and turn the status LEDs off. Wake already resets the MCU, and the Profet constructor sets DEN high again.
- **Input boards:** none.

Conflicting info found:
- `docs/parts-audit.md` P3/P11 still call U3 a PCA82C250.
- The netlist and `sch_board_fix.py` (C3d) say MCP2562FD-E/SN.
- Recommend refreshing P3/P11 in the same PR.

---

## G. Questions for Dan

- **s4** (open from before): what should the next board change do about sleep current?
  - a) Swap the regulator **and** turn off the power LED (recommended: it cuts system sleep from about 35 mA to about 20 mA with no re-route)
  - b) Only turn off the LED
  - c) No change
- **s5**: TI's TLV1117LV is out of stock at LCSC. Which one should we buy?
  - a) The genuine TI part from Digi-Key or Mouser, hand-placed or consigned (recommended once stock is checked)
  - b) The JSMSEMI clone C48937499 (84k at LCSC, specs unverified)
  - c) The onsemi NCP1117LP (in stock and genuine, but about 0.5 mA more and not rated below 0 C)
- **s6**: how should the power LED be turned off?
  - a) Mark R3 + LED DNP: no PCB change, saves 2 parts (recommended)
  - b) Open-jumper footprint: you can bridge it by hand to get the LED back
  - c) Remove the LED from the design
- **s7**: the PROFETs draw 4.8 mA per board in sleep because DEN stays high. Should we fix it?
  - a) Separate small firmware PR: DEN low, MCP9808 off and status LEDs off in sleep (recommended: the biggest single cut)
  - b) Fold it into the board PR
  - c) Leave it
- **s8**: should the RET7 go in the same PR, given it is out of stock at LCSC?
  - a) Yes, as the schematic part, and buy it elsewhere (TME / Digi-Key, stock TBD)
  - b) Keep RET6 and buy the 79 at LCSC now (recommended if the build is soon)
  - c) Wait for stock
