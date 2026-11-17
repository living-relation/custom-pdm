using System.Globalization;
using System.Text;
using domain.CustomPdm;

namespace CarCanDummy;

// L3a (Dan, 2026-11-16): bus-load estimate for everything on car CAN bus 1 (1 Mbit/s), from the DUMMY ID table
// (docs/car-can-dummy/can-id-table.dummy.md: used rows at their typical / worst cycle, planned rows in the worst case)
// plus the PDM message list (3 boards x NUM_TX_MSGS 38 cyclic msgs, all DLC 8, period CAN_TX_CYCLIC_MSG_DELAY 100 ms;
// typical = the always-sent msgs of DbcExport.MessageComment, worst = all 38 incl. the keypad msgs 24-26).
// Bits per classic standard (11-bit) data frame, Davis et al. 2007 "CAN schedulability analysis: refuted, revisited
// and revised": SOF + ID 11 + RTR + IDE + r0 + DLC 4 + 8n data + CRC 15 = 34 + 8n stuffable bits, + CRC delimiter,
// ACK 2, EOF 7, inter-frame space 3 = 13 more; worst-case stuffing adds floor((34 + 8n - 1) / 4) bits.
// DLC 8: 111 bits, 135 with worst-case stuffing.
public record LoadLine(string Ids, string Name, int Dlc, double FpsTypical, double FpsWorst)
{
    // worst: worst rates with worst-case stuffing; else typical rates without stuffing
    public double BitsPerSecond(bool worst) =>
        (worst ? FpsWorst : FpsTypical) * BusLoadDummy.FrameBits(Dlc, worst);
}

public static class BusLoadDummy
{
    public const string FileName = "bus-load.dummy.md";
    public const double BitRate = 1_000_000;
    public const int PdmCycleMs = 100;    // firmware core/device_config.h CAN_TX_CYCLIC_MSG_DELAY (sleep after each pass)
    public const int PdmDlc = 8;          // every TxMsgN in firmware/boards/custompdm_*/msg.cpp sets DLC 8
    public const double FlagPercent = 50;

    public static int FrameBits(int dlc, bool worstStuffing) =>
        47 + 8 * dlc + (worstStuffing ? (34 + 8 * dlc - 1) / 4 : 0);

    public static bool AlwaysSent(int msg) => DbcExport.MessageComment(msg).Contains("always sent");

    public static List<LoadLine> Lines(IReadOnlyList<IdRow> rows)
    {
        var lines = new List<LoadLine>();
        foreach (var r in rows.Where(r => r.Kind is IdKind.Used or IdKind.Planned))
        {
            if (r.Dlc is not { } dlc) throw new FormatException($"{r.Ids} {r.Name}: no DLC");
            var count = r.Last - r.First + 1;
            double Fps(double? ms) => ms is { } v && v > 0 ? count * r.FramesPerCycle * 1000.0 / v : 0;
            lines.Add(new LoadLine(r.Ids, r.Name + (r.Kind == IdKind.Planned ? " (planned, worst case only)" : ""), dlc,
                r.Kind == IdKind.Planned ? 0 : Fps(r.TypicalMs), Fps(r.WorstMs)));
        }
        foreach (var b in DbcExport.RepoBoards)
        {
            var all = Enumerable.Range(0, CanIdTableDummy.NumTxMsgs).ToList();
            var always = all.Where(AlwaysSent).ToList();
            var optional = all.Except(always).ToList();
            var perMsg = 1000.0 / PdmCycleMs;
            lines.Add(new LoadLine(Ids(b.BaseId, always), $"PDM {b.Node} always-sent msgs {string.Join(", ", always)}", PdmDlc,
                always.Count * perMsg, always.Count * perMsg));
            lines.Add(new LoadLine(Ids(b.BaseId, optional), $"PDM {b.Node} optional msgs {optional.First()}-{optional.Last()} " +
                "(sent only when the function is enabled; keypads 24-26 included)", PdmDlc, 0, optional.Count * perMsg));
        }
        return lines;
    }

    private static string Ids(int baseId, List<int> msgs) =>
        string.Join(", ", Runs(msgs).Select(r => r.a == r.b
            ? $"0x{baseId + DbcExport.CyclicTxOffset + r.a:X3}"
            : $"0x{baseId + DbcExport.CyclicTxOffset + r.a:X3}-0x{baseId + DbcExport.CyclicTxOffset + r.b:X3}"));

