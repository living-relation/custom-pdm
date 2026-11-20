using domain.CustomPdm;
using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// One-PDM editor phase 2 (editor2): device presets, the per-output link-loss delay, ECU-driven outputs, PWM / fan
// curve, turn signals + hazards and the wiper, all through PdmEngine. Live proof: PdmEditor2LiveSimTests.
// Numbers: outputs A1 1-8, A2 9-16 (10 = fans), B 17-24; digital inputs A1 1-7, A2 8-14, B 15-24.
public class PdmEditor2Tests
{
    private static PdmView NewPdm() => PdmLinkedTests.NewPdm();
    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;
    private static PdmOutputRow Out(PdmView v, int n) => v.Outputs.Single(o => o.Number == n);
    private static int Di(FwDevice d, int i) => PdmFactoryDefaults.VarOf(d, d.DigitalInputs[i]);
    private static PdmModel M(PdmView v) => PdmModel.Build(v);
    private static string Words(PdmView v, int n) => PdmTriggers.Of(M(v), n).Words;
    private static int Free(PdmView v, string role, PdmResKind k) => M(v).FreeOf(role, k).Count;
    private static PdmProtection Pro(PdmView v, int n) => new(Out(v, n));
    // no conflict of any kind; "not enabled" inputs are expected here (the tests do not enable them)
    private static void NoConflicts(PdmView v) => Assert.Empty(M(v).Problems.Where(p => p.Kind != PdmProblemKind.MissingRef || !p.Text.EndsWith("which is not enabled.")));

    internal sealed record PdmProtection(PdmOutputRow O)
    {
        public OutputProtection P => O.Device.CustomPdm!.OutputProtection[O.BoardOutput - 1];
    }

    // ================================================================ presets

    [Theory]
    [InlineData(PdmDeviceKind.RadiatorFan, 17, 30.0, 100.0, 500, 100, true, 3, 2000, 0.0, PdmLinkLoss.On)]     // B OUT1 31 A: fan 30 A cap
    [InlineData(PdmDeviceKind.FuelPump, 19, 25.0, 100.0, 500, 100, false, 3, 1000, 1.0, PdmLinkLoss.Off)]      // 25 A x 4 = 100 A (cap)
    [InlineData(PdmDeviceKind.FuelPump, 21, 15.0, 60.0, 500, 100, false, 3, 1000, 1.0, PdmLinkLoss.Off)]       // B OUT5 15 A rating wins
    [InlineData(PdmDeviceKind.Lamp, 1, 7.5, 75.0, 100, 50, false, 5, 1000, 0.5, PdmLinkLoss.Hold)]            // A 7.5 A, 10 x
    [InlineData(PdmDeviceKind.LedLamp, 3, 5.0, 15.0, 100, 50, false, 5, 1000, 0.0, PdmLinkLoss.Hold)]
    [InlineData(PdmDeviceKind.Horn, 5, 7.5, 22.5, 200, 50, false, 3, 1000, 0.0, PdmLinkLoss.Off)]
    [InlineData(PdmDeviceKind.AcClutch, 22, 10.0, 20.0, 200, 50, false, 3, 1000, 1.0, PdmLinkLoss.Off)]
    [InlineData(PdmDeviceKind.Solenoid, 6, 5.0, 10.0, 100, 50, false, 3, 1000, 0.0, PdmLinkLoss.Off)]
    [InlineData(PdmDeviceKind.Motor, 23, 15.0, 60.0, 500, 100, false, 3, 2000, 0.0, PdmLinkLoss.Off)]
    [InlineData(PdmDeviceKind.Heater, 20, 31.0, 46.5, 500, 100, false, 3, 1000, 0.0, PdmLinkLoss.Off)]
    [InlineData(PdmDeviceKind.Module, 8, 5.0, 10.0, 100, 50, false, 5, 1000, 0.0, PdmLinkLoss.Hold)]
    [InlineData(PdmDeviceKind.Other, 2, 7.5, 50.0, 1000, 50, false, 3, 1000, 0.0, PdmLinkLoss.Off)]
    public void PresetFillsTheOutputFromItsRatingAndTheDevice(PdmDeviceKind k, int n, double limit, double inrush, int inrushMs, int tripMs,
        bool soft, int trips, int retryMs, double minA, PdmLinkLoss loss)
    {
        var v = NewPdm();
        Assert.Null(PdmPresets.Apply(v, n, k));
        var x = Out(v, n).Output;
        Assert.Equal((limit, inrush, inrushMs), (x.CurrentLimit, x.InrushCurrentLimit, x.InrushTime));
        Assert.Equal((ResetMode.Count, trips, retryMs), (x.ResetMode, x.ResetCountLimit, x.ResetTime));
        Assert.Equal(soft, x.SoftStartEnabled);
        if (soft) Assert.True(x is { PwmEnabled: true, VariableDutyCycle: false, FixedDutyCycle: 100, Frequency: 100, SoftStartRampTime: 1000 });
        Assert.Equal((tripMs, minA), (Pro(v, n).P.TripTime, Pro(v, n).P.MinCurrent));
        Assert.Equal(loss, PdmPresets.Of(k).Loss);
        Assert.Equal(k, PdmPresets.KindOf(v, Out(v, n)));
        Assert.Empty(PdmPresets.Changed(v, Out(v, n), k));
    }

