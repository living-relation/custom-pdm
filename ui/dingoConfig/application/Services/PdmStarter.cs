using domain.CustomPdm;
using domain.Devices;
using domain.Enums;

namespace application.Services;

// uiwalk (2026-11-21): "Load the ST185 starter" on the empty /pdm page. The starter (ui/examples/st185-starter.json)
// is a DUMMY example built by hand on the simulated boards from docs/car-loads.dummy.md; it is not car data.
// A project file normally counts as "not read" (CustomPdmGuards: its Write All needs a Read All first, and a board
// that connects is read over it). The starter is different on purpose: UiWalkTests proves that its critical settings
// (base IDs, 1000K, temperature limits, fan logic) equal New PDM's factory settings, so it is loaded like a New PDM:
// writable, and a connected board asks "Keep PC settings / Take the board's" instead of being read over it.
public static class PdmStarter
{
    public const string FileName = "st185-starter.json";

    // ui/examples/<file> next to the app's sources (dotnet run from the repo: content root = ui/dingoConfig/web)
    public static string? Find(string startDir)
    {
        for (var dir = new DirectoryInfo(startDir); dir != null; dir = dir.Parent)
        {
            foreach (var rel in new[] { Path.Combine("examples", FileName), Path.Combine("ui", "examples", FileName) })
                if (File.Exists(Path.Combine(dir.FullName, rel))) return Path.Combine(dir.FullName, rel);
        }

        return null;
    }

    // Why a loaded file is not our three boards on their factory IDs and bit rate (null = it is)
    public static string? Problem(IReadOnlyList<FwDevice> devices)
    {
        var view = PdmView.Build(devices);
        foreach (var (role, _, baseId) in PdmFactoryDefaults.Boards)
        {
            var dev = view.Boards.FirstOrDefault(b => b.Role == role)?.Device;
            if (dev == null) return $"{role} is missing.";
            if (dev.BaseId != baseId) return $"{role} is on 0x{dev.BaseId:X3}, not 0x{baseId:X3}.";
            if (dev.BitRate != CanBitRate.BitRate1000K) return $"{role} is not on 1000K.";
        }

        return devices.Count == 3 ? null : "The file holds other devices too.";
    }

    // Replaces the project with the starter. Returns why it was refused, or null.
    public static async Task<string?> LoadAsync(string path, ConfigFileManager files, DeviceManager devices, PdmOps ops)
    {
        if (ops.Busy) return PdmOps.BusyReason;
        var loaded = await files.LoadDevices(path);
        files.NewFile(); // not "the open file": Save must ask for a name, never write into ui/examples
        var boards = loaded?.OfType<FwDevice>().ToList() ?? [];
        if (loaded == null || boards.Count != loaded.Count) return "The starter file could not be read.";
        if (Problem(boards) is { } why) return "The starter file is not a PDM project: " + why;
        devices.ClearDevices();
        devices.AddDevices(loaded);
        foreach (var d in boards) d.CustomPdm!.FactoryNew = true;
        ops.ClearResults();
        return null;
    }
}
