using domain.Devices;
using domain.Enums;
using domain.Interfaces;

namespace domain.CustomPdm;

// custom-pdm uiguide (2026-11-23, "can a user break the one-PDM feel?"): what keeps A1, A2 and B acting as ONE PDM
// whatever the way in. Each rule closes a way that went through before (driven by hand on the simulated boards;
// docs/ui-setup-guide.md "How the one-PDM feel is protected"; proof OnePdmGuardTests):
// 1. ID clash: a device whose CAN ID block (base .. base + 0x27) overlaps a custom-pdm board's: a second board on the
//    same / an overlapping base ID (an edited project file), or a stock dingoPDM / CANBoard device added on the Devices
//    page at a board's ID. The PC sends neither of them anything (DeviceManager.QueueMessage), /pdm says why and Read All
//    / Write All / Burn are off. Before: the stock device's Write All put stock settings (500K) onto A1; two boards at
//    0x500 were both written to A1, then both read from it.
// 2. CAN bit rate not the same on A1, A2 and B (the Unlock dialog only ever sets one rate for all): Write All / Burn off.
// 3. A board listening to its own ID block (no board hears its own frames): its settings belong to another board, e.g.
//    a file with A1's and A2's base IDs exchanged (that wrote A2's fan logic onto A1's OUT2): Write All / Burn off.
// 4. Critical settings a project file brought that differ from our factory ones (CAN bit rate, critical temperature,
//    outputs kept on at critical): Write All / Burn off until each is set with Unlock (PdmCritical.Apply), board A's
//    temperature put back to factory, or the board is read (Take the PDM's settings). Before: written as they were.
public static class PdmIntegrity
{
    public const int BlockSize = PdmLinked.BlockSize;

    private static bool IsBoard(FwDevice d) => d.CustomPdm != null;
    private static bool Overlap(int a, int b) => a < b + BlockSize && b < a + BlockSize;
    private static string Block(int b) => $"0x{b:X3}-0x{b + BlockSize - 1:X3}";
    private static string Name(FwDevice d) => IsBoard(d) ? d.Name : $"'{d.Name}' (not a custom-pdm board)";

    private static IEnumerable<(FwDevice X, FwDevice Y)> Clashing(IEnumerable<IDevice> devices)
    {
        var list = devices.OfType<FwDevice>().ToList();
        for (var i = 0; i < list.Count; i++)
        for (var j = i + 1; j < list.Count; j++)
            if ((IsBoard(list[i]) || IsBoard(list[j])) && Overlap(list[i].BaseId, list[j].BaseId))
                yield return IsBoard(list[i]) ? (list[i], list[j]) : (list[j], list[i]);
    }

    private static string ClashText(FwDevice x, FwDevice y) =>
        $"{Name(x)} ({Block(x.BaseId)}) and {Name(y)} ({Block(y.BaseId)}) overlap: the PC cannot tell them apart on the bus, " +
        "so it sends neither of them anything (no Read, Write, Burn or other command). Delete the extra device on the Devices " +
        "page, or open a project file where each board has its own base ID.";

    // every clash in the project (shown on /pdm; each blocks Read All, Write All and Burn)
    public static IReadOnlyList<string> IdClashes(IEnumerable<IDevice> devices) =>
        Clashing(devices).Select(p => ClashText(p.X, p.Y)).ToList();

    // why nothing may be sent to the device at baseId (DeviceManager.QueueMessage), or null
    public static string? ClashReason(int baseId, IEnumerable<IDevice> devices) =>
        Clashing(devices).Where(p => Targets(p.X, baseId) || Targets(p.Y, baseId)).Select(p => ClashText(p.X, p.Y)).FirstOrDefault();

    // a frame for this device: its base ID, or base + 1 (the Modify message)
    private static bool Targets(FwDevice d, int id) => id == d.BaseId || id == d.BaseId + 1;

    // one log line per base ID and 5 s (a refused Write All is thousands of frames)
    private static readonly Dictionary<int, DateTime> LastLog = new();

    public static bool LogNow(int baseId, DateTime now)
    {
        lock (LastLog)
        {
            if (LastLog.TryGetValue(baseId, out var t) && now - t < TimeSpan.FromSeconds(5)) return false;
            LastLog[baseId] = now;
            return true;
        }
    }

    // ---- what must be true before Write All / Burn (rules 2-4) ----

