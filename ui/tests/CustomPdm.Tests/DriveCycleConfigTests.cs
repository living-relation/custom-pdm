using application.Services;
using domain.CustomPdm;
using domain.Devices;
using domain.Devices.Functions;
using domain.Enums;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace CustomPdm.Tests;

// configfix (2026-11-23): what the drive-cycle simulation (firmware/sim/s5_drive_cycle.py, docs/simulation-index.md
// section 2) found in the ST185 demo starter (ui/examples/st185-starter.json), fixed, and the generic preset rules
// (Dan via the coordinator, 2026-11-23: ECU-commanded loads go OFF at ECU frame loss - the ECU keeps control and
// does its own shutdown / after-run; A/C on an OEM switch, no keypad). s5 proves the behaviour on the real firmware
// logic; these tests pin the settings.
public class DriveCycleConfigTests
{
    private static async Task<PdmView> Starter()
    {
        var (mgr, svc) = St185CarTests.NewApp();
        Assert.Null(await PdmStarter.LoadAsync(PdmStarter.Find(AppContext.BaseDirectory)!,
            new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager()), mgr, svc.Ops));
        return svc.BuildView();
    }

    private static PdmView NewPdm()
    {
        var (_, svc) = St185CarTests.NewApp();
        Assert.Null(svc.NewPdm());
        return svc.BuildView();
    }

    private static PdmOutputRow Out(PdmView v, int n) => v.Outputs.Single(o => o.Number == n);

    private static FwDevice Dev(PdmView v, string role) => v.Boards.Single(b => b.Role == role).Device;

    private static object? Owner(FwDevice d, int var) => d.VarMap.FirstOrDefault(x => x.VariableIndex == var)?.Owner;

    // CAN-Lambda (B OUT5): the load starts at 8.1 A x 1.5 for 100 ms (tools/presim_parts.py CAR_LOADS): inrush 20 A /
    // 200 ms, the steady limit at or under the LAM 10 A fuse
    [Fact]
    public async Task TheStartersCanLambdaStartsWithoutATrip()
    {
        var o = Out(await Starter(), 21).Output;
        Assert.True(o.CurrentLimit <= 10.0, $"CAN-Lambda limit {o.CurrentLimit} A above the LAM 10 A fuse");
        Assert.Equal((20.0, 200), (o.InrushCurrentLimit, o.InrushTime));
        Assert.True(o.InrushCurrentLimit >= 8.1 * 1.5 * 14.4 / 13.5, "inrush limit under the key-on start at 14.4 V");
    }

    // ECU-commanded loads OFF at ECU frame loss: pump and condenser fan (ECU bytes), radiator fan (coolant value: it
    // times out to 0 = below the off level); nothing "on at loss" left
    [Fact]
    public async Task TheStartersEcuLoadsGoOffAtEcuLoss()
    {
        var v = await Starter();
        var b = Dev(v, "B");
        Assert.Equal([(18, PdmLinkLoss.Off), (19, PdmLinkLoss.Off)], PdmEcu.All(v).Select(e => (e.Out.Number, e.Loss)).OrderBy(x => x.Item1).ToList());
        var hyst = Assert.IsType<VirtualInput>(Owner(b, Out(v, 17).Output.Input));
        var on = Assert.IsType<Condition>(Owner(b, hyst.Var0));
        var cool = Assert.IsType<CanInput>(Owner(b, on.Input));              // the CAN value "ECU coolant"
        Assert.Equal(("ECU coolant", true, 92.0), (cool.Name, cool.TimeoutEnabled, on.Arg));
        Assert.DoesNotContain(b.VirtualInputs, x => x.Enabled && x.Name.Contains("at loss"));
    }

    // A/C clutch on the OEM A/C switch (a 12 V digital input, IN20 = B IN6), no keypad
    [Fact]
    public async Task TheStartersAcClutchFollowsItsSwitch()
    {
        var v = await Starter();
        var b = Dev(v, "B");
        var sw = v.Inputs.Single(i => i.Number == 20);
        Assert.Equal(("A/C switch", true, false, InputPull.PullDown, InputMode.Momentary),
            (sw.Name, sw.Digital!.Enabled, sw.Digital.Invert, sw.Digital.Pull, sw.Digital.Mode));
        Assert.Equal(PdmFactoryDefaults.VarOf(b, sw.Digital), Out(v, 22).Output.Input);
        Assert.DoesNotContain(b.CanInputs, c => c.Enabled && c.Id == 0x1A8);
    }

    // Auto sleep (stock core/sleep.cpp CheckEnterSleep + device.muteCanTxInput, PdmKeyOff): every board mutes its CAN
    // TX 10 s after the key off (IN15) and sleeps 30 s after the bus went quiet
    [Fact]
    public async Task EveryStarterBoardSleepsByItselfAfterTheKeyOff()
    {
        var v = await Starter();
        var wire = v.Inputs.Single(i => i.Number == 15);
        foreach (var q in v.Boards)
        {
            var d = q.Device;
            var tm = PdmKeyOff.SleepTimer(d);
            Assert.True(d.SleepEnabled, $"{q.Role} auto sleep off");
            Assert.NotNull(tm);
            Assert.Equal((true, TimerMode.OnDelay, PdmKeyOff.MuteDelayMs, PdmTriggers.AlwaysOnVar), (tm!.Enabled, tm.Mode, tm.Time, tm.Input));
            if (q.Role == wire.Board) Assert.Equal(PdmFactoryDefaults.VarOf(d, wire.Digital!), tm.ResetInput);
            else
            {
                var slot = Assert.IsType<CanInput>(Owner(d, tm.ResetInput));
                Assert.Equal((Dev(v, "B").BaseId + PdmLinks.StatusOffset, 0, true, 1000), (slot.Id, slot.StartBit, slot.TimeoutEnabled, slot.Timeout));
            }
        }
        Assert.Empty(PdmModel.Build(v).Problems);
        Assert.Equal(0, PdmLinks.RemoveUnused(v));   // "Remove unused" keeps the recipe
    }

    // The device presets: ECU-commanded loads off at ECU loss (all presets); fans / pump off at loss on links too
    [Fact]
    public void EcuCommandedPresetsGoOffAtEcuLoss()
    {
        Assert.All(new[] { PdmDeviceKind.RadiatorFan, PdmDeviceKind.CondenserFan, PdmDeviceKind.FuelPump },
            k => Assert.Equal(PdmLinkLoss.Off, PdmPresets.Of(k).Loss));
        Assert.Equal(PdmLinkLoss.Off, PdmPresets.EcuLoss);
        var v = NewPdm();
        Assert.Null(PdmEcu.Set(v, 6, 0x3F4, 3, PdmLinkLoss.Hold));            // ECU-commanded module feed (EPS enable)
        Assert.Null(PdmEcu.Set(v, 17, 0x3F4, 1, PdmLinkLoss.On));             // radiator fan
        Assert.Null(PdmPresets.Apply(v, 6, PdmDeviceKind.Module));
        Assert.Null(PdmPresets.Apply(v, 17, PdmDeviceKind.RadiatorFan));
        Assert.Equal((PdmLinkLoss.Off, PdmLinkLoss.Off), (PdmEcu.Of(v, Out(v, 6))!.Loss, PdmEcu.Of(v, Out(v, 17))!.Loss));
        Assert.Empty(PdmPresets.Changed(v, Out(v, 6), PdmDeviceKind.Module));
        Assert.Equal(PdmLinkLoss.Off, PdmPresets.DefaultLoss(v, Out(v, 6), ecu: true));
        // a module feed linked from another board's input still holds (not ECU-commanded)
        Assert.Null(PdmLinks.Add(v, 1, 21));
        Assert.Null(PdmPresets.Apply(v, 21, PdmDeviceKind.Module));
        Assert.Equal(PdmLinkLoss.Hold, PdmLinks.LinkOf(v, Out(v, 21))!.Loss);
        Assert.Equal(PdmLinkLoss.Hold, PdmPresets.DefaultLoss(v, Out(v, 21)));
        // editing an ECU output back to "on at loss" by hand shows as a preset change
        Assert.Null(PdmEcu.Set(v, 17, 0x3F4, 1, PdmLinkLoss.On, overwrite: true));
        Assert.Contains("link loss", PdmPresets.Changed(v, Out(v, 17), PdmDeviceKind.RadiatorFan));
    }

    // Editing a preset output's current limit keeps its inrush on the preset rule (Module: 2 x the limit)
    [Fact]
    public void EditingAPresetLimitKeepsTheInrushRule()
    {
        var v = NewPdm();
        var o = Out(v, 21);
        Assert.Null(PdmPresets.Apply(v, 21, PdmDeviceKind.Module));
        Assert.Equal((5.0, 10.0), (o.Output.CurrentLimit, o.Output.InrushCurrentLimit));
        o.Output.CurrentLimit = 10;
        Assert.Equal("inrush limit 20 A (ECU / module feed preset: 2 x the limit)", PdmPresets.LimitEdited(v, o, 5));
        Assert.Equal(20.0, o.Output.InrushCurrentLimit);
        o.Output.InrushCurrentLimit = 33;                       // set by hand: kept
        o.Output.CurrentLimit = 8;
        Assert.Null(PdmPresets.LimitEdited(v, o, 10));
        Assert.Equal(33.0, o.Output.InrushCurrentLimit);
        var h = Out(v, 22);                                     // another preset: its own factor (heater 1.5 x)
        Assert.Null(PdmPresets.Apply(v, 22, PdmDeviceKind.Heater));
        h.Output.CurrentLimit = 10;
        Assert.NotNull(PdmPresets.LimitEdited(v, h, 15));
        Assert.Equal(15.0, h.Output.InrushCurrentLimit);
        var n = Out(v, 4);                                      // no preset: nothing
        n.Output.CurrentLimit = 3;
        Assert.Null(PdmPresets.LimitEdited(v, n, 7.5));
    }

    // tools/verify_switching.py WARN rows the presets did not hold: PWM switching heat, halogen cold start
    [Fact]
    public void ThePresetsWarnAboutPwmHeatAndHalogenColdStarts()
    {
        Assert.Equal(6.8, PdmPresets.PwmMaxA(PdmPresets.Bts7008, 100, false), 1);    // verify_switching: 100 Hz 6.8 A
        Assert.Equal(12.5, PdmPresets.PwmMaxA(PdmPresets.Bts7004, 100, false), 1);
        Assert.Equal(23.8, PdmPresets.PwmMaxA(PdmPresets.Bts70012, 100, false), 1);
        Assert.Equal(61, PdmPresets.HalogenMaxW(PdmPresets.Bts7008), 0);             // 65 A / 14 x 13.2 V
        var v = NewPdm();
        var o = Out(v, 1);
        Assert.Null(PdmPresets.Apply(v, 1, PdmDeviceKind.LedLamp));
        o.Output.Enabled = true;
        Assert.Empty(PdmPresets.Warnings(v, o));
        (o.Output.PwmEnabled, o.Output.VariableDutyCycle, o.Output.FixedDutyCycle, o.Output.Frequency) = (true, false, 50, 100);
        o.Output.CurrentLimit = 7.5;
        Assert.Contains("PWM at 100 Hz: above 6.8 A the BTS7008-2EPA", Assert.Single(PdmPresets.Warnings(v, o)));
        o.Output.CurrentLimit = 5;
        Assert.Empty(PdmPresets.Warnings(v, o));
        Assert.Null(PdmPresets.Apply(v, 2, PdmDeviceKind.Lamp));
        Assert.Contains("Halogen lamp: above 61 W", Assert.Single(PdmPresets.Warnings(v, Out(v, 2))));
        // the fans' soft start alone (1 s ramp at full duty) is not PWM heat
        Assert.Null(PdmPresets.Apply(v, 17, PdmDeviceKind.RadiatorFan));
        Out(v, 17).Output.Enabled = true;
        Assert.Empty(PdmPresets.Warnings(v, Out(v, 17)));
    }
}
