using System.Collections.Concurrent;
using System.Diagnostics;
using application.Services;
using domain.CustomPdm;
using domain.Enums;
using domain.Interfaces;
using domain.Models;
using infrastructure.Adapters;
using infrastructure.Comms;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// uipolish (2026-11-21): the /pdm Simulator panel (PdmSim.cs, PdmSimService.cs, sim_bridge.py "!" lines)
public class SimPanelTests
{
    [Fact]
    public void PlayLinesNameTheBoardAndCountFromZero()
    {
        var v = new FakePdm().View;
        foreach (var r in v.Inputs.Where(r => r.Digital != null))
            Assert.Equal($"IN {r.Board} {r.BoardInput - 1} gnd", PdmSim.InputLine(v, r.Number, "gnd"));
        Assert.Equal("IN A1 0 12v", PdmSim.InputLine(v, v.Inputs.First(r => r.Board == "A1").Number, "12v"));
        Assert.EndsWith(" open", PdmSim.InputLine(v, 1, "open"));
        Assert.Null(PdmSim.InputLine(v, 1, "5v"));
        Assert.Null(PdmSim.InputLine(v, 25, "gnd"));      // analog input: its own line
        Assert.Null(PdmSim.InputLine(v, 0, "gnd"));

        foreach (var r in v.Outputs)
            Assert.Equal($"LOAD {r.Board} {r.BoardOutput - 1} 12.5", PdmSim.LoadLine(v, r.Number, 12.5));
        Assert.EndsWith(" 0", PdmSim.LoadLine(v, 1, 0));
        Assert.EndsWith(" 200", PdmSim.LoadLine(v, 1, 200));
        Assert.Null(PdmSim.LoadLine(v, 1, -1));
        Assert.Null(PdmSim.LoadLine(v, 1, 200.5));
        Assert.Null(PdmSim.LoadLine(v, 25, 5));

        Assert.Equal("TEMP B 99.5", PdmSim.TempLine(v, "B", 99.5));
        Assert.Equal(("TEMP A1 -40", "TEMP A2 150"), (PdmSim.TempLine(v, "A1", -40), PdmSim.TempLine(v, "A2", 150)));
        Assert.Null(PdmSim.TempLine(v, "B", 151));
        Assert.Null(PdmSim.TempLine(v, "B", -41));
        Assert.Null(PdmSim.TempLine(v, "C", 20));
        Assert.Equal("AN A2 2.5", PdmSim.AnalogLine(v, "A2", 2.5));
        Assert.Equal(("AN B 0", "AN B 5"), (PdmSim.AnalogLine(v, "B", 0), PdmSim.AnalogLine(v, "B", 5)));
        Assert.Null(PdmSim.AnalogLine(v, "B", 5.1));
        Assert.Null(PdmSim.AnalogLine(v, "B", -0.1));
        Assert.Null(PdmSim.AnalogLine(v, "X", 1));
        Assert.Equal("RESTART A1 A2 B", PdmSim.RestartLine(v));
        Assert.Equal("RESTART A1 B", PdmSim.RestartLine(new FakePdm("A1", "B").View));
        Assert.Null(PdmSim.RestartLine(new PdmView()));
        Assert.Equal("TXP 3F4 0100000000000000 50", PdmSim.FrameLine(0x3F4, [1, 0, 0, 0, 0, 0, 0, 0], 50));
        Assert.Equal("TXP 1A8 off", PdmSim.StopLine(0x1A8));
    }

