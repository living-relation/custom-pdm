using application.Services;
using domain.Common;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using domain.Interfaces;
using domain.Models;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace CustomPdm.Tests;

// uiwalk (2026-11-21): what the real-life walkthrough of /pdm found (ui/README.md "Walkthrough fixes"): the adapter
// connects by itself at start, a Write All result survives the read on connect after it, the page texts, and the
// ST185 starter project (ui/examples).
public class UiWalkTests
{
    // ---------------- auto-connect ----------------

    private sealed class FakeAdapters : ICommsAdapterManager
    {
        public int FailFirst;
        public bool Throw;
        public List<(string Adapter, string Port, CanBitRate Rate)> Calls { get; } = [];
        private string _asked = "";
        public bool IsConnected { get; set; }
        public ICommsAdapter? ActiveAdapter => null;
        public (string[] adapters, string[] ports) GetAvailable() => ([], []);
        public (bool isConnected, string? activeAdapter, string? activePort, CanBitRate activeBitRate) GetStatus() => (IsConnected, null, null, default);
        public ICommsAdapter ToAdapter(string adapterName) { _asked = adapterName; return null!; }

        public Task<bool> ConnectAsync(ICommsAdapter commsAdapter, string port, CanBitRate bitRate, CancellationToken ct = default)
        {
            Calls.Add((_asked, port, bitRate));
            if (Throw) throw new IOException("connection refused");
            IsConnected = Calls.Count > FailFirst;
            return Task.FromResult(IsConnected);
        }

        public Task<bool> DisconnectAsync() { IsConnected = false; return Task.FromResult(true); }
#pragma warning disable CS0067
        public event EventHandler<CanFrameEventArgs>? DataReceived;
        public event EventHandler? Connected;
        public event EventHandler? Disconnected;
#pragma warning restore CS0067
    }

    private static readonly PdmLastAdapter NoLast = new(null, null, null, CanBitRate.BitRate500K);

    [Fact]
    public void LaunchFlagsBecomeAConnectPlan()
    {
        var (plan, why) = PdmAutoConnect.Plan("SLCAN TCP", "localhost:3333", "1000K", false, NoLast);
        Assert.Null(why);
        Assert.Equal(new PdmAutoConnectPlan("SLCAN TCP", "localhost:3333", CanBitRate.BitRate1000K), plan);
        Assert.Equal(CanBitRate.BitRate500K, PdmAutoConnect.ParseBitRate("500k"));
        Assert.Equal(CanBitRate.BitRate1000K, PdmAutoConnect.ParseBitRate("BitRate1000K"));
        Assert.Null(PdmAutoConnect.ParseBitRate("fast"));
        Assert.Null(PdmAutoConnect.ParseBitRate("7"));

        // no flag: stock behaviour, and nothing to say
        Assert.Equal((null, null), PdmAutoConnect.Plan(null, null, null, false, new PdmLastAdapter("SLCAN TCP", null, "localhost:3333", CanBitRate.BitRate1000K)));
        // wrong flags are refused in words, never guessed
        Assert.Contains("needs --PdmAutoConnect:Port", PdmAutoConnect.Plan("SLCAN TCP", " ", "1000K", false, NoLast).Why);
        Assert.Contains("not a CAN bit rate", PdmAutoConnect.Plan("SLCAN TCP", "localhost:3333", "fast", false, NoLast).Why);
        Assert.Equal("Simulated", PdmAutoConnect.Plan("Sim", null, null, false, NoLast).Plan!.Port);
    }

    [Fact]
    public void LastFlagUsesTheRememberedAdapter()
    {
        var tcp = PdmAutoConnect.Plan(null, null, null, true, new PdmLastAdapter("SLCAN TCP", "COM3", "localhost:3333", CanBitRate.BitRate1000K));
        Assert.Equal(new PdmAutoConnectPlan("SLCAN TCP", "localhost:3333", CanBitRate.BitRate1000K), tcp.Plan);
        var serial = PdmAutoConnect.Plan(null, null, null, true, new PdmLastAdapter("SLCAN", "COM3", "localhost:3333", CanBitRate.BitRate500K));
        Assert.Equal(new PdmAutoConnectPlan("SLCAN", "COM3", CanBitRate.BitRate500K), serial.Plan);
        Assert.Contains("no adapter remembered", PdmAutoConnect.Plan(null, null, null, true, NoLast).Why);
        Assert.Contains("no port remembered", PdmAutoConnect.Plan(null, null, null, true, new PdmLastAdapter("SLCAN", "", null, CanBitRate.BitRate500K)).Why);
    }

