using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// One-PDM editor phase 1: the /pdm trigger editor (PdmTriggers) -> the stock functions it writes on the OUTPUT's board,
// read back in words, freed when replaced, refused cleanly when a board is full. Live proof: PdmTriggersLiveSimTests.
// Numbers: outputs A1 1-8, A2 9-16 (10 = fans), B 17-24; digital inputs A1 1-7, A2 8-14, B 15-24.
public class PdmTriggersTests
{
    internal static PdmView NewPdm() => PdmLinkedTests.NewPdm();
    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;
    private static int Di(FwDevice d, int i) => PdmFactoryDefaults.VarOf(d, d.DigitalInputs[i]);
    private static PdmTrigger Trig(PdmView v, int output) => PdmTriggers.Of(PdmModel.Build(v), output);
    private static string Words(PdmView v, int output) => Trig(v, output).Words;
    private static int Free(PdmView v, string role, PdmResKind k) => PdmModel.Build(v).FreeOf(role, k).Count;
    internal static List<string> Raw(PdmView v) => v.Boards.SelectMany(b => PdmLinksTests.Raw(b.Device)).ToList();

    private static readonly PdmTerm In15 = PdmTerm.In(15), In16 = PdmTerm.In(16), In17 = PdmTerm.In(17);

    [Fact]
    public void NewPdmHasNoTriggersAndTheFanOutputIsTheFanLogic()
    {
        var v = NewPdm();
        var m = PdmModel.Build(v);
        Assert.All(m.Triggers.Where(t => t.Out.Number != 10), t => Assert.Equal(PdmTriggerKind.None, t.Kind));
        Assert.Equal(PdmTriggerKind.Hand, PdmTriggers.Of(m, 10).Kind);
        Assert.Contains("fan logic", PdmTriggers.Of(m, 10).Words);
        Assert.Contains("runs the fans", PdmTriggers.Set(v, 10, PdmTriggerSpec.Input(In15)));
    }

