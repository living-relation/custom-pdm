using domain.Devices;

namespace domain.CustomPdm;

// custom-pdm route B, phase B2 (docs/ui-route-b-plan.md): ONE Read All / Write All / Burn for the three boards.
// - Boards are handled one after another (A1, A2, B). The next board starts only after the board before gave its
//   real result: the stock "... Successful" notification of FwDevice plus, for read and write, a config CRC check
//   reply that matches (FwDevice.ConfigMismatch false). No reply in time = failed.
// - Write All and Burn are refused unless A1, A2 and B are all in the project, connected and read in this session
//   (FwDevice.FullReadDone), or come from "New PDM" (B3, CustomPdmGuards.ReadOrFactoryNew). A failure stops a
//   Write All / Burn run: later boards are left alone and every board
//   keeps its own result line, so it is visible that the boards are on different settings.
// - Burn is never started by a read or a write. It first asks every board for a fresh config CRC check; one
//   mismatch (or no reply) and nothing is burned. The firmware answers a burn with its own result
//   (comms/request_msg.cpp: cmd 30, byte 4 = WriteConfig()), dingoConfig turns only result 1 into "Burn Successful".
// - Read All goes on to the next board after a failure (a read changes nothing on a board).
// The class sends nothing itself: the stock DeviceManager calls come in through PdmOpsLinks. Time comes in through
// Start / Tick, so tests can run it against the firmware sim clock.
public enum PdmOpKind { ReadAll, WriteAll, Burn }

public enum PdmStepState { Waiting, Running, Ok, Failed, NotDone }

public record PdmBoardResult(string Role, PdmStepState State, string Text);

public record PdmEarlierRun(PdmOpKind Op, IReadOnlyList<PdmBoardResult> Results);

public class PdmOpsLinks
{
    public required Func<FwDevice, bool> SendReadAll { get; init; }   // false = not sent
    public required Func<FwDevice, bool> SendWriteAll { get; init; }
    public required Func<FwDevice, bool> SendBurn { get; init; }
    public required Action<FwDevice> SendCheck { get; init; }         // config CRC check request
    public Func<FwDevice, bool> IsConnected { get; init; } = d => d.Connected;
}

public class PdmOps(PdmOpsLinks links)
{
    public static readonly string[] Roles = ["A1", "A2", "B"];

    public const string AdapterOffReason = "CAN adapter not connected.";
    public const string BusyReason = "Another PDM operation is still running.";
    public const string NoBoardReason = "No custom-pdm board is connected.";

    // Measured against the firmware sim (ui/tests PdmLiveSimTests output, about 2500 params per board, frames 2 ms
    // apart): Read All of one board about 0.6 s, Write All about 5 s. Through the real-time SLCAN TCP sim bridge
    // (ui/README.md) one Write All took 41 s per board until 2026-11-21: the SLCAN adapter's Thread.Sleep(2) between
    // frames lasts 15.6 ms on Windows (PdmPacer.cs). Now about 5.6 s per board through the bridge, as on a real board.
    // So the write has no fixed wait (b3a, 2026-11-16): the wait restarts on every frame the PC actually sends to
    // that board and on every config-channel reply from it (NoteTraffic), and the board fails WriteIdleTimeout after
    // the last of those. WriteMaxTimeout caps one board's write in any case.
    // DeviceManager re-sends an unanswered Write All / Burn request once after 3 s, so the write idle wait and the
    // burn wait must stay past 6 s.
    public TimeSpan ReadTimeout { get; set; } = TimeSpan.FromSeconds(10);
    public TimeSpan WriteIdleTimeout { get; set; } = TimeSpan.FromSeconds(10);
    public TimeSpan WriteMaxTimeout { get; set; } = TimeSpan.FromMinutes(5);
    public TimeSpan CheckTimeout { get; set; } = TimeSpan.FromSeconds(3);
    public TimeSpan BurnTimeout { get; set; } = TimeSpan.FromSeconds(8);

    private enum StepKind { Read, Write, Check, Burn }