    [Fact]
    public async Task AutoConnectRetriesUntilTheBridgeIsUp()
    {
        var plan = new PdmAutoConnectPlan("SLCAN TCP", "localhost:3333", CanBitRate.BitRate1000K);
        var waits = new List<TimeSpan>();
        Task Delay(TimeSpan t, CancellationToken _) { waits.Add(t); return Task.CompletedTask; }

        var late = new FakeAdapters { FailFirst = 2 };
        var (ok, text) = await PdmAutoConnect.RunAsync(late, plan, 10, TimeSpan.FromSeconds(1), Delay);
        Assert.True(ok);
        Assert.Equal("auto-connect: connected to SLCAN TCP localhost:3333 1000K (try 3).", text);
        Assert.Equal(3, late.Calls.Count);
        Assert.All(late.Calls, c => Assert.Equal(("SLCAN TCP", "localhost:3333", CanBitRate.BitRate1000K), c));
        Assert.Equal(2, waits.Count);

        var never = new FakeAdapters { Throw = true };
        (ok, text) = await PdmAutoConnect.RunAsync(never, plan, 3, TimeSpan.FromSeconds(1), Delay);
        Assert.False(ok);
        Assert.Equal("auto-connect: SLCAN TCP localhost:3333 1000K did not connect in 3 tries (connection refused). Use the Adapter button.", text);
        Assert.Equal(3, never.Calls.Count);

        // the user was faster (or another start connected already): nothing is touched
        var already = new FakeAdapters { IsConnected = true };
        (ok, text) = await PdmAutoConnect.RunAsync(already, plan, 3, TimeSpan.FromSeconds(1), Delay);
        Assert.True(ok);
        Assert.Empty(already.Calls);
        Assert.Contains("already connected", text);
    }

    // ---------------- PdmOps: results ----------------

    private static FakePdm ReadPdm()
    {
        var pdm = new FakePdm();
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        return pdm;
    }

    [Fact]
    public void AWriteAllResultSurvivesTheReadOnConnectAfterIt()
    {
        var pdm = ReadPdm();
        pdm.Dev("A1").Outputs[2].CurrentLimit = 5.5;
        Assert.Null(pdm.Run(PdmOpKind.WriteAll));
        var written = PdmOps.Roles.Select(pdm.Line).ToList();
        Assert.All(written, l => Assert.StartsWith("Ok: written OK", l));
        Assert.Null(pdm.Service.Ops.Earlier);

        // B dropped off the bus for a moment during the long write and is read when it is back (PdmAutoRead)
        Assert.Null(pdm.Service.Ops.Start(PdmOpKind.ReadAll, pdm.View, true, pdm.Clock, ["B"]));
        pdm.Settle();
        Assert.True(pdm.Service.Ops.LastOnConnect);
        Assert.Equal("Ok: read OK", pdm.Line("B"));
        var earlier = pdm.Service.Ops.Earlier;
        Assert.NotNull(earlier);
        Assert.Equal(PdmOpKind.WriteAll, earlier.Op);
        Assert.Equal(written, earlier.Results.Select(r => $"{r.State}: {r.Text}"));

        // a second read on connect keeps it; the next run the user starts drops it
        Assert.Null(pdm.Service.Ops.Start(PdmOpKind.ReadAll, pdm.View, true, pdm.Clock, ["A2"]));
        pdm.Settle();
        Assert.Equal(PdmOpKind.WriteAll, pdm.Service.Ops.Earlier?.Op);
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        Assert.Null(pdm.Service.Ops.Earlier);
    }

