using domain.CustomPdm;
using domain.Devices;

namespace application.Services;

// custom-pdm route B, phase B2: PdmOps (domain/CustomPdm) wired to the stock DeviceManager calls.
// A singleton with its own 10 Hz timer while a run is active, so a Read All / Write All / Burn of the three boards
// carries on, and keeps its per-board results, when the user leaves the /pdm page.
public class PdmOpsService : IDisposable
{
    private readonly DeviceManager _deviceManager;
    private readonly object _timerLock = new();
    private readonly Func<FwDevice, bool> _isConnected;
    private Timer? _timer;

    public PdmOps Ops { get; }

    // false in tests: they call Tick themselves with the sim clock
    public bool AutoTick { get; set; } = true;

    public PdmOpsService(DeviceManager deviceManager) : this(deviceManager, null) { }

    public PdmOpsService(DeviceManager deviceManager, Func<FwDevice, bool>? isConnected)
    {
        _deviceManager = deviceManager;
        _isConnected = isConnected ?? (d => d.Connected);
        Ops = new PdmOps(new PdmOpsLinks
        {
            SendReadAll = d => { deviceManager.ReadAllDeviceConfig(d.Guid); return true; },
            SendWriteAll = d => deviceManager.WriteAllDeviceConfig(d.Guid),
            SendBurn = d => deviceManager.BurnSettings(d.Guid),
            SendCheck = d => deviceManager.CheckConfig(d.Guid),
            IsConnected = _isConnected
        });
        // frames sent to / config replies from a board (pipeline thread): the Write All wait restarts on them
        deviceManager.ConfigTraffic += Ops.NoteTraffic;
    }

    // GetDevicesByType also refreshes FwDevice.Connected, as on every stock page refresh
    public PdmView BuildView() => PdmView.Build(_deviceManager.GetDevicesByType<FwDevice>());

    public string? BlockedReason(PdmOpKind op, PdmView view, bool adapterConnected) =>
        Ops.BlockedReason(op, view, adapterConnected);

    // Returns why the operation was refused, or null when it started
    public string? Start(PdmOpKind op, bool adapterConnected, DateTime? now = null)
    {
        var refused = Ops.Start(op, BuildView(), adapterConnected, now ?? DateTime.UtcNow);
        if (refused == null && AutoTick)
            lock (_timerLock)
                _timer ??= new Timer(_ => Tick(), null, 100, 100);
        return refused;
    }

    // ---------------- B3 (docs/ui-route-b-plan.md) ----------------

    public const string NewPdmHasBoardsReason =
        "The project already has custom-pdm boards. Start a new project (File > New) or delete them on the Devices page first.";

    // "New PDM" (u2a): adds A1, A2 and B with our firmware's factory defaults (PdmFactoryDefaults). Returns why it was
    // refused, or null when the three devices were added.
    public string? NewPdm()
    {
        if (Ops.Busy) return PdmOps.BusyReason;
        var all = _deviceManager.GetAllDevices().ToList();
        if (all.OfType<FwDevice>().Any(d => d.CustomPdm != null)) return NewPdmHasBoardsReason;
        foreach (var (role, _, baseId) in PdmFactoryDefaults.Boards)
            if (all.FirstOrDefault(d => d.BaseId < baseId + PdmLinked.BlockSize && baseId < d.BaseId + PdmLinked.BlockSize) is { } clash)
                return $"Device '{clash.Name}' (0x{clash.BaseId:X3}) sits in {role}'s factory block 0x{baseId:X3}-0x{baseId + PdmLinked.BlockSize - 1:X3}.";

        foreach (var (role, type, baseId) in PdmFactoryDefaults.Boards)
        {
            var before = _deviceManager.GetAllDevices().Select(d => d.Guid).ToHashSet();
            _deviceManager.AddDevice($"fwD:{type}", role, baseId);
            var dev = _deviceManager.GetDevicesByType<FwDevice>().Single(d => !before.Contains(d.Guid));
            PdmFactoryDefaults.Apply(dev, role);
        }
        return null;
    }

    // Base ID of one board. A base ID is not a Write All value: the board answers on its base ID, so the stock
    // "Modify" message is used (DeviceManager.ModifyDeviceConfig, as on the Devices page): ONE param write to the
    // board's current ID; the board moves at once (running settings only, kept after Burn), then the PC device moves.
    // Before that, A2's fan CAN inputs that listen to this board follow it (PC side: they reach A2 with Write All).
    public (string? Refused, IReadOnlyList<string> Done) ChangeBaseId(string role, int newBase, bool adapterConnected)
    {
        if (Ops.Busy) return (PdmOps.BusyReason, []);
        if (!adapterConnected) return (PdmOps.AdapterOffReason, []);
        var view = BuildView();
        var dev = view.Boards.FirstOrDefault(b => b.Role == role)?.Device;
        if (dev == null) return ($"{role} is not in the project.", []);
        if (newBase == dev.BaseId) return ($"{role} is already on 0x{newBase:X3}.", []);
        if (!_isConnected(dev)) return ($"{role} is offline: the board must hear the change.", []);
        if (PdmLinked.BaseIdProblem(view, role, newBase) is { } why) return (why, []);
        var boards = view.Boards.Select(b => b.Device.Guid).ToHashSet();
        if (_deviceManager.GetAllDevices().FirstOrDefault(d => !boards.Contains(d.Guid)
                && d.BaseId < newBase + PdmLinked.BlockSize && newBase < d.BaseId + PdmLinked.BlockSize) is { } clash)
            return ($"Device '{clash.Name}' (0x{clash.BaseId:X3}) sits in 0x{newBase:X3}-0x{newBase + PdmLinked.BlockSize - 1:X3}.", []);

        var done = new List<string>(PdmLinked.FollowBaseId(view, role, newBase));
        _deviceManager.ModifyDeviceConfig(dev.Guid, dev.Name, newBase);
        done.Insert(0, $"{role} -> 0x{newBase:X3} (sent to the board)");
        return (null, done);
    }

    public void Tick(DateTime? now = null)
    {
        try { _deviceManager.GetDevicesByType<FwDevice>(); }
        catch (InvalidOperationException) { /* device list changed on another thread: next tick */ }
        Ops.Tick(now ?? DateTime.UtcNow);
        if (Ops.Busy) return;
        lock (_timerLock)
        {
            if (Ops.Busy) return;
            _timer?.Dispose();
            _timer = null;
        }
    }

    public void Dispose()
    {
        _deviceManager.ConfigTraffic -= Ops.NoteTraffic;
        lock (_timerLock)
        {
            _timer?.Dispose();
            _timer = null;
        }
    }
}
