# Parts audit - custom-pdm

Written 2026-11-11 on branch `feat/parts-audit` (from main d319ad3). Stock and prices were checked 2026-11-10 to 2026-11-11.
This file lists what the design really needs and where each rating came from. It makes no choices: the choices it offered are in section 3, each now marked with its decision (`DECISIONS.md` 2026-11-11 to 2026-11-14).
Progress and open items are not repeated here: see the memory-store `BACKLOG.md` (AGENTS.md role table) and `DECISIONS.md`.
Machine-readable copy of the board tables, one row per part group with LCSC stock and price breaks: `docs/parts-audit.csv`.

Marks: **TBD** = could not be confirmed from a primary source. **Proposal** = a part number I suggest, not one the design names.

How the lists were made: `kicad-cli sch export python-bom` (KiCad 10.0.7, read-only) on the three schematics, grouped by value + footprint + fields.
**Update 2026-11-13:** board A J3 (DT15-12PA) and board B J6 (Micro-Fit 2x2) are no longer fitted: both are pads-only footprints in the same holes and the wires are soldered in (PR #41; `docs/box-connectors.md`). Rows below that list the DT15-12PA, its DT06-12SA plug, the J6 Micro-Fit or its 4-way mate are history from 2026-11-11 and are not orderable parts now. The input boards' Micro-Fit J2 and the JST GH links are unchanged.

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
| Choices offered (all decided since) | 7 | section 3 |
| BOM v4 lines that are guesses | 11 of 20 | section 5 |

## 2. Problems and thin margins (most serious first)

Status after the board fix (2026-11-11, branch `feat/board-fix`): section 9. After the board power change (2026-11-14, branch `feat/board-power`): section 10.

| # | What | Why it matters | Source |
|---|---|---|---|
| P1 | **Fixed 2026-11-11 (C1b): one TSR 1-2450 fitted, the other two DNP; see section 9.** Problem as found: **Three 5 V regulators are all in the parts list of every main board** (A: U1, U14, U15; B: U1, U12, U13). All three sit on the same input (+12P) and output (+5VP) nets and none is marked "do not fit". | The schematic's own note says "Use one in place of U1". An assembler working from the BOM would fit all three and tie three switching outputs together. One must be chosen and the other two marked DNP. The default one (U1, VXO7805-500-M-TR) is out of stock everywhere I looked. | Netlist export (nets `+12P`, `+5VP`); text in `Power.kicad_sch`; stock: section 3, C1. Choice C1. |
| P2 | **Fixed 2026-11-11 (C7b): 120 ohm + solder jumper on each main board; see section 9.** Problem as found: **No CAN termination resistor or jumper exists on any board.** Nets CAN_H / CAN_L only reach the transceiver, the protection diode and the connector. The 120 ohm resistors that are on the boards (9 on A, 12 on B) are current-sense filters and LED resistors. | `DECISIONS.md` (CAN, 2026-11-08) says every board keeps a selectable 120 ohm termination. That part is not in the design. | Netlist export, both main boards. Choice C7. |
| P3 | **Fixed 2026-11-11 (C3d): U3 is now Microchip MCP2562FD-E/SN on both main boards (netlist checked 2026-11-14), wiring unchanged; see section 9.** Problem as found: **CAN transceiver U3 was a PCA82C250, wired as if it were a 3.3 V-logic type.** Pin 5 is tied to +3V3 and pin 8 is driven straight from a 3.3 V MCU pin. On a PCA82C250 pin 5 is a reference *output* (0.45 to 0.55 x VCC, specified only for +-50 uA) and standby needs pin 8 above 0.75 x VCC = 3.75 V at 5 V. | A 3.3 V pin cannot reach the 3.75 V standby level, so sleep / standby was not guaranteed; pin 5 was being fed from a supply. This project did not change that part of the circuit, so it most likely comes from stock dingoPDM (not compared with `reference/`); it was outside the data sheet. BOM v4 lists a different chip (TJA1051T/3/2Z). `hardware/board-a/CAN.kicad_sch` is a leftover sheet (its U5 = TJA1042T/3 is not in the netlist). | NXP PCA82C250 data sheet Rev. 06 (2011-08-25), Table 3, Table 5, Table 8. Choice C3. |
| P4 | **Fixed 2026-11-11 (C2b): U5 is now MB85RC64TA; see section 9.** Problem as found: **FRAM U5 (MB85RC256V): the LCSC number in the schematic (C47538) no longer exists**, and the order code behind the Digi-Key field could not be confirmed. Mouser sells the part only as RAMXEED MB85RC256VPNF-G-AMERE2 at 8.41 USD. | Needs a decision anyway (already an open item). | LCSC lookup returned nothing; Mouser search. Choice C2. |
| P5 | **Output terminals T1-T8 (Wuerth 74650074R): rated 50 A "at 20 C" only.** The data sheet has no derating curve and says "Operating current depends on PCB, cable lug and cross section of the cable". | OUT1-4 carry 31 A (62 % of the 20 C figure) in a box designed for about 60 C air. The margin at 60 C is **TBD**: it cannot be read from the data sheet. T5-T8 at 15 A are at 30 %. | Wuerth data sheet 74650074R, rev. 002.002, 2022-08-01, page 1. |
| P6 | **Feed terminals (Wuerth 7461084, 2 per main board): press-fit only, 160 A at 20 C.** The data sheet says "Wave and reflow soldering is not applicable". | (a) They must be pressed in, not soldered: check that the assembler does press-fit and that the hole size follows the Wuerth drawing. (b) Board B can draw 4 x 31 + 4 x 15 = 184 A at rated load, more than the terminal's 160 A; with the 150 A feed limit it is at 94 % of the 20 C figure. Derating at 60 C: **TBD**. | Wuerth data sheet 7461084, rev. 001.003, 2025-06-18. |
| P7 | **All three switch types are used at 100 % of their nominal current.** BTS7008-2EPA 7.5 A of 7.5 A, BTS7004-1EPP 15 A of 15 A, BTS70012-1ESP 31 A of 31.3 A. | The nominal current is defined at 85 C air on a standard test board with junction at or under 150 C. There is no spare: whether it holds depends fully on the heat sink (not designed yet). | Infineon data sheets, Table 13 (P_7.5.1.8, P_7.5.11.8, P_7.5.23.8). Section 6. |
| P8 | **Changed 2026-11-14 (r2a): U4 is now STM32F446RET7 (-40 to 105 C) on both main boards; stock and checks in section 10.** Problem as found: **MCU STM32F446RET6: scarce, and the "6" grade ends at 85 C air.** Mouser 0 in stock with a 52-week factory lead time; LCSC 79; Octopart showed 0 at TME, Newark, Future, Avnet, Arrow. | 3 needed. Buy early. The box air is planned at about 60 C plus its own heating; the 105 C grade is STM32F446RET7 (availability **TBD**). | Mouser, LCSC, Octopart (2026-11-10/11); ST DS10693 Rev 11, ordering scheme. |
| P9 | **Fixed 2026-11-11: +12 V caps now 35 V / 50 V parts; see section 9.** Problem as found: **Capacitors on the +12 V rail below the schematic's own voltage note.** C3 (10 uF, next to the "Min 35V" note) has LCSC part CL21A106KAYNNNE = 25 V. The 47 nF caps on +12 V (4 on A, 8 on B) are 25 V parts too. The TVS clamps at 32.4 V (LCSC listing; schematic note says 33 V). | During a voltage spike the rail may sit above the capacitors' rating. Which part the Digi-Key field points to was not confirmed (**TBD**). | `Power.kicad_sch` text positions; LCSC C15850, C520039, C152086. |
| P10 | **Current-sense resistors (1.2 kohm, 4 per A, 8 on B): the LCSC part is a 5 % type** (FOJAN FRC0805J122). | These set the measured output current (and the overcurrent trip). 5 % resistor error adds straight onto the switch's own 4 to 5 % sense error. The Digi-Key field may point to a 1 % part (**TBD**). | LCSC C2933520; Infineon Table 21 / 22 (kILIS tolerance). |
| P11 | **Fixed 2026-11-11 (p1a, PMEG2010AEH): see section 9. Regulator U2 changed 2026-11-14 to TI TLV1117LV33DCYR (90 mV dropout at 200 mA): section 10.** Problem as found: **The 3.3 V regulator and the CAN chip are fed through a diode from 5 V.** +5VP goes through Schottky D18 (A) / D4 (B) to +5V, which fed LD1117S33 (dropout 1.10 V typ, 1.20 V max at 800 mA) and feeds the CAN chip U3 (then PCA82C250, now MCP2562FD-E/SN; both VDD 4.5 to 5.5 V). | 5.0 V - 3.3 V = 1.7 V, minus the diode drop, is what the regulator gets against a need of up to 1.2 V; the same diode drop may put the CAN chip under its 4.5 V minimum. Diode drop at the real current: worked out in section 9. Most likely the same in stock dingoPDM (not compared). | ST LD1117 Rev 38 Table 12; NXP PCA82C250 Table 1; Microchip DS20005284B section 2.3; netlist. |
| P12 | **LCSC and Digi-Key fields name different makers for protection parts.** TVS D2: LCSC gives BORN SMCJ20CA; CAN protector: LCSC gives DOWO "NUP2105LT1G" (not onsemi); 47 uF: LCSC gives PSA FS55X476K250LRG. | Which column is the real choice? If the boards are assembled from the LCSC column, these are second-source copies of the named parts. | LCSC lookups (section 4.1). Choice C6. |
| P13 | **Parts with no supplier field at all:** board B T1-T8, U23-U26, J6, J7; board A J6; every part on the input board. | An assembly order cannot be made from these BOMs as they are. | Schematic exports. Section 4. |
| P14 | **Out of stock at LCSC (2026-11-10):** USB-C socket USB4085-GF-A (Mouser has 105,196), BOOT switch CJS-1200TB1 (Mouser 0, 5,000 expected 2026-12-01), 47 kohm C327035 and 120 ohm C229076 (generic, pick another line), VXO7805, OKI-78SR, TSR 1-2450 (see P1). | Not blocking, but the BOOT switch has no stock at either place today. | LCSC, Mouser. |
| P15 | **BTS70012-1ESP at LCSC: 23 left** (36 on 2026-11-05). LCSC sells BTS700121ESPXUMA1; the schematic's Digi-Key field and Mouser / Digi-Key stock are BTS700121ESPXUMA2 (Mouser 7,968, Digi-Key 19,906 per Octopart, 4.48 USD at 1). | 4 needed. No shortage outside LCSC. The difference between XUMA1 and XUMA2: **TBD** (Infineon page did not load). | LCSC, Mouser, Octopart. |
| P16 | **Harness-side parts short today:** size 20 sockets 0462-201-20141 (Mouser 0, due 2027-02/03), size 12/16 sealing plugs 114017-ZZ (Mouser 0, due 2026-12-10). The two DT06-12SA plugs on Dan's TE list are marked claimed by the ST185 loom. | The size 20 sockets go in the box-side X2 half, so X2 cannot be finished without them. Other distributors not checked (**TBD**). | Mouser; `te-on-hand-bom.csv`. Choice C5. |

Not problems, checked and fine: LD1117S33**C**TR is the -40 to +125 C version (ST Table 1: "for C version -40 to +125 C"; replaced by TLV1117LV33DCYR 2026-11-14, section 10); FRAM address pins and write-protect are all tied to ground (address 0x50, writes enabled); DT15-12PA contacts are rated 13 A against 7.5 A loads; JST GH carries only signals (1 A rating).


## 3. Choices offered (all decided since)

Prices are USD each at quantity 1 unless noted. "Rec." is my recommendation, not a decision.

### C1. Which 5 V regulator is fitted (3 per PDM)? The other two positions become "do not fit".

Decided 2026-11-11: **b** (C1b, `DECISIONS.md`); built in section 9. The table is the choice as it was offered.

| | Option | Stock (2026-11-10/11) | Trade-off |
|---|---|---|---|
| a | U1 = CUI VXO7805-500-M-TR, surface mount, 0.5 A | LCSC 0; Mouser "non-stocked"; Octopart "no stock available" | The default in the design, machine-placed, but cannot be bought today. |
| b | U15 (A) / U13 (B) = Traco TSR 1-2450, through-hole, 1 A | Mouser 17,903 at 5.94; LCSC 0 | In stock. Through-hole: soldered by hand or in a second step, and its pins stick out of the back of the board (the back sits on the heat-sink pad: check clearance). |
| c | U14 (A) / U12 (B) = Murata OKI-78SR-5/1.5-W36H-C, through-hole, 1.5 A | Mouser 6,532 at 6.00; LCSC 0 | In stock, most current. Same through-hole notes as b. |
| d | Recom ROF-78E5.0-0.5SMD-R on the U1 pads (named in the schematic note) | not checked: TBD | Surface mount like a; 9 to 36 V input per the schematic note. |

Rec.: **b**, if the pin clearance under the board is fine; otherwise check d. Input range and current of all four are from the schematic note and distributor listings, not from the makers' data sheets (TBD). The 5 V load of a board has not been added up (TBD).

### C2. FRAM (config memory, 3 per PDM)

Decided 2026-11-11: **b** (C2b, `DECISIONS.md`); built in section 9. The table is the choice as it was offered.

What the firmware assumes (read in `firmware/hardware/mb85rc.cpp`, `mb85rc.h`, `firmware/core/config_ext.cpp`): I2C address 0x50, **two address bytes**, config written at address 0 in one go, 4-byte CRC right after it, and the chip-ID check is switched off (`CheckId()` returns true before reading the ID). Config size today: `firmware/sim/RESULTS.md` (Results); the "% used" figures below are from the 2026-11-11 size.

| | Option | Stock | Trade-off |
|---|---|---|---|
| a | MB85RC256V, 256 Kbit (as in the schematic). Order code today: RAMXEED MB85RC256VPNF-G-AMERE2 | Mouser 1,425 at 8.41; LCSC: the schematic's number is gone | No change at all. 32,768 bytes (13 % used). 2.7 to 5.5 V, -40 to +85 C. Costs about 25 USD per PDM. |
| b | MB85RC64TA, 64 Kbit. Order codes: MB85RC64TAPNF-G-BDERE1 (Mouser), -AWERE2 (LCSC C43379785) | Mouser 18,749 at 2.90; LCSC 474 at 1.11 | Same 8 pins, same two address bytes (top 3 bits must be 0: true for anything under 8,192), 1.8 to 3.6 V (board gives 3.3 V), -40 to +105 C. 8,192 bytes (53 % used, about 3.8 KB left for growth). Chip ID differs (358h, not 510h): harmless while the ID check is off. No firmware change needed. |
| c | Old order code MB85RC256VPNF-G-JNERE1 from brokers | only non-authorised sellers on Octopart | Not recommended (unknown origin). |

Rec.: **b**. Before ordering, check the 64TA "PNF" package width against the board's SOIC-8 3.9 mm footprint (TBD, not read from the drawing).

### C3. CAN transceiver (3 per PDM), see P3

Decided 2026-11-11: **d** (C3d, `DECISIONS.md`); built in section 9. The table is the choice as it was offered.

| | Option | Stock | Trade-off |
|---|---|---|---|
| a | Keep PCA82C250T/YM,118 | LCSC 24,968 at 1.92; Mouser 1,372 at 3.78 | What the schematic names today. Pin 5 and the standby pin are used outside the data sheet. |
| b | TJA1042T/3 | Mouser: /1J 7,481 at 1.90 but flagged **NRND**; the ",118" and "/CM,118" versions flagged **End of Life** | The only option I verified pin by pin: pin 5 = VIO (2.8 to 5.5 V), pin 8 = standby with thresholds relative to VIO. Fits the wiring exactly, but is being phased out. |
| c | TJA1051T/3/2Z (the chip BOM v4 lists) | LCSC C1850231 725 at 1.24; Mouser 10,284 at 1.68 (the /1J version is NRND, ",118" End of Life) | Pin functions not read from the data sheet: TBD. |
| d | Microchip MCP2562FD-E/SN | Mouser 7,747 at 1.29 | Has a VIO pin (Mouser description). Pinout and standby pin not read from the data sheet: TBD. |

Rec.: do not order **a** blind. Have the data sheets of **c** and **d** read (one short job), then pick the one whose pin 5 is VIO and pin 8 is standby. If neither fits, **b** from current stock.

### C4. MCU grade (3 per PDM), see P8

Decided: C4a on 2026-11-11, replaced by **b** (r2a, `DECISIONS.md` 2026-11-13); built in section 10. The table is the choice as it was offered.

| | Option | Trade-off |
|---|---|---|
| a | STM32F446RET6 (-40 to +85 C), as designed | LCSC 79 at 11.61 (10.25 at 10). Nothing at Mouser. Buy soon. |
| b | STM32F446RET7 (-40 to +105 C) | Same chip, hotter rating. Availability and price TBD. |

Rec.: **a** now (it exists), and look at b only if the enclosure heat check shows board air above about 75 C.

### C5. Harness-side parts still to buy

Decided 2026-11-11: studs **a** for BATT and GND (C5, `DECISIONS.md`); the studs were then replaced by copper bosses and OUT1-4 offset risers (v3b, b4a, d1a; `docs/enclosure-v2b.md`), so the stud table below is superseded. The harness-part list is the list as it was offered; what is still to buy: `STATE.md`, Open items (hardware).

Checked against TE product pages (contacts, plugs, shells), JST's GH data sheet and Molex part pages. Quantities are for one PDM, no spares.

| Part | Exact number | Qty | Stock | Note |
|---|---|---|---|---|
| X2 box side, size 20 **socket**, solid, nickel, 20 AWG, 7.5 A | TE 0462-201-20141 | 33 | Mouser 0, 130,533 on order (2027-02/03), 0.92 | TE page: "Size 20", "20 AWG", "7.5 A", Active. |
| X2 harness side, size 20 **pin**, solid, nickel, 20 AWG, 7.5 A | TE 0460-202-20141 | 33 | Mouser 318,975 at 0.43 | TE page lists one wire size only: 20 AWG. |
| Sealing plug, size 20 (red) | TE 0413-204-2005 | 9 per X2 half (18 for both) | Mouser 256,825 at 0.18 | For X2 spares 39-47. |
| Sealing plug, size 12 and 16 | TE 114017-ZZ | X2: 5 per half; X1: 1 per half (12 for both halves of both) | Mouser 0, due 2026-12-10, 0.29 | For X2 cavities 1, 4, 5, 6, 34 and X1 cavity F. The TE page for 114017 did not load; fit is from Mouser's description ("SZ12 & 16"): confirm (TBD). |
| Plug for board A header J3 (**not needed since PR #41: wire pads**) | TE DT06-12SA + wedge W12S | 2 + 2 | Mouser DT06-12SA 34,408 at 4.52; kit DT06-12SA-KIT 282 at 9.37 (wedge included per its description) | Dan's two on-hand DT06-12SA are marked claimed by the ST185 loom. Contacts: 24 size 16 sockets from the on-hand stock. |
| Cable between main board and input board | JST GHR-12V-S housing x 2 per cable, SSHL-002T-P0.2 contact x 24 per cable (or ready-crimped GH leads) | 3 cables | not checked: TBD | JST GH: 1 A, AWG 26 to 30. |
| Mate for input board J2 | Molex 43025-1200 (Micro-Fit receptacle, 12-way) | 3 | Mouser 73,033 at 0.81 | Crimp terminal number: TBD (Molex page lists none). Proposal to verify: Micro-Fit 43030 series for 20 to 24 AWG. |
| Mate for board B J6 (**not needed since PR #41: wire pads**) | Molex 43025-0400 (Micro-Fit receptacle, 4-way). Proposal: not verified | 1 | TBD | Same terminal as above. |
| Screws and ring lugs for T1-T8 (M4) and the M6 feed terminals | generic | 8 x M4, 6 x M6 | - | Torque: 1.2 Nm (M4, 74650074R), 3.9 Nm (M6, 7461084), Wuerth data sheets. Wire size for 31 A: TBD. |

Studs (6: BATT 150 A, GND, OUT1-4 at 31 A each). **Superseded: no studs; copper bosses (BATT, GND) and offset risers (OUT1-4) instead (b4a, d1a, `docs/enclosure-v2b.md`).** The options as offered:

| | Option | Trade-off |
|---|---|---|
| a | Blue Sea Systems 2202 (red) / 2201 (black) feed-through, 5/16"-18 studs | Maker page: 250 A, 48 V DC, IP66, reinforced plastic base, tin-plated copper studs. Ready-made and insulated from the wall. Not on the page (TBD): temperature rating, panel hole and thickness, whether caps are included. |
| b | Blue Sea 2203 / 2204, 3/8"-16 studs | Same family, bigger stud. Ratings not read (TBD). |
| c | Plain brass or copper studs through insulating bushings, with separate rubber boots | Smallest, but every part (stud, bushing, boot) must be picked and its rating found. Nothing researched yet. |

Rec.: **a** for BATT and GND. For the four 31 A outputs **a** also works (large for the job); tell me if size matters and I will research smaller insulated studs. Boots: TBD for every option.

### C6. Which column is the truth for the common parts?

Decided 2026-11-11: **c** (C6c, `DECISIONS.md`); started in section 9. The table is the choice as it was offered.

The schematics carry a Digi-Key number and an LCSC number per part, and no maker part number. In at least 5 places the two point to different parts (P9, P10, P12).

| | Option | Trade-off |
|---|---|---|
| a | LCSC column wins (suits JLCPCB assembly) | Cheapest; some parts are copies by other makers and some ratings are lower (P9, P10, P12). |
| b | Digi-Key column wins | Original makers; costs more; each number still has to be looked up (Digi-Key pages could not be read by my tools). |
| c | Add a maker part number field to every part and make both columns follow it | One-time job in the schematic scripts; removes the doubt for good. |

Rec.: **c**, starting with the safety parts (TVS, +12 V capacitors, sense resistors, switches).

### C7. CAN termination (P2)

Decided 2026-11-11: **b** (C7b, `DECISIONS.md`); built in section 9. The table is the choice as it was offered.

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
| STM32F446RET7 (was STM32F446RETx = RET6 until 2026-11-14) | ST STM32F446RET7 | 1 | 1 | 3 | C1343794: **0** (2026-11-14); was RET6 C69336: 79, 11.61 | P8, C4, section 10 |
| MB85RC64TA (was MB85RC256V until 2026-11-11) | RAMXEED MB85RC64TAPNF-G-AWERE2 | 1 | 1 | 3 | C43379785 (was MB85RC256V C47538: **gone**) | P4, C2b, section 9 |
| MCP9808 | Microchip MCP9808T-E/MS | 1 | 1 | 3 | C129490: 516, 2.12 | Mouser 21,642 at 1.40 |
| MCP2562FD-E/SN (was PCA82C250 until 2026-11-11) | Microchip MCP2562FD-E/SN | 1 | 1 | 3 | C124016 (was PCA82C250T/YM,118, C7439) | P3, C3, section 9 |
| TLV9004IPWR (TSSOP-14; LM324 until 2026-11-14, LM2902PWR until 2026-11-20) | TI TLV9004IPWR | 2 | 2 | 6 | see CSV; was LM2902PWR C46864 | sense buffers, rail-to-rail; section 14 |
| TLV1117LV33DCYR (was LD1117S33CTR until 2026-11-14) | TI TLV1117LV33DCYR | 1 | 1 | 3 | C15578: **0** (2026-11-14); was LD1117 C35879: 17,135, 0.16 | P11, section 10 |
| VXO7805-500-M (U1) | CUI VXO7805-500-M-TR | 1 | 1 | 3 | C5137464: **0** | P1, C1 |
| OKI-78SR-5/1.5-W36H-C | Murata, same | 1 | 1 | 3 | C266374: **0** | P1, C1: alternative to U1 |
| TSR 1-2450 | Traco, same | 1 | 1 | 3 | C6886877: **0** | P1, C1: alternative to U1 |
| 8 MHz crystal 5032 | Abracon ABM3-8.000MHZ-D2Y-T | 1 | 1 | 3 | C144380: 5,267, 0.56 | 18 pF load, matches the "CL=18pF" note |
| SMCJ20CA (TVS; **5.0SMDJ24CA since 2026-11-16**, section 13.3; **Vishay SM8S24CAHM3/I, DO-218, new spot, since 2026-11-20**, section 14.3) | BORN SMCJ20CA | 1 | 1 | 3 | C152086: 3,725, 0.20 | P12 |
| NUP2105LT1G (CAN protection) | DOWO "NUP2105LT1G" | 1 | 1 | 3 | C2976509: 32,220, 0.05 | P12 |
| Schottky, SOD-123 | Nexperia PMEG10010ELRX (100 V, 1 A) | 3 | 3 | 9 | C179426: 4,080, 0.14 | reverse-battery, 5 V and USB diodes |
| BYG23M (flyback) | Vishay BYG23M-E3/TR | 0 | 8 | 8 | C141573: 19,145, 0.18 | one per board B output |
| 3.3 V zener, SOD-323 | Nexperia PDZ3.3B,115 | 1 | 1 | 3 | C426855 | battery-sense clamp D1 (IS clamps are PDZ5.1B since 2026-11-20, section 14) |
| 5.1 V zener, SOD-323 | Nexperia PDZ5.1B,115 | 4 | 8 | 16 | C85392 | IS-chain clamps (A D9 D12 D13 D14, B D14 D16 D18 D20-D24); section 14 |
| BAT54S | Nexperia BAT54S,215 | 2 | 2 | 6 | C47546: 264,340, 0.02 | plus 27 on the input boards |
| LED green / red 0805 | OSRAM LG R971 / LS R976 | 1 + 2 fitted (+1 green DNP) | 1 + 2 fitted (+1 green DNP) | 3 + 6 | C2899888: 7,080; C2899997: 10,190 | green power LED (A D3, B D5) DNP since 2026-11-14, section 10 |
| Ferrite bead 0805 | Murata BLM21PG221SN1D | 1 | 1 | 3 | C85840: 27,660 | |
| RedCubeTerminal (M6 feed) | Wuerth 7461084 (from the footprint name) | 2 | 2 | 6 | C6828431: **gone** | P6. Mouser 4,253 at 4.14 |
| 74650074R (M4 output terminal) | Wuerth 74650074R | 0 | 8 | 8 | no field | P5, P13. Mouser 4,794 at 4.09, 47-week lead time beyond stock |
| Conn_01x12 (J3) (**wire pads since PR #41, not fitted**) | TE DT15-12PA | 1 | 0 | 2 | C5341788: 236, 11.13 | Mouser 5,321 at 10.29 |
| USB-C | GCT USB4085-GF-A | 1 | 1 | 3 | C7095263: **0** | P14. Mouser 105,196 at 0.91 |
| J6 on A (to input board) | none. Footprint says JST SM12B-GHS-TB (side entry) | 1 | 0 | 2 | no field | P13. JST data sheet confirms this is the 12-way side-entry header |
| J7 on B (to input board) | none. Footprint says JST BM12B-GHS-TBT (top entry) | 0 | 1 | 1 | no field | P13 |
| J6 on B (CAN + IN1-2) (**wire pads since PR #41, not fitted**) | none. Footprint says Molex 43045-0412 (Micro-Fit 2x2, vertical) | 0 | 1 | 1 | no field | P13. Molex page: vertical, 8.5 A max |
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
| 120 ohm 0805 | Yageo AC0805JR-07120RL (5 %) | 7 (+2 DNP: R12, R3) | 11 (+1 DNP: R3) | 25 | C229076: **0** | P14. R12 on A and R3 (power LED, both boards, since 2026-11-14) are "do not fit" |
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
| MCU, plan B | STM32F446RET6 x 3 | STM32F446RET7 x 3 (since 2026-11-14) | **different grade** (r2a) |
| FRAM | MB85RC64TA x 3 ("Estimate") | MB85RC64TA x 3 (since 2026-11-11; MB85RC256V before) | same (C2b) |
| Temperature sensor | MCP9808T-E/MS x 3 | x 3 | same |
| CAN transceiver | TJA1051T/3/2Z x 3 | schematic says MCP2562FD-E/SN (PCA82C250 until 2026-11-11) | **different chip** (C3) |
| MCU plan C, external ADC, board-to-board connectors | plan C lines | not in the built design | drop |
| Power stage per board | **guess**, 6 USD | 5 V converter (one of three), TLV1117LV33 (LD1117S33 until 2026-11-14), SMCJ20CA, 3 Schottky, capacitors | real parts in 4.1 |
| Flyback diodes | **guess**, 8 | 8 x BYG23M (board B only) | count right, price was a guess |
| Passives and misc | **guess**, 10 USD per board | 4.1 | - |
| Universal input front end | **guess**, 21 inputs | 3 input boards with 9 channels each (27 built), plus 2 inputs on each main board | different |
| Connectors, 16 x 8 A | **guess**: 2 Deutsch DT sets | wires soldered to board A J3 wire pads (PR #41; no header or plug), X1 HD30 on the wall (on hand) | different |
| Screw terminals / studs | **guess** | 8 x 74650074R on board B; BATT / GND copper bosses and OUT1-4 copper offset risers through the lid (b4a, d1a; `docs/enclosure-v2b.md`) | different |
| Heat plate, feed stud / busbar, enclosure | **guess** x 3 | not designed yet | - |

Guessed lines in v4: 11 of 20 (10 marked "Guess", 1 "Estimate"); 2 more are "Marketplace" prices.

Missing from v4 completely: 6 x LM324, 3 x crystal, 3 x USB-C socket, 3 x BOOT switch, 6 x M6 feed terminal (7461084), 5 + 1 JST GH headers and 3 cables, 3 + 1 Micro-Fit headers and their mates, 6 x DIP switch, 3 input-board PCBs, X2 connector with 66 size 20 contacts, sealing plugs, LEDs, protection diodes (zeners, BAT54S, CAN protector, TVS).

## 6. Ratings checked against maker data sheets

| Part | Rating (source) | Load here | Use |
|---|---|---|---|
| BTS7008-2EPA | IL(NOM) 7.5 A at TA 85 C, TJ <= 150 C, all channels active (Table 13, P_7.5.1.8). RDS(ON) 9 mohm typ at 25 C, 16 mohm max at 150 C (P_7.5.1.1/.2). Sense ratio kILIS 5450 typ, +-4.0 % at 5.5 A (Rev 1.21 Table 22, P_9.7.1.20; +-3.9 % at 10 A, P_9.7.1.22); firmware `BTS7008_2EPA_KILIS` 5450 on custompdm_a / _b since 2026-11-20 (was the stock 5950, read 9.2 % high; ADR-2026-11-20-kilis). RthJC 0.8 typ / 1.4 max K/W (Table 6). VS 6 to 18 V normal, 28 V max (Table 5, Table 3). | 7.5 A per channel | **100 %** (P7) |
| BTS7004-1EPP | IL(NOM) 15 A at TA 85 C (Table 13, P_7.5.11.8). RDS(ON) 4.4 typ / 8 max mohm. kILIS 20000, +-5.0 % at 15 A (Rev 1.11 Table 21, P_9.7.11.23; 20000 from 2 A up); firmware `BTS7004_1EPP_KILIS` 20000 (equal). RthJC 1.4 / 2.4 K/W. | 15 A | **100 %** (P7) |
| BTS70012-1ESP | IL(NOM) 31.3 A at TA 85 C (Table 13, P_7.5.23.8). RDS(ON) 1.4 typ / 2.47 max mohm. kILIS 33700, +-4.8 % at 30 A (Rev 1.21 Table 21, P_9.7.26.26; 33700 from 7 A up); firmware `BTS70012_1ESP_KILIS` 33700 on custompdm_a / _b since 2026-11-20 (was the stock 35000, read 3.9 % high; ADR-2026-11-20-kilis). RthJC 0.4 / 0.7 K/W. | 31 A | **99 %** (P7) |
| Sense resistor 1.2 kohm | Sense voltage = load / kILIS x 1200 (worked from the rows above) | 1.65 V at 7.5 A, 0.90 V at 15 A, 1.10 V at 31 A | inside the 3.3 V ADC range; the top of the chain is the PDZ3.3B zener (about 2.7 V at the 0.4 mA a PROFET fault pushes into it, estimate), so the firmware full-scale rule fires at 75 % (2.475 V, `PROFET_IS_FULL_SCALE` 3071, 2026-11-20) |
| Wuerth 74650074R | 50 A at 20 C, no derating data; -55 to +150 C; M4, 1.2 Nm; board 1.6 to 2.0 mm (board B is 1.77 mm) | 31 A / 15 A | 62 % / 30 % of the 20 C figure; at 60 C **TBD** (P5) |
| Wuerth 7461084 | 160 A at 20 C; press-fit; M6, 3.9 Nm; board 1.6 to 3.2 mm | up to 150 A (B), 60 A (A) | 94 % / 38 % of the 20 C figure (P6) |
| TE DT15-12PA (J3; not fitted since PR #41) | 13 A per contact, -55 to +125 C, through-hole solder (TE product page) | 7.5 A | 58 %. 8 outputs = 60 A through one header; TE gives no total limit (TBD) |
| TE HD34-24-21SN (X1) | 21 positions, size 12 and 16, socket housing, aluminium, -55 to +125 C (TE page). Per-contact 13 A / 25 A as in `docs/box-connectors.md` | 7.5 A / 15 A | 58 % / 60 % |
| TE HDP24-24-47SE-L017 (X2) | 47 positions, size 16 and 20, socket housing, IP67, -55 to +125 C (TE page) | signals | - |
| TE size 20 contacts | 7.5 A, 20 AWG, nickel, solid (TE pages 0460-202-20141, 0462-201-20141) | signals | - |
| JST GH | 1.0 A with AWG 26, 50 V, -40 to +105 C, wire AWG 30 to 26 (JST eGH data sheet, page 1) | signals, 3.3 V for pull-ups | fine |
| Molex Micro-Fit 43045 | 8.5 A max per contact, 600 V, -40 to +105 C (Molex part pages 430450412, 430451200) | signals | fine |
| PCA82C250 (replaced by MCP2562FD-E/SN 2026-11-11, section 9) | VCC 4.5 to 5.5 V; pin 5 = reference output; standby >= 0.75 x VCC; high speed <= 0.3 x VCC; -40 to +125 C (Rev. 06, Tables 1, 3, 5, 8) | pin 5 on +3V3, pin 8 on a 3.3 V output | **was outside the data sheet** (P3) |
| LD1117S33CTR (replaced by TLV1117LV33DCYR 2026-11-14, section 10) | Input 15 V max, 800 mA, dropout 1.10 typ / 1.20 max V at 800 mA, junction -40 to +125 C for the C version (Rev 38, Tables 1, 12) | fed from 5 V through a diode | thin (P11) |
| STM32F446RET7 (RET6 until 2026-11-14) | VDD 1.7 to 3.6 V; suffix 6 = -40 to +85 C, 7 = -40 to +105 C; LQFP64 46 C/W (DS10693 Rev 11) | 3.3 V, box air about 60 C + rise | P8. 5 V tolerance of CAN RX pin PB8: TBD |
| MB85RC256V | 2.7 to 5.5 V, -40 to +85 C, 15-bit address in 2 bytes, ID 00Ah / 510h (DS501-00017-7v0) | 3.3 V | fine |
| MB85RC64TA | 1.8 to 3.6 V, -40 to +105 C, 13-bit address in 2 bytes, ID 00Ah / 358h, same 8-pin layout (DS5v0, pages 1, 2, 7, 12) | 3.3 V | fine (C2) |
| MCP9808T-E/MS | 2.7 to 5.5 V, +-0.5 C, -40 to +125 C (Mouser listing; Microchip PDF could not be fetched) | 3.3 V | maker data sheet: TBD |

## 7. Could not be confirmed (TBD list)

- Digi-Key: no page could be read by my tools, so none of the Digi-Key numbers in the schematics was resolved to a maker part (2026-11-14: the PR #23 / #24 parts and BTS7004-1EPP were looked up, see `tools/sch_digikey.py`; the older inherited numbers are still unchecked). Digi-Key stock for BTS70012 is from Octopart.
- The three 5 V converters' ratings from their makers' data sheets (CUI site refused the download).
- ~~TVS SMCJ20CA breakdown and clamp values from a maker data sheet, and whether a 32 to 33 V clamp is acceptable for switches with a 28 V maximum.~~ Answered 2026-11-16: section 13.3 (D2 is now 5.0SMDJ24CA).
- Derating of both Wuerth terminals above 20 C.
- XUMA1 against XUMA2 for BTS70012; lifecycle status from Infineon, NXP (PCA82C250) and Wuerth pages beyond what distributors show.
- Pinout of TJA1051T/3 (C3; MCP2562FD done in section 9). Whether PB8 (CAN RX) is 5 V tolerant.
- MB85RC64TA package width against the footprint (done in section 9). STM32F446RET7 availability (checked 2026-11-14: none in stock, section 10).
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
| C6c | `Manufacturer` + `MPN` fields on every part above and on the safety parts: TVS D2, all switches, 1.2k sense resistors | MPNs are what the LCSC column resolves to (the assembler's column). Digi-Key numbers of changed parts: filled 2026-11-14 by `tools/sch_digikey.py` (numbers, product pages and the two left TBD there). Sense resistors are still the 5 % part (P10 open). Not yet done: every other part. |

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

`docs/parts-audit.csv` is regenerated from the schematics by `tools/gen_parts_audit_csv.py` (2026-11-11; LCSC data of the new part numbers looked up 2026-11-12 03:21 UTC, the rest carried over from 2026-11-10).

## 10. Board power change (2026-11-14)

Choices: r2a (`DECISIONS.md` 2026-11-13) and s4a / s5a / s6a (2026-11-14). Scripts: `tools/sch_board_power.py` and `tools/pcb_board_power.py`, the last stages of `tools/build_board_a.ps1` and `tools/build_board_b.ps1`. Part fields and fit attributes only: no symbol pin, net, footprint, pad, track or zone change.

| Ref (both main boards) | Change | Check |
|---|---|---|
| U4 MCU | STM32F446RETx (RET6, LCSC C69336) -> **STM32F446RET7**: LCSC C1343794, Digi-Key 497-16775-ND, Manufacturer + MPN | ST DS10693 Rev 11 (May 2026), section 8 "Ordering information": the last digit is only the temperature range ("6 = -40 to 85 C", "7 = -40 to 105 C"); R = 64 pins, E = 512 KB, T = LQFP. Section 4 "Pinout and pin description" gives one LQFP64 pinout (Figure 10) and one pin table (Table 10) for every STM32F446xC/xE; nothing in them depends on the temperature digit. Same LQFP-64 footprint, so no pin, board or firmware change. |
| U2 3.3 V regulator | LD1117S33CTR -> **TI TLV1117LV33DCYR**: LCSC C15578, Digi-Key 296-28778-1-ND (cut tape; -2-ND reel, -6-ND Digi-Reel), Manufacturer + MPN, Datasheet link | Checks (a) to (d) below: all pass. |
| Power LED: A D3 + R3, B D5 + R3 | **Do not fit** (s6a), and left out of the BOM and the position files (schematic `dnp` / `in_bom` / `in_pos_files`; PCB attributes) | Footprints, the bridged jumper JP1 and all copper stay, so the LED can be fitted by hand later. Expected saving: about 6.7 mA or more per board, asleep or awake ((3.3 V - 2.5 V) / 120 ohm; LED Vf at 20 mA, figure from the 2026-11-13 sleep study, PR #52). |

TLV1117LV33DCYR checks (TI SBVS160C, revision C, January 2023):
- (a) **Pinout.** Table 5-1, DCY (SOT-223): pin 1 GND, pin 2 OUT, pin 3 IN, tab = OUT. Netlist, both boards: U2.1 = GND, U2.2 and U2.4 (tab) = +3V3, U2.3 = +5V. Same pads as the LD1117: pass.
- (b) **Input voltage.** Recommended VIN 2 to 5.5 V; absolute maximum 6 V (sections 6.3, 6.1). U2 is fed only from +5V. +5V has only two sources (netlist): the 5 V converter through D18 (A) / D4 (B), and USB VBUS through D15 (A) / D6 (B). There is no path from +12 V; the DNP converters U1 / U14 (A) and U1 / U12 (B) would feed +5VP like the TSR. Worst-case highs:
  - TSR 1-2450 (Traco TSR 1 data sheet, 2024-10-22): 5.00 V x (1 + 2 % set accuracy + 0.2 % line + 0.4 % load) = 5.13 V, plus 1 % start-up overshoot = 5.18 V, before the Schottky. Pass.
  - USB: port VBUS 5.50 V maximum (USB 3.1 ECN "VBUS Max Limit", raised from 5.25 V), minus the D15 / D6 drop. Pass. This is the thinnest case: at very light load the drop is small, so U2 can see close to 5.5 V, still under the 6 V absolute maximum.
- (c) **Capacitors.** Section 8.2.2.1: "1.0-uF ceramic capacitors are required at the output"; effective output capacitance must stay above 0.5 uF; stable with no ESR. **No maximum output capacitance is stated** (this closes the earlier TBD). +3V3 has 10 uF + 4.7 uF + 2 x 1 uF + 9 x 100 nF, all 0805 ceramic (A: C6, C14, C16, C18; B: C6, C15, C17, C19), about 18.6 uF nominal. The input capacitor is optional; 0.1 to 1 uF is suggested. +5V has 100 nF (C5) + 2 x 47 uF (A: C41 / C42, B: C39 / C40). Pass.
- (d) **Load.** IOUT 0 to 1 A (section 6.3); current limit 1.1 A minimum (6.5). The awake 3.3 V load is about 155 mA worst case: MCU at 180 MHz with all peripherals on, 110 mA max at 105 C with prefetch off (DS10693 Table 23, read 2026-11-14) or about 125 mA with prefetch on (Table 24, value from the 2026-11-13 sleep study, PR #52, not re-read), plus two status LEDs, 2 x LM324, sensor and FRAM. That is about 16 % of the 1 A rating. Dropout at 200 mA is 90 mV typical (6.5), so U2 needs about 3.4 V in; +5V is at least 4.44 V (section 9, every tolerance stacked at -40 C). Heat: (5.18 - 3.3) V x 0.155 A = 0.29 W; RθJA 62.9 C/W (6.4) gives about 18 C over the board, against TJ up to 125 C. Pass.
- Sleep: quiescent current 50 uA typical, 100 uA maximum (6.5), against 5 mA typical for the LD1117.

Stock, checked 2026-11-14 (the assembler sources these, s5a):
- STM32F446RET7: **none in stock anywhere checked.** LCSC C1343794 0; Digi-Key 497-16775-ND out of stock, backorder, 52-week factory lead time; Mouser 511-STM32F446RET7 4,787 shown with an expected date of 2027-02-22, and 511-STM32F446RET7TR 17,000 on order with no date.
- TLV1117LV33DCYR: LCSC C15578 0; Mouser 153,317 in stock; Digi-Key stock not shown on the page read (20-week lead time).

Checks vs `main` efa632d (KiCad 10 kicad-cli, read-only): board A ERC 625 (35 errors), DRC 214 (86 errors), 0 unconnected, parity 4; board B ERC 778 (81 errors), DRC 413 (206 errors), 0 unconnected, parity 4. Every ERC and DRC category is equal on both boards. Netlist connectivity is identical: same nets, same pin sets. The only component differences are the four parts above. `tools/check_board_b.py`: ALL OK. PCB diff: field and attribute lines only, and the PCBs stay KiCad 9 format (version 20241229). A full rebuild of each board with the build scripts gives the same result (same nets, same DRC counts, same attributes).

`docs/parts-audit.csv` regenerated 2026-11-14 by `tools/gen_parts_audit_csv.py`: C1343794 and C15578 looked up live at LCSC (both 0 in stock), every other row carried over. Because the power LED and its resistor are now out of the BOM, the CSV no longer lists A D3 / R3 or B D5 / R3.

Sources for this section: TI TLV1117LV SBVS160C (https://www.ti.com/lit/ds/symlink/tlv1117lv.pdf); ST DS10693 Rev 11 (https://www.st.com/resource/en/datasheet/stm32f446re.pdf); Traco TSR 1 (https://tracopower.com/tsr1-datasheet); USB 3.1 ECN "VBUS Max Limit" (https://doc.xdevs.com/doc/Standards/USB%203.1/usb_31_030215/ECNs/USB%203.1%20ECN%20VBUS%20Max%20Limit.pdf); Digi-Key https://www.digikey.com/en/products/detail/texas-instruments/TLV1117LV33DCYR/2666508 and https://www.digikey.ca/en/products/detail/stmicroelectronics/STM32F446RET7/6207480; Mouser search pages for both parts; LCSC through `tools/gen_parts_audit_csv.py`.

- RET6 as an approved alternate: s9a, `DECISIONS.md` 2026-11-14.

## 11. Temperature-grade check (2026-11-14, research only)

Basis: board-top background 100 C at worst load, hot spots 119-121 C at the switch chips (`docs/heat-analysis.md`, v2b model). No checked IC or diode sits within about 9 mm of a switch chip (closest: U3 CAN chip about 10 mm, zener clamps 9-10 mm). Input board is not in the heat model; 100 C assumed. Ratings from maker data sheets (links below); TBD = not confirmed.

| Part (refs, qty per PDM) | Rated | Margin at 100 C | Candidate replacement |
|---|---|---|---|
| LM324PWR (A U7 / U12, B U7 / U22; 6) | TA 0 to 70 C (TI SLOS066AE 6.3) | -30 K | LM2902PWR, -40 to 125 C, same TSSOP-14 pinout (same TI document); LCSC C46864, DK 296-6600-1-ND; drop-in. **Fitted 2026-11-14 (t1a, branch `feat/lm2902`)**, part fields only via `tools/sch_board_power.py` / `tools/pcb_board_power.py`. SLOS066AE (rev AE, Sept 2025, https://www.ti.com/lit/ds/symlink/lm2902.pdf): pinout Figure 5-1 / Table 5-1 is one table for LM324 and LM2902 (PW pkg); LM2902PWR = plain LM2902 (package addendum), 6.3: VCC 3 to 26 V, TA -40 to 125 C; rail here is +3V3 (pin 4; pin 11 GND, netlist); 6.7 vs 6.8: VICR (0 to VCC - 1.5 V at 25 C, VCC - 2 V full range), VOH (VCC - 1.5 V at 25 C), VOL, ICC 0.7 / 1.2 mA all equal, so the sense-buffer swing (3.3 V clamp assumption, `firmware/sim/RESULTS.md`) is unchanged; LCSC and Digi-Key pages both show TI LM2902PWR, TSSOP-14 (DK -40 to 125 C). ERC / DRC / parity / netlist equal to `main` 12c7fef on both boards |
| Omron A6S-8104 DIP (input SW1 / SW2; 6) | -20 to +70 C (Omron A102-E1-02) | -30 K | no 105 C DIP switch found: solder jumpers / 0R (footprint change), or C&K SD08H0SBR (-40 to 85 C, DK CKN6128CT-ND, footprint change, still 15 K short) |
| Traco TSR 1-2450 (A U15, B U13; 3) | -40 to +85 C (Traco TSR 1, 2026-07-02) | -15 K (real air is lid air, TBD) | TI LMZM23601V5 (TJ -40 to 125 C, SMD, footprint change; LCSC C2868357, DK TBD) or RECOM RPX-1.0 (TJ -40 to 125 C, needs 4 resistors); every SIP-3 7805-type found stops at 85-90 C |
| Abracon ABM3-8.000MHZ-D2Y-T (Y1; 3) | -40 to +85 C (code D) | -15 K | ECS-80-18-30Q-CES-TR, 2-pad 5 x 3.2, 18 pF, -40 to 125 C, AEC-Q200, DK 50-ECS-80-18-30Q-CES-TRCT-ND; drop-in |
| X5R caps (A C3, C4, C6, C14, C38; B C3, C4, C6, C10, C15; 15) | 85 C (X5R) | -15 K | X7R: +12 V 10 uF CL31B106KBHNNNE (50 V, 1206, footprint change, LCSC C89632); +5VP 22 uF GRM21BZ71A226ME15L (0805, LCSC C907991); 3V3 10 uF TDK C2012X7R1A106K125AC (LCSC C2167452); 4.7 uF CL21B475KAFNNNE (LCSC C98195) |
| OSRAM LS R976 / LG R971 LEDs (9) | -30 to +85 C (LG R971 current sheet TBD) | -15 K | best 0805 found: Lumex SML-LX0805SIC-HT, -40 to +100 C |
| GCT USB4085-GF-A (A J5, B J2; 3) | -40 to +85 C | -15 K | service port; no 105 C part found |
| CJS-1200TB BOOT switch (3) | -40 to 85 C | -15 K | bench use only; no replacement found |
| STM32F446RET7 (U4; 3) | TA 105 C at max power, TJ max 125 C (DS10693 Rev 11 Table 16) | TA +5 K; TJ about 110-115 C (power TBD) | keep; RET6 is an approved alternate (s9a, `DECISIONS.md` 2026-11-14), but its TJ max is 105 C (same table), so the firmware thermal limits must suit RET6 if it is fitted |
| MB85RC64TA FRAM (U5; 3) | -40 to +105 C (RAMXEED DS5v0) | +5 K | keep, or Infineon CY15B064J-SXE (-40 to 125 C, about +3.4 USD) |
| JST GH, Molex Micro-Fit 43045 | -40 to +105 C incl. current rise | +5 K | keep |

Pass: TLV1117LV (TJ 125 C), MCP2562FD-E (TA 125 C), MCP9808-E (125 C; accuracy +-1 C above 100 C), PMEG2010AEH / PMEG10010ELR / PDZ3.3B / SMCJ20CA / BYG23M (150-175 C), NUP2105L (125 C), BLM21PG ferrite (125 C), UNI-ROYAL / FOJAN resistors (155 C), X7R / C0G caps, REDCUBE terminals (150 C). TBD: BAT54S, YAGEO and Viking resistors, input-board passives (no part numbers yet).

FRAM size: config size in `firmware/sim/RESULTS.md` (Results); it fits the 8,192-byte 64 Kbit part. The 256 Kbit MB85RC256V is rated only 85 C; a 125 C 256 Kbit part exists (CY15B256J-SXE, about +15 USD). Recommendation: stay at 64 Kbit.

Sources: TI SLOS066AE (LM324 / LM2902); Omron https://media.onlinecomponents.com/productfiles/mf-om/en-a6ta6s.pdf ; Traco TSR 1 data sheet; TI SNVSAQ4C (LMZM23601); RECOM https://recom-power.com/pdf/Innoline/RPX-1.0.pdf ; Abracon ABM3; OSRAM https://ams-osram.com/de/products/leds/color-leds/osram-chip-led-0805-ls-r976 ; GCT https://gct.co/connector/USB4085 ; ST DS10693 Rev 11; RAMXEED https://mouser.com/datasheet/2/1113/MB85RC64TA_DS5v0_E-3538551.pdf ; Infineon 002-42371 (CY15B256J); TI SBVS160C; Microchip DS20005284A, DS20005095B; JST eGH.

## 12. Sources (was section 8; sections 10 and 11 list their own sources)

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

## 13. PCB order prep (2026-11-16, branch `feat/pcb-order-prep`)

Fab and assembler: JLCPCB with LCSC parts, PCBWay as the fallback (DECISIONS 2026-11-11, 2026-11-16 f1). Fab outputs and how to upload them: `hardware/fab/README.md`.

### 13.1 Order fields

`tools/sch_bom_fields.py` (schematic, A | B | IN) and `tools/pcb_bom_fields.py` (PCB) are the last stage of all three board builds. One table sets Manufacturer, MPN, LCSC, Digi-Key_PN and Alternates on every fitted part; a placed part with no row stops the script. Fields only (each changed file equals the old one once those property blocks are removed), PCBs stay KiCad 9.

| Board | Fitted parts | MPN before -> after | LCSC before -> after | Digi-Key before -> after |
|---|---|---|---|---|
| A | 123 | 23 -> 123 | 122 -> 123 | 117 -> 123 |
| B | 188 | 36 -> 188 | 179 -> 180 | 170 -> 188 |
| Input | 48 | 0 -> 48 | 0 -> 48 | 0 -> 48 |

Not counted as parts: holes, logos, solder jumpers, wire pads (A J3, B J6), Tag-Connect pads. B T1-T8 (Wurth 74650074R) have no LCSC / JLCPCB listing: JLCPCB global sourcing (Digi-Key 732-74650074RCT-ND).
Digi-Key numbers that were already in the schematics are kept (inherited from stock dingoPDM, not re-checked); several name another maker than the MPN (same value / package): the LCSC column is what JLCPCB fits.

Changed for design need and cost (same footprint, no copper change):
- 120R (A 8, B 12, incl. the CAN terminators): YAGEO AC0805JR-07120RL (5 %, extended) -> UNI-ROYAL 0805W8F1200T5E (1 %, JLCPCB basic, LCSC C17437).
- 1.2k current-sense resistors (P10): FOJAN FRC0805J122 (5 %, extended) -> UNI-ROYAL 0805W8F1201T5E (1 %, basic, LCSC C17379). The Digi-Key column already named a 1 % part (YAGEO RC0805FR-071K2L, 311-1.20KCRCT-ND).
- D2 TVS: section 13.3.

Footprint checks (MPN package against the footprint): every part matches its footprint's package and pin count (LCSC package field 2026-11-16; ICs, connectors and switches by maker part). One loose fit, inherited from stock dingoPDM: PMEG10010ELRX (A D15 / D19, B D3 / D6) is SOD123W on a `D_SOD-123` land: lead tips 1.65-1.85 mm and lead inner ends 1.05-1.55 mm from the centre (Nexperia PMEG10010ELR, SOD123W outline: HE 3.3-3.7, Lp 0.3-0.6 mm) against pads at 1.2-2.1 mm, so every lead overlaps its pad by 0.3 mm or more.

### 13.2 Parts against JLCPCB (stock read 2026-11-16 on jlcpcb.com part pages; LCSC stock in `docs/parts-audit.csv`)

Per PDM = 2 x A + 1 x B + 3 x input board. "short" = JLCPCB stock below one PDM's need. Rule (Dan 2026-11-14): the design part stays; the assembler buys it (JLCPCB global sourcing) or fits the approved alternate.

| Maker MPN | LCSC | JLCPCB type | JLCPCB stock | Per PDM | Boards | Approved alternates |
|---|---|---|---|---|---|---|
| YAGEO CC0805KRX7R9BB104 | C49678 | basic | 23699183 | 52 | A B | - |
| Nexperia PDZ3.3B,115 | C426855 | ext | 5561 | 3 | A B | - |
| Nexperia PDZ5.1B,115 | C85392 | ext | LCSC 6230 (2026-11-20) | 16 | A B | - |
| YAGEO RT0805DRD0747KL | C327035 | ext | 52 | 3 | A B | UNI-ROYAL 0805W8F4702T5E (1 %, LCSC C17713, basic) |
| UNI-ROYAL 0805W8F4701T5E | C17673 | basic | 4625794 | 92 | A B | - |
| Murata GRM21BR6YA106KE43L | C162422 | ext | 14573 | 3 | A B | - |
| Samsung Electro-Mechanics CL21A226MAQNNNE | C45783 | basic | 3907161 | 3 | A B | - |
| Samsung Electro-Mechanics CL21A106KAYNNNE | C15850 | basic | 8829911 | 3 | A B | - |
| PSA FS55X476K250LRG | C22388555 | ext | 4752 | 6 | A B | - |
| Vishay SM8S24CAHM3/I (D2 since 2026-11-20; was DOWO 5.0SMDJ24CA, C284111) | C20036943 | ext | LCSC 2 (2026-11-20): assembler global sourcing or an alternate | 3 | A B | Bourns SM8S24CA-Q (DK SM8S24CA-QCT-ND, active, 14,800 in stock 2026-11-20); Panjit SM8H24CAS-AU |
| Nexperia PMEG2010AEH,115 | C110921 | ext | 10670 | 3 | A B | - |
| Nexperia PMEG10010ELRX | C179426 | ext | 33245 | 6 | A B | - |
| Texas Instruments TLV1117LV33DCYR | C15578 | ext | 498 | 3 | A B | - |
| Traco Power TSR 1-2450 | C6886877 | ext | 40 | 3 | A B | - |
| Wurth Elektronik 7461084 | C6828431 | ext | 0 **short** | 6 | A B | - |
| GCT USB4085-GF-A | C7095263 | ext | 4146 | 3 | A B | - |
| Viking ARG05FTC5101 | C218638 | ext | 12131 | 6 | A B | - |
| UNI-ROYAL 0805W8F1002T5E | C17414 | basic | 47179913 | 13 | A B | - |
| FH (Guangdong Fenghua) 0805CG270J500NT | C1808 | ext | 46803 | 6 | A B | - |
| Samsung Electro-Mechanics CL21A475KAQNNNE | C1779 | basic | 2084257 | 6 | A B | - |
| Samsung Electro-Mechanics CL21B105KBFNNNE | C28323 | basic | 4246729 | 6 | A B | - |
| DOWO NUP2105LT1G | C2976509 | ext | 27272 | 3 | A B | onsemi NUP2105LT1G (DK NUP2105LT1GOSCT-ND) |
| OSRAM LS R976-NR-1-0-20-R18 | C2899997 | ext | 12692 | 6 | A B | - |
| OSRAM LG R971-KN-1-0-20-R18 | C2899888 | ext | 2625 | 3 | A B | - |
| Murata BLM21PG221SN1D | C85840 | ext | 26736 | 3 | A B | - |
| JST SM12B-GHS-TB(LF)(SN) | C265421 | ext | 34539 | 5 | A IN | - |
| UNI-ROYAL 0805W8F1001T5E | C17513 | basic | 39261625 | 3 | A B | - |
| UNI-ROYAL 0805W8F1200T5E | C17437 | basic | 969818 | 28 | A B | YAGEO RC0805FR-07120RL (DK 311-120CRCT-ND) |
| Nidec Components CJS-1200TB1 | C2921631 | ext | 0 **short** | 3 | A B | - |
| Microchip MCP2562FD-E/SN | C124016 | ext | 792 | 3 | A B | - |
| STMicroelectronics STM32F446RET7 | C1343794 | ext | 0 **short** | 3 | A B | STMicroelectronics STM32F446RET6 (s9a; LCSC C69336) |
| Abracon ABM3-8.000MHZ-D2Y-T | C144380 | ext | 5015 | 3 | A B | - |
| RAMXEED (Fujitsu) MB85RC64TAPNF-G-AWERE2 | C43379785 | ext | 468 | 3 | A B | RAMXEED MB85RC64TAPNF-G-BDERE1 (same chip, other packing; Mouser) |
| Microchip MCP9808T-E/MS | C129490 | ext | 503 | 3 | A B | - |
| Samsung Electro-Mechanics CL21B103KBANNNC | C1710 | basic | 2133107 | 14 | A B | - |
| Nexperia BAT54S,215 | C47546 | ext | 238920 | 33 | A B IN | onsemi BAT54SLT1G (DK BAT54SLT1GOSCT-ND) |
| Texas Instruments TLV9004IPWR (was LM2902PWR C46864) | C2058050 | ext | LCSC 2190 (2026-11-20) | 6 | A B | Microchip MCP6004T-E/ST |
| KEMET C0805C473K5RAC7800 | C3879816 | ext | 7957 | 16 | A B | KEMET C0805C473K5RACTU (same part, other reel code; DK 399-C0805C473K5RACTUCT-ND) |
| YAGEO CC0805GRNPO0BN221 | C576920 | ext | 3366 | 16 | A B | - |
| UNI-ROYAL 0805W8F1201T5E | C17379 | basic | 1366298 | 16 | A B | YAGEO RC0805FR-071K2L (DK 311-1.20KCRCT-ND) |
| FOJAN FRC1206J470 TS | C2907508 | ext | 648789 | 16 | A B | - |
| Infineon BTS70082EPAXUMA1 | C2150060 | ext | 0 **short** | 8 | A | Infineon BTS7008-2EPA (same chip, LCSC C534830) |
| JST BM12B-GHS-TBT | C20089173 | ext | 0 **short** | 1 | B | - |
| Wurth Elektronik 74650074R | - | - | - **not listed** | 8 | B | - |
| Vishay BYG23M-E3/TR | C141573 | ext | 18867 | 8 | B | - |
| Infineon BTS70041EPPXUMA1 | C534825 | ext | 20949 | 4 | B | - |
| Infineon BTS700121ESPXUMA1 | C3232444 | ext | 23 | 4 | B | Infineon BTS700121ESPXUMA2 (DK 448-BTS700121ESPXUMA2CT-ND) |
| FH (Guangdong Fenghua) 0603B103K500NT | C57112 | basic | 5007514 | 27 | IN | YAGEO CC0603KRX7R9BB103 (DK 311-1085-1-ND) |
| Molex 0430451200 | C277636 | ext | 1279 | 3 | IN | - |
| UNI-ROYAL 0603WAF4701T5E | C23162 | basic | 14571731 | 24 | IN | YAGEO RC0603FR-074K7L (DK 311-4.70KHRCT-ND) |
| UNI-ROYAL 0603WAF1002T5E | C25804 | basic | 41630755 | 51 | IN | YAGEO RC0603FR-0710KL (DK 311-10.0KHRCT-ND) |
| UNI-ROYAL 0603WAF2002T5E | C4184 | basic | 4459627 | 3 | IN | YAGEO RC0603FR-0720KL (DK 311-20.0KHRCT-ND) |
| Omron A6S-8104-H | C231310 | ext | 20 | 6 | IN | - |

### 13.3 TVS D2 (A and B): SMCJ20CA -> 5.0SMDJ24CA (default, DECISIONS 2026-11-16 rule: research, decide with sources)

D2 sits straight across the +12 V feed (terminal J1, every PROFET VS pin) to GND on both main boards. The open question was: the old part clamps at 32-33 V and the switches' maximum is 28 V. Answer: 28 V is the wrong limit, and the old part has a worse problem.

Limits (Infineon BTS7008-2EPA, BTS7004-1EPP, BTS70012-1ESP data sheets, Table 3 and the suggested-components table):
- VS 28 V is the supply-voltage maximum (P_4.1.0.1). For transients the rating is VBAT(LD) = 35 V, "suppressed load dump acc. to ISO 16750-2 (2010), Ri = 2 ohm" (P_4.1.0.3), the same on all three switches. Outputs keep working up to VBAT(LD) (BTS7008-2EPA 8.4.2).
- Infineon's own suggested circuit uses "DZ2: 33 V TVS diode" on VS (protection at overvoltage and at loss of battery with an inductive load).
- VBAT(SC) 0-24 V (short-circuit protection proven up to 24 V); -VBAT(REV) 16 V for 2 min.

Car side (12 V system; Analog Devices articles on ISO 16750-2 / ISO 7637-2, Nexperia IAN50007):
- Jump start: 24 V for 60 s. Suppressed load dump (Test B, central suppression assumed): clamped at 35 V, Ri 0.5-4 ohm, td 40-400 ms. A TVS with its breakdown below 35 V "may be forced to absorb the alternator's energy" (ADI).
- ISO 7637-2 pulse 2a: +112 V, Ri 2 ohm, 50 us; pulse 1: -150 V, Ri 10 ohm, 2 ms.

The two parts (maker data; estimate: clamp = VBR max + Rd x I, Rd from the data-sheet VC / IPP point; worst current from VBR min; pulse power for long pulses scaled as 1 / sqrt(t) from the 10/1000 us rating, the usual TVS curve shape; rectangular pulse, so on the safe side):

| Case | SMCJ20CA (BORN, LCSC C152086) | 5.0SMDJ24CA (DOWO C284111 = Littelfuse 5.0SMDJ24CA) |
|---|---|---|
| Ratings | VRWM 20 V, VBR 22.2-24.5 V, VC 32.4 V at 46.3 A, 1500 W 10/1000 us (BORN data sheet) | VRWM 24 V, VBR 26.7-29.5 V, IR 5 uA, VC 38.9 V at 129 A, 5000 W 10/1000 us, DO-214AB (Littelfuse 5.0SMDJ data sheet v.4; DOWO listing at JLCPCB: same values) |
| Jump start 24 V, 60 s | 24 V is inside its breakdown band: it conducts the battery's current for a minute: **fails** (a TVS usually fails short, here across the feed) | below VRWM: leakage only (5 uA): **pass** |
| Suppressed load dump 35 V, Ri 2 ohm, 400 ms | about 5.9 A at 23 V = 137 W against about 75 W allowed at 400 ms: **fails** | about 4.0 A at 27 V = 108 W against about 250 W: **pass** (Ri 1 ohm: 212 W, pass). At Ri 0.5 ohm and 400 ms (about 400 W) it would not survive |
| Pulse 2a (+112 V, 2 ohm) | about 46 A, clamp about 32.5 V | about 46 A, clamp about 32.9 V (35 V reached only at about 75 A) |
| Against the switches' 35 V | below 35 V | below 35 V |

Decision: D2 = 5.0SMDJ24CA on A and B (same DO-214AB footprint, no copper change). MPN = DOWO 5.0SMDJ24CA (LCSC C284111, JLCPCB extended, 4,224 in stock; the LCSC column is the fitted part, C6c); approved alternate Littelfuse 5.0SMDJ24CA (Digi-Key F5634CT-ND). Rest of the +12 V rail at up to 35 V: TSR 1-2450 input 6.5-36 V (LCSC listing), C3 35 V, 47 nF / 100 nF 50 V: all within rating. Unchanged and not covered by the switch data sheets either way: pulse 1 drives VS to about -30 V (old part about -26 V) for about 2 ms against the -16 V / 2 min reverse rating.

Sources: Infineon BTS7008-2EPA / BTS7004-1EPP / BTS70012-1ESP data sheets (links in section 12); Littelfuse 5.0SMDJ data sheet (https://littelfuse.com/~/media/electronics/datasheets/tvs_diodes/littelfuse_tvs_diode_5_0smdj_datasheet.pdf.pdf); BORN SMCJ data sheet (LCSC C152086); JLCPCB part page C284111; Digi-Key 5.0SMDJ24CA (https://www.digikey.com/en/products/detail/littelfuse-inc/5-0SMDJ24CA/3307005); Analog Devices "Low quiescent current surge stopper ... ISO 7637-2 and ISO 16750-2" (https://www.analog.com/en/resources/technical-articles/low-quiescent-current-surge-stopper-robust-automotive-supply-protection.html) and "LTspice: models of ISO 7637-2 & ISO 16750-2 transients" (https://www.analog.com/en/resources/technical-articles/ltspice-models-of-iso-7637-2-iso-16750-2-transients.html); Nexperia IAN50007 (https://www.nexperia.com/applications/interactive-app-notes/IAN50007_Conducted_battery_line_transients).

## 14. IS buffer, IS clamp zener and input TVS (2026-11-20, branch `fix/hw-sense-tvs-feed`, job hwfix)

ADR-2026-11-20-is-buffer, ADR-2026-11-20-is-fullscale (PR #112) follow-up, ADR-2026-11-20-tvs-loaddump. Proof:
`tools/verify_spice.py` (rows in `docs/pcb-verification.md`).

### 14.1 Sense buffer U7 / U12 (A), U7 / U22 (B): LM2902PWR -> TI TLV9004IPWR (fitted)

| | LM2902PWR (before) | TLV9004IPWR (fitted) |
|---|---|---|
| Input range on 3.3 V | 0 to VCC-1.5 V (25 C) / VCC-2 V (-40..125 C) (TI SLOS066AE 6.8) | (V-)-0.1 to (V+)+0.1 V, rail-to-rail in and out, swing 20 mV max from the rails at RL 10 k (TI SBOS833R 7.5) |
| TA | -40 to 125 C | -40 to 125 C (SBOS833R 7.3) |
| Pinout, TSSOP-14 (PW) | 1 OUT1, 2 IN1-, 3 IN1+, 4 V+, 5 IN2+, 6 IN2-, 7 OUT2, 8 OUT3, 9 IN3-, 10 IN3+, 11 V-, 12 IN4+, 13 IN4-, 14 OUT4 (SLOS066AE Table 5-1) | identical, pin for pin (SBOS833R Table 6-5) |
| Input overdrive | - | diode-clamped to the rails, <= 10 mA (SBOS833R 7.1 note 2): 4.7 k in front keeps it <= 0.34 mA at IIS(SAT) 15 mA |
| Order | LCSC C46864 | LCSC C2058050 (TI, 2,190 in stock 2026-11-20, 0.25 USD at 5), Digi-Key 296-51827-1-ND (product page 2026-11-20); approved alternate Microchip MCP6004T-E/ST (RRIO, VDD-25 mV swing, E grade -40 to 125 C, same TSSOP-14 pinout: Microchip DS20001733) |

Symbol: stays the generic `Amplifier_Operational:LM324` quad (same pins); KiCad 9 / 10 ship TLV9004 only as `TLV9004xRUCR` (X2QFN numbering). Value / MPN / LCSC / Digi-Key / Datasheet / Alternates carry the part.

### 14.2 IS-chain clamp zeners: PDZ3.3B -> Nexperia PDZ5.1B,115 (fitted; D1 battery sense stays PDZ3.3B)

Why: with the rail-to-rail buffer the clamp no longer has to sit at the 3.3 V rail; the TLV9004 input diodes take the overdrive. The 3.3 V zener's knee is soft (PDZ-B series Table 2: rdif <= 1000 Ohm at 0.5 mA, 95 Ohm at 5 mA; IR <= 5 uA at 1 V; SZ -2.4 mV/K): in the softest data-sheet corner a PROFET fault (IIS(FAULT) 4.4 mA min) reads only 2.31 V at 125 C, under the firmware fault level 2.475 V (PROFET_IS_FULL_SCALE 3071, ADR-2026-11-20-is-fullscale). PDZ5.1B (VZ 4.96-5.20 V at 5 mA, rdif <= 60 / 250 Ohm at 5 / 0.5 mA, IR <= 2 uA at 1.5 V, SZ +0.3 mV/K): a fault reads 3.28 V (4070 counts, the op-amp rail) at -40 / 25 / 125 C in both corners (margin +0.805 V), no leakage error at rated current (readings at rating 0.0 %), op-amp input current 0.25-0.34 mA at IIS(SAT) 15 mA. Infineon's own list asks for a 7 V Z-diode at the IS line (BTS7008-2EPA Table 24, DZ1). Order: LCSC C85392 (Nexperia, 6,230 in stock 2026-11-20), Digi-Key 1727-5155-1-ND (product page 2026-11-20), same SOD-323 footprint.
TLV9004 input pin with PDZ5.1B (d2tvs, 2026-11-20, `verify_spice.py` tlv_input): TI SBOS833R 7.1 (p. 14) allows -10 .. +10 mA into a signal input; note 2: inputs that swing more than 0.5 V beyond the rails must be current-limited to 10 mA. Worst case, IIS(FAULT) max 10 mA and IIS(SAT) max 15 mA, zener at VZ max 5.20 V + rdif 60 Ohm, a low 0.3 V clamp-diode drop, -40 / 25 / 125 C: 0.31-0.44 mA with +3V3 up, 1.01-1.12 mA with +3V3 not yet up (0 V). R2 (4.7k) already limits it 9x below the maximum: no change needed (accuracy unchanged).

### 14.3 Input TVS D2 (A and B): load-dump part SM8S24CAHM3/I, fitted at a new D2 spot since 2026-11-20 (d2tvs, ADR-2026-11-20-d2-move)

| Part | Package | Suppressed load dump B (35 V, Ri 0.5 / 2 / 4 Ohm, 400 ms) | Pulse 2a (+112 V, 2 Ohm) | Verdict |
|---|---|---|---|---|
| 5.0SMDJ24CA (fitted until 2026-11-20) | DO-214AB | 12-123 J vs a 10/1000 us rating of about 7 J (no long-pulse rating) | 33.5-34.9 V | FAIL |
| Vishay SM8S24CA (HM3: AEC-Q101), bidirectional (fitted since 2026-11-20) | DO-218AB / AC | 31-327 W for 400 ms vs 622 W allowed (Vishay doc 98647 fig. 1: 6.6 kW 1 ms, 5.2 kW 10 ms, 1.9 kW 100 ms, extrapolated with the 10-100 ms slope to 1.04 kW at 400 ms; derated linearly to 0 at 175 C from an 85 C start, doc 98229 fig. 3) | 32.4-34.0 V | PASS |
| Littelfuse 5.0SMDJ33CA (Infineon DZ2 "33 V TVS") | DO-214AB | stays off (VBR 36.7 V min): 0.01 J | 44.0-46.0 V (> 35 V VBAT(LD); PROFET GND current through RGND 47R 0.23-0.28 A) | FAIL (clamp) |

Independent evidence for the DO-218AB class: Panjit's AEC-Q101 SM8H24CAS-AU (same VBR 26.7-29.5 V, 6.6 kW) is tested to ISO 16750-2 test A, the UNsuppressed load dump (Us 101 V, Ri 0.5 Ohm, td 400 ms, 10 pulses at 1 min), clamping at 33.2 V max (Panjit "Automotive-Grade Bidirectional Load Dump TVS" flyer, Rev 03, 2025-05). No DO-214AB part survives 100+ J for 400 ms. DOWO's SM8S24CA (LCSC C557518) is rated only 3.65 kW at 10/10000 us (its LCSC data sheet) against Vishay's 5.2 kW, so it is not an approved equal.
Fitted part: Vishay SM8S24CAHM3/I (LCSC C20036943: 2 in stock 2026-11-20, so assembler global sourcing or an alternate; Digi-Key 112-SM8S24CAHM3/ITR-ND, which Digi-Key lists as obsolete for the "/I" code: Vishay's ordering example is the "_A/I" code, so the order may come as SM8S24CAHM3_A/I, same part); approved alternates Bourns SM8S24CA-Q (Digi-Key SM8S24CA-QCT-ND, active, 14,800 in stock 2026-11-20; its "Recommended Footprint" tab 9.0 x 10.0 + lead 2.0 x 2.7, 14.5 overall sits inside our pattern), Panjit SM8H24CAS-AU (DO-218AB, body 9.7-10.3 x 8.7-9.3 x 4.7-5.0 mm = Vishay's; SM8H14CAS-AU series data sheet Rev.00, 2025-05-22).
Footprint (`tools/d2_tvs.py lib`, dingoPDM:D_DO-218AB_Vishay_SM8S): Vishay doc 98229 rev 23-Jan-2026 page 5 "Mounting Pad Layout" (IPC-7351): heat-sink pad 9.80 x 10.70, lead pad 2.15 x 2.60, 3.35 between, 15.30 overall; pad 1 = lead (+12V), pad 2 = tab (GND: the tab is the heat path and sits on the GND planes); tab paste in 2 x 2 windows (78 %); courtyard 16.5 x 11.2. 3D model from the page-5 maximum dimensions (`tools/d2_model.py`, 5.0 mm tall; the maker's CAD is behind the Ultra Librarian login). The old spot (-33.66, 30.59) had 7.6 mm free across, so D2 alone moved (C2 / J1 and every other part stay; `tools/board_semdiff.py`: only D2, its 4 old stub tracks, its new vias and the +12V / GND fills differ from main):
- Board A: (-19.75, 5.25) rot 270, lead pad 16.1 mm from the J1 feed terminal's centre (the hwfix site at (24.9, ...) would have been 56 mm away); +12V on the bottom +12V pour, GND on In1 + top; 12 +12V and 10 GND stitching vias (none on the tab side the J1 feed passes: verify_copper A 42.1 mV / 2.25 W vs main 41.2 mV / 2.22 W).
- Board B: (36.25, -12.25) rot 180, lead towards J1 (66 mm from its centre: the only clean site); +12V on the In2 +12V plane + bottom pour, GND on In1 + top; 10 +12V and 14 GND vias; R68's label turned 90 deg and moved 0.6 mm off the tab (text only).
- Clamp copper: top +12V pour over the lead pad and under the body, top GND pour over the tab (solid connections; the main GND pour uses thermal spokes), 0.8 / 0.4 mm vias, none in a pad. Surge current (verify_spice, below): load dump B Ri 0.5 Ohm 11.2 A for 400 ms, pulse 2a 32 A for 50 us, pulse 1 10 A for 2 ms; one 0.4 mm via fuses at about 11 A for 0.4 s (Onderdonk, 20 um wall), so >= 10 vias per net (A 12 / 10, B 10 / 14) keep each under about 1.1 A.
- SPICE after the move (`verify_spice.py`, a 4 nH J1 -> D2 plane path added): load dump B 31-327 W (12-131 J) vs 622 W allowed PASS; 2a 32.4-34.0 V PASS; 3a / 3b absorbed by the caps PASS; pulse 1 -29.1 / -31.6 V WARN (as before). Same as at the old spot to 0.1 V.
- Enclosure v2c rev B (models folder; revC not published on 2026-11-20), D2 body from our board STEPs: board A 5.83 mm to the heat sink (side), the input deck 20.0 mm above; board B 2.61 mm to the M3 x 8 carrier standoff (side), 3.04 mm under the G10 carrier (insulator), 4.10 mm to an M3 screw. No collision.
- JLCPCB placement for D2 (CPL 270 on A, 180 on B, no table offset; origin = middle of the pattern, pin 1 = lead): `verify_cpl.py` cannot compare it, because C20036943 has no footprint in the EasyEDA library (API 404, 2026-11-20); JLCPCB places such parts from the CPL: check its placement preview at order time (BACKLOG).
Pulse 1 (-150 V, 10 Ohm, 2 ms), every bidirectional part: -29 to -32 V on +12V vs the PROFETs' -16 V 2-minute reverse rating; their GND-VS path breaks down at 16-30 V (-VS(REV), P_6.4.0.9) and the fitted RGND 47 Ohm (Infineon Table 24, already on every switch, with CVSGND 47 nF) then carries up to about 0.3 A for the pulse (IGND abs max 50 mA static). The data sheets give no pulse rating; a unidirectional TVS (forward clamp about -1 V) would short a reverse-connected battery, so no sourced standard fix keeps reverse-battery survival: WARN kept, noted in BACKLOG.

Sources: TI SBOS833R (TLV900x, Nov 2021); TI SLOS066AE; Microchip DS20001733L (MCP6001/2/4); Nexperia PDZ-B series data sheet (2004-03-22 / NXP); Infineon BTS7008-2EPA Rev 1.20, BTS7004-1EPP, BTS70012-1ESP Rev 1.21 (Tables 3, 24, P_4.1.0.3 / .5 / .9, P_6.4.0.9, P_8.6.0.6 / .7, P_9.6.x); Vishay SM8S10CA thru SM8S85CA doc 98229 (rev 23-Jan-2026), SM8S10AHM3 thru SM8S43AHM3 doc 98647 (rev 16-Jan-2024); Littelfuse 5.0SMDJ data sheet; Panjit load-dump TVS flyer (panjit.com.tw); Panjit SM8H14CAS-AU ~ SM8H48CAS-AU data sheet Rev.00 (2025-05-22, page 5 DO-218AB dimensions / pad layout); Bourns SM8S-Q series data sheet ("Product Dimensions", "Recommended Footprint"); LCSC product pages C2058050, C85392, C557518, C3720850, C2990549, C20036943 (read 2026-11-20); Digi-Key product pages 18869881 (Vishay SM8S24CAHM3/I, listed obsolete) and 9920516 (Bourns SM8S24CA-Q, active, 14,800 in stock), read 2026-11-20.

