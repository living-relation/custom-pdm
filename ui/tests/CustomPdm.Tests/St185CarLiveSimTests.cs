using application.Services;
using domain.CustomPdm;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// carconfig: the ST185 install steps on the simulated boards (real firmware logic): "Load the ST185 car config" on
// fresh boards, Write All, Burn, a power cycle of all three boards, then a fresh PC (app restart) reads every function
// back in the same words; then the outputs act on the bench: key on, the ECU frame, ECU frames lost.
[Collection("sim")]
public class St185CarLiveSimTests(ITestOutputHelper output)
{
    private void Run(PdmRig rig, PdmOpsService svc, PdmOpKind op)
    {
        var t = rig.SimMs;
        Assert.Null(svc.Start(op, true, rig.Now));
        while (svc.Ops.Busy && rig.SimMs - t < 300000)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }
        output.WriteLine($"{op}: {string.Join(" | ", svc.Ops.Results.Select(r => $"{r.Role} {r.State}: {r.Text}"))} ({rig.SimMs - t:F0} ms sim time)");
        Assert.All(svc.Ops.Results, r => Assert.Equal(PdmStepState.Ok, r.State));
    }

    [SimFact]
    public async Task WriteAllBurnPowerCycleReadAllGivesBackEveryFunction()
    {
        using var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        var svc = new PdmOpsService(rig.Mgr, _ => true) { AutoTick = false };
        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
        Assert.Null(await PdmStarter.LoadAsync(St185CarTests.CarPath(), files, rig.Mgr, svc.Ops, "car config"));
        rig.Step(1000);
        var want = St185Car.Functions(svc.BuildView());

        Run(rig, svc, PdmOpKind.WriteAll);
        Run(rig, svc, PdmOpKind.Burn);
        output.WriteLine($"power cycle: {bus.Restart("A1", "A2", "B")} ms");

        var pc2 = PdmLiveSimTests.Boot(bus);
        var svc2 = new PdmOpsService(pc2.Mgr) { AutoTick = false };
        Run(pc2, svc2, PdmOpKind.ReadAll);
        var got = St185Car.Functions(svc2.BuildView());
        output.WriteLine(string.Join("\n", got));
        Assert.Equal(want, got);
        Assert.Empty(PdmModel.Build(svc2.BuildView()).Problems);

        // on the bench (inputs and outputs count from 0 in the bridge): key on -> CSB3, cluster (A1) and the
        // CAN-Lambda (B, A1's input over CAN); off until the ECU's first frame: pump, fans, EPS enable
        bus.Cmd("IN A1 4 12v");
        bus.Run(500);
        Assert.Equal((true, true, true), (bus.Pin("A1", 6), bus.Pin("A1", 7), bus.Pin("B", 4)));
        Assert.Equal((false, false, false, false), (bus.Pin("B", 2), bus.Pin("B", 0), bus.Pin("B", 1), bus.Pin("A1", 5)));

        // the ECU frame (placeholder 0x3F4): pump and EPS enable on, fans off
        for (var t = 0; t < 600; t += 50)
        {
            bus.Cmd("T 3F4 0100000100000000");
            bus.Run(50);
        }
        Assert.Equal((true, true, false, false), (bus.Pin("B", 2), bus.Pin("A1", 5), bus.Pin("B", 0), bus.Pin("B", 1)));

        // ECU frames lost: pump off and fans on after 1 s (fans after their 1 s soft start), EPS enable holds
        bus.Run(3000);
        Assert.Equal((false, true, true, true), (bus.Pin("B", 2), bus.Pin("A1", 5), bus.Pin("B", 0), bus.Pin("B", 1)));

        // head lamps: low (A1 OUT1) and high (A1 OUT2) on their switches to ground; DRL off with the head lamps on
        bus.Cmd("IN A1 2 gnd");   // DRL switch on
        bus.Run(300);
        Assert.Equal((true, false, false), (bus.Pin("A1", 2), bus.Pin("A1", 0), bus.Pin("A1", 1)));
        bus.Cmd("IN A1 0 gnd");
        bus.Cmd("IN A1 1 gnd");
        bus.Run(300);
        Assert.Equal((false, true, true), (bus.Pin("A1", 2), bus.Pin("A1", 0), bus.Pin("A1", 1)));
    }
}
