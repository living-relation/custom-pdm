using System.Globalization;
using domain.Enums;

namespace domain.CustomPdm;

// custom-pdm one-PDM editor, phase 1 (DECISIONS 2026-11-16 p1 / p3): the critical settings are read-only on /pdm and
// change only through Unlock + type the new value + type it again + Change (PdmCriticalDialog.razor). The Advanced
// screen refuses them (PdmEngine.IsCritical). A wrong value stops the boards talking (base ID, CAN bit rate) or the
// thermal shutdown (critical temperature, outputs kept on at critical temperature).
// - Base ID: one board; moves at once with the stock Modify message (PdmOpsService.ChangeBaseId, checks PdmLinked).
// - CAN bit rate, kept-on outputs: one value for the PDM, set on all three boards (PC edit: Write All sends it, Burn
//   keeps it). Critical temperature: one hot-spot value for the PDM, converted per board (ADR-2026-11-20-temp-onepdm,
//   PdmThermal: each board's sensor = hot spot - its offset, 21 K on A and B since hwtemp).
public enum PdmCriticalKind { BaseId, BitRate, CritTemp, KeptOn }

// Board = "" for a PDM-wide setting
public record PdmCriticalItem(PdmCriticalKind Kind, string Board, string Label, string Current, string Hint, string Risk);

public static class PdmCritical
{
    public static readonly CanBitRate[] BitRates = [CanBitRate.BitRate1000K, CanBitRate.BitRate500K, CanBitRate.BitRate250K, CanBitRate.BitRate125K];

    public static string RateText(CanBitRate r) => r.ToString().Replace("BitRate", "");

    private static string Differs<T>(PdmView v, Func<domain.Devices.FwDevice, T> get, Func<T, string> show)
    {
        var vals = v.Boards.Select(b => (b.Role, Val: get(b.Device))).ToList();
        return vals.Select(x => x.Val).Distinct().Count() <= 1
            ? vals.Count == 0 ? "" : show(vals[0].Val)
            : "differs: " + string.Join(", ", vals.Select(x => $"{x.Role} {show(x.Val)}"));
    }

    // PDM output numbers kept on at critical temperature (the exempt-from-shutdown masks of the three boards)
    public static IReadOnlyList<int> KeptOn(PdmView v) =>
        v.Outputs.Where(o => o.Device.CustomPdm is { } c && (c.CritExemptMask >> (o.BoardOutput - 1) & 1) != 0).Select(o => o.Number).ToList();

    private static string KeptOnText(PdmView v) => KeptOn(v) is { Count: > 0 } k ? string.Join(", ", k) : "none";

    public static IReadOnlyList<PdmCriticalItem> Items(PdmView v)
    {
        var list = v.Boards.Select(b => new PdmCriticalItem(PdmCriticalKind.BaseId, b.Role, $"{b.Role} base ID", $"0x{b.Device.BaseId:X3}",
            "hex, e.g. 600 or 0x600", "the board moves at once; the other boards, the ECU and the DBC must follow")).ToList();
        if (v.Boards.Count == 0) return list;
        list.Add(new PdmCriticalItem(PdmCriticalKind.BitRate, "", "CAN bit rate (all boards)", Differs(v, d => d.BitRate, RateText),
            string.Join(", ", BitRates.Select(RateText)), "every device on the bus (ECU, dash, this PC adapter) must use the same rate, or nothing talks"));
        // custom-pdm ADR-2026-11-20-temp-onepdm: one hot-spot value, converted per board (PdmThermal)
        list.Add(new PdmCriticalItem(PdmCriticalKind.CritTemp, "", "Critical hot-spot temperature, all outputs off", CritTempText(v), CritTempHint(v),
            "too high: the boards can overheat; too low: outputs drop while driving"));
        list.Add(new PdmCriticalItem(PdmCriticalKind.KeptOn, "", "Outputs kept on at critical temperature", KeptOnText(v),
            "output numbers, e.g. 10, 17 (or none)", "these outputs keep running when the board is too hot (the fans, output 10, should)"));
        return list;
    }

    private static int? ParseTemp(string s) => int.TryParse(s.Trim().TrimEnd('C', 'c').Trim(), out var t) ? t : null;

    private static string CritTempText(PdmView v) => PdmThermal.Current(v) is { } h
        ? $"{h.Crit} C hot spot ({string.Join("; ", PdmThermal.Preview(v, h).Select(r => $"{r.Role} sensor {r.Sensor.Crit} C{(r.Converted ? "" : ", kept")}"))})"
        : Differs(v, d => d.CustomPdm?.TempCrit ?? 0, t => $"{t} C sensor");

    private static string CritTempHint(PdmView v)
    {
        var off = v.Boards.Select(b => PdmThermal.OffsetK(b.Device)).FirstOrDefault(o => o != null);
        if (PdmThermal.Current(v) is not { } h || off is null) return "no custom-pdm board in the project";
        return $"hot spot, whole C, {Math.Max(h.Warn + 1, CustomPdmSettings.TempMin + off.Value)} to {CustomPdmSettings.TempMax + off.Value} (above warn {h.Warn} C)";
    }

