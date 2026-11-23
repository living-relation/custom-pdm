using application.Services;
using domain.Common;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace CustomPdm.Tests;

// carsim (2026-11-23): the ST185 car config (ui/examples/st185-car.dummy.json, DUMMY / demo) is exactly what the map in
// St185Car.cs builds; the doc (docs/st185-car-config.dummy.md), the drive-cycle param file
// (firmware/sim/data/st185-car.params.dummy.tsv)
// follow it; no ECU <-> PDM CAN frame is needed (Dan 2026-11-23 07:44: the ECU's loads stay off the PDM). Regenerate: $env:CUSTOMPDM_WRITE_CAR_CONFIG='1'; dotnet test --filter St185CarTests
public class St185CarTests
{
    internal static (DeviceManager Mgr, PdmOpsService Service) NewApp()
    {
        var mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance,
            new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs")), new FwDeviceDefManager());
        mgr.SetBatchTransmitCallback(_ => { });
        return (mgr, new PdmOpsService(mgr, _ => true) { AutoTick = false });
    }

    private static ConfigFileManager Files() => new(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
    private static bool Write => Environment.GetEnvironmentVariable("CUSTOMPDM_WRITE_CAR_CONFIG") == "1";

    internal static string CarPath()
    {
        var path = PdmStarter.Find(AppContext.BaseDirectory, PdmStarter.CarFileName);
        Assert.NotNull(path);
        Assert.EndsWith(Path.Combine("ui", "examples", PdmStarter.CarFileName), path);
        return path;
    }

    private static string ExamplesDir()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (!Directory.Exists(Path.Combine(dir!.FullName, "ui", "examples"))) dir = dir.Parent;
        return Path.Combine(dir.FullName, "ui", "examples");
    }

    internal static string Root() => new DirectoryInfo(ExamplesDir()).Parent!.Parent!.FullName;

    private static PdmOpsService Built()
    {
        var (_, svc) = NewApp();
        Assert.Null(svc.NewPdm());
        St185Car.Build(svc.BuildView());
        return svc;
    }

    private static async Task<PdmOpsService> Loaded()
    {
        var (mgr, svc) = NewApp();
        Assert.Null(await PdmStarter.LoadAsync(CarPath(), Files(), mgr, svc.Ops, "car config"));
        return svc;
    }

    private static List<(string Name, int Index, int Sub, string Bytes)> Raw(FwDevice d) => d.Params
        .Select(p => (p.Name, p.Index, p.SubIndex, Convert.ToHexString(ParamCodec.ToFrame(MessageCommand.Write, p, 0).Payload, 4, 4))).ToList();

    [Fact]
    public async Task TheCarFileIsWhatTheMapBuilds()
    {
        var built = Built();
        if (Write)
            await Files().SaveDevices(built.BuildView().Boards.Select(b => (domain.Interfaces.IDevice)b.Device).ToList(),
                Path.Combine(ExamplesDir(), PdmStarter.CarFileName));
        var loaded = await Loaded();
        foreach (var role in PdmOps.Roles)
        {
            var b = built.BuildView().Boards.Single(x => x.Role == role).Device;
            var l = loaded.BuildView().Boards.Single(x => x.Role == role).Device;
            Assert.Equal(Raw(b), Raw(l));
            Assert.Equal(b.Outputs.Select(o => o.Name), l.Outputs.Select(o => o.Name));
            Assert.Equal(b.DigitalInputs.Select(i => i.Name), l.DigitalInputs.Select(i => i.Name));
            Assert.Equal(b.CustomPdm!.OutputPresets, l.CustomPdm!.OutputPresets);
        }
    }

    // the wire values (as Write All sends them) for the firmware drive cycle s5 --car (as StarterParamsExportTests)
    public const string ParamsRelPath = "firmware/sim/data/st185-car.params.dummy.tsv";

