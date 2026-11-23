# DRC / ERC review - board A, board B, input board

Job drcclean, 2026-11-23, from main 19479b5. Question (Dan): are the boards verified error-free?
Tool: `kicad-cli` 10.0.7 (the schematics are KiCad 10 format; kicad-cli 9 cannot load them), run as
`pcb drc --schematic-parity --refill-zones --all-track-errors --severity-all` and `sch erc --severity-all`, JSON reports.
Every item is now fixed or waived by `tools/drc_erc_waivers.py` (last stage of `build_board_a.ps1`,
`build_board_b.ps1`, `build_input_board.ps1`) with its reason written next to it; the stage fails the build on any new item.

**Verdict: no real defect blocks the order. DRC 0, unconnected 0, parity 0, ERC errors 0 on all three boards. One small real
item was open (board A: 3 unused op-amp channels float, stock design): CLOSED 2026-11-23 by job tlvunused (below); board A
ERC is now 0 errors, 0 warnings. Fab outputs (Gerbers, drills, BOM, CPL, JLC check) were unchanged by drcclean; tlvunused
changed board A's copper / drill files only (see "Closed").**

## Counts (active = not excluded; excluded items stay visible with `--severity-exclusions` and carry their reason)

| Board | Check | Before (main 19479b5) | After |
|---|---|---|---|
| A | DRC | 225: 165 active (28 clearance, 4 courtyard, 4 silk, 129 library) + 60 stock exclusions without a reason | 0 active, 22 excluded with reasons |
| A | unconnected / parity | 0 / 4 | 0 / 0 |
| A | ERC | 646: 29 errors, 617 warnings | 0 errors; 4 warnings OPEN (real, below); 336 excluded. tlvunused 2026-11-23: 0 errors, 0 warnings, 336 excluded |
| B | DRC | 418 active: 211 errors, 207 warnings | 0 active, 35 excluded |
| B | unconnected / parity | 0 / 4 | 0 / 0 |
| B | ERC | 806: 80 errors, 726 warnings | 0 errors, 0 warnings, 419 excluded |
| IN | DRC / parity / ERC | 50 / 0 / 100 warnings (library only) | 0 / 0 / 0 |

Library-link warnings (A 129 + 306, B 199 + 387, IN 50 + 100) are switched off (group 1), not counted in "after".

## Groups: what each is and why it is safe

