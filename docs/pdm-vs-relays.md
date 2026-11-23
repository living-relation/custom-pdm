# PDM or relays for the ST185: is the PDM worth it? (carsim, 2026-11-23)

Dan's question (2026-11-23): "is the PDM cost effective, saving money and time vs more wiring and relays?" The loads
compared are the 20 car loads of the full-PDM car config (`docs/st185-car-config.dummy.md`, a DUMMY / demo config).
What the ECU controls and powers (fuel pump, EPS, both fans, heater, A/C, ETB, pedal, boost, injectors, coils) is the
same on both sides and not counted (Dan 2026-11-23 07:44): its relays, fuses, boxes and wiring stay as st185 designed.
Prices are USD; "ASSUMED" marks an estimate with no quote behind it.

## Short answer

- **Money: no.** For Dan's car alone the PDM costs about **$1,050-1,450** more than the relays and fuses it replaces
  (about **$110-150**), because most of the relays it replaces are factory parts that are already in the car (free)
  and the st185 POWER / LOGIC / trunk boxes stay anyway for the ECU's loads.
- **Time: no, about even or slightly worse.** Re-terminating about 23 switch wires and adding 4 limit-contact wires
  takes about as long as building the relay seats it saves (table below).
- **Worth it for what money cannot buy with relays:** current reading on every output, fault and trip diagnostics,
  soft start, the pop-ups / DRL / defogger / battery-shed / auto-sleep logic in software instead of relays and diodes,
  one box instead of 7 relays + the retract relay + the flasher, and it is the product Dan is building (an open-source
  alternative to ECUMaster / MoTeC / Link PDMs). Against a bought PDM it is cheap: two ECUMaster PMU16s (16 outputs
  each) would be about $2,700-3,000.

## (a) The PDM route

| Item | Cost | Source |
|---|---|---|
| Boards A1, A2, B assembled by JLCPCB / PCBWay, with spares | $650-850 | `docs/order-checklist.md` order (JLCPCB quote page, 2026-11-23), coordinator figure |
| Enclosure (machined sink and lid, printed parts, fasteners, seals) | $80-200 | ASSUMED (material only: Spark Robotic machining / Dan's printer) |
| Box connectors X1 / X2 (HDP20), contacts, sealing plugs, ring lugs | $40-120 | `docs/box-connectors.md`: "mostly on hand"; contacts $0.88 each (TE 0460-202-2031, st185 BOM, Digi-Key 2026-10-20) x about 60 = $53 |
| Internal box wiring and fans | $20-40 | ASSUMED |
| Car harness changes: about 23 input wires to X2, 20 output wires to X1 / studs, 4 pop-up limit wires, a reverse wire | $60-100 | TXL / M22759 wire about $0.42-1.00 per ft (st185 BOM) x about 150 ft + contacts |
| USB-CAN adapter for setting it up | $0-40 | ASSUMED (the RealDash CANable can be used) |
| **PDM route total** | **about $850-1,350**, plus spares already in the order | |

Install hours (ASSUMED, for one careful builder): box assembly and checks 6-10 h, harness changes 10-16 h, setup on the
bench and in the car 4-6 h: **about 20-32 h**.

## (b) The relay / fuse route for the same 20 loads

What st185 already designed or the car already has, for exactly these loads:

| Load(s) | Relay / fuse route part | Cost | Source |
|---|---|---|---|
| Low beams, high beams | K-HL, K-HR (TE 5-1393292-8) + HL / HR 15 A | 2 x $3.66 + 2 x $2.55 = $12.42 | st185 PROJECT-BOM.csv (Digi-Key 2026-10-20) |
| DRLs + pop-up DRL raise | K-DRL (4-1904124-2, $5.05), K-POD (4-1904124-3, $4.54), RLY-DRL (Song Chuan 301-1C + GEP FRH-A12 holder), D1 / D2 diodes, DRL 7.5 A | about $9.59 + $20-30 + $5 + $2.91 = $37-47 | st185 BOM; RLY-DRL / holder / diodes ASSUMED |
| Horns | K-HORN (4-1904124-3) | $4.54 | st185 BOM |
| CAN-Lambda | K-ON (6-1419137-4) + LAM 10 A | $4.49 + $2.62 = $7.11 | st185 BOM |
| CSB3, cluster | CSB 5 A, DEV 5 A | 2 x $2.61 = $5.22 | st185 BOM |
| Pop-up motors | OEM retract relay R8 + RTR 30 A AMI | $0 + $5.30 | in the car; AMI-40 price as the RTR proxy (st185 BOM) |
| Turn / hazard, tail / park, stop, back-up, wipers, washer, rear defogger, power windows | OEM flasher, taillight relay, defogger relay, wiper switch, power main relay, J/B No.1 fuses | $0 | in the car (st185 keeps them, `docs/harness/circuit-plan.md`) |
| Fuse / relay receptacles, box wire for those seats | about 40 terminals x $0.10-0.25 + wire | $10-15 | st185 BOM |
| **Relay route total** | | **about $110-150** | |

Install hours: the relay seats in the LOGIC box are part of a box st185 builds anyway; the OEM relays are already wired.
For these loads: crimp and seat 7 relays, 7 fuses and their box wires, RLY-DRL and D1 / D2: **about 6-10 h**, plus
the st185 harness runs that exist on both routes.

## (c) What only the PDM gives

- Current on every output (firmware reading within 0.3 % of the model current in s5 car), trips with retries, latched
  faults, open-load flags: a blown lamp, a stalled pop-up or wiper motor, a short is seen and named.
- Soft start and PWM (fans are not on the PDM now, but the outputs can), inrush windows per load type.
- Logic in software: pop-ups without the retract relay, DRL-off-with-head-lamps without RLY-DRL, push on / push off
  defogger, wipers with intermittent and wash wipes, battery shed (defogger at <= 11.8 V for 30 s, back at 12.8 V),
  auto sleep that waits for the ECU's after-run hold, the tail switch and the hazards.
- Fewer parts in the boxes: 7 relays, 7 fuses, the retract relay, K-POD, RLY-DRL, D1 / D2, the flasher, the taillight,
  defogger and power main relays come out; one box with two connectors and studs instead.
- One CAN view of the whole body electrics (status frames 0x500-0x5A7, readable by the ECU or RealDash later).

## What moves the answer

| Assumption | If it changes | Effect |
|---|---|---|
| The ECU's loads stay on its relays (Dan 07:44) | if the pump, fans, EPS enable and A/C moved to the PDM | the PDM would also replace K-FP (HCR150 $48.46), K-FAN, K-FAN2, K-EPS-EN, K-ACC and their fuses (about $90-110 more relays), still not enough to pay for the boards |
| The OEM relays are free | building a car from scratch (no factory relays) | the relay route gains about 8 relays + holders ($60-120) and a flasher ($15-30): still under $300 |
| Board cost $650-850 with spares | a second car / a production run (spares reused, assembly per board falls) | the PDM nears $400-600 per car: closer, still above relays |
| Dan's hours are free | valuing time | the routes are about even on hours; the PDM wins only if the diagnostics save fault-finding later |
| Commercial PDM as the alternative | ECUMaster PMU16 $1,349-1,499 each (ecumasterusa.com), 16 outputs | for 20 loads two are needed: the custom PDM is about half the price |

Verdict in plain words: as a money or time saver for this one car, the PDM does not pay off; the relays are cheap and
mostly already there. It pays off as a feature set (diagnostics, logic, fewer parts) and as the product being built,
and it is far cheaper than a bought PDM with the same output count.
