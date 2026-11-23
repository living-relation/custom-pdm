using application.Services;
using domain.Common;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace CustomPdm.Tests;

// carconfig (Dan c4 = a, 2026-11-23): the ST185 install config (ui/examples/st185-car.json), built from the car map
// below with the /pdm domain code on a New PDM. The map is a DUMMY COPY of st185-link-ecu-config @ 839be705
// (sot/fuse-relay-map.csv, sot/channels.csv, docs/harness/circuit-plan.md, FUEL-SYSTEM.md, CAN-BUS-ID-ALLOCATION-TABLE.md;
// that repo is read only), written out in docs/st185-car-config.md. The ECU command frame (0x3F4 bytes 0-3, 50 ms) is
// a placeholder: TO CONFIRM when the Link ECU CAN setup is done (st185 plans no PDM frame yet).
// Regenerate the file: $env:CUSTOMPDM_WRITE_CAR_CONFIG='1'; dotnet test --filter St185CarTests
public static class St185Car
{
    public const string Source = "st185-link-ecu-config @ 839be705";
    public const int EcuId = 0x3F4;   // TO CONFIRM (placeholder in st185's free range 0x3F2-0x63F)
    public const int PumpByte = 0, RadFanByte = 1, CondFanByte = 2, EpsByte = 3;

    // st185 fuse = the fuse that protects that circuit's wiring today (sot/fuse-relay-map.csv)
    public record Load(int Number, string Name, PdmDeviceKind Kind, double St185FuseA, string Replaces, double? LimitA = null, double? InrushA = null);

    public record Sw(int Number, string Name, bool GroundActive, string Wire);

    public static readonly Load[] Loads =
    [
        new(1, "Low beams", PdmDeviceKind.LedLamp, 15, "K-HL relay (LOGIC M1) + HL 15 A"),
        new(2, "High beams", PdmDeviceKind.LedLamp, 15, "K-HR relay (LOGIC M2) + HR 15 A"),
        new(3, "DRLs", PdmDeviceKind.LedLamp, 7.5, "K-DRL relay (LOGIC M8) + RLY-DRL (B5) + DRL 7.5 A"),
        new(5, "Horns", PdmDeviceKind.Horn, 15, "K-HORN relay (LOGIC M3); HZ 15 A stays for the hazard feed"),
        new(6, "EPS pump enable", PdmDeviceKind.Module, 5, "K-EPS-EN relay (LOGIC M6) + EPSEN 5 A"),
        new(7, "CSB3 switchboard", PdmDeviceKind.Module, 5, "CSB 5 A (BUS2-5)"),
        new(8, "Centre cluster", PdmDeviceKind.Module, 5, "DEV 5 A (BUS2-6)"),
        new(17, "Radiator fan", PdmDeviceKind.RadiatorFan, 30, "K-FAN relay (POWER R4) + AMI IN-4 30 A"),
        new(18, "Condenser fan", PdmDeviceKind.CondenserFan, 30, "K-FAN2 relay (POWER R5) + AMI IN-5 30 A"),
        new(19, "Fuel pump", PdmDeviceKind.FuelPump, 40, "K-FP relay (trunk block B3 K1) + FP 40 A"),
        new(21, "CAN-Lambda", PdmDeviceKind.Heater, 10, "K-ON relay (LOGIC M7) + LAM 10 A", LimitA: 10, InrushA: 15),
        new(22, "A/C clutch", PdmDeviceKind.AcClutch, 10, "K-ACC relay (LOGIC M5) + ACC 10 A"),
    ];