    [Fact]
    public void NoPresetEverSetsALimitAboveTheRating()
    {
        var v = NewPdm();
        foreach (var o in v.Outputs.Where(o => !PdmTriggers.IsFanOutput(o)))
        foreach (var p in PdmPresets.All)
        {
            Assert.Null(PdmPresets.Apply(v, o.Number, p.Kind));
            Assert.True(o.Output.CurrentLimit <= o.RatingA, $"{p.Name} on {o.Number}");
            Assert.InRange(o.Output.InrushCurrentLimit, o.Output.CurrentLimit, PdmPresets.MaxInrushA);
            Assert.False(o.OverRating);
        }
    }

    [Fact]
    public void EditAfterPresetShowsWhatChangedAndTheLabelSurvivesInTheProjectOnly()
    {
        var v = NewPdm();
        Assert.Null(PdmPresets.Apply(v, 17, PdmDeviceKind.CondenserFan));
        var o = Out(v, 17);
        Assert.Equal(PdmDeviceKind.CondenserFan, PdmPresets.KindOf(v, o));   // label, not the radiator fan (same values)
        o.Output.InrushCurrentLimit = 80;
        Pro(v, 17).P.TripTime = 200;
        Assert.Equal(["inrush limit", "trip time"], PdmPresets.Changed(v, o, PdmDeviceKind.CondenserFan));
        // a fresh PC (no label): the matching preset is found, an edited one is "none"
        o.Device.CustomPdm!.OutputPresets.Clear();
        Assert.Equal(PdmDeviceKind.None, PdmPresets.KindOf(v, o));
        Assert.Null(PdmPresets.Apply(v, 18, PdmDeviceKind.FuelPump));
        o.Device.CustomPdm!.OutputPresets.Clear();
        Assert.Equal(PdmDeviceKind.FuelPump, PdmPresets.KindOf(v, Out(v, 18)));
        Assert.DoesNotContain(o.Device.Params, p => p.Name.Contains("preset", StringComparison.OrdinalIgnoreCase)); // not a board param
    }

