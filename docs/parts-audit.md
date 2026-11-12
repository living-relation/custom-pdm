# Parts audit - custom-pdm

Written 2026-11-11 on branch `feat/parts-audit` (from main d319ad3). Stock and prices were checked 2026-11-10 to 2026-11-11.
This file lists what the design really needs and where each rating came from. It makes no choices: the open ones are in section 3.
Progress and open items are not repeated here: see `STATE.md` ("Open items") and `DECISIONS.md`.
Machine-readable copy of the board tables, one row per part group with LCSC stock and price breaks: `docs/parts-audit.csv`.

Marks: **TBD** = could not be confirmed from a primary source. **Proposal** = a part number I suggest, not one the design names.

How the lists were made: `kicad-cli sch export python-bom` (KiCad 10.0.7, read-only) on the three schematics, grouped by value + footprint + fields.
Board count for one PDM: **2 x board A, 1 x board B, 3 x input board** (input boards #1, #2, #3 in `docs/box-connectors.md`, X2 table; three input boards drawn in `docs/enclosure-layout.md` section 1).

## 1. Summary

| Count | Number | Note |
|---|---|---|
| Components placed per PDM | 612 | 2 x 135 (A) + 198 (B) + 3 x 48 (input); includes logos, holes and one DNP resistor per board A |
| Unique parts on the boards | 54 | 42 on board A, 6 more on board B, 6 more on the input board |
| ...with an exact maker part number behind them | 41 | none comes from an MPN field (the schematics have none); all 41 come from the LCSC number in the schematic, looked up at LCSC |
| ...identified but with a loose end | 4 | 74650074R, BTS7004-1EPP (no supplier fields); 7461084 and MB85RC256V (LCSC number no longer exists) |
| ...named only by a footprint or a short value (guesses) | 9 | JST GH x 2, Micro-Fit x 2, DIP switch, and 4 input-board resistor / capacitor values |
| Off-board parts (box connectors, mates, contacts, studs) | about 20 lines | on hand: section 4.3; still to buy: section 3, C5 |
| Problems and thin margins | 16 | section 2 |
| Open choices | 7 | section 3 |
| BOM v4 lines that are guesses | 11 of 20 | section 5 |

## 2. Problems and thin margins (most serious first)

Status after the board fix (2026-11-11, branch `feat/board-fix`): section 9.

| # | What | Why it matters | Source |
|---|---|---|---|
| P1 | **Three 5 V regulators are all in the parts list of every main board** (A: U1, U14, U15; B: U1, U12, U13). All three sit on the same input (+12P) and output (+5VP) nets and none is marked "do not fit". | The schematic's own note says "Use one in place of U1". An assembler working from the BOM would fit all three and tie three switching outputs together. One must be chosen and the other two marked DNP. The default one (U1, VXO7805-500-M-TR) is out of stock everywhere I looked. | Netlist export (nets `+12P`, `+5VP`); text in `Power.kicad_sch`; stock: section 3, C1. Choice C1. |
| P2 | **No CAN termination resistor or jumper exists on any board.** Nets CAN_H / CAN_L only reach the transceiver, the protection diode and the connector. The 120 ohm resistors that are on the boards (9 on A, 12 on B) are current-sense filters and LED resistors. | `DECISIONS.md` (CAN, 2026-11-08) says every board keeps a selectable 120 ohm termination. That part is not in the design. | Netlist export, both main boards. Choice C7. |
| P3 | **CAN transceiver U3 is a PCA82C250, wired as if it were a 3.3 V-logic type.** Pin 5 is tied to +3V3 and pin 8 is driven straight from a 3.3 V MCU pin. On a PCA82C250 pin 5 is a reference *output* (0.45 to 0.55 x VCC, specified only for +-50 uA) and standby needs pin 8 above 0.75 x VCC = 3.75 V at 5 V. | A 3.3 V pin cannot reach the 3.75 V standby level, so sleep / standby is not guaranteed; pin 5 is being fed from a supply. This project did not change that part of the circuit, so it most likely comes from stock dingoPDM (not compared with `reference/`); it is still outside the data sheet. BOM v4 lists a different chip (TJA1051T/3/2Z). `hardware/board-a/CAN.kicad_sch` is a leftover sheet (its U5 = TJA1042T/3 is not in the netlist). | NXP PCA82C250 data sheet Rev. 06 (2011-08-25), Table 3, Table 5, Table 8. Choice C3. |
| P4 | **FRAM U5 (MB85RC256V): the LCSC number in the schematic (C47538) no longer exists**, and the order code behind the Digi-Key field could not be confirmed. Mouser sells the part only as RAMXEED MB85RC256VPNF-G-AMERE2 at 8.41 USD. | Needs a decision anyway (already an open item). | LCSC lookup returned nothing; Mouser search. Choice C2. |
| P5 | **Output terminals T1-T8 (Wuerth 74650074R): rated 50 A "at 20 C" only.** The data sheet has no derating curve and says "Operating current depends on PCB, cable lug and cross section of the cable". | OUT1-4 carry 31 A (62 % of the 20 C figure) in a box designed for about 60 C air. The margin at 60 C is **TBD**: it cannot be read from the data sheet. T5-T8 at 15 A are at 30 %. | Wuerth data sheet 74650074R, rev. 002.002, 2022-08-01, page 1. |
| P6 | **Feed terminals (Wuerth 7461084, 2 per main board): press-fit only, 160 A at 20 C.** The data sheet says "Wave and reflow soldering is not applicable". | (a) They must be pressed in, not soldered: check that the assembler does press-fit and that the hole size follows the Wuerth drawing. (b) Board B can draw 4 x 31 + 4 x 15 = 184 A at rated load, more than the terminal's 160 A; with the 150 A feed limit it is at 94 % of the 20 C figure. Derating at 60 C: **TBD**. | Wuerth data sheet 7461084, rev. 001.003, 2025-06-18. |
| P7 | **All three switch types are used at 100 % of their nominal current.** BTS7008-2EPA 7.5 A of 7.5 A, BTS7004-1EPP 15 A of 15 A, BTS70012-1ESP 31 A of 31.3 A. | The nominal current is defined at 85 C air on a standard test board with junction at or under 150 C. There is no spare: whether it holds depends fully on the heat sink (not designed yet). | Infineon data sheets, Table 13 (P_7.5.1.8, P_7.5.11.8, P_7.5.23.8). Section 6. |
| P8 | **MCU STM32F446RET6: scarce, and the "6" grade ends at 85 C air.** Mouser 0 in stock with a 52-week factory lead time; LCSC 79; Octopart showed 0 at TME, Newark, Future, Avnet, Arrow. | 3 needed. Buy early. The box air is planned at about 60 C plus its own heating; the 105 C grade is STM32F446RET7 (availability **TBD**). | Mouser, LCSC, Octopart (2026-11-10/11); ST DS10693 Rev 11, ordering scheme. |
| P9 | **Capacitors on the +12 V rail below the schematic's own voltage note.** C3 (10 uF, next to the "Min 35V" note) has LCSC part CL21A106KAYNNNE = 25 V. The 47 nF caps on +12 V (4 on A, 8 on B) are 25 V parts too. The TVS clamps at 32.4 V (LCSC listing; schematic note says 33 V). | During a voltage spike the rail may sit above the capacitors' rating. Which part the Digi-Key field points to was not confirmed (**TBD**). | `Power.kicad_sch` text positions; LCSC C15850, C520039, C152086. |
| P10 | **Current-sense resistors (1.2 kohm, 4 per A, 8 on B): the LCSC part is a 5 % type** (FOJAN FRC0805J122). | These set the measured output current (and the overcurrent trip). 5 % resistor error adds straight onto the switch's own 4 to 5 % sense error. The Digi-Key field may point to a 1 % part (**TBD**). | LCSC C2933520; Infineon Table 21 / 22 (kILIS tolerance). |
| P11 | **Fixed 2026-11-11 (p1a, PMEG2010AEH): see section 9.** **The 3.3 V regulator and the CAN chip are fed through a diode from 5 V.** +5VP goes through Schottky D18 (A) / D4 (B) to +5V, which feeds LD1117S33 (dropout 1.10 V typ, 1.20 V max at 800 mA) and the PCA82C250 (VCC 4.5 to 5.5 V). | 5.0 V - 3.3 V = 1.7 V, minus the diode drop, is what the regulator gets against a need of up to 1.2 V; the same diode drop may put the CAN chip under its 4.5 V minimum. Diode drop at the real current: **TBD**. Most likely the same in stock dingoPDM (not compared). | ST LD1117 Rev 38 Table 12; NXP PCA82C250 Table 1; netlist. |
| P12 | **LCSC and Digi-Key fields name different makers for protection parts.** TVS D2: LCSC gives BORN SMCJ20CA; CAN protector: LCSC gives DOWO "NUP2105LT1G" (not onsemi); 47 uF: LCSC gives PSA FS55X476K250LRG. | Which column is the real choice? If the boards are assembled from the LCSC column, these are second-source copies of the named parts. | LCSC lookups (section 4.1). Choice C6. |
| P13 | **Parts with no supplier field at all:** board B T1-T8, U23-U26, J6, J7; board A J6; every part on the input board. | An assembly order cannot be made from these BOMs as they are. | Schematic exports. Section 4. |
| P14 | **Out of stock at LCSC (2026-11-10):** USB-C socket USB4085-GF-A (Mouser has 105,196), BOOT switch CJS-1200TB1 (Mouser 0, 5,000 expected 2026-12-01), 47 kohm C327035 and 120 ohm C229076 (generic, pick another line), VXO7805, OKI-78SR, TSR 1-2450 (see P1). | Not blocking, but the BOOT switch has no stock at either place today. | LCSC, Mouser. |
| P15 | **BTS70012-1ESP at LCSC: 23 left** (36 on 2026-11-05). LCSC sells BTS700121ESPXUMA1; the schematic's Digi-Key field and Mouser / Digi-Key stock are BTS700121ESPXUMA2 (Mouser 7,968, Digi-Key 19,906 per Octopart, 4.48 USD at 1). | 4 needed. No shortage outside LCSC. The difference between XUMA1 and XUMA2: **TBD** (Infineon page did not load). | LCSC, Mouser, Octopart. |
| P16 | **Harness-side parts short today:** size 20 sockets 0462-201-20141 (Mouser 0, due 2027-02/03), size 12/16 sealing plugs 114017-ZZ (Mouser 0, due 2026-12-10). The two DT06-12SA plugs on Dan's TE list are marked claimed by the ST185 loom. | The size 20 sockets go in the box-side X2 half, so X2 cannot be finished without them. Other distributors not checked (**TBD**). | Mouser; `te-on-hand-bom.csv`. Choice C5. |

Not problems, checked and fine: LD1117S33**C**TR is the -40 to +125 C version (ST Table 1: "for C version -40 to +125 C"); FRAM address pins and write-protect are all tied to ground (address 0x50, writes enabled); DT15-12PA contacts are rated 13 A against 7.5 A loads; JST GH carries only signals (1 A rating).


## 3. Open choices (for Dan)

Prices are USD each at quantity 1 unless noted. "Rec." is my recommendation, not a decision.

### C1. Which 5 V regulator is fitted (3 per PDM)? The other two positions become "do not fit".

| | Option | Stock (2026-11-10/11) | Trade-off |
|---|---|---|---|
| a | U1 = CUI VXO7805-500-M-TR, surface mount, 0.5 A | LCSC 0; Mouser "non-stocked"; Octopart "no stock available" | The default in the design, machine-placed, but cannot be bought today. |
| b | U15 (A) / U13 (B) = Traco TSR 1-2450, through-hole, 1 A | Mouser 17,903 at 5.94; LCSC 0 | In stock. Through-hole: soldered by hand or in a second step, and its pins stick out of the back of the board (the back sits on the heat-sink pad: check clearance). |
| c | U14 (A) / U12 (B) = Murata OKI-78SR-5/1.5-W36H-C, through-hole, 1.5 A | Mouser 6,532 at 6.00; LCSC 0 | In stock, most current. Same through-hole notes as b. |
| d | Recom ROF-78E5.0-0.5SMD-R on the U1 pads (named in the schematic note) | not checked: TBD | Surface mount like a; 9 to 36 V input per the schematic note. |

Rec.: **b**, if the pin clearance under the board is fine; otherwise check d. Input range and current of all four are from the schematic note and distributor listings, not from the makers' data sheets (TBD). The 5 V load of a board has not been added up (TBD).

### C2. FRAM (config memory, 3 per PDM)

What the firmware assumes (read in `firmware/hardware/mb85rc.cpp`, `mb85rc.h`, `firmware/core/config_ext.cpp`): I2C address 0x50, **two address bytes**, config written at address 0 in one go, 4-byte CRC right after it, and the chip-ID check is switched off (`CheckId()` returns true before reading the ID). Config is 4,364 bytes (`STATE.md`, Status) + 4 = 4,368 bytes.

| | Option | Stock | Trade-off |
|---|---|---|---|
| a | MB85RC256V, 256 Kbit (as in the schematic). Order code today: RAMXEED MB85RC256VPNF-G-AMERE2 | Mouser 1,425 at 8.41; LCSC: the schematic's number is gone | No change at all. 32,768 bytes (13 % used). 2.7 to 5.5 V, -40 to +85 C. Costs about 25 USD per PDM. |
| b | MB85RC64TA, 64 Kbit. Order codes: MB85RC64TAPNF-G-BDERE1 (Mouser), -AWERE2 (LCSC C43379785) | Mouser 18,749 at 2.90; LCSC 474 at 1.11 | Same 8 pins, same two address bytes (top 3 bits must be 0: true for anything under 8,192), 1.8 to 3.6 V (board gives 3.3 V), -40 to +105 C. 8,192 bytes (53 % used, about 3.8 KB left for growth). Chip ID differs (358h, not 510h): harmless while the ID check is off. No firmware change needed. |
| c | Old order code MB85RC256VPNF-G-JNERE1 from brokers | only non-authorised sellers on Octopart | Not recommended (unknown origin). |

Rec.: **b**. Before ordering, check the 64TA "PNF" package width against the board's SOIC-8 3.9 mm footprint (TBD, not read from the drawing).

### C3. CAN transceiver (3 per PDM), see P3

| | Option | Stock | Trade-off |
|---|---|---|---|
| a | Keep PCA82C250T/YM,118 | LCSC 24,968 at 1.92; Mouser 1,372 at 3.78 | What the schematic names today. Pin 5 and the standby pin are used outside the data sheet. |
| b | TJA1042T/3 | Mouser: /1J 7,481 at 1.90 but flagged **NRND**; the ",118" and "/CM,118" versions flagged **End of Life** | The only option I verified pin by pin: pin 5 = VIO (2.8 to 5.5 V), pin 8 = standby with thresholds relative to VIO. Fits the wiring exactly, but is being phased out. |
| c | TJA1051T/3/2Z (the chip BOM v4 lists) | LCSC C1850231 725 at 1.24; Mouser 10,284 at 1.68 (the /1J version is NRND, ",118" End of Life) | Pin functions not read from the data sheet: TBD. |
| d | Microchip MCP2562FD-E/SN | Mouser 7,747 at 1.29 | Has a VIO pin (Mouser description). Pinout and standby pin not read from the data sheet: TBD. |

Rec.: do not order **a** blind. Have the data sheets of **c** and **d** read (one short job), then pick the one whose pin 5 is VIO and pin 8 is standby. If neither fits, **b** from current stock.

### C4. MCU grade (3 per PDM), see P8

| | Option | Trade-off |
|---|---|---|
| a | STM32F446RET6 (-40 to +85 C), as designed | LCSC 79 at 11.61 (10.25 at 10). Nothing at Mouser. Buy soon. |
| b | STM32F446RET7 (-40 to +105 C) | Same chip, hotter rating. Availability and price TBD. |

Rec.: **a** now (it exists), and look at b only if the enclosure heat check shows board air above about 75 C.

### C5. Harness-side parts still to buy

Checked against TE product pages (contacts, plugs, shells), JST's GH data sheet and Molex part pages. Quantities are for one PDM, no spares.

| Part | Exact number | Qty | Stock | Note |
|---|---|---|---|---|
| X2 box side, size 20 **socket**, solid, nickel, 20 AWG, 7.5 A | TE 0462-201-20141 | 33 | Mouser 0, 130,533 on order (2027-02/03), 0.92 | TE page: "Size 20", "20 AWG", "7.5 A", Active. |
| X2 harness side, size 20 **pin**, solid, nickel, 20 AWG, 7.5 A | TE 0460-202-20141 | 33 | Mouser 318,975 at 0.43 | TE page lists one wire size only: 20 AWG. |
| Sealing plug, size 20 (red) | TE 0413-204-2005 | 9 per X2 half (18 for both) | Mouser 256,825 at 0.18 | For X2 spares 39-47. |
| Sealing plug, size 12 and 16 | TE 114017-ZZ | X2: 5 per half; X1: 1 per half (12 for both halves of both) | Mouser 0, due 2026-12-10, 0.29 | For X2 cavities 1, 4, 5, 6, 34 and X1 cavity F. The TE page for 114017 did not load; fit is from Mouser's description ("SZ12 & 16"): confirm (TBD). |
| Plug for board A header J3 | TE DT06-12SA + wedge W12S | 2 + 2 | Mouser DT06-12SA 34,408 at 4.52; kit DT06-12SA-KIT 282 at 9.37 (wedge included per its description) | Dan's two on-hand DT06-12SA are marked claimed by the ST185 loom. Contacts: 24 size 16 sockets from the on-hand stock. |
| Cable between main board and input board | JST GHR-12V-S housing x 2 per cable, SSHL-002T-P0.2 contact x 24 per cable (or ready-crimped GH leads) | 3 cables | not checked: TBD | JST GH: 1 A, AWG 26 to 30. |
| Mate for input board J2 | Molex 43025-1200 (Micro-Fit receptacle, 12-way) | 3 | Mouser 73,033 at 0.81 | Crimp terminal number: TBD (Molex page lists none). Proposal to verify: Micro-Fit 43030 series for 20 to 24 AWG. |
| Mate for board B J6 | Molex 43025-0400 (Micro-Fit receptacle, 4-way). Proposal: not verified | 1 | TBD | Same terminal as above. |
| Screws and ring lugs for T1-T8 (M4) and the M6 feed terminals | generic | 8 x M4, 6 x M6 | - | Torque: 1.2 Nm (M4, 74650074R), 3.9 Nm (M6, 7461084), Wuerth data sheets. Wire size for 31 A: TBD. |

Studs (6: BATT 150 A, GND, OUT1-4 at 31 A each):

| | Option | Trade-off |
|---|---|---|
| a | Blue Sea Systems 2202 (red) / 2201 (black) feed-through, 5/16"-18 studs | Maker page: 250 A, 48 V DC, IP66, reinforced plastic base, tin-plated copper studs. Ready-made and insulated from the wall. Not on the page (TBD): temperature rating, panel hole and thickness, whether caps are included. |
| b | Blue Sea 2203 / 2204, 3/8"-16 studs | Same family, bigger stud. Ratings not read (TBD). |
| c | Plain brass or copper studs through insulating bushings, with separate rubber boots | Smallest, but every part (stud, bushing, boot) must be picked and its rating found. Nothing researched yet. |

Rec.: **a** for BATT and GND. For the four 31 A outputs **a** also works (large for the job); tell me if size matters and I will research smaller insulated studs. Boots: TBD for every option.

### C6. Which column is the truth for the common parts?

The schematics carry a Digi-Key number and an LCSC number per part, and no maker part number. In at least 5 places the two point to different parts (P9, P10, P12).

| | Option | Trade-off |
|---|---|---|
| a | LCSC column wins (suits JLCPCB assembly) | Cheapest; some parts are copies by other makers and some ratings are lower (P9, P10, P12). |
| b | Digi-Key column wins | Original makers; costs more; each number still has to be looked up (Digi-Key pages could not be read by my tools). |
| c | Add a maker part number field to every part and make both columns follow it | One-time job in the schematic scripts; removes the doubt for good. |

Rec.: **c**, starting with the safety parts (TVS, +12 V capacitors, sense resistors, switches).

### C7. CAN termination (P2)

| | Option | Trade-off |
|---|---|---|
| a | No termination on the boards; a 120 ohm resistor goes in the harness or connector where needed | No board change. Differs from the 2026-11-08 decision. |
| b | Add a 120 ohm resistor and a solder jumper to each main board | Matches the decision. Small board change on A and B. |

Rec.: **b**, done together with the next planned board change.


## 4. Parts by board

"Maker part" is what the schematic's LCSC number resolves to at LCSC on 2026-11-10; the schematics have no maker-part field. Where the Digi-Key field may mean a different maker, see C6. Reference designators, footprints and Digi-Key fields: `docs/parts-audit.csv`.
Per PDM = 2 x A + 1 x B.

### 4.1 Main boards A and B

| Value in schematic | Maker part (from LCSC no.) | Qty A | Qty B | Per PDM | LCSC no., stock, price | Note |
|---|---|---|---|---|---|---|
| BTS7008-2EPA | Infineon BTS70082EPAXUMA1 | 4 | 0 | 8 | C2150060: 98, 1.71. Also C534830 (same chip): 1,940, 1.19 | Mouser 37,831 at 2.40 |
| BTS70012-1ESP | Infineon BTS700121ESPXUMA1 | 0 | 4 | 4 | C3232444: **23**, 6.84 | P15 |
| BTS7004-1EPP | Infineon (order code BTS70041EPPXUMA1 at Mouser) | 0 | 4 | 4 | no field. C534825: 20,982, 1.80 | P13. Mouser 2,720 at 2.39 |
| STM32F446RETx | ST STM32F446RET6 | 1 | 1 | 3 | C69336: **79**, 11.61 | P8, C4 |
| MB85RC256V | not resolved | 1 | 1 | 3 | C47538: **gone** | P4, C2 |
| MCP9808 | Microchip MCP9808T-E/MS | 1 | 1 | 3 | C129490: 516, 2.12 | Mouser 21,642 at 1.40 |
| PCA82C250 | NXP PCA82C250T/YM,118 | 1 | 1 | 3 | C7439: 24,968, 1.92 | P3, C3 |
| LM324 (TSSOP-14) | TI LM324PWR | 2 | 2 | 6 | C7942: 112,900, 0.15 | sense buffers |
| LD1117S33CTR | ST LD1117S33CTR | 1 | 1 | 3 | C35879: 17,135, 0.16 | P11 |
| VXO7805-500-M (U1) | CUI VXO7805-500-M-TR | 1 | 1 | 3 | C5137464: **0** | P1, C1 |
| OKI-78SR-5/1.5-W36H-C | Murata, same | 1 | 1 | 3 | C266374: **0** | P1, C1: alternative to U1 |
| TSR 1-2450 | Traco, same | 1 | 1 | 3 | C6886877: **0** | P1, C1: alternative to U1 |
| 8 MHz crystal 5032 | Abracon ABM3-8.000MHZ-D2Y-T | 1 | 1 | 3 | C144380: 5,267, 0.56 | 18 pF load, matches the "CL=18pF" note |
| SMCJ20CA (TVS) | BORN SMCJ20CA | 1 | 1 | 3 | C152086: 3,725, 0.20 | P12 |
| NUP2105LT1G (CAN protection) | DOWO "NUP2105LT1G" | 1 | 1 | 3 | C2976509: 32,220, 0.05 | P12 |
| Schottky, SOD-123 | Nexperia PMEG10010ELRX (100 V, 1 A) | 3 | 3 | 9 | C179426: 4,080, 0.14 | reverse-battery, 5 V and USB diodes |
| BYG23M (flyback) | Vishay BYG23M-E3/TR | 0 | 8 | 8 | C141573: 19,145, 0.18 | one per board B output |
| 3.3 V zener, SOD-323 | Nexperia PDZ3.3B,115 | 5 | 9 | 19 | C426855: 5,350, 0.20 | clamps on sense and battery-sense lines |
| BAT54S | Nexperia BAT54S,215 | 2 | 2 | 6 | C47546: 264,340, 0.02 | plus 27 on the input boards |
| LED green / red 0805 | OSRAM LG R971 / LS R976 | 2 + 2 | 2 + 2 | 6 + 6 | C2899888: 7,080; C2899997: 10,190 | |
| Ferrite bead 0805 | Murata BLM21PG221SN1D | 1 | 1 | 3 | C85840: 27,660 | |
| RedCubeTerminal (M6 feed) | Wuerth 7461084 (from the footprint name) | 2 | 2 | 6 | C6828431: **gone** | P6. Mouser 4,253 at 4.14 |
| 74650074R (M4 output terminal) | Wuerth 74650074R | 0 | 8 | 8 | no field | P5, P13. Mouser 4,794 at 4.09, 47-week lead time beyond stock |
| Conn_01x12 (J3) | TE DT15-12PA | 1 | 0 | 2 | C5341788: 236, 11.13 | Mouser 5,321 at 10.29 |
| USB-C | GCT USB4085-GF-A | 1 | 1 | 3 | C7095263: **0** | P14. Mouser 105,196 at 0.91 |
| J6 on A (to input board) | none. Footprint says JST SM12B-GHS-TB (side entry) | 1 | 0 | 2 | no field | P13. JST data sheet confirms this is the 12-way side-entry header |
| J7 on B (to input board) | none. Footprint says JST BM12B-GHS-TBT (top entry) | 0 | 1 | 1 | no field | P13 |
| J6 on B (CAN + IN1-2) | none. Footprint says Molex 43045-0412 (Micro-Fit 2x2, vertical) | 0 | 1 | 1 | no field | P13. Molex page: vertical, 8.5 A max |
| BOOT switch | Nidec CJS-1200TB1 | 1 | 1 | 3 | C2921631: **0** | P14 |
| 47 uF 2220 | PSA FS55X476K250LRG (25 V X7R) | 2 | 2 | 6 | C22388555: 5,000, 0.75 | on +5 V. P12 |
| 22 uF 0805 | Samsung CL21A226MAQNNNE (25 V) | 1 | 1 | 3 | C45783 | on +5VP |
| 10 uF 0805 | Samsung CL21A106KAYNNNE (25 V) | 2 | 2 | 6 | C15850 | **C3 is on +12 V: P9** |
| 4.7 uF, 1 uF, 100 nF, 10 nF 0805 | Samsung / Yageo (25 V, 50 V, 50 V, 50 V) | 2, 2, 16, 2 | 2, 2, 20, 10 | 6, 6, 52, 14 | C1779, C28323, C49678, C1710 | |
| 47 nF 0805 | Yageo CC0805JRX7R8BB473 (25 V) | 4 | 8 | 16 | C520039: **400** | on +12 V: P9. 400 covers one PDM |
| 220 pF, 27 pF 0805 | Yageo, FH | 4, 2 | 8, 2 | 16, 6 | C576920, C1808 | |
| 1.2 kohm 0805 (sense) | FOJAN FRC0805J122 (5 %) | 4 | 8 | 16 | C2933520 | P10 |
| 47 ohm 1206 | FOJAN FRC1206J470 (5 %, 0.25 W) | 4 | 8 | 16 | C2907508 | switch ground resistors |
| 4.7 kohm 0805 | Uniroyal 0805W8F4701T5E (1 %) | 28 | 36 | 92 | C17673 | |
| 120 ohm 0805 | Yageo AC0805JR-07120RL (5 %) | 8 (+1 DNP, R12) | 12 | 28 | C229076: **0** | P14. R12 on A is "do not fit" |
| 10 kohm, 1 kohm, 5.1 kohm 0805 | Uniroyal, Uniroyal, Viking | 4, 1, 2 | 4, 1, 2 | 12, 3, 6 | C17414, C17513, C218638 | |
| 47 kohm 0805 | Yageo RT0805DRD0747KL (0.5 %) | 1 | 1 | 3 | C327035: **0** | P14. Battery-voltage divider top resistor |

No part to buy: G2 (logo), H1-H4 (holes), JP1 (solder jumper), and the programming pads (J4 on A, J5 on B: Tag-Connect TC2030 footprint, the cable is a tool).

### 4.2 Input board (x 3 per PDM). No supplier fields at all (P13).

| Value | Footprint | Qty per board | Per PDM | Maker part |
|---|---|---|---|---|
| BAT54S | SOT-23 | 9 | 27 | none given. Same part as on the main boards (Nexperia BAT54S,215 at LCSC C47546) |
| 10 nF | 0603 | 9 | 27 | none: generic, voltage and type not stated |
| 4.7 k | 0603 | 8 | 24 | none: generic |
| 10 k | 0603 | 17 (8 pull-up, 8 pull-down, 1 divider) | 51 | none: generic |
| 20 k | 0603 | 1 | 3 | none: generic. Sets the 0-5 V analog scaling with the 10 k: use 1 % (proposal) |
| J1 "JST GH 12p" | SM12B-GHS-TB footprint | 1 | 3 | none. Proposal: JST SM12B-GHS-TB |
| J2 "Micro-Fit 2x6" | Molex 43045-1200 footprint | 1 | 3 | none. Proposal: Molex 43045-1200 (right-angle, 12-way, 8.5 A max per Molex) |
| SW1, SW2 "A6S-8104" | Omron A6S-810x footprint | 2 | 6 | none. Proposal: Omron A6S-8104-H (Mouser 1,721 at 2.52) |

JST SM12B-GHS-TB total for one PDM: 2 (boards A) + 3 (input boards) = 5.

### 4.3 What is on hand for the box connectors

From `te-on-hand-bom.csv` (not changed): X1 shells HD34-24-21SN and HD36-24-21PN, X2 shells HDP24-24-47SE-L017 and HDP26-24-47PE-L015, size 16 contacts (sockets 0462-201-1631 x 118, pins 0460-202-1631 x 130), size 12 contacts (0462-210-1231 and 0460-220-1231, 20 each), 2 gaskets, 2 panel nuts. No size 20 contacts, no size 20 or 12/16 sealing plugs.

### 4.4 Off-board parts

To buy: section 3, C5. Already on hand: 4.3. Wire sizes and the cavity maps: `docs/box-connectors.md`.

## 5. BOM v4 against the real design

`docs/custom-pdm-bom-v4.xlsx`, sheet "BOM" (its header still says "Draft v3, 2026-11-05"). Not changed.

| v4 line | v4 says | Real design | Difference |
|---|---|---|---|
| 8 A outputs | BTS7008-2EPA x 8 | x 8 | same |
| 15 A outputs | BTS7004-1EPP x 6 | x 4 | **-2** |
| 30 A outputs | BTS70012-1ESP x 2 | x 4 | **+2** (about +14 USD at LCSC price) |
| MCU, plan B | STM32F446RET6 x 3 | x 3 | same |
| FRAM | MB85RC64TA x 3 ("Estimate") | schematic says MB85RC256V | open (C2) |
| Temperature sensor | MCP9808T-E/MS x 3 | x 3 | same |
| CAN transceiver | TJA1051T/3/2Z x 3 | schematic says PCA82C250 | **different chip** (C3) |
| MCU plan C, external ADC, board-to-board connectors | plan C lines | not in the built design | drop |
| Power stage per board | **guess**, 6 USD | 5 V converter (one of three), LD1117S33, SMCJ20CA, 3 Schottky, capacitors | real parts in 4.1 |
| Flyback diodes | **guess**, 8 | 8 x BYG23M (board B only) | count right, price was a guess |
| Passives and misc | **guess**, 10 USD per board | 4.1 | - |
| Universal input front end | **guess**, 21 inputs | 3 input boards with 9 channels each (27 built), plus 2 inputs on each main board | different |
| Connectors, 16 x 8 A | **guess**: 2 Deutsch DT sets | 2 x DT15-12PA header + 2 x DT06-12SA plug inside the box, X1 HD30 on the wall (on hand) | different |
| Screw terminals / studs | **guess** | 8 x 74650074R on board B, 6 studs on the wall | different |
| Heat plate, feed stud / busbar, enclosure | **guess** x 3 | not designed yet | - |

Guessed lines in v4: 11 of 20 (10 marked "Guess", 1 "Estimate"); 2 more are "Marketplace" prices.

Missing from v4 completely: 6 x LM324, 3 x crystal, 3 x USB-C socket, 3 x BOOT switch, 6 x M6 feed terminal (7461084), 5 + 1 JST GH headers and 3 cables, 3 + 1 Micro-Fit headers and their mates, 6 x DIP switch, 3 input-board PCBs, X2 connector with 66 size 20 contacts, sealing plugs, LEDs, protection diodes (zeners, BAT54S, CAN protector, TVS).

## 6. Ratings checked against maker data sheets

| Part | Rating (source) | Load here | Use |
|---|---|---|---|
| BTS7008-2EPA | IL(NOM) 7.5 A at TA 85 C, TJ <= 150 C, all channels active (Table 13, P_7.5.1.8). RDS(ON) 9 mohm typ at 25 C, 16 mohm max at 150 C (P_7.5.1.1/.2). Sense ratio kILIS 5450 typ, +-4.0 % at 5.5 A (Table 22). RthJC 0.8 typ / 1.4 max K/W (Table 6). VS 6 to 18 V normal, 28 V max (Table 5, Table 3). | 7.5 A per channel | **100 %** (P7) |
| BTS7004-1EPP | IL(NOM) 15 A at TA 85 C (Table 13, P_7.5.11.8). RDS(ON) 4.4 typ / 8 max mohm. kILIS 20000, +-5.0 % at 15 A (Table 21). RthJC 1.4 / 2.4 K/W. | 15 A | **100 %** (P7) |
| BTS70012-1ESP | IL(NOM) 31.3 A at TA 85 C (Table 13, P_7.5.23.8). RDS(ON) 1.4 typ / 2.47 max mohm. kILIS 33700, +-4.8 % at 30 A (Table 21). RthJC 0.4 / 0.7 K/W. | 31 A | **99 %** (P7) |
| Sense resistor 1.2 kohm | Sense voltage = load / kILIS x 1200 (worked from the rows above) | 1.65 V at 7.5 A, 0.90 V at 15 A, 1.10 V at 31 A | inside the 3.3 V ADC range |
| Wuerth 74650074R | 50 A at 20 C, no derating data; -55 to +150 C; M4, 1.2 Nm; board 1.6 to 2.0 mm (board B is 1.77 mm) | 31 A / 15 A | 62 % / 30 % of the 20 C figure; at 60 C **TBD** (P5) |
| Wuerth 7461084 | 160 A at 20 C; press-fit; M6, 3.9 Nm; board 1.6 to 3.2 mm | up to 150 A (B), 60 A (A) | 94 % / 38 % of the 20 C figure (P6) |
| TE DT15-12PA (J3) | 13 A per contact, -55 to +125 C, through-hole solder (TE product page) | 7.5 A | 58 %. 8 outputs = 60 A through one header; TE gives no total limit (TBD) |
| TE HD34-24-21SN (X1) | 21 positions, size 12 and 16, socket housing, aluminium, -55 to +125 C (TE page). Per-contact 13 A / 25 A as in `docs/box-connectors.md` | 7.5 A / 15 A | 58 % / 60 % |
| TE HDP24-24-47SE-L017 (X2) | 47 positions, size 16 and 20, socket housing, IP67, -55 to +125 C (TE page) | signals | - |
| TE size 20 contacts | 7.5 A, 20 AWG, nickel, solid (TE pages 0460-202-20141, 0462-201-20141) | signals | - |
| JST GH | 1.0 A with AWG 26, 50 V, -40 to +105 C, wire AWG 30 to 26 (JST eGH data sheet, page 1) | signals, 3.3 V for pull-ups | fine |
| Molex Micro-Fit 43045 | 8.5 A max per contact, 600 V, -40 to +105 C (Molex part pages 430450412, 430451200) | signals | fine |
| PCA82C250 | VCC 4.5 to 5.5 V; pin 5 = reference output; standby >= 0.75 x VCC; high speed <= 0.3 x VCC; -40 to +125 C (Rev. 06, Tables 1, 3, 5, 8) | pin 5 on +3V3, pin 8 on a 3.3 V output | **outside the data sheet** (P3) |
| LD1117S33CTR | Input 15 V max, 800 mA, dropout 1.10 typ / 1.20 max V at 800 mA, junction -40 to +125 C for the C version (Rev 38, Tables 1, 12) | fed from 5 V through a diode | thin (P11) |
| STM32F446RET6 | VDD 1.7 to 3.6 V; suffix 6 = -40 to +85 C, 7 = -40 to +105 C; LQFP64 46 C/W (DS10693 Rev 11) | 3.3 V, box air about 60 C + rise | P8. 5 V tolerance of CAN RX pin PB8: TBD |
| MB85RC256V | 2.7 to 5.5 V, -40 to +85 C, 15-bit address in 2 bytes, ID 00Ah / 510h (DS501-00017-7v0) | 3.3 V | fine |
| MB85RC64TA | 1.8 to 3.6 V, -40 to +105 C, 13-bit address in 2 bytes, ID 00Ah / 358h, same 8-pin layout (DS5v0, pages 1, 2, 7, 12) | 3.3 V | fine (C2) |
| MCP9808T-E/MS | 2.7 to 5.5 V, +-0.5 C, -40 to +125 C (Mouser listing; Microchip PDF could not be fetched) | 3.3 V | maker data sheet: TBD |

## 7. Could not be confirmed (TBD list)

- Digi-Key: no page could be read by my tools, so none of the Digi-Key numbers in the schematics was resolved to a maker part. Digi-Key stock for BTS70012 is from Octopart.
- The three 5 V converters' ratings from their makers' data sheets (CUI site refused the download).
- TVS SMCJ20CA breakdown and clamp values from a maker data sheet (only the LCSC listing and the schematic note), and whether a 32 to 33 V clamp is acceptable for switches with a 28 V maximum (Infineon load-dump rating not read).
- Derating of both Wuerth terminals above 20 C.
- XUMA1 against XUMA2 for BTS70012; lifecycle status from Infineon, NXP (PCA82C250) and Wuerth pages beyond what distributors show.
- Pinouts of TJA1051T/3 and MCP2562FD (C3). Whether PB8 (CAN RX) is 5 V tolerant.
- MB85RC64TA package width against the footprint. STM32F446RET7 availability.
- TE 114017 fit (TE page failed), TE drawings (403 as before), gold against nickel contacts in one mated pair (on-hand size 16 are gold "-1631"; DT15 header pins are nickel per TE).
- Molex Micro-Fit crimp terminal number and the 4-way receptacle number. JST GH housing / contact stock.
- Stud option details (temperature, panel hole, boots). Wire size for 31 A.
- Schottky drop at the real 5 V load (P11); total 5 V load per board.
- Which other schematic files besides `board-a/CAN.kicad_sch` are leftovers.
- The "Assembly" sheet of BOM v4 was not compared.

## 9. Board fix (2026-11-11)

What changed on the boards (choices from `DECISIONS.md` 2026-11-11). Scripts: `tools/sch_board_fix.py`, `tools/board_fix_pcb.py`, `tools/pcb_fix_board_a.py`, `tools/route_board_b.py`.

| Item | Change | Check |
|---|---|---|
| P1 / C1b | U15 (A) / U13 (B) Traco TSR 1-2450 fitted; U1 + U14 (A), U1 + U12 (B) marked DNP | Pin tails about 2.3 mm below the board, far from the pedestals: see `docs/enclosure-layout.md` section 4.1. C1d not needed. |
| P2 / C7b | Open solder jumper + 120 ohm (UNI-ROYAL 0805W8F1200T5E, LCSC C17437) between CAN_H and CAN_L on A and B | Bridge the jumper only on the board at the end of the bus. |
| P3 / C3d | U3 = Microchip MCP2562FD-E/SN (LCSC C124016) | Pin 5 VIO (on +3V3) 1.8 to 5.5 V, pin 8 STBY, STBY high threshold 0.7 x VIO, VDD 4.5 to 5.5 V (Microchip DS20005284B, pin table and section 2.3). Wiring unchanged: matches. |
| P4 / C2b | U5 = MB85RC64TA, order code MB85RC64TAPNF-G-AWERE2 (LCSC C43379785) | All three PNF (SOP-8) drawings: body 3.90 x 4.90 mm, pitch 1.27 mm (JNE drawing: lead span 6.00 mm) = the board's SOIC-8 3.9 x 4.9 mm footprint (RAMXEED DS501-00044-5v0-E). |
| P9 | +12V caps: C3 (10 uF) -> Murata GRM21BR6YA106KE43L, 35 V X5R (LCSC C162422); 47 nF (A: C10, C22, C30, C35; B: C23, C27, C31, C35, C51-C54) -> KEMET C0805C473K5RAC7800, 50 V X7R (LCSC C3879816) | Ratings from the LCSC listings. X5R loses capacitance under 12-14 V DC bias (amount TBD, Murata curve not read). |
| B4-b(b) | Board B: 10k (LCSC C17414) from PB2 (BOOT1) to GND | Firmware unchanged (`LINE_UNUSED` = PB2, input with pull-down). |
| C6c | `Manufacturer` + `MPN` fields on every part above and on the safety parts: TVS D2, all switches, 1.2k sense resistors | MPNs are what the LCSC column resolves to (the assembler's column). Digi-Key numbers of changed parts: TBD (Digi-Key pages not readable). Sense resistors are still the 5 % part (P10 open). Not yet done: every other part. |

**P11 (diode drop on the +5V feed), numbers.** +5V = TSR output minus the Schottky D18 (A) / D4 (B), PMEG10010ELR.
- TSR 1-2450 output: 5 V, set accuracy +-2 % max = 4.90 to 5.10 V (Traco TSR 1 data sheet).
- Load through the diode: CAN chip 45 mA typ / 70 mA max with the bus dominant (DS20005284B, IDD) + LD1117 own use 5 / 10 mA (ST LD1117 Rev 38, Table 6) + the 3.3 V rail (MCU, FRAM, sensor, LEDs: not added up, TBD). So about 0.1 A or more.
- Diode drop at 0.1 A, 25 C: 505 mV typ, 565 mV max (Nexperia PMEG10010ELR v.5, Table 7); 640 / 710 mV at 0.5 A; higher when cold.
- +5V at 0.1 A: 5.00 - 0.505 = **4.50 V typical**, 4.90 - 0.565 = **4.34 V worst case**.
- MCP2562FD needs VDD >= 4.5 V: typical is at the limit, worst case **fails** (the stock PCA82C250 had the same 4.5 V minimum).
- LD1117S33 needs Vin >= 3.3 V + dropout 1.0 typ / 1.1 max V at 100 mA = 4.3 / 4.4 V (ST Table 6): typical passes (0.2 V spare), worst case **fails by about 0.06 V**.
- Fix options (not built; a design choice for Dan): (a) feed U3 VDD from +5VP, ahead of the diode (CAN chip then gets 4.90 to 5.10 V; the regulator stays thin); (b) a lower-drop Schottky for D18 / D4 (part TBD); (c) an ideal-diode / P-FET OR-ing in place of D18 / D4.

**P11 fix (p1a, 2026-11-11): D18 (A) / D4 (B) = Nexperia PMEG2010AEH,115.** Scripts: `tools/sch_board_fix.py` (part and footprint), `tools/board_fix_pcb.py` `swap_footprint` (called by `tools/pcb_fix_board_a.py` and `tools/route_board_b.py`).
- Part (Nexperia PMEG2010AEH v.4, 13 June 2023): 20 V, 1 A, AEC-Q101. VF at 25 C, pulsed: 200 / 220 mV at 10 mA, **265 / 290 mV at 100 mA**, 380 / 430 mV at 1 A (typ / max, Table 7, page 3). IR 15 / 50 uA at 5 V, 25 C (Table 7).
- Cold: at -40 C and 100 mA, VF is about **355 mV typical**, read from the graph (Fig. 1, page 3, curve 4; the 25 C curve reads about 270 mV there, matching Table 7). The data sheet gives no cold maximum; adding the 25 C max-minus-typ spread (25 mV) gives about 380 mV (estimate).
- Footprint: SOD123F, body 2.5-2.7 x 1.5-1.7 mm, lead tips 3.4-3.6 mm apart, leads 0.55-0.70 mm wide (Fig. 5, page 5); Nexperia's reflow footprint has about 1.2 x 1.2 mm lands (Fig. 6, page 5). The old footprint was KiCad `D_SOD-123` (0.9 x 1.2 mm pads, 3.3 mm pitch; the PMEG10010ELR is really SOD123W). Changed to KiCad `Diode_SMD:D_SOD-123F` (1.1 x 1.1 mm pads, 2.8 mm pitch) in the same spot and rotation. The old tracks end at x +-1.65 mm, inside the new pads (+-0.85 to +-1.95 mm), so no re-route; DRC shows 0 unconnected.
- +5V with the new diode, TSR at its 4.90 V minimum (Traco TSR 1, set accuracy +-2 %):
  - 25 C: 4.90 - 0.290 = **4.61 V** (typical 5.00 - 0.265 = 4.74 V; was 4.34 / 4.50 V).
  - -40 C: 4.90 - 0.355 = **4.55 V** (typical VF from the graph); 4.90 - 0.380 = **4.52 V** (estimated cold max).
  - MCP2562FD VDD >= 4.5 V: passes, 0.11 V spare at 25 C, 0.02-0.05 V spare at -40 C (thin).
  - LD1117S33 needs 4.3 / 4.4 V at 100 mA (above): passes with 0.12 V or more spare in every case.
  - Every tolerance stacked at -40 C (TSR tempco +-0.015 %/K max over 65 K = 49 mV, load regulation 0.4 % = 20 mV, line 0.2 % = 10 mV; Traco TSR 1 data sheet) puts the TSR at 4.82 V and +5V at about 4.44 V: 0.06 V under the CAN-chip minimum. That needs all of them at their limit at -40 C at once; not counted as a fail here. If -40 C operation matters, p1b (ideal diode) removes the drop.
- Assembly stock: LCSC C110921 (Nexperia PMEG2010AEH,115, SOD-123F): 10,835 in stock, 0.1082 USD at 5 pcs (LCSC product data, 2026-11-12 01:26 UTC). Digi-Key 1727-PMEG2010AEH,115CT-ND (on backorder, 30-week lead time, Digi-Key page 2026-11-11).
- USB diode D15 (A) / D6 (B), VBUS -> +5V, unchanged: with the TSR running, +5V sits above VBUS minus that diode's drop, so it does not carry the load and does not affect the numbers above. On USB power alone (no 12 V) +5V is VBUS minus about 0.5 V, as before; CAN is not needed then.
- Checks vs `main` 9745129 (KiCad 10 kicad-cli): board A ERC 625 (35 errors), DRC 214 (86 errors), board B ERC 778 (81 errors), DRC 413 (206 errors): every category equal on both boards, 0 unconnected, parity 4 / 4 with the same items; `tools/check_board_b.py` ALL OK.

`docs/parts-audit.csv` still lists the parts as before the board fix.

## 8. Sources

Data sheets (maker):
- Board fix: Traco TSR 1 (https://tracopower.com/tsr1-datasheet; drawing in the 2012 copy https://www.dessy.ru/include/images/ware/pdf/t/tsr_1-2450.pdf); Microchip MCP2561/2FD DS20005284B (https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP2561-2FD-High-Speed-CAN-Flexible-Data-Rate-Transceiver-DS20005284.pdf); Nexperia PMEG10010ELR v.5 (https://assets.nexperia.com/documents/data-sheet/PMEG10010ELR.pdf); Nexperia PMEG2010AEH v.4, 13 June 2023 (https://assets.nexperia.com/documents/data-sheet/PMEG2010AEH.pdf, blocked for scripts; same file read from a distributor copy https://store.comet.bg/download-file.php?id=22368); Digi-Key https://www.digikey.nl/en/products/detail/nexperia-usa-inc/PMEG2010AEH-115/1157670; LCSC listings C124016, C43379785, C162422, C3879816, C17437, C17414, C534825.
- Infineon BTS7008-2EPA, Rev. 1.21, 2024-07-29: https://www.infineon.com/assets/row/public/documents/10/49/infineon-bts7008-2epa-datasheet-cn.pdf
- Infineon BTS70012-1ESP, Rev. 1.21, 2024-07-29: https://www.infineon.com/assets/row/public/documents/10/49/infineon-bts70012-1esp-datasheet-cn.pdf
- Infineon BTS7004-1EPP, Rev. 1.11, 2024-07-29: https://www.infineon.com/assets/row/public/documents/10/49/infineon-bts7004-1epp-datasheet-cn.pdf
  (these three are Infineon's reference-translation copies; they state that the English version rules)
- Wuerth 74650074R: https://www.we-online.com/components/products/datasheet/74650074R.pdf and 7461084: https://www.we-online.com/components/products/datasheet/7461084.pdf
- NXP PCA82C250 Rev. 06: https://www.nxp.com/docs/en/data-sheet/PCA82C250.pdf ; NXP TJA1042 Rev. 11: https://www.nxp.com/docs/en/data-sheet/TJA1042.pdf
- ST LD1117 Rev 38: https://www.st.com/resource/en/datasheet/ld1117.pdf ; ST STM32F446xC/E DS10693 Rev 11: https://www.st.com/resource/en/datasheet/stm32f446re.pdf
- RAMXEED MB85RC64TA DS5v0 (Mouser-hosted copy): https://mouser.com/datasheet/2/1113/MB85RC64TA_DS5v0_E-3538551.pdf ; MB85RC256V DS501-00017-7v0: https://www.mouser.com/datasheet/2/1113/MB85RC256V_DS501_00017_7v0_E-2329117.pdf
- JST GH: https://www.jst-mfg.com/product/pdf/eng/eGH.pdf
- Molex: https://www.molex.com/en-us/products/part-detail/430450412 , .../430451200 , .../430251200
- TE: https://www.te.com/en/product-DT15-12PA.html , product-HD34-24-21SN.html , product-HDP24-24-47SE-L017.html , product-0460-202-20141.html , product-0462-201-20141.html , product-0413-204-2005.html
- Blue Sea Systems 2202: https://www.bluesea.com/products/2202

Stock and price (2026-11-10 to 11):
- LCSC product data by LCSC number (`wmsc.lcsc.com/ftps/wm/product/detail?productCode=...`), 47 numbers, 2026-11-10 23:59 local.
- Mouser search pages (`https://www.mouser.com/c/?q=<part>`), Octopart search pages (`https://octopart.com/search?q=<part>`).

Repo: schematics under `hardware/`, firmware files named in C2, `docs/box-connectors.md`, `docs/enclosure-layout.md`, `docs/custom-pdm-bom-v4.xlsx`; Dan's on-hand list `st185-link-ecu-config/docs/sourcing/te-on-hand-bom.csv`.