| # | Group (KiCad rule key) | Boards, count | Kind | Why it is safe / what was done |
|---|---|---|---|---|
| 1 | `lib_footprint_issues`, `lib_symbol_issues`, `footprint_link_issues` (warning): "configuration does not include library X" | A, B, IN | environment | DansPC's KiCad 9 / 10 have no global library tables. The board file holds a full copy of every footprint, the schematic of every symbol; these checks only compare with libraries. Set to `ignore` in the 3 `.kicad_pro` (stock already ignores `lib_footprint_mismatch`). |
| 2 | `endpoint_off_grid` (warning) | A 306, B 339 | cosmetic | Wire ends / pins off the 1.27 mm grid (stock sheets 312 / 324 of them). Connectivity is proven separately: 0 dangling-wire / unconnected-pin errors, parity 0, `check_board_b.py`. Excluded. |
| 3 | `pin_to_pin` Output-Output, PROFET OUT pins | A 16, B 64 | false alarm | Pins of ONE output of the same PROFET joined, as the data sheets require (BTS7008-2EPA: OUT0 with OUT0, OUT1 with OUT1 only - the waiver matches only same-name pins; BTS70012-1ESP / BTS7004-1EPP are single-channel). The symbols type the pins Output. Excluded. |
| 4 | `pin_to_pin` Power output, U2 pin 2 / pin 4 | A, B 1 each | false alarm | TLV1117LV SOT-223 tab is the same VOUT. Excluded. |
| 5 | `pin_to_pin` Power output on +5VP | A 2, B 2 | false alarm | Three 5 V module footprints on one net; only the LMZM23601V5 (A U21, B U27) is fitted; U1 / U14 (A), U1 / U12 (B) are DNP. The tool stops if they ever stop being DNP. Excluded. |
| 6 | `power_pin_not_driven` | A 9, B 13 | false alarm | Rails fed through passive parts: +12V / GND from the terminals, +12P via the reverse-battery path, +5V via the OR diodes, VDDA via ferrite FB1, PROFET GND pins via their RGND resistor. No PWR_FLAG symbols. Excluded. |
| 7 | `pin_not_driven` J4 SWO + `isolated_pin_label` SWO_UNUSED | A 1 + 1 | intentional | Debug header SWO pin left unused on purpose (SWD needs SWDIO / SWCLK). Excluded. |
| 8 | `clearance`, `hole_clearance`, `annular_width`: USB-C J5 (A) / J2 (B) | A 56 clearance + 20 ring, B 56 hole clearance + 20 ring | maker land pattern | GCT USB4085 pattern: 0.15 mm pad gap and ring at 0.85 mm pitch. JLCPCB limits pass (`gen_fab_jlcpcb.py` JLC-limit DRC: no violations). `.kicad_dru` rule sets the pattern's own limits for pairs inside the connector only. |
| 9 | `track_width` (101) + `clearance` 0.2 vs 0.2032 mm (5), B | B 106 | rule setting | Stock dingoPDM-Max rule file asks 8 mil; stock and our routing use 0.2 mm; JLCPCB 4-layer limit 0.09 mm. Rule: 0.2 mm design minimum (zones keep 8 mil, so a refill gives the same copper: JLC check "zone change 0.000 %"). |
| 10 | `clearance` U4 pins 62 / 64 to the GND track from VSS pin 63 | B 4 | stock layout | LQFP 0.5 mm pitch fan-out, 0.11-0.17 mm, same in stock; JLCPCB min 0.09 mm. Rule: 0.1 mm for that case only. |
| 11 | `courtyards_overlap` | A 7, B 13 | no clash | DNP OKI-78SR footprint (A U14 / B U12) under the fitted 5 V module + caps; J1 / H1, JP1 / U2, C4 / U14 stock; B: T1-T4 terminals vs U8-U11 and T1 / T3, T2 / T4 (courtyard margins only, bodies 2.3 mm apart, docs/pcb-verification.md). DRC copper clearance is clean for every pair. Rule with `(severity exclusion)`. |
| 12 | `starved_thermal` | A 6, B 10 | OK | 1 of 2 spokes on small GND pads (passives, U3, U4 VSS): still joined to the pour, mA currents, same as stock. Excluded. |
| 13 | `silk_over_copper`, `silk_edge_clearance`, `silk_overlap` (USB-C silk at the edge, reported twice) | A 4 + 2 + 2, B 5 + 2 + 2 | cosmetic | Silk over pad openings (Y1, SW1, R38 label) and the USB-C outline at the board edge: the fab clips silk there. Rules with `(severity exclusion)`. |
| 14 | `text_height` / `text_thickness` SW1 'BOOT' | B 1 + 1 | cosmetic | 1.0 / 0.15 mm vs the stock minimum 1.016 / 0.1524 mm; prints fine at JLCPCB. Rule with `(severity exclusion)`. |
| 15 | `footprint_type_mismatch` U1 | A, B 1 each | false alarm | DNP VXO7805 alternate footprint marked SMD with through-hole pads (stock). Excluded. |

## The 4 parity items on A and B (fixed)

All four were `footprint_symbol_field_mismatch`: field 'Datasheet' is '~' on the footprint and '' in the symbol, on
C41 / C42 / JP1 / SW1 (A) and C39 / C40 / JP1 / SW1 (B). Both mean "no data sheet"; stock dingoPDM / dingoPDM-Max had
the same 4 (plus 3 test points and a D2 LCSC field, removed earlier). Fixed in the schematic (field '~'), so the PCB is
untouched. Parity now 0 on both boards.

## Fixes made (no footprint, pad, track, zone, net or terminal change; the `.kicad_pcb` files are not written)

- Schematic: the 4 Datasheet fields per board (above).
- Board B schematic: 66 wire / junction / label / text / no-connect UUIDs and the pin UUIDs in `BTS7004_1EPP.kicad_sch`
  duplicated the stock `BTS700n_1EPP.kicad_sch` (`tools/sch_board_b.py` copies that sheet). KiCad replaces duplicates with
  random IDs on every load, so markers on them were never stable. Renewed as uuid5(file, old) (stable across runs).
  The 18 shared symbol UUIDs stay: the PCB footprint paths use them (sheet paths differ, parity 0). Board A had the same
  for 12 symbol pin UUIDs in `MedCurrentDrivers.kicad_sch`, renewed the same way.
  Netlists of A and B (kicad-cli 10, all nets and nodes, values, footprints) are identical to main.
