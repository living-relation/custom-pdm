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
    private Timer? _timer;

    public PdmOps Ops { get; }

    // false in tests: they call Tick themselves with the sim clock
    public bool AutoTick { get; set; } = true;

    public PdmOpsService(DeviceManager deviceManager) : this(deviceManager, null) { }

    public PdmOpsService(DeviceManager deviceManager, Func<FwDevice, bool>? isConnected)
    {
        _deviceManager = deviceManager;
        Ops = new PdmOps(new PdmOpsLinks
        {
            SendReadAll = d => { deviceManager.ReadAllDeviceConfig(d.Guid); return true; },
            SendWriteAll = d => deviceManager.WriteAllDeviceConfig(d.Guid),
            SendBurn = d => deviceManager.BurnSettings(d.Guid),
            SendCheck = d => deviceManager.CheckConfig(d.Guid),
            IsConnected = isConnected ?? (d => d.Connected)
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
