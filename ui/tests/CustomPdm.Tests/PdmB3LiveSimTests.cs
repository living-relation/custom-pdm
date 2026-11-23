using application.Services;
using domain.Common;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// Route B phase B3 against the real firmware logic (all three boards on one bus, one real DeviceManager):
// "New PDM" = our factory defaults (proven param by param), the linked settings through the /pdm Write All, the fan
// thresholds acting on the boards, and base-ID changes.
[Collection("sim")]
public class PdmB3LiveSimTests(ITestOutputHelper output)
{
    private static PdmRig BootNew(SimBus bus)
    {
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        return rig;
    }

    private static List<(string Name, int Index, int Sub, string Raw)> Raw(FwDevice d) =>
        d.Params.Select(p => (p.Name, p.Index, p.SubIndex, Convert.ToHexString(ParamCodec.ToFrame(MessageCommand.Write, p, 0).Payload, 4, 4))).ToList();

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
    private static readonly PdmStepState[] AllOk = [PdmStepState.Ok, PdmStepState.Ok, PdmStepState.Ok];

    // u2a: every param of a New PDM project equals what fresh boards hold (the firmware's built-in defaults)
    [SimFact]
    public void NewPdmEqualsFreshBoardsParamByParam()
    {
        using var bus = new SimBus();
        var rig = BootNew(bus);
        foreach (var dev in rig.All)
        {
            // 1. before any read: the board's CRC over its whole config equals the PC's
            dev.ConfigMismatch = true;
            rig.Mgr.CheckConfig(dev.Guid);
            Assert.True(rig.RunUntil(() => !dev.ConfigMismatch, 2000), $"{dev.Name}: config CRC of New PDM != board");

            // 2. then a Read All, param by param
            var pc = Raw(dev);
            var stock = Raw(StockTests.MakeDevice(dev.DeviceTypeId, dev.BaseId));
            Assert.True(PdmLiveSimTests.ReadOne(rig, dev), $"{dev.Name}: Read All");
            var board = Raw(dev);
            var differ = pc.Zip(board).Where(p => p.First != p.Second).Select(p => $"{p.First.Name}: PC {p.First.Raw} board {p.Second.Raw}").ToList();
            var fromStock = stock.Zip(board).Count(p => p.First.Raw != p.Second.Raw);
            output.WriteLine($"{dev.Name}: {pc.Count} params, New PDM differs in {differ.Count}; a hand-added device differs in {fromStock}");
            Assert.Empty(differ);
            Assert.True(fromStock >= 30, $"{dev.Name}: only {fromStock} params differ from stock PC defaults");
        }
    }

    // w3a + the UI check rule: fresh boards hold each output's rating as their current limit (the fan 1 A), so after a
    // Read All into hand-added devices (stock PC defaults, 20 A) /pdm shows no "above rating" warning
    [SimFact]
    public void FreshBoardsReadShowNoRatingWarning()
    {
        using var bus = new SimBus();
        var rig = PdmLiveSimTests.Boot(bus);
        var svc = Service(rig);
        Assert.Equal(20, svc.BuildView().OverRating.Count); // before the read: 20 A on the 7.5 A and 15 A outputs
        Assert.Null(Run(rig, svc, PdmOpKind.ReadAll));
        Assert.Equal(AllOk, States(svc));
        var view = svc.BuildView();
        double[] want = [.. Enumerable.Repeat(7.5, 9), 1.0, .. Enumerable.Repeat(7.5, 6), 31.0, 31.0, 31.0, 31.0, 15.0, 15.0, 15.0, 15.0];
        Assert.Equal(want, view.Outputs.Select(o => o.Output.CurrentLimit));
        Assert.All(view.Outputs, o => Assert.Equal(o.Number == 10 ? 2.0 : 50.0, o.Output.InrushCurrentLimit));
        Assert.Empty(view.OverRating);
        Assert.All(view.Outputs, o => Assert.Null(o.RatingWarning));
    }

    // The /pdm flow on a New PDM project: shared temp limits + fan thresholds, Write All with no Read All, then a
    // fresh PC (as after an app restart) reads the same values back from all three boards
    [SimFact]
    public void NewPdmLinkedSettingsWriteAllAndReadBack()
    {
        using var bus = new SimBus();
        var rig = BootNew(bus);
        var svc = Service(rig);
        var view = svc.BuildView();
        Assert.Null(PdmThermal.Set(view, new PdmHotSpotLimits(116, 123, 4, 7))); // 95 / 102 on A and B (21 K each, hwtemp)
        Assert.Null(PdmLinked.SetFanThresholds(rig.A2, new PdmFanThresholds(50, 44)));
        Assert.Null(Run(rig, svc, PdmOpKind.WriteAll));
        Assert.Equal(AllOk, States(svc));
        Assert.All(rig.All, d => Assert.False(d.FullReadDone)); // written without a Read All
        Assert.Equal(0, rig.All.Sum(d => rig.CountSent(d.BaseId, MessageCommand.BurnParams)));

        var pc2 = PdmLiveSimTests.Boot(bus);            // hand-added devices: stock PC defaults until read
        var svc2 = Service(pc2);
        Assert.Null(Run(pc2, svc2, PdmOpKind.ReadAll));
        Assert.Equal(AllOk, States(svc2));
        var v2 = svc2.BuildView();
        Assert.All(pc2.All, d => Assert.Equal(new PdmTempLimits(95, 102, 4, 7), PdmTempLimits.Of(d)));
        Assert.Equal(new PdmHotSpotLimits(116, 123, 4, 7), PdmThermal.Current(v2));
        Assert.Equal(new PdmFanThresholds(50, 44), PdmLinked.FanThresholds(pc2.A2));
        Assert.Empty(PdmLinked.FanRemoteIdProblems(v2));
    }

