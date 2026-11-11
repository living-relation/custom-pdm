# Enclosure layout - first proposal (Job A)

Status: PROPOSAL for Dan to approve or change. Nothing here is decided. Written 2026-11-10 on branch `feat/enclosure` (from main 62d38fc).
Picture: `docs/diagrams/enclosure-layout.svg` (illustration, drawn by `tools/gen_enclosure_layout.py` from the board files; not a source of truth).
2D only. No 3D model and no Fusion thermal study (Dan: heat by hand calc, Elmer later). Fusion was used only to measure vendor STEP files in a scratch document (closed, nothing saved).
Marks: **TBD** = not confirmed, **ASSUMED** = my placement choice, each one is a question in the last section.

## 1. The layout in one paragraph

Three main boards lie flat in one row on one aluminium base plate (the heat sink): B (west), A1, A2 (east). The three input boards sit in a second row under their main boards. Walls: BATT and GND studs on the west wall, X1 and the OUT1-4 studs on the north wall, X2 on the south wall. Two copper bars (BATT, GND) run from the west studs across the boards' own M6 terminals.

| Item | Size from the placed layout | Basis |
|---|---|---|
| Main row | 28 + 111.4 + 10 + 72.4 + 10 + 72.4 + 10 = **314.2 mm** long, 95.3 mm deep | board outlines from the PCB files; 28 / 10 / 10 mm margins are ASSUMED |
| Whole inner plan | **314.2 x 261.3 mm** = 45 + 95.3 + 12 + 64.0 + 45 | 45 mm north and south = X1 / X2 inside part (about 28 mm, TBD for HD34) + wire bend; ASSUMED |
| Inner height | **TBD**, see section 3 | lower bound 30.1 mm (J3 housing), the mated DT plug adds more |

Board outlines (Edge.Cuts rectangle): A 72.39 x 95.25 mm, B 111.39 x 95.25 mm, input board 66.0 x 64.0 mm. Board thickness 1.77 mm (A, B), 1.6 mm (input) from the board setup. Source: `hardware/board-a/DingoPDM.kicad_pcb`, `hardware/board-b-max/dingoPDM-Max.kicad_pcb`, `hardware/input-board/input-board.kicad_pcb`, read with `tools/pcb_info.py` style scripts.

## 2. Board placements and what they carry

Board coordinates are KiCad coordinates (board A and B share one frame; outline starts at x -37.846, y -33.274).

| Board | Placed at (inner coords, mm) | Notable items (from the board file) |
|---|---|---|
| B | (28.0, 45.0) | four BTS70012 U8-U11 at about x +-9, y +-12.6; T1-T4 (REDCUBE 74650074) around the centre; four BTS7004 U23-U26 in the right column (x 54.9); T5-T8 at the east edge (x 68.4); M6 terminals J1 (+12 V) and J3 (GND) at the west edge; J7 JST GH at x 38.3, y 44.6 |
| A1 | (149.4, 45.0) | four BTS7008-2EPA U8, U10, U11, U13 (two pairs, y +12.7 and -12.6); J3 DT15-12PA at the board centre; M6 J1 (+12 V), J2 (GND) at the west edge; J6 JST GH at the west edge |
| A2 | (231.8, 45.0) | same as A1 |
| input #3 / #1 / #2 | (31.0 / 152.4 / 234.8, 152.2) | 66 x 64 mm, J1 JST GH (east edge) and J2 Micro-Fit (west edge) |

Each main board has its own +12 V and GND M6 terminal (Wuerth 7461084) on the west edge, 54.4 mm apart (y +27.2 and -27.2 in board coordinates). That fixes the feed topology in section 5.
USB-C (service port), BOOT switch and status LEDs are on the south edge of every main board: keep a service opening or a removable lid over that edge.

## 3. Heights (what limits the lid)

