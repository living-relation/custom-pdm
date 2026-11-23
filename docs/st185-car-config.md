DUMMY COPY of the car facts - source: st185-link-ecu-config @ 839be705 (`sot/fuse-relay-map.csv`, `sot/channels.csv`, `docs/harness/circuit-plan.md`, `FUEL-SYSTEM.md`, `CAN-BUS-ID-ALLOCATION-TABLE.md`; read only, nothing written there). The config itself (`ui/examples/st185-car.json`) is the install config Dan approved (c4 = a, 2026-11-23).

# ST185 car config (install config)

What this is: the PDM settings for Dan's ST185, built from the st185 car map. It is the file behind the
"Load the ST185 car config" button on the empty /pdm page. The map lives in `ui/tests/CustomPdm.Tests/St185CarTests.cs`
(`St185Car`); a test keeps the file, the map and the tables below the same. The PDM is unproven until the PCBs are made.

In plain words:
- The PDM takes the loads that the st185 design switches with its own relays and fuses today (POWER box B1, LOGIC
  box B2, trunk block B3): 12 car loads on 12 outputs. Board A2 takes no car load (its OUT2 still runs the box fans).
- The Link ECU keeps the logic it has today (fuel pump prime, fan temperatures, EPS above 400 rpm) and sends the
  PDM one on / off byte per load over CAN. Until the ECU sends that frame, those 4 outputs stay off.
- Lights, horns, the module feeds and the CAN-Lambda follow switch and ignition inputs wired to the PDM.
- Every limit comes from a device preset (`ui/README.md` table), at or under both the output rating and the st185
  fuse that protects that wire today.

## Outputs

PDM numbers: 1-8 = A1 OUT1-8, 9-16 = A2 OUT1-8, 17-24 = B OUT1-8. Connector: `docs/box-connectors.md` (X1 cavity or
B stud riser).

| # | Board output | Connector | Load | Device preset | Limit / inrush | Trigger | At ECU or link loss | Replaces in st185 |
|---|---|---|---|---|---|---|---|---|
| 1 | A1 OUT1 | X1-H | Low beams | LED lamp | 5 A / 15 A 100 ms | IN1 (head / flash) | - (own board) | K-HL relay (LOGIC M1) + HL 15 A |
| 2 | A1 OUT2 | X1-J | High beams | LED lamp | 5 A / 15 A 100 ms | IN2 AND IN1 (only with the head lamps on, as K-HR) | - | K-HR relay (LOGIC M2) + HR 15 A; also feeds the dash high-beam LED |
| 3 | A1 OUT3 | X1-K | DRLs | LED lamp | 5 A / 15 A 100 ms | IN3 AND IN5 AND NOT IN1 (DRL switch, key on, head lamps off) | - | K-DRL relay (LOGIC M8) + RLY-DRL (B5) + DRL 7.5 A |
| 5 | A1 OUT5 | X1-M | Horns | Horn | 7.5 A / 22.5 A 200 ms | IN4 (horn switch) | - | K-HORN relay (LOGIC M3); the HZ 15 A fuse stays for the hazard feed |
| 6 | A1 OUT6 | X1-N | EPS pump enable | ECU / module feed | 5 A / 10 A 100 ms | ECU 0x3F4 byte 3 = 1 | keeps its last state (off at power-up) | K-EPS-EN relay (LOGIC M6) + EPSEN 5 A; drives the pump's C1 enable |
| 7 | A1 OUT7 | X1-P | CSB3 switchboard | ECU / module feed | 5 A / 10 A 100 ms | IN5 (ignition) | - | CSB 5 A (BUS2-5) |
| 8 | A1 OUT8 | X1-R | Centre cluster | ECU / module feed | 5 A / 10 A 100 ms | IN5 (ignition) | - | DEV 5 A (BUS2-6) |
| 17 | B OUT1 | Stud OUT1 | Radiator fan | Radiator fan | 30 A / 100 A 500 ms, soft start 1 s (22 Hz) | ECU 0x3F4 byte 1 = 1 | on 1 s after the frames stop | K-FAN relay (POWER R4) + AMI IN-4 30 A |
| 18 | B OUT2 | Stud OUT2 | Condenser fan | Condenser fan | 30 A / 100 A 500 ms, soft start 1 s (22 Hz) | ECU 0x3F4 byte 2 = 1 | on 1 s after the frames stop | K-FAN2 relay (POWER R5) + AMI IN-5 30 A |
| 19 | B OUT3 | Stud OUT3 | Fuel pump | Fuel pump | 25 A / 100 A 500 ms, open-load 1 A | ECU 0x3F4 byte 0 = 1 | off 1 s after the frames stop | K-FP relay (trunk block B3 K1) + FP 40 A |
| 21 | B OUT5 | X1-B | CAN-Lambda | Heater / resistive, limit lowered | 10 A / 15 A 500 ms | IN5 (ignition, from A1 over CAN) | off 1 s after A1's frames stop | K-ON relay (LOGIC M7) + LAM 10 A (Link: 10 A through an ignition relay; load up to 8.1 A) |
| 22 | B OUT6 | X1-D | A/C clutch | A/C clutch | 10 A / 20 A 200 ms, open-load 1 A | IN15 (A/C amp request) | - | K-ACC relay (LOGIC M5) + ACC 10 A |

