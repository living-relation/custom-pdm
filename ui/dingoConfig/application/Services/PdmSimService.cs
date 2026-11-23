using System.Collections.Concurrent;
using domain.CustomPdm;
using domain.Interfaces;
using domain.Models;

namespace application.Services;

// custom-pdm uipolish: the app side of the /pdm Simulator panel (domain/CustomPdm/PdmSim.cs). Knows whether the
// connected adapter is the simulator bridge (it answered "!HELLO") and sends it play lines.
public class PdmSimService : IDisposable
{
    public const string NotSimReason = "The simulator bridge is not connected.";

    private readonly ICommsAdapterManager _manager;
    private readonly object _lock = new();
    private IPdmSimLink? _link;

    public bool IsSimulator { get; private set; }
    public string? LastReply { get; private set; }                // "OK LOAD B 4 20" / "ERR ..."
    public event Action? Changed;

    // what the panel has set, by what it is ("IN 15", "LOAD 19", "TEMP B", "TXP 3F4"): shown as chips, gone on disconnect
    private readonly Dictionary<string, string> _set = new();
    public IReadOnlyList<string> SetLines { get { lock (_lock) return _set.Values.ToList(); } }

    public PdmSimService(ICommsAdapterManager manager)
    {
        _manager = manager;
        _manager.Connected += OnConnected;
        _manager.Disconnected += OnDisconnected;
        _manager.DataReceived += OnFrame;
        Attach();
    }

    // ---------------- canboard: the simulated CANBoards (PdmCanBoardSim) ----------------

    private readonly ConcurrentDictionary<int, (byte[] Data, long At)> _frames = new();
    private readonly Dictionary<int, string> _cbOut = new();          // base ID -> the output lines last sent
    private volatile HashSet<int> _watch = [];
    public Func<long> Clock { get; set; } = () => Environment.TickCount64;   // ms

    // the panel says which CANBoards (base IDs) it shows: only their status frames are kept
    public void Watch(IEnumerable<int> baseIds)
    {
        var ids = baseIds.SelectMany(PdmCanBoardSim.WatchIds).ToHashSet();
        if (!ids.SetEquals(_watch)) _watch = ids;
    }

    private void OnFrame(object? sender, CanFrameEventArgs e)
    {
        var w = _watch;
        if (w.Count == 0 || !w.Contains(e.Frame.Id)) return;
        _frames[e.Frame.Id] = (e.Frame.Payload.Take(e.Frame.Len).ToArray(), Clock());
    }

    // what the CANBoard at baseId reports on the bus right now (Alive false: no state frame for 350 ms)
    public PdmCanBoardLive CanBoard(int baseId)
    {
        var ids = PdmCanBoardSim.WatchIds(baseId);
        byte[]? D(int id) => _frames.TryGetValue(id, out var f) ? f.Data : null;
        var alive = IsSimulator && _frames.TryGetValue(ids[2], out var st) && Clock() - st.At <= PdmCanBoardSim.StaleMs;
        return PdmCanBoardSim.Decode(D(ids[0]), D(ids[1]), D(ids[2]), alive);
    }

    // Put a simulated CANBoard on the bus (or back on it), set as the CANBoard card says. null = sent.
    public string? PlugCanBoard(PdmCanBoardInfo cb)
    {
        lock (_lock) _cbOut.Remove(cb.BaseId);
        return Send(PdmCanBoardSim.AddLine(cb.BaseId)) ?? Send(PdmCanBoardSim.LinkLine(cb.BaseId, true)) ?? SyncCanBoard(cb);
    }

    // keep the simulated CANBoard's outputs as the setup has them (sent again only when they changed)
    public string? SyncCanBoard(PdmCanBoardInfo cb)
    {
        var lines = PdmCanBoardSim.OutputLines(cb);
        var key = string.Join('|', lines);
        lock (_lock)
            if (_cbOut.GetValueOrDefault(cb.BaseId) == key) return null;
        foreach (var l in lines)
            if (Send(l) is { } refused) return refused;
        lock (_lock) _cbOut[cb.BaseId] = key;
        return null;
    }

    private void OnConnected(object? sender, EventArgs e) => Attach();
    private void OnDisconnected(object? sender, EventArgs e) => Detach();

    private void Attach()
    {
        Detach();
        if (_manager.ActiveAdapter is not IPdmSimLink link || _manager.ActiveAdapter.Name != PdmSim.BridgeAdapter) return;
        lock (_lock) _link = link;
        link.SimLine += OnLine;
        link.SendSimLine(PdmSim.Mark + PdmSim.Hello);
    }

    private void Detach()
    {
        IPdmSimLink? old;
        lock (_lock)
        {
            old = _link;
            _link = null;
            IsSimulator = false;
            LastReply = null;
            _set.Clear();
            _cbOut.Clear();
        }

        _frames.Clear();

        if (old != null) old.SimLine -= OnLine;
        Changed?.Invoke();
    }

    // Ask again (the page does, now and then, while an SLCAN TCP adapter is connected and has not answered)
    public void Probe()
    {
        IPdmSimLink? link;
        lock (_lock) link = _link;
        if (link == null || !ReferenceEquals(link, _manager.ActiveAdapter)) Attach();
        else if (!IsSimulator) link.SendSimLine(PdmSim.Mark + PdmSim.Hello);
    }

    private void OnLine(string raw)
    {
        if (raw.Length < 2 || raw[0] != PdmSim.Mark) return;
        var text = raw[1..].Trim();
        lock (_lock)
        {
            if (text == PdmSim.HelloReply) IsSimulator = true;
            else LastReply = text;
        }

        Changed?.Invoke();
    }

    // Sends one play line. what = the thing it sets (a new line for the same thing replaces the old chip).
    // Returns why it was not sent, or null.
    public string? Send(string? line, string? what = null)
    {
        if (line == null) return "Not a valid value.";
        IPdmSimLink? link;
        lock (_lock) link = IsSimulator ? _link : null;
        if (link == null) return NotSimReason;
        if (!link.SendSimLine(PdmSim.Mark + line)) return "The line could not be sent (adapter closed).";
        lock (_lock)
        {
            if (line.StartsWith("RESTART", StringComparison.Ordinal)) { }
            else if (line.EndsWith(" off", StringComparison.Ordinal) && what != null) _set.Remove(what);
            else if (what != null) _set[what] = line;
        }

        Changed?.Invoke();
        return null;
    }

    public void Dispose()
    {
        _manager.Connected -= OnConnected;
        _manager.Disconnected -= OnDisconnected;
        _manager.DataReceived -= OnFrame;
        Detach();
    }
}
