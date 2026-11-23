using domain.CustomPdm;
using domain.Devices;
using domain.Enums;

namespace application.Services;

// custom-pdm uifix2 (2026-11-23): the /pdm Output test (domain/CustomPdm/PdmOutputTest.cs) with its clock. A singleton
// with its own 10 Hz timer, so a test ends and its values go back also when the browser tab is closed. While a test
// runs or its values are not back yet, PdmOps refuses Read All / Write All / Burn (PdmOps.Hold): a Burn would keep
// "always on", a Read All would copy it into the PC. Adapter disconnect (CommsAdapterManager.BeforeDisconnect) and app
// close (ApplicationStopping) call StopNow: the old values are sent before the adapter goes, and sent again when the
// board is next seen (an adapter that was already gone did not carry them).
public sealed class PdmOutputTestRun
{
    public required string Label { get; init; }
    public required string Role { get; init; }
    public required int Number { get; init; }
    public required FwDevice Dev { get; init; }
    public required int Index { get; init; }              // board output, 0-based
    public required PdmOutputTestSaved Saved { get; init; }
    public required DateTime Started { get; init; }
    public DateTime Until { get; set; }
    public DateTime? Ended { get; set; }
    public PdmOutputTestState State { get; set; } = PdmOutputTestState.On;
    public double LastA { get; set; }
    public double PeakA { get; set; }
    public OutState LastState { get; set; }
    public string Why { get; set; } = "";                 // why it ended
    public DateTime? SentAt { get; set; }                 // the restore frames went out
    public bool SendAgain { get; set; }                   // sent while the adapter was going: send once more when back
}

public sealed class PdmOutputTestService : IDisposable
{
    private readonly DeviceManager _mgr;
    private readonly PdmOpsService _pdm;
    private readonly Func<FwDevice, bool> _isConnected;
    private readonly object _lock = new();
    private Timer? _timer;

    public Func<bool> AdapterConnected { get; set; } = () => true;
    public bool AutoTick { get; set; } = true;                               // false in tests: they call Tick
    public TimeSpan Settle { get; set; } = TimeSpan.FromMilliseconds(300);   // after the restore: the board's replies
    public TimeSpan Resend { get; set; } = TimeSpan.FromSeconds(1);          // restore not confirmed: send again
    public Action<TimeSpan> Wait { get; set; } = Thread.Sleep;              // StopNow: let the frames go out

    public PdmOutputTestRun? Active { get; private set; }   // on now, or its values not back yet
    public PdmOutputTestRun? Last { get; private set; }

    public PdmOutputTestService(DeviceManager mgr, PdmOpsService pdm, Func<FwDevice, bool>? isConnected = null)
    {
        _mgr = mgr;
        _pdm = pdm;
        _isConnected = isConnected ?? (d => d.Connected);
        pdm.Ops.Hold = HoldReason;
    }

    // why no PDM run may start now (PdmOps.Hold), or null
    public string? HoldReason()
    {
        var r = Active;
        return r?.State switch
        {
            PdmOutputTestState.On => $"Output test running on {r.Label}: wait until it ends, or press Stop.",
            PdmOutputTestState.Restoring => $"Output test of {r.Label}: its own settings are not back on {r.Role} yet ({r.Why}); " +
                                            "they are sent as soon as the board is there. A power cycle also brings them back (nothing was burned).",
            PdmOutputTestState.Settling => $"Output test of {r.Label}: putting its settings back.",
            _ => null
        };
    }

    // why this output cannot be tested now (the page shows it next to the button), or null
    public string? Check(int number, bool safetyConfirmed)
    {
        if (HoldReason() is { } hold) return hold;
        var view = _pdm.BuildView();
        var row = view.Outputs.FirstOrDefault(o => o.Number == number);
        return PdmOutputTest.Refused(view, row, AdapterConnected(), _pdm.Ops.Busy,
            row != null && _pdm.AutoReader.InSync(row.Device), _isConnected, safetyConfirmed);
    }

    public string? SafetyFunction(int number)
    {
        var view = _pdm.BuildView();
        return view.Outputs.FirstOrDefault(o => o.Number == number) is { } row ? PdmOutputTest.SafetyFunction(view, row) : null;
    }

