namespace domain.CustomPdm;

// custom-pdm ADR-2026-11-20-temp-onepdm: /pdm keeps ONE temperature set (warn / critical / recovery / critical-soon
// margin), entered as the board hot-spot (laminate) temperature. Each board's firmware compares its limits with its
// own MCP9808 reading, so the tool converts the set per board with that board's sensor -> hot-spot offset:
//   board B: the FEA map of docs/system-verification.md "Board B temperature limits" (tools/thermal_board_b.py +
//            tools/verify_thermal_box.py, 12 cases: car, drive, feed150 / hi / lo, rating; fans on / failed; 60 C
//            cabin; job hwtemp 2026-11-23 with the TI 5 V module loss): at the ORDERED copper (1 oz outer + 1 oz
//            inner, Dan 2026-11-22; tools/copper_order.py), 0.3 mm grid: laminate = U6 + 9.9 .. 20.0 K. Conservative
//            worst case: the largest offset (20.0 K) + the MCP9808 maximum error (+-1 C at -40..125 C, Microchip
//            DS20005095B DC characteristics) = 21 K, so sensor limit = hot spot - 21 K. Board B's factory 98 / 104 C
//            (port_boards.py, ADR-2026-11-20-fwsafety) is the hot-spot set 119 / 125 C.
//   board A: its FEA map since job hwtemp (tools/thermal_a.py, 8 cases: rating, feed150a, car, drive; fans on /
//            failed): laminate = U6 + 14.5 .. 19.8 K, + 1 K sensor error = 20.8, rounded up to 21 K: the same
//            offset as board B, so its factory 98 / 104 C (port_boards.py) is the same hot-spot set 119 / 125 C.
//   tools/verify_thermal_box.py fails when these constants and the maps differ.
//   Sensor critical maximum, both boards: 104 C (ADR-2026-11-20-fwsafety: the MCU beside the sensor, 105 C, at the
//   sensor reading + 1 K; the hwtemp part maps allow 105.2 C on A and 106.7 C on B, bound by the 5 V module).
// Recovery (hysteresis) and the critical-soon margin are differences, the same on the sensor as at the hot spot.
// Everything here is a PC edit: Write All sends it, Burn keeps it.
public record PdmHotSpotLimits(int Warn, int Crit, int Hyst, int Margin);

// One board's sensor limits for a hot-spot set: Converted = from the set (the board has a thermal model), else the
// board's own limits, kept
public record PdmBoardTempRow(string Role, PdmTempLimits Sensor, bool Converted, string Note);

public static class PdmThermal
{
    public const double BoardBLaminateOffsetK = 20.0; // largest laminate - U6 offset of the FEA map (docs/system-verification.md)
    public const double BoardALaminateOffsetK = 19.8; // the same for board A (tools/thermal_a.py, docs/heat-analysis.md 5)
    public const double SensorErrorK = 1.0;           // MCP9808 maximum error (DS20005095B), tools/verify_thermal_box.py SENSOR_ERR
    public static readonly int BoardBOffsetK = (int)Math.Ceiling(BoardBLaminateOffsetK + SensorErrorK);
    public static readonly int BoardAOffsetK = (int)Math.Ceiling(BoardALaminateOffsetK + SensorErrorK);
    public const int LaminateMaxC = 130;              // FR-4 laminate limit, tools/verify_thermal_box.py LAMINATE_C
    // ADR-2026-11-20-fwsafety binding limit: the MCU (STM32F446RET7, 105 C ambient) sits at the sensor reading + 1 K, so
    // each board's sensor critical must stay <= 104 C (the FRAM is a 125 C part since hwtemp)
    public const int BoardBSensorCritMaxC = 104;
    public const int BoardASensorCritMaxC = 104;

    public const string NoModelBoard = "No custom-pdm board in the project: there is no board to convert the hot-spot set for.";

    // sensor -> hot-spot offset in K, null = no thermal model (the board keeps its own limits)
    public static int? OffsetK(domain.Devices.FwDevice d) => d.CustomPdm == null ? null
        : d.DeviceTypeId == 15 ? BoardBOffsetK : d.DeviceTypeId == 14 ? BoardAOffsetK : null;
    private static double LaminateOffsetK(domain.Devices.FwDevice d) => d.DeviceTypeId == 15 ? BoardBLaminateOffsetK : BoardALaminateOffsetK;
    public static int SensorCritMaxC(domain.Devices.FwDevice d) => d.DeviceTypeId == 15 ? BoardBSensorCritMaxC : BoardASensorCritMaxC;

    public static PdmTempLimits ToSensor(PdmHotSpotLimits h, int offset) => new(h.Warn - offset, h.Crit - offset, h.Hyst, h.Margin);
    public static PdmHotSpotLimits FromSensor(PdmTempLimits s, int offset) => new(s.Warn + offset, s.Crit + offset, s.Hyst, s.Margin);

    private static IEnumerable<(PdmBoard Board, int Offset)> Modelled(PdmView v) =>
        v.Boards.Where(b => OffsetK(b.Device) != null).Select(b => (b, OffsetK(b.Device)!.Value));

