# Enclosure v2 concept (phase 1, 2026-11-12)

Status: concept only (massing). Brief: `DECISIONS.md` 2026-11-12 "v2" lines. Base: a copy of Grok's TEST 2 **variant b** (no J3, matches a1a). The pack itself is untouched.

Fusion copy (not in git): `.claude/tmp/enclosure-v2-concept.f3d` / `.step` in the `encl-v2` worktree.
Views: `docs/diagrams/enclosure-v2-concept-{iso-front-right,iso-back-left,top,front}.png`.

## 1. What the concept changes (and nothing else)
- Removed the two vertical connector turrets.
- Added a raised connector housing on the lid (X 150-240, top Z 85, r 8 top edges), trimmed to the drafted body width.
- Cut a step-down at the east end (lid top lowered to a Z 22-25 terrace, X 240-270).
- X1 and X2 are turned horizontal and mounted on the housing's east riser face, pointing east over the step-down. Centres are at Z 55, Y -24 (X1) and Y -80 (X2). The flanges span Z 29.6-80.4.
- Everything else is Grok's: heat sink, feet, fan pod, BATT/GND and OUT extensions, input deck, standoffs, gap pads, the lid styling, and the lid fastening.

Massing only. The housing is solid, the panel holes aren't cut, and there's a leftover turret patch on the main top. X1/X2 are still Grok's envelope shapes, not TE models (see section 4).

## 2. Grok TEST 2 inventory (from the pack's SUMMARY.md / DRIVING-DIMENSIONS.md)
| Item | Variant a | Variant b |
|---|---|---|
| Board A J3 | DT15 kept, lid pods over the plugs | Removed (our a1a) |
| Lid footprint | 280.2 x 142.0 | 280.2 x 119.25 |
| Height, feet to lid top | 125 | 116 |
| Connector tips | 144.7 | 144.7 |

Shared by both variants:
- **Base:** 6063/6061 sink, 8 mm plate, 30 mm fins down running east-west. 4 feet, dia 16, M6 through, Z -44.
- **Lid attachment:** 12 x SSH-M4 x 12 from below, through counterbores in the sink, into M4 heat-set inserts in dia 9 lid bosses.
- **Lid style:** skirt band with knuckle ribs, 6° drafted upper body, low power terrace (Z 30), main body (Z 55) with grooves, turrets (Z 72).
- **Fans:** 2 x Sunon MF30101V1 (30 x 30 x 10) in a PA12 pod at the east end, under the sink. They pull air east.
- **Power terminals:**
  - BATT/GND: M6 M-F extensions AF10 on board B's M6 terminals, in raised collars. Only the top shows.
  - OUT1-4: M4 M-F extensions AF7 in a recessed bay with a barrier. Lugs exit north/south.
  - A1/A2 feed: internal flex links clamped under the M6 extensions (not modelled).
- **Input boards:** a PA12 input deck on M3 x 25 standoffs at Z 30.8-33.8. The 3 input boards are rotated 90°, bottom at Z 37.8.
- **USB:** 3 USB-C slots in the south skirt.

## 3. Conflicts with DECISIONS.md and the minimal change for each
| # | Grok TEST 2 | Our decision | Minimal change |
|---|---|---|---|
| 1 | J3 removed; route to X1 TBD | a1a: wire pads in the 12 J3 holes | Wires run from the board centre under the input deck to X1/X2 |
| 2 | X1/X2 vertical in turrets | v2: horizontal, on a lid step-down, pointing to one side | Done in the concept (pointing east) |
| 3 | Input board IN2 at X 196-262, Z 37.8-49 | v2 connector housing | **Clash.** X1/X2 rear bodies inside the housing (X 212-240, Z 30-80) collide with IN2 and the deck (to X 262). Shift the deck and IN2 west, or relocate IN2 (question v2) |
| 4 | BATT/GND only on board B; flex links to A1/A2 | e4a / b1b: copper bars for about 150 A | Flat copper bars under the lid instead of flex links, clamped in the 4 mm gap under the M6 extensions. Covered, no stud ends showing |
| 5 | OUT1-4 on M4 extensions in a bay | p2a: straps to enclosure studs | Drop the straps. Grok's extensions already show only the terminal top (Dan v2). Upsize the hex (question v3) |
| 6 | 2 x 30 mm fans, pulling, east | e3c: push, quietest, one larger fan preferred | Reverse the airflow. Fan size is question v5. The fan end must not be the side the plugs exit (question v1) |
| 7 | 3 USB-C slots | y1a: one sealed USB-C bulkhead + hub | One Amphenol LTW bulkhead on the connector riser or step + an internal hub; close the 3 slots |
| 8 | Height 116 (b) | Limit about 127 | Concept is 129 (housing top Z 85, feet Z -44): 2 mm over. Lower the housing by 2 mm or shorten the feet |
| 9 | Panel hole dia 43.08 (TBD) | Real cut-outs | TE spec 0425-021-0000 isn't public. Use TE's customer drawing / STEP once downloaded |

