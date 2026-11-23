using application.Services;
using Bunit;
using domain.CustomPdm;
using domain.Enums;
using domain.Interfaces;
using domain.Models;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using MudBlazor;
using MudBlazor.Services;
using web.Components.CustomPdm;
using web.Services;
using Xunit;

namespace CustomPdm.Tests;

// canboard: the /pdm "CANBoard" card and the simulated CANBoard of the Simulator panel themselves (bUnit), and the
// service between that panel and the bridge (stand-in adapter).
public class PdmCanBoardPanelTests : BunitContext, IAsyncLifetime
{
    private sealed class FakeLink : ICommsAdapter, IPdmSimLink
    {
        public string? Name => PdmSim.BridgeAdapter;
        public List<string> Got { get; } = [];
        public event Action<string>? SimLine;
        public bool SendSimLine(string line) { Got.Add(line); return true; }
        public void Say(string line) => SimLine?.Invoke(line);
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
        public void Frame(int id, params byte[] data) => DataReceived?.Invoke(this, new CanFrameEventArgs(new CanFrame(id, data.Length, data)));
        public (string[] adapters, string[] ports) GetAvailable() => ([], []);
        public (bool isConnected, string? activeAdapter, string? activePort, CanBitRate activeBitRate) GetStatus() => (IsConnected, null, null, default);
        public ICommsAdapter ToAdapter(string adapterName) => null!;
        public Task<bool> ConnectAsync(ICommsAdapter commsAdapter, string port, CanBitRate bitRate, CancellationToken ct = default) => Task.FromResult(true);
        public Task<bool> DisconnectAsync() => Task.FromResult(true);
        public event EventHandler? Connected;
        public event EventHandler? Disconnected;
        public event EventHandler<CanFrameEventArgs>? DataReceived;
    }

    private readonly FakeManager _mgr = new();
    private readonly FakeLink _link = new();
    private readonly PdmSimService _sim;
    private long _now = 1000;