    public static readonly Sw[] Switches =
    [
        new(1, "Head / flash (R-Y)", true, "R-Y IE1-2: light switch HEAD (C15-14) / dimmer FLASH (C15-13) to ground"),
        new(2, "High / flash (R-W)", true, "R-W IE1-18: dimmer HIGH / FLASH to ground"),
        new(3, "DRL switch", true, "DRL-SW (the K-DRL coil 85 wire) to ground"),
        new(4, "Horn switch", true, "G IE1-19: horn switch C15-10 to ground"),
        new(5, "Ignition (IG2)", false, "B-O J/B1 1H-7 IGN (live at ON and ST), 12 V = on"),
        new(15, "A/C clutch request", true, "A/C amplifier A15 pin 8 (sinks the old K-ACC coil 85)"),
    ];

    public static Load LoadOf(int n) => Loads.Single(l => l.Number == n);

    // the trigger of every load (PDM input numbers; IN1-7 = A1, IN8-14 = A2, IN15-24 = B)
    private static readonly (int Out, PdmTriggerSpec Spec)[] Triggers =
    [
        (1, PdmTriggerSpec.Input(PdmTerm.In(1))),
        (2, PdmTriggerSpec.Logic(PdmLogicOp.And, PdmTerm.In(2), PdmTerm.In(1))),                     // as K-HR: only with the head lamps on
        (3, PdmTriggerSpec.Logic(PdmLogicOp.And, PdmTerm.In(3), PdmTerm.In(5), PdmTerm.In(1, true))),  // as K-DRL + RLY-DRL
        (5, PdmTriggerSpec.Input(PdmTerm.In(4))),
        (7, PdmTriggerSpec.Input(PdmTerm.In(5))),
        (8, PdmTriggerSpec.Input(PdmTerm.In(5))),
        (21, PdmTriggerSpec.Input(PdmTerm.In(5))),                                                   // B, over CAN from A1
        (22, PdmTriggerSpec.Input(PdmTerm.In(15))),
    ];

    // the ECU switches what it switches today (sot/channels.csv: Aux 3 pump, Aux 5 radiator fan, Ign 5 condenser fan,
    // Ign 6 EPS enable); loss behaviour = the device preset's (pump off, fans on, EPS enable hold)
    private static readonly (int Out, int Byte, PdmLinkLoss Loss)[] Ecu =
    [
        (19, PumpByte, PdmLinkLoss.Off), (17, RadFanByte, PdmLinkLoss.On), (18, CondFanByte, PdmLinkLoss.On), (6, EpsByte, PdmLinkLoss.Hold),
    ];

    // Builds the car config on the boards of v (a New PDM). Throws when any step is refused.
    public static void Build(PdmView v)
    {
        static void Ok(string? why, string what) { if (why != null) throw new InvalidOperationException($"{what}: {why}"); }

        foreach (var s in Switches)
        {
            var d = v.Inputs.Single(r => r.Number == s.Number && r.Digital != null).Digital!;
            (d.Enabled, d.Name, d.Mode, d.Invert) = (true, s.Name, InputMode.Momentary, s.GroundActive);
            d.Pull = s.GroundActive ? InputPull.PullUp : InputPull.PullDown;
        }
        foreach (var (o, spec) in Triggers) Ok(PdmTriggers.Set(v, o, spec), $"output {o} trigger");
        foreach (var (o, b, loss) in Ecu) Ok(PdmEcu.Set(v, o, EcuId, b, loss, PdmLinks.TimeoutMs), $"output {o} ECU byte {b}");
        foreach (var l in Loads)
        {
            Ok(PdmPresets.Apply(v, l.Number, l.Kind), $"output {l.Number} preset");
            var x = v.Outputs.Single(r => r.Number == l.Number).Output;
            (x.Enabled, x.Name) = (true, l.Name);
            if (l.LimitA is { } a) x.CurrentLimit = a;
            if (l.InrushA is { } i) x.InrushCurrentLimit = i;
        }
    }