    public static PdmTempLimits FactoryLimits(domain.Devices.FwDevice d) =>
        new(CustomPdmSettings.TempWarnDefault(d.DeviceTypeId), CustomPdmSettings.TempCritDefault(d.DeviceTypeId),
            CustomPdmSettings.DefaultTempCritHyst, CustomPdmSettings.DefaultTempCritSoonMargin);

    // The PDM's hot-spot set as the PC holds it (from board B, else the first board A); null = no board with a thermal
    // model in the project
    public static PdmHotSpotLimits? Current(PdmView v) =>
        Modelled(v).OrderBy(m => m.Board.Device.DeviceTypeId == 15 ? 0 : 1)
            .Select(m => FromSensor(PdmTempLimits.Of(m.Board.Device)!, m.Offset)).FirstOrDefault();

    // null = the set can be written; else why not
    public static string? Problem(PdmView v, PdmHotSpotLimits h)
    {
        var modelled = Modelled(v).ToList();
        if (modelled.Count == 0) return NoModelBoard;
        foreach (var (b, off) in modelled)
        {
            string Range(string name) =>
                $"{name} must be {CustomPdmSettings.TempMin + off} to {CustomPdmSettings.TempMax + off} C hot spot (board {b.Role} sensor {CustomPdmSettings.TempMin} to {CustomPdmSettings.TempMax} C).";
            var s = ToSensor(h, off);
            if (s.Warn < CustomPdmSettings.TempMin || s.Warn > CustomPdmSettings.TempMax) return Range("Warn");
            if (s.Crit < CustomPdmSettings.TempMin || s.Crit > CustomPdmSettings.TempMax) return Range("Critical");
            if (s.Problem() is { } why) return why; // warn below critical, recovery, margin (the offset keeps their order)
        }
        return null;
    }

    // What each board's sensor limits become (nothing changed)
    public static IReadOnlyList<PdmBoardTempRow> Preview(PdmView v, PdmHotSpotLimits h) =>
        v.Boards.Where(b => b.Device.CustomPdm != null).Select(b => OffsetK(b.Device) is { } off
            ? new PdmBoardTempRow(b.Role, ToSensor(h, off), true,
                FormattableString.Invariant($"sensor = hot spot - {off} K (FEA map: largest laminate offset {LaminateOffsetK(b.Device):0.0} K + {SensorErrorK:0} K sensor error)"))
            : new PdmBoardTempRow(b.Role, PdmTempLimits.Of(b.Device)!, false,
                $"no thermal model yet: keeps its own limits (factory {FactoryLimits(b.Device).Warn} / {FactoryLimits(b.Device).Crit} C)")).ToList();

    // null = written on the PC for every board with a thermal model (board A untouched); else why not (nothing changed)
    public static string? Set(PdmView v, PdmHotSpotLimits h)
    {
        if (Problem(v, h) is { } why) return why;
        foreach (var (b, off) in Modelled(v))
        {
            var s = ToSensor(h, off);
            var c = b.Device.CustomPdm!;
            (c.TempWarn, c.TempCrit, c.TempCritHyst, c.TempCritSoonMargin) = (s.Warn, s.Crit, s.Hyst, s.Margin);
        }
        return null;
    }

    // Allowed but above a rated limit (shown under the field and in the Unlock dialog)
    public static IReadOnlyList<string> RatingNotes(PdmView v, PdmHotSpotLimits h)
    {
        var list = new List<string>();
        if (h.Crit > LaminateMaxC) list.Add($"Critical {h.Crit} C is above the {LaminateMaxC} C laminate limit.");
        foreach (var (b, off) in Modelled(v))
            if (ToSensor(h, off).Crit is var s && s > SensorCritMaxC(b.Device))
                list.Add($"Board {b.Role} sensor critical {s} C is above {SensorCritMaxC(b.Device)} C: the MCU beside the sensor is rated 105 C (ADR-2026-11-20-fwsafety).");
        return list;
    }

    private static string Text(PdmTempLimits t) => $"{t.Warn} / {t.Crit} / {t.Hyst} / {t.Margin}";

    // Boards without a thermal model whose limits are not their factory values (e.g. written by an older /pdm that
    // put one raw set on all three boards)
    public static IReadOnlyList<string> OffFactory(PdmView v) =>
        v.Boards.Where(b => b.Device.CustomPdm != null && OffsetK(b.Device) == null && PdmTempLimits.Of(b.Device) != FactoryLimits(b.Device))
            .Select(b => $"{b.Role} holds {Text(PdmTempLimits.Of(b.Device)!)}, factory {Text(FactoryLimits(b.Device))} (warn / critical / recovery / margin).").ToList();

    // Puts every board without a thermal model back on its own factory limits (critical included: the panel asks
    // through the Unlock dialog first, PdmCritical.RestoreCheck)
    public static void RestoreFactory(PdmView v)
    {
        foreach (var b in v.Boards.Where(b => b.Device.CustomPdm != null && OffsetK(b.Device) == null))
        {
            var f = FactoryLimits(b.Device);
            var c = b.Device.CustomPdm!;
            (c.TempWarn, c.TempCrit, c.TempCritHyst, c.TempCritSoonMargin) = (f.Warn, f.Crit, f.Hyst, f.Margin);
        }
    }
}