    private static bool FanOn(PdmRig rig) => rig.A2.Outputs[PdmFactoryDefaults.FanOutput].State == OutState.On;

    private static bool FanAt(SimBus bus, PdmRig rig, double a1, double a2, double b)
    {
        bus.Cmd($"TEMP A1 {a1}");
        bus.Cmd($"TEMP A2 {a2}");
        bus.Cmd($"TEMP B {b}");
        for (var i = 0; i < 14; i++) rig.Step(); // 700 ms: 250 ms sensor period, cyclic status
        return FanOn(rig);
    }

    // The 6 params really move the fan: on 50 / off 44 on A2's own sensor and on A1 / B over CAN
    [SimFact]
    public void FanFollowsTheNewThresholdsOnTheBoards()
    {
        using var bus = new SimBus();
        var rig = BootNew(bus);
        var svc = Service(rig);
        Assert.Null(PdmLinked.SetFanThresholds(rig.A2, new PdmFanThresholds(50, 44)));
        Assert.Null(Run(rig, svc, PdmOpKind.WriteAll));
        Assert.Equal(AllOk, States(svc));

        Assert.False(FanAt(bus, rig, 30, 49, 30));   // old "on" (45) no longer switches it
        Assert.True(FanAt(bus, rig, 30, 50, 30));    // A2 own sensor
        Assert.True(FanAt(bus, rig, 30, 45, 30));    // latch: stays on above 44
        Assert.False(FanAt(bus, rig, 30, 44, 30));   // off at 44
        Assert.True(FanAt(bus, rig, 50.5, 30, 30));  // A1 over CAN
        Assert.False(FanAt(bus, rig, 44, 30, 30));
        Assert.True(FanAt(bus, rig, 30, 30, 51));    // B over CAN
        Assert.True(FanAt(bus, rig, 30, 30, 45));
        Assert.False(FanAt(bus, rig, 30, 30, 43));
    }

    // Base IDs: A1 moves down, B moves up (the stock FwDevice ID range used to stay at the old ID). A2's fan inputs
    // follow, reach A2 with Write All, and the fan reacts to A1 / B on their new IDs.
    [SimFact]
    public void BaseIdChangesKeepTheFanLinks()
    {
        using var bus = new SimBus();
        var rig = BootNew(bus);
        var svc = Service(rig);

        var (refused, done) = svc.ChangeBaseId("A1", 0x400, true);
        Assert.Null(refused);
        output.WriteLine(string.Join("; ", done));
        (refused, done) = svc.ChangeBaseId("B", 0x600, true);
        Assert.Null(refused);
        output.WriteLine(string.Join("; ", done));
        rig.Step(1000);
        Assert.Equal([0x400, 0x540, 0x600], rig.All.Select(d => d.BaseId));
        Assert.All(rig.All, d => Assert.True(d.Connected, $"{d.Name} not connected after the move"));
        Assert.Equal([0x402, 0x402, 0x602, 0x602], rig.A2.CanInputs.Skip(24).Take(4).Select(c => c.Id));
        Assert.Empty(PdmLinked.FanRemoteIdProblems(svc.BuildView()));
        Assert.Equal("A1 must stay below A2 (0x540): the PDM page tells the two A boards apart by base ID.",
            svc.ChangeBaseId("A1", 0x580, true).Refused);

        // Write All (A2 gets the new fan IDs; the moved boards answer on their new IDs), then the fan reacts
        Assert.Null(Run(rig, svc, PdmOpKind.WriteAll));
        Assert.Equal(AllOk, States(svc));
        Assert.True(FanAt(bus, rig, 50, 30, 30));
        Assert.False(FanAt(bus, rig, 30, 30, 30));
        Assert.True(FanAt(bus, rig, 30, 30, 50));
        Assert.False(FanAt(bus, rig, 30, 30, 30));

        // Read All of the three boards on their new IDs: A2 hands back the new fan IDs
        Assert.Null(Run(rig, svc, PdmOpKind.ReadAll));
        Assert.Equal(AllOk, States(svc));
        Assert.Equal([0x402, 0x402, 0x602, 0x602], rig.A2.CanInputs.Skip(24).Take(4).Select(c => c.Id));
        Assert.Empty(PdmLinked.FanRemoteIdProblems(svc.BuildView()));

        // a fresh PC with the new IDs reads the same: the board kept them (running config, not burned)
        var pc2 = new PdmRig(bus);
        pc2.A1.BaseId = 0x400;
        pc2.B.BaseId = 0x600;
        pc2.Step(1500);
        var svc2 = Service(pc2);
        Assert.Null(Run(pc2, svc2, PdmOpKind.ReadAll));
        Assert.Equal(AllOk, States(svc2));
        Assert.Equal([0x402, 0x402, 0x602, 0x602], pc2.A2.CanInputs.Skip(24).Take(4).Select(c => c.Id));
    }
}
