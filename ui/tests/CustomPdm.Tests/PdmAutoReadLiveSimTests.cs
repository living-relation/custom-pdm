using application.Services;
using domain.CustomPdm;
using domain.Enums;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// p2a against the real firmware logic: the three boards are read by themselves when they connect, one after another;
// a board with PC edits is asked about; a New PDM project is asked about instead of being read over.
[Collection("sim")]
public class PdmAutoReadLiveSimTests(ITestOutputHelper output)
{
    private readonly HashSet<string> _offline = [];

    private PdmOpsService Service(PdmRig rig) =>
        new(rig.Mgr, d => d.Connected && !_offline.Contains(d.Name)) { AutoTick = false, AutoRead = true };

    private static void Run(PdmRig rig, PdmOpsService svc, double ms)
    {
        var end = rig.SimMs + ms;
        while (rig.SimMs < end)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }
    }

    private static bool Settle(PdmRig rig, PdmOpsService svc, double maxMs = 60000)
    {
        var end = rig.SimMs + maxMs;
        Run(rig, svc, 200);
        while (svc.Ops.Busy && rig.SimMs < end) Run(rig, svc, 50);
        return !svc.Ops.Busy;
    }

    private static int Sent(PdmRig rig, MessageCommand cmd) => rig.All.Sum(d => rig.CountSent(d.BaseId, cmd));

    [SimFact]
    public void BoardsAreReadOnConnectAndEditsAreAskedAbout()
    {
        using var bus = new SimBus();
        var rig = PdmLiveSimTests.Boot(bus);
        var svc = Service(rig);
        var t = rig.SimMs;
        Assert.True(Settle(rig, svc));
        output.WriteLine($"read on connect: {string.Join(" | ", svc.Ops.Results.Select(r => $"{r.Role} {r.State}: {r.Text}"))} ({rig.SimMs - t:F0} ms sim time)");
        Assert.True(svc.Ops.LastOnConnect);
        Assert.Equal([PdmStepState.Ok, PdmStepState.Ok, PdmStepState.Ok], svc.Ops.Results.Select(r => r.State));
        Assert.All(rig.All, d => Assert.True(d.FullReadDone && !d.ConfigMismatch, d.Name));
        Assert.Equal([0x501, 0x541, 0x581], rig.Sent.Where(f => f.Payload[0] == (byte)MessageCommand.ReadAll).Select(f => f.Id));
        Assert.Null(svc.BlockedReason(PdmOpKind.WriteAll, svc.BuildView(), true));

        // edit A2 on the PC, A2 drops off and comes back: asked, not read
        var board = rig.A2.Outputs[4].CurrentLimit;
        rig.A2.Outputs[4].CurrentLimit = 6.5;
        _offline.Add("A2");
        Run(rig, svc, 300);
        _offline.Clear();
        Run(rig, svc, 2000);
        Assert.Equal(["A2"], svc.ConnectAsks().Select(b => b.Role));
        Assert.Equal(3, Sent(rig, MessageCommand.ReadAll));
        svc.AnswerConnect(rig.A2, PdmConnectAnswer.TakeBoard);
        Assert.True(Settle(rig, svc));
        Assert.Equal(4, Sent(rig, MessageCommand.ReadAll));
        Assert.Equal(board, rig.A2.Outputs[4].CurrentLimit);
        Assert.Empty(svc.ConnectAsks());
        Assert.Equal(0, Sent(rig, MessageCommand.WriteAll) + Sent(rig, MessageCommand.BurnParams));
    }

    [SimFact]
    public void NewPdmIsAskedAboutNotReadOver()
    {
        using var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        var svc = Service(rig);
        Run(rig, svc, 3000);
        Assert.Equal(PdmOps.Roles, svc.ConnectAsks().Select(b => b.Role));
        Assert.Equal(0, Sent(rig, MessageCommand.ReadAll));
        Assert.All(rig.All, d => Assert.True(d.CustomPdm!.FactoryNew && !d.FullReadDone));
        Assert.Equal(0, Sent(rig, MessageCommand.WriteAll) + Sent(rig, MessageCommand.BurnParams));
    }
}