| Part | Height above the board top | Source |
|---|---|---|
| J3 DT15-12PA housing (A boards) | **30.12 mm** mating face above the feet plane (STEP); DigiKey lists insulation height 30.10 mm; TE web page says "profile height from PCB" 35.26 mm. Conflict: use 35.3 mm until the TE drawing is read | STEP `c-dt15-12pa-e-3d.stp` measured in Fusion; [DigiKey DT15-12PA](https://www.digikey.ca/en/products/detail/te-connectivity-deutsch-connectors/DT15-12PA/6566591); [TE DT15-12PA](https://www.te.com/en/product-DT15-12PA.html) (drawing ENG_CD_DT15-12PX_D2.pdf: download refused with 403, TBD) |
| DT06-12SA plug on J3 (wires to X1) | **TBD** insertion depth. TE lists the plug as 40.56 mm tall, 30.94 x 18.19 mm. Upper bound if it all sat above the header: 30.1 + 40.56 = 70.7 mm, plus wire bend | [TE DT06-12SA](https://www.te.com/en/product-DT06-12SA.html) |
| M6 terminal 7461084 (all main boards) | 13.5 mm (10 x 10 mm base, M6, thread length 9 mm, 160 A) | [Wuerth 7461084](https://www.we-online.com/catalog/en/article/7461084); STEP agrees |
| REDCUBE 74650074 (T1-T8, M4) | about 3 mm (STEP 3.2 mm), plus ring lug and screw head: TBD | [Wuerth 74650074](https://www.we-online.com/catalog/en/article/74650074) |
| Everything else on the boards (USB-C, regulators U1, U14, U15, caps) | TBD (U14 / U15 models are .wrl, not measured) | |

The DT15 housing is 59.2 x 35.3 mm in plan (STEP) about J3's origin, so in plan it covers all four BTS7008 chips (their pads span y 9.2-16.2 and -16.2 to -9.2). It works in the stock dingoPDM because the housing seats on four 5.6 x 5.6 mm feet (x +-14.7..20.3, y +-7.9..13.5) and its underside is 3.96 mm above the board. The feet clear the chips (U8 courtyard ends at x 14.0, the foot starts at 14.7).

## 4. Heat path

Rules from Dan: switches on top, bare back side is +12 V so an insulating gap pad goes between board and sink, pedestals on board A, bottom mask openings on board B, hand calc now, "more than enough cooling".

### 4.1 What the boards actually have (checked in the PCB files)
- Bottom solder-mask windows are `B.Mask` zones, one per switch, the size of the exposed pad:
  - Board A: **5** windows, 3.96 x 2.64 mm. Four are under U8, U10, U11, U13. **The fifth, at x -12.9..-8.94, y 11.38..14.02, is a leftover from the removed U9 (there is no chip there).** Net under it not checked: TBD.
  - Board B: **8** windows. Four BTS70012: 6.38 x 2.77 mm at x -12.2..-5.8 and 5.8..12.3, y +-(11.2..14.1). Four BTS7004: 2.64 x 3.96 mm at x 53.62..56.26 (y -27.4..-23.5, -4.1..-0.2, 19.2..23.1, 42.5..46.4). So the board B openings exist and match the brief.
- Bottom copper around them is output / +12 V pour under mask; only the windows are bare.
- J3 pin tails: TE contact post 3.10 mm (STEP: 3.10 below the feet plane) minus board 1.77 mm = **about 1.33 mm** sticking out of the bottom. Pin pads span x -12.4..12.4, y -5.9..5.9 in board A coordinates.

### 4.2 Proposed sink shape (placeholders, TBD by Dan's answers)
Board rests on pedestals only, the rest of the sink is recessed. Pedestal = window hull + 1.5 mm (ASSUMED margin). Sizes are from the placed layout:

| Pedestal | Covers | Size (mm) | Area |
|---|---|---|---|
| A south | U11 + U8 windows | 18.0 x 5.6 | 102 mm2 |
| A north | U13 + U10 windows | 15.9 x 5.7 | 91 mm2 |
| A pocket | J3 pin tails + margin 1 mm, between the two pedestals | 26.8 x 13.8 (x -13.4..13.4, y -6.9..6.9) | - |
| B south pair | two BTS70012 (U8, U9) | 27.5 x 5.9 | 162 mm2 |
| B north pair | two BTS70012 (U10, U11) | 27.4 x 5.8 | 160 mm2 |
| B rail | four BTS7004, one rail | 5.6 x 76.8 | 433 mm2 |

Pocket depth: tail 1.33 mm + clearance, against pedestal height + pad thickness. Pedestal height and pad thickness are TBD (pad product not chosen). The old plan "centre standoff" (Dan, 2026-11-08) sits at about (5.6, 0.05): between the pin rows, inside the DT15 housing outline, and there is no hole in the board there. How it presses the board down is open (question G). The four M3 holes of board A are at (-33.0, 21.6), (-21.1, -21.6), (26.7, -21.6), (26.7, 21.6).

### 4.3 Heat budget by hand
Worst case = every channel at its rated current, R(on) at 150 C (datasheet max). Typical = R(on) at 25 C. Current ratings from Dan's decisions (7.5 A, 31 A, 15 A).

| Switch | R(on) typ 25 C / max 150 C | Current | W per chip (max R) | Chips | Board W (max R) / (typ) |
|---|---|---|---|---|---|
| BTS7008-2EPA (2 ch each) | 9 / 16 mOhm per channel | 7.5 A x 2 | 1.80 | 4 | A: 7.2 / 4.05 |
| BTS70012-1ESP | 1.4 / 2.47 mOhm | 31 A | 2.37 | 4 | B: 9.49 / 5.38 |
| BTS7004-1EPP | 4.4 / 8 mOhm | 15 A | 1.80 | 4 | B: 7.2 / 3.96 |

- Board B total 16.7 W (typ 9.3 W). **System total 31.1 W worst case** (A1 + A2 + B), 17.4 W typical. This matches the old "about 25 W" call.
- All channels at rating would draw 16 x 7.5 + 4 x 31 + 4 x 15 = 304 A, twice the 150 A feed. The 31 W figure is therefore an upper bound.
- Junction to case (datasheet max RthJC): BTS7008 1.4 K/W x 1.8 W = 2.5 K, BTS70012 0.7 x 2.37 = 1.7 K, BTS7004 2.4 x 1.8 = 4.3 K. Small. The pad, the vias and the sink decide.
- Gap pad, formula R = t / (k x A). **ILLUSTRATION only (k = 3 W/mK and t = 1 mm assumed, pad product TBD):** A south pedestal 3.3 K/W x 3.6 W = 11.8 K; A north 3.7 x 3.6 = 13.2 K; B pair 2.1 x 4.75 = 9.9 K; B rail 0.77 x 7.2 = 5.5 K.
- Sink to air, 31.1 W at 60 C cabin air (illustration): sink at 85 C needs 0.80 K/W, 95 C needs 1.13 K/W, 105 C needs 1.45 K/W.
- One worked chain, worst chip (BTS70012 pair): sink 95 C + pad 9.9 K + RthJC 1.7 K = 107 C before the PCB (vias, 1.77 mm board), TBD. That leaves about 43 K to the 150 C limit for the PCB path. To be checked in Elmer.

Sources: Infineon datasheets, [BTS7008-2EPA](https://www.infineon.com/assets/row/public/documents/10/49/infineon-bts7008-2epa-datasheet-cn.pdf) (RDS(ON)_25 9 mOhm typ, RDS(ON)_150 16 mOhm max, IL(NOM) 7.5 A at 85 C, RthJC 0.8 typ / 1.4 max K/W), [BTS70012-1ESP](https://www.infineon.com/assets/row/public/documents/10/49/infineon-bts70012-1esp-datasheet-cn.pdf) (1.4 typ / 2.47 max mOhm, 31.3 A, RthJC 0.4 / 0.7), [BTS7004-1EPP](https://datasheet.chipsmall.com/BTS70041EPPXUMA1/370225.pdf) (4.4 typ / 8 max mOhm, 15 A, RthJC 1.4 / 2.4; chipsmall copy of the Infineon datasheet).

## 5. Wiring runs (plan distances only, no height; Manhattan)

| Run | From | To | Wires | Plan length |
|---|---|---|---|---|
| A1 outputs, A2 outputs | J3 (DT06-12SA plug) | X1 size 16 cavities | 8 + 8, 16 AWG | 90 mm (A1), 93 mm (A2) |
| Board B OUT5-8 | T5-T8 | X1 size 12 cavities B, D, E, G | 4 x 14 AWG | 119, 143, 166, 189 mm |
| Board B OUT1-4 | T1-T4 | OUT stud, one wire each | 4, wire size TBD (31 A) | 90, 70, 98, 76 mm (stud order left to right: OUT2, OUT4, OUT1, OUT3 so wires do not cross) |
| Inputs | input board J2 | X2 | 8 + 1 analog + grounds per board | short, south wall |
| Input board J1 | board J6 (A) / J7 (B) | JST GH cable | 12-way | about 100 mm, TBD |
| CAN | board J3 pins 1-2 (A), J6 (B) | X2 cavities 2, 3 | twisted pair, daisy chain | TBD |

Wire sizes for X1 and X2 are from `docs/box-connectors.md`. The X1 cavity map and contact ratings are in that file.

### Feed split (150 A)
Each board has its own M6 terminal pair on its west edge, all at the same y. So two straight bars along x reach all three boards: BATT bar at y 105.5, GND bar at y 51.1 (inner coords), about 231 mm and 225 mm long from the stud's inner end to the A2 terminal. Order along the bar: stud, B, A1, A2. B can draw 4 x 31 + 4 x 15 = 184 A at rating (limited by the 150 A feed), A1 and A2 at most 60 A each, so the first segment carries up to 150 A and the last 60 A. The M6 terminals are rated 160 A each (Wuerth), so B's terminal is the closest to its limit. Bar cross-section: TBD (hand calc with the allowed temperature rise once Dan picks bars).
Stud sizes (BATT 150 A, GND, OUT1-4 at 31 A) and boot diameter: TBD (drawn as 20 mm).

## 6. X1 / X2 on the wall
- X1 HD34-24-21SN and X2 HDP24-24-47SE-L017: flange 50.8 mm round with a flat to 47.6 mm; receptacle overall length 41.86 mm ([TE catalog p.147, in `te-drawings\rs_te_catalog.pdf`]; [TE HD34-24-21SN](https://www.te.com/en/product-HD34-24-21SN.html): height 41.8, length 50.8, width 47.6). HDP24 drawing (-L015 mod; L017 not read): 26.16 mm in front of the flange, flange 2.54 mm, about 30 mm behind it with the threaded adapter.
- Panel cut-out and torque: TE application spec 0425-021-0000 (not read): TBD. HD34 customer drawing HD34-24-XXP/SX (not read): TBD.
- Plug side adds 38.63 mm length (catalog) outside the box.

## 7. Questions for Dan (assumptions that are not decided)

**A. Where does it mount and how big may it be?** (a) flat, lid up, shelf or floor, space at least about 320 x 270 mm plus height; (b) on its side on a bulkhead; (c) smaller limit: tell me the limit and I compact it (inputs stacked, tighter margins). Recommendation: (a) for now, and tell me the size limit.

**B. Material and lid.** (a) all aluminium tray plus gasketed lid; (b) MJF print cover on an aluminium base plate that is the heat sink, gasket between; (c) MJF only with an internal plate. Recommendation: (b), because the sink and the sealing are separate jobs.

**C. Fan.** (a) passive only; (b) passive with mounting holes and room for a small fan (not fitted); (c) fan fitted. Recommendation: (b), matching "more than enough cooling" without noise by default.

**D. 150 A feed split.** (a) two copper bars across the boards' M6 terminals (as drawn); (b) one stud, three cables with ring lugs per board, same for GND; (c) a distribution block. Recommendation: (a).

**E. Input boards.** (a) flat second row as drawn (adds 64 + 12 mm to the depth); (b) stacked over the main boards on standoffs: over board A only 44 mm south of the DT15 housing is free, the input board is 64 mm deep, so it would overhang the edge by about 20 mm; over board B it fits; (c) a deck above everything. Recommendation: (a) first, revisit if size limit (A) is tight.

**F. J3 and the DT plug.** The stock vertical DT15-12PA is 30.1-35.3 mm tall and its plug adds more; this is what sets the lid height. (a) keep it (lid height about 80 mm or more, TBD); (b) change board A to a right-angle DT header so the plug lies flat toward the wall (board change, not done here). Recommendation: (a) until the plug drawing gives the real height; tell me if height is limited.

**G. Centre standoff / pressing board A onto the pedestals.** No hole exists at the centre and the point is inside the DT15 housing. (a) a post from the lid or a cross bar presses on the housing top; (b) rely on the four M3 holes and size pedestal plus pad compression, check later; (c) add a mounting hole (board change). Recommendation: (b), then check in Elmer.

**H. Leftover mask window on board A (old U9 spot).** (a) remove it in the board A build; (b) leave it, the pad covers it. Recommendation: (a) next time board A is rebuilt (not touched here).

## 8. Not done
3D layout; stacking check; gap pad and sink product choice; Elmer; the TE drawings for DT15-12PA, DT06-12SA, HD34-24 and HDP24 -L017 (only product pages, STEP and catalog data used).