    [Fact]
    public void ValuesArePackedAsTheBoardReadsThem()
    {
        byte[] Packed(int start, int len, ByteOrder order, long raw, byte fill = 0)
        {
            var d = Enumerable.Repeat(fill, 8).ToArray();
            PdmSim.Put(d, start, len, order, raw);
            return d;
        }

        Assert.Equal("0000AB0000000000", Convert.ToHexString(Packed(16, 8, ByteOrder.LittleEndian, 0xAB)));
        Assert.Equal("0000AB0000000000", Convert.ToHexString(Packed(23, 8, ByteOrder.BigEndian, 0xAB)));   // Motorola MSB of byte 2
        Assert.Equal("C0AB000000000000", Convert.ToHexString(Packed(4, 12, ByteOrder.LittleEndian, 0xABC)));
        Assert.Equal("1234000000000000", Convert.ToHexString(Packed(7, 16, ByteOrder.BigEndian, 0x1234)));
        Assert.Equal("3412000000000000", Convert.ToHexString(Packed(0, 16, ByteOrder.LittleEndian, 0x1234)));
        Assert.Equal("0001010000000000", Convert.ToHexString(Packed(8, 9, ByteOrder.BigEndian, 0x101)));           // MSB at bit 8, the rest in byte 2
        Assert.Equal("FFFFFBFFFFFFFFFF", Convert.ToHexString(Packed(18, 1, ByteOrder.LittleEndian, 0, 0xFF)));     // clears as well as sets
        Assert.Equal("0000000000000080", Convert.ToHexString(Packed(63, 4, ByteOrder.LittleEndian, 0xF)));         // stops at the frame end

        var coolant = new PdmSimField("k", "coolant", 0x3E0, 0, 8, ByteOrder.LittleEndian, false, 1, -40);
        Assert.Equal(135, PdmSim.Raw(coolant, 95));                     // 95 = raw x 1 - 40
        Assert.Equal(255, PdmSim.Raw(coolant, 1000));                   // clamped to the field
        Assert.Equal(0, PdmSim.Raw(coolant, -100));
        var signed = coolant with { Signed = true, Factor = 0.5, Offset = 0, Length = 12 };
        Assert.Equal(0xFF6, PdmSim.Raw(signed, -5));                    // -10 in 12 bits
        Assert.Equal(0x7FF, PdmSim.Raw(signed, 5000));
        Assert.Equal(0x800, PdmSim.Raw(signed, -5000));

        var frames = PdmSim.Frames([coolant, coolant with { Key = "b", StartBit = 8 }, coolant with { Key = "c", Id = 0x100, StartBit = 56 }],
            f => f.StartBit == 8 ? 0 : 95);
        Assert.Equal([0x100, 0x3E0], frames.Keys);
        Assert.Equal(("8728000000000000", "0000000000000087"), (Convert.ToHexString(frames[0x3E0]), Convert.ToHexString(frames[0x100])));
    }

    [Fact]
    public async Task TheFieldsAreWhatTheSetupListensToFromOutsideThePdm()
    {
        var mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance,
            new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs")), new FwDeviceDefManager());
        mgr.SetBatchTransmitCallback(_ => { });
        var service = new PdmOpsService(mgr, _ => true) { AutoTick = false };
        Assert.Empty(PdmSim.Fields(new FakePdm().View));                 // a setup that reads nothing from outside

        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
        Assert.Null(await PdmStarter.LoadAsync(PdmStarter.Find(AppContext.BaseDirectory)!, files, mgr, service.Ops));
        var v = service.BuildView();
        var fields = PdmSim.Fields(v);
        Assert.Equal(fields.Count, fields.Select(f => f.Key).Distinct().Count());
        Assert.All(fields, f => Assert.False(PdmEcu.IsPdmId(v, f.Id)));  // never a frame one of our boards sends
        var pump = Assert.Single(fields, f => f.Name == "Fuel pump (B OUT3): ECU command (1 = on)");
        Assert.Equal((0x3F4, 0, 8), (pump.Id, pump.StartBit, pump.Length));
        var fan = Assert.Single(fields, f => f.Name == "Condenser fan (B OUT2): ECU command (1 = on)");
        Assert.Equal((0x3F4, 8, 8), (fan.Id, fan.StartBit, fan.Length));
        var coolant = Assert.Single(fields, f => f.Name.StartsWith("ECU coolant (0x"));
        Assert.Contains(fields, f => f.Id == 0x180 + 0x28 && f.Length == 1);   // the keypad button of the starter
        Assert.Equal(fields.OrderBy(f => f.Id).ThenBy(f => f.StartBit).Select(f => f.Key), fields.Select(f => f.Key));

        // a value one board reads from ANOTHER board's status frame is not for the simulator to send
        var signal = PdmValues.RemoteSignals(v, "A1", out _).First().Name;
        PdmValues.AddRemoteValue(v, "B", "A1", signal, out var refused);
        Assert.Null(refused);
        Assert.Equal(fields.Select(f => f.Key), PdmSim.Fields(v).Select(f => f.Key));

        var frames = PdmSim.Frames(fields, f => f.Key == pump.Key ? 1 : f.Key == coolant.Key ? 95 : 0);
        Assert.Equal("01", Convert.ToHexString(frames[0x3F4])[..2]);
        Assert.Equal("00", Convert.ToHexString(frames[0x3F4])[2..4]);
        Assert.Contains(frames[coolant.Id], b => b != 0);
    }