    // Switches output `number` (PDM-wide, 1-24) on for `seconds` (0.5-10 s). Returns why it was refused, or null.
    public string? Start(int number, double seconds, bool safetyConfirmed, DateTime? now = null)
    {
        lock (_lock)
        {
            if (Check(number, safetyConfirmed) is { } why) return why;
            var t = now ?? DateTime.UtcNow;
            var row = _pdm.BuildView().Outputs.Single(o => o.Number == number);
            var run = new PdmOutputTestRun
            {
                Label = PdmFaults.OutputLabel(row), Role = row.Board, Number = number, Dev = row.Device, Index = row.BoardOutput - 1,
                Saved = new PdmOutputTestSaved(row.Output.Enabled, row.Output.Input), Started = t,
                Until = t + TimeSpan.FromSeconds(PdmOutputTest.Seconds(seconds))
            };
            Active = run;
            Last = run;
            _mgr.SendCustomPdmFrames(PdmOutputTest.OnFrames(run.Dev, run.Index).ToList());
            if (AutoTick) _timer ??= new Timer(_ => SafeTick(), null, 100, 100);
            return null;
        }
    }

    // the Stop button
    public void Stop(DateTime? now = null)
    {
        lock (_lock)
            if (Active is { State: PdmOutputTestState.On } r) End(r, now ?? DateTime.UtcNow, "stopped");
    }

    private void SafeTick()
    {
        try { Tick(); }
        catch (Exception) { /* next tick */ }
    }

    public void Tick(DateTime? now = null)
    {
        lock (_lock)
        {
            var t = now ?? DateTime.UtcNow;
            var r = Active;
            if (r == null)
            {
                _timer?.Dispose();
                _timer = null;
                return;
            }

            if (r.State == PdmOutputTestState.On)
            {
                var o = r.Dev.Outputs[r.Index];
                (r.LastA, r.LastState) = (o.Current, o.State);
                r.PeakA = Math.Max(r.PeakA, o.Current);
                Pin(r);
                if (!AdapterConnected()) End(r, t, "the CAN adapter went away");
                else if (!_isConnected(r.Dev)) End(r, t, $"{r.Role} went offline");
                else if (t >= r.Until) End(r, t, "time up");
            }
            else if (r.State == PdmOutputTestState.Restoring && (r.SentAt == null || t - r.SentAt >= Resend || r.SendAgain))
                Send(r, t);
            else if (r.State == PdmOutputTestState.Settling)
            {
                Pin(r);
                if (t - r.SentAt >= Settle)
                {
                    r.State = PdmOutputTestState.Done;
                    Active = null;
                }
            }
        }
    }

    // The board's reply to each test write sets the PC value to it (stock ParamProtocol): the PC keeps the saved
    // values, so the page, the trigger texts and a later Write All never see the test values.
    private static void Pin(PdmOutputTestRun r)
    {
        var o = r.Dev.Outputs[r.Index];
        (o.Enabled, o.Input) = (r.Saved.Enabled, r.Saved.Input);
    }

    private void End(PdmOutputTestRun r, DateTime t, string why)
    {
        r.Ended = t;
        r.Why = why;
        r.State = PdmOutputTestState.Restoring;
        Send(r, t);
    }

    private void Send(PdmOutputTestRun r, DateTime t)
    {
        Pin(r);
        if (!AdapterConnected()) return;
        var reached = _isConnected(r.Dev) && !r.SendAgain;
        _mgr.SendCustomPdmFrames(PdmOutputTest.RestoreFrames(r.Dev, r.Index, r.Saved).ToList());
        r.SentAt = t;
        r.SendAgain = false;
        if (reached) r.State = PdmOutputTestState.Settling;
    }

    // Adapter disconnect / app close: the old values go out now (the adapter is still there), and once more when the
    // board is next seen, in case the adapter was already gone.
    public void StopNow(string why)
    {
        bool sent;
        lock (_lock)
        {
            var r = Active;
            if (r == null || r.State == PdmOutputTestState.Done) return;
            if (r.State == PdmOutputTestState.On)
            {
                r.Ended = DateTime.UtcNow;
                r.Why = why;
            }

            Pin(r);
            sent = AdapterConnected();
            if (sent)
            {
                _mgr.SendCustomPdmFrames(PdmOutputTest.RestoreFrames(r.Dev, r.Index, r.Saved).ToList());
                r.SentAt = DateTime.UtcNow;
            }

            r.State = PdmOutputTestState.Restoring;
            r.SendAgain = true;
        }

        if (sent) Wait(TimeSpan.FromMilliseconds(200));
    }

    public void Dispose()
    {
        lock (_lock)
        {
            _timer?.Dispose();
            _timer = null;
        }
    }
}
