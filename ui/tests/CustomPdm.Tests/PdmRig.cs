using application.Services;
using domain.Devices;
using domain.Models;
using Microsoft.Extensions.Logging.Abstractions;

namespace CustomPdm.Tests;

// Route B: the three PC devices (A1 0x500, A2 0x540, B 0x580) in one REAL DeviceManager, on one SimBus.
// The rig does the job of CommsDataPipeline: what DeviceManager queues goes to the bus (2 ms apart, as dingoConfig
// paces it), every frame the boards send goes to DeviceManager.OnCanDataReceived.
public sealed class PdmRig
{
    private readonly SimBus _bus;
    private readonly List<DeviceCanFrame> _pending = [];
    private readonly DateTime _t0 = new(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc);

    public DeviceManager Mgr { get; }
    public FwDevice A1 { get; }
    public FwDevice A2 { get; }
    public FwDevice B { get; }
    public FwDevice[] All => [A1, A2, B];
    public List<string> Notes { get; } = [];
    public List<CanFrame> Sent { get; } = [];
    public double SimMs { get; private set; }
    public DateTime Now => _t0.AddMilliseconds(SimMs);       // sim time as a clock for PdmOps
    public Action<CanFrame>? BeforeSend { get; set; }         // called just before a frame goes to the bus

    public PdmRig(SimBus bus)
    {
        _bus = bus;
        Mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance,
            new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs")), new FwDeviceDefManager());
        Mgr.SetBatchTransmitCallback(batch => { lock (_pending) _pending.AddRange(batch); });
        // same call as the Devices page ("fwD:<type>")
        Mgr.AddDevice("fwD:14", "A1", 0x500);
        Mgr.AddDevice("fwD:14", "A2", 0x540);
        Mgr.AddDevice("fwD:15", "B", 0x580);
        var devs = Mgr.GetDevicesByType<FwDevice>().ToList();
        A1 = devs.Single(d => d.Name == "A1");
        A2 = devs.Single(d => d.Name == "A2");
        B = devs.Single(d => d.Name == "B");
        foreach (var d in devs) d.SuccessNotification += Notes.Add;
    }

    private void Feed(IEnumerable<(int Id, byte[] Data)> frames, double ms)
    {
        SimMs += ms;
        foreach (var (id, data) in frames) Mgr.OnCanDataReceived(new CanFrame(id, data.Length, data));
    }

    // Send what DeviceManager queued (and what the devices answer), then run the bus for ms
    public void Step(double ms = 50)
    {
        while (true)
        {
            List<CanFrame> batch;
            lock (_pending)
            {
                var queued = _pending.Take(64).ToList();
                _pending.RemoveRange(0, queued.Count);
                foreach (var df in queued) Mgr.OnFrameTransmitted(df);   // as CommsDataPipeline does after the adapter
                batch = queued.Select(df => df.Frame).ToList();
            }
            if (batch.Count == 0) break;
            if (BeforeSend == null) { Sent.AddRange(batch); Feed(_bus.Tx(batch), 2 * batch.Count); continue; }
            foreach (var f in batch) { BeforeSend(f); Sent.Add(f); Feed(_bus.Tx([f]), 2); }
        }
        Feed(_bus.Run(ms), ms);
        Mgr.GetDevicesByType<FwDevice>(); // as the pages do on every refresh: updates FwDevice.Connected
    }

    public bool RunUntil(Func<bool> done, int maxMs = 20000)
    {
        var end = SimMs + maxMs;
        while (SimMs < end)
        {
            if (done()) return true;
            Step();
        }
        return done();
    }

    public int CountSent(int baseId, domain.Enums.MessageCommand cmd) =>
        Sent.Count(f => f.Id == baseId + 1 && f.Payload[0] == (byte)cmd);
}
