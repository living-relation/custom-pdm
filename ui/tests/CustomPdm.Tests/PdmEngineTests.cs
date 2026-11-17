using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// One-PDM editor phase 1: the conflict engine (PdmEngine / PdmModel): claims, every problem kind, the Advanced-screen
// edit check ("X is already assigned to Y. Overwrite?", Cancel = no change) and the critical settings lock (PdmCritical).
public class PdmEngineTests
{
    private static PdmView NewPdm() => PdmLinkedTests.NewPdm();
    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;
    private static int Di(FwDevice d, int i) => PdmFactoryDefaults.VarOf(d, d.DigitalInputs[i]);
    private static IReadOnlyList<PdmProblem> Problems(PdmView v) => PdmModel.Build(v).Problems;
    private static IEnumerable<string> Of(PdmView v, PdmProblemKind k) => Problems(v).Where(p => p.Kind == k).Select(p => p.Text);
    private static readonly PdmTerm In15 = PdmTerm.In(15), In16 = PdmTerm.In(16);

    // an enabled B pair: OUT1 IN15 AND IN16, OUT2 the same virtual input (set by hand)
    private static PdmView TwoOnOneTrigger()
    {
        var v = NewPdm();
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Logic(PdmLogicOp.And, In15, In16)));
        var b = Dev(v, "B");
        b.Outputs[1].Input = b.Outputs[0].Input;
        return v;
    }

    [Fact]
    public void NewPdmHasNoProblemsAndTheReservedSlotsAreClaimed()
    {
        var v = NewPdm();
        var m = PdmModel.Build(v);
        Assert.Empty(m.Problems);
        var a2 = m.Use("A2");
        Assert.Equal((32, 4, 28), (a2.Of(PdmResKind.CanInput).Total, a2.Of(PdmResKind.CanInput).Reserved, a2.Of(PdmResKind.CanInput).Free));
        Assert.Equal((16, 5, 11), (a2.Of(PdmResKind.VirtualInput).Total, a2.Of(PdmResKind.VirtualInput).Reserved, a2.Of(PdmResKind.VirtualInput).Free));
        Assert.Equal((32, 6, 26), (a2.Of(PdmResKind.Condition).Total, a2.Of(PdmResKind.Condition).Reserved, a2.Of(PdmResKind.Condition).Free));
        var b = m.Use("B");
        Assert.Equal((16, 2, 14), (b.Of(PdmResKind.VirtualInput).Total, b.Of(PdmResKind.VirtualInput).Reserved, b.Of(PdmResKind.VirtualInput).Free));
        Assert.Equal((8, 8), (b.Of(PdmResKind.Timer).Total, b.Of(PdmResKind.Timer).Free));
        Assert.Equal((4, 4, 4), (b.Of(PdmResKind.Flasher).Free, b.Of(PdmResKind.Counter).Free, b.Of(PdmResKind.Counter).Total));
        Assert.Equal(PdmModel.FanText, m.ClaimOf(new PdmRes("A2", PdmResKind.CanInput, 24)).Text);
        Assert.Equal(PdmModel.ShedText, m.ClaimOf(new PdmRes("A1", PdmResKind.VirtualInput, 14)).Text);
        Assert.StartsWith("B: CAN inputs 0 of 32 used, 32 free; virtual inputs 2 of 16 used, 14 free", b.Summary);
    }

    [Fact]
    public void TriggersAndLinksAreClaimedByTheirOwner()
    {
        var v = NewPdm();
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Logic(PdmLogicOp.And, In15, PdmTerm.In(2)).WithTimer(PdmTimerKind.OnDelay, 2000)));
        Assert.Null(PdmLinks.Add(v, 1, 17, PdmLinkLoss.On));
        var m = PdmModel.Build(v);
        var t = m.ClaimOf(new PdmRes("B", PdmResKind.Timer, 0));
        Assert.Equal((PdmClaimKind.Trigger, "output 18's trigger (IN15 AND IN2, on-delay 2 s)", 18), (t.Kind, t.Text, t.Output));
        Assert.Equal(PdmClaimKind.Trigger, m.ClaimOf(new PdmRes("B", PdmResKind.CanInput, 0)).Kind); // the term's link slot
        var linkSlot = PdmLinks.Links(v).Single(l => l.Out.Number == 17).Slot!.Value;
        Assert.Equal("the link IN1 -> output 17", m.ClaimOf(new PdmRes("B", PdmResKind.CanInput, linkSlot)).Text);
        Assert.Equal(PdmClaimKind.Shared, m.ClaimOf(new PdmRes("B", PdmResKind.VirtualInput, PdmLinks.Shared(v).Single().Lost)).Kind);
        Assert.DoesNotContain(m.Problems, p => p.Kind != PdmProblemKind.MissingRef); // only "not enabled" (outputs / inputs left off)
        var use = m.Use("B");
        Assert.Equal((1, 2), (use.Of(PdmResKind.VirtualInput).Triggers, use.Of(PdmResKind.VirtualInput).Links)); // link VI + shared LOST
    }

    [Fact]
    public void AnOutputDrivenTwiceIsReported()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        b.Outputs[1].PrimaryOutput = 0;
        Assert.Empty(Of(v, PdmProblemKind.OutputDrivenTwice));
        b.Outputs[1].Input = Di(b, 3);
        Assert.Equal("Output 18 (B OUT2) follows B OUT1 (paired) and also has its own trigger (IN18): the pairing wins, the trigger does nothing.",
            Assert.Single(Of(v, PdmProblemKind.OutputDrivenTwice)));
    }

    [Fact]
    public void AResourceUsedByTwoOwnersIsReported()
    {
        var v = TwoOnOneTrigger();
        var p = Of(v, PdmProblemKind.TwoOwners).ToList();
        Assert.Contains("B virtual input 1 is part of output 17's trigger (IN15 AND IN16) and of output 18's trigger (IN15 AND IN16): changing one changes the other.", p);
        // and its trigger is no longer the editor's own: replacing it asks
        Assert.EndsWith("It shares parts with another output's trigger or with hand-made settings.", PdmTriggers.Conflict(v, 17));

        // a hand-made function reading a trigger's part
        var v2 = NewPdm();
        Assert.Null(PdmTriggers.Set(v2, 17, PdmTriggerSpec.Logic(PdmLogicOp.Or, In15, In16)));
        var b = Dev(v2, "B");
        b.Flashers[2].Input = b.Outputs[0].Input;
        Assert.Equal("B virtual input 1 belongs to output 17's trigger (IN15 OR IN16), but B flasher 3 also reads it (input): changing or removing that one changes this too.",
            Assert.Single(Of(v2, PdmProblemKind.TwoOwners)));
        // replacing that trigger leaves the shared part alone
        Assert.Null(PdmTriggers.Set(v2, 17, PdmTriggerSpec.Input(In15), overwrite: true));
        Assert.True(b.VirtualInputs[0].Enabled);
    }

    [Fact]
    public void AReferenceToADisabledOrMissingResourceIsReported()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Logic(PdmLogicOp.And, In15, PdmTerm.In(2))));
        Assert.Equal(["B virtual input 1 (term 1) uses IN15 (B IN1), which is not enabled.",
                      "B virtual input 1 uses IN2 of A1 (through B CAN input 1), which is not enabled."], Of(v, PdmProblemKind.MissingRef));
        b.DigitalInputs[0].Enabled = true;
        Dev(v, "A1").DigitalInputs[1].Enabled = true;
        Assert.Empty(Of(v, PdmProblemKind.MissingRef));
        b.Outputs[0].Enabled = true; // an enabled output reading an enabled virtual input: fine
        Assert.Empty(Of(v, PdmProblemKind.MissingRef));
        b.Outputs[2].Enabled = true;
        b.Outputs[2].Input = 9999;
        Assert.Contains("Output 19 (B OUT3) (trigger) uses variable 9999, which this board does not have.", Of(v, PdmProblemKind.MissingRef));
    }

    [Fact]
    public void ALinkSlotChangedByHandIsReported()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 1, 17));
        Assert.Empty(Of(v, PdmProblemKind.LinkSlotByHand));
        Dev(v, "B").CanInputs[0].BitLength = 8;
        Assert.Equal("B CAN input 1 listens to A1's link message (0x527) but its settings were changed by hand: links and triggers no longer recognise it.",
            Assert.Single(Of(v, PdmProblemKind.LinkSlotByHand)));
    }

    [Fact]
    public void AReservedSlotTouchedIsReported()
    {
        var v = NewPdm();
        var a2 = Dev(v, "A2");
        var a1 = Dev(v, "A1");
        // allowed: fan thresholds, enabling the load-shed example and its thresholds
        a2.Conditions[PdmFactoryDefaults.FanCond0(a2)].Arg = 50;
        a1.Conditions[PdmFactoryDefaults.ShedCond0(a1)].Enabled = true;
        a1.Conditions[PdmFactoryDefaults.ShedCond0(a1)].Arg = 72;
        a1.VirtualInputs[PdmFactoryDefaults.ShedVirt0(a1)].Enabled = true;
        Assert.Empty(Of(v, PdmProblemKind.ReservedTouched));
        a2.VirtualInputs[PdmFactoryDefaults.FanVirt0(a2) + 2].Not2 = false;
        a1.Conditions[PdmFactoryDefaults.ShedCond0(a1) + 1].Operator = Operator.GreaterThan;
        a2.Outputs[1].Input = Di(a2, 0);
        var p = Of(v, PdmProblemKind.ReservedTouched).ToList();
        Assert.Equal(3, p.Count);
        Assert.Contains("A2 virtual inputs 12-14 (fan logic, reserved) were changed by hand.", p);
        Assert.Contains("Output 10 (A2 OUT2, the fans) is not driven by the fan logic.", p);
        Assert.Contains(p, x => x.StartsWith("A1 load-shed example (conditions 29-32, virtual inputs 15-16, reserved) was rewired by hand"));
        a2.CanInputs[PdmFactoryDefaults.FanCanIn0].Enabled = false;
        Assert.Contains(PdmLinked.FanLayoutProblem(a2), Of(v, PdmProblemKind.ReservedTouched));
    }

    // ---------------- the Advanced-screen edit check ----------------

    [Fact]
    public void AnEditOfATriggerPartAsksOverwriteAndCancelChangesNothing()
    {
        var v = NewPdm();
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Logic(PdmLogicOp.And, In15, In16).WithTimer(PdmTimerKind.OnDelay, 2000)));
        var b = Dev(v, "B");
        var before = PdmSnapshot.Take(v);
        var raw = PdmTriggersTests.Raw(v);
        b.Timers[0].Time = 5000; // the Advanced timers grid
        var c = PdmEngine.CheckEdit(v, before);
        Assert.Equal("B timer 1 is already assigned to output 18's trigger (IN15 AND IN16, on-delay 2 s).", Assert.Single(c.Assigned));
        Assert.Empty(c.Critical);
        Assert.Equal(5000, b.Timers[0].Time); // the model holds the edit until the answer
        before.Restore();                     // Cancel
        Assert.Equal(raw, PdmTriggersTests.Raw(v));
        Assert.True(PdmEngine.CheckEdit(v, before).Clean);
    }

    [Fact]
    public void ReplacingAnOutputTriggerOnTheAdvancedScreenAsks()
    {
        var v = NewPdm();
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Input(In15)));
        var b = Dev(v, "B");
        var before = PdmSnapshot.Take(v);
        b.Outputs[1].Input = Di(b, 5);
        Assert.Equal("Output 18 (B OUT2) is already assigned to its trigger (IN15).", Assert.Single(PdmEngine.CheckEdit(v, before).Assigned));
        // an output with no trigger is free to set
        var before2 = PdmSnapshot.Take(v);
        b.Outputs[2].Input = Di(b, 5);
        Assert.True(PdmEngine.CheckEdit(v, before2).Clean);
    }

    [Fact]
    public void EditsOfLinksSharedAndReservedSlotsAsk()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 1, 17, PdmLinkLoss.On));
        var b = Dev(v, "B");
        var a2 = Dev(v, "A2");
        var l = PdmLinks.Links(v).Single(x => x.Out.Number == 17);
        var sh = PdmLinks.Shared(v).Single();
        var problems = Problems(v);
        var before = PdmSnapshot.Take(v);
        b.CanInputs[l.Slot!.Value].Timeout = 2000;
        b.CanInputs[sh.Alive].Timeout = 500;
        a2.VirtualInputs[PdmFactoryDefaults.FanVirt0(a2)].Not0 = true;
        var c = PdmEngine.CheckEdit(v, before);
        Assert.Contains($"B CAN input {l.Slot + 1} is already assigned to the link IN1 -> output 17.", c.Assigned);
        Assert.Contains($"B CAN input {sh.Alive + 1} is already assigned to the shared ALIVE / SEEN / LOST of the links from A1.", c.Assigned);
        Assert.Contains("A2 virtual input 12 is already assigned to the fan logic (A2 OUT2).", c.Assigned);
        Assert.Contains(c.NewProblems, p => p.Kind == PdmProblemKind.ReservedTouched);
        before.Restore();
        Assert.Equal(problems, Problems(v));
    }

    [Fact]
    public void EditsOfFreeOrHandMadeFunctionsPassUnlessTheyMakeANewProblem()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var before = PdmSnapshot.Take(v);
        (b.Counters[0].Enabled, b.Counters[0].IncInput) = (true, Di(b, 4));
        b.DigitalInputs[4].Enabled = true;
        b.Outputs[0].CurrentLimit = 5;
        Assert.True(PdmEngine.CheckEdit(v, before).Clean);
        // the counter reads IN19, which is off now: a new problem
        b.DigitalInputs[4].Enabled = false;
        var c = PdmEngine.CheckEdit(v, before);
        Assert.Empty(c.Assigned);
        Assert.Contains(c.NewProblems, p => p.Text == "B counter 1 (count-up input) uses IN19 (B IN5), which is not enabled.");
    }

    [Fact]
    public void CriticalSettingsAreRefusedOnTheAdvancedScreen()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var before = PdmSnapshot.Take(v);
        b.BaseId = 0x600;
        b.BitRate = CanBitRate.BitRate500K;
        b.CustomPdm!.TempCrit = 90;
        b.CustomPdm.CritExemptMask = 3;
        b.CustomPdm.TempWarn = 50; // not critical
        var c = PdmEngine.CheckEdit(v, before);
        Assert.Equal(4, c.Critical.Count);
        Assert.Contains(c.Critical, x => x.EndsWith("device.baseId 0x580 -> 0x600"));
        Assert.Equal(["device.baseId", "device.canSpeed", "customPdm.tempCrit", "customPdm.critExemptMask"], PdmEngine.CriticalParams);
    }

    // ---------------- critical settings lock on /pdm (p1 / p3) ----------------

    [Fact]
    public void CriticalItemsShowTheCurrentValues()
    {
        var v = NewPdm();
        var items = PdmCritical.Items(v);
        Assert.Equal(["0x500", "0x540", "0x580", "1000K", "80 C", "10"], items.Select(i => i.Current));
        Dev(v, "B").BitRate = CanBitRate.BitRate500K;
        Assert.Equal("differs: A1 1000K, A2 1000K, B 500K", PdmCritical.Items(v).Single(i => i.Kind == PdmCriticalKind.BitRate).Current);
    }

    [Fact]
    public void CriticalChangesNeedAValidValueAndApplyToAllBoards()
    {
        var v = NewPdm();
        Assert.Equal("Type one of 1000K, 500K, 250K, 125K.", PdmCritical.Problem(v, PdmCriticalKind.BitRate, "", "333"));
        Assert.Null(PdmCritical.Apply(v, PdmCriticalKind.BitRate, "500k"));
        Assert.All(v.Boards, b => Assert.Equal(CanBitRate.BitRate500K, b.Device.BitRate));
        Assert.Equal("Warn must be below critical.", PdmCritical.Apply(v, PdmCriticalKind.CritTemp, "50"));
        Assert.Null(PdmCritical.Apply(v, PdmCriticalKind.CritTemp, "85"));
        Assert.All(v.Boards, b => Assert.Equal(85, b.Device.CustomPdm!.TempCrit));
        Assert.Null(PdmCritical.Apply(v, PdmCriticalKind.KeptOn, "10, 17, 24"));
        Assert.Equal([0, 1 << 1, 1 | 1 << 7], v.Boards.Select(b => b.Device.CustomPdm!.CritExemptMask));
        Assert.Equal([10, 17, 24], PdmCritical.KeptOn(v));
        Assert.Contains("Output 25 is not in this PDM", PdmCritical.Apply(v, PdmCriticalKind.KeptOn, "25"));
        Assert.Null(PdmCritical.Apply(v, PdmCriticalKind.KeptOn, "none"));
        Assert.Empty(PdmCritical.KeptOn(v));
        Assert.Contains("overlap", PdmCritical.Problem(v, PdmCriticalKind.BaseId, "A2", "560"));
        Assert.Null(PdmCritical.Problem(v, PdmCriticalKind.BaseId, "A2", "0x5C0"));
        Assert.Equal("That is the base ID it has now.", PdmCritical.Problem(v, PdmCriticalKind.BaseId, "A2", "540"));
        Assert.NotNull(PdmCritical.Apply(v, PdmCriticalKind.BaseId, "600")); // base IDs move through PdmOpsService
    }

    [Fact]
    public void ResetGivesFreshBoardValues()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        (b.Timers[3].Enabled, b.Timers[3].Input, b.Timers[3].Time, b.Timers[3].Name) = (true, 7, 42, "x");
        PdmEngine.Reset(b.Timers[3]);
        Assert.Equal(PdmTriggersTests.Raw(NewPdm()), PdmTriggersTests.Raw(v));
        Assert.Equal("timer4", b.Timers[3].Name);
        Assert.True(PdmModel.Build(v).IsFree(new PdmRes("B", PdmResKind.Timer, 3)));
    }
}