    private sealed class Step(string role, FwDevice dev, StepKind kind)
    {
        public string Role { get; } = role;
        public FwDevice Dev { get; } = dev;
        public StepKind Kind { get; } = kind;
        public volatile bool Acked;
        public Action<string>? Handler;
        public DateTime Started;        // write: the last traffic with this board
        public DateTime Begun;
        public volatile bool Traffic;   // set by NoteTraffic (pipeline thread), turned into Started by Tick
    }

    private volatile Step? _current;

    private readonly object _lock = new();
    private readonly List<Step> _steps = [];
    private readonly Dictionary<string, PdmBoardResult> _results = new();
    private int _index;

    public bool Busy { get; private set; }
    public PdmOpKind? LastOp { get; private set; }
    public bool LastOnConnect { get; private set; } // the last run was a read on connect (PdmAutoRead)

    // uiwalk (2026-11-21): the Write All / Burn the user pressed, kept when a read on connect that follows it takes
    // over the result lines (a slow bus drops a board for a moment during a long write, and the page then showed
    // only "Read on connect: read OK"). Gone with the next run the user starts.
    public PdmEarlierRun? Earlier { get; private set; }

    // uiwalk: the board in work and how long it has been at it (a Write All shows no other progress)
    public (string Role, TimeSpan For)? Running(DateTime now)
    {
        var step = _current;
        return Busy && step != null ? (step.Role, now - step.Begun) : null;
    }

    public static string ElapsedText(TimeSpan t) =>
        t.TotalSeconds < 60 ? $"{Math.Max(0, (int)t.TotalSeconds)} s" : $"{(int)t.TotalMinutes} min {t.Seconds:00} s";

    // uiwalk: a new project (New PDM, file open) must not show the result lines of the boards of the project before
    public bool ClearResults()
    {
        lock (_lock)
        {
            if (Busy) return false;
            _results.Clear();
            LastOp = null;
            LastOnConnect = false;
            Earlier = null;
            return true;
        }
    }

    // One line per board (A1, A2, B) for the last operation
    public IReadOnlyList<PdmBoardResult> Results
    {
        get
        {
            lock (_lock) return Roles.Where(_results.ContainsKey).Select(r => _results[r]).ToList();
        }
    }

    // Why an operation must not start (null = allowed). The text names every board that is in the way, and why.
    public static string? BlockedReason(PdmOpKind op, PdmView view, bool adapterConnected,
        Func<FwDevice, bool>? isConnected = null)
    {
        isConnected ??= d => d.Connected;
        if (!adapterConnected) return AdapterOffReason;
        // uiguide (PdmIntegrity rule 1): two devices on one ID block get nothing, not even a Read All
        if (view.Blocking.Count > 0) return string.Join(" ", view.Blocking);
        if (op == PdmOpKind.ReadAll)
            return view.Boards.Any(b => isConnected(b.Device)) ? null : NoBoardReason;

        var why = new List<string>();
        foreach (var role in Roles)
        {
            var dev = view.Boards.FirstOrDefault(b => b.Role == role)?.Device;
            if (dev == null) why.Add($"{role}: not in the project");
            else if (!isConnected(dev)) why.Add($"{role}: offline");
            else if (!CustomPdmGuards.ReadOrFactoryNew(dev)) why.Add($"{role}: not read yet (Read All first)");
            // Burn: FwDevice.ConfigMismatch is NOT looked at here. It is only as fresh as the last check (an edit on
            // the PC does not change it), so the burn run asks every board for a fresh check first.
        }

        var refused = why.Count == 0 ? null : string.Join("; ", why) + ".";
        // uiguide (PdmIntegrity rules 2-4): settings that would make the boards stop acting as one PDM
        var integrity = PdmIntegrity.WriteProblems(view);
        return integrity.Count == 0 ? refused : string.Join(" ", new[] { refused }.Concat(integrity).Where(s => s != null));
    }

    public string? BlockedReason(PdmOpKind op, PdmView view, bool adapterConnected) =>
        Busy ? BusyReason : BlockedReason(op, view, adapterConnected, links.IsConnected);

