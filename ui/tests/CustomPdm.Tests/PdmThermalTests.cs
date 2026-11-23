using System.Globalization;
using System.Text.RegularExpressions;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// ADR-2026-11-20-temp-onepdm: /pdm keeps ONE temperature set, entered as the board hot-spot (laminate) temperature;
// the tool converts it per board with that board's sensor -> hot-spot offset (board B: the FEA map of
// docs/system-verification.md; board A: its FEA map since hwtemp, tools/thermal_a.py). Both offsets are 21 K, so one set
// gives both boards the same sensor limits. The live proof on the firmware: PdmThermalLiveSimTests.
public class PdmThermalTests
{
    private static PdmView NewPdm() => PdmLinkedTests.NewPdm();
    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;
    private static readonly PdmTempLimits FactoryA = new(98, 104, 6, 5), FactoryB = new(98, 104, 6, 5);

    private static string Repo(params string[] parts)
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "firmware", "tools_custom", "port_boards.py"))) dir = dir.Parent;
        Assert.NotNull(dir);
        return File.ReadAllText(Path.Combine([dir!.FullName, .. parts]));
    }

    private static double Num(string text, string pattern)
    {
        var m = Regex.Match(text, pattern);
        Assert.True(m.Success, $"not found: {pattern}");
        return double.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture);
    }

    // ---------------- the offset and its sources ----------------

    // Board B offset = the largest laminate - U6 offset of the 10 FEA cases + the MCP9808 maximum error, as cited by
    // docs/system-verification.md, tools/verify_thermal_box.py and port_boards.py (a change there fails this test)
    [Fact]
    public void BoardBOffsetIsTheFeaMapPlusSensorError()
    {
        var doc = Repo("docs", "system-verification.md");
        Assert.Equal(PdmThermal.BoardBLaminateOffsetK, Num(doc, @"Board B temperature limits[\s\S]*?laminate = U6 \+ [0-9.]+ \.\. ([0-9.]+) K"));
        var box = Repo("tools", "verify_thermal_box.py");
        Assert.Equal(PdmThermal.SensorErrorK, Num(box, @"SENSOR_ERR = ([0-9.]+)"));
        Assert.Equal(PdmThermal.LaminateMaxC, Num(box, @"LAMINATE_C, TJ_C = ([0-9.]+),"));
        var py = Repo("firmware", "tools_custom", "port_boards.py");
        Assert.Equal(PdmThermal.BoardBLaminateOffsetK, Num(py, @"# Board B temperature limits[\s\S]*?laminate = sensor \+ [0-9.]+ \.\. ([0-9.]+) K"));
        Assert.Equal(21, PdmThermal.BoardBOffsetK);
        // the binding limit of ADR-2026-11-20-fwsafety: the MCU beside the sensor at the sensor + 1 K <= 105 C
        Assert.Equal(104, PdmThermal.BoardBSensorCritMaxC);
        // board B's factory critical as a hot spot = the documented laminate result (124.6 C) rounded up
        Assert.Equal(Math.Ceiling(Num(doc, @"critical 104 C \(\+1 C MCP9808, largest offset\) \| ([0-9.]+) /")), CustomPdmSettings.DefaultTempCritB + PdmThermal.BoardBOffsetK);
    }

    // Board A offset (hwtemp) = the largest laminate - U6 offset of its 8 FEA cases + the sensor error, as cited by
    // port_boards.py (FAN_A block) and docs/heat-analysis.md; its factory critical as a hot spot = board B's
    [Fact]
    public void BoardAOffsetIsItsFeaMapPlusSensorError()
    {
        var py = Repo("firmware", "tools_custom", "port_boards.py");
        Assert.Equal(PdmThermal.BoardALaminateOffsetK, Num(py, @"# Board A temperature limits[\s\S]*?laminate = sensor \+ [0-9.]+ \.\. ([0-9.]+) K"));
        var heat = Repo("docs", "heat-analysis.md");
        Assert.Equal(PdmThermal.BoardALaminateOffsetK, Num(heat, @"\| A \| laminate \+([0-9.]+) K"));
        Assert.Equal(21, PdmThermal.BoardAOffsetK);
        Assert.Equal(104, PdmThermal.BoardASensorCritMaxC);
        Assert.Equal(CustomPdmSettings.DefaultTempCritB + PdmThermal.BoardBOffsetK, CustomPdmSettings.DefaultTempCritA + PdmThermal.BoardAOffsetK);
        Assert.Equal(CustomPdmSettings.DefaultTempWarnB + PdmThermal.BoardBOffsetK, CustomPdmSettings.DefaultTempWarnA + PdmThermal.BoardAOffsetK);
    }

    [Fact]
    public void EveryBoardHasAThermalModel()
    {
        var v = NewPdm();
        Assert.Equal([21, 21, 21], v.Boards.Select(b => PdmThermal.OffsetK(b.Device)));
        Assert.Equal([14, 14, 15], v.Boards.Select(b => b.Device.DeviceTypeId));
    }

    // ---------------- conversion ----------------

    [Fact]
    public void HotSpotSetOfANewPdmIsBoardBFactoryPlusOffset()
    {
        var v = NewPdm();
        Assert.Equal(new PdmHotSpotLimits(119, 125, 6, 5), PdmThermal.Current(v));
        Assert.Equal(new PdmTempLimits(98, 104, 6, 5), PdmThermal.ToSensor(new PdmHotSpotLimits(119, 125, 6, 5), 21));
        Assert.Equal(new PdmHotSpotLimits(119, 125, 6, 5), PdmThermal.FromSensor(FactoryB, 21));
    }

    // Without board B the set comes from board A (its own FEA map); with no custom board at all there is none
    [Fact]
    public void HotSpotSetFromBoardAWithoutBoardB()
    {
        var v = PdmView.Build(NewPdm().Boards.Where(b => b.Role != "B").Select(b => b.Device).ToList());
        Assert.Equal(new PdmHotSpotLimits(119, 125, 6, 5), PdmThermal.Current(v));
        Assert.Null(PdmThermal.Set(v, new PdmHotSpotLimits(110, 120, 6, 5)));
        Assert.All(v.Boards, b => Assert.Equal(new PdmTempLimits(89, 99, 6, 5), PdmTempLimits.Of(b.Device)));
        var none = PdmView.Build([]);
        Assert.Null(PdmThermal.Current(none));
        Assert.Equal(PdmThermal.NoModelBoard, PdmThermal.Set(none, new PdmHotSpotLimits(110, 120, 6, 5)));
    }

    // 'Set on A1, A2, B': every board gets the set converted with its own offset; whatever A1 held is replaced
    [Fact]
    public void SetConvertsForEveryBoard()
    {
        var v = NewPdm();
        var a1 = Dev(v, "A1").CustomPdm!;
        (a1.TempWarn, a1.TempCrit) = (60, 85);              // A1 holds something else: the B view still leads Current
        Assert.Equal(new PdmHotSpotLimits(119, 125, 6, 5), PdmThermal.Current(v));
        Assert.Null(PdmThermal.Set(v, new PdmHotSpotLimits(116, 123, 4, 7)));
        Assert.All(v.Boards, b => Assert.Equal(new PdmTempLimits(95, 102, 4, 7), PdmTempLimits.Of(b.Device)));
        Assert.Equal(new PdmHotSpotLimits(116, 123, 4, 7), PdmThermal.Current(v));
        Assert.All(v.Boards, b => Assert.True(b.Device.CustomPdm!.IsValid()));
    }

    [Fact]
    public void PreviewShowsEachBoardsSensorLimitAndChangesNothing()
    {
        var v = NewPdm();
        var rows = PdmThermal.Preview(v, new PdmHotSpotLimits(116, 123, 4, 7));
        Assert.Equal(["A1", "A2", "B"], rows.Select(r => r.Role));
        Assert.All(rows, r => Assert.Equal(new PdmTempLimits(95, 102, 4, 7), r.Sensor));
        Assert.Equal([true, true, true], rows.Select(r => r.Converted));
        Assert.Equal("sensor = hot spot - 21 K (FEA map: largest laminate offset 19.8 K + 1 K sensor error)", rows[0].Note);
        Assert.Equal("sensor = hot spot - 21 K (FEA map: largest laminate offset 20.0 K + 1 K sensor error)", rows[2].Note);
        Assert.Equal(FactoryA, PdmTempLimits.Of(Dev(v, "A1")));
        Assert.Equal(FactoryB, PdmTempLimits.Of(Dev(v, "B")));
    }

    [Theory]
    [InlineData(125, 125, 6, 5, "Warn must be below critical.")]
    [InlineData(20, 125, 6, 5, "Warn must be 21 to 146 C hot spot (board A1 sensor 0 to 125 C).")]
    [InlineData(119, 147, 6, 5, "Critical must be 21 to 146 C hot spot (board A1 sensor 0 to 125 C).")]
    [InlineData(119, 125, 0, 5, "Recovery hysteresis must be 1 to 30 C.")]
    [InlineData(119, 125, 31, 5, "Recovery hysteresis must be 1 to 30 C.")]
    [InlineData(119, 125, 6, 31, "Critical-soon margin must be 0 to 30 C.")]
    public void BadHotSpotSetRefusedAndNothingChanged(int warn, int crit, int hyst, int margin, string why)
    {
        var v = NewPdm();
        Assert.Equal(why, PdmThermal.Problem(v, new PdmHotSpotLimits(warn, crit, hyst, margin)));
        Assert.Equal(why, PdmThermal.Set(v, new PdmHotSpotLimits(warn, crit, hyst, margin)));
        Assert.All(v.Boards, b => Assert.Equal(b.Role == "B" ? FactoryB : FactoryA, PdmTempLimits.Of(b.Device)));
    }

    [Theory]
    [InlineData(21, 22)]
    [InlineData(145, 146)]
    public void RangeEndsAccepted(int warn, int crit) => Assert.Null(PdmThermal.Problem(NewPdm(), new PdmHotSpotLimits(warn, crit, 6, 5)));

    [Fact]
    public void RatingNotesAboveTheBindingLimit()
    {
        var v = NewPdm();
        Assert.Empty(PdmThermal.RatingNotes(v, new PdmHotSpotLimits(119, 125, 6, 5)));
        static string Note(string b, int s) => $"Board {b} sensor critical {s} C is above 104 C: the MCU beside the sensor is rated 105 C (ADR-2026-11-20-fwsafety).";
        Assert.Equal([Note("A1", 105), Note("A2", 105), Note("B", 105)], PdmThermal.RatingNotes(v, new PdmHotSpotLimits(119, 126, 6, 5)));
        Assert.Equal(["Critical 132 C is above the 130 C laminate limit.", Note("A1", 111), Note("A2", 111), Note("B", 111)],
            PdmThermal.RatingNotes(v, new PdmHotSpotLimits(119, 132, 6, 5)));
        Assert.Equal(3, PdmThermal.RatingNotes(v, new PdmHotSpotLimits(119, 130, 6, 5)).Count);
    }

    // ---------------- boards without a thermal model not on their factory limits: none since hwtemp ----------------

    [Fact]
    public void EveryBoardIsSetFromTheHotSpotSetSoNoneIsListedOffFactory()
    {
        var v = NewPdm();
        Assert.Empty(PdmThermal.OffFactory(v));
        var a2 = Dev(v, "A2").CustomPdm!;
        (a2.TempWarn, a2.TempCrit, a2.TempCritHyst) = (55, 80, 4);   // e.g. an older /pdm wrote the stock values
        Dev(v, "B").CustomPdm!.TempWarn = 90;
        Assert.Empty(PdmThermal.OffFactory(v));                     // every board has a model: the hot-spot set rules
        PdmThermal.RestoreFactory(v);                               // nothing to restore
        Assert.Equal(new PdmTempLimits(55, 80, 4, 5), PdmTempLimits.Of(Dev(v, "A2")));
        Assert.Equal(90, Dev(v, "B").CustomPdm!.TempWarn);
        Assert.Null(PdmCritical.RestoreCheck("factory"));
        Assert.Null(PdmCritical.RestoreCheck(" Factory "));
        Assert.Equal("Type factory to confirm.", PdmCritical.RestoreCheck("80"));
    }

    // ---------------- critical (locked, Unlock + type twice + Change) ----------------

    [Fact]
    public void CriticalItemShowsTheHotSpotAndEachBoard()
    {
        var item = PdmCritical.Items(NewPdm()).Single(i => i.Kind == PdmCriticalKind.CritTemp);
        Assert.Equal("Critical hot-spot temperature, all outputs off", item.Label);
        Assert.Equal("125 C hot spot (A1 sensor 104 C; A2 sensor 104 C; B sensor 104 C)", item.Current);
        Assert.Equal("hot spot, whole C, 120 to 146 (above warn 119 C)", item.Hint);
    }

    [Fact]
    public void CriticalChangeConvertsForEveryBoard()
    {
        var v = NewPdm();
        Assert.Equal("Warn must be below critical.", PdmCritical.Problem(v, PdmCriticalKind.CritTemp, "", "119"));
        Assert.Equal("Type a whole number of degrees C.", PdmCritical.Problem(v, PdmCriticalKind.CritTemp, "", "12x"));
        Assert.Equal(["A1 sensor critical becomes 102 C", "A2 sensor critical becomes 102 C", "B sensor critical becomes 102 C"],
            PdmCritical.Notes(v, PdmCriticalKind.CritTemp, "123 C"));
        Assert.Contains("rated 105 C", PdmCritical.Notes(v, PdmCriticalKind.CritTemp, "127").Last());
        Assert.Empty(PdmCritical.Notes(v, PdmCriticalKind.CritTemp, "abc"));
        Assert.Null(PdmCritical.Apply(v, PdmCriticalKind.CritTemp, "123 C"));
        Assert.Equal([102, 102, 102], v.Boards.Select(b => b.Device.CustomPdm!.TempCrit));
        Assert.Equal([98, 98, 98], v.Boards.Select(b => b.Device.CustomPdm!.TempWarn));
    }

    // ---------------- boot warnings in words (fwsafety: firmware/core/safety.h SAFETY_MSG_*) ----------------

    [Theory]
    [InlineData(1, 0, 0, "watchdog reset: the board restarted itself (outputs were off for the restart)")]
    [InlineData(2, 0, 0, "brown-out reset: the board's supply dipped below about 2.8 V and it restarted")]
    [InlineData(3, 96, 3, "BOR not set (low battery): 9.6 V, needs 10 V; tried again at the next start")]
    [InlineData(4, 3, 0, "BOR write failed: brown-out level reads off after the write; tried again at the next start")]
    [InlineData(4, 0, 0, "BOR write failed: brown-out level reads level 3 after the write; tried again at the next start")]
    public void BootWarningsInWords(int code, int d1, int d2, string words) =>
        Assert.Equal(words, CustomPdmBootMessages.Words(MessageType.Warning, MessageSrc.Init, code, d1, d2));

    [Fact]
    public void OtherMessagesHaveNoWords()
    {
        Assert.Null(CustomPdmBootMessages.Words(MessageType.Error, MessageSrc.Init, 1, 0, 0));
        Assert.Null(CustomPdmBootMessages.Words(MessageType.Warning, MessageSrc.CAN, 1, 0, 0));
        Assert.Null(CustomPdmBootMessages.Words(MessageType.Warning, MessageSrc.Init, 5, 0, 0));
        Assert.Null(CustomPdmBootMessages.Words(MessageType.Warning, MessageSrc.Init, 0, 0, 0));
    }

    // The codes follow the firmware (a renumbering there fails this test)
    [Fact]
    public void BootCodesMatchSafetyH()
    {
        var h = Repo("firmware", "core", "safety.h");
        Assert.Equal(CustomPdmBootMessages.WdgReset, (int)Num(h, @"#define SAFETY_MSG_WDG_RESET (\d+)U"));
        Assert.Equal(CustomPdmBootMessages.BorReset, (int)Num(h, @"#define SAFETY_MSG_BOR_RESET (\d+)U"));
        Assert.Equal(CustomPdmBootMessages.BorLowVbat, (int)Num(h, @"#define SAFETY_MSG_BOR_LOW_VBAT (\d+)U"));
        Assert.Equal(CustomPdmBootMessages.BorFailed, (int)Num(h, @"#define SAFETY_MSG_BOR_FAILED (\d+)U"));
        Assert.Equal(CustomPdmBootMessages.BorMinVbatX10, (int)(Num(h, @"#define SAFETY_BOR_MIN_VBAT ([0-9.]+)f") * 10));
    }
}