    public PdmCanBoardPanelTests()
    {
        JSInterop.Mode = JSRuntimeMode.Loose;
        Services.AddMudServices();
        var log = new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs"));
        var mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance, log, new FwDeviceDefManager());
        _sim = new PdmSimService(_mgr) { Clock = () => _now };
        Services.AddSingleton(log);
        Services.AddSingleton(new PdmOpsService(mgr));
        Services.AddSingleton(_sim);
        Services.AddSingleton<ICommsAdapterManager>(_mgr);
        Services.AddScoped<NotificationService>();
        Render<MudPopoverProvider>();
    }

    Task IAsyncLifetime.InitializeAsync() => Task.CompletedTask;
    Task IAsyncLifetime.DisposeAsync() => DisposeAsync().AsTask();

    private void Bridge()
    {
        _mgr.Connect(_link);
        _link.Say("!SIM custom-pdm");
        _link.Got.Clear();
    }

    [Fact]
    public void AddCanBoardIsOneClickAndTheCardSaysWhatToSetOnTheCanBoard()
    {
        var v = PdmLinkedTests.NewPdm();
        var cut = Render<PdmCanBoardPanel>(p => p.Add(x => x.View, v));
        Assert.Contains("Add CANBoard", cut.Markup);
        Assert.Equal("640", cut.Find("#pdm-cb-base").GetAttribute("value"));             // the firmware's default base ID
        Assert.Contains("Uses 13 of the PDM's 92 free CAN inputs and the IDs 0x640-0x652", cut.Find("#pdm-cb-hint").TextContent);
        Assert.Contains("One CANBoard adds about 1.4 % bus load", cut.Find("#pdm-cb-hint").TextContent);
        Assert.DoesNotContain("No board", cut.Markup);                                    // PDM-wide: no board question
        Assert.Empty(cut.FindAll("#pdm-cb-640"));

        // a base ID inside the PDM's own IDs: said in plain words, the button is off
        cut.Find("#pdm-cb-base").Input("510");
        Assert.Contains("A CANBoard at 0x510 uses 0x510-0x522: that overlaps board A1's own IDs (0x500-0x53F). Pick another base ID, e.g. 0x640.", cut.Find("#pdm-cb-hint").TextContent);
        Assert.True(cut.Find("#pdm-cb-add").HasAttribute("disabled"));
        cut.Find("#pdm-cb-base").Input("zz");
        Assert.Contains("The base ID is a hex number, e.g. 640.", cut.Find("#pdm-cb-hint").TextContent);
        Assert.True(cut.Find("#pdm-cb-add").HasAttribute("disabled"));
        Assert.Empty(PdmCanBoard.All(v));

        cut.Find("#pdm-cb-base").Input("640");
        Assert.False(cut.Find("#pdm-cb-add").HasAttribute("disabled"));
        cut.Find("#pdm-cb-base").Blur();                                                  // the click takes the focus, as in a browser
        cut.Find("#pdm-cb-add").Click();
        cut.WaitForAssertion(() => Assert.Single(PdmCanBoard.All(v)));
        var cb = Assert.Single(PdmCanBoard.All(v));
        Assert.Equal(("CANBoard 1", 0x640, 13), (cb.Name, cb.BaseId, cb.Inputs.Count));
        var card = cut.Find("#pdm-cb-640");
        Assert.Contains("CANBoard 1", card.TextContent);
        Assert.Contains("IDs 0x640-0x652", card.TextContent);
        Assert.Contains("Inputs: CANBoard 1 switch 1-8, analog 1-5 (mV).", card.TextContent);
        Assert.Contains("they read off and 0 mV after 1 s", System.Text.RegularExpressions.Regex.Replace(card.TextContent, @"\s+", " "));
        Assert.Contains("CAN bit rate: 1000K (a new CANBoard is on 500K", card.TextContent);
        Assert.Contains("Base ID: 0x640 (its factory value).", card.TextContent);
        Assert.Equal(4, cut.FindAll(".pdm-cb-out").Count);
        Assert.Equal("660", cut.Find("#pdm-cb-base").GetAttribute("value"));             // the next free base for a second one
        Assert.Contains("1 CANBoard: about 1.4 % bus load added", cut.Find("#pdm-cb-hint").TextContent);

        // an output set in the model shows as a step for the CANBoard; Remove takes the card away
        var b = v.Boards.Single(x => x.Role == "B").Device;
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 2, "B", PdmFactoryDefaults.VarOf(b, b.DigitalInputs[0])));
        cut.Render(p => p.Add(x => x.View, v));
        Assert.Contains("Output 2: CAN input 2 = ID 0x652, start bit 8, 8 bits, Equal 1, time-out on, 1000 ms; digital output 2 enabled, input = CAN input 2.", cut.Find(".pdm-cb-steps").TextContent);
        cut.Find(".pdm-cb-remove").Click();
        cut.WaitForAssertion(() => Assert.Empty(PdmCanBoard.All(v)));   // MudButton's click handler is async: bUnit's Click() does not wait for it
        Assert.Empty(cut.FindAll("#pdm-cb-640"));
    }

    [Fact]
    public void TooFewFreeCanInputsTurnsTheButtonOffWithTheCount()
    {
        var v = PdmLinkedTests.NewPdm();
        foreach (var q in v.Boards)
        foreach (var c in q.Device.CanInputs.Skip(q.Role == "B" ? 12 : 0)) (c.Enabled, c.Id) = (true, 0x7A0);
        var cut = Render<PdmCanBoardPanel>(p => p.Add(x => x.View, v));
        Assert.Contains("It needs 13 free CAN inputs on the PDM; only 12 are free (A1 0, A2 0, B 12).", cut.Find("#pdm-cb-hint").TextContent);
        Assert.True(cut.Find("#pdm-cb-add").HasAttribute("disabled"));
    }

    [Fact]
    public void TheServiceKeepsOnlyTheWatchedFramesAndKnowsWhenACanBoardIsSilent()
    {
        Bridge();
        Assert.False(_sim.CanBoard(0x640).Alive);
        _mgr.Frame(0x644, 0, 0, 0, 0, 0x04, 0, 0x02, 9);          // not watched yet: dropped
        Assert.False(_sim.CanBoard(0x640).Alive);
        _sim.Watch([0x640]);
        _mgr.Frame(0x644, 0x30, 0, 0, 0, 0x04, 0, 0x02, 9);
        _mgr.Frame(0x642, 0x10, 0x27, 0, 0, 0, 0, 0, 0);
        _mgr.Frame(0x643, 0xE8, 0x03, 0, 0, 0, 0, 30, 0);
        _mgr.Frame(0x664, 0, 0, 0, 0, 0xFF, 0, 0x0F, 1);          // another CANBoard: not watched
        var live = _sim.CanBoard(0x640);
        Assert.True(live.Alive);
        Assert.Equal((true, 3, 10000, 1000, true, 9), (live.Switches[2], live.Rotary[1], live.Mv[0], live.Mv[4], live.Outputs[1], live.Heartbeat));
        Assert.False(_sim.CanBoard(0x660).Alive);
        _now += PdmCanBoardSim.StaleMs;
        Assert.True(_sim.CanBoard(0x640).Alive);
        _now += 1;
        Assert.False(_sim.CanBoard(0x640).Alive);                  // no state frame for more than 350 ms
        Assert.True(_sim.CanBoard(0x640).Switches[2]);             // the last known values stay on show
        _mgr.Frame(0x644, 0, 0, 0, 0, 0, 0, 0, 10);
        Assert.True(_sim.CanBoard(0x640).Alive);
        _mgr.Drop();                                               // adapter gone: nothing is alive, nothing kept
        Assert.False(_sim.CanBoard(0x640).Alive);
        Assert.False(_sim.CanBoard(0x640).Switches[2]);
    }

    [Fact]
    public void PlugInPutsTheSimulatedCanBoardOnTheBusSetAsTheCardSays()
    {
        var v = PdmLinkedTests.NewPdm();
        Assert.Null(PdmCanBoard.Add(v, 0x640, "Wheel", rotary: true));
        var b = v.Boards.Single(x => x.Role == "B").Device;
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 2, "B", PdmFactoryDefaults.VarOf(b, b.DigitalInputs[0])));
        var cb = PdmCanBoard.All(v).Single();
        Assert.Equal(PdmSimService.NotSimReason, _sim.PlugCanBoard(cb));             // no bridge: nothing sent
        Bridge();
        Assert.Null(_sim.PlugCanBoard(cb));
        Assert.Equal(["!CB 640 ADD", "!CB 640 LINK on", "!CB 640 OUT 0 off", "!CB 640 OUT 1 652 8 1000", "!CB 640 OUT 2 off", "!CB 640 OUT 3 off"], _link.Got);
        _link.Got.Clear();
        Assert.Null(_sim.SyncCanBoard(cb));                                          // unchanged: not sent again
        Assert.Empty(_link.Got);
        Assert.Null(PdmCanBoard.SetOutput(v, 0x640, 3, "B", PdmFactoryDefaults.VarOf(b, b.DigitalInputs[1])));
        Assert.Null(_sim.SyncCanBoard(PdmCanBoard.All(v).Single()));
        Assert.Equal(["!CB 640 OUT 0 off", "!CB 640 OUT 1 652 8 1000", "!CB 640 OUT 2 652 16 1000", "!CB 640 OUT 3 off"], _link.Got);

        // the panel: silent until its frames come, then switches / sliders / output lamps from the frames
        _sim.Watch([]);
        var cut = Render<PdmCanBoardSimPanel>(p => p.Add(x => x.View, v));
        var box = cut.Find("#pdm-sim-cb-640");
        Assert.Contains("Simulated CANBoard: Wheel", box.TextContent);
        Assert.Contains("not on the bus (silent)", cut.Find(".pdm-sim-cb-state").TextContent);
        Assert.Equal(8, cut.FindAll(".pdm-sim-cb-sw").Count);
        Assert.Equal(5, cut.FindAll(".pdm-sim-cb-an").Count);
        Assert.Equal(5, cut.FindAll(".pdm-sim-cb-rot").Count);
        Assert.Equal(4, cut.FindAll(".pdm-sim-cb-out").Count);
        _mgr.Frame(0x642, 0, 0, 0x28, 0x0A, 0, 0, 0, 0);                             // analog 2 = 2600 mV
        _mgr.Frame(0x644, 0, 0, 0, 0, 0x04, 0, 0x02, 1);                             // switch 3 on, output 2 on
        cut.Render(p => p.Add(x => x.View, v));
        Assert.Contains("on the bus", cut.Find(".pdm-sim-cb-state").TextContent);
        Assert.DoesNotContain("silent", cut.Find(".pdm-sim-cb-state").TextContent);
        Assert.Contains("2: 2600 mV", cut.Find(".pdm-sim-cb-an-2").TextContent);
        Assert.Contains("2: ON", cut.Find(".pdm-sim-cb-out-2").TextContent);
        Assert.Contains("1: off (follows nothing)", System.Text.RegularExpressions.Regex.Replace(cut.Find(".pdm-sim-cb-out-1").TextContent, @"\s+", " "));
        Assert.Contains("3: off", cut.Find(".pdm-sim-cb-out-3").TextContent);
        Assert.DoesNotContain("follows nothing", cut.Find(".pdm-sim-cb-out-3").TextContent);

        // Unplug sends the link line; a project without rotary positions shows no rotary row
        _link.Got.Clear();
        cut.Find(".pdm-sim-cb-unplug").Click();
        cut.WaitForAssertion(() => Assert.Equal(["!CB 640 LINK off"], _link.Got));
        _link.Got.Clear();
        cut.Find(".pdm-sim-cb-plug").Click();
        cut.WaitForAssertion(() => Assert.Equal("!CB 640 ADD", Assert.Single(_link.Got.Take(1))));
        var w = PdmLinkedTests.NewPdm();
        Assert.Null(PdmCanBoard.Add(w, 0x660, null));
        var plain = Render<PdmCanBoardSimPanel>(p => p.Add(x => x.View, w));
        Assert.Empty(plain.FindAll(".pdm-sim-cb-rot"));
        Assert.Empty(Render<PdmCanBoardSimPanel>(p => p.Add(x => x.View, PdmLinkedTests.NewPdm())).FindAll(".mud-paper"));   // no CANBoard: nothing
    }
}
