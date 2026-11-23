namespace domain.CustomPdm;

public record PdmCarId(int First, int Last, string Name);

// DUMMY COPY (not a source of truth) of the used and planned rows of docs/car-can-dummy/can-id-table.dummy.md, itself a
// dummy copy of st185-link-ecu-config CAN-BUS-ID-ALLOCATION-TABLE.md (read only). OnePdmGuardTests keeps the two equal.
// Use (uiguide, 2026-11-23, after carconfig PR #137): a CANBoard is never put on IDs the car already uses (its factory
// base 0x640 is the car's CSB3 switchboard, 0x640-0x643).
public static class PdmCarIds
{
    public static readonly PdmCarId[] Known =
    [
        new(0x3B6, 0x3B6, "Link CAN-Lambda broadcast"),
        new(0x3BE, 0x3BE, "ECU -> CAN-Lambda"),
        new(0x3E8, 0x3E8, "ECU Engine Fast"),
        new(0x3E9, 0x3E9, "ECU Speed / Press / Ign"),
        new(0x3EA, 0x3EA, "ECU Lambda"),
        new(0x3EB, 0x3EB, "ECU Gear / Fuel"),
        new(0x3EC, 0x3EC, "cluster boost map selection"),
        new(0x3ED, 0x3ED, "cluster TC selection"),
        new(0x3EE, 0x3EE, "ECU Engine Protect"),
        new(0x3EF, 0x3EF, "ECU Drive Assist & Status"),
        new(0x3F0, 0x3F0, "ECU Extended Sensors"),
        new(0x3F1, 0x3F1, "ECU IMU & Extended Warnings"),
        new(0x3F4, 0x3F4, "ECU -> PDM output control (planned)"),
        new(0x640, 0x640, "CSB3 switchboard Analog 1-4"),
        new(0x641, 0x641, "CSB3 switchboard Analog 5-8"),
        new(0x642, 0x642, "CSB3 switchboard Rotary / Switch / Heartbeat"),
        new(0x643, 0x643, "CSB3 switchboard output control"),
    ];

    // the first known car ID row that overlaps first..last, or null
    public static PdmCarId? In(int first, int last) => Known.FirstOrDefault(k => k.First <= last && first <= k.Last);
}
