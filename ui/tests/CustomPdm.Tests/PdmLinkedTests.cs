using System.Globalization;
using System.Text.RegularExpressions;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// Route B phase B3 (docs/ui-route-b-plan.md): settings that are set once for the PDM (PdmLinked) and the "New PDM"
// factory defaults (PdmFactoryDefaults). The live proof that the defaults equal the firmware's: PdmB3LiveSimTests.
public class PdmLinkedTests
{
    internal static PdmView NewPdm()
    {
        var devs = PdmFactoryDefaults.Boards.Select(b =>
        {
            var d = StockTests.MakeDevice(b.Type, b.BaseId);
            PdmFactoryDefaults.Apply(d, b.Role);
            return d;
        }).ToList();
        return PdmView.Build(devs);
    }

    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;

    // ---------------- New PDM defaults ----------------

    [Fact]
    public void NewPdmHasOurFactoryValues()
    {
        var v = NewPdm();
        Assert.Equal(["A1", "A2", "B"], v.Boards.Select(b => b.Role));
        Assert.Equal([0x500, 0x540, 0x580], v.Boards.Select(b => b.Device.BaseId));
        Assert.All(v.Boards, b => Assert.Equal(CanBitRate.BitRate1000K, b.Device.BitRate));
        Assert.All(v.Boards, b => Assert.All(b.Device.Outputs, o => Assert.Equal(ResetMode.Count, o.ResetMode)));
        Assert.Equal([0, 2, 0], v.Boards.Select(b => b.Device.CustomPdm!.CritExemptMask));
        Assert.All(v.Boards, b => Assert.Equal(new PdmTempLimits(55, 80, 6, 5), PdmTempLimits.Of(b.Device)));
        Assert.All(v.Boards, b => Assert.True(b.Device.CustomPdm!.FactoryNew));
        // w3a: current limit = each output's rating (A2 OUT2, the fan: 1 A); inrush limits stay 50 A (fan 2 A)
        Assert.Equal([7.5, 7.5, 7.5, 7.5, 7.5, 7.5, 7.5, 7.5], Dev(v, "A1").Outputs.Select(o => o.CurrentLimit));
        Assert.Equal([7.5, 1.0, 7.5, 7.5, 7.5, 7.5, 7.5, 7.5], Dev(v, "A2").Outputs.Select(o => o.CurrentLimit));
        Assert.Equal([31.0, 31.0, 31.0, 31.0, 15.0, 15.0, 15.0, 15.0], Dev(v, "B").Outputs.Select(o => o.CurrentLimit));
        Assert.Equal(24, v.Outputs.Count);
        Assert.All(v.Outputs, o => Assert.Equal(o.Number == 10 ? 2.0 : 50.0, o.Output.InrushCurrentLimit));
        Assert.Empty(v.OverRating); // /pdm shows no "above rating" warning for a New PDM

        var a2 = Dev(v, "A2");
        var fan = a2.Outputs[1];
        Assert.True(fan.Enabled);
        Assert.Equal((1.0, 2.0), (fan.CurrentLimit, fan.InrushCurrentLimit));
        Assert.Equal(PdmFactoryDefaults.VarOf(a2, a2.VirtualInputs[13]), fan.Input); // the fan latch
        Assert.Equal(new PdmFanThresholds(45, 40), PdmLinked.FanThresholds(a2));
        Assert.Null(PdmLinked.FanLayoutProblem(a2));
        Assert.Equal([0x502, 0x502, 0x582, 0x582], a2.CanInputs.Skip(24).Take(4).Select(c => c.Id));
        Assert.Empty(PdmLinked.FanRemoteIdProblems(v));
        // A1 and B: no fan logic, the load-shed example prefilled but off
        foreach (var role in new[] { "A1", "B" })
        {
            var d = Dev(v, role);
            Assert.DoesNotContain(d.Outputs, o => o.Enabled);
            Assert.DoesNotContain(d.CanInputs, c => c.Enabled);
            Assert.DoesNotContain(d.Conditions, c => c.Enabled);
            Assert.Equal([70.0, 65.0, 75.0, 70.0], d.Conditions.Skip(d.Conditions.Count - 4).Select(c => c.Arg));
        }
    }

