using application.Services;
using domain.CustomPdm;
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

    // ---- the /pdm buttons: PdmOpsService (PdmOps + the real DeviceManager), clocked by sim time ----

    private static PdmOpsService Service(PdmRig rig) => new(rig.Mgr) { AutoTick = false };

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

    private static PdmStepState[] States(PdmOpsService svc) => svc.Ops.Results.Select(r => r.State).ToArray();

    [SimFact]
    public void PdmReadAllEditWriteAllReadBackThenBurn()
    {
        using var bus = new SimBus();
        var rig = Boot(bus);
        var svc = Service(rig);

        // Write All / Burn refused until all three boards are read; nothing goes to the bus
        const string notRead = "A1: not read yet (Read All first); A2: not read yet (Read All first); B: not read yet (Read All first).";
        Assert.Equal(notRead, Run(rig, svc, PdmOpKind.WriteAll));
        Assert.Equal(notRead, Run(rig, svc, PdmOpKind.Burn));
        Assert.True(ReadOne(rig, rig.A1));
        Assert.True(ReadOne(rig, rig.A2));
        Assert.Equal("B: not read yet (Read All first).", Run(rig, svc, PdmOpKind.WriteAll));
        rig.Step(200);
        Assert.All(rig.All, d => Assert.Equal(0, rig.CountSent(d.BaseId, MessageCommand.WriteAll) + rig.CountSent(d.BaseId, MessageCommand.BurnParams)));

        Assert.Null(Run(rig, svc, PdmOpKind.ReadAll));
        Assert.Equal([PdmStepState.Ok, PdmStepState.Ok, PdmStepState.Ok], States(svc));
        Assert.Equal([0x500, 0x540, 0x580], rig.All.Select(d => d.BaseId));

        Edit(rig);
        Assert.Null(Run(rig, svc, PdmOpKind.WriteAll));
        Assert.Equal([PdmStepState.Ok, PdmStepState.Ok, PdmStepState.Ok], States(svc));
        Assert.Equal(0, rig.All.Sum(d => rig.CountSent(d.BaseId, MessageCommand.BurnParams))); // a write never burns

        var pc2 = Boot(bus);
        var svc2 = Service(pc2);
        Assert.Null(Run(pc2, svc2, PdmOpKind.ReadAll));
        Assert.Equal([PdmStepState.Ok, PdmStepState.Ok, PdmStepState.Ok], States(svc2));
        Assert.Equal(NewValues, Edited(pc2));

        // Burn: the PC differs from board A2 in one value -> the fresh check stops it, no burn frame for any board
        pc2.A2.Outputs[4].CurrentLimit = 6.0;
        Assert.Null(Run(pc2, svc2, PdmOpKind.Burn));
        Assert.Equal([PdmStepState.NotDone, PdmStepState.Failed, PdmStepState.NotDone], States(svc2));
        Assert.Equal(0, pc2.All.Sum(d => pc2.CountSent(d.BaseId, MessageCommand.BurnParams)));

        // Burn with all three matching: the firmware's own "burn OK" answer from each board, one after another
        pc2.A2.Outputs[4].CurrentLimit = 6.5;
        Assert.Null(Run(pc2, svc2, PdmOpKind.Burn));
        Assert.Equal([PdmStepState.Ok, PdmStepState.Ok, PdmStepState.Ok], States(svc2));
        Assert.Equal([1, 1, 1], pc2.All.Select(d => pc2.CountSent(d.BaseId, MessageCommand.BurnParams)));
        Assert.Equal(3, pc2.Notes.Count(n => n.EndsWith("Burn Successful")));
    }

    // A2 stops answering after the run started (its CAN wires are cut just before its Write All goes out)
    [SimFact]
    public void PdmWriteAllStopsAtTheSilentBoard()
    {
        using var bus = new SimBus();
        var rig = Boot(bus);
        var svc = Service(rig);
        Assert.Null(Run(rig, svc, PdmOpKind.ReadAll));
        var before = Edited(rig);
        Edit(rig);

        var cut = false;
        rig.BeforeSend = f =>
        {
            if (cut || f.Id != 0x541 || f.Payload[0] != (byte)MessageCommand.WriteAll) return;
            bus.Cmd("LINK A2 off");
            cut = true;
        };
        Assert.Null(Run(rig, svc, PdmOpKind.WriteAll));
        Assert.True(cut);
        Assert.Equal([PdmStepState.Ok, PdmStepState.Failed, PdmStepState.NotDone], States(svc));
        Assert.StartsWith("no reply", svc.Ops.Results[1].Text);
        Assert.Equal("not written (run stopped at A2)", svc.Ops.Results[2].Text);
        Assert.Equal(0, rig.CountSent(0x580, MessageCommand.WriteAll));

        // with A2 back on the bus a fresh PC sees: A1 new values, A2 and B still the old ones
        rig.BeforeSend = null;
        bus.Cmd("LINK A2 on");
        var pc2 = new PdmRig(bus);
        pc2.Step(1500);
        Assert.Null(Run(pc2, Service(pc2), PdmOpKind.ReadAll));
        Assert.Equal([NewValues[0], before[1], before[2]], Edited(pc2));

        // and a board that is silent before the run: refused, with the board named
        bus.Cmd("LINK B off");
        pc2.Step(200);
        Thread.Sleep(600);                // FwDevice.Connected is wall-clock: 500 ms without a frame
        pc2.Step(100);                    // A1 and A2 are heard again, B is not
        Assert.Equal("B: offline.", Service(pc2).Start(PdmOpKind.WriteAll, true, pc2.Now));
    }
}
