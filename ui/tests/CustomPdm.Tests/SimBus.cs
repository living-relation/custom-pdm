using System.Collections.Concurrent;
using System.Diagnostics;
using domain.Devices;
using domain.Enums;
using domain.Models;

namespace CustomPdm.Tests;

// ui/tests/sim_bridge.py --stdio in WSL: our three boards (real dingoFW logic) on one CAN bus with a PC-tool node
public sealed class SimBus : IDisposable
{
    private readonly Process _p;

    public SimBus()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "ui", "tests", "sim_bridge.py"))) dir = dir.Parent;
        if (dir == null) throw new InvalidOperationException("repo root with ui/tests/sim_bridge.py not found");
        var win = Path.Combine(dir.FullName, "ui", "tests", "sim_bridge.py");
        var wsl = "/mnt/" + char.ToLowerInvariant(win[0]) + win[2..].Replace('\\', '/');
        var so = Environment.GetEnvironmentVariable("CUSTOMPDM_SIM_SO")!;
        _p = Process.Start(new ProcessStartInfo("wsl.exe", $"-e python3 {wsl} {so} --stdio")
        {
            RedirectStandardInput = true, RedirectStandardOutput = true, UseShellExecute = false
        })!;
    }

    public List<(int Id, byte[] Data)> Cmd(string line)
    {
        _p.StandardInput.WriteLine(line);
        _p.StandardInput.Flush();
        var frames = new List<(int, byte[])>();
        while (true)
        {
            var r = _p.StandardOutput.ReadLine() ?? throw new InvalidOperationException("sim bridge stopped");
            if (r == "OK") return frames;
            if (r.StartsWith("ERR")) throw new InvalidOperationException(r);
            var a = r.Split(' ');
            frames.Add((Convert.ToInt32(a[1], 16), Convert.FromHexString(a[2])));
        }
    }

    public List<(int Id, byte[] Data)> Run(double ms) => Cmd($"RUN {ms}");

    public List<(int Id, byte[] Data)> Tx(IEnumerable<CanFrame> frames, double gapMs = 2) =>
        Cmd($"TX {gapMs} " + string.Join(' ', frames.Select(f => $"{f.Id:X}:{Convert.ToHexString(f.Payload, 0, f.Len)}")));

    // B4: output o (0-based) of a board, from its PROFET IN pin (ground truth, not the status message)
    public bool Pin(string board, int o)
    {
        _p.StandardInput.WriteLine($"PIN {board} {o}");
        _p.StandardInput.Flush();
        bool? level = null;
        while (true)
        {
            var r = _p.StandardOutput.ReadLine() ?? throw new InvalidOperationException("sim bridge stopped");
            if (r == "OK") return level ?? throw new InvalidOperationException("no P line");
            if (r.StartsWith("ERR")) throw new InvalidOperationException(r);
            if (r.StartsWith("P ")) level = r == "P 1";
        }
    }

    public void Dispose()
    {
        try { _p.StandardInput.WriteLine("QUIT"); _p.WaitForExit(5000); } catch { /* ignored */ }
        if (!_p.HasExited) _p.Kill();
        _p.Dispose();
    }
}

// The part of DeviceManager a test needs: send a device's frames, route the replies to it, send what it answers
public sealed class PcTool(SimBus bus, FwDevice dev)
{
    public FwDevice Dev { get; } = dev;
    public List<string> Notes { get; } = [];
    public List<(int Id, byte[] Data)> Seen { get; } = [];
    private ConcurrentDictionary<(int BaseId, int Index, int SubIndex), DeviceCanFrame> _queue = new();
    private readonly Queue<CanFrame> _pending = new();
    private bool _hooked;

    public static PcTool For(SimBus bus, int deviceType, int baseId)
    {
        var dev = StockTests.MakeDevice(deviceType, baseId);
        return new PcTool(bus, dev);
    }

    private void Feed(IEnumerable<(int Id, byte[] Data)> frames)
    {
        if (!_hooked) { Dev.SuccessNotification += Notes.Add; _hooked = true; }
        foreach (var (id, data) in frames)
        {
            Seen.Add((id, data));
            if (!Dev.InIdRange(id)) continue;
            var outgoing = new List<DeviceCanFrame>();
            Dev.Read(id, data, ref _queue, outgoing);
            foreach (var f in outgoing) _pending.Enqueue(f.Frame);
        }
    }

    public void Run(double ms) => Feed(bus.Run(ms));

    public void Send(IEnumerable<DeviceCanFrame> frames)
    {
        foreach (var f in frames) _pending.Enqueue(f.Frame);
        Pump();
    }

    private void Pump()
    {
        while (_pending.Count > 0)
        {
            var batch = new List<CanFrame>();
            while (_pending.Count > 0 && batch.Count < 64) batch.Add(_pending.Dequeue());
            Feed(bus.Tx(batch));
        }
    }

    // Run the bus (answering whatever the device sends) until done() or maxMs
    public bool RunUntil(Func<bool> done, int maxMs = 20000)
    {
        for (var t = 0; t < maxMs; t += 50)
        {
            if (done()) return true;
            Run(50);
            Pump();
        }
        return done();
    }

    public int CountCmd(MessageCommand cmd) =>
        Seen.Count(s => s.Id == Dev.BaseId && s.Data.Length == 8 && s.Data[0] == (byte)cmd);

    // Read All (version + read all, then the CRC check dingoConfig sends by itself)
    public bool ReadAll()
    {
        var n = CountCmd(MessageCommand.CheckCrcRsp);
        Send(Dev.GetReadMsgs(true));
        return RunUntil(() => CountCmd(MessageCommand.CheckCrcRsp) > n);
    }

    public bool WriteAll()
    {
        var n = CountCmd(MessageCommand.CheckCrcRsp);
        Send(Dev.GetWriteMsgs(true));
        return RunUntil(() => CountCmd(MessageCommand.CheckCrcRsp) > n);
    }
}