    [Fact]
    public void ARunningBoardShowsHowLongItHasBeenAtIt()
    {
        var pdm = ReadPdm();
        Assert.Null(pdm.Service.Ops.Running(pdm.Clock));
        Assert.Null(pdm.Service.Start(PdmOpKind.WriteAll, true, pdm.Clock));
        var run = pdm.Service.Ops.Running(pdm.Clock.AddSeconds(75));
        Assert.Equal(("A1", TimeSpan.FromSeconds(75)), run);
        Assert.Equal("1 min 15 s", PdmOps.ElapsedText(run!.Value.For));
        Assert.Equal("9 s", PdmOps.ElapsedText(TimeSpan.FromSeconds(9.9)));
        Assert.Equal("0 s", PdmOps.ElapsedText(TimeSpan.FromSeconds(-1)));
        Assert.False(pdm.Service.Ops.ClearResults());   // never in the middle of a run
        pdm.Settle();
        Assert.Null(pdm.Service.Ops.Running(pdm.Clock));
    }

    [Fact]
    public void ANewProjectDoesNotShowTheOldBoardsResults()
    {
        var pdm = ReadPdm();
        Assert.Equal(3, pdm.Service.Ops.Results.Count);
        pdm.Rounds(1);                      // the same boards: the lines stay
        Assert.Equal(3, pdm.Service.Ops.Results.Count);
        pdm.Mgr.ClearDevices();             // File > New
        pdm.Service.Tick(pdm.Clock);
        Assert.Empty(pdm.Service.Ops.Results);
        Assert.Null(pdm.Service.Ops.LastOp);
        Assert.False(pdm.Service.Ops.LastOnConnect);
    }

    // ---------------- page texts ----------------

    [Fact]
    public void OffLinesNameEveryButtonThatIsOff()
    {
        Assert.Equal(["Read All, Write All and Burn are off: CAN adapter not connected."],
            PdmPageText.OffLines(PdmOps.AdapterOffReason, PdmOps.AdapterOffReason, PdmOps.AdapterOffReason));
        Assert.Equal(["Write All and Burn are off: B: offline."], PdmPageText.OffLines(null, "B: offline.", "B: offline."));
        Assert.Equal(["Read All is off: r", "Write All is off: w", "Burn is off: b"], PdmPageText.OffLines("r", "w", "b"));
        Assert.Equal(["Read All and Burn are off: x", "Write All is off: w"], PdmPageText.OffLines("x", "w", "x"));
        Assert.Empty(PdmPageText.OffLines(null, null, null));
    }

    [Fact]
    public void AnOfflineBoardIsSaidAtTheTopOfThePage()
    {
        var pdm = new FakePdm();
        Assert.Null(PdmPageText.OfflineLine(pdm.View, true, _ => true));
        Assert.Null(PdmPageText.OfflineLine(pdm.View, false, _ => false));   // no adapter: the off lines say it
        var one = PdmPageText.OfflineLine(pdm.View, true, d => d.Name != "B");
        Assert.StartsWith("B is offline (no CAN messages). Its outputs and inputs below show the last values received", one);
        var all = PdmPageText.OfflineLine(pdm.View, true, _ => false);
        Assert.StartsWith("A1, A2, B are offline (no CAN messages: check power, the CAN wiring and the bit rate). Their outputs", all);
    }

    [Fact]
    public void TriggerWordsGetTheInputNames()
    {
        var pdm = new FakePdm();
        pdm.Dev("B").DigitalInputs[0].Name = "Ignition";      // IN15
        pdm.Dev("A2").DigitalInputs[1].Name = "Turn R sw";    // IN9
        var v = pdm.View;
        Assert.Equal("IN15 = Ignition, IN9 = Turn R sw", PdmPageText.InputNames(v, "IN15 AND IN9, on-delay 2 s"));
        Assert.Equal("IN15 = Ignition", PdmPageText.InputNames(v, "IN15 OR IN15 OR IN3"));   // IN3 has its stock name
        Assert.Equal("", PdmPageText.InputNames(v, "ECU 0x3F4 byte 0 = 1"));
        Assert.Equal("", PdmPageText.InputNames(v, "WIN15 or IN150"));                       // whole numbers only
        Assert.Equal("", PdmPageText.InputNames(v, null));
    }