    // ---------------- the service, with a stand-in adapter ----------------

    private sealed class FakeLink(string name) : ICommsAdapter, IPdmSimLink
    {
        public string? Name { get; } = name;
        public List<string> Got { get; } = [];
        public bool Closed;
        public event Action<string>? SimLine;
        public bool SendSimLine(string line) { if (Closed) return false; Got.Add(line); return true; }
        public void Say(string line) => SimLine?.Invoke(line);
        public bool Hooked => SimLine != null;
        public Task<bool> InitAsync(string port, CanBitRate bitRate, CancellationToken ct) => Task.FromResult(true);
        public Task<bool> StartAsync(CancellationToken ct) => Task.FromResult(true);
        public Task<bool> StopAsync() => Task.FromResult(true);
        public Task<bool> WriteAsync(CanFrame frame, CancellationToken ct) => Task.FromResult(true);
        public Task<bool> WriteBatchAsync(IReadOnlyList<CanFrame> frames, CancellationToken ct) => Task.FromResult(true);
        public bool IsConnected => true;
#pragma warning disable CS0067
        public event DataReceivedHandler? DataReceived;
        public event EventHandler? Disconnected;
#pragma warning restore CS0067
    }

    private sealed class FakeManager : ICommsAdapterManager
    {
        public ICommsAdapter? ActiveAdapter { get; private set; }
        public bool IsConnected => ActiveAdapter != null;
        public void Connect(ICommsAdapter a) { ActiveAdapter = a; Connected?.Invoke(this, EventArgs.Empty); }
        public void Drop() { ActiveAdapter = null; Disconnected?.Invoke(this, EventArgs.Empty); }
        public (string[] adapters, string[] ports) GetAvailable() => ([], []);
        public (bool isConnected, string? activeAdapter, string? activePort, CanBitRate activeBitRate) GetStatus() => (IsConnected, null, null, default);
        public ICommsAdapter ToAdapter(string adapterName) => null!;
        public Task<bool> ConnectAsync(ICommsAdapter commsAdapter, string port, CanBitRate bitRate, CancellationToken ct = default) => Task.FromResult(true);
        public Task<bool> DisconnectAsync() => Task.FromResult(true);
        public event EventHandler? Connected;
        public event EventHandler? Disconnected;
#pragma warning disable CS0067
        public event EventHandler<CanFrameEventArgs>? DataReceived;
#pragma warning restore CS0067
    }

