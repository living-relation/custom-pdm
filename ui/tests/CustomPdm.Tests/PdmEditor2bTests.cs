using domain.CustomPdm;
using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// One-PDM editor phase 2b (editor2b): counters, math, levels as signals, other-board values, keypad buttons, starter
// interlock, master retry, CAN outputs (PdmValues). Live proof: PdmEditor2bLiveSimTests.
// Numbers: outputs A1 1-8, A2 9-16 (10 = fans), B 17-24; digital inputs A1 1-7, A2 8-14, B 15-24.
public class PdmEditor2bTests
{
    private static PdmView NewPdm() => PdmLinkedTests.NewPdm();
    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;
    private static int Di(FwDevice d, int i) => PdmFactoryDefaults.VarOf(d, d.DigitalInputs[i]);
    private static PdmModel M(PdmView v) => PdmModel.Build(v);
    private static int Free(PdmView v, string role, PdmResKind k) => M(v).FreeOf(role, k).Count;
    private static void NoConflicts(PdmView v) => Assert.Empty(M(v).Problems.Where(p => !p.Text.EndsWith("which is not enabled.")));
    private static string Words(PdmView v, PdmResKind k, string role, int i) => PdmValues.All(M(v)).Single(f => f.Main == new PdmRes(role, k, i)).Words;