    // Starts the operation on the boards of this view. Returns why it was refused, or null when it started.
    // onConnect (p2a, PdmAutoRead): a Read All of just these roles, the boards that have just connected. The result
    // lines of the other boards stay when the run before was a Read All too.
    public string? Start(PdmOpKind op, PdmView view, bool adapterConnected, DateTime now,
        IReadOnlyCollection<string>? onConnect = null)
    {
        lock (_lock)
        {
            if (onConnect != null && op != PdmOpKind.ReadAll) throw new ArgumentException("only a Read All runs on connect");
            if (BlockedReason(op, view, adapterConnected) is { } blocked) return blocked;

            _steps.Clear();
            if (onConnect == null) Earlier = null;
            else if (!LastOnConnect && LastOp is PdmOpKind.WriteAll or PdmOpKind.Burn && _results.Count > 0)
                Earlier = new PdmEarlierRun(LastOp.Value, Roles.Where(_results.ContainsKey).Select(r => _results[r]).ToList());
            if (onConnect == null || LastOp != PdmOpKind.ReadAll) _results.Clear();
            var boards = Roles.Select(r => view.Boards.FirstOrDefault(b => b.Role == r))
                .Where(b => onConnect == null || (b != null && onConnect.Contains(b.Role))).ToList();
            if (onConnect == null)
                foreach (var role in Roles.Where(r => view.Boards.All(b => b.Role != r)))
                    _results[role] = new PdmBoardResult(role, PdmStepState.NotDone, "not in the project");
            LastOnConnect = onConnect != null;

            if (op == PdmOpKind.Burn)
                _steps.AddRange(boards.Where(b => b != null).Select(b => new Step(b!.Role, b.Device, StepKind.Check)));
            var kind = op switch { PdmOpKind.ReadAll => StepKind.Read, PdmOpKind.WriteAll => StepKind.Write, _ => StepKind.Burn };
            _steps.AddRange(boards.Where(b => b != null).Select(b => new Step(b!.Role, b.Device, kind)));
            foreach (var step in _steps)
                _results[step.Role] = new PdmBoardResult(step.Role, PdmStepState.Waiting, "waiting");

            LastOp = op;
            Busy = true;
            _index = -1;
            Next(now);
            return null;
        }
    }

    // A config frame the PC sent to the board with this BaseId, or a config-channel reply from it (any thread).
    // Only marks it: the next Tick restarts the write wait on its own clock.
    public void NoteTraffic(int baseId)
    {
        var step = _current;
        if (step is { Kind: StepKind.Write } && step.Dev.BaseId == baseId) step.Traffic = true;
    }

    // Call often (the page and PdmOpsService do, at 10 Hz): looks at the board in work, moves on or times out
    public void Tick(DateTime now)
    {
        lock (_lock)
        {
            if (!Busy) return;
            var step = _steps[_index];
            var dev = step.Dev;
            if (step.Traffic)
            {
                step.Traffic = false;
                step.Started = now;
            }

            var late = now - step.Started > Timeout(step.Kind);
            switch (step.Kind)
            {
                case StepKind.Read:
                    if (step.Acked && dev.FullReadDone && !dev.ConfigMismatch) Finish(step, true, "read OK", now);
                    else if (late)
                        Finish(step, false, step.Acked
                            ? "read, but the config check after it did not confirm a match"
                            : $"no reply (no complete read in {ReadTimeout.TotalSeconds:0} s)", now);
                    break;
                case StepKind.Write:
                    if (step.Acked && !dev.ConfigMismatch) Finish(step, true, "written OK (the board confirms the same settings)", now);
                    else if (now - step.Begun > WriteMaxTimeout)
                        Finish(step, false, $"write not confirmed in {WriteMaxTimeout.TotalMinutes:0} min", now);
                    else if (late)
                        Finish(step, false, step.Acked
                            ? "written, but the config check after it did not confirm a match"
                            : $"no reply (no answer for {WriteIdleTimeout.TotalSeconds:0} s while writing)", now);
                    break;
                case StepKind.Check:
                    if (!dev.ConfigMismatch)
                    {
                        Unhook(step);
                        _results[step.Role] = new PdmBoardResult(step.Role, PdmStepState.Waiting, "matches the board, burn pending");
                        Next(now);
                    }
                    else if (late)
                        Finish(step, false, "PC settings differ from the board, or no reply to the config check: nothing burned", now);
                    break;
                case StepKind.Burn:
                    if (step.Acked) Finish(step, true, "burned OK (the board confirmed)", now);
                    else if (late)
                        Finish(step, false, $"no \"burn successful\" reply in {BurnTimeout.TotalSeconds:0} s (burn failed or no answer)", now);
                    break;
            }
        }
    }