No conflict found: the lid fastening (answers Dan's "how does the lid attach"), heat-sink concept, feet, pedestals and gap pads, and board positions.

## 4. Real vendor CAD models
| Part | Use | Source | Status |
|---|---|---|---|
| TE HD34-24-21SN | X1 | https://www.te.com/en/product-HD34-24-21SN.html (Customer View Model, 3d_stp.zip) | **Blocked:** TE requires accepting its "ECAD Model Terms and Conditions" in a dialog, and scripted downloads return 403 |
| TE HDP24-24-47SE-L017 | X2 | TE product page, same terms | Blocked, same reason |
| TE HD36-24-21PN / HDP26-24-47PE-L015 | Mating plugs (plug clearance) | TE product pages | Blocked, same reason |
| Amphenol LTW USC series (e.g. USC-00PMFY-SC7001) | USB-C bulkhead | https://www.digikey.com/en/products/detail/amphenol-ltw/USC-00PMFY-SC7001/21310276 | Not downloaded yet |
| Fan (Sunon / Noctua) | Push fan | Vendor sites | Not downloaded yet |
| Würth 7461084 (M6) / 74650074R (M4) | Board terminals | In the board STEPs already | OK |

Dimensions known so far (Grok's sources, unchanged):
- **X1 HD34-24-21SN:** length 41.86, flange 50.80 / 47.63 (TE ICT catalogue p.147).
- **X2 HDP24-24-47SE-L017:** front 26.16, flange 2.54, rear body 42.29 x 17.07 (TE customer drawing).
- **Panel cut-out:** TBD.

## 5. Professional PDM design cues (research)
Grok's survey (pack `reference/SOURCES.md`) covers OBR PCM2, Link Razor PDM, Haltech PD16, ECUMaster PMU16, MoTeC PDM15/30/32, Bosch PBX90, Cosworth IPS32/48, AiM PDM32, Life Racing PDU10 and Cartek PDP16. Current product pages checked 2026-11-12: Link Razor, ECUMaster PMU16, AiM PDM32/PDM08, Syvecs PDU.

Cues that make them look professional, and where v2 uses them:
1. **One connector face.** All circular connectors sit on one raised face or plateau, never scattered (OBR PCM2, Cosworth IPS). v2: X1/X2 together on one riser.
2. **Battery stud in a raised collar** with a printed polarity mark; only the stud top shows (Link Razor, Haltech PD16, ECUMaster PMU16). v2: Grok's collars stay.
3. **Stepped body:** a low power terrace plus a taller electronics body (Haltech PD16). v2: kept, plus the connector step.
4. **Machined or anodised aluminium with fins** as the visible base (Bosch PBX90, ECUMaster PMU). v2: Grok's sink.
5. **Clean flat top** with a logo or label recess and channel numbering near the connectors (all brands). To add: a label recess and pin-map plate on the connector riser.
6. **Flange mounting ears or feet** with through-bolts (most units). v2: Grok's 4 feet.
7. **No exposed copper or ring lugs** except the main stud (all brands). v2 meets this with covered bars and the terminal bay.
