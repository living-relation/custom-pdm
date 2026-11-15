using domain.Devices;
using domain.Enums;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// Route B phase B2 against the real firmware logic: all three boards on ONE bus, three PC devices in ONE real
// DeviceManager (shared request queue, frames routed by ID range), as the /pdm page uses them.
[Collection("sim")]
public class PdmLiveSimTests(ITestOutputHelper output)
{
    internal static PdmRig Boot(SimBus bus)
    {
        var rig = new PdmRig(bus);
        rig.Step(1500);
        return rig;
    }

    // one output setting and one input setting per board, different on every board
    internal static void Edit(PdmRig rig)
    {
        (rig.A1.Outputs[2].CurrentLimit, rig.A1.Outputs[2].ResetCountLimit, rig.A1.DigitalInputs[3].DebounceTime, rig.A1.DigitalInputs[3].Invert) = (5.5, 4, 35, true);
        (rig.A2.Outputs[4].CurrentLimit, rig.A2.Outputs[4].ResetCountLimit, rig.A2.DigitalInputs[5].DebounceTime, rig.A2.DigitalInputs[5].Invert) = (6.5, 5, 45, true);
        (rig.B.Outputs[6].CurrentLimit, rig.B.Outputs[6].ResetCountLimit, rig.B.DigitalInputs[8].DebounceTime, rig.B.DigitalInputs[8].Invert) = (12.5, 6, 55, true);
    }

    internal static (double, int, int, bool)[] Edited(PdmRig rig) =>
    [
        (rig.A1.Outputs[2].CurrentLimit, rig.A1.Outputs[2].ResetCountLimit, rig.A1.DigitalInputs[3].DebounceTime, rig.A1.DigitalInputs[3].Invert),
        (rig.A2.Outputs[4].CurrentLimit, rig.A2.Outputs[4].ResetCountLimit, rig.A2.DigitalInputs[5].DebounceTime, rig.A2.DigitalInputs[5].Invert),
        (rig.B.Outputs[6].CurrentLimit, rig.B.Outputs[6].ResetCountLimit, rig.B.DigitalInputs[8].DebounceTime, rig.B.DigitalInputs[8].Invert),
    ];

    internal static readonly (double, int, int, bool)[] NewValues = [(5.5, 4, 35, true), (6.5, 5, 45, true), (12.5, 6, 55, true)];

    internal static bool ReadOne(PdmRig rig, FwDevice dev)
    {
        dev.ConfigMismatch = true;
        rig.Mgr.ReadAllDeviceConfig(dev.Guid);
        return rig.RunUntil(() => dev.FullReadDone && !dev.ConfigMismatch);
    }

    // The plain stock calls, one board after another: Read All x3, edit, Write All x3, then a fresh PC reads back.
    [SimFact]
    public void ThreeBoardsOnOneBusReadEditWriteReadBack()
    {
        using var bus = new SimBus();
        var rig = Boot(bus);
        Assert.All(rig.All, d => Assert.True(d.Connected, $"{d.Name} not connected"));

        foreach (var dev in rig.All)
        {
            var t = rig.SimMs;
            Assert.True(ReadOne(rig, dev), $"{dev.Name}: Read All");
            output.WriteLine($"{dev.Name}: Read All {rig.SimMs - t:F0} ms sim time, {dev.Params.Count} params");
        }
        Assert.Equal([0x500, 0x540, 0x580], rig.All.Select(d => d.BaseId));
        Assert.Equal(3, rig.Notes.Count(n => n.EndsWith("Read Successful")));
        var before = Edited(rig);
        Assert.DoesNotContain(before, b => NewValues.Contains(b));

        Edit(rig);
        foreach (var dev in rig.All)
        {
            var t = rig.SimMs;
            dev.ConfigMismatch = true;
            Assert.True(rig.Mgr.WriteAllDeviceConfig(dev.Guid));
            Assert.True(rig.RunUntil(() => rig.Notes.Contains($"{dev.Name}: Write Successful") && !dev.ConfigMismatch), $"{dev.Name}: Write All");
            output.WriteLine($"{dev.Name}: Write All {rig.SimMs - t:F0} ms sim time");
        }

        var pc2 = new PdmRig(bus);
        foreach (var dev in pc2.All) Assert.True(ReadOne(pc2, dev), $"{dev.Name}: read back");
        Assert.Equal(NewValues, Edited(pc2));
        Assert.Equal([0x500, 0x540, 0x580], pc2.All.Select(d => d.BaseId));
    }
}