    [Fact]
    public void ThePanelIsOnlyForTheBridgeThatAnswersTheHello()
    {
        var mgr = new FakeManager();
        using var sim = new PdmSimService(mgr);
        var changes = 0;
        sim.Changed += () => changes++;
        Assert.False(sim.IsSimulator);
        Assert.Equal(PdmSimService.NotSimReason, sim.Send("LOAD B 4 20", "LOAD 21"));

        var real = new FakeLink("SLCAN TCP");     // ser2net / an ESP32 bridge to real boards: it never answers
        mgr.Connect(real);
        Assert.Equal(["!HELLO"], real.Got);
        Assert.False(sim.IsSimulator);
        Assert.Equal(PdmSimService.NotSimReason, sim.Send("LOAD B 4 20", "LOAD 21"));
        sim.Probe();
        Assert.Equal(["!HELLO", "!HELLO"], real.Got);
        real.Say("!OK LOAD B 4 20");               // some other "!" line is not the hello
        Assert.False(sim.IsSimulator);

        real.Say("!SIM custom-pdm");
        Assert.True(sim.IsSimulator);
        Assert.True(changes > 0);
        sim.Probe();                               // known: asked no more
        Assert.Equal(2, real.Got.Count);

        Assert.Null(sim.Send("LOAD B 4 20", "LOAD 21"));
        Assert.Null(sim.Send("LOAD B 4 7.5", "LOAD 21"));          // the same thing again: one chip
        Assert.Null(sim.Send("TXP 3F4 0100000000000000 50", "TXP 3F4"));
        Assert.Equal(["!LOAD B 4 20", "!LOAD B 4 7.5", "!TXP 3F4 0100000000000000 50"], real.Got.Skip(2));
        Assert.Equal(["LOAD B 4 7.5", "TXP 3F4 0100000000000000 50"], sim.SetLines);
        Assert.Null(sim.Send("TXP 3F4 off", "TXP 3F4"));
        Assert.Null(sim.Send("RESTART A1 A2 B"));
        Assert.Equal(["LOAD B 4 7.5"], sim.SetLines);
        Assert.Equal("Not a valid value.", sim.Send(null, "LOAD 1"));
        real.Say("!ERR LOAD B 99 5");
        Assert.Equal("ERR LOAD B 99 5", sim.LastReply);
        real.Say("t5001100");                      // not a "!" line: ignored
        Assert.Equal("ERR LOAD B 99 5", sim.LastReply);
        real.Closed = true;
        Assert.Equal("The line could not be sent (adapter closed).", sim.Send("TEMP B 50", "TEMP B"));

        mgr.Drop();
        Assert.False(sim.IsSimulator);
        Assert.False(real.Hooked);
        Assert.Empty(sim.SetLines);
        Assert.Null(sim.LastReply);

        var usb = new FakeLink("USB");             // a serial SLCAN adapter is never asked
        mgr.Connect(usb);
        sim.Probe();
        Assert.Empty(usb.Got);
        usb.Say("!SIM custom-pdm");
        Assert.False(sim.IsSimulator);
    }
}

// The real thing: the app's adapter on sim_bridge.py --slcan-tcp, play lines sent in band
[Collection("sim")]
public class SimPanelLiveSimTests(ITestOutputHelper output)
{
    private const int Port = 3393;   // own port: 3333 play bridge, 3391 SlcanBridgeTests, 3392 UiWalkLiveSimTests