    [Fact]
    public async Task TheDriveCycleParamFileIsTheCarConfig()
    {
        var svc = await Loaded();
        var want = new List<string>
        {
            "# DUMMY TEST COPY - not a source of truth: the wire values (4 bytes, as Write All sends them) of ui/examples/st185-car.dummy.json "
            + "(a DUMMY / demo car config, docs/st185-car-config.dummy.md), written by ui/tests/CustomPdm.Tests/St185CarTests.cs",
            "# role\tindex\tsub\tbytes\tname"
        };
        foreach (var role in PdmOps.Roles)
            want.AddRange(svc.BuildView().Boards.Single(b => b.Role == role).Device.Params.Select(p =>
                $"{role}\t0x{p.Index:X4}\t{p.SubIndex}\t{Convert.ToHexString(ParamCodec.ToFrame(MessageCommand.Write, p, 0).Payload, 4, 4)}\t{p.Name}"));
        var path = Path.Combine(Root(), ParamsRelPath);
        if (Write) File.WriteAllText(path, string.Join("\n", want) + "\n");
        Assert.True(File.Exists(path), $"{ParamsRelPath} missing: run the tests once with CUSTOMPDM_WRITE_CAR_CONFIG=1");
        Assert.Equal(want, File.ReadAllText(path).Replace("\r\n", "\n").TrimEnd('\n').Split('\n'));
    }

    [Fact]
    public async Task TheCarConfigLoadsAsAWritablePdmWithEveryFunctionInWords()
    {
        var svc = await Loaded();
        var v = svc.BuildView();
        Assert.Equal(["A1", "A2", "B"], v.Boards.Select(b => b.Role));
        Assert.Empty(v.Problems);
        Assert.All(v.Boards, b => Assert.True(b.Device.CustomPdm!.FactoryNew));
        Assert.Null(svc.BlockedReason(PdmOpKind.WriteAll, v, true));
        var m = PdmModel.Build(v);
        Assert.Empty(m.Problems);
        Assert.Empty(v.OverRating);
        var dump = Environment.GetEnvironmentVariable("CUSTOMPDM_DUMP_CAR");
        if (!string.IsNullOrEmpty(dump))
            File.WriteAllLines(dump, St185Car.Functions(v)
                .Concat(v.Outputs.Select(o => $"ROW | {o.Number} | {o.Board} OUT{o.BoardOutput} | {o.Connector} | {PdmTriggers.Of(m, o.Number).Words}"))
                .Concat(v.Inputs.Where(r => r.Digital != null).Select(i => $"IN | IN{i.Number} | {i.Board} IN{i.BoardInput} | {i.Connector} |")));

        string Words(int n) => PdmTriggers.Of(m, n).Words;
        Assert.Equal("IN1", Words(1));
        Assert.Equal("IN2 AND IN1", Words(2));
        Assert.Equal("IN3 AND IN5 AND NOT IN1", Words(3));
        Assert.Equal("IN6", Words(4));
        Assert.Equal("IN4", Words(5));
        Assert.Equal(("IN5", "IN5", "IN21", "IN16", "IN16", "IN24"), (Words(7), Words(8), Words(16), Words(17), Words(21), Words(22)));
        Assert.Equal(("IN7 (link: keeps its last state (off at power-up))", "IN7 (link: keeps its last state (off at power-up))"), (Words(14), Words(15)));   // lamps hold at loss
        Assert.Equal("turn signal LEFT: IN8 or hazard IN9, flashing 350 / 350 ms in step with output 11", Words(9));
        Assert.Equal("pop-up LH motor: up on (IN3 and IN5) or IN1, down on IN23 (not while up); stops at its own limit contacts IN11 (top) / IN12 (bottom)", Words(12));
        Assert.Equal("pop-up RH motor: up on (IN3 and IN5) or IN1, down on IN23 (not while up); stops at its own limit contacts IN13 (top) / IN14 (bottom)", Words(13));
        Assert.StartsWith("IN22 AND IN16 AND NOT B virtual input", Words(20));
        Assert.StartsWith("wiper motor run (wiper on B:", Words(23));
        Assert.Contains("fan logic", Words(10));           // A2 OUT2 still runs the box fans
        // every output but the box fans and three spares (A1 OUT6, B OUT2 / OUT3, 31 A) is a car load
        var spare = Enumerable.Range(1, 24).Except([10]).Except(St185Car.Loads.Select(l => l.Number)).ToList();
        Assert.Equal([6, 18, 19], spare);
        Assert.All(spare, n => Assert.Equal("none", Words(n)));

        foreach (var l in St185Car.Loads)
        {
            var o = v.Outputs.Single(r => r.Number == l.Number);
            Assert.Equal((l.Name, true), (o.Output.Name, o.Output.Enabled));
            Assert.Equal(l.Kind, PdmPresets.KindOf(v, o));
            Assert.True(o.Output.CurrentLimit <= Math.Min(o.RatingA, l.St185FuseA), $"output {l.Number}: {o.Output.CurrentLimit} A over its rating or the st185 fuse");
            Assert.NotEqual("none", Words(l.Number));
        }
        foreach (var s in St185Car.Switches)
        {
            var i = v.Inputs.Single(r => r.Number == s.Number);
            Assert.Equal((s.Name, true, s.GroundActive, s.GroundActive ? InputPull.PullUp : InputPull.PullDown, s.Latched ? InputMode.Latched : InputMode.Momentary),
                (i.Name, i.Digital!.Enabled, i.Digital.Invert, i.Digital.Pull, i.Digital.Mode));
        }
    }