Spare (nothing set, output off): 4 (A1 OUT4, X1-L), 9 and 11-16 (A2 OUT1, OUT3-8), 20 (B OUT4, stud OUT4),
23 and 24 (B OUT7, OUT8). 10 = A2 OUT2 = the box fans (factory fan logic, untouched).

Trips: lamps and module feeds 5 trips in all, 1 s apart; horns, pump, clutch, CAN-Lambda 3 trips, 1 s apart; fans
3 trips, 2 s apart (presets). Trip time 50 ms (100 ms for the fans, pump and CAN-Lambda).

## Inputs

Ground-switched inputs: pull-up on and inverted (on = switch to ground). Inputs on an input board (A1 IN3-7, B IN3-10)
also have the per-channel DIP switches: SW1 (10 k pull-up) ON for a ground-switched input, SW2 (10 k pull-down) ON for
ignition. A1 IN1 / IN2 and B IN1 / IN2 sit on the boards themselves (MCU pull only).

| Input | Board input | Connector | Name | Active | Wire in the car (st185) |
|---|---|---|---|---|---|
| IN1 | A1 IN1 | X2-7 | Head / flash (R-Y) | to ground | R-Y IE1-2: light switch HEAD (C15-14) / dimmer FLASH (C15-13) |
| IN2 | A1 IN2 | X2-8 | High / flash (R-W) | to ground | R-W IE1-18: dimmer HIGH / FLASH |
| IN3 | A1 IN3 | X2-9 | DRL switch | to ground | DRL-SW (the old K-DRL coil 85 wire) |
| IN4 | A1 IN4 | X2-10 | Horn switch | to ground | G IE1-19: horn switch C15-10 |
| IN5 | A1 IN5 | X2-11 | Ignition (IG2) | 12 V | B-O J/B1 1H-7 IGN (live at ON and ST) |
| IN15 | B IN1 | X2-23 | A/C clutch request | to ground | A/C amplifier A15 pin 8 (sank the old K-ACC coil 85) |

Not used: IN6, IN7, IN8-14 (all of A2), IN16-24 and the analog inputs 25-27. Signal ground: X2-35 to X2-38.

## ECU CAN (TO CONFIRM when the Link ECU CAN setup is done)

The st185 repo plans no PDM frame yet (its ID table marks 0x3F2-0x63F free). Placeholder used here (the
`docs/car-can-dummy/ecu-pdm-control-plan.dummy.md` sample): ID 0x3F4, 8 bytes, every 50 ms, one byte per command,
1 = on, 0 = off. Integration goes on the ECU side (a PCLink custom TX stream, as the ECU already sends 0x643 to the
CSB3); nothing changes on the cluster.

