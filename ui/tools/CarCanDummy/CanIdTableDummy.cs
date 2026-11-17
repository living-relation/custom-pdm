using System.Globalization;
using System.Text.RegularExpressions;
using domain.CustomPdm;

namespace CarCanDummy;

// L2 (Dan, 2026-11-16): the car CAN ID table as a DUMMY TEST COPY (docs/car-can-dummy/can-id-table.dummy.md, hand
// made from st185 CAN-BUS-ID-ALLOCATION-TABLE.md) plus the PDM's own IDs, and the clash check: no PDM ID may share an
// ID with a used or planned row, every PDM ID must sit in a free range of the st185 table, and the PDM rows must be
// exactly what the firmware / DbcExport give (base + 0 config reply, base + 1 config request, base + 2 .. base + 0x27
// status msgs 0-37 incl. the keypad msgs 24-26).
public enum IdKind { Used, Free, Pdm, Planned }

public record IdRow(int First, int Last, string Name, string Path, int? Dlc, double? TypicalMs, double? WorstMs,
    int FramesPerCycle, IdKind Kind, string Note)
{
    public bool Has(int id) => id >= First && id <= Last;
    public bool Overlaps(IdRow o) => First <= o.Last && o.First <= Last;
    public string Ids => First == Last ? $"0x{First:X3}" : $"0x{First:X3}-0x{Last:X3}";
}

public static class CanIdTableDummy
{
    public const string FileName = "can-id-table.dummy.md";
    public const int ConfigTxOffset = 0, ConfigRxOffset = 1;   // firmware core/device_config.h CONFIG_TX_OFFSET / _RX_
    public const int NumTxMsgs = 38;                           // firmware boards/custompdm_*/port.h NUM_TX_MSGS

    private static readonly Regex IdCell = new(@"^(0x[0-9A-Fa-f]{3})(?:\s*-\s*(0x[0-9A-Fa-f]{3}))?$");

    // Table rows: | ID | Name | From -> to | DLC | Typical ms | Worst ms | Frames per cycle | Kind | Note |
    // (ID "0x3B6" or a range "0x3F2-0x63F"; a cycle "event" or "-" = no cyclic frames)
    public static List<IdRow> Parse(string markdown)
    {
        var rows = new List<IdRow>();
        foreach (var line in markdown.Split('\n').Select(l => l.Trim()))
        {
            if (!line.StartsWith("|")) continue;
            var c = line.Trim('|').Split('|').Select(x => x.Trim().Replace("`", "").Replace("**", "")).ToArray();
            var m = IdCell.Match(c[0]);
            if (!m.Success) continue;
            if (c.Length < 9) throw new FormatException($"row '{line}': expected 9 cells");
            var first = Convert.ToInt32(m.Groups[1].Value, 16);
            var last = m.Groups[2].Success ? Convert.ToInt32(m.Groups[2].Value, 16) : first;
            if (last < first) throw new FormatException($"row '{line}': range ends before it starts");
            var kind = Enum.Parse<IdKind>(c[7], ignoreCase: true);
            rows.Add(new IdRow(first, last, c[1], c[2], Int(c[3]), Ms(c[4]), Ms(c[5]), Int(c[6]) ?? 0, kind, c[8]));
        }
        return rows;
    }

    private static int? Int(string s) => int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out var v) ? v : null;
    private static double? Ms(string s) => double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : null;

    // The PDM rows the firmware gives at the repo base IDs (DbcExport.RepoBoards)
    public static List<(int First, int Last, string What)> PdmBlocks() =>
        DbcExport.RepoBoards.SelectMany(b => new[]
        {
            (b.BaseId + ConfigTxOffset, b.BaseId + ConfigTxOffset, $"{b.Node} config reply"),
            (b.BaseId + ConfigRxOffset, b.BaseId + ConfigRxOffset, $"{b.Node} config request"),
            (b.BaseId + DbcExport.CyclicTxOffset, b.BaseId + DbcExport.CyclicTxOffset + NumTxMsgs - 1, $"{b.Node} status msgs 0-{NumTxMsgs - 1}")
        }).ToList();

    public static IEnumerable<int> PdmIds() => PdmBlocks().SelectMany(b => Enumerable.Range(b.First, b.Last - b.First + 1));

    // Empty = no clash. Every problem is one line.
    public static List<string> Check(IReadOnlyList<IdRow> rows)
    {
        var errors = new List<string>();
        var taken = rows.Where(r => r.Kind != IdKind.Free).ToList();
        for (var i = 0; i < taken.Count; i++)
        for (var j = i + 1; j < taken.Count; j++)
            if (taken[i].Overlaps(taken[j]))
                errors.Add($"CLASH {taken[i].Ids} {taken[i].Name} ({taken[i].Kind}) and {taken[j].Ids} {taken[j].Name} ({taken[j].Kind})");

        var free = rows.Where(r => r.Kind == IdKind.Free).ToList();
        var pdmRows = rows.Where(r => r.Kind == IdKind.Pdm).ToList();
        foreach (var id in PdmIds())
        {
            if (!pdmRows.Any(r => r.Has(id))) errors.Add($"PDM ID 0x{id:X3} has no pdm row in the table");
            if (!free.Any(r => r.Has(id))) errors.Add($"PDM ID 0x{id:X3} is not inside a free range of the st185 table");
        }
        foreach (var r in taken.Where(r => r.Kind == IdKind.Planned && !free.Any(f => f.First <= r.First && r.Last <= f.Last)))
            errors.Add($"planned {r.Ids} {r.Name} is not inside a free range");

        var want = PdmBlocks().Select(b => (b.First, b.Last)).OrderBy(x => x).ToList();
        var have = pdmRows.Select(r => (r.First, r.Last)).OrderBy(x => x).ToList();
        if (!want.SequenceEqual(have))
            errors.Add("pdm rows " + string.Join(", ", have.Select(x => $"0x{x.First:X3}-0x{x.Last:X3}")) +
                       " differ from the firmware blocks " + string.Join(", ", want.Select(x => $"0x{x.First:X3}-0x{x.Last:X3}")));
        return errors;
    }
}