    // The C# defaults follow firmware/tools_custom/port_boards.py (base IDs, fan thresholds). The full check of every
    // param is the live sim test; this one also runs without the sim.
    [Fact]
    public void DefaultsMatchPortBoardsPy()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "firmware", "tools_custom", "port_boards.py"))) dir = dir.Parent;
        Assert.NotNull(dir);
        var py = File.ReadAllText(Path.Combine(dir!.FullName, "firmware", "tools_custom", "port_boards.py"));
        var bases = Regex.Match(py, @"BASE_A1, BASE_A2, BASE_B = 0x([0-9A-Fa-f]+), 0x([0-9A-Fa-f]+), 0x([0-9A-Fa-f]+)");
        Assert.True(bases.Success);
        Assert.Equal([PdmFactoryDefaults.BaseA1, PdmFactoryDefaults.BaseA2, PdmFactoryDefaults.BaseB],
            Enumerable.Range(1, 3).Select(i => Convert.ToInt32(bases.Groups[i].Value, 16)));
        Assert.Equal(PdmFactoryDefaults.CyclicTxOffset, int.Parse(Regex.Match(py, @"CYCLIC_TX_OFFSET = (\d+)").Groups[1].Value));
        double Num(string name) => double.Parse(Regex.Match(py, $@"#define {name} ([0-9.]+)f").Groups[1].Value, CultureInfo.InvariantCulture);
        Assert.Equal(PdmFactoryDefaults.FanOnC, Num("FAN_ON_C"));
        Assert.Equal(PdmFactoryDefaults.FanOffC, Num("FAN_OFF_C"));
        Assert.Equal(PdmFactoryDefaults.FanCanIn0, int.Parse(Regex.Match(py, @"#define FAN_CANIN0 (\d+)").Groups[1].Value));
        // w3a current limits: board A, board B OUT1-4, board B OUT5-8, the fan
        var lim = Regex.Match(py, @"LIMIT_A, LIMIT_B_STUD, LIMIT_B, LIMIT_FAN = ([0-9.]+), ([0-9.]+), ([0-9.]+), ([0-9.]+)");
        Assert.True(lim.Success);
        Assert.Equal(Enumerable.Range(1, 4).Select(i => double.Parse(lim.Groups[i].Value, CultureInfo.InvariantCulture)),
            new[] { PdmFactoryDefaults.CurrentLimit("A1", 0), PdmFactoryDefaults.CurrentLimit("B", 0), PdmFactoryDefaults.CurrentLimit("B", 4), PdmFactoryDefaults.FanCurrentLimit });
    }

    [Fact]
    public void NewPdmMayBeWrittenWithoutRead_aLoadedOrHandAddedBoardMayNot()
    {
        var v = NewPdm();
        Assert.All(v.Boards, b => Assert.Null(CustomPdmGuards.WriteAllBlockedReason(b.Device)));
        Assert.All(v.Boards, b => Assert.NotEmpty(b.Device.GetWriteMsgs(true)));
        var hand = StockTests.MakeDevice(14, 0x500);  // added on the Devices page: stock PC defaults
        Assert.Equal(CustomPdmGuards.WriteAllNeedsReadReason, CustomPdmGuards.WriteAllBlockedReason(hand));
        Assert.Empty(hand.GetWriteMsgs(true));
    }

    [Fact]
    public void PdmWriteAllAllowedOnANewPdmProject()
    {
        Assert.Null(PdmOps.BlockedReason(PdmOpKind.WriteAll, NewPdm(), true, _ => true));
        Assert.Null(PdmOps.BlockedReason(PdmOpKind.Burn, NewPdm(), true, _ => true));
        var hand = PdmView.Build([StockTests.MakeDevice(14, 0x500), StockTests.MakeDevice(14, 0x540), StockTests.MakeDevice(15, 0x580)]);
        Assert.Equal("A1: not read yet (Read All first); A2: not read yet (Read All first); B: not read yet (Read All first).",
            PdmOps.BlockedReason(PdmOpKind.WriteAll, hand, true, _ => true));
    }

    // ---------------- temperature limits, one set for the three boards (u1a) ----------------

    [Fact]
    public void TempLimitsSetOnAllThreeBoards()
    {
        var v = NewPdm();
        Assert.False(PdmLinked.TempLimitsDiffer(v));
        Dev(v, "B").CustomPdm!.TempWarn = 60;
        Assert.True(PdmLinked.TempLimitsDiffer(v));
        Assert.Equal([55, 55, 60], PdmLinked.TempLimitsByBoard(v).Select(t => t.Limits.Warn));

        Assert.Null(PdmLinked.SetTempLimits(v, new PdmTempLimits(58, 85, 4, 7)));
        Assert.False(PdmLinked.TempLimitsDiffer(v));
        Assert.All(v.Boards, b => Assert.Equal(new PdmTempLimits(58, 85, 4, 7), PdmTempLimits.Of(b.Device)));
        Assert.All(v.Boards, b => Assert.True(b.Device.CustomPdm!.IsValid()));
    }

    [Theory]
    [InlineData(80, 80, 6, 5, "Warn must be below critical.")]
    [InlineData(55, 126, 6, 5, "Critical must be 0 to 125 C.")]
    [InlineData(-1, 80, 6, 5, "Warn must be 0 to 125 C.")]
    [InlineData(55, 80, 0, 5, "Recovery hysteresis must be 1 to 30 C.")]
    [InlineData(55, 80, 31, 5, "Recovery hysteresis must be 1 to 30 C.")]
    [InlineData(55, 80, 6, 31, "Critical-soon margin must be 0 to 30 C.")]
    public void BadTempLimitsRefusedAndNothingChanged(int warn, int crit, int hyst, int margin, string why)
    {
        var v = NewPdm();
        Assert.Equal(why, PdmLinked.SetTempLimits(v, new PdmTempLimits(warn, crit, hyst, margin)));
        Assert.All(v.Boards, b => Assert.Equal(new PdmTempLimits(55, 80, 6, 5), PdmTempLimits.Of(b.Device)));
    }

    // ---------------- fan on / off: 6 params on A2 that move together ----------------

    [Fact]
    public void FanThresholdsSetAllSixParams()
    {
        var a2 = Dev(NewPdm(), "A2");
        Assert.Null(PdmLinked.SetFanThresholds(a2, new PdmFanThresholds(50.5, 44)));
        var c0 = PdmFactoryDefaults.FanCond0(a2);
        Assert.Equal([50.5, 44.0], [a2.Conditions[c0].Arg, a2.Conditions[c0 + 1].Arg]);
        Assert.Equal([50.5, 44.0, 50.5, 44.0], a2.CanInputs.Skip(24).Take(4).Select(c => c.Operand));
        Assert.Equal(new PdmFanThresholds(50.5, 44), PdmLinked.FanThresholds(a2));
        // nothing else of the fan logic moved
        Assert.Equal(Operator.GreaterThanOrEqual, a2.Conditions[c0].Operator);
        Assert.Equal([0x502, 0x502, 0x582, 0x582], a2.CanInputs.Skip(24).Take(4).Select(c => c.Id));
    }

    [Theory]
    [InlineData(40, 40, "Fan off must be below fan on.")]
    [InlineData(40, 45, "Fan off must be below fan on.")]
    [InlineData(126, 40, "Fan on must be 0 to 125 C.")]
    [InlineData(45, -1, "Fan off must be 0 to 125 C.")]
    public void BadFanThresholdsRefused(double on, double off, string why)
    {
        var a2 = Dev(NewPdm(), "A2");
        Assert.Equal(why, PdmLinked.SetFanThresholds(a2, new PdmFanThresholds(on, off)));
        Assert.Equal(new PdmFanThresholds(45, 40), PdmLinked.FanThresholds(a2));
    }

    [Fact]
    public void FanParamsThatDisagreeAreShownAsDiffering()
    {
        var a2 = Dev(NewPdm(), "A2");
        a2.CanInputs[26].Operand = 47; // B hot threshold changed by hand on A2's own page
        Assert.Null(PdmLinked.FanThresholds(a2));
        Assert.Contains("B hot (CAN input 27) 47", string.Join("; ", PdmLinked.FanParamsText(a2)));
        Assert.Null(PdmLinked.SetFanThresholds(a2, new PdmFanThresholds(45, 40))); // set once: consistent again
        Assert.Equal(new PdmFanThresholds(45, 40), PdmLinked.FanThresholds(a2));
    }

    [Theory]
    [InlineData("canIn25op")]
    [InlineData("canIn27off")]
    [InlineData("condOnOff")]
    [InlineData("condOffOp")]
    [InlineData("condOnInput")]
    public void FanLogicChangedByHandIsNotTouched(string change)
    {
        var a2 = Dev(NewPdm(), "A2");
        var c0 = PdmFactoryDefaults.FanCond0(a2);
        switch (change)
        {
            case "canIn25op": a2.CanInputs[25].Operator = Operator.GreaterThan; break;
            case "canIn27off": a2.CanInputs[27].Enabled = false; break;
            case "condOnOff": a2.Conditions[c0].Enabled = false; break;
            case "condOffOp": a2.Conditions[c0 + 1].Operator = Operator.GreaterThanOrEqual; break;
            case "condOnInput": a2.Conditions[c0].Input = 0; break;
        }
        Assert.NotNull(PdmLinked.FanLayoutProblem(a2));
        Assert.Equal(PdmLinked.FanLayoutProblem(a2), PdmLinked.SetFanThresholds(a2, new PdmFanThresholds(50, 44)));
        Assert.Equal(45.0, a2.CanInputs[24].Operand);
    }

    // ---------------- base IDs ----------------

    [Theory]
    [InlineData("A1", 0x400, null)]
    [InlineData("A1", 0x518, null)]
    [InlineData("A1", 0x519, "A1 0x519-0x540 would overlap A2 (0x540-0x567).")]
    [InlineData("A1", 0x528, "A1 0x528-0x54F would overlap A2 (0x540-0x567).")]
    [InlineData("A2", 0x5A0, "A2 0x5A0-0x5C7 would overlap B (0x580-0x5A7).")]
    [InlineData("A2", 0x559, "A2 0x559-0x580 would overlap B (0x580-0x5A7).")]
    [InlineData("A2", 0x558, null)]
    [InlineData("B", 0x550, "B 0x550-0x577 would overlap A2 (0x540-0x567).")]
    [InlineData("B", 0x600, null)]
    [InlineData("B", 0x7D8, null)]
    [InlineData("B", 0x7D9, "Base ID must be 0x000 to 0x7D8 (the board uses base to base + 0x27).")]
    [InlineData("A2", 0x4F0, "A2 must stay above A1 (0x500): the PDM page tells the two A boards apart by base ID.")]
    [InlineData("A1", 0x600, "A1 must stay below A2 (0x540): the PDM page tells the two A boards apart by base ID.")]
    [InlineData("A1", 0x541, "A1 must stay below A2 (0x540): the PDM page tells the two A boards apart by base ID.")]
    public void BaseIdChecks(string role, int newBase, string? why)
    {
        Assert.Equal(why, PdmLinked.BaseIdProblem(NewPdm(), role, newBase));
    }

    [Fact]
    public void BoardBlockIsWhatTheSignalsFileUses()
    {
        foreach (var b in NewPdm().Boards)
            Assert.Equal(PdmLinked.BlockSize, b.Device.MaxCyclicId - b.Device.BaseId + 1);
    }

    [Fact]
    public void MovingA1OrBMovesTheFanInputsOnA2()
    {
        var v = NewPdm();
        var a2 = Dev(v, "A2");
        Assert.Equal(["A2 CAN inputs 25, 26 (fan, A1 temperature) -> 0x402"], PdmLinked.FollowBaseId(v, "A1", 0x400));
        Assert.Equal(["A2 CAN inputs 27, 28 (fan, B temperature) -> 0x602"], PdmLinked.FollowBaseId(v, "B", 0x600));
        Assert.Equal([0x402, 0x402, 0x602, 0x602], a2.CanInputs.Skip(24).Take(4).Select(c => c.Id));
        Assert.Empty(PdmLinked.FollowBaseId(v, "A2", 0x570)); // nothing listens to A2
    }

    [Fact]
    public void FanInputsNotOnTheBoardsAreFlagged()
    {
        var v = NewPdm();
        Dev(v, "A1").BaseId = 0x400; // e.g. moved on the Devices page
        Assert.Equal(["A2 CAN inputs 25, 26 (fan, A1 temperature) listen to 0x502, A1 sends its temperature on 0x402."],
            PdmLinked.FanRemoteIdProblems(v));
        PdmLinked.PointFanAtBoards(v);
        Assert.Empty(PdmLinked.FanRemoteIdProblems(v));
        Assert.Equal(0x402, Dev(v, "A2").CanInputs[24].Id);
    }

    [Fact]
    public void OtherLinksIntoTheMovedBlockAreWarned()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        (b.CanInputs[3].Enabled, b.CanInputs[3].Id) = (true, 0x503);      // a hand-made link B <- A1 msg 1
        (b.CanOutputs[0].Enabled, b.CanOutputs[0].Id) = (true, 0x410);   // B sends on 0x410
        Assert.Equal(
        [
            "B CAN input 4 listens to 0x503 (A1's old block): change it by hand.",
            "B CAN output 1 sends on 0x410, inside A1's new block 0x400-0x427."
        ], PdmLinked.BaseIdWarnings(v, "A1", 0x400));
    }

    // stock fix (FwDevice.MaxCyclicId): a device that moves to a higher base ID still hears its own frames
    [Fact]
    public void DeviceHearsItsFramesAfterABaseIdChange()
    {
        var dev = StockTests.MakeDevice(14, 0x500);
        dev.BaseId = 0x600;
        Assert.True(dev.InIdRange(0x600 + 0x27));
        Assert.False(dev.InIdRange(0x527));
        Assert.False(dev.InIdRange(0x628));
    }
}