    [Fact]
    public void SeveralBoardsAskingIsOneQuestion()
    {
        // uipolish: the question speaks of the PDM, not of boards, when all three ask
        Assert.Equal("The PDM is connected. The PC holds the New PDM settings, not written yet. Which settings do you want?",
            PdmPageText.ConnectAskText(["A1", "A2", "B"], PdmAskKind.NewPdm));
        Assert.Equal("A1, B connected. The PC has changes that are not on the PDM yet. Which settings do you want?",
            PdmPageText.ConnectAskText(["A1", "B"], PdmAskKind.Edits));
        Assert.Equal("The PDM is connected. The PC holds the settings of the project file; the PDM may hold other ones. Which settings do you want?",
            PdmPageText.ConnectAskText(["B", "A1", "A2"], PdmAskKind.ProjectFile));
        Assert.Equal(("Keep the PC's settings (write them to the PDM)", "Take the PDM's settings"),
            (PdmPageText.KeepPcButton, PdmPageText.TakePdmButton));
    }

    // uipolish: Enter in the Open File dialog's Path field
    [Theory]
    [InlineData("  C:\\cars\\st185.json  ", "C:\\cars\\st185.json")]
    [InlineData("\"C:\\my cars\\st185.json\"", "C:\\my cars\\st185.json")]
    [InlineData(" 'C:\\my cars' ", "C:\\my cars")]
    [InlineData("\" C:\\x \"", "C:\\x")]
    [InlineData("", "")]
    [InlineData(null, "")]
    public void ATypedPathLosesSpacesAndQuotes(string? typed, string path) => Assert.Equal(path, PdmPageText.TypedPath(typed));

    [Fact]
    public void ABoardInARunIsNotAskedAboutUntilTheRunEnds()
    {
        PdmBoardResult[] run =
        [
            new("A1", PdmStepState.Ok, "written OK"), new("A2", PdmStepState.Running, "writing ..."),
            new("B", PdmStepState.Waiting, "waiting")
        ];
        Assert.True(PdmPageText.AskNow("A1", true, run));     // done already: its question is a real one
        Assert.False(PdmPageText.AskNow("A2", true, run));
        Assert.False(PdmPageText.AskNow("B", true, run));
        Assert.All(PdmOps.Roles, r => Assert.True(PdmPageText.AskNow(r, false, run)));   // the run is over
        Assert.True(PdmPageText.AskNow("A2", true, []));
    }

    // ---------------- the ST185 starter (ui/examples) ----------------

    private static (DeviceManager Mgr, PdmOpsService Service) NewApp()
    {
        var mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance,
            new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs")), new FwDeviceDefManager());
        mgr.SetBatchTransmitCallback(_ => { });
        return (mgr, new PdmOpsService(mgr, _ => true) { AutoTick = false });
    }

    private static string StarterPath()
    {
        var path = PdmStarter.Find(AppContext.BaseDirectory);
        Assert.NotNull(path);
        Assert.EndsWith(Path.Combine("ui", "examples", PdmStarter.FileName), path);
        return path;
    }

