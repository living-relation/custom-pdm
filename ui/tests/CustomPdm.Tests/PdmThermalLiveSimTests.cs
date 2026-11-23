using application.Services;
using domain.CustomPdm;
using domain.Devices;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// ADR-2026-11-20-temp-onepdm on the real firmware logic (A1, A2, B on one bus): the /pdm hot-spot set reaches board B
// converted (hot spot - 21 K) and board A keeps its factory 55 / 80, through the /pdm Write All; the boards' own
// thermal flags (msg 3 byte 7) then switch at those sensor values, and a fresh PC reads the same set back.
[Collection("sim")]
public class PdmThermalLiveSimTests(ITestOutputHelper output)
{
    private string? Run(PdmRig rig, PdmOpsService svc, PdmOpKind op)
    {
        var t = rig.SimMs;
        var refused = svc.Start(op, true, rig.Now);
        while (refused == null && svc.Ops.Busy && rig.SimMs - t < 120000)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }
        output.WriteLine($"{op}: {refused ?? string.Join(" | ", svc.Ops.Results.Select(r => $"{r.Role} {r.State}: {r.Text}"))} ({rig.SimMs - t:F0} ms sim time)");
        return refused;
    }

    private int Flags(SimBus bus, PdmRig rig, FwDevice dev, string board, double c)
    {
        bus.Cmd($"TEMP {board} {c.ToString(System.Globalization.CultureInfo.InvariantCulture)} 41");
        rig.Step(1500); // 250 ms sensor period + the 100 ms cyclic status
        var f = dev.CustomPdm!.ThermalFlags;
        output.WriteLine($"{board} sensor {c} C: flags {f} (warn {dev.CustomPdm.OverWarn}, soon {dev.CustomPdm.CriticalSoon}, critical {dev.CustomPdm.Critical})");
        return f;
    }

    [SimFact]
    public void HotSpotSetReachesBoardBConvertedAndBoardAKeepsItsFactoryLimits()
    {
        using var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        var svc = new PdmOpsService(rig.Mgr) { AutoTick = false };
        var view = svc.BuildView();
        foreach (var b in new[] { "A1", "A2", "B" }) bus.Cmd($"TEMP {b} 30 41");

        // warn / recovery / margin as one set, critical through the locked path (Unlock + type twice + Change)
        Assert.Null(PdmThermal.Set(view, new PdmHotSpotLimits(116, 125, 6, 5)));
        Assert.Null(PdmCritical.Apply(view, PdmCriticalKind.CritTemp, "123"));
        Assert.Equal([new PdmTempLimits(55, 80, 6, 5), new PdmTempLimits(55, 80, 6, 5), new PdmTempLimits(95, 102, 6, 5)], rig.All.Select(PdmTempLimits.Of));
        Assert.Null(Run(rig, svc, PdmOpKind.WriteAll));
        Assert.All(svc.Ops.Results, r => Assert.Equal(PdmStepState.Ok, r.State));

        // board B switches at hot spot - 21 K: warn 95, critical soon 97 (102 - 5), critical 102
        Assert.Equal(0, Flags(bus, rig, rig.B, "B", 94.5));
        Assert.Equal(1, Flags(bus, rig, rig.B, "B", 95.5));
        Assert.Equal(3, Flags(bus, rig, rig.B, "B", 97.5));
        Assert.Equal(3, Flags(bus, rig, rig.B, "B", 101.5));
        Assert.Equal(5, Flags(bus, rig, rig.B, "B", 102.5)); // critical (critical soon clears once critical, device.cpp)
        // board A was not given B's values: its factory 80 C critical still applies (and 55 C warn)
        Assert.Equal(0, Flags(bus, rig, rig.A1, "A1", 54.5));
        Assert.Equal(3, Flags(bus, rig, rig.A1, "A1", 79.5));
        Assert.Equal(5, Flags(bus, rig, rig.A1, "A1", 81.0));
        Assert.Equal(1, Flags(bus, rig, rig.A2, "A2", 60.0));

        // a fresh PC (as after an app restart) reads the same set back from the boards
        var pc2 = PdmLiveSimTests.Boot(bus);
        var svc2 = new PdmOpsService(pc2.Mgr) { AutoTick = false };
        Assert.Null(Run(pc2, svc2, PdmOpKind.ReadAll));
        var v2 = svc2.BuildView();
        Assert.Equal(new PdmHotSpotLimits(116, 123, 6, 5), PdmThermal.Current(v2));
        Assert.Equal([80, 80, 102], v2.Boards.Select(b => b.Device.CustomPdm!.TempCrit));
        Assert.Empty(PdmThermal.OffFactory(v2));
    }
}
