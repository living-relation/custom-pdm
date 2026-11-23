DUMMY TEST COPY - not a source of truth; real source: st185-link-ecu-config @ 1bf9f527 (`sot/fuse-relay-map.csv`, `sot/channels.csv`, `docs/harness/circuit-plan.md`, `FUEL-SYSTEM.md`, `cad/fusebox/src/spec.py` fuse ratings); read only, nothing written there; Dan approves any use (Dan, 2026-11-16)
SUPERSEDED for the car config by docs/st185-car-config.dummy.md and ADR-2026-11-23-ecu-loads; kept as the pre-07:44 worst-case load set for the thermal 'car' case

# ST185 car loads for the PDM (parity job, dummy)

What this is: every load the car's st185 design switches today with a relay or a fuse, and which of them the PDM
could take, on which board / output (by current), what controls it, and which PDM features it needs (row numbers
= `docs/feature-parity.md` matrix). The st185 design has no PDM yet: it uses the POWER / LOGIC fuse-relay boxes
(B1 / B2), a trunk relay block (B3) and the OEM boxes. So this is a fit plan to check, not a decision.

PDM outputs (24): board A1 and A2 OUT1-8 7.5 A each (A2 OUT2 = the PDM's own box fans, 1 A, not for the car),
board B OUT1-4 31 A, OUT5-8 15 A (factory limits = ratings, `docs/firmware-pin-map.md` / PR #89). 23 for the car.
Rule used: the fuse rating in st185 is an upper bound; the steady load must sit at or under the output's rating;
loads over 31 A pair two B outputs (row 34) or stay on their relay.

## Loads the PDM can take

| Load (st185 seat, fuse) | Current (source) | PDM board / output | Control source | PDM features needed (matrix rows) |
|---|---|---|---|---|
| Radiator fan (B1 R4 K-FAN, FAN 30 A) | under 30 A (fuse, A17 a) | B OUT1 (31 A) | **ECU CAN** (Link Aux 5 today) | CAN input 22, link-loss "on" 23 / w1, inrush 26, trip time 28 (P1), PWM 15 + soft start 16 optional (fan curve: ECU, or T1 table 14) |
| Condenser fan (B1 R5 K-FAN2, FAN2 30 A) | under 30 A (fuse) | B OUT2 (31 A) | **ECU CAN** (Link Ign 5 today) | 22, 23, 26, 28 |
| Fuel pump (B3 K1 K-FP, FP 40 A) | 19 A rated, up to 25 A, inrush not measured (`FUEL-SYSTEM.md`: measure first) | B OUT3 (31 A); pair B OUT3 + OUT4 (row 34) if the bench shows more | **ECU CAN** (Link Aux 3 today; prime is ECU logic) | 22, link-loss "off" 23 (ECUMaster's example: pump default 0 "for safety", E p.145), 26, 28, open-load flag 31 (P2) |
| CAN-Lambda (B2 M7 K-ON, LAM 10 A) | up to 8.1 A (Link QSG, st185 note) | B OUT5 (15 A) | ignition input (IG2 sense; K-ON coil is J/B1 1H-7 IGN today) | digital input, on-delay 9 optional |
| A/C compressor clutch (B2 M5 K-ACC, ACC 10 A) | clutch coil, under 10 A | B OUT6 (15 A) | wire input: A/C amp A15 pin 8 (low-side drive, so invert) | digital input invert, inrush 26, starter shed 18 |
| Low beams (B2 M1 K-HL, HL 15 A; 2 x HWSTAR H6054 LED) | not published (N84 a); measure | A1 OUT1 (7.5 A) | wire inputs: stalk HEAD / FLASH (R-Y) | logic 1, 4 |
| High beams + dash LED (B2 M2 K-HR, HR 15 A) | not published; measure | A1 OUT2 (7.5 A) | stalk HIGH / FLASH (R-W) AND low beams on | logic 1 |
| DRLs (B2 M8 K-DRL + RLY-DRL, DRL 7.5 A) | about 0.5 A pair (A34 estimate) | A1 OUT3 (7.5 A) | DRL switch AND key on AND NOT low beams (replaces K-DRL, RLY-DRL) | logic 1, 2; open-load flag 31 cannot see 0.24 A on board A (P2 limit) |
| Pop-up raise request (B2 M10 K-POD, signal to R8 pin 8) | signal | A1 OUT4 (7.5 A) | DRL switch AND key on (replaces K-POD) | logic 1 |
| Horn pair (B2 M3 K-HORN, from HZ 15 A) | PIAA Slim pair, under 7.5 A (measure) | A1 OUT5 (7.5 A) | horn switch (C15-10, to ground: invert) | digital input |
| EPS pump enable (B2 M6 K-EPS-EN, EPSEN 5 A) | relay / pump-enable line, under 5 A | A1 OUT6 (7.5 A) | **ECU CAN** (Link Ign 6 today) | 22, 23 |
| Switchboard CSB3 feed (B2 BUS2-5, CSB 5 A) | under 5 A | A1 OUT7 (7.5 A) | ignition input | digital input |
| Centre cluster feed (B2 BUS2-6, DEV 5 A) | under 5 A | A1 OUT8 (7.5 A) | ignition input | digital input, off-delay 9 optional |
| Turn signals L / R (OEM flasher + hazard switch, HZ 15 A) | LED leads 0.2 A + bumper / side lamps | A2 OUT1 / OUT3 (7.5 A) | stalk L / R, hazard switch | flasher 10, logic; lamp-out warning needs P2 (open load 31) |
| Wiper motor run / high (OEM, on the driver fender run) | motor run under 15 A (stall higher: measure) | B OUT7 / OUT8 (15 A) | wiper switch positions + park cam input | wiper 17, inrush 26, trip time 28 (P1) |
| Washer pump (OEM, front run) | under 7.5 A | A2 OUT4 (7.5 A) | washer switch | wiper wash 17 |
| Spare | - | B OUT4 (or fuel-pump pair), A2 OUT5-8 | - | - |

Starter interlock (row 18): the start request (ST1 tap, R/B No.4 pin 1, wired to Link DI 7 today) as a PDM input can
shed the lamps, fans and A/C clutch while cranking. The starter itself stays on the OEM relay through the clutch
switch C11 (st185 circuit 2).

## Loads that stay off the PDM (and why)

| Load | Why not the PDM |
|---|---|
| EFI main relay K-EFI (EFI 30 A; Link Aux 6 holds it) and what it feeds (coils COP 10 A, injectors INJ 7.5 A, ECU switched 12 V SW12 5 A) | the ECU powers itself through it (power hold); it must not depend on the PDM or on CAN. Possible later with an ignition input, not in a first fit |
| ETB power relay K-ETB (ETB 7.5 A; Link Aux 2) | drive-by-wire safety: Link's ETB checks own this relay |
| EPS pump K-EPS (EPS 50 A, HCR150) | above one 31 A output; pairing two B outputs (62 A) is possible but not needed: the PDM switches its enable (row above) |
| Heater blower (R/B No.4 heater relay, 40 A) | OEM A/C amp logic and relay stay (st185 circuit 9) |
| Starter (R/B No.4) | OEM relay + clutch switch C11 in hardware (circuit 2) |
| AM1 40 A, AM2 30 A, J/B1 60 A, LOGIC Bus 1 50 A, dome 20 A, alarm 5 / 2 / 2 A, alternator S 2 A, pop-up feed RTR 30 A | constant feeds: in sleep every PDM output is off (row 38), so anything that must work with the key off stays on a fuse |
| Boost solenoid (Link Aux 1), MRS speed out (Aux 7), A/C ACT kill (Aux 4), tacho (Ign 8) | ECU signal outputs, not loads |

## ECU-switched outputs (answers k5 from the car docs)

The Link G4X drives these relay coils today (`sot/channels.csv`): Aux 2 ETB power, Aux 3 fuel pump, Aux 5 radiator
fan, Aux 6 EFI main, Ign 5 condenser fan, Ign 6 EPS enable. Default for the PDM (from the table above): the ECU
switches **4 PDM outputs over CAN: fuel pump (B OUT3), radiator fan (B OUT1), condenser fan (B OUT2), EPS enable
(A1 OUT6)**; EFI main and ETB power stay on their relays. Each takes one CAN input slot on its board
(`docs/car-can-dummy/ecu-pdm-control-plan.dummy.md`); with BigEndian bytes the start bit is byte x 8 + 7
(`docs/feature-parity.md`, "Found").

## Inputs the PDM would need

Ignition (IG2 sense), start request (ST1), stalk HEAD / FLASH (R-Y), HIGH (R-W), DRL switch, horn switch, A/C amp
clutch request (A15 pin 8), turn L / R, hazard switch, wiper switch (slow / fast / intermittent), wiper park cam,
washer switch: 14 of the 24 digital inputs (the stalk / switch lines go to ground: input-board DIP pull-up + invert).
