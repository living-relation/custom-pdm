using application.Services;
using domain.CustomPdm;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// carconfig: the ST185 install steps on the simulated boards (real firmware logic): "Load the ST185 car config" on
// fresh boards, Write All, Burn, a power cycle of all three boards, then a fresh PC (app restart) reads every function
// back in the same words; then the outputs act on the bench: key on, head lamps, the ECU letting go of its main relay.
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

        // on the bench (inputs and outputs count from 0 in the bridge; carsim 2026-11-23 map): key on = the ignition on B IN2
        // and the EFI main relay output on A1 IN5 -> CAN-Lambda and power windows (B), CSB3 and cluster (A1, Bus 2 = IN5)
        bus.Cmd("IN B 1 12v");
        bus.Cmd("IN A1 4 12v");
        bus.Run(500);
        Assert.Equal((true, true, true, true), (bus.Pin("A1", 6), bus.Pin("A1", 7), bus.Pin("B", 4), bus.Pin("B", 0)));
        // the ECU's own loads are not on the PDM: B OUT2 / OUT3 and A1 OUT6 stay spare (off)
        Assert.Equal((false, false, false), (bus.Pin("B", 1), bus.Pin("B", 2), bus.Pin("A1", 5)));

        // head lamps: low (A1 OUT1) and high (A1 OUT2) on their switches to ground; DRL off with the head lamps on
        bus.Cmd("IN A1 2 gnd");   // DRL switch on
        bus.Run(300);
        Assert.Equal((true, false, false), (bus.Pin("A1", 2), bus.Pin("A1", 0), bus.Pin("A1", 1)));
        bus.Cmd("IN A1 0 gnd");
        bus.Cmd("IN A1 1 gnd");
        bus.Run(300);
        Assert.Equal((false, true, true), (bus.Pin("A1", 2), bus.Pin("A1", 0), bus.Pin("A1", 1)));

        // the ECU lets go of its main relay (end of its after-run): CSB3 and cluster off with IN5, the key-off functions stay
        bus.Cmd("IN A1 4 open down");
        bus.Run(300);
        Assert.Equal((false, false), (bus.Pin("A1", 6), bus.Pin("A1", 7)));
    }
}
