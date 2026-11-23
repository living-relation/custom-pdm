# Assembly options and costs (for Dan's go / no-go)

Updated 2026-11-23 by job cheaperpcba (branch `docs/cheaper-assembly`), after Dan (18:12): "There has got to be
cheaper options ... there's no way import duties are that much. Look for other options." The first estimate (job
assemblyquotes, PR #155) is kept word for word under "First estimate" at the end; its JLCPCB fee and parts numbers
are still the inputs here. Prices USD. "ASSUMED" = no published price or quote behind it. Every web page below was
read on 2026-11-23 (no logins, no uploads, no quotes made).

## 1. Short answer

- **The duty is real, and 35 % is not too high for assembled boards.** The legal US duty on an assembled PCB from
  China is about **41 %** today; on a bare 2- or 4-layer FR-4 board it is **12.5 %** (until 2027-01-09). JLCPCB
  charges a flat ~35 % on both (section 2). So JLCPCB slightly under-charges the assembled boards and over-charges
  the bare ones.
- **Cheapest credible route: bare boards + stencils from JLCPCB, parts from Digi-Key / Mouser, assembled at Spark
  (c8): about $650-870** for one set, against $1,265-1,422 for the JLCPCB plan (saves about $550-600). Needs
  Spark's SMT line or reflow oven; no labour is costed (c8).
- **If Spark's line is not free:** get one NextPCB quote (its small-batch offer takes up to $200 off the SMT cost of
  every 1-10 piece order, and builds 1 board B): about $730-1,310, ASSUMED. Take it only if it beats the JLCPCB
  SMT-only route ($1,165-1,321) and NextPCB confirms the press-fit hole tolerance (section 4).
- **Assembly outside China does not pay off here.** Taiwan / EU pay about 10 % duty, but no Taiwan, Vietnam, EU,
  UK, Canada, Mexico or US assembler publishes a low-volume price, and their labour is ASSUMED to cost more than
  the ~25-30 points of duty saved. Sending Dan's own chips to China does not avoid duty either (section 3, row 8).

## 2. US import duty, verified (read 2026-11-23)

