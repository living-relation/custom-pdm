using domain.Devices;

namespace domain.CustomPdm;

// custom-pdm p2a (Dan, 2026-11-16): /pdm reads a board by itself when it connects, and asks first when the PC holds
// unsaved edits for it. Nothing is ever written or burned from here.
// "Unsaved edits" of a board = its PC param values differ from the values last read from / written to that board in
// this session (the snapshot below, taken on the stock "Read Successful" / "Write Successful" of that device, from
// /pdm or from the board's own page). No snapshot yet: a "New PDM" board counts as edited (its factory settings are
// not on the boards until written); any other board does not (a hand-added or loaded device cannot be written before
// a Read All anyway, CustomPdmGuards). The config CRC check is not used for this: a mismatch cannot tell a PC edit
// from a board that was changed elsewhere.
// Connect = the board goes from offline to connected (first look counts as a connect). The read waits while any PDM
// run is busy (Read All / Write All / Burn) and the boards that wait are read in ONE run, one after another. The
// edits check is made again on every Step, so a board that waits and gets edits is asked about instead.
public enum PdmConnectAnswer { KeepPc, TakeBoard }

public class PdmAutoRead
{
    private sealed class Board(FwDevice dev)
    {
        public FwDevice Dev { get; } = dev;
        public bool WasConnected;
        public object[]? Synced;          // param values last read from / written to the board
        public Action<string>? Handler;
        public bool Queued, Forced, Ask;  // Forced: "Take the board's" (read even with edits)
    }

    private readonly object _lock = new();
    private readonly Dictionary<Guid, Board> _boards = new();
    private readonly List<Guid> _order = []; // queue order (connect order)

    private static object[] Values(FwDevice d) => d.Params.Select(p => p.GetValue()).ToArray();

    // true = the PC values of this board differ from what the board was last seen to hold (or a New PDM not written)
    public bool HasEdits(FwDevice dev)
    {
        lock (_lock)
        {
            var synced = _boards.TryGetValue(dev.Guid, out var b) ? b.Synced : null;
            if (synced == null) return dev.CustomPdm?.FactoryNew == true;
            var now = Values(dev);
            return now.Length != synced.Length || now.Where((v, i) => !Equals(v, synced[i])).Any();
        }
    }

    // Boards (by role) that wait for an answer: connected with unsaved edits
    public IReadOnlyList<PdmBoard> Asks(PdmView view)
    {
        lock (_lock) return view.Boards.Where(b => _boards.TryGetValue(b.Device.Guid, out var s) && s.Ask).ToList();
    }

    // Boards (by role) whose read on connect waits for the PDM run that is busy
    public IReadOnlyList<PdmBoard> Waiting(PdmView view)
    {
        lock (_lock) return view.Boards.Where(b => _boards.TryGetValue(b.Device.Guid, out var s) && s.Queued).ToList();
    }

    public void Answer(FwDevice dev, PdmConnectAnswer answer)
    {
        lock (_lock)
        {
            if (!_boards.TryGetValue(dev.Guid, out var b) || !b.Ask) return;
            b.Ask = false;
            if (answer != PdmConnectAnswer.TakeBoard) return;
            Enqueue(b);
            b.Forced = true;
        }
    }

    private void Enqueue(Board b)
    {
        b.Queued = true;
        if (!_order.Contains(b.Dev.Guid)) _order.Add(b.Dev.Guid);
    }

    private void Dequeue(Board b)
    {
        b.Queued = b.Forced = false;
        _order.Remove(b.Dev.Guid);
    }

    // Call often (PdmOpsService does, at 10 Hz). busy = a PDM run is active. Returns the roles to read now (empty =
    // nothing to start); the caller starts ONE Read All run of just these boards.
    public IReadOnlyList<string> Step(PdmView view, Func<FwDevice, bool> isConnected, bool busy)
    {
        lock (_lock)
        {
            var inView = view.Boards.Select(b => b.Device.Guid).ToHashSet();
            foreach (var gone in _boards.Keys.Where(g => !inView.Contains(g)).ToList()) Forget(gone);

            foreach (var pb in view.Boards)
            {
                var b = Track(pb.Device);
                var connected = isConnected(b.Dev);
                if (connected && !b.WasConnected && !b.Ask) Enqueue(b);
                if (!connected && b.WasConnected)
                {
                    Dequeue(b);
                    b.Ask = false; // asked again at the next connect
                }
                b.WasConnected = connected;

                // edits decide, again on every step: a waiting board that got edits is asked about instead, an asked
                // board whose edits are gone (e.g. written meanwhile) is read without asking
                if (b.Queued && !b.Forced && HasEdits(b.Dev))
                {
                    Dequeue(b);
                    b.Ask = true;
                }
                else if (b.Ask && !HasEdits(b.Dev))
                {
                    b.Ask = false;
                    Enqueue(b);
                }
            }

            if (busy || _order.Count == 0) return [];
            return view.Boards.Where(pb => _order.Contains(pb.Device.Guid)).Select(pb => pb.Role).ToList();
        }
    }

    // The read of these roles has started (the caller's Start was not refused): they wait no more
    public void Started(PdmView view, IEnumerable<string> roles)
    {
        lock (_lock)
            foreach (var pb in view.Boards.Where(pb => roles.Contains(pb.Role)))
                if (_boards.TryGetValue(pb.Device.Guid, out var b)) Dequeue(b);
    }

    private Board Track(FwDevice dev)
    {
        if (_boards.TryGetValue(dev.Guid, out var b)) return b;
        b = new Board(dev);
        b.Handler = msg =>
        {
            if (!msg.EndsWith(": Read Successful", StringComparison.Ordinal)
                && !msg.EndsWith(": Write Successful", StringComparison.Ordinal)) return;
            lock (_lock) b.Synced = Values(dev);
        };
        dev.SuccessNotification += b.Handler;
        _boards[dev.Guid] = b;
        return b;
    }

    private void Forget(Guid g)
    {
        var b = _boards[g];
        if (b.Handler != null) b.Dev.SuccessNotification -= b.Handler;
        _order.Remove(g);
        _boards.Remove(g);
    }

    // Start watching these boards now (snapshots from here on). Step does it too.
    public void Watch(PdmView view)
    {
        lock (_lock)
            foreach (var pb in view.Boards) Track(pb.Device);
    }
}