    private static IEnumerable<(int a, int b)> Runs(List<int> v)
    {
        for (var i = 0; i < v.Count;)
        {
            var j = i;
            while (j + 1 < v.Count && v[j + 1] == v[j] + 1) j++;
            yield return (v[i], v[j]);
            i = j + 1;
        }
    }

    // Load in percent of 1 Mbit/s: typical rates without stuffing, typical rates with worst-case stuffing, worst case
    public static (double TypicalNominal, double Typical, double Worst) Totals(IReadOnlyList<LoadLine> lines) =>
        (Pct(lines.Sum(l => l.FpsTypical * FrameBits(l.Dlc, false))),
         Pct(lines.Sum(l => l.FpsTypical * FrameBits(l.Dlc, true))),
         Pct(lines.Sum(l => l.BitsPerSecond(true))));

    private static double Pct(double bitsPerSecond) => bitsPerSecond / BitRate * 100.0;

    private static string F(double v, string fmt = "0.##") => v.ToString(fmt, CultureInfo.InvariantCulture);

    public static string Markdown(IReadOnlyList<IdRow> rows)
    {
        var lines = Lines(rows);
        var (nominal, typical, worst) = Totals(lines);
        var sb = new StringBuilder();
        void L(string s = "") => sb.Append(s).Append('\n');
        L(DummySources.Banner($"{DummySources.Repo}/{DummySources.IdTable} via {CanIdTableDummy.FileName}, and firmware/boards/custompdm_*/msg.cpp"));
        L();
        L("# CAN bus 1 load estimate (L3a, dummy)");
        L();
        L("Generated by `dotnet run --project ui/tools/DbcGen` (`ui/tools/CarCanDummy/BusLoadDummy.cs`): do not edit. " +
          $"Inputs: `{CanIdTableDummy.FileName}` (used rows; planned rows in the worst case only) and the PDM message list " +
          $"(3 boards x {CanIdTableDummy.NumTxMsgs} cyclic msgs, DLC {PdmDlc}, every {PdmCycleMs} ms). Bus: 1 Mbit/s, " +
          "classic CAN, 11-bit IDs. Every cycle time marked not verified in the table is an assumption.");
        L();
        L($"- Bits per frame: 47 + 8 x DLC without stuffing, plus floor((34 + 8 x DLC - 1) / 4) for worst-case bit stuffing " +
          $"(DLC 8: {FrameBits(8, false)} / {FrameBits(8, true)} bits; DLC 1: {FrameBits(1, false)} / {FrameBits(1, true)}).");
        L("- Typical: typical cycle times, PDM always-sent msgs only. Worst: worst cycle times, all PDM msgs, planned rows.");
        L("- Not counted: dingoConfig config traffic (only while a PC is connected), PDM CAN outputs (none in our defaults; " +
          "up to 32 user frames per board), keypad node frames, error frames and retransmissions, RealDash (listen only).");
        L();
        L("| IDs | What | DLC | Frames/s typical | Frames/s worst | Load typical % (worst stuffing) | Load worst % |");
        L("|---|---|---|---|---|---|---|");
        foreach (var l in lines)
            L($"| {l.Ids} | {l.Name} | {l.Dlc} | {F(l.FpsTypical, "0.#")} | {F(l.FpsWorst, "0.#")} | " +
              $"{F(Pct(l.FpsTypical * FrameBits(l.Dlc, true)))} | {F(Pct(l.BitsPerSecond(true)))} |");
        L($"| | **Total** | | {F(lines.Sum(l => l.FpsTypical), "0.#")} | {F(lines.Sum(l => l.FpsWorst), "0.#")} | **{F(typical, "0.0")}** | **{F(worst, "0.0")}** |");
        L();
        L($"- Typical load: **{F(typical, "0.0")} %** with worst-case stuffing ({F(nominal, "0.0")} % without stuffing).");
        L($"- Worst-case load: **{F(worst, "0.0")} %**.");
        L(worst > FlagPercent
            ? $"- FLAG: the worst case is above {F(FlagPercent)} %."
            : $"- Flag (above {F(FlagPercent)} %): no, the worst case stays below {F(FlagPercent)} %.");
        return sb.ToString();
    }
}
