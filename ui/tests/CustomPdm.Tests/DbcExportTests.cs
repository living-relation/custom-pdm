using application.Services;
using domain.Common;
using domain.CustomPdm;
using domain.Devices;
using domain.Models;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// Route B phase B5: DBC files for the ECU (domain/CustomPdm/DbcExport.cs). One generator for the repo files
// (firmware/dbc/custompdm_*.dbc, ui/tools/DbcGen) and the /pdm Export DBC button, checked against the app's own
// decode and against the firmware TX code (firmware/boards/custompdm_*/msg.cpp, identical for A and B).
public class DbcExportTests(ITestOutputHelper output)
{
    private static readonly FwDeviceDefManager Mgr = new();

    private static List<(string FileName, string Text)> Generated() =>
        DbcExport.RepoFiles(Mgr.GetByDeviceType, Mgr.GetDeviceCyclicSigsConfig);

    internal static string RepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "automation.yml"))) dir = dir.Parent;
        return dir?.FullName ?? throw new InvalidOperationException("repo root (automation.yml) not found");
    }

    internal static List<DbcSignal> Parse(string text)
    {
        var path = Path.Combine(Path.GetTempPath(), $"custompdm-{Guid.NewGuid():N}.dbc");
        File.WriteAllText(path, text);
        try { return DbcParser.ParseFile(path); }
        finally { File.Delete(path); }
    }

    // The committed files are exactly the generator output: script, button and files cannot drift apart
    [Fact]
    public void RepoFilesEqualGenerator()
    {
        var files = Generated();
        Assert.Equal(["custompdm_A1_0x500.dbc", "custompdm_A2_0x540.dbc", "custompdm_B_0x580.dbc", "custompdm_PDM.dbc"],
            files.Select(f => f.FileName));
        foreach (var (name, text) in files)
        {
            var path = Path.Combine(RepoRoot(), "firmware", "dbc", name);
            Assert.True(File.Exists(path), $"{name} missing: run dotnet run --project ui/tools/DbcGen");
            Assert.True(File.ReadAllText(path).Replace("\r\n", "\n") == text,
                $"firmware/dbc/{name} differs from the generator: run dotnet run --project ui/tools/DbcGen");
        }
    }

    // The button's file for a default project (A1 0x500, A2 0x540, B 0x580) is the committed PDM file
    [Fact]
    public void ButtonOutputForDefaultProjectIsRepoPdmFile()
    {
        var devices = DbcExport.RepoBoards.Select(b => StockTests.MakeDevice(b.DeviceType, b.BaseId)).Reverse().ToList();
        var view = PdmView.Build(devices);
        var text = DbcExport.Build(view.Boards.Select(b => new DbcBoard(b.Role, b.Device)));
        Assert.Equal(Generated().Single(f => f.FileName == DbcExport.PdmFileName).Text, text);
    }

    // Every generated file, read back with dingoConfig's own DBC parser, holds exactly the signals the app decodes
    [Fact]
    public void ParsedBackWithDingoConfigParserMatchesAppDecode()
    {
        foreach (var (name, text) in Generated())
        {
            var parsed = Parse(text);
            var boards = DbcExport.RepoBoards.Where(b => name == DbcExport.PdmFileName || name == DbcExport.FileName(b)).ToList();
            var expectedCount = 0;
            foreach (var b in boards)
            {
                var app = StockTests.MakeDevice(b.DeviceType, b.BaseId).GetCyclicSigs().ToList();
                foreach (var (id, s) in app)
                {
                    if (s.Name == "ThermalFlags")
                    {
                        foreach (var (bit, flag) in new[] { (0, "ThermalOverWarn"), (1, "ThermalCritSoon"), (2, "ThermalCritical") })
                            Assert.Single(parsed, p => p.Id == id && p.Name == $"{b.Node}_{flag}" && p.StartBit == s.StartBit + bit
                                                       && p.Length == 1 && !p.IsSigned);
                        expectedCount += 3;
                        continue;
                    }
                    var stem = $"{b.Node}_{s.Name.Replace('.', '_')}";
                    var p = Assert.Single(parsed, p => p.Id == id && (p.Name == stem || p.Name.StartsWith(stem + "_M")) && p.StartBit == s.StartBit);
                    Assert.Equal((s.Length, s.IsSigned, s.Factor, s.Offset, s.Unit, s.ByteOrder),
                        (p.Length, p.IsSigned, p.Factor, p.Offset, p.Unit, p.ByteOrder));
                    expectedCount++;
                }
            }
            Assert.Equal(expectedCount, parsed.Count);
            // signal names unique in the file (one file can hold the whole PDM), DBC identifiers only
            Assert.Equal(parsed.Count, parsed.Select(p => p.Name).Distinct().Count());
            Assert.All(parsed, p => Assert.Matches("^[A-Za-z_][A-Za-z0-9_]*$", p.Name));
            output.WriteLine($"{name}: {parsed.Count} signals, {parsed.Select(p => p.Id).Distinct().Count()} messages");
        }
    }

    // The value tables come through the parser too (device state, board type, output states)
    [Fact]
    public void ValueTablesParse()
    {
        var parsed = Parse(Generated().Single(f => f.FileName == "custompdm_B_0x580.dbc").Text);
        Assert.Equal("Overcurrent", parsed.Single(p => p.Name == "B_Output3_State").ValueTable![2]);
        Assert.Equal("OverTemp", parsed.Single(p => p.Name == "B_DeviceState").ValueTable![2]);
        Assert.Equal("custom-pdm B", parsed.Single(p => p.Name == "B_PdmType").ValueTable![15]);
    }

    // Two boards on the same base ID would give one CAN ID twice: refused, not written
    [Fact]
    public void OverlappingBaseIdsRefused()
    {
        var ex = Assert.Throws<InvalidOperationException>(() => DbcExport.Build(
            [new DbcBoard("A1", StockTests.MakeDevice(14, 0x500)), new DbcBoard("A2", StockTests.MakeDevice(14, 0x510))]));
        Assert.Contains("overlap", ex.Message);
    }

    // Hand-read from firmware/boards/custompdm_a/msg.cpp (custompdm_b/msg.cpp is the same file) and core/status.cpp:
    // (msg, signal stem, start bit, length, signed, factor, unit). Intel byte order (data16 / data32 on the STM32).
    private static readonly (int Msg, string Stem, int Start, int Len, bool Signed, double Factor, string Unit)[] Firmware =
    [
        (0, "DeviceState", 8, 4, false, 1, ""), (0, "PdmType", 12, 4, false, 1, ""),
        (0, "TotalCurrent", 16, 16, false, 1, "A"),            // (uint16_t)GetTotalCurrent(), whole amps
        (0, "BatteryVoltage", 32, 16, false, 0.1, "V"),        // GetBattVolt() * 10
        (0, "BoardTemp", 48, 16, false, 0.1, "degC"),          // (uint16_t)(GetBoardTemp() * 10), unsigned (stock)
        (1, "Output1_Current", 0, 16, false, 1, "A"), (1, "Output4_Current", 48, 16, false, 1, "A"),
        (2, "Output5_Current", 0, 16, false, 1, "A"), (2, "Output8_Current", 48, 16, false, 1, "A"),
        (3, "Output1_State", 0, 4, false, 1, ""), (3, "Output8_State", 28, 4, false, 1, ""),
        (3, "WiperSlowState", 32, 1, false, 1, ""), (3, "WiperFastState", 33, 1, false, 1, ""),
        (3, "WiperSpeed", 40, 4, false, 1, ""), (3, "WiperState", 44, 4, false, 1, ""),
        (3, "Flasher1", 48, 1, false, 1, ""), (3, "Flasher4", 51, 1, false, 1, ""),
        (3, "ThermalOverWarn", 56, 1, false, 1, ""), (3, "ThermalCritSoon", 57, 1, false, 1, ""), (3, "ThermalCritical", 58, 1, false, 1, ""),
        (4, "Output1_ResetCount", 0, 8, false, 1, ""), (4, "Output8_ResetCount", 56, 8, false, 1, ""),
        (5, "CanInput1", 0, 1, false, 1, ""), (5, "CanInput32", 31, 1, false, 1, ""),
        (5, "VirtualInput1", 32, 1, false, 1, ""), (5, "VirtualInput16", 47, 1, false, 1, ""),
        (6, "Counter1", 0, 8, false, 1, ""), (6, "Counter4", 24, 8, false, 1, ""),
        (6, "Condition1", 32, 1, false, 1, ""), (6, "Condition32", 63, 1, false, 1, ""),
        (7, "CanInput1_Value", 0, 32, true, 1, ""), (7, "CanInput2_Value", 32, 32, true, 1, ""),   // Dbc::EncodeFloat -> int32
        (22, "CanInput31_Value", 0, 32, true, 1, ""), (22, "CanInput32_Value", 32, 32, true, 1, ""),
        (23, "Output1_DutyCycle", 0, 8, false, 1, "%"), (23, "Output8_DutyCycle", 56, 8, false, 1, "%"),
        (27, "Timer1_Output", 0, 1, false, 1, ""), (27, "Timer8_Output", 7, 1, false, 1, ""),
        (27, "Timer1_Running", 8, 1, false, 1, ""), (27, "Timer8_Running", 15, 1, false, 1, ""),
        (28, "Timer1_Elapsed", 0, 16, false, 0.01, "s"), (29, "Timer8_Elapsed", 48, 16, false, 0.01, "s"), // ms / 10
        (30, "Math1_Value", 0, 32, true, 0.001, ""), (33, "Math8_Value", 32, 32, true, 0.001, ""),           // x1000, int32
        (34, "DigitalInput1_Duty", 0, 16, false, 0.01, "%"), (34, "DigitalInput1_Frequency", 16, 16, false, 0.1, "Hz"),
        (36, "DigitalInput6_Duty", 32, 16, false, 0.01, "%"), (36, "DigitalInput6_Frequency", 48, 16, false, 0.1, "Hz"),
        (37, "AnalogInput1_Millivolts", 16, 16, false, 1, "mV"), (37, "AnalogInput1_Raw", 32, 16, false, 1, ""),
        (37, "DieTemp", 48, 16, true, 0.1, "degC"),            // (uint16_t)(int16_t)(GetTemperature() * 10), signed
    ];

    [Theory]
    [InlineData("A1", 7)]
    [InlineData("A2", 7)]
    [InlineData("B", 10)]
    public void MatchesFirmwareTxCode(string node, int numDi)
    {
        var b = DbcExport.RepoBoards.Single(r => r.Node == node);
        var msgs = DbcExport.Messages(new DbcBoard(node, StockTests.MakeDevice(b.DeviceType, b.BaseId)));
        // NUM_TX_MSGS 38; msgs 24-26 (keypads, sent only with a keypad enabled) are not decoded by the app
        Assert.Equal(Enumerable.Range(0, 38).Except([24, 25, 26]), msgs.Select(m => m.MsgNumber));
        Assert.All(msgs, m => Assert.Equal(b.BaseId + DbcExport.CyclicTxOffset + m.MsgNumber, m.Id));
        var wrong = new List<string>();
        foreach (var f in Firmware)
        {
            var s = msgs.Single(m => m.MsgNumber == f.Msg).Signals.SingleOrDefault(s => s.Name == $"{node}_{f.Stem}" || s.Name == $"{node}_{f.Stem}_M{f.Msg}");
            if (s == null || (s.StartBit, s.Length, s.IsSigned, s.Factor, s.Unit) != (f.Start, f.Len, f.Signed, f.Factor, f.Unit))
                wrong.Add($"msg {f.Msg} {f.Stem}: {(s == null ? "missing" : $"{s.StartBit}|{s.Length} signed {s.IsSigned} x{s.Factor} {s.Unit}")}");
        }
        Assert.Empty(wrong);
        // msg 0 byte 0: digital inputs 1-8 (min(NUM_DIG_INPUTS, 8)); msg 37 data16[0]: all NUM_DIG_INPUTS
        Assert.Equal(Enumerable.Range(0, Math.Min(numDi, 8)), DiBits(msgs, 0, node));
        Assert.Equal(Enumerable.Range(0, numDi), DiBits(msgs, 37, node));
        Assert.Equal(numDi > 6 ? 6 : numDi, msgs.Where(m => m.MsgNumber is >= 34 and <= 36).Sum(m => m.Signals.Count) / 2); // DI PWM 1-6
    }

    private static IEnumerable<int> DiBits(List<DbcExport.Message> msgs, int msg, string node) =>
        msgs.Single(m => m.MsgNumber == msg).Signals.Where(s => s.Name.StartsWith($"{node}_DigitalInput") && s.Name.Contains("_State"))
            .Select(s => { Assert.Equal(1, s.Length); return s.StartBit; });
}