    [Fact]
    public void SingleInputSameBoardIsTheInputItself()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(In15)));
        Assert.Equal(Di(b, 0), b.Outputs[0].Input);
        Assert.Equal("IN15", Words(v, 17));
        Assert.Empty(Trig(v, 17).Made);
        Assert.Empty(PdmTriggers.Cost(v, "B", PdmTriggerSpec.Input(In15)));
        Assert.Equal(14, Free(v, "B", PdmResKind.VirtualInput));
    }

    [Fact]
    public void NotInputIsOneVirtualInputNotAAndAlwaysOn()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(PdmTerm.In(15, true))));
        var vi = b.VirtualInputs[0];
        Assert.True(vi is { Enabled: true, Not0: true, Cond0: Conditional.And, Not1: false, Var2: 0 });
        Assert.Equal((Di(b, 0), PdmTriggers.AlwaysOnVar), (vi.Var0, vi.Var1));
        Assert.Equal(PdmFactoryDefaults.VarOf(b, vi), b.Outputs[0].Input);
        Assert.Equal("NOT IN15", Words(v, 17));
        Assert.Equal(13, Free(v, "B", PdmResKind.VirtualInput));
    }

    [Fact]
    public void OtherBoardInputIsOneLinkSlotOnTheOutputBoard()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var a1Raw = PdmLinksTests.Raw(Dev(v, "A1"));
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(PdmTerm.In(3))));
        var c = b.CanInputs[0];
        Assert.True(c is { Enabled: true, TimeoutEnabled: true, Timeout: 1000, StartBit: 2, BitLength: 1, Operator: Operator.Equal, Operand: 1.0 });
        Assert.Equal(0x500 + 0x27, c.Id);
        Assert.Equal(PdmFactoryDefaults.CanInState(b, 0), b.Outputs[0].Input);
        Assert.Equal(a1Raw, PdmLinksTests.Raw(Dev(v, "A1"))); // nothing set on the input board
        Assert.Equal("IN3", Words(v, 17));
        var link = Assert.Single(PdmLinks.Links(v)); // the same as the Links panel's 'off' link
        Assert.Equal(PdmLinkLoss.Off, link.Loss);
        Assert.Null(PdmTriggers.Conflict(v, 17));    // the editor's own: edit without asking
    }

    [Theory]
    [InlineData(PdmLogicOp.And, 2, Conditional.And, Conditional.And, "IN15 AND NOT IN16")]
    [InlineData(PdmLogicOp.Or, 3, Conditional.Or, Conditional.Or, "IN15 OR NOT IN16 OR IN17")]
    [InlineData(PdmLogicOp.Nor, 2, Conditional.Nor, Conditional.And, "NOT (IN15 OR NOT IN16)")]
    [InlineData(PdmLogicOp.Nor, 3, Conditional.Or, Conditional.Nor, "NOT (IN15 OR NOT IN16 OR IN17)")]
    public void LogicIsOneVirtualInput(PdmLogicOp op, int n, Conditional c0, Conditional c1, string words)
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var terms = new[] { In15, PdmTerm.In(16, true), In17 }.Take(n).ToArray();
        var spec = PdmTriggerSpec.Logic(op, terms);
        Assert.Null(PdmTriggers.Set(v, 18, spec));
        var vi = b.VirtualInputs[0];
        Assert.Equal((c0, Di(b, 0), Di(b, 1), false, true), (vi.Cond0, vi.Var0, vi.Var1, vi.Not0, vi.Not1));
        if (n == 3) Assert.Equal((c1, Di(b, 2)), (vi.Cond1, vi.Var2)); else Assert.Equal(0, vi.Var2);
        Assert.Equal(words, Words(v, 18));
        Assert.Equal(spec, Trig(v, 18).Spec);
    }

    [Fact]
    public void OtherBoardTermComesInThroughTheLinkMachineryAndIsNotRemovedAsUnused()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var spec = PdmTriggerSpec.Logic(PdmLogicOp.And, In15, PdmTerm.In(9));   // A2 IN2
        Assert.Equal("1 CAN input, 1 virtual input", PdmTriggers.CostText(PdmTriggers.Cost(v, "B", spec)));
        Assert.Null(PdmTriggers.Set(v, 18, spec));
        Assert.Equal((0x540 + 0x27, 1), (b.CanInputs[0].Id, b.CanInputs[0].StartBit));
        Assert.Equal(PdmFactoryDefaults.CanInState(b, 0), b.VirtualInputs[0].Var1);
        Assert.Equal("IN15 AND IN9", Words(v, 18));
        Assert.Equal(0, PdmLinks.RemoveUnused(v));
        Assert.Equal(spec, Trig(v, 18).Spec);
        var use = PdmLinks.Slots(v).Single(s => s.Board == "B").CanInputs[0];
        Assert.Contains("used by a trigger", use.UsedBy);
        Assert.False(use.Unused);
        // the base-ID move follows it like a link slot
        PdmLinked.FollowBaseId(v, "A2", 0x600);
        Assert.Equal(0x600 + 0x27, b.CanInputs[0].Id);
    }

    [Theory]
    [InlineData(true, 14.0, 13.0, Operator.GreaterThanOrEqual, Operator.LessThanOrEqual, "B battery voltage (V) on at 14 or more, off at 13 or less")]
    [InlineData(false, 11.5, 12.5, Operator.LessThanOrEqual, Operator.GreaterThanOrEqual, "B battery voltage (V) on at 11.5 or less, off at 12.5 or more")]
    public void ThresholdIsTwoConditionsAndALatch(bool above, double on, double off, Operator opOn, Operator opOff, string words)
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var batt = b.VarMap.Single(e => e.Owner == null && e.GetName() == "Battery Voltage").VariableIndex;
        var spec = PdmTriggerSpec.Level(new PdmThreshold(batt, above, on, off));
        Assert.Null(PdmTriggers.Set(v, 19, spec));
        var (c1, c2, vi) = (b.Conditions[0], b.Conditions[1], b.VirtualInputs[0]);
        Assert.Equal((true, batt, opOn, on), (c1.Enabled, c1.Input, c1.Operator, c1.Arg));
        Assert.Equal((true, batt, opOff, off), (c2.Enabled, c2.Input, c2.Operator, c2.Arg));
        var self = PdmFactoryDefaults.VarOf(b, vi);
        Assert.Equal((PdmFactoryDefaults.VarOf(b, c1), Conditional.Or, self, Conditional.And, true, PdmFactoryDefaults.VarOf(b, c2)),
            (vi.Var0, vi.Cond0, vi.Var1, vi.Cond1, vi.Not2, vi.Var2));
        Assert.Equal(self, b.Outputs[2].Input);
        Assert.Equal(words, Words(v, 19));
        Assert.Equal(spec, Trig(v, 19).Spec);
        Assert.Contains(PdmTriggers.ValueChoices(PdmModel.Build(v), "B"), c => c.Var == batt);
        Assert.Contains("Off must be below on", PdmTriggers.Set(v, 20, PdmTriggerSpec.Level(new PdmThreshold(batt, true, 13, 14))));
        Assert.Contains("Off must be above on", PdmTriggers.Set(v, 20, PdmTriggerSpec.Level(new PdmThreshold(batt, false, 13, 12))));
    }

    [Fact]
    public void AnalogVoltageIsAThresholdValue()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var mv = PdmFactoryDefaults.VarOf(b, b.AnalogInputs[0]) + 1; // Value, then Millivolts
        Assert.Equal("Millivolts", b.VarMap.Single(e => e.VariableIndex == mv).PropertyName);
        Assert.Null(PdmTriggers.Set(v, 19, PdmTriggerSpec.Level(new PdmThreshold(mv, true, 3000, 2000))));
        Assert.Equal("IN27 voltage (mV) on at 3000 or more, off at 2000 or less", Words(v, 19));
    }

    [Theory]
    [InlineData(PdmTimerKind.OnDelay, 2000, TimerMode.OnDelay, "IN15 AND IN16, on-delay 2 s")]
    [InlineData(PdmTimerKind.OffDelay, 1500, TimerMode.OffDelay, "IN15 AND IN16, off-delay 1.5 s")]
    [InlineData(PdmTimerKind.Pulse, 300, TimerMode.PulseOneShot, "IN15 AND IN16, pulse 300 ms")]
    public void TimerWrapsTheTrigger(PdmTimerKind k, int ms, TimerMode mode, string words)
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var spec = PdmTriggerSpec.Logic(PdmLogicOp.And, In15, In16).WithTimer(k, ms);
        Assert.Null(PdmTriggers.Set(v, 20, spec));
        var t = b.Timers[0];
        Assert.Equal((true, PdmFactoryDefaults.VarOf(b, b.VirtualInputs[0]), 0, mode, ms), (t.Enabled, t.Input, t.ResetInput, t.Mode, t.Time));
        Assert.Equal(PdmFactoryDefaults.VarOf(b, t), b.Outputs[3].Input);
        Assert.Equal(words, Words(v, 20));
        Assert.Equal(spec, Trig(v, 20).Spec);
    }

    [Fact]
    public void FlasherWrapsTheTimer()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var spec = PdmTriggerSpec.Input(In15).WithTimer(PdmTimerKind.OffDelay, 3000).WithFlash(350, 350);
        Assert.Equal("1 timer, 1 flasher", PdmTriggers.CostText(PdmTriggers.Cost(v, "B", spec)));
        Assert.Null(PdmTriggers.Set(v, 21, spec));
        var (t, f) = (b.Timers[0], b.Flashers[0]);
        Assert.Equal(Di(b, 0), t.Input);
        Assert.Equal((true, PdmFactoryDefaults.VarOf(b, t), 350, 350, false), (f.Enabled, f.Input, f.OnTime, f.OffTime, f.Single));
        Assert.Equal(PdmFactoryDefaults.VarOf(b, f), b.Outputs[4].Input);
        Assert.Equal("IN15, off-delay 3 s, flashing 350 / 350 ms", Words(v, 21));
        Assert.Equal(spec, Trig(v, 21).Spec);
        Assert.Equal(2, Trig(v, 21).Made.Count); // timer + flasher (no virtual input for a plain input)
    }

    [Fact]
    public void EditingItsOwnTriggerAsksNothingAndFreesTheOldParts()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var fresh = Raw(v);
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Level(new PdmThreshold(PdmFactoryDefaults.VarOf(b, b.AnalogInputs[0]) + 1, true, 3000, 2000))
            .WithTimer(PdmTimerKind.OnDelay, 2000).WithFlash(200, 200)));
        Assert.Null(PdmTriggers.Conflict(v, 18));
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Logic(PdmLogicOp.Or, In15, PdmTerm.In(2))));
        Assert.Equal("IN15 OR IN2", Words(v, 18));
        Assert.Equal(28, Free(v, "B", PdmResKind.Condition));
        Assert.Equal(8, Free(v, "B", PdmResKind.Timer));
        Assert.Equal(4, Free(v, "B", PdmResKind.Flasher));
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.None));
        Assert.Equal(fresh, Raw(v)); // every part back to fresh-board values (the other-board slot too)
    }

    [Fact]
    public void ReplacingALinkAsksAndOverwriteRemovesTheLink()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 1, 17, PdmLinkLoss.On));
        var before = Raw(v);
        var c = PdmTriggers.Conflict(v, 17);
        Assert.Equal("Output 17 (B OUT1) is already assigned to IN1 (link: on 1 s after the message stops; off until the first frame).", c);
        Assert.Equal(c, PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(In15)));
        Assert.Equal(before, Raw(v)); // Cancel = nothing changed
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(In15), overwrite: true));
        Assert.DoesNotContain(PdmLinks.Links(v), l => l.CrossBoard);
        Assert.Empty(PdmLinks.Shared(v));
        Assert.Equal("IN15", Words(v, 17));
    }

    [Fact]
    public void ReplacingAHandMadeTriggerAsksAndOnlyUnhooksIt()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var vi = b.VirtualInputs[5]; // set by hand: mixed operators (not an editor shape)
        (vi.Enabled, vi.Var0, vi.Cond0, vi.Var1, vi.Cond1, vi.Var2) = (true, Di(b, 0), Conditional.Or, Di(b, 1), Conditional.And, Di(b, 2));
        b.Outputs[1].Input = PdmFactoryDefaults.VarOf(b, vi);
        var t = Trig(v, 18);
        Assert.Equal(PdmTriggerKind.Hand, t.Kind);
        Assert.Equal("B virtual input 6 (set by hand)", t.Words);
        Assert.Equal("Output 18 (B OUT2) is already assigned to B virtual input 6 (set by hand).", PdmTriggers.Conflict(v, 18));
        var viRaw = vi.Params.Select(p => p.GetValue()).ToList();
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Input(In15), overwrite: true));
        Assert.Equal(viRaw, vi.Params.Select(p => p.GetValue()).ToList()); // never changed
        Assert.Equal(Di(b, 0), b.Outputs[1].Input);
    }

    [Fact]
    public void ABoardFullIsRefusedCleanly()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        foreach (var k in PdmModel.Build(v).FreeOf("B", PdmResKind.VirtualInput).Skip(1)) b.VirtualInputs[k].Enabled = true; // set by hand
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Logic(PdmLogicOp.And, In15, In16)));   // the last free one
        var before = Raw(v);
        var why = PdmTriggers.Set(v, 18, PdmTriggerSpec.Logic(PdmLogicOp.Or, In15, PdmTerm.In(3)));
        Assert.Equal("B is full: this trigger needs 1 CAN input, 1 virtual input; B has 0 virtual inputs free (16 of 16 in use: " +
                     "1 by triggers, 2 reserved, 13 set by hand). Nothing changed. Free some on this board (other triggers, links, Advanced) or pick a simpler trigger.", why);
        Assert.Equal(before, Raw(v));
        // a plain input needs nothing and still works; replacing its own trigger reuses its own parts
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Input(In16)));
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Logic(PdmLogicOp.Or, In15, In17)));
        // timers: 8 per board
        for (var o = 0; o < 8; o++) b.Timers[o].Enabled = o < 8;
        Assert.StartsWith("B is full: this trigger needs 1 timer; B has 0 timers free", PdmTriggers.Set(v, 19, PdmTriggerSpec.Input(In15).WithTimer(PdmTimerKind.OnDelay, 500)));
    }

    [Fact]
    public void PairedOutputsAndBadSpecsAreRefused()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        b.Outputs[5].PrimaryOutput = 4;
        Assert.Contains("is paired", PdmTriggers.Set(v, 22, PdmTriggerSpec.Input(In15)));
        Assert.Contains("2 or 3 terms", PdmTriggers.Set(v, 17, PdmTriggerSpec.Logic(PdmLogicOp.And, In15)));
        Assert.Contains("different signal", PdmTriggers.Set(v, 17, PdmTriggerSpec.Logic(PdmLogicOp.And, In15, In15)));
        Assert.Contains("not a digital input", PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(PdmTerm.In(30))));
        Assert.Contains("1 to 600000 ms", PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(In15).WithTimer(PdmTimerKind.OnDelay, 0)));
        Assert.Contains("1 to 5000 ms", PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(In15).WithFlash(6000, 100)));
        var batt = b.VarMap.Single(e => e.Owner == null && e.GetName() == "Battery Voltage").VariableIndex;
        Assert.Contains("on / off signal", PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(PdmTerm.Of(batt)))); // a number is not a term
        b.Outputs[5].PrimaryOutput = -1;
        Assert.Equal(Raw(NewPdm()), Raw(v)); // nothing written by a refused Set
    }

    [Fact]
    public void TheLinksPanelOverwritingATriggerFreesItsParts()
    {
        var v = NewPdm();
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Logic(PdmLogicOp.And, In15, In16).WithTimer(PdmTimerKind.OnDelay, 2000)));
        Assert.StartsWith("Output 17 (B OUT1) is already assigned", PdmLinks.Conflict(v, 17));
        Assert.Null(PdmLinks.Add(v, 3, 17, overwrite: true));
        Assert.Equal(14, Free(v, "B", PdmResKind.VirtualInput)); // the 'off' link needs no virtual input; the trigger's was freed
        Assert.Equal(8, Free(v, "B", PdmResKind.Timer));
        Assert.Equal("IN3", Words(v, 17));
    }

    [Fact]
    public void TriggersSurviveAFreshProjectReadingTheSameParams()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var batt = b.VarMap.Single(e => e.Owner == null && e.GetName() == "Battery Voltage").VariableIndex;
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Logic(PdmLogicOp.And, In15, PdmTerm.In(2))));
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Level(new PdmThreshold(batt, true, 14.2, 13.4)).WithTimer(PdmTimerKind.OnDelay, 2000)));
        Assert.Null(PdmTriggers.Set(v, 19, PdmTriggerSpec.Input(In16).WithFlash(350, 350)));
        // a second PC with stock names (only params travel to the boards and back)
        var v2 = NewPdm();
        foreach (var (d1, d2) in v.Boards.Zip(v2.Boards))
            for (var i = 0; i < d1.Device.Params.Count; i++) d2.Device.Params[i].SetValue(d1.Device.Params[i].GetValue());
        foreach (var o in new[] { 17, 18, 19 }) Assert.Equal(Trig(v, o).Spec, Trig(v2, o).Spec);
        Assert.Equal(["IN15 AND IN2", "B battery voltage (V) on at 14.2 or more, off at 13.4 or less, on-delay 2 s", "IN16, flashing 350 / 350 ms"],
            new[] { 17, 18, 19 }.Select(o => Words(v2, o)));
    }
}
