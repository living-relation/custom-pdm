using System.Text.RegularExpressions;
using domain.Devices;

namespace domain.CustomPdm;

// uiwalk (2026-11-21, the real-life walkthrough of /pdm): small texts of the PDM page, kept here so they are tested.
public static partial class PdmPageText
{
    // Why the three buttons are off, one line per different reason. Before: with the adapter off the page said only
    // "Read All is off: ..." although Write All and Burn were off for the same reason.
    public static IReadOnlyList<string> OffLines(string? read, string? write, string? burn)
    {
        var lines = new List<string>();
        foreach (var g in new[] { ("Read All", read), ("Write All", write), ("Burn", burn) }
                     .Where(x => x.Item2 != null).GroupBy(x => x.Item2!))
        {
            var names = g.Select(x => x.Item1).ToList();
            var who = names.Count == 1 ? names[0] : string.Join(", ", names.Take(names.Count - 1)) + " and " + names[^1];
            lines.Add($"{who} {(names.Count == 1 ? "is" : "are")} off: {g.Key}");
        }

        return lines;
    }

    // A board of the project that is not on the bus while the adapter is connected (null = all there, or no adapter:
    // then the "off" lines already say so). Before: only the small chip on the board's card said "Offline".
    public static string? OfflineLine(PdmView view, bool adapterConnected, Func<FwDevice, bool>? isConnected = null)
    {
        isConnected ??= d => d.Connected;
        if (!adapterConnected) return null;
        var off = view.Boards.Where(b => !isConnected(b.Device)).Select(b => b.Role).ToList();
        if (off.Count == 0) return null;
        var all = off.Count == view.Boards.Count;
        return $"{string.Join(", ", off)} {(off.Count == 1 ? "is" : "are")} offline (no CAN messages" +
               (all ? ": check power, the CAN wiring and the bit rate" : "") + "). " +
               $"{(off.Count == 1 ? "Its" : "Their")} outputs and inputs below show the last values received; " +
               "Write All and Burn wait until the PDM is complete.";
    }

    [GeneratedRegex(@"\bIN(\d+)\b")]
    private static partial Regex InRef();

    [GeneratedRegex(@"^(digitalInput|analogInput)\d+$")]
    private static partial Regex StockName();

    // "IN15 AND IN9" -> "IN15 = Ignition, IN9 = Brake switch": the names the user gave the inputs a trigger text
    // mentions (inputs with their stock name are left out). The trigger words themselves stay as they are.
    public static string InputNames(PdmView view, string? words)
    {
        if (string.IsNullOrEmpty(words)) return "";
        var parts = new List<string>();
        foreach (var n in InRef().Matches(words).Select(m => int.Parse(m.Groups[1].Value)).Distinct())
        {
            var name = view.Inputs.FirstOrDefault(i => i.Number == n)?.Name;
            if (!string.IsNullOrWhiteSpace(name) && !StockName().IsMatch(name)) parts.Add($"IN{n} = {name}");
        }

        return string.Join(", ", parts);
    }

    // A board the running Read All / Write All / Burn still has to handle, or is handling, is not asked about until
    // that run ends. Seen on the simulated boards: the board being written drops off the bus for a moment and
    // "connects" again, and the page asked "Keep PC settings / Take the board's" in the middle of its own write.
    public static bool AskNow(string role, bool busy, IReadOnlyList<PdmBoardResult> results) =>
        !(busy && results.Any(r => r.Role == role && r.State is PdmStepState.Running or PdmStepState.Waiting));

    // One question for the PDM when several boards ask at once (New PDM with the three boards on the bus asked
    // three times, once per board).
    // uipolish (2026-11-21): always one question, also for one board and for an opened project file; "Keep" writes.
    public static string ConnectAskText(IReadOnlyList<string> roles, PdmAskKind kind) =>
        (PdmOps.Roles.All(roles.Contains) ? "The PDM is connected. " : $"{string.Join(", ", roles)} connected. ") +
        kind switch
        {
            PdmAskKind.NewPdm => "The PC holds the New PDM settings, not written yet.",
            PdmAskKind.ProjectFile => "The PC holds the settings of the project file; the PDM may hold other ones.",
            _ => "The PC has changes that are not on the PDM yet."
        } +
        " Which settings do you want?";

    public const string KeepPcButton = "Keep the PC's settings (write them to the PDM)";
    public const string TakePdmButton = "Take the PDM's settings";

    // What the PC holds for the boards that ask: a project file, a New PDM, or edits made after a read / write
    public static PdmAskKind AskKind(IReadOnlyList<PdmBoard> asks)
    {
        var fresh = asks.Where(a => !a.Device.FullReadDone).ToList();
        if (fresh.Count != asks.Count || asks.Count == 0) return PdmAskKind.Edits;
        if (fresh.All(a => a.Device.CustomPdm?.FromFile == true)) return PdmAskKind.ProjectFile;
        return fresh.All(a => a.Device.CustomPdm?.FactoryNew == true) ? PdmAskKind.NewPdm : PdmAskKind.Edits;
    }
}

public enum PdmAskKind { NewPdm, ProjectFile, Edits }
