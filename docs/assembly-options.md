# Assembly options and costs (for Dan's go / no-go)

Written 2026-11-23 by job assemblyquotes (branch `docs/assembly-options`, from main a422adf). Dan's question (2026-11-23 09:01):
cheaper places to get the boards assembled, or mostly assembled so he solders the big through-hole parts himself?
Prices are USD. "ASSUMED" = an estimate with no published price or quote behind it. Every web price was read on
2026-11-23 (no logins, no quotes made). Part prices: LCSC price breaks in `docs/parts-audit.csv`, at each part's
smallest sold quantity; three parts not in that file are ASSUMED (U5 CY15B064J-SXE $5.00, Y1 ECS-80-18-30Q $0.60)
or from Mouser (T1-T8 Wurth 74650074R $4.09, `docs/parts-audit.md` 4.1). The 6 press-fit terminals (7461084) and the
harness wire pads (A J3, B J6) are Dan's in every route, so they are left out of every total.

## 1. Short answer

- **No cheaper published-price assembler than JLCPCB for these boards.** The others (PCBWay, Seeed, NextPCB, MacroFab,
  Eurocircuits, Aisler assembly) only price after an upload with a login; none publishes a lower fee list.
- **Soldering the through-hole parts yourself saves about $62 (4-5 %)** for about 3.5-4 h, most of it on the big
  output terminals of board B (the hardest joints on the PDM). Small win, real risk.
- **Building everything yourself (bare boards + stencils)** saves about $585 (41-46 %) but is 10-16 h of reflow work
  on exposed-pad switches, an LQFP-64 and via-in-pad boards with no X-ray / AOI.
- **Budget check:** the JLCPCB plan for one PDM set comes to about **$1,265-1,422** with the 35 % US duty JLCPCB
  charges at checkout and the second board B that its minimum forces. The $650-850 in `docs/pdm-vs-relays.md` looks
  like it leaves out the duty (about $320-360) and the second B.

## 2. What each board needs (from the BOMs, CPLs and board files)

| | Board A | Board B | Input board |
|---|---|---|---|
| Need per PDM | 2 | 1 | 3 |
| Bare boards (smallest lot) | 5 | 5 | 5 |
| Assembled (smallest lot) | 2 | **2** (JLCPCB minimum is 2: 1 spare B) | 3 |
| Layers, size | 4, 72.4 x 95.3 mm | 4, 111.4 x 95.3 mm | 2, 66.1 x 64.1 mm |
| Special fab items | ENIG, 1 oz inner, TG155, epoxy-filled vias (58), press-fit holes | same (151 filled vias) | ENIG, epoxy-filled vias (21) |
| JLCPCB BOM lines / placed parts | 44 / 129 | 47 / 194 | 7 / 46 |
| Basic / extended lines (`docs/parts-audit.md` 13.2; unknown = extended, ASSUMED) | 8 / 35 + 1 global | 8 / 37 + 2 global | 4 / 3 |
| SMD pads per board (board file) | 464 | 700 | 143 |
| Parts cost (this lot) | $166.23 (2 boards) | $291.82 (2 boards) | $8.59 (3 boards) |

Minimum lots: JLCPCB Economic "2 - 50 pcs", Standard "2 - 80000 pcs"
([JLCPCB PCBA capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities), read 2026-11-23).

### Through-hole parts (what Dan would solder in the partial route)