[Collection("sim")] // the sim tests run one after another (WSL processes, real-time bridge)
public class DbcLiveSimTests(ITestOutputHelper output)
{
    // Live: the firmware's real frames (host sim of A1, A2 and B on one bus) decoded with the committed PDM file
    [SimFact]
    public void LiveFramesDecodeWithPdmFile()
    {
        var path = Path.Combine(DbcExportTests.RepoRoot(), "firmware", "dbc", DbcExport.PdmFileName);
        var dbc = DbcExportTests.Parse(File.ReadAllText(path));
        var ids = dbc.Select(s => s.Id).ToHashSet();
        using var bus = new SimBus();
        bus.Run(1500);
        var temps = new Dictionary<string, double> { ["A1"] = 62.5, ["A2"] = 77.0, ["B"] = 48.0 };
        foreach (var (node, t) in temps) bus.Cmd($"TEMP {node} {t} 41");
        var frames = bus.Run(1500);

        foreach (var b in DbcExport.RepoBoards)
        {
            var mine = frames.Where(f => f.Id >= b.BaseId + DbcExport.CyclicTxOffset && f.Id < b.BaseId + 0x40).ToList();
            Assert.NotEmpty(mine);
            // every status frame the firmware sends is in the file
            Assert.All(mine, f => Assert.Contains(f.Id, ids));
            double Get(string sig)
            {
                var s = dbc.Single(x => x.Name == $"{b.Node}_{sig}");
                return DbcSignalCodec.ExtractSignal(mine.Last(f => f.Id == s.Id).Data, s);
            }
            // the app decodes the same frames: same values
            var dev = StockTests.MakeDevice(b.DeviceType, b.BaseId);
            foreach (var f in mine) DefinitionsTests.Feed(dev, f.Id, f.Data);

            Assert.Equal(b.DeviceType, Get("PdmType"));
            Assert.Equal(temps[b.Node] > 55 ? 2 : 0, Get("DeviceState"));           // OverTemp above warn 55, else Run
            Assert.Equal((int)dev.DeviceState, Get("DeviceState"));
            Assert.Equal(temps[b.Node], Get("BoardTemp"), 3);
            Assert.Equal(dev.BoardTempC, Get("BoardTemp"), 3);
            var raw = (int)((0.76 + (41 - 25.0) * 0.0025) / 3.3 * 4095.0 + 0.5); // sim die sensor model (LiveSimTests)
            Assert.Equal((int)((30.0 + (raw - 943) / (1199.0 - 943) * 80.0) * 10.0) / 10.0, Get("DieTemp"), 3);
            Assert.Equal(dev.CustomPdm!.DieTempC, Get("DieTemp"), 3);
            Assert.Equal(dev.BatteryVoltage, Get("BatteryVoltage"), 3);
            // warn 55, critical 80, critical-soon margin 5 (factory defaults)
            var flags = (Get("ThermalOverWarn"), Get("ThermalCritSoon"), Get("ThermalCritical"));
            Assert.Equal(temps[b.Node] switch { > 75 => (1.0, 1.0, 0.0), > 55 => (1.0, 0.0, 0.0), _ => (0.0, 0.0, 0.0) }, flags);
            Assert.Equal(dev.CustomPdm.ThermalFlags, (int)(flags.Item1 + 2 * flags.Item2 + 4 * flags.Item3));
            output.WriteLine($"{b.Node}: {mine.Select(f => f.Id).Distinct().Count()} status IDs seen, board {Get("BoardTemp")} C, die {Get("DieTemp")} C, batt {Get("BatteryVoltage")} V, flags {flags}");
        }
    }
}
