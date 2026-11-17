DUMMY TEST COPY - not a source of truth; real source: st185-link-ecu-config/CAN-BUS-ID-ALLOCATION-TABLE.md @ 3df293f2 (0x3BE from CAN-BUS-MASTER-DESIGN.md @ a6f5f328); never use alone to decide a design change (Dan, 2026-11-16)

# Car CAN bus 1 ID table + custom-pdm IDs (L2, dummy)

Hand-made summary of the st185 master table (section 1) for the custom-pdm checks, plus the PDM's own IDs. The
real table stays in st185 (read only for this project; L2 "later in st185" needs Dan's go). Bus: one bus, 1 Mbit/s.

- Read by `ui/tools/CarCanDummy` (`dotnet run --project ui/tools/DbcGen`): the clash check (`CanIdTableDummy.Check`,
  also `ui/tests` `CarCanDummyTests`) and the bus-load estimate (`bus-load.dummy.md`).
- Kind: `used` = on the bus today (st185), `free` = st185 range marked available, `pdm` = custom-pdm (must match the
  firmware blocks and sit inside a free range), `planned` = proposal only, nothing agreed.
- Cycle "event" or "-" = no cyclic frames. Values marked not verified are assumptions for the bus-load estimate.
- PDM rows: base + 0 config reply, base + 1 config request (dingoConfig), base + 2 .. base + 0x27 status msgs 0-37
  (`firmware/core/device_config.h`, `NUM_TX_MSGS` 38). Bus load for the PDM comes from its msg list, not these rows.

| ID | Name | From -> to | DLC | Typical ms | Worst ms | Frames per cycle | Kind | Note |
|---|---|---|---|---|---|---|---|---|
| 0x3B6 | Link CAN-Lambda broadcast (compound frames 50 and 51) | CAN-Lambda -> ECU | 8 | 50 | 10 | 2 | used | st185: reserved, ~10-20 Hz, module controlled. The manual (section 4.2) states no rate: 20 Hz typical / 100 Hz worst are assumptions, not verified |
| 0x3BE | ECU -> CAN-Lambda (engine speed, exhaust pressure) | ECU -> CAN-Lambda | 8 | 50 | 10 | 1 | used | In the master design section 1 and the lambda manual section 4.3, not a row of the st185 master table. Rate not verified (assumed as 0x3B6) |
| 0x3E8 | Engine Fast | ECU -> cluster | 8 | 10 | 10 | 1 | used | DLC 8 assumed for every Link custom stream (not verified) |
| 0x3E9 | Speed / Press / Ign | ECU -> cluster | 8 | 10 | 10 | 1 | used | |
| 0x3EA | Lambda | ECU -> cluster | 8 | 10 | 10 | 1 | used | |
| 0x3EB | Gear / Fuel | ECU -> cluster, RealDash | 8 | 50 | 50 | 1 | used | |
| 0x3EC | Boost map selection | cluster -> ECU | 1 | event | 100 | 1 | used | Event on a confirmed button press; worst 100 ms is an assumed bound, not verified |
| 0x3ED | TC slip-angle / setting selection | cluster -> ECU | 1 | event | 100 | 1 | used | As 0x3EC |
| 0x3EE | Engine Protect | ECU -> cluster | 8 | 10 | 10 | 1 | used | |
| 0x3EF | Drive Assist & Status | ECU -> RealDash | 8 | 50 | 50 | 1 | used | |
| 0x3F0 | Extended Sensors | ECU -> RealDash | 8 | 100 | 100 | 1 | used | |
| 0x3F1 | IMU & Extended Warnings | ECU -> RealDash | 8 | 50 | 50 | 1 | used | |
| 0x3F2-0x63F | Reserved / available (st185) | - | - | - | - | - | free | st185 names 0x3F2 for a cabin-temp frame if one is ever restored |
| 0x3F4 | ECU -> PDM output control (L4a sample) | ECU -> PDM | 8 | 50 | 50 | 1 | planned | `ecu-pdm-control-plan.dummy.md`; ID, layout and rate are open questions for Dan |
| 0x500 | PDM A1 config reply (base + 0) | A1 -> dingoConfig | 8 | - | - | - | pdm | Only while a PC is connected |
| 0x501 | PDM A1 config request (base + 1) | dingoConfig -> A1 | 8 | - | - | - | pdm | Only while a PC is connected |
| 0x502-0x527 | PDM A1 status msgs 0-37 | A1 -> ECU, A2, B, PC | 8 | 100 | 100 | 1 | pdm | Always: msgs 0-4, 37; the rest only when the function is enabled |
| 0x540 | PDM A2 config reply (base + 0) | A2 -> dingoConfig | 8 | - | - | - | pdm | Only while a PC is connected |
| 0x541 | PDM A2 config request (base + 1) | dingoConfig -> A2 | 8 | - | - | - | pdm | Only while a PC is connected |
| 0x542-0x567 | PDM A2 status msgs 0-37 | A2 -> ECU, A1, B, PC | 8 | 100 | 100 | 1 | pdm | As A1 |
| 0x580 | PDM B config reply (base + 0) | B -> dingoConfig | 8 | - | - | - | pdm | Only while a PC is connected |
| 0x581 | PDM B config request (base + 1) | dingoConfig -> B | 8 | - | - | - | pdm | Only while a PC is connected |
| 0x582-0x5A7 | PDM B status msgs 0-37 | B -> ECU, A1, A2, PC | 8 | 100 | 100 | 1 | pdm | As A1 |
| 0x640 | CSB3 Analog 1-4 (base + 0) | CSB3 -> ECU | 8 | 50 | 50 | 1 | used | CSB3 send rate is user set, default 20 Hz (manual section 5); st185 keeps the default |
| 0x641 | CSB3 Analog 5-8 (base + 1) | CSB3 -> ECU | 8 | 50 | 50 | 1 | used | |
| 0x642 | CSB3 Rotary / Switch / Heartbeat (base + 2) | CSB3 -> ECU | 8 | 50 | 50 | 1 | used | |
| 0x643 | CSB3 low-side output control (base + 3) | ECU -> CSB3 | 8 | 50 | 50 | 1 | used | Periodic PCLink TX stream |
| 0x644-0x7FF | Available (st185: 0x644+ if a second switchboard is added) | - | - | - | - | - | free | |

Not on the bus as a sender: RealDash (Pi USB-CAN adapter, listen only). Side displays are not CAN nodes.
