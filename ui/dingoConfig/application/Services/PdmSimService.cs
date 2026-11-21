using domain.CustomPdm;
using domain.Interfaces;

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
        Attach();
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
        }

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
        Detach();
    }
}