    [Fact]
    public void PresetSetsTheLinkLossModeAndSoftStartGoesWithTheFanPresetOnly()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 1, 17));                                   // A1 IN1 -> B OUT1, off
        var notes = new List<string>();
        Assert.Null(PdmPresets.Apply(v, 17, PdmDeviceKind.RadiatorFan, notes));
        Assert.Equal(PdmLinkLoss.On, PdmLinks.LinkOf(v, Out(v, 17))!.Loss);
        Assert.Contains(notes, n => n.Contains("on 1 s after the message stops"));
        Assert.Null(PdmPresets.Apply(v, 17, PdmDeviceKind.FuelPump));
        Assert.Equal(PdmLinkLoss.Off, PdmLinks.LinkOf(v, Out(v, 17))!.Loss);
        Assert.False(Out(v, 17).Output.SoftStartEnabled);
        Assert.False(Out(v, 17).Output.PwmEnabled);                           // PWM was only for the soft start
        Assert.Contains("link loss", (PdmLinks.SetMode(v, 17, PdmLinkLoss.Hold), PdmPresets.Changed(v, Out(v, 17), PdmDeviceKind.FuelPump)).Item2);
        var n2 = new List<string>();
        Assert.Null(PdmPresets.Apply(v, 20, PdmDeviceKind.Lamp, n2));
        Assert.Contains("no link or ECU command yet", n2.Single());
        Assert.Contains("runs the PDM's own fans", PdmPresets.Apply(v, 10, PdmDeviceKind.Lamp));
        Assert.Equal("3 trips in all (2 retries, 2 s apart)", PdmPresets.TripsText(3, 2000));
    }

    [Fact]
    public void PresetKeepsAFanCurveWhenItTurnsSoftStartOff()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var temp = PdmFactoryDefaults.BoardTempVar(b);
        Assert.Null(PdmPwm.Set(v, 17, new PdmPwmSpec(true, 200, PdmDutyKind.Curve, Var: temp, Points: [(40, 20), (60, 100)], SoftStart: true)));
        Assert.Null(PdmPresets.Apply(v, 17, PdmDeviceKind.Motor));
        Assert.True(Out(v, 17).Output is { PwmEnabled: true, VariableDutyCycle: true, SoftStartEnabled: false });
    }

    // ================================================================ loss delay

    [Fact]
    public void LossDelayIsTheLinkTimeOutAndOnLinksGetAnAliveWithTheSameDelay()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Null(PdmLinks.Add(v, 1, 17, PdmLinkLoss.Off, delayMs: 500));
        Assert.Null(PdmLinks.Add(v, 1, 18, PdmLinkLoss.On, delayMs: 2000));
        Assert.Null(PdmLinks.Add(v, 2, 19, PdmLinkLoss.On, delayMs: 2000));   // same delay: same ALIVE / LOST
        Assert.Null(PdmLinks.Add(v, 3, 20, PdmLinkLoss.On));                   // 1 s: its own ALIVE + LOST, SEEN shared
        var l = PdmLinks.Links(v).ToDictionary(x => x.Out.Number);
        Assert.Equal((500, 2000, 2000, 1000), (l[17].DelayMs, l[18].DelayMs, l[19].DelayMs, l[20].DelayMs));
        Assert.Equal(500, b.CanInputs[l[17].Slot!.Value].Timeout);
        Assert.Equal(2000, b.CanInputs[l[18].Shared!.Alive].Timeout);
        Assert.Equal(l[18].Shared, l[19].Shared);
        Assert.NotEqual(l[18].Shared!.Alive, l[20].Shared!.Alive);
        Assert.Equal(l[18].Shared!.Seen, l[20].Shared!.Seen);
        Assert.False(b.CanInputs[l[18].Shared!.Seen].TimeoutEnabled);
        Assert.True(l[18].Virt > l[18].Shared!.Lost && l[20].Virt > l[20].Shared!.Lost);
        Assert.Equal("off 0.5 s after the message stops", l[17].LossText);
        Assert.Equal("on 2 s after the message stops; off until the first frame", l[18].LossText);
        // cost: 4 link slots + SEEN + 2 ALIVE = 7 CAN inputs, 3 link + 2 LOST = 5 virtual inputs
        Assert.Equal(32 - 7, Free(v, "B", PdmResKind.CanInput));
        NoConflicts(v);
        Assert.Contains(PdmLinks.Slots(v).Single(s => s.Board == "B").CanInputs, u => u.UsedBy.Contains("alive (its message 37 heard in the last 2 s)"));
    }

    [Fact]
    public void ChangingTheDelayMovesTheLinkAndFreesTheOldAlive()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Null(PdmLinks.Add(v, 1, 18, PdmLinkLoss.On));
        Assert.Null(PdmLinks.SetDelay(v, 18, 3000));
        var l = PdmLinks.LinkOf(v, Out(v, 18))!;
        Assert.Equal((PdmLinkLoss.On, 3000), (l.Loss!.Value, l.DelayMs));
        Assert.Single(PdmLinks.Shared(v));                                     // the 1 s ALIVE / LOST is gone
        Assert.Equal(32 - 3, Free(v, "B", PdmResKind.CanInput));
        Assert.Null(PdmLinks.Remove(v, 18));
        Assert.Empty(PdmLinks.Shared(v));
        Assert.All(b.CanInputs, c => Assert.False(c.Enabled));
        Assert.Equal(32, Free(v, "B", PdmResKind.CanInput));
    }

    [Theory]
    [InlineData(299)]
    [InlineData(10001)]
    public void LossDelayOutOfRangeIsRefused(int ms)
    {
        var v = NewPdm();
        var before = PdmTriggersTests.Raw(v);
        Assert.Contains("300 to 10000 ms", PdmLinks.Add(v, 1, 17, PdmLinkLoss.Off, delayMs: ms));
        Assert.Equal(before, PdmTriggersTests.Raw(v));
        Assert.Null(PdmLinks.Add(v, 1, 17, PdmLinkLoss.Hold, delayMs: ms));  // hold: no delay
        Assert.Contains("no loss delay", PdmLinks.SetDelay(v, 17, 1000));
    }

    [Fact]
    public void DelayIsReadBackFromTheParams()
    {
        var v = NewPdm();
        Assert.Null(PdmLinks.Add(v, 1, 21, PdmLinkLoss.Condition, cond: Di(Dev(v, "B"), 0), delayMs: 750));
        var copy = PdmView.Build(v.Boards.Select(b => b.Device));               // the same params, nothing else
        var l = PdmLinks.LinkOf(copy, copy.Outputs.Single(o => o.Number == 21))!;
        Assert.Equal((PdmLinkLoss.Condition, 750), (l.Loss!.Value, l.DelayMs));
    }

    // ================================================================ ECU-driven outputs

    [Fact]
    public void EcuOffOutputIsOneCanInputOnTheStreamByteLittleEndian()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Null(PdmEcu.Set(v, 19, PdmEcu.DefaultId, 2));
        var c = b.CanInputs[0];
        Assert.True(c is { Enabled: true, Id: 0x3F4, StartBit: 16, BitLength: 8, ByteOrder: ByteOrder.LittleEndian, Operator: Operator.Equal, Operand: 1.0, TimeoutEnabled: true, Timeout: 1000 });
        Assert.Equal(PdmFactoryDefaults.CanInState(b, 0), b.Outputs[2].Input);
        Assert.Equal("ECU 0x3F4 byte 2 = 1 (ECU only; off 1 s after the ECU frames stop)", Words(v, 19));
        Assert.Equal(PdmTriggerKind.Ecu, PdmTriggers.Of(M(v), 19).Kind);
        Assert.Equal(PdmClaimKind.Link, M(v).ClaimOf(new PdmRes("B", PdmResKind.CanInput, 0)).Kind);
        Assert.Equal(23, PdmEcu.StartBit(2, ByteOrder.BigEndian));            // DBC Motorola MSB rule (utils/dbc.cpp)
        NoConflicts(v);
    }

    [Fact]
    public void EcuOnOutputUsesTheLinkLossRecipeOnTheEcuStream()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        Assert.Equal(3, PdmEcu.Cost(v, Out(v, 17), 0x3F4, PdmLinkLoss.On, 500)[PdmResKind.CanInput]);
        Assert.Null(PdmEcu.Set(v, 17, 0x3F4, 0, PdmLinkLoss.On, 500));          // radiator fan
        Assert.Null(PdmEcu.Set(v, 18, 0x3F4, 1, PdmLinkLoss.On, 500));          // condenser fan: shares ALIVE / SEEN / LOST
        Assert.Null(PdmEcu.Set(v, 19, 0x3F4, 2, PdmLinkLoss.Hold));            // fuel pump: hold here (test)
        var e = PdmEcu.All(v).ToDictionary(x => x.Out.Number);
        Assert.Equal(e[17].Shared, e[18].Shared);
        var sh = e[17].Shared!.Value;
        Assert.True(b.CanInputs[sh.Alive] is { Id: 0x3F4, StartBit: 0, BitLength: 1, Operator: Operator.GreaterThanOrEqual, TimeoutEnabled: true, Timeout: 500 });
        Assert.False(b.CanInputs[sh.Seen].TimeoutEnabled);
        Assert.True(e[17].Virt > sh.Lost);
        Assert.Equal(500, b.CanInputs[e[17].Slot].Timeout);
        Assert.False(b.CanInputs[e[19].Slot].TimeoutEnabled);
        Assert.Equal(32 - 5, Free(v, "B", PdmResKind.CanInput));
        Assert.Equal(16 - 2 - 3, Free(v, "B", PdmResKind.VirtualInput));        // 2 load-shed reserved, LOST + 2
        NoConflicts(v);
        Assert.Contains("on 0.5 s after the ECU frames stop", Words(v, 17));
        Assert.Contains(PdmLinks.Slots(v).Single(s => s.Board == "B").CanInputs, u => u.UsedBy.StartsWith("shared: ECU 0x3F4 alive"));
        // remove: the last on output frees ALIVE / SEEN / LOST
        Assert.Null(PdmEcu.Remove(v, 17));
        Assert.NotNull(PdmEcu.All(v).Single(x => x.Out.Number == 18).Shared);
        Assert.Null(PdmEcu.Remove(v, 18));
        Assert.Null(PdmEcu.Remove(v, 19));
        Assert.Equal(32, Free(v, "B", PdmResKind.CanInput));
        Assert.Equal(14, Free(v, "B", PdmResKind.VirtualInput));
    }

    [Fact]
    public void EcuOutputRefusesBadSettingsAndAsksBeforeReplacing()
    {
        var v = NewPdm();
        Assert.Contains("inside a PDM board's own ID block", PdmEcu.Set(v, 17, 0x527, 0));
        Assert.Contains("0 to 7", PdmEcu.Set(v, 17, 0x3F4, 8));
        Assert.Contains("150 to 10000 ms", PdmEcu.Set(v, 17, 0x3F4, 0, PdmLinkLoss.Off, 100));
        Assert.Null(PdmEcu.Set(v, 17, 0x3F4, 0, PdmLinkLoss.Off, 150));          // 3 x 50 ms
        Assert.Contains("runs the fans", PdmEcu.Set(v, 10, 0x3F4, 0));
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Input(PdmTerm.In(15))));
        Assert.Contains("already assigned", PdmEcu.Set(v, 18, 0x3F4, 1));
        Assert.Null(PdmEcu.Set(v, 18, 0x3F4, 1, overwrite: true));
        Assert.Null(PdmEcu.Set(v, 18, 0x3F4, 3));                               // its own: no question
        Assert.Contains("already assigned", PdmTriggers.Conflict(v, 18));      // the trigger editor asks first
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.None, overwrite: true));
        Assert.Empty(PdmEcu.All(v).Where(x => x.Out.Number == 18));
    }

    [Fact]
    public void OnlyByteAlignedCommandsOnAForeignIdAreEcuCommands()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        foreach (var (s, id, bit) in new[] { (0, 0x527, 0), (1, 0x3F4, 4) })   // A1's msg 37 ID; a start bit inside a byte
        {
            var c = b.CanInputs[s];
            (c.Enabled, c.Id, c.StartBit, c.BitLength, c.Operator, c.Operand) = (true, id, bit, 8, Operator.Equal, 1.0);
            b.Outputs[s].Input = PdmFactoryDefaults.CanInState(b, s);
        }
        Assert.Empty(PdmEcu.All(v));
        Assert.Equal(PdmTriggerKind.Hand, PdmTriggers.Of(M(v), 17).Kind);
    }

    [Fact]
    public void FullBoardRefusesAnEcuOutputAndChangesNothing()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        for (var s = 0; s < 32; s++) (b.CanInputs[s].Enabled, b.CanInputs[s].Id) = (true, 0x100 + s);
        var before = PdmTriggersTests.Raw(v);
        Assert.Contains("B is full", PdmEcu.Set(v, 17, 0x3F4, 0));
        Assert.Equal(before, PdmTriggersTests.Raw(v));
    }

    [Fact]
    public void CanValueIsAHandMadeNumberForLevelsAndCurves()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var s = PdmEcu.AddValue(v, "B", "ECU coolant", 0x3F5, 2, 16, ByteOrder.BigEndian, true, 0.1, -40, 1000, out var why);
        Assert.Null(why);
        var c = b.CanInputs[s];
        Assert.True(c is { Id: 0x3F5, StartBit: 23, BitLength: 16, ByteOrder: ByteOrder.BigEndian, Signed: true, Factor: 0.1, Offset: -40.0, Operator: Operator.GreaterThanOrEqual });
        var val = PdmFactoryDefaults.CanInState(b, s) + 1;
        Assert.Contains(PdmTriggers.ValueChoices(M(v), "B"), x => x.Var == val);
        Assert.Contains(PdmPwm.ValueChoices(M(v), "B"), x => x.Var == val);
    }

    // ================================================================ PWM / fan curve

    [Fact]
    public void FanCurveIsOneLookupTableDrivingTheDuty()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var s0 = PdmEcu.AddValue(v, "B", "coolant", 0x3F5, 0, 16, ByteOrder.LittleEndian, false, 0.1, 0, 1000, out _);
        var cool = PdmFactoryDefaults.CanInState(b, s0) + 1;
        var spec = new PdmPwmSpec(true, 200, PdmDutyKind.Curve, Var: cool, Points: [(80, 0), (90, 40), (100, 100)], SoftStart: true, SoftStartMs: 800, MinDuty: 20);
        Assert.Equal(1, PdmPwm.Cost(spec)[PdmResKind.Table]);
        Assert.Null(PdmPwm.Set(v, 17, spec));
        var t = b.CustomPdm!.Tables[0];
        Assert.True(t is { Enabled: true, Points: 3 });
        Assert.Equal(cool, t.Input);
        Assert.Equal((90.0, 40.0), (t.X[1], t.Y[1]));
        var x = b.Outputs[0];
        Assert.True(x is { PwmEnabled: true, VariableDutyCycle: true, DutyCycleDenominator: 1, Frequency: 200, MinDutyCycle: 20, SoftStartEnabled: true, SoftStartRampTime: 800 });
        Assert.Equal(PdmPwm.TableVar(b, 0), x.DutyCycleInput);
        Assert.Equal(spec, PdmPwm.Of(M(v), Out(v, 17)));
        Assert.Contains("PWM 200 Hz, duty from B CAN input 1 'coolant' value: 80 -> 0 %, 90 -> 40 %, 100 -> 100 %, at least 20 %, soft start 0.8 s", PdmPwm.Words(M(v), Out(v, 17)));
        Assert.Equal(PdmClaimKind.Trigger, M(v).ClaimOf(new PdmRes("B", PdmResKind.Table, 0)).Kind);
        NoConflicts(v);
        // a second curve takes table 2; fixed duty frees table 1
        Assert.Null(PdmPwm.Set(v, 18, spec with { FreqHz = 100 }));
        Assert.Equal(1, PdmPwm.TableVar(b, 1) - PdmPwm.TableVar(b, 0));
        Assert.Null(PdmPwm.Set(v, 17, new PdmPwmSpec(true, 100, PdmDutyKind.Fixed, 60)));
        Assert.True(PdmModel.Fresh(b.CustomPdm.Tables[0]));
        Assert.Equal("PWM 100 Hz, 60 %", PdmPwm.Words(M(v), Out(v, 17)));
        Assert.Null(PdmPwm.Set(v, 18, PdmPwmSpec.Off));
        Assert.Equal(4, Free(v, "B", PdmResKind.Table));
        Assert.False(b.Outputs[1].PwmEnabled);
    }

    [Fact]
    public void PwmRefusesBadValuesAndAFullBoard()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var temp = PdmFactoryDefaults.BoardTempVar(b);
        var c = new PdmPwmSpec(true, 100, PdmDutyKind.Curve, Var: temp, Points: [(40, 20), (60, 100)]);
        Assert.Contains("16 to 400 Hz", PdmPwm.Set(v, 17, c with { FreqHz = 401 }));
        Assert.Contains("rise", PdmPwm.Set(v, 17, c with { Points = [(60, 20), (40, 100)] }));
        Assert.Contains("2 to 8 points", PdmPwm.Set(v, 17, c with { Points = [(60, 20)] }));
        Assert.Contains("0 to 100 %", PdmPwm.Set(v, 17, c with { Points = [(40, 20), (60, 120)] }));
        Assert.Contains("own fans", PdmPwm.Set(v, 10, c));
        for (var n = 17; n <= 20; n++) Assert.Null(PdmPwm.Set(v, n, c));
        var before = PdmTriggersTests.Raw(v);
        Assert.Contains("B is full", PdmPwm.Set(v, 21, c));
        Assert.Equal(before, PdmTriggersTests.Raw(v));
        Assert.Null(PdmPwm.Set(v, 21, c with { Duty = PdmDutyKind.Value }));   // a value as the duty: no table
        Assert.Equal(1, b.Outputs[4].DutyCycleDenominator);
    }

    [Fact]
    public void TachOutputFrequencyFollowsAValueWithPulsesPerRev()
    {
        var v = NewPdm();
        var a1 = Dev(v, "A1");
        var s0 = PdmEcu.AddValue(v, "A1", "ECU rpm", 0x3F6, 0, 16, ByteOrder.LittleEndian, false, 1, 0, 1000, out _);
        var rpm = PdmFactoryDefaults.CanInState(a1, s0) + 1;
        Assert.Null(PdmPresets.Apply(v, 4, PdmDeviceKind.Tacho));
        Assert.Equal((1.0, 2.0), (Out(v, 4).Output.CurrentLimit, Out(v, 4).Output.InrushCurrentLimit));
        var spec = new PdmPwmSpec(true, 100, PdmDutyKind.Fixed, 50, FreqInput: new PdmFreqInput(rpm, 2, 16, 400));
        Assert.Null(PdmPwm.Set(v, 4, spec));
        var f = a1.CustomPdm!.PwmFreqInputs[3];
        Assert.True(f is { Enabled: true, MinHz: 16, MaxHz: 400 });
        Assert.Equal((rpm, 2.0 / 60), (f.Input, f.Factor));
        Assert.Equal(spec, PdmPwm.Of(M(v), Out(v, 4)));
        Assert.Equal("PWM 2 pulses per rev of A1 CAN input 1 'ECU rpm' value (16-400 Hz), 50 %", PdmPwm.Words(M(v), Out(v, 4)));
        Assert.Contains(M(v).Refs, r => r.Field == "PWM frequency input" && r.Var == rpm);
        Assert.Contains("16 to 400 Hz", PdmPwm.Set(v, 5, new PdmPwmSpec(true, 15)));
        Assert.Contains("16 to 1000 Hz", PdmPwm.Set(v, 5, spec with { FreqInput = new PdmFreqInput(rpm, 2, 10, 400) }));
        Assert.Null(PdmPwm.Set(v, 4, PdmPwmSpec.Off));
        Assert.False(f.Enabled);
        Assert.Equal(1.0, f.Factor);
    }

    // ================================================================ turn signals + hazards

    [Fact]
    public void TurnSignalsAreOneFlasherAndThreeVirtualInputs()
    {
        var v = NewPdm();
        var a2 = Dev(v, "A2");
        var spec = new PdmTurnSpec(9, 11, PdmTerm.In(8), PdmTerm.In(9), PdmTerm.In(15)); // L / R on A2, hazard on B (CAN)
        Assert.Equal(new Dictionary<PdmResKind, int> { [PdmResKind.VirtualInput] = 3, [PdmResKind.Flasher] = 1, [PdmResKind.CanInput] = 1 },
            PdmFunctions.TurnCost(v, "A2", spec));
        var freeV = Free(v, "A2", PdmResKind.VirtualInput);
        Assert.Null(PdmFunctions.SetTurn(v, spec));
        Assert.Equal(freeV - 3, Free(v, "A2", PdmResKind.VirtualInput));
        var fl = a2.Flashers.Single(f => f.Enabled);
        Assert.Equal((350, 350, false), (fl.OnTime, fl.OffTime, fl.Single));
        Assert.Equal("turn signal LEFT: IN8 or hazard IN15, flashing 350 / 350 ms in step with output 11", Words(v, 9));
        Assert.Equal("turn signal RIGHT: IN9 or hazard IN15, flashing 350 / 350 ms in step with output 9", Words(v, 11));
        Assert.Equal(PdmTriggerKind.Function, PdmTriggers.Of(M(v), 9).Kind);
        NoConflicts(v);
        // replacing one side asks, and removes the whole function
        Assert.Contains("already assigned", PdmTriggers.Conflict(v, 11));
        Assert.Null(PdmTriggers.Set(v, 11, PdmTriggerSpec.Input(PdmTerm.In(10)), overwrite: true));
        Assert.Equal(PdmTriggerKind.None, PdmTriggers.Of(M(v), 9).Kind);
        Assert.Equal(freeV, Free(v, "A2", PdmResKind.VirtualInput));
        Assert.Equal(4, Free(v, "A2", PdmResKind.Flasher));
        Assert.Equal(28, Free(v, "A2", PdmResKind.CanInput));                  // 4 fan slots reserved, the hazard slot freed
    }

    [Fact]
    public void TurnSignalsRefuseTwoBoardsAndFullBoards()
    {
        var v = NewPdm();
        Assert.Contains("on one board", PdmFunctions.SetTurn(v, new PdmTurnSpec(9, 17, PdmTerm.In(8), PdmTerm.In(9), PdmTerm.In(10))));
        Assert.Contains("three different", PdmFunctions.SetTurn(v, new PdmTurnSpec(9, 11, PdmTerm.In(8), PdmTerm.In(8), PdmTerm.In(10))));
        var a2 = Dev(v, "A2");
        foreach (var f in a2.Flashers) (f.Enabled, f.Input) = (true, 1);
        var before = PdmTriggersTests.Raw(v);
        Assert.Contains("A2 is full", PdmFunctions.SetTurn(v, new PdmTurnSpec(9, 11, PdmTerm.In(8), PdmTerm.In(9), PdmTerm.In(10))));
        Assert.Equal(before, PdmTriggersTests.Raw(v));
    }

    // ================================================================ wiper

    [Fact]
    public void WiperUsesTheBoardWiperFunctionWithTheParkCamOnTheSameBoard()
    {
        var v = NewPdm();
        var b = Dev(v, "B");
        var spec = new PdmWiperSpec(23, 24, PdmTerm.In(15), PdmTerm.In(16), PdmTerm.In(17), 18, true, PdmTerm.In(19), 3, 1500);
        Assert.Contains("park cam must be a digital input of B", PdmFunctions.SetWiper(v, spec with { ParkInput = 1 }));
        Assert.Null(PdmFunctions.SetWiper(v, spec));
        var w = b.Wipers;
        Assert.True(w is { Enabled: true, Mode: WiperMode.DigIn, ParkStopLevel: true, WashWipeCycles: 3 });
        Assert.Equal((Di(b, 0), Di(b, 1), Di(b, 2), Di(b, 3), Di(b, 4)), (w.SlowInput, w.FastInput, w.InterInput, w.ParkInput, w.WashInput));
        Assert.Equal(1500, w.IntermitTime[0]);
        Assert.StartsWith("wiper motor run (wiper on B: switches slow IN15, fast IN16, intermittent IN17, wash IN19; park cam IN18 (on in the park zone), intermittent pause 1.5 s, 3 wipes after a wash)", Words(v, 23));
        Assert.Equal("wiper high speed (output 23's wiper)", Words(v, 24));
        NoConflicts(v);
        Assert.Null(PdmFunctions.Remove(v, 24));
        Assert.False(b.Wipers.Enabled);
        Assert.Equal(PdmTriggerKind.None, PdmTriggers.Of(M(v), 23).Kind);
    }
}