| Board | Part (ref) | Maker part | Joints per board | Difficulty | Why |
|---|---|---|---|---|---|
| A | USB-C (J5) | GCT USB4085-GF-A | 20 (16 pins in 2 close rows + 4 shell legs) | medium | close pin rows: fine tip, flux, check for bridges |
| B | USB-C (J2) | GCT USB4085-GF-A | 20 | medium | as above |
| B | Output terminals (T1-T8) | Wurth 74650074R (REDCUBE THR, M4) | 4 per terminal, 32 per board | **hard** | made for machine (reflow) soldering ([Wurth WP-THRBU page](https://www.we-online.com/en/components/products/WP-THRBU_THROUGH-HOLE): "focus on automated assembly"); pins sit in big copper pours on a 1 oz / 1 oz 4-layer board: needs a 100 W+ iron with a big tip and board preheat (ASSUMED); OUT1-4 carry 31 A, so a cold joint matters |
| Input | Micro-Fit 2x6 (J2) | Molex 43045-1200 | 12 | easy | 3 mm pitch |
| A, B | Power terminals (A J1/J2, B J1/J3) | Wurth 7461084 press-fit | not soldered | arbor press | already Dan's job in every route (`docs/order-checklist.md` 8) |

Per PDM order (2 A + 2 B + 3 input assembled): 180 through-hole joints, 104 of them on board B.

## 3. JLCPCB (the current plan) in detail

### 3.1 Published fees ([JLCPCB "PCB assembly price"](https://jlcpcb.com/help/article/pcb-assembly-price), "Last updated on Oct 22, 2026", read 2026-11-23)

| Fee | Economic | Standard |
|---|---|---|
| Setup | $8.18 | $25.56 (one side) |
| Stencil (kept by JLCPCB) | $1.53 | $8.21 (one side) |
| Feeder loading | $3.07 per **extended** part line | $1.53 per part line (basic and extended) |
| SMT placement | $0.0016 per joint | $0.0016 per joint |
| Through-hole (manual) | $0.0164 per joint + $3.58 hand-soldering labour per order | same |
| Confirm parts placement | $0.45 | $0.45 |
| Packing | free | $0.50 + area |
| Global sourcing (parts LCSC lacks) | no shipping charge; **connectors: $20 commodity inspection per part type**; lead time 9-15 days | same |

Global sourcing: [terms](https://jlcpcb.com/help/article/global-sourcing-parts-order-terms-conditions) and
[sourcing instruction](https://jlcpcb.com/help/article/pcba-parts-sourcing-instruction) (read 2026-11-23). On this PDM:
A Y1 and U5 (CY15B064J-SXE, 0 at LCSC on 2026-11-23), B Y1, U5 and T1-T8. The $20 is counted once, for T1-T8
(a terminal; ASSUMED to count as a connector).

**Bare boards are ASSUMED** (the JLCPCB price only shows on the live quote page): 5 pcs board A $60-100, board B
$75-120, input board $25-45, with ENIG, epoxy-filled vias, 1 oz inner copper, TG155 and press-fit holes. JLCPCB says
4-layer resin-filled via prices rose "slightly" ([notice 2026-08-06](https://jlcpcb.com/news/pcb-lead-time-and-price-adjustment-august2026)).
Shipping to the US (one DHL box): $25-40, ASSUMED.

### 3.2 US import duty

- JLCPCB ships to individuals DDP: duty is paid at checkout. Its rate table: **PCB 35 %, SMT (assembled) 35 %,
  stencil 90 %** (update of 2026-03-17); orders charged inside the 35-90 % band are not refunded or topped up
  ([JLCPCB US tariff FAQ](https://jlcpcb.com/help/article/us-tariff-policy-faq) and
  [policy updates](https://jlcpcb.com/blog/logistics-policy-updates-due-to-the-us-tariff-on-china), read 2026-11-23).
- Background: IEEPA tariffs struck down 2026-02-20, Section 122 10 % from 2026-02-24
  ([Altium, 2026-04-14](https://resources.altium.com/p/tariff-reset-pcb-workarounds)); Section 122 expired 2026-07-24,
  largely replaced by Section 301 duties of 10 or 12.5 %
  ([ABA, fall 2026](https://www.americanbar.org/groups/public_contract_law/resources/procurement-lawyer/2026-fall/ieepa-tariffs-struck-down-replacement-tariffs-expired/));
  the 178 Section 301 exclusions (Altium: they include 2- and 4-layer PCBs) run to 2027-01-09
  ([KPMG, 2026-11](https://kpmg.com/us/en/taxnewsflash/news/2026/11/ustr-section-301-china-product-exclusions.html)).
  So the legal stack on a bare board may be lower than 35 %, but JLCPCB's checkout charges 35 %.
- This page applies 35 % to everything in a JLCPCB order (boards, fees, parts; not shipping): ASSUMED.
- Parts Dan buys from a US distributor (Digi-Key) carry no extra import step for him.

### 3.3 Per board, one PDM order (Standard, the plan in `docs/order-checklist.md`)

| Board (lot) | Assembly fees | Parts | Bare boards (ASSUMED) | With 35 % duty |
|---|---|---|---|---|
| A (5 bare, 2 assembled) | $107.76 | $166.23 | $60-100 | $451-505 |
| B (5 bare, 2 assembled) | $134.16 (incl. $20 inspection) | $291.82 | $75-120 | $676-737 |
| Input (5 bare, 3 assembled) | $50.29 | $8.59 | $25-45 | $113-140 |
| **Set, + shipping $25-40** | $292.21 | $466.64 | $160-265 | **$1,265-1,422** |

### 3.4 Economic vs Standard (assembly fees only, same parts)

| Board | Economic | Standard | Verdict |
|---|---|---|---|
| A | $126.40 | $107.76 | Standard cheaper (Economic charges $3.07 for each of about 36 extended lines) |
| B | $137.42 | $114.16 (+ $20 inspection either way) | Standard cheaper |
| Input | $24.23 | $50.29 | **Economic $26 cheaper (about $35 with duty)**, if the quote page allows Economic with epoxy-filled vias (not checked) |

Economic also allows only "standard stack-up", single-side placement and ENIG on 1.6 mm green boards (capabilities
page above): A and B need 1 oz inner copper, press-fit holes and filled vias, so they stay Standard (as the order
checklist says). Try Economic for the input board only at quote time.

### 3.5 Partial: JLCPCB fits the SMD parts, Dan solders the through-hole parts

Removes from the JLCPCB order: 4 feeder lines ($6.12), 180 hand joints ($2.95), 3 x $3.58 labour, the $20
inspection, the through-hole parts ($75.20) and the 35 % duty on all of that. Dan buys those parts at Digi-Key
(ASSUMED LCSC price + 15 %, + $7 shipping = $93.48).

| Board | Assembly fees | Parts (JLCPCB) | With duty (bare ASSUMED) |
|---|---|---|---|
| A | $101.99 | $163.40 | $439-493 |
| B | $105.81 | $223.55 | $546-607 |
| Input | $44.59 | $4.49 | $100-127 |
| **Set, + shipping + Dan's Digi-Key parts** | | | **$1,204-1,360** |

Saving: **$62 (4.3-4.9 %)**. Extra for Dan: about 3.5-4 h for all 7 assembled boards (ASSUMED: USB-C 4 x 15 min,
16 terminals 6-9 min each with preheat, Micro-Fit 3 x 5 min, checks 30 min) and a 100 W+ iron with preheat. If Dan
leaves the spare B without its terminals and USB-C: about $39 more saved ($101 in all) and about 2-2.5 h. Side effects: T1-T8 leave JLCPCB global sourcing (one 9-15 day wait
and the "no approved alternate" risk go away; Y1 and U5 still need it); the generator's BOM / CPL would need T1-T8,
J5 / J2 and input J2 marked "fitted by Dan" (`tools/sch_bom_fields.py`, then `tools/gen_fab_jlcpcb.py`), and the
T1-T4 vs U8-U11 overlap question stays open.

## 4. Other services and routes

| Service / route | What is published (read 2026-11-23) | For this PDM | Verdict |
|---|---|---|---|
| PCBWay (the fallback fab) | assembly "starting from $88 for 10 pcs in total", "$0.1 - $0.3 per component" ([electronics-lab, undated](https://electronics-lab.com/pcbway-low-cost-prototype-pcba-services-starts-just-88-10-units)); 7-15 business days ([NextPCB comparison, updated 2026-11](https://www.nextpcb.com/blog/jlcpcb-vs-pcbway-vs-nextpcb-comparison-2026)) | quote by MPN from `*-bom-full.csv` needs a login: not priced; China origin, so the same duty band (ASSUMED) | not shown cheaper; keep as the fallback |
| Seeed Fusion | no fee list; one user paid "$142 for the assembly of 2 boards" ([hackaday.io, 2022-10-11](https://hackaday.io/project/185901-seeed-fusion-pcb-pcba-review)) | not priced | ASSUMED not cheaper |
| NextPCB | Rev 0 PCBA launch: "free assembly on their first Rev 0 PCBA order (up to $500 USD)" ([CNX Software sponsored post, 2026-05-13](https://www.cnx-software.com/2026/05/13/nextpcb-officially-launches-rev-0-pcba-an-automated-no-touch-prototype-assembly-service-built-for-speed-and-predictability/)); site banner "Free for 10pcs" and a 50 %-off coupon for 100 pcs to 2026-12-31 ([NextPCB free assembly page](https://www.nextpcb.com/blog/free-pcb-assembly)) | if the promo covers one of our designs: up to that design's assembly fees (B: about $114 + duty) saved; whether Rev 0 takes 4-layer filled-via, press-fit and THR boards is **not known** | the only possible cheaper full route: worth one quote with Dan's login |
| MacroFab (US) | "no minimum order quantities"; quote only ([MacroFab prototyping](https://macrofab.com/prototyping)) | not priced; US-made, so no import duty | ASSUMED dearer (US labour) |
| Eurocircuits (EU) | 1-5 boards, "No Minimum Order Charge", 6 working days; price only in their calculator ([Eurocircuits PCB Proto](https://www.eurocircuits.com/pcb-assembly-proto/)) | not priced | ASSUMED dearer |
| Aisler (EU) | bare: job fee + area: 4-layer ENIG Budget EUR 14 + EUR 0.13/cm2 per board; 2-layer ENIG Budget EUR 12 + EUR 0.097/cm2 (sets of 3; page 2023-08-27, [Aisler pricing](https://community.aisler.net/t/our-simple-pricing/102)); assembly per task, no rates published, EUR 15 per customer-supplied part ([Aisler assembly](https://aisler.net/products/assembly)) | bare, 3 each: A EUR 40.91, B EUR 55.40, input EUR 24.33; 1 oz inner, filled vias, press-fit: not checked; US duty on EU goods: not checked | bare boards look cheap; specs unproven |
| OSH Park (US, bare only) | 4-layer $10 per sq in for 3 boards, 1 oz outer / **1/2 oz inner**, ENIG, 9-14 days ([4-layer](https://docs.oshpark.com/services/four-layer)); 2-layer $5 per sq in for 3, 1 oz ([2-layer](https://docs.oshpark.com/services/two-layer/)) | 3 each: A $106.95, B $164.55, input $32.84 (= $304.34), no duty | **A and B: not allowed** (1 oz inner is the decided copper, `tools/copper_order.py`); input board possible but no filled vias (ASSUMED) |
| Bare boards + stencils only (JLCPCB), Dan builds all | stencil "$3" up to 100 x 100 mm ([JLCPCB small stencil](https://jlcpcb.com/resources/small-stencil)); stencil duty 90 % (3.2) | one set: bare $160-265 + 35 %, stencils A $3 / B $7 (ASSUMED) / input $3 + 90 %, shipping $25-40, parts for exactly 1 set from Digi-Key ($329.72 + 15 % ASSUMED + $7), paste and flux $30 (ASSUMED) = **$682-839** | cheapest cash route; 10-16 h (ASSUMED: 590 placements, 4 reflow runs, exposed-pad PROFETs, LQFP-64 MCU, 10-pin uSiP 5 V module, via-in-pad); no X-ray / AOI; needs a hot plate or oven |
| In-house build at Spark (cost rule c8) | parts at each part's smallest sold quantity (LCSC first price break; full reels cost more, not priced) + blank PCBs and stencils from JLCPCB; no labour or machine cost | one set: **$595-752** | cheapest on paper; depends on the line being available |

## 5. Comparison (one PDM; JLCPCB's minimum order already is one test set: 5 bare boards each, 2 A + 2 B + 3 input assembled)

| Route | One test set | Saving vs current plan | % | Dan's extra hours |
|---|---|---|---|---|
| **Current plan**: JLCPCB Standard, JLCPCB fits all but the press-fit terminals | $1,265-1,422 | - | - | 0 |
| **Cheapest full assembly**: same, input board on Economic (if the quote page allows it) | $1,230-1,387 | $35 | 2.5-2.8 % | 0 |
| **Cheapest partial**: JLCPCB SMD only, Dan solders the 180 through-hole joints | $1,204-1,360 | $62 | 4.3-4.9 % | 3.5-4 h |
| Partial, spare B left without terminals / USB-C | $1,165-1,321 | $101 | 7.1-8.0 % | 2-2.5 h |
| Partial + input board on Economic | $1,167-1,323 | $98-99 | 7.0-7.8 % | 3.5-4 h |
| Bare boards + stencils, Dan builds everything | $682-839 | $583-584 | 41-46 % | 10-16 h |
| In-house at Spark (c8 costing) | $595-752 | $670 | 47-53 % | labour not costed (c8) |

All rows: + 6 press-fit terminals (Dan, every route). The bare-board price (ASSUMED $160-265 for the three lots)
is the biggest unknown: the live JLCPCB quote page fixes it in 2 minutes and moves every row by the same amount.
`docs/pdm-vs-relays.md` gives $650-850 for the assembled boards; this model is $415-770 higher, mostly the 35 %
duty ($322-358) and the second board B the 2-board minimum forces (about $190 with duty).

Lead time (current plan): bare boards + assembly (Standard build ">= 4 days", capabilities page) + global sourcing
9-15 days (Y1, U5, T1-T8) + DHL: about 3-4 weeks (ASSUMED). The partial route does not shorten it (Y1 and U5 still
wait for global sourcing).

## 6. Recommendation (for the go / no-go, c7 = a)

Stay with the current plan, JLCPCB Standard with everything but the press-fit terminals fitted by JLCPCB: no
assembler with published prices is cheaper, and soldering the through-hole parts yourself saves only about $62
(about 5 %; about $100 if the spare B is left unfinished) for 2-4 hours, most of it on the heavy THR output terminals of board B, which carry 31 A and are made
for machine soldering, so it is not worth the risk. Take the one free win at quote time: try Economic for the input
board (about $35 less if the page accepts it with filled vias), and ask NextPCB for one quote in case its first-order
free-assembly offer covers a design. Budget the first PDM set at about $1,265-1,422 including the 35 % US duty
JLCPCB charges, not $650-850; the only big saving (about $585-670, 41-53 %) is a full in-house or bench build from
bare boards and stencils, which makes sense only if a reflow line with inspection is at hand.

## 7. How the numbers were made, and what was not read

- Fees: section 3.1 table x the counts in section 2 (BOM lines from `hardware/fab/*/*-bom-jlcpcb.csv`, SMD pads and
  through-hole pads counted in the three `.kicad_pcb` files, B assembled x 2). Parts: each JLCPCB BOM line at its
  LCSC price break for the lot, bought at no less than LCSC's smallest quantity.
- Not read (the page did not load for this job): PCBWay's assembly price page, OSH Park's pricing page (its service
  pages above were read instead), Seeed Fusion's PCBA page. No live quote page was used (they need an upload; PCBA
  needs a login).
- Before paying: the live JLCPCB quote replaces every ASSUMED bare-board figure. Every route buys the same 5 + 5 + 5
  bare boards with the same 35 % duty, so a different board price moves every row by about the same amount and
  does not change their order (OSH Park and Aisler rows aside).