    [Fact]
    public async Task TheStarterLoadsAsAWritablePdmWithItsFunctionsInWords()
    {
        var (mgr, service) = NewApp();
        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
        Assert.Null(await PdmStarter.LoadAsync(StarterPath(), files, mgr, service.Ops));
        Assert.Null(files.CurrentFilePath);                 // Save asks for a name: never written back into ui/examples
        var v = service.BuildView();
        Assert.Equal(["A1", "A2", "B"], v.Boards.Select(b => b.Role));
        Assert.Empty(v.Problems);
        Assert.All(v.Boards, b => Assert.True(b.Device.CustomPdm!.FactoryNew));
        Assert.Null(service.BlockedReason(PdmOpKind.WriteAll, v, true));   // writable without a Read All, as a New PDM

        string Name(int n) => v.Outputs.Single(o => o.Number == n).Output.Name;
        Assert.Equal(("Radiator fan", "Condenser fan", "Fuel pump", "Low beams", "Horn", "Turn left"),
            (Name(17), Name(18), Name(19), Name(1), Name(5), Name(9)));
        Assert.Equal("Ignition", v.Inputs.Single(i => i.Number == 15).Name);
        Assert.Equal(PdmDeviceKind.FuelPump, PdmPresets.KindOf(v, v.Outputs.Single(o => o.Number == 19)));
        Assert.Equal((25.0, 100.0, 500), (v.Outputs[18].Output.CurrentLimit, v.Outputs[18].Output.InrushCurrentLimit, v.Outputs[18].Output.InrushTime));

        var m = PdmModel.Build(v);
        string Words(int n) => PdmTriggers.Of(m, n).Words;
        Assert.Equal("ECU 0x3F4 byte 0 = 1 (ECU only; off 1 s after the ECU frames stop)", Words(19));
        Assert.Equal("ECU 0x3F4 byte 1 = 1 (ECU only; on 1 s after the ECU frames stop; off until the first frame)", Words(18));
        Assert.Equal("B CAN input 5 'ECU coolant' value on at 92 or more, off at 88 or less", Words(17));
        Assert.Equal("IN2 AND IN1", Words(2));
        Assert.Equal("IN15, off-delay 5 s", Words(8));
        Assert.Equal(("IN15", "IN15", "IN1", "IN5"), (Words(7), Words(21), Words(1), Words(5)));
        Assert.StartsWith("turn signal LEFT: IN8 or hazard IN10, flashing 350 / 350 ms", Words(9));
        Assert.StartsWith("turn signal RIGHT: IN9 or hazard IN10", Words(11));
        Assert.StartsWith("wiper motor run (wiper on B: switches slow IN16, fast IN17, intermittent IN19; park cam IN18", Words(23));
        Assert.Contains("keypad 0x28 button 1", Words(22));
        Assert.Contains("fan logic", Words(10));           // A2 OUT2 still runs the box fans
        Assert.Equal("IN15 = Ignition", PdmPageText.InputNames(v, Words(8)));
    }

    // Why the starter may be loaded "as a New PDM": everything a wrong file could break is what New PDM sets
    [Fact]
    public async Task TheStartersCriticalSettingsAreTheFactoryOnes()
    {
        var (mgr, service) = NewApp();
        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
        Assert.Null(await PdmStarter.LoadAsync(StarterPath(), files, mgr, service.Ops));
        var (mgr2, factory) = NewApp();
        Assert.Null(factory.NewPdm());
        _ = mgr2;

        static List<string> Block(FwDevice d) => d.Params.Where(p => p.Index == CustomPdmSettings.BaseIndex)
            .Select(p => $"{p.Name} {p.SubIndex} = {p.GetValue()}").ToList();
        foreach (var role in PdmOps.Roles)
        {
            var s = service.BuildView().Boards.Single(b => b.Role == role).Device;
            var f = factory.BuildView().Boards.Single(b => b.Role == role).Device;
            Assert.Equal((f.BaseId, f.BitRate, f.Type), (s.BaseId, s.BitRate, s.Type));
            Assert.Equal(CanBitRate.BitRate1000K, s.BitRate);
            Assert.NotEmpty(Block(f));
            Assert.Equal(Block(f), Block(s));   // 0x7F00: temperature limits, outputs kept on at critical, wake inputs
        }
    }

    // Found with the starter on the simulated boards: Write All failed on A1 ("Write Param Out of Range -
    // rotarySwitch[1].step"), because the params of a loaded analog input read the constructor's objects, not the file's
    [Fact]
    public void ALoadedAnalogInputWritesTheValuesOfItsFile()
    {
        var a = new domain.Devices.Functions.AnalogInput(1, "analogInput1");
        a.Switch.Threshold = 2000;
        a.Rotary.Step = 100;
        a.Rotary.MaxPos = 10;
        var json = System.Text.Json.JsonSerializer.Serialize(a);
        var back = System.Text.Json.JsonSerializer.Deserialize<domain.Devices.Functions.AnalogInput>(json)!;
        double V(domain.Devices.Functions.AnalogInput x, string name) => Convert.ToDouble(x.Params.Single(p => p.Name.EndsWith(name)).GetValue());
        Assert.Equal((2000, 100, 10), (V(a, ".threshold"), V(a, ".step"), V(a, ".maxpos")));
        Assert.Equal((2000, 100, 10), (V(back, ".threshold"), V(back, ".step"), V(back, ".maxpos")));
        Assert.Equal(a.Params.Select(p => (p.Name, p.Index, p.SubIndex)), back.Params.Select(p => (p.Name, p.Index, p.SubIndex)));
        // and a read from the board lands in the object the file gave (the one the UI shows)
        back.Params.Single(p => p.Name.EndsWith(".step")).SetValue(250.0);
        Assert.Equal(250.0, back.Rotary.Step);
    }

