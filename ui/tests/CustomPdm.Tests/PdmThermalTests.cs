using System.Globalization;
using System.Text.RegularExpressions;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// ADR-2026-11-20-temp-onepdm: /pdm keeps ONE temperature set, entered as the board hot-spot (laminate) temperature;
// the tool converts it per board with that board's sensor -> hot-spot offset (board B: the FEA map of
// docs/system-verification.md); board A has no thermal model yet, so it keeps its own (factory) limits and never gets
// another board's. The live proof on the firmware: PdmThermalLiveSimTests.
public class PdmThermalTests
{
    private static PdmView NewPdm() => PdmLinkedTests.NewPdm();
    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;
    private static readonly PdmTempLimits FactoryA = new(55, 80, 6, 5), FactoryB = new(98, 104, 6, 5);

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
        Assert.Equal(PdmThermal.BoardBLaminateOffsetK, Num(doc, @"laminate = U6 \+ [0-9.]+ \.\. ([0-9.]+) K"));
        var box = Repo("tools", "verify_thermal_box.py");
        Assert.Equal(PdmThermal.SensorErrorK, Num(box, @"SENSOR_ERR = ([0-9.]+)"));
        Assert.Equal(PdmThermal.LaminateMaxC, Num(box, @"LAMINATE_C, TJ_C = ([0-9.]+),"));
        var py = Repo("firmware", "tools_custom", "port_boards.py");
        Assert.Equal(PdmThermal.BoardBLaminateOffsetK, Num(py, @"laminate = sensor \+ [0-9.]+ \.\. ([0-9.]+) K"));
        Assert.Equal(20, PdmThermal.BoardBOffsetK);
        // the binding limit of ADR-2026-11-20-fwsafety: logic-area parts at the sensor + 1 K <= 105 C
        Assert.Equal(104, PdmThermal.BoardBSensorCritMaxC);
        // board B's factory critical sits exactly on the documented laminate result (124.0 C)
        Assert.Equal(Num(doc, @"critical 104 C \(\+1 C MCP9808, largest offset\) \| ([0-9.]+) /"), CustomPdmSettings.DefaultTempCritB + PdmThermal.BoardBOffsetK);
    }

    [Fact]
    public void OnlyBoardBHasAThermalModel()
    {
        var v = NewPdm();
        Assert.Equal([null, null, 20], v.Boards.Select(b => PdmThermal.OffsetK(b.Device)));
        Assert.Equal(15, Dev(v, "B").DeviceTypeId);
    }

    // ---------------- conversion ----------------

    [Fact]
    public void HotSpotSetOfANewPdmIsBoardBFactoryPlusOffset()
    {
        var v = NewPdm();
        Assert.Equal(new PdmHotSpotLimits(118, 124, 6, 5), PdmThermal.Current(v));
        Assert.Equal(new PdmTempLimits(98, 104, 6, 5), PdmThermal.ToSensor(new PdmHotSpotLimits(118, 124, 6, 5), 20));
        Assert.Equal(new PdmHotSpotLimits(118, 124, 6, 5), PdmThermal.FromSensor(FactoryB, 20));
    }

    [Fact]
    public void NoHotSpotSetWithoutBoardB()
    {
        var v = PdmView.Build(NewPdm().Boards.Where(b => b.Role != "B").Select(b => b.Device).ToList());
        Assert.Null(PdmThermal.Current(v));
        Assert.Equal(PdmThermal.NoModelBoard, PdmThermal.Set(v, new PdmHotSpotLimits(110, 120, 6, 5)));
        Assert.All(v.Boards, b => Assert.Equal(FactoryA, PdmTempLimits.Of(b.Device)));
    }

    // 'Set on A1, A2, B' must not copy A's values to B (nor B's to A): B gets the converted set, A keeps its own
    [Fact]
    public void SetConvertsForBoardBAndLeavesBoardAAlone()
    {
        var v = NewPdm();
        var a1 = Dev(v, "A1").CustomPdm!;
        (a1.TempWarn, a1.TempCrit) = (60, 85);              // A1 holds something else: still not copied anywhere
        Assert.Null(PdmThermal.Set(v, new PdmHotSpotLimits(115, 122, 4, 7)));
        Assert.Equal(new PdmTempLimits(95, 102, 4, 7), PdmTempLimits.Of(Dev(v, "B")));
        Assert.Equal(new PdmTempLimits(60, 85, 6, 5), PdmTempLimits.Of(Dev(v, "A1")));
        Assert.Equal(FactoryA, PdmTempLimits.Of(Dev(v, "A2")));
        Assert.Equal(new PdmHotSpotLimits(115, 122, 4, 7), PdmThermal.Current(v));
        Assert.All(v.Boards, b => Assert.True(b.Device.CustomPdm!.IsValid()));
    }

    [Fact]
    public void PreviewShowsEachBoardsSensorLimitAndChangesNothing()
    {
        var v = NewPdm();
        var rows = PdmThermal.Preview(v, new PdmHotSpotLimits(115, 122, 4, 7));
        Assert.Equal(["A1", "A2", "B"], rows.Select(r => r.Role));
        Assert.Equal([FactoryA, FactoryA, new PdmTempLimits(95, 102, 4, 7)], rows.Select(r => r.Sensor));
        Assert.Equal([false, false, true], rows.Select(r => r.Converted));
        Assert.Equal("no thermal model yet: keeps its own limits (factory 55 / 80 C)", rows[0].Note);
        Assert.Equal("sensor = hot spot - 20 K (FEA map: largest laminate offset 19.0 K + 1 K sensor error)", rows[2].Note);
        Assert.Equal(FactoryB, PdmTempLimits.Of(Dev(v, "B")));
    }

    [Theory]
    [InlineData(124, 124, 6, 5, "Warn must be below critical.")]
    [InlineData(19, 124, 6, 5, "Warn must be 20 to 145 C hot spot (board B sensor 0 to 125 C).")]
    [InlineData(118, 146, 6, 5, "Critical must be 20 to 145 C hot spot (board B sensor 0 to 125 C).")]
    [InlineData(118, 124, 0, 5, "Recovery hysteresis must be 1 to 30 C.")]
    [InlineData(118, 124, 31, 5, "Recovery hysteresis must be 1 to 30 C.")]
    [InlineData(118, 124, 6, 31, "Critical-soon margin must be 0 to 30 C.")]
    public void BadHotSpotSetRefusedAndNothingChanged(int warn, int crit, int hyst, int margin, string why)
    {
        var v = NewPdm();
        Assert.Equal(why, PdmThermal.Problem(v, new PdmHotSpotLimits(warn, crit, hyst, margin)));
        Assert.Equal(why, PdmThermal.Set(v, new PdmHotSpotLimits(warn, crit, hyst, margin)));
        Assert.All(v.Boards, b => Assert.Equal(b.Role == "B" ? FactoryB : FactoryA, PdmTempLimits.Of(b.Device)));
    }

    [Theory]
    [InlineData(20, 21)]
    [InlineData(144, 145)]
    public void RangeEndsAccepted(int warn, int crit) => Assert.Null(PdmThermal.Problem(NewPdm(), new PdmHotSpotLimits(warn, crit, 6, 5)));

    [Fact]
    public void RatingNotesAboveTheBindingLimit()
    {
        var v = NewPdm();
        Assert.Empty(PdmThermal.RatingNotes(v, new PdmHotSpotLimits(118, 124, 6, 5)));
        Assert.Equal(["Board B sensor critical 105 C is above 104 C: the MCU and FRAM beside the sensor are rated 105 C (ADR-2026-11-20-fwsafety)."],
            PdmThermal.RatingNotes(v, new PdmHotSpotLimits(118, 125, 6, 5)));
        Assert.Equal(["Critical 131 C is above the 130 C laminate limit.",
                      "Board B sensor critical 111 C is above 104 C: the MCU and FRAM beside the sensor are rated 105 C (ADR-2026-11-20-fwsafety)."],
            PdmThermal.RatingNotes(v, new PdmHotSpotLimits(118, 131, 6, 5)));
        Assert.Single(PdmThermal.RatingNotes(v, new PdmHotSpotLimits(118, 130, 6, 5)));
    }

    // ---------------- board A not on its factory limits (e.g. written by an older /pdm that copied one set) ----------------

    [Fact]
    public void BoardANotOnFactoryIsShownAndCanBeRestored()
    {
        var v = NewPdm();
        Assert.Empty(PdmThermal.OffFactory(v));
        var a2 = Dev(v, "A2").CustomPdm!;
        (a2.TempWarn, a2.TempCrit, a2.TempCritHyst) = (98, 104, 4);
        Dev(v, "B").CustomPdm!.TempWarn = 90;                  // B is set from the hot-spot set: never listed here
        Assert.Equal(["A2 holds 98 / 104 / 4 / 5, factory 55 / 80 / 6 / 5 (warn / critical / recovery / margin)."], PdmThermal.OffFactory(v));
        PdmThermal.RestoreFactory(v);
        Assert.Empty(PdmThermal.OffFactory(v));
        Assert.All(v.Boards.Where(b => b.Role != "B"), b => Assert.Equal(FactoryA, PdmTempLimits.Of(b.Device)));
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
        Assert.Equal("124 C hot spot (A1 sensor 80 C, kept; A2 sensor 80 C, kept; B sensor 104 C)", item.Current);
        Assert.Equal("hot spot, whole C, 119 to 145 (above warn 118 C)", item.Hint);
    }

    [Fact]
    public void CriticalChangeConvertsForBoardBOnly()
    {
        var v = NewPdm();
        Assert.Equal("Warn must be below critical.", PdmCritical.Problem(v, PdmCriticalKind.CritTemp, "", "118"));
        Assert.Equal("Type a whole number of degrees C.", PdmCritical.Problem(v, PdmCriticalKind.CritTemp, "", "12x"));
        Assert.Equal(["A1 sensor critical stays 80 C (no thermal model yet)", "A2 sensor critical stays 80 C (no thermal model yet)", "B sensor critical becomes 102 C"],
            PdmCritical.Notes(v, PdmCriticalKind.CritTemp, "122 C"));
        Assert.Contains("rated 105 C", PdmCritical.Notes(v, PdmCriticalKind.CritTemp, "126").Last());
        Assert.Empty(PdmCritical.Notes(v, PdmCriticalKind.CritTemp, "abc"));
        Assert.Null(PdmCritical.Apply(v, PdmCriticalKind.CritTemp, "122 C"));
        Assert.Equal([80, 80, 102], v.Boards.Select(b => b.Device.CustomPdm!.TempCrit));
        Assert.Equal([55, 55, 98], v.Boards.Select(b => b.Device.CustomPdm!.TempWarn));
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