    // What a valid typed value does to each board (shown in the Unlock dialog); empty for an invalid value
    public static IReadOnlyList<string> Notes(PdmView v, PdmCriticalKind k, string typed)
    {
        if (k != PdmCriticalKind.CritTemp || Problem(v, k, "", typed) != null) return [];
        var h = PdmThermal.Current(v)! with { Crit = ParseTemp(typed)!.Value };
        return PdmThermal.Preview(v, h).Select(r => r.Converted
                ? $"{r.Role} sensor critical becomes {r.Sensor.Crit} C"
                : $"{r.Role} sensor critical stays {r.Sensor.Crit} C (no thermal model yet)")
            .Concat(PdmThermal.RatingNotes(v, h)).ToList();
    }

    // Board A back on its factory limits (PdmThermal.RestoreFactory) goes through the same dialog: type "factory"
    public static string? RestoreCheck(string typed) =>
        typed.Trim().Equals("factory", StringComparison.OrdinalIgnoreCase) ? null : "Type factory to confirm.";

    public static string Normal(string s) => s.Trim().Replace(" ", "").ToUpperInvariant();

    private static int? Hex(string s)
    {
        s = s.Trim();
        if (s.StartsWith("0x", StringComparison.OrdinalIgnoreCase)) s = s[2..];
        return s.Length is > 0 and <= 3 && int.TryParse(s, NumberStyles.HexNumber, null, out var x) ? x : null;
    }

    public static CanBitRate? ParseRate(string s)
    {
        var n = Normal(s).Replace("KBIT/S", "K").Replace("KBPS", "K").Replace("1M", "1000K");
        if (!n.EndsWith('K')) n += "K";
        return BitRates.Cast<CanBitRate?>().FirstOrDefault(r => RateText(r!.Value) == n);
    }

    public static IReadOnlyList<int>? ParseOutputs(string s)
    {
        var n = s.Trim();
        if (n.Equals("none", StringComparison.OrdinalIgnoreCase) || n == "") return [];
        var list = new List<int>();
        foreach (var part in n.Split([',', ';', ' '], StringSplitOptions.RemoveEmptyEntries))
        {
            if (!int.TryParse(part, out var x)) return null;
            list.Add(x);
        }
        return list.Distinct().Order().ToList();
    }

    // null = typed is a valid new value; else why not
    public static string? Problem(PdmView v, PdmCriticalKind k, string board, string typed)
    {
        switch (k)
        {
            case PdmCriticalKind.BaseId:
                if (Hex(typed) is not { } b) return "Type a hex ID, e.g. 600 or 0x600.";
                if (v.Boards.FirstOrDefault(x => x.Role == board) is not { } q) return $"No {board} in the project.";
                if (b == q.Device.BaseId) return "That is the base ID it has now.";
                return PdmLinked.BaseIdProblem(v, board, b);
            case PdmCriticalKind.BitRate:
                return ParseRate(typed) == null ? $"Type one of {string.Join(", ", BitRates.Select(RateText))}." : null;
            case PdmCriticalKind.CritTemp:
                if (ParseTemp(typed) is not { } t) return "Type a whole number of degrees C.";
                if (PdmThermal.Current(v) is not { } now) return PdmThermal.NoModelBoard;
                return PdmThermal.Problem(v, now with { Crit = t });
            case PdmCriticalKind.KeptOn:
                if (ParseOutputs(typed) is not { } outs) return "Type output numbers separated by commas (e.g. 10, 17), or none.";
                return outs.FirstOrDefault(n => v.Outputs.All(o => o.Number != n)) is var bad and > 0
                    ? $"Output {bad} is not in this PDM (1-24, its board must be in the project)." : null;
        }
        return "Unknown setting.";
    }

    // Applies a PDM-wide setting on the PC (all boards). null = done; else why not (nothing changed). Base IDs move a
    // board at once and go through PdmOpsService.ChangeBaseId instead.
    public static string? Apply(PdmView v, PdmCriticalKind k, string typed)
    {
        if (k == PdmCriticalKind.BaseId) return "A base ID moves the board at once: use PdmOpsService.ChangeBaseId.";
        if (Problem(v, k, "", typed) is { } why) return why;
        switch (k)
        {
            case PdmCriticalKind.BitRate:
                foreach (var b in v.Boards) b.Device.BitRate = ParseRate(typed)!.Value;
                break;
            case PdmCriticalKind.CritTemp:
                return PdmThermal.Set(v, PdmThermal.Current(v)! with { Crit = ParseTemp(typed)!.Value });
            case PdmCriticalKind.KeptOn:
                var outs = ParseOutputs(typed)!;
                foreach (var b in v.Boards.Where(b => b.Device.CustomPdm != null))
                    b.Device.CustomPdm!.CritExemptMask = v.Outputs.Where(o => o.Board == b.Role && outs.Contains(o.Number))
                        .Aggregate(0, (m, o) => m | 1 << (o.BoardOutput - 1));
                break;
        }
        return null;
    }
}