    [Fact]
    public void CounterIsOneCounterInWordsAndAnyoneMayReadIt()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var spec = new PdmCounterSpec("B", PdmTerm.In(15), Reset: PdmTerm.In(1), Max: 3, HoldResetMs: 2000);  // reset from A1 over CAN
        Assert.Equal(new Dictionary<PdmResKind, int> { [PdmResKind.Counter] = 1, [PdmResKind.CanInput] = 1 }, PdmValues.CounterCost(v, spec));
        Assert.Null(PdmValues.AddCounter(v, spec, out var i));
        var c = b.Counters[i];
        Assert.True(c is { Enabled: true, MinCount: 0, MaxCount: 3, WrapAround: true, HoldToReset: true, ResetTime: 2000 });
        Assert.Equal(Di(b, 0), c.IncInput);
        Assert.Equal("counter: up on IN15, reset on IN1, 0 to 3 (wraps), hold 2 s to reset", Words(v, PdmResKind.Counter, "B", i));
        Assert.Equal(PdmClaimKind.Value, M(v).ClaimOf(new PdmRes("B", PdmResKind.Counter, i)).Kind);
        Assert.Equal(PdmClaimKind.Value, M(v).ClaimOf(new PdmRes("B", PdmResKind.CanInput, 0)).Kind);  // its A1 IN1 slot
        // a trigger level on the counter: nobody complains, the counter cannot be removed while read
        var cv = PdmFactoryDefaults.VarOf(b, c);
        Assert.Contains(PdmTriggers.ValueChoices(M(v), "B"), x => x.Var == cv);
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Level(new PdmThreshold(cv, true, 2, 1))));
        NoConflicts(v);
        Assert.Contains("used by", PdmValues.Remove(v, new PdmRes("B", PdmResKind.Counter, i)));
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.None));
        Assert.Null(PdmValues.Remove(v, new PdmRes("B", PdmResKind.Counter, i)));
        Assert.Equal((4, 32), (Free(v, "B", PdmResKind.Counter), Free(v, "B", PdmResKind.CanInput)));
    }

    [Fact]
    public void MathIsAOpBTimesFactorPlusOffset()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var temp = PdmFactoryDefaults.BoardTempVar(b);
        var bat = b.VarMap.First(e => e.Owner == null && e.GetName() == "Battery Voltage").VariableIndex;
        Assert.Null(PdmValues.AddMath(v, new PdmMathSpec("B", MathOp.Add, temp, ConstB: 10, Factor: 0.5, Offset: -3), out var i));
        Assert.True(b.MathBlocks[i] is { Enabled: true, Operation: MathOp.Add, InputB: 0, ConstB: 10, Factor: 0.5, Offset: -3 });
        Assert.Equal("math: (B board temperature (C) + 10) x 0.5 - 3", Words(v, PdmResKind.Math, "B", i));
        Assert.Null(PdmValues.AddMath(v, new PdmMathSpec("B", MathOp.Max, temp, bat), out var j));
        Assert.Equal("math: (the higher of B board temperature (C) and B battery voltage (V))", Words(v, PdmResKind.Math, "B", j));
        Assert.Contains("factor", PdmValues.AddMath(v, new PdmMathSpec("B", MathOp.Add, temp, Factor: 0), out _));
        for (var k = 2; k < 8; k++) Assert.Null(PdmValues.AddMath(v, new PdmMathSpec("B", MathOp.Add, temp), out _));
        var before = PdmTriggersTests.Raw(v);
        Assert.Contains("B is full", PdmValues.AddMath(v, new PdmMathSpec("B", MathOp.Add, temp), out _));
        Assert.Equal(before, PdmTriggersTests.Raw(v));
    }

    [Fact]
    public void LevelIsASignalForAndOrTerms()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var temp = PdmFactoryDefaults.BoardTempVar(b);
        Assert.Null(PdmValues.AddLevel(v, "B", new PdmThreshold(temp, true, 50, 45), out var lv));
        Assert.Contains(PdmTriggers.SignalChoices(M(v), "B"), c => c.Var == lv && c.Text == "level (B board temperature (C) on at 50 or more, off at 45 or less)");
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Logic(PdmLogicOp.And, PdmTerm.In(15), PdmTerm.Of(lv))));
        Assert.Equal("IN15 AND level (B board temperature (C) on at 50 or more, off at 45 or less)", PdmTriggers.Of(M(v), 17).Words);
        NoConflicts(v);
        // replacing the trigger leaves the level (a value of its own)
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(PdmTerm.In(15)), overwrite: true));
        Assert.Single(PdmValues.All(M(v)), f => f.Kind == PdmValueKind.Level);
        Assert.Contains("Off must be below on", PdmValues.AddLevel(v, "B", new PdmThreshold(temp, true, 50, 55), out _));
    }

    [Fact]
    public void ValueOfAnotherBoardIsItsCyclicSignalReadHere()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var sigs = PdmValues.RemoteSignals(v, "A1", out var ids);
        Assert.DoesNotContain(ids, id => id == 0x500 + PdmLinks.StatusOffset);  // not msg 37
        var mv = sigs.Single(s => s.Name == "A1_BoardTemp");
        var s0 = PdmValues.AddRemoteValue(v, "B", "A1", mv.Name, out var why);
        Assert.Null(why);
        var c = b.CanInputs[s0];
        Assert.Equal((ids[sigs.ToList().IndexOf(mv)], mv.StartBit, mv.Length), (c.Id, c.StartBit, c.BitLength));
        Assert.StartsWith("CAN value: A1's frame 0x5", Words(v, PdmResKind.CanInput, "B", s0));
        var val = PdmFactoryDefaults.CanInState(b, s0) + 1;
        Assert.Contains(PdmTriggers.ValueChoices(M(v), "B"), x => x.Var == val);
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Level(new PdmThreshold(val, true, 50, 45))));
        NoConflicts(v);
        Assert.Contains("same board", PdmValues.AddRemoteValue(v, "B", "B", mv.Name, out var w2) < 0 ? w2 : "");
    }

    [Fact]
    public void KeypadButtonIsACanInputAndANodeInsideAPdmBlockIsRefused()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Contains("uses ID 0x515, inside A1's block (0x500-0x527): set the keypad to another node, e.g. 0x28", PdmValues.KeypadClash(v, 0x15));   // Blink default node: backlight 0x500 + 0x15
        Assert.Contains("uses ID 0x515", PdmValues.AddKeypadButton(v, "B", 0x15, 1, out var why) < 0 ? why : "");
        Assert.Null(PdmValues.KeypadClash(v, 0x28));                               // free: 0x28-0x3F, 0x68-0x7F
        Assert.NotNull(PdmValues.KeypadClash(v, 0x50));                            // 0x500 + 0x50 = 0x550: A2
        var s = PdmValues.AddKeypadButton(v, "B", 0x2A, 3, out why);
        Assert.Null(why);
        Assert.True(b.CanInputs[s] is { Id: 0x1AA, StartBit: 2, BitLength: 1, Operator: Operator.Equal, Operand: 1.0, TimeoutEnabled: true });
        Assert.Equal("keypad node 0x2A button 3", Words(v, PdmResKind.CanInput, "B", s));
        var bv = PdmFactoryDefaults.CanInState(b, s);
        Assert.Contains(PdmTriggers.SignalChoices(M(v), "B"), c => c.Var == bv);
        Assert.Null(PdmTriggers.Set(v, 19, PdmTriggerSpec.Input(PdmTerm.Of(bv))));
        NoConflicts(v);
    }

    [Fact]
    public void StarterInterlockSetsTheStarterBlockOfEachBoardWithAShedOutput()
    {
        var v = NewPdm();
        var (a1, b) = (Dev(v, "A1"), Dev(v, "B"));
        Assert.Null(PdmValues.SetStarter(v, PdmTerm.In(15), [1, 2, 22]));      // crank = B IN1; lamps on A1, A/C clutch on B
        Assert.True(b.StarterDisable is { Enabled: true });
        Assert.Equal(Di(b, 0), b.StarterDisable.Input);
        Assert.Equal([false, false, false, false, false, true, false, false], b.StarterDisable.OutputsDisabled);
        Assert.True(a1.StarterDisable is { Enabled: true });
        Assert.Equal([true, true, false, false, false, false, false, false], a1.StarterDisable.OutputsDisabled);
        Assert.Equal(PdmClaimKind.Value, M(v).ClaimOf(new PdmRes("A1", PdmResKind.CanInput, 0)).Kind);   // B IN1 over CAN
        Assert.False(Dev(v, "A2").StarterDisable.Enabled);
        Assert.Contains("starter interlock: while IN15 is on, outputs 1, 2 are held off", PdmValues.All(M(v)).Select(f => f.Words));
        Assert.Contains("own fans", PdmValues.SetStarter(v, PdmTerm.In(15), [10]));
        NoConflicts(v);
        Assert.Null(PdmValues.SetStarter(v, PdmTerm.In(15), [22]));
        Assert.False(a1.StarterDisable.Enabled);
        Assert.Equal(32, Free(v, "A1", PdmResKind.CanInput));                  // the A1 slot is freed again
    }

    [Fact]
    public void MasterRetryIsSetOnAllThreeBoards()
    {
        var v = NewPdm();
        Assert.Null(PdmValues.SetRetry(v, PdmTerm.In(15)));
        Assert.Equal(Di(Dev(v, "B"), 0), Dev(v, "B").CustomPdm!.MasterRetryInput);
        foreach (var r in new[] { "A1", "A2" })
        {
            var d = Dev(v, r);
            Assert.Equal(PdmFactoryDefaults.CanInState(d, 0), d.CustomPdm!.MasterRetryInput);   // B IN1 over CAN, slot 1
            Assert.Equal(PdmClaimKind.Value, M(v).ClaimOf(new PdmRes(r, PdmResKind.CanInput, 0)).Kind);
        }
        Assert.Contains("master retry: IN15 switching on clears the faults of every A2 output", PdmValues.All(M(v)).Select(f => f.Words));
        NoConflicts(v);
        Assert.Null(PdmValues.SetRetry(v, null));
        Assert.All(v.Boards, q => Assert.Equal(0, q.Device.CustomPdm!.MasterRetryInput));
        Assert.Equal(32, Free(v, "A1", PdmResKind.CanInput));
    }

    [Fact]
    public void CanOutputSendsAValueAndTheOpenLoadFlagsAsOneFrame()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var cur = b.VarMap.First(e => ReferenceEquals(e.Owner, b.Outputs[0]) && e.PropertyName == "Current").VariableIndex;
        Assert.Null(PdmValues.AddCanOut(v, new PdmCanOutSpec("B", 0x6A0, 16, 16, cur, Factor: 0.1, IntervalMs: 100), out var i));
        Assert.True(b.CanOutputs[i] is { Enabled: true, Id: 0x6A0, StartBit: 16, BitLength: 16, Factor: 0.1, Interval: 100 });
        Assert.Equal("CAN out: output 17 current on 0x6A0 start bit 16, 16 bits, raw = (value - 0) / 0.1, every 100 ms", Words(v, PdmResKind.CanOutput, "B", i));
        Assert.Contains("overlap", PdmValues.AddCanOut(v, new PdmCanOutSpec("B", 0x6A0, 20, 8, cur), out _));
        Assert.Contains("PDM board's own ID block", PdmValues.AddCanOut(v, new PdmCanOutSpec("B", 0x590, 0, 8, cur), out _));
        Assert.Null(PdmValues.AddOpenLoadFrame(v, "B", 0x6A0, 100));            // bits 0-7 of the same frame
        var ol = b.CanOutputs.Where(c => c.Enabled && c.BitLength == 1).ToList();
        Assert.Equal(Enumerable.Range(0, 8), ol.Select(c => c.StartBit));
        Assert.Equal("CAN out: output 17 undercurrent on 0x6A0 start bit 0, 1 bits, every 100 ms", Words(v, PdmResKind.CanOutput, "B", b.CanOutputs.IndexOf(ol[0])));
        Assert.Equal(32 - 9, Free(v, "B", PdmResKind.CanOutput));
        Assert.Null(PdmValues.Remove(v, new PdmRes("B", PdmResKind.CanOutput, i)));
        Assert.True(PdmModel.Fresh(b.CanOutputs[i]));
        NoConflicts(v);
    }
}