    public static IReadOnlyList<string> WriteProblems(PdmView v)
    {
        var list = new List<string>();
        if (!v.Boards.All(b => CustomPdmGuards.ReadOrFactoryNew(b.Device))) return list; // "not read yet" refuses first
        if (v.Boards.Select(b => b.Device.BitRate).Distinct().Count() > 1)
            list.Add($"CAN bit rate differs ({string.Join(", ", v.Boards.Select(b => $"{b.Role} {PdmCritical.RateText(b.Device.BitRate)}"))}): " +
                     "the boards would not hear each other. Set one rate with Unlock (PDM settings, Critical settings).");

        foreach (var b in v.Boards)
        {
            var own = b.Device.CanInputs.Where(c => c.Enabled && !c.Ide && c.Id >= b.Device.BaseId && c.Id < b.Device.BaseId + BlockSize).ToList();
            if (own.Count > 0)
                list.Add($"{b.Role} CAN input {own[0].Number} listens to 0x{own[0].Id:X3}, inside its own ID block ({Block(b.Device.BaseId)})" +
                         (own.Count > 1 ? $" ({own.Count} CAN inputs in all)" : "") +
                         ": a board never hears its own frames, so these settings belong to another board (were two boards' base IDs " +
                         "swapped in the project file?). Take the PDM's settings, or open the right file.");
        }

        list.AddRange(Unconfirmed(v));
        return list;
    }

    // ---- rule 4: critical values a project file brought ----

    private static int Factory(PdmCriticalKind k, FwDevice d, string role) => k switch
    {
        PdmCriticalKind.BitRate => (int)CanBitRate.BitRate1000K,
        PdmCriticalKind.CritTemp => CustomPdmSettings.TempCritDefault(d.DeviceTypeId),
        PdmCriticalKind.KeptOn => role == "A2" ? 1 << PdmFactoryDefaults.FanOutput : CustomPdmSettings.DefaultCritExemptMask,
        _ => 0
    };

    private static readonly PdmCriticalKind[] FileKinds = [PdmCriticalKind.BitRate, PdmCriticalKind.CritTemp, PdmCriticalKind.KeptOn];

    private static int Value(PdmCriticalKind k, FwDevice d) => k switch
    {
        PdmCriticalKind.BitRate => (int)d.BitRate,
        PdmCriticalKind.CritTemp => d.CustomPdm!.TempCrit,
        PdmCriticalKind.KeptOn => d.CustomPdm!.CritExemptMask,
        _ => 0
    };

    private static string Text(PdmCriticalKind k, FwDevice d, string role, int value) => k switch
    {
        PdmCriticalKind.BitRate => $"CAN bit rate {PdmCritical.RateText((CanBitRate)value)}",
        PdmCriticalKind.CritTemp => $"critical temperature {value} C",
        _ => "outputs kept on at critical temperature " + (Enumerable.Range(0, d.Outputs.Count).Where(i => (value >> i & 1) != 0)
            .Select(i => PdmView.OutputNumber(role, i)?.ToString() ?? $"{role} OUT{i + 1}").DefaultIfEmpty("none").Aggregate((a, b) => $"{a}, {b}"))
    };

    // just after a project file was read (PdmProjectFile.MarkLoaded): remember the critical values of each writable board
    // that are not our factory ones
    public static void MarkFileCritical(PdmView v)
    {
        foreach (var b in v.Boards)
        {
            if (b.Device.CustomPdm is not { FromFile: true } c) continue;
            c.FileCritical.Clear();
            if (c.CriticalSeal != null && c.CriticalSeal == PdmProjectFile.Seal(b.Device)) continue; // saved by the app as it was
            foreach (var k in FileKinds)
                if (Value(k, b.Device) != Factory(k, b.Device, b.Role)) c.FileCritical[k] = Value(k, b.Device);
        }
    }

    public static bool HasUnconfirmed(FwDevice d) =>
        !d.FullReadDone && d.CustomPdm is { } c && c.FileCritical.Any(kv => Value(kv.Key, d) == kv.Value);

    // the file's critical values still on the PC and not confirmed (a board read since holds the board's own values)
    public static IReadOnlyList<string> Unconfirmed(PdmView v)
    {
        var list = new List<string>();
        foreach (var b in v.Boards)
        {
            if (b.Device.FullReadDone || b.Device.CustomPdm is not { } c) continue;
            var open = c.FileCritical.Where(kv => Value(kv.Key, b.Device) == kv.Value).Select(kv => Text(kv.Key, b.Device, b.Role, kv.Value)).ToList();
            if (open.Count > 0)
                list.Add($"{b.Role}: {string.Join("; ", open)} from the project file, not our factory value and not set with Unlock: " +
                         "set it with Unlock on PDM settings (board A temperature: Unlock, back to factory), or Take the PDM's settings.");
        }

        return list;
    }

    // the Unlock dialog set kind k (PdmCritical.Apply): the boards it changed hold a confirmed value
    public static void Confirmed(PdmView v, PdmCriticalKind k)
    {
        foreach (var b in v.Boards)
            if (k != PdmCriticalKind.CritTemp || PdmThermal.OffsetK(b.Device) != null)
                b.Device.CustomPdm?.FileCritical.Remove(k);
    }
}