    // Dan 2026-11-23: the ECU controls and powers its own loads (no PDM output, no ECU command on the PDM); what the EFI
    // main relay fed (Bus 2) follows IN5, never the ignition; auto sleep waits for IN5 (key on or the ECU's after-run
    // hold), the tail switch and the hazard switch.
    [Fact]
    public async Task TheEcuKeepsItsLoadsAndItsHoldIsNeverCut()
    {
        var v = (await Loaded()).BuildView();
        var m = PdmModel.Build(v);
        Assert.Empty(PdmEcu.All(v));
        foreach (var ecuLoad in new[] { "fuel pump", "fan", "EPS", "steering", "heater", "blower", "A/C", "throttle", "boost", "injector", "coil" })
            Assert.DoesNotContain(St185Car.Loads, l => l.Name.Contains(ecuLoad, StringComparison.OrdinalIgnoreCase));
        foreach (var o in new[] { 3, 7, 8 })
        {
            var w = PdmTriggers.Of(m, o).Words;
            Assert.Contains("IN5", w);
            Assert.DoesNotContain("IN16", w);
        }
        foreach (var q in v.Boards)
        {
            var d = q.Device;
            Assert.True(d.SleepEnabled);
            var tm = PdmKeyOff.SleepTimer(d);
            Assert.NotNull(tm);
            Assert.Equal((TimerMode.OnDelay, PdmKeyOff.MuteDelayMs), (tm!.Mode, tm.Time));
            Assert.Equal(St185Car.WakeMask(q.Role), d.CustomPdm!.WakeInputMask);
        }
        var sleepWords = PdmValues.All(m).Where(f => f.Kind == PdmValueKind.AutoSleep).Select(f => f.Words).ToList();
        Assert.Equal(3, sleepWords.Count);
        Assert.All(sleepWords, w => Assert.Contains("IN5 and IN7 and IN9 are all off", w));
        // the firmware can arm every wake input (core/sleep.cpp: not A IN1 / IN3 / IN4, not B IN1 / IN9 / IN10)
        Assert.Equal((0b1110010, 0b10, 0b10), (St185Car.WakeMask("A1"), St185Car.WakeMask("A2"), St185Car.WakeMask("B")));
    }

    [Fact]
    public async Task TheCarConfigsCriticalSettingsAreTheFactoryOnes()
    {
        var svc = await Loaded();
        var (_, factory) = NewApp();
        Assert.Null(factory.NewPdm());

        static List<string> Block(FwDevice d) => d.Params.Where(p => p.Index == CustomPdmSettings.BaseIndex && p.Name != "customPdm.wakeInputMask")
            .Select(p => $"{p.Name} {p.SubIndex} = {p.GetValue()}").ToList();
        foreach (var role in PdmOps.Roles)
        {
            var s = svc.BuildView().Boards.Single(b => b.Role == role).Device;
            var f = factory.BuildView().Boards.Single(b => b.Role == role).Device;
            Assert.Equal((f.BaseId, f.BitRate, f.Type), (s.BaseId, s.BitRate, s.Type));
            Assert.Equal(CanBitRate.BitRate1000K, s.BitRate);
            Assert.NotEmpty(Block(f));
            Assert.Equal(Block(f), Block(s));   // 0x7F00: temperature limits, outputs kept on at critical (wake inputs: the car's)
        }
    }