| Byte | Output | Today in st185 (`sot/channels.csv`) |
|---|---|---|
| 0 | 19 Fuel pump | Link Aux 3 (A19), fuel pump relay coil |
| 1 | 17 Radiator fan | Link Aux 5 (A29), radiator fan relay coil |
| 2 | 18 Condenser fan | Link Ign 5 (B13), condenser fan relay coil |
| 3 | 6 EPS pump enable | Link Ign 6 (B12), EPS enable relay coil (on above about 400 rpm, 1-2 s off-delay: ECU logic) |
| 4-7 | - | free |

If the ECU stream gets another ID or byte order, change it on /pdm (Functions panel, "outputs switched by the ECU"),
Write All, Burn, and regenerate this file (St185CarTests).

## TO CONFIRM

- T1 The ECU frame (above): ID, bytes, 50 ms rate. Until the ECU sends it, the fuel pump, both fans and EPS enable stay
  off: the car cannot run on the PDM before the ECU side is set up.
- T2 Currents to measure on the car: low / high beams (HWSTAR H6054: no published current; the presets allow 5 A per
  output for the pair), the PIAA horn pair (7.5 A output), the fuel pump inrush (`FUEL-SYSTEM.md`: 19 A rated, up to
  25 A, inrush not measured), both fans (30 A fuses, no measured draw). Anything above its limit trips: move it to a
  bigger output (B OUT4 is spare, 31 A).
- T3 A/C amplifier A15 pin 8: st185 wires it as a sink for the K-ACC coil; check that it reads as a switch to ground
  on IN15 with the pull-up and no relay coil on it.
- T4 The DIP switches of input board #1 (A1 IN3-5) as above.

## Stays off the PDM (st185 keeps it)

EFI main relay K-EFI (the ECU holds its own power with it) and what it feeds (coils, injectors, SW12); ETB power
K-ETB (drive-by-wire checks); EPS pump K-EPS (50 A); heater blower (R/B No.4); starter (R/B No.4 + clutch switch);
constant feeds (AM1, AM2, J/B1, dome, alarm, alternator S, RTR); the pop-up raise relay K-POD (it switches a signal to
ground, which a high-side output cannot do); the OEM turn signal flasher, hazard switch, wiper and washer (st185
circuit plan keeps them on the factory parts). ECU signal outputs (boost solenoid, MRS speed, A/C kill, tacho) are
not loads.

## Install in the car

1. Wire the box: X1, X2 and the B stud risers as in the tables above (`docs/box-connectors.md`), battery feed and
   chassis ground on the bosses. Set the input-board DIP switches (Inputs). Take out the relays and fuses each output
   replaces, or leave their seats empty (the st185 harness work is done on the st185 side).
2. Connect: a USB-CAN adapter on the car's CAN bus (1 Mbit/s), key on, start the PDM UI (`ui\Start-PdmUi.ps1 -NoSim`),
   open /pdm.
3. On the empty /pdm page press "Load the ST185 car config". When the PDM is on the bus, /pdm asks once: pick
   "Keep the PC's settings (write them to the PDM)" (that starts Write All), or press Write All. Wait for "written OK"
   on A1, A2 and B (about 6 s each).
4. Press Burn (all three boards answer "burn OK").
5. Power cycle the PDM (key off, PDM feed off, then on). /pdm reads the boards on connect: the Output triggers list
   must show the triggers in the Outputs table.
6. Check the outputs, key on: CSB3 and the centre cluster come on (7, 8), the CAN-Lambda (21); head lamps, high
   beams, DRLs, horns and the A/C clutch on their switches; with the ECU stream running, the fuel pump prime and the
   fans and EPS enable as the ECU commands them. Watch the /pdm fault line: a load that trips needs a bigger output
   (T2).