    private TimeSpan Timeout(StepKind kind) => kind switch
    {
        StepKind.Read => ReadTimeout,
        StepKind.Write => WriteIdleTimeout,
        StepKind.Check => CheckTimeout,
        _ => BurnTimeout
    };

    private void Next(DateTime now)
    {
        while (true)
        {
            _index++;
            if (_index >= _steps.Count)
            {
                _current = null;
                Busy = false;
                return;
            }

            if (Begin(_steps[_index], now)) return;
            if (!Busy) return; // stopped by a failure
        }
    }

    // true = sent, now waiting for the board. false = this step already has its result.
    private bool Begin(Step step, DateTime now)
    {
        var dev = step.Dev;
        step.Started = step.Begun = now;
        step.Traffic = false;
        _current = step;   // before sending: the frames of this request count as traffic
        if (!links.IsConnected(dev))
        {
            Finish(step, false, "offline: nothing sent", now, advance: false);
            return false;
        }

        var doing = "";
        var sent = true;
        switch (step.Kind)
        {
            case StepKind.Read:
                Hook(step, ": Read Successful", resetMismatch: true);
                doing = "reading ...";
                sent = links.SendReadAll(dev);
                break;
            case StepKind.Write:
                Hook(step, ": Write Successful", resetMismatch: true);
                doing = "writing ...";
                sent = links.SendWriteAll(dev);
                break;
            case StepKind.Check:
                dev.ConfigMismatch = true; // only a fresh matching reply clears it
                doing = "config check ...";
                links.SendCheck(dev);
                break;
            case StepKind.Burn:
                Hook(step, ": Burn Successful", resetMismatch: false);
                doing = "burning ...";
                sent = links.SendBurn(dev);
                break;
        }

        if (!sent)
        {
            Finish(step, false, "not sent: " + (CustomPdmGuards.WriteAllBlockedReason(dev) ?? "refused"), now, advance: false);
            return false;
        }

        _results[step.Role] = new PdmBoardResult(step.Role, PdmStepState.Running, doing);
        return true;
    }

    // The stock success notification of this one device. After a read / write the stock code sends a config CRC
    // check by itself: the flag is set back to "mismatch" here so that only the reply to THAT check counts.
    private static void Hook(Step step, string suffix, bool resetMismatch)
    {
        step.Handler = msg =>
        {
            if (!msg.EndsWith(suffix, StringComparison.Ordinal)) return;
            if (resetMismatch) step.Dev.ConfigMismatch = true;
            step.Acked = true;
        };
        step.Dev.SuccessNotification += step.Handler;
    }

    private static void Unhook(Step step)
    {
        if (step.Handler != null) step.Dev.SuccessNotification -= step.Handler;
        step.Handler = null;
    }

    private void Finish(Step step, bool ok, string text, DateTime now, bool advance = true)
    {
        Unhook(step);
        _results[step.Role] = new PdmBoardResult(step.Role, ok ? PdmStepState.Ok : PdmStepState.Failed, text);

        if (!ok && LastOp != PdmOpKind.ReadAll)
        {
            // stop: every board that has no final result yet is left alone
            var left = LastOp == PdmOpKind.WriteAll ? "not written" : "not burned";
            foreach (var role in _results.Keys.ToList())
                if (_results[role].State is PdmStepState.Waiting or PdmStepState.Running)
                    _results[role] = new PdmBoardResult(role, PdmStepState.NotDone, $"{left} (run stopped at {step.Role})");
            _current = null;
            Busy = false;
            return;
        }

        if (advance) Next(now);
    }
}