    // Every param the starter writes, as the 4 bytes on the wire, against a New PDM: only the blocks the example set
    // up may differ (a param that does not survive the project file would show up here, in a block nobody touched)
    [Fact]
    public async Task TheStarterDiffersFromANewPdmOnlyWhereTheExampleSetSomething()
    {
        var (mgr, service) = NewApp();
        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
        Assert.Null(await PdmStarter.LoadAsync(StarterPath(), files, mgr, service.Ops));
        var (_, factory) = NewApp();
        Assert.Null(factory.NewPdm());

        static List<(string Name, int Index, int Sub, string Bytes)> Raw(FwDevice d) => d.Params
            .Select(p => (p.Name, p.Index, p.SubIndex, Convert.ToHexString(ParamCodec.ToFrame(MessageCommand.Write, p, 0).Payload, 4, 4))).ToList();
        var touched = new HashSet<string>();
        var detail = new List<string>();
        foreach (var role in PdmOps.Roles)
        {
            var s = Raw(service.BuildView().Boards.Single(b => b.Role == role).Device);
            var f = Raw(factory.BuildView().Boards.Single(b => b.Role == role).Device);
            Assert.Equal(f.Select(p => (p.Name, p.Index, p.Sub)), s.Select(p => (p.Name, p.Index, p.Sub)));   // same params, same order
            foreach (var (a, b) in s.Zip(f).Where(x => x.First.Bytes != x.Second.Bytes))
            {
                var block = a.Name.Split('[', '.')[0];
                touched.Add($"{role} 0x{a.Index & 0xFF00:X4} {block}");
                if (!SetUpByTheExample.Contains(block)) detail.Add($"{role} {a.Name} 0x{a.Index:X4}:{a.Sub} starter {a.Bytes} factory {b.Bytes}");
            }
        }

        var blocks = touched.Select(t => t.Split(' ', 3)[2]).Distinct().Order().ToList();
        Assert.True(blocks.All(b => SetUpByTheExample.Contains(b)), "params outside the example: " + string.Join("; ", detail.Take(12)) + " | blocks that differ: " + string.Join(", ", blocks));
    }

    private static readonly string[] SetUpByTheExample =
    [
        "output", "input", "canInput", "virtualInput", "condition", "timer", "flasher", "wiper", "customPdm"
    ];

    [Fact]
    public async Task AFileThatIsNotThePdmIsNotLoadedAsAStarter()
    {
        var stock = new FakePdm();   // hand-added devices: stock dingoPDM defaults (500K)
        Assert.Equal("A1 is not on 1000K.", PdmStarter.Problem([stock.Dev("A1"), stock.Dev("A2"), stock.Dev("B")]));
        Assert.Equal("B is missing.", PdmStarter.Problem([ReadPdm().Dev("A1"), ReadPdm().Dev("A2")]));
        Assert.Null(PdmStarter.Find(Path.GetPathRoot(Path.GetTempPath())!));

        var (mgr, service) = NewApp();
        Assert.Null(service.NewPdm());
        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
        var missing = Path.Combine(Path.GetTempPath(), "cpdm-no-such-starter.json");
        Assert.Equal("The starter file could not be read.", await PdmStarter.LoadAsync(missing, files, mgr, service.Ops));
        Assert.Equal(3, service.BuildView().Boards.Count);   // the project in the app is untouched
    }
}