    [Fact]
    public async Task TheCarConfigDiffersFromANewPdmOnlyWhereTheMapSetSomething()
    {
        var svc = await Loaded();
        var (_, factory) = NewApp();
        Assert.Null(factory.NewPdm());
        var outside = new List<string>();
        foreach (var role in PdmOps.Roles)
        {
            var s = Raw(svc.BuildView().Boards.Single(b => b.Role == role).Device);
            var f = Raw(factory.BuildView().Boards.Single(b => b.Role == role).Device);
            Assert.Equal(f.Select(p => (p.Name, p.Index, p.Sub)), s.Select(p => (p.Name, p.Index, p.Sub)));
            outside.AddRange(s.Zip(f).Where(x => x.First.Bytes != x.Second.Bytes)
                .Select(x => x.First.Name).Where(n => !Allowed.Contains(n.Split('[', '.')[0]) && !AllowedDevice.Contains(n)).Select(b => $"{role} {b}"));
        }
        Assert.Empty(outside.Distinct());
    }

    private static readonly string[] Allowed = ["output", "input", "canInput", "virtualInput", "customPdm", "condition", "timer", "flasher", "wiper"];
    private static readonly string[] AllowedDevice = ["device.sleepEnabled", "device.muteCanTxInput"];

    // docs/st185-car-config.dummy.md shows the map that is in the file: one table row per load and per switch
    [Fact]
    public async Task TheDocTableIsTheMap()
    {
        var doc = await File.ReadAllTextAsync(Path.Combine(Root(), "docs", "st185-car-config.dummy.md"));
        var v = Built().BuildView();
        Assert.StartsWith("DUMMY COPY", doc);
        Assert.Contains(St185Car.Source, doc.Split('\n')[0]);
        foreach (var l in St185Car.Loads)
        {
            var o = v.Outputs.Single(r => r.Number == l.Number);
            Assert.Contains($"| {l.Number} | {o.Board} OUT{o.BoardOutput} | {o.Connector} | {l.Name} |", doc);
        }
        foreach (var s in St185Car.Switches)
        {
            var i = v.Inputs.Single(r => r.Number == s.Number);
            Assert.Contains($"| IN{s.Number} | {i.Board} IN{i.BoardInput} | {i.Connector} | {s.Name} |", doc);
        }
    }

    // Dan 2026-11-23 (coordinator): the car CAN files of this repo are DUMMY / DEMO / TEST ONLY: every file says so on
    // line 1 and in its name, and nothing in the app or the firmware reads them.
    [Fact]
    public void TheEcuPdmCanConfigIsADummyThatNothingRealLoads()
    {
        var dir = Path.Combine(Root(), "docs", "car-can-dummy");
        foreach (var f in Directory.GetFiles(dir))
        {
            Assert.Contains(".dummy.", Path.GetFileName(f));
            Assert.Contains("DUMMY", File.ReadLines(f).First());
        }
        // no app or firmware source line (comments aside) names a dummy CAN file; the car config file itself is named dummy
        var bad = new List<string>();
        foreach (var root in new[] { Path.Combine(Root(), "ui", "dingoConfig"), Path.Combine(Root(), "firmware") })
            foreach (var f in Directory.EnumerateFiles(root, "*.*", SearchOption.AllDirectories)
                         .Where(f => f.EndsWith(".cs") || f.EndsWith(".razor") || f.EndsWith(".cpp") || f.EndsWith(".h") || f.EndsWith(".c"))
                         .Where(f => !f.Contains($"{Path.DirectorySeparatorChar}bin{Path.DirectorySeparatorChar}") && !f.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}")))
                foreach (var (line, n) in File.ReadLines(f).Select((l, n) => (l.Trim(), n + 1)))
                    if (!line.StartsWith("//") && !line.StartsWith("@*") && !line.StartsWith("*") && (line.Contains("car-can-dummy") || line.Contains("link_pdm_")))
                        bad.Add($"{f}:{n}");
        Assert.Empty(bad);
        Assert.Contains(".dummy.", PdmStarter.CarFileName);
    }

    [Fact]
    public async Task TheCarConfigButtonFindsItsFileAndRefusesAMissingOne()
    {
        Assert.Equal(Path.Combine(Path.GetDirectoryName(CarPath())!, PdmStarter.FileName), PdmStarter.Find(AppContext.BaseDirectory));
        Assert.Null(PdmStarter.Find(Path.GetPathRoot(Path.GetTempPath())!, PdmStarter.CarFileName));
        var (mgr, service) = NewApp();
        Assert.Null(service.NewPdm());
        var missing = Path.Combine(Path.GetTempPath(), "cpdm-no-such-car.json");
        Assert.Equal("The car config file could not be read.", await PdmStarter.LoadAsync(missing, Files(), mgr, service.Ops, "car config"));
        Assert.Equal(3, service.BuildView().Boards.Count);
        _ = mgr;
    }
}
