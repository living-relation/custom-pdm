DUMMY TEST COPY - not a source of truth; real source: st185-link-ecu-config/CAN-BUS-ID-ALLOCATION-TABLE.md @ 3df293f2 and CAN-BUS-MASTER-DESIGN.md @ a6f5f328 (sections 6, 8); never use alone to decide a design change (Dan, 2026-11-16)

# ECU -> PDM output control: preliminary plan (L4a, dummy)

carsim (2026-11-23): the ST185 car config (`docs/st185-car-config.dummy.md`) needs NO ECU -> PDM frame: Dan 07:44, the ECU
controls and powers its own loads (pump, EPS, fans, heater, A/C, ETB, injectors, coils) on its own relays. This plan
stays for the starter and for any user who wants ECU-commanded outputs (the /pdm Functions panel, default ID 0x3F4).

Plan only (Dan, 2026-11-16, L4a): nothing built, nothing agreed, no code change. The PDM is unproven theory until
the PCBs are made. IDs and the bus come from `can-id-table.dummy.md`; bus load from `bus-load.dummy.md`.

## Idea

- The Link G4X sends one custom TX stream to the PDM, the same way it already drives the CSB3 low-side outputs on
  0x643 (PCLink aux output -> periodic CAN TX, st185 master design section 8). ID in st185's free range 0x3F2-0x63F.
- All three PDM boards already sit on that bus. Each ECU-switched output uses ONE stock CAN input slot on its own
  board (no hop between boards, unlike a B4 cross-board link): ID = the ECU frame, start bit = byte x 8, length 8,
  operator Equal 1, and the output's trigger = that slot. Stock firmware only (same pattern as the B4 links and the
  A2 fan CAN inputs).
- One byte per command, not one bit: st185 section 8 says per-bit aux mapping in a PCLink custom TX stream is not
  confirmed, and 0x643 uses one byte per output. Not verified for PCLink either way.
- Byte order BigEndian (st185 Rule 2 default; the CAN input has a byte-order setting, and single bytes make it moot).
- The ECU can check each command against the output state it receives (`link_pdm_receive.dummy.*`, msg 3).

## Sample layout (ID 0x3F4, DLC 8, every 50 ms)

| Byte | Content | PDM output |
|---|---|---|
| 0-7 | ECU command 1-8: 1 = on, 0 = off | any one PDM output each (1-24), chosen in the PDM config; none chosen yet |

More than 8 commands: a second frame (0x3F5) with the same layout.

## Behaviour when the ECU frames stop (per link, as B4 / u3c)

| Choice | CAN input slot | Output after the last ECU frame |
|---|---|---|
| Off (B4 default) | time-out on, 1 s (D3a) | off after 1 s |
| Hold | time-out off | keeps its last state |
| On | time-out on, slot Equal 0, output driven by one virtual input "NOT slot" | on after 1 s; also on at power-up until the first frame |

- 1 s = 20 missed frames at 50 ms. Off / Hold outputs stay off at key-on until the ECU's first frame.
- The board's thermal critical hold-off still wins (all outputs off except the exempt fan output).

## Slot use per board (32 CAN inputs each, `NUM_CAN_INPUTS` 32)

| Board | Reserved today | ECU control, max (1 slot per switched output) | Left for B4 links |
|---|---|---|---|
| A1 | none | 8 | 24 or more |
| A2 | CAN inputs 25-28 = fan (A1 / B temperatures) | 7 (OUT2 is the fan) | 21 or more |
| B | none | 8 | 24 or more |

- B4 links take the lowest free slot; ECU links would share the same pool (rule for which end they take: open).
- Virtual inputs: one per "On" link; A2 virtual inputs 12-14 (fan) and 15-16 (load-shed example) stay reserved.

## Bus load and UI

- One frame every 50 ms = 0.27 % of 1 Mbit/s with worst-case stuffing; already in the worst case of
  `bus-load.dummy.md`.
- UI check (AGENTS.md): stock dingoConfig shows and edits every CAN input slot on the per-board pages, so it can be
  set by hand now. The /pdm links panel would need an "ECU frame byte" source next to the 24 inputs (new UI work).

## Open questions for Dan

- Q1 ID: a) 0x3F4 (rec: free, leaves 0x3F2 that st185 names for a cabin-temp frame) b) 0x3F2 c) another free ID.
- Q2 Layout: a) one byte per command, up to 8 per frame (rec, like 0x643) b) one bit per PDM output, 24 bits
  (needs per-bit PCLink TX, not verified) c) bytes plus a PWM duty per output.
- Q3 Rate: a) 50 ms (rec, same as 0x643) b) 20 ms c) 100 ms.
- Q4 Default when ECU frames stop: a) Off after 1 s (rec, same as B4 u3c) b) Hold c) no default, set per output.
- Q5 ECU command plus a PDM input on one output: a) ECU only for those outputs (rec for a first pass) b) either one
  turns it on (one more virtual input per output).
- Q6 Which outputs the ECU switches: list needed from Dan (none chosen here).
- Q7 Real allocation: a) in the st185 ID table once Dan says go (rec; L2 "later in st185") b) keep it only here.