- `.kicad_dru` (A, B): rules for groups 8-11, 13, 14, each with its reason; `.kicad_pro` (A, B, IN): group 1 severities,
  exclusions with comments for groups 2-7, 12, 15 (A's 60 stock exclusions without reasons are replaced).
- Re-run after the fixes: kicad-cli DRC / ERC (counts above), `gen_fab_jlcpcb.py` (JLC-limit DRC 0 types, co-located holes 0,
  zone change 0.000 % on all three; Gerbers, drills, BOM, CPL and `jlcpcb-drc.txt` identical to main),
  `copper_order.py --check` PASS, `verify_layout.py` PASS, `verify_mcu.py` 18 PASS / 2 WARN / 0 FAIL, `verify_dfm.py`
  7 PASS / 7 WARN / 0 FAIL, `verify_cpl.py` PASS (all as before), `check_board_b.py` ALL OK on the new netlist,
  `drc_erc_waivers.py --check` exit 0 on A, B, IN (a second run changes nothing).
  Not re-run: `verify_copper.py`, `verify_si.py`, `thermal_board_b.py`, `verify_spice.py`: they read only copper or
  circuit values, which did not change (the `.kicad_pcb` files are byte-identical to main).

## Closed 2026-11-23 (job tlvunused): board A unused TLV9004 channels

Coordinator default (technical, 2026-11-23): each unused channel is a voltage follower, OUT to IN-, IN+ to GND.
Sources: TI SBOA204A "How to Properly Configure Unused Operational Amplifiers" (follower with the non-inverting input
on a voltage inside the common-mode and output ranges; favours rail-to-rail parts; for single supply it prefers a
mid-supply divider, which would be 2 new parts per channel) and TI SBOS833R 7.5 (TLV9004 input common-mode
(V-) - 0.1 V .. (V+) + 0.1 V: GND is inside it; rail-to-rail output). With IN+ at GND the output rests at the GND rail,
the same state every used IS follower is in while its PROFET is off; stock dingoPDM already wires U7 channel D this way
(pin 12 on GND, pins 13 / 14 joined).

- Generator: `tools/tlv_unused.py` (stage of `build_board_a.ps1`). Schematic: U7 unit 1 (HighCurrentDrivers),
  U12 units 1 / 2 (MedCurrentDrivers) placed with wires OUT -> IN- and IN+ -> GND symbol (stable uuid5 IDs); the
  stage runs after the board-a.net export, so every earlier PCB stage is unchanged. PCB: pads get the netlist nets
  (new Net-(U7A--), Net-(U12A--), Net-(U12B--); U7.3, U12.3, U12.5 on GND), one 0.65 mm top track per OUT / IN- pair,
  a 0.8 / 0.4 mm GND via per IN+ on a short top track (U7.3 -> (30.974, 56.777), U12.3 -> (31.558, 50.18),
  U12.5 -> (33.858, 48.88)); zones refilled. No footprint, pad, terminal or other net change, nothing moved.
- Proof: netlist diff vs main = exactly those 9 pins (4 nets), parts equal; `board_semdiff` vs main: U7 / U12 pad
  nets, + 7 tracks, + 3 GND vias, B.Cu +3V3 pour -4.0 mm2, F.Cu GND pour +0.6 mm2; a full `build_board_a.ps1`
  rebuild gives the same nets, parts, footprints, tracks and vias as the committed board.
- Checks: kicad-cli DRC 0 active (22 excluded), unconnected 0, parity 0; ERC 0 errors, 0 warnings (336 excluded);
  the OPEN rows in `drc_erc_waivers.py` are removed (a floating unit is a NOT WAIVED item again); `--check` exit 0 on
  A, B, IN. New `verify_layout.py` row "Op-amp inputs": PASS on A (U7 / U12) and B (U7 / U22), FAIL on main's A
  (9 floating pins). `gen_fab_jlcpcb.py`: JLC DRC 0 types, co-located holes 0, zone change 0.000 % on all three.
  `copper_order.py --check` PASS, `verify_dfm.py` 7 PASS / 7 WARN / 0 FAIL (as before), `verify_cpl.py` PASS (BOM / CPL
  unchanged). `verify_spice.py` not run: no ngspice on DansPC or its WSL; its inputs did not change and the netlist
  diff shows the IS chain nets untouched (only the 9 unused pins changed).
- Fab diff (board A only): F_Cu, B_Cu (+3V3 pour around the 3 vias), In1_Cu, In2_Cu (via pads), PTH drill (+3
  holes), `jlcpcb-drc.txt` (zone line label); BOM, CPL, masks, paste, silk, edge, NPTH unchanged. Boards B and IN:
  fab outputs identical to main.

## (was) Open (real, not waived; needs a yes because it changes nets)

- Board A: TLV9004 U7 channel A and U12 channels A and B are not placed in the schematic, so their pins have no net and
  the inputs float (ERC `missing_unit` / `missing_input_pin`, 2 + 2 warnings; stock dingoPDM has the same). A floating
  CMOS op-amp input can make that channel's output swing or oscillate and draw extra supply current; the used channels'
  circuits do not depend on it, but it is poor practice. Fix: wire each unused channel as a follower (OUT to IN-, which are
  neighbouring pins, and IN+ to GND, fine for the rail-to-rail TLV9004): new nets and short tracks on U7 / U12, no part
  moves. Not done here (net and track change; needs the coordinator's yes first).

## Re-run

`python tools/drc_erc_waivers.py A|B|IN` (writes) or `--check` (writes nothing; exit 1 on an unwaived item or a file
that would change). To see the waived items in KiCad: Inspect > DRC / ERC, "Show exclusions".