    [SimFact]
    public async Task TheBridgeAnswersTheHelloAndActsOnThePlayLinesOfThePanel()
    {
        var so = Environment.GetEnvironmentVariable("CUSTOMPDM_SIM_SO")!;
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (!File.Exists(Path.Combine(dir!.FullName, "ui", "tests", "sim_bridge.py"))) dir = dir.Parent;
        var win = Path.Combine(dir.FullName, "ui", "tests", "sim_bridge.py");
        var wsl = "/mnt/" + char.ToLowerInvariant(win[0]) + win[2..].Replace('\\', '/');

        var services = new ServiceCollection();
        services.AddLogging();
        services.AddTransient<SlcanTcpAdapter>();
        await using var sp = services.BuildServiceProvider();
        var manager = new CommsAdapterManager(sp, sp.GetRequiredService<ILogger<CommsAdapterManager>>());
        var rx = new ConcurrentQueue<CanFrame>();
        manager.DataReceived += (_, e) => rx.Enqueue(e.Frame);
        using var sim = new PdmSimService(manager);
        var bridge = Process.Start(new ProcessStartInfo("wsl.exe", $"-e python3 {wsl} {so} --slcan-tcp {Port}")
            { RedirectStandardOutput = true, UseShellExecute = false })!;
        try
        {
            var (plan, _) = PdmAutoConnect.Plan("SLCAN TCP", $"localhost:{Port}", "1000K", false, null);
            var (ok, text) = await PdmAutoConnect.RunAsync(manager, plan!, tries: 20, gap: TimeSpan.FromSeconds(1));
            Assert.True(ok, text);

            async Task<bool> Until(Func<bool> done, int seconds)
            {
                for (var i = 0; i < seconds * 10 && !done(); i++) await Task.Delay(100);
                return done();
            }

            sim.Probe();
            Assert.True(await Until(() => sim.IsSimulator, 10), "no answer to !HELLO");

            var v = new FakePdm().View;
            Assert.True(await Until(() => rx.Any(f => f.Id == 0x5A7), 20));
            Assert.Null(sim.Send(PdmSim.InputLine(v, v.Inputs.First(r => r.Board == "A1").Number, "gnd"), "IN 1"));
            Assert.True(await Until(() => sim.LastReply == "OK IN A1 0 gnd", 5), sim.LastReply);

            // the line acts on the simulated board: board B's temperature goes into its status frames. Frames of B that
            // held still for two looks in a row before the line, and what they hold after it.
            async Task<Dictionary<int, string>> Look()
            {
                rx.Clear();
                await Task.Delay(1200);
                return rx.Where(f => f.Id is >= 0x580 and < 0x5C0).GroupBy(f => f.Id)
                    .ToDictionary(g => g.Key, g => Convert.ToHexString(g.Last().Payload));
            }

            var (a, b) = (await Look(), await Look());
            var still = a.Where(x => b.TryGetValue(x.Key, out var y) && y == x.Value).ToDictionary(x => x.Key, x => x.Value);
            Assert.NotEmpty(still);
            Assert.Null(sim.Send(PdmSim.TempLine(v, "B", 77), "TEMP B"));
            Assert.True(await Until(() => sim.LastReply == "OK TEMP B 77", 5), sim.LastReply);
            var after = await Look();
            var changed = still.Where(x => after.TryGetValue(x.Key, out var y) && y != x.Value).Select(x => $"0x{x.Key:X}: {x.Value} -> {after[x.Key]}").ToList();
            output.WriteLine(string.Join("; ", changed));
            Assert.NotEmpty(changed);

            // every kind of line the panel sends is taken; a wrong one is refused and the bridge stays up
            foreach (var line in new[] { PdmSim.LoadLine(v, 21, 20)!, PdmSim.TempLine(v, "B", 60)!, PdmSim.AnalogLine(v, "A2", 2.5)!,
                         PdmSim.FrameLine(0x3F4, [1, 0, 0, 0, 0, 0, 0, 0], 50), PdmSim.StopLine(0x3F4) })
            {
                Assert.Null(sim.Send(line));
                Assert.True(await Until(() => sim.LastReply == "OK " + line, 5), $"{line}: {sim.LastReply}");
            }

            Assert.Null(sim.Send("TEMP nobody 50"));
            Assert.True(await Until(() => sim.LastReply == "ERR TEMP nobody 50", 5), sim.LastReply);
            Assert.Null(sim.Send("BOGUS 1"));
            Assert.True(await Until(() => sim.LastReply == "ERR BOGUS 1", 5), sim.LastReply);

            // power cycle: the boards come back by themselves
            Assert.Null(sim.Send(PdmSim.RestartLine(v)));
            Assert.True(await Until(() => sim.LastReply == "OK RESTART A1 A2 B", 5), sim.LastReply);
            rx.Clear();
            Assert.True(await Until(() => rx.Any(f => f.Id == 0x527) && rx.Any(f => f.Id == 0x5A7), 20));
        }
        finally
        {
            await manager.DisconnectAsync();
            if (!bridge.HasExited) bridge.Kill(true);
            bridge.Dispose();
        }
    }
}