| Layer | Bare PCB, HTS 8534.00.00 (4-layer .0020, 2-layer .0040) | Assembled PCB (PCBA), HTS 8538.90.30 (PCAs for 8536 / 8537 apparatus) | Source |
|---|---|---|---|
| MFN (normal) duty | Free | 3.5 % | [wove 8534.00.00](https://tariffs.wove.com/us/tariff/8534.00.00), [wove 8538.90.30](https://tariffs.wove.com/us/tariff/8538.90.30) (CBP HTS file of 2026-11-09) |
| Section 301 China lists (9903.88.03) | 25 %, **excluded** for "Printed circuit boards, each with a base wholly of plastics impregnated glass, not flexible, with 4 [or 2] layers of copper" until 2027-01-09 | 25 % (no exclusion found) | [gatewaylines exclusions list, updated 2026-11-07](https://tariff.gatewaylines.com/section-301-exclusions); [KPMG 2026-11-09](https://kpmg.com/us/en/taxnewsflash/news/2026/11/ustr-section-301-china-product-exclusions.html): "All 178 current exclusions are extended through January 9, 2027" |
| Section 301 forced-labour action (9903.05.31), from 2026-07-24 | 12.5 % | 12.5 % | [EY 2026-07-24](https://taxnews.ey.com/news/2026-1607-ustr-finalizes-section-301-forced-labor-tariffs-on-60-economies-additional-tariffs-of-10-percent-or-125-percent-take-effect-24-july-2026); stacks on the China lists and MFN ([Zonos, Aug 2026](https://zonos.com/docs/guides/country-guides/united-states/section-301-forced-labor)) |
| IEEPA "reciprocal" / fentanyl, Section 122 | none: IEEPA struck down; Section 122 10 % expired 2026-07-24 | none | [AtlasPCB, 2026-08-21](https://www.atlaspcb.com/news/news-pcb-tariff-section-301-exclusion-expiry-november-2026/) |
| De minimis ($800) | gone for every mode but the postal network, indefinitely, from 2026-06-24 (DHL / FedEx included) | same | [Federal Register 2026-12670](https://www.federalregister.gov/documents/2026/06/24/2026-12670/indefinite-suspension-of-the-de-minimis-exemption-for-merchandise-arriving-through-all-modes-other) |
| **Legal total from China** | **12.5 %** (37.5 % if the exclusion lapses on 2027-01-09) | **41 %** (wove shows 41 % for a "Power Distribution Unit Control PCB" from China) | [wove PDU control PCB from CN](https://tariffs.wove.com/us/tariff/8538.90.30.00/power-distribution-unit-control-pcb/from/CN) |

Other HS codes sometimes used for a PCBA: 8537.10.91 (a complete control board, MFN 2.7 %, ASSUMED: page not read;
total about 40 %) and 8473.30.11 (computer parts only, does not fit a PDM).

**How the assemblers charge it:**
- **JLCPCB** ([US tariff FAQ, updated 2026-10-29](https://jlcpcb.com/help/article/us-tariff-policy-faq)): US
  individuals must take DDP (duty pre-paid at checkout); companies may pick CPT and pay customs themselves. Its
  build-up: regular duty "0~7.5%", Section 301 25 %, and for the 12.5 % action of 2026-07-24 "JLCPCB sets its own
  rate at 10%"; total "About 35%~92.5%". Inside the 35-90 % band it does not refund or top up. **That is where the
  35 % came from:** 0 % MFN + 25 % + JLCPCB's 10 %.
- **PCBWay** ([tariff news, section "Updated on August 15 2026"](https://www.pcbway.com/blog/News/Impact_of_the_New_U_S_Tariff_Policy_on_Customs_Clearance_51dff4fd.html)):
  "PCB: 37.5%", "SMT: 47.50%" (estimates), pre-paid on DHL / FedEx DDP.
- **NextPCB:** its own US duty billing is not published ([NextPCB tariff article, Aug 2026](https://www.nextpcb.com/blog/pcb-manufacturing-tariffs-2026-china-sourcing) quotes "a combined Section 301 rate of 37.5% on top of the underlying MFN duty"). ASSUMED 35-47.5 %.
- **Other countries** (same EY / ghy pages): Taiwan and the EU pay 10 % in total with MFN (MFN counts toward it);
  UK, Canada, Mexico, Malaysia 10 % on top of MFN; Vietnam, Thailand 12.5 %; Canada / Mexico goods that qualify for
  USMCA pay nothing ([ghy, 2026-07-23](https://www.ghy.com/trade-compliance/ustr-section-301-forced-labor-60-economies/)).
  A PCBA assembled there from Chinese bare boards is ASSUMED to take the assembly country's origin (SMT assembly is
  usually a substantial transformation; not checked for this case).
- **US distributors:** Mouser adds a tariff line item on some China-origin HTS 8541 / 8542 parts shipped in the US
  ([Mouser, updated 2026-07-24](https://www.mouser.com/en/tariff-updates/)); Digi-Key "minimized tariff pass-through"
  ([Digi-Key, updated 2026-09-08](https://www.digikey.com/resources/tariff-resources)). Hence +15-25 % over LCSC
  below (ASSUMED).

## 3. Routes to one assembled PDM set, ranked (cheapest credible first)

One set = 2 x board A, 1 x board B, 3 x input board, fitted (the 6 press-fit terminals are Dan's in every route).
Shared inputs from the first estimate: JLCPCB bare boards, 5 of each, $160-265 (ASSUMED); JLCPCB stencils $13
(+ 90 % duty = $25); DHL $25-40 (ASSUMED); parts for exactly one set $329.72 at LCSC prices, bought from Digi-Key /
Mouser at +15-25 % + $7 = **$386-419** (ASSUMED mark-up, section 2). 590 placed parts per set.

| # | Route | Landed total, one set | Lead time | MOQ | Gotchas (4-layer ENIG, filled vias, 1 oz inner, TG155, press-fit) |
|---|---|---|---|---|---|
| 1 | **Bare boards + stencils from JLCPCB, US-bought parts, built at Spark (c8)** | **$650-870** (bare 216-358 with 35 % + stencils 25 + DHL 25-40 + parts 386-419 + paste / flux 0-30); Spark's own c8 figure with reels at MOQ is $758-837 (Spark pitch, ADR-2026-11-23-proof-and-assembly) | ~2 weeks (ASSUMED: boards ~1 week + DHL, Digi-Key 2-3 days, 1-2 days build) | 5 bare per design | JLCPCB makes every board spec (fab notes). Needs Spark's paste printer / reflow and an X-ray or careful inspection of the PROFET exposed pads; labour not costed (c8). As a company Spark may take CPT and pay the legal 12.5 % on bare boards (saves about $20-50 after a courier brokerage fee, ASSUMED $15-30). |
| 2 | Same, built by Dan at his bench | $680-900 (+ hot plate if none, ASSUMED $30) | ~2 weeks + 10-16 h of Dan's time | 5 bare | via-in-pad, LQFP-64, exposed-pad switches, no X-ray / AOI (first estimate section 4) |
| 3 | **NextPCB turnkey, small-batch offer** (1-10 pcs, "Up to $200 off eligible assembly costs", any number of orders, turnkey only, under 5 % customer parts; [NextPCB offers](https://www.nextpcb.com/offers)); 3 orders, board B qty 1 | $730-1,310 (ASSUMED: bare 160-265, parts 330-396, fees after the $200 off 30-200, duty 35-47.5 %, DHL 25-40) | 7-14 business days + sourcing + DHL (~3-4 weeks, ASSUMED) | 1 assembled | Plated-hole tolerance **±0.075 mm** "suitable for press-fit connectors"; Wurth 7461084 needs 1.475 ±0.05 mm ([NextPCB capabilities](https://www.nextpcb.com/pcb-capabilities)). Tg 130 / 150 / 170 (TG155 per ADR-2026-11-23-laminate reopen), inner 1 oz offered; resin-filled vias and ENIG not stated. Y1, U5 and T1-T8 must come from NextPCB sourcing. SMT fee level unpublished: one quote decides it. |
| 4 | JLCPCB SMT only, Dan solders the through-hole parts, spare B left without them | $1,165-1,321 (first estimate 3.5) | 3-4 weeks | 2 assembled B | 2-2.5 h hand soldering, heavy THR terminals |
| 5 | JLCPCB SMT only, Dan solders all through-hole parts | $1,204-1,360 (first estimate 3.5) | 3-4 weeks | 2 B | 3.5-4 h |
| 6 | **JLCPCB full (current plan)** | $1,265-1,422 (first estimate 3.3); coupons take off about $25-40 (new user $6 PCB + $10 SMT, monthly $6 / $9 SMT, [JLCPCB coupons, updated 2026-11-10](https://jlcpcb.com/help/article/new-customer-coupons)) | 3-4 weeks | 2 B | none: every spec is on its quote page |
| 7 | PCBWay, board B qty 1 ("Assembly MOQ is 1 piece", [PCBWay help](https://www.pcbway.com/helpcenter/pcb_assembly_ordering/What_s_the_min_quantity_of_assembly_.html)) | $1,100-1,580 (ASSUMED fees 250-400; duty 37.5 % bare / 47.5 % SMT) | 7-15 business days + DHL | 1 | its 47.5 % SMT duty eats the ~$190 saved on the second B |
| 8 | Dan buys the dear chips in the US and consigns them to JLCPCB | no saving: US customs value includes parts the buyer supplies (an "assist", ASSUMED), so they pay 35 % on the way back, plus ~$40-60 shipping to China (ASSUMED) | +1-2 weeks | 2 B | consigned-part handling, parts can be lost |
| 9 | US assembler with a kit (MacroFab, Screaming Circuits, CircuitHub, Advanced Assembly, Sierra): China bare boards + US parts | $1,250-2,340 (ASSUMED assembly $600-1,500 for 3 designs; none publishes a price: [MacroFab platform](https://www.macrofab.com/platform) "No minimum order quantities", quote only) | 1-3 weeks | 1 | US shops quote per job; Tempo Automation is gone (bankruptcy 2023, [Delaware case 23-11969](https://www.inforuptcy.com/browse-filings/delaware-bankruptcy-court/1:23-bk-11969/bankruptcy-case-tempo-automation-holdings-inc)) |
| 10 | EU turnkey (Aisler: "starts at a single populated PCBA", free worldwide shipping, [Aisler assembly](https://aisler.net/products/assembly)); US duty 10 % | not priced: assembly task prices only in its calculator, EUR 15 per customer-supplied part ([Aisler pricing, 2023-08-27](https://community.aisler.net/t/our-simple-pricing/102)); ASSUMED $1,300-2,500 | 6-9+ business days | 1 | 1 oz inner, filled vias, TG and press-fit holes not listed |
| 11 | Taiwan / Vietnam / Thailand / Malaysia / Canada / Mexico | not priced: no online low-volume price list found; Bittele (Canada) lists Shenzhen and Toronto sites, so origin is unclear ([7pcb](https://www.7pcb.com/Low-Cost-PCB-Assembly)); bestpcb.vn (Bac Ninh) quotes by e-mail only ([bestpcb.vn, 2026-05-22](https://www.bestpcb.vn/2026/05/22/prototype-pcb-assembly-services-low-volume/)) | - | - | quote by e-mail, specs unproven |
| 12 | Sponsorships (NextPCB Accelerator "Up to $500 project sponsorship", application; Seeed / PCBWay programmes) | not plannable | weeks | 1-2 | needs approval and a public open-source project; dingoPDM-Max (board B base) has no licence (ADR-2026-11-23-proof-and-assembly) |

US-made bare boards do not help: AdvancedPCB's $66 4-layer special has 1 oz inner but a minimum of 4, at most 30 sq in
and 35 holes per sq in, and no via fill stated ([AdvancedPCB $66 special](https://advancedpcb.com/en-us/66-each-special)):
$528 for A and B alone, more than all JLCPCB bare boards with duty. OSH Park's 4-layer has 1/2 oz inner (not allowed;
first estimate section 4). US stencils (Pololu: "$25 for first 4 square inches, $1 for each additional square inch",
[Pololu](https://www.pololu.com/product/446)) come to about $100, more than JLCPCB's with 90 % duty.

## 4. Recommendation (for the go / no-go, c7 = a)

- The duty Dan doubted is right: ~35 % at JLCPCB checkout, ~41 % in law for an assembled board. It cannot be dodged
  by consigning parts or by de minimis, and assembly outside China only pays off if the labour were no dearer than
  in China, which no low-volume shop shows.
- **Build at Spark if its SMT line (paste printer + reflow, and an X-ray or careful pad inspection) is free:** order
  only the bare boards (5 each) and stencils from JLCPCB with the current fab notes, buy the parts from Digi-Key /
  Mouser with `*-bom-full.csv`, and build there. About **$650-870**, about $550-600 under the JLCPCB plan, and about
  2 weeks. Check the STM32F446RET7 stock first (0 at LCSC and Mouser on 2026-11-23).
- **If Spark's line is not free:** one NextPCB quote (3 orders, B qty 1). Use it only if it lands under $1,165 and
  NextPCB confirms ±0.05 mm press-fit holes, resin-filled vias, ENIG, TG155 and 1 oz inner in writing. Otherwise the
  JLCPCB SMT-only route with the spare B left without its through-hole parts ($1,165-1,321).
- Budget: $650-870 (Spark build) or $1,165-1,422 (JLCPCB assembled). The $650-850 in `docs/pdm-vs-relays.md` matches
  the Spark build, not a bought assembly.

## 5. What was not read or not priced

- No live quote at any assembler (they need an upload and mostly a login); every assembler fee outside JLCPCB is ASSUMED.
- Not fetched: macrofab.com/pricing (the fetch needed an approval that nobody answered), unisco 8537.10.91 (site
  error); the 8537.10.91 MFN 2.7 % is ASSUMED. LCSC's own US duty billing was not found (ASSUMED the same 35 % as
  JLCPCB; the c8 LCSC part prices carry no US duty, so buying them from LCSC adds it).
- Not legal advice: wove, gatewaylines, AtlasPCB, ghy and Zonos are trade-data sites, not CBP; the Federal Register,
  EY and KPMG items agree with them.

---

## First estimate (job assemblyquotes, PR #155, 2026-11-23 morning; kept as written)

Written 2026-11-23 by job assemblyquotes (branch `docs/assembly-options`, from main a422adf). Dan's question (2026-11-23 09:01):
cheaper places to get the boards assembled, or mostly assembled so he solders the big through-hole parts himself?
Prices are USD. "ASSUMED" = an estimate with no published price or quote behind it. Every web price was read on
2026-11-23 (no logins, no quotes made). Part prices: LCSC price breaks in `docs/parts-audit.csv`, at each part's
smallest sold quantity; three parts not in that file are ASSUMED (U5 CY15B064J-SXE $5.00, Y1 ECS-80-18-30Q $0.60)
or from Mouser (T1-T8 Wurth 74650074R $4.09, `docs/parts-audit.md` 4.1). The 6 press-fit terminals (7461084) and the
harness wire pads (A J3, B J6) are Dan's in every route, so they are left out of every total.

### 1. Short answer

- **No cheaper published-price assembler than JLCPCB for these boards.** The others (PCBWay, Seeed, NextPCB, MacroFab,
  Eurocircuits, Aisler assembly) only price after an upload with a login; none publishes a lower fee list.
- **Soldering the through-hole parts yourself saves about $62 (4-5 %)** for about 3.5-4 h, most of it on the big
  output terminals of board B (the hardest joints on the PDM). Small win, real risk.
- **Building everything yourself (bare boards + stencils)** saves about $585 (41-46 %) but is 10-16 h of reflow work
  on exposed-pad switches, an LQFP-64 and via-in-pad boards with no X-ray / AOI.
- **Budget check:** the JLCPCB plan for one PDM set comes to about **$1,265-1,422** with the 35 % US duty JLCPCB
  charges at checkout and the second board B that its minimum forces. The $650-850 in `docs/pdm-vs-relays.md` looks
  like it leaves out the duty (about $320-360) and the second B.

### 2. What each board needs (from the BOMs, CPLs and board files)

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

#### Through-hole parts (what Dan would solder in the partial route)

| Board | Part (ref) | Maker part | Joints per board | Difficulty | Why |
|---|---|---|---|---|---|
| A | USB-C (J5) | GCT USB4085-GF-A | 20 (16 pins in 2 close rows + 4 shell legs) | medium | close pin rows: fine tip, flux, check for bridges |
| B | USB-C (J2) | GCT USB4085-GF-A | 20 | medium | as above |
| B | Output terminals (T1-T8) | Wurth 74650074R (REDCUBE THR, M4) | 4 per terminal, 32 per board | **hard** | made for machine (reflow) soldering ([Wurth WP-THRBU page](https://www.we-online.com/en/components/products/WP-THRBU_THROUGH-HOLE): "focus on automated assembly"); pins sit in big copper pours on a 1 oz / 1 oz 4-layer board: needs a 100 W+ iron with a big tip and board preheat (ASSUMED); OUT1-4 carry 31 A, so a cold joint matters |
| Input | Micro-Fit 2x6 (J2) | Molex 43045-1200 | 12 | easy | 3 mm pitch |
| A, B | Power terminals (A J1/J2, B J1/J3) | Wurth 7461084 press-fit | not soldered | arbor press | already Dan's job in every route (`docs/order-checklist.md` 8) |

Per PDM order (2 A + 2 B + 3 input assembled): 180 through-hole joints, 104 of them on board B.

### 3. JLCPCB (the current plan) in detail

#### 3.1 Published fees ([JLCPCB "PCB assembly price"](https://jlcpcb.com/help/article/pcb-assembly-price), "Last updated on Oct 22, 2026", read 2026-11-23)

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

#### 3.2 US import duty

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

#### 3.3 Per board, one PDM order (Standard, the plan in `docs/order-checklist.md`)

| Board (lot) | Assembly fees | Parts | Bare boards (ASSUMED) | With 35 % duty |
|---|---|---|---|---|
| A (5 bare, 2 assembled) | $107.76 | $166.23 | $60-100 | $451-505 |
| B (5 bare, 2 assembled) | $134.16 (incl. $20 inspection) | $291.82 | $75-120 | $676-737 |
| Input (5 bare, 3 assembled) | $50.29 | $8.59 | $25-45 | $113-140 |
| **Set, + shipping $25-40** | $292.21 | $466.64 | $160-265 | **$1,265-1,422** |

#### 3.4 Economic vs Standard (assembly fees only, same parts)

| Board | Economic | Standard | Verdict |
|---|---|---|---|
| A | $126.40 | $107.76 | Standard cheaper (Economic charges $3.07 for each of about 36 extended lines) |
| B | $137.42 | $114.16 (+ $20 inspection either way) | Standard cheaper |
| Input | $24.23 | $50.29 | **Economic $26 cheaper (about $35 with duty)**, if the quote page allows Economic with epoxy-filled vias (not checked) |

Economic also allows only "standard stack-up", single-side placement and ENIG on 1.6 mm green boards (capabilities
page above): A and B need 1 oz inner copper, press-fit holes and filled vias, so they stay Standard (as the order
checklist says). Try Economic for the input board only at quote time.

#### 3.5 Partial: JLCPCB fits the SMD parts, Dan solders the through-hole parts

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

### 4. Other services and routes

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

### 5. Comparison (one PDM; JLCPCB's minimum order already is one test set: 5 bare boards each, 2 A + 2 B + 3 input assembled)

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

### 6. Recommendation (for the go / no-go, c7 = a)

Stay with the current plan, JLCPCB Standard with everything but the press-fit terminals fitted by JLCPCB: no
assembler with published prices is cheaper, and soldering the through-hole parts yourself saves only about $62
(about 5 %; about $100 if the spare B is left unfinished) for 2-4 hours, most of it on the heavy THR output terminals of board B, which carry 31 A and are made
for machine soldering, so it is not worth the risk. Take the one free win at quote time: try Economic for the input
board (about $35 less if the page accepts it with filled vias), and ask NextPCB for one quote in case its first-order
free-assembly offer covers a design. Budget the first PDM set at about $1,265-1,422 including the 35 % US duty
JLCPCB charges, not $650-850; the only big saving (about $585-670, 41-53 %) is a full in-house or bench build from
bare boards and stencils, which makes sense only if a reflow line with inspection is at hand.

### 7. How the numbers were made, and what was not read

- Fees: section 3.1 table x the counts in section 2 (BOM lines from `hardware/fab/*/*-bom-jlcpcb.csv`, SMD pads and
  through-hole pads counted in the three `.kicad_pcb` files, B assembled x 2). Parts: each JLCPCB BOM line at its
  LCSC price break for the lot, bought at no less than LCSC's smallest quantity.
- Not read (the page did not load for this job): PCBWay's assembly price page, OSH Park's pricing page (its service
  pages above were read instead), Seeed Fusion's PCBA page. No live quote page was used (they need an upload; PCBA
  needs a login).
- Before paying: the live JLCPCB quote replaces every ASSUMED bare-board figure. Every route buys the same 5 + 5 + 5
  bare boards with the same 35 % duty, so a different board price moves every row by about the same amount and
  does not change their order (OSH Park and Aisler rows aside).