    // every function in words, from the board params only (names left out: they live in the project file)
    public static List<string> Functions(PdmView v)
    {
        var m = PdmModel.Build(v);
        var list = m.Triggers.Select(t => $"{t.Out.Number}: {System.Text.RegularExpressions.Regex.Replace(t.Words, " '[^']*'", "")}").ToList();
        foreach (var o in v.Outputs)
        {
            var x = o.Output;
            var pro = o.Device.CustomPdm!.OutputProtection[o.BoardOutput - 1];
            list.Add($"{o.Number} {o.Board} OUT{o.BoardOutput}: {(x.Enabled ? "on" : "off")}, limit {x.CurrentLimit:0.##} A, inrush {x.InrushCurrentLimit:0.##} A / {x.InrushTime} ms, " +
                     $"trip {pro.TripTime} ms, {PdmPresets.TripsText(x.ResetCountLimit, x.ResetTime)}, soft start {(x.SoftStartEnabled ? $"{x.SoftStartRampTime} ms at {x.Frequency} Hz" : "no")}, " +
                     $"open-load {pro.MinCurrent:0.##} A");
        }
        foreach (var i in v.Inputs.Where(r => r.Digital != null))
            list.Add($"IN{i.Number}: {(i.Digital!.Enabled ? "on" : "off")}, {i.Digital.Pull}, {(i.Digital.Invert ? "inverted" : "not inverted")}, {i.Digital.Mode}, {i.Digital.DebounceTime} ms");
        return list;
    }
}

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

    // The committed file is exactly what the map builds (param by param, names and preset labels too), so the file,
    // the map in this class and docs/st185-car-config.md cannot drift apart. CUSTOMPDM_WRITE_CAR_CONFIG=1 writes it.
    [Fact]
    public async Task TheCarFileIsWhatTheMapBuilds()
    {
        var built = Built();
        if (Environment.GetEnvironmentVariable("CUSTOMPDM_WRITE_CAR_CONFIG") == "1")
        {
            var files = Files();
            await files.SaveDevices(built.BuildView().Boards.Select(b => (domain.Interfaces.IDevice)b.Device).ToList(),
                Path.Combine(ExamplesDir(), PdmStarter.CarFileName));
        }
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

    [Fact]
    public async Task TheCarConfigLoadsAsAWritablePdmWithEveryFunctionInWords()
    {
        var svc = await Loaded();
        var v = svc.BuildView();
        Assert.Equal(["A1", "A2", "B"], v.Boards.Select(b => b.Role));
        Assert.Empty(v.Problems);
        Assert.All(v.Boards, b => Assert.True(b.Device.CustomPdm!.FactoryNew));
        Assert.Null(svc.BlockedReason(PdmOpKind.WriteAll, v, true));   // writable without a Read All, as a New PDM
        var m = PdmModel.Build(v);
        Assert.Empty(m.Problems);
        Assert.Empty(v.OverRating);

        string Words(int n) => PdmTriggers.Of(m, n).Words;
        Assert.Equal("IN1", Words(1));
        Assert.Equal("IN2 AND IN1", Words(2));
        Assert.Equal("IN3 AND IN5 AND NOT IN1", Words(3));
        Assert.Equal("IN4", Words(5));
        Assert.Equal("ECU 0x3F4 byte 3 = 1 (ECU only; keeps its last state (off at power-up))", Words(6));
        Assert.Equal(("IN5", "IN5", "IN5", "IN15"), (Words(7), Words(8), Words(21), Words(22)));
        Assert.Equal("ECU 0x3F4 byte 0 = 1 (ECU only; off 1 s after the ECU frames stop)", Words(19));
        Assert.Equal("ECU 0x3F4 byte 1 = 1 (ECU only; on 1 s after the ECU frames stop; off until the first frame)", Words(17));
        Assert.Equal("ECU 0x3F4 byte 2 = 1 (ECU only; on 1 s after the ECU frames stop; off until the first frame)", Words(18));
        Assert.Contains("fan logic", Words(10));           // A2 OUT2 still runs the box fans
        var spare = v.Outputs.Select(o => o.Number).Except(St185Car.Loads.Select(l => l.Number)).Except([10]).ToList();
        Assert.Equal([4, 9, 11, 12, 13, 14, 15, 16, 20, 23, 24], spare);
        Assert.All(spare, n => Assert.Equal("none", Words(n)));

        foreach (var l in St185Car.Loads)
        {
            var o = v.Outputs.Single(r => r.Number == l.Number);
            Assert.Equal((l.Name, true), (o.Output.Name, o.Output.Enabled));
            Assert.Equal(l.Kind, PdmPresets.KindOf(v, o));
            Assert.True(o.Output.CurrentLimit <= Math.Min(o.RatingA, l.St185FuseA), $"output {l.Number}: {o.Output.CurrentLimit} A over its rating or the st185 fuse");
        }
        Assert.Equal((25.0, 100.0, 500), (v.Outputs[18].Output.CurrentLimit, v.Outputs[18].Output.InrushCurrentLimit, v.Outputs[18].Output.InrushTime));
        Assert.Equal((10.0, 15.0), (v.Outputs[20].Output.CurrentLimit, v.Outputs[20].Output.InrushCurrentLimit));   // CAN-Lambda: LAM 10 A
        Assert.Equal(["current limit", "inrush limit"], PdmPresets.Changed(v, v.Outputs[20], PdmDeviceKind.Heater));

        foreach (var s in St185Car.Switches)
        {
            var i = v.Inputs.Single(r => r.Number == s.Number);
            Assert.Equal((s.Name, true, s.GroundActive, s.GroundActive ? InputPull.PullUp : InputPull.PullDown),
                (i.Name, i.Digital!.Enabled, i.Digital.Invert, i.Digital.Pull));
        }
        Assert.Equal("IN5 = Ignition (IG2), IN1 = Head / flash (R-Y)", PdmPageText.InputNames(v, "IN5 AND NOT IN1"));
    }

    // Why the car config may be loaded "as a New PDM": everything a wrong file could break is what New PDM sets
    [Fact]
    public async Task TheCarConfigsCriticalSettingsAreTheFactoryOnes()
    {
        var svc = await Loaded();
        var (_, factory) = NewApp();
        Assert.Null(factory.NewPdm());

        static List<string> Block(FwDevice d) => d.Params.Where(p => p.Index == CustomPdmSettings.BaseIndex)
            .Select(p => $"{p.Name} {p.SubIndex} = {p.GetValue()}").ToList();
        foreach (var role in PdmOps.Roles)
        {
            var s = svc.BuildView().Boards.Single(b => b.Role == role).Device;
            var f = factory.BuildView().Boards.Single(b => b.Role == role).Device;
            Assert.Equal((f.BaseId, f.BitRate, f.Type), (s.BaseId, s.BitRate, s.Type));
            Assert.Equal(CanBitRate.BitRate1000K, s.BitRate);
            Assert.NotEmpty(Block(f));
            Assert.Equal(Block(f), Block(s));   // 0x7F00: temperature limits, outputs kept on at critical, wake inputs
        }
        // A2 takes no car load: every A2 param (its box fan logic included) is the factory one
        Assert.Equal(Raw(factory.BuildView().Boards.Single(b => b.Role == "A2").Device), Raw(svc.BuildView().Boards.Single(b => b.Role == "A2").Device));
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
                .Select(x => x.First.Name.Split('[', '.')[0]).Where(b => !Allowed.Contains(b)).Select(b => $"{role} {b}"));
        }
        Assert.Empty(outside.Distinct());
    }

    private static readonly string[] Allowed = ["output", "input", "canInput", "virtualInput", "customPdm"];

    // docs/st185-car-config.md shows the map that is in the file: one table row per load and per switch
    [Fact]
    public async Task TheDocTableIsTheMap()
    {
        var dir = new DirectoryInfo(ExamplesDir()).Parent!.Parent!.FullName;
        var doc = await File.ReadAllTextAsync(Path.Combine(dir, "docs", "st185-car-config.md"));
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
