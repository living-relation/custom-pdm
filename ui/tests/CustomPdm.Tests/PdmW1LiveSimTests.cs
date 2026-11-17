using application.Services;
using domain.CustomPdm;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// w1 recipe through the real UI code: PdmLinks makes the links on the PC, the /pdm Write All + Burn put them on the
// boards (real firmware logic, sim bridge), then the boards are power-cycled (config kept in FRAM) and the output
// pins (PROFET IN, ground truth) are traced in 0.5 ms steps.
// Output board Q = B, source board P = A1 (its msg 37 = 0x527), all on A1 IN1; C = B IN1 (the example condition).
// B OUT1 off, OUT2 hold, OUT3 on, OUT4 on critical, OUT5 condition, OUT6 condition critical;
// B OUT7 on from A2 IN1 (a second source board, its own ALIVE / SEEN / LOST).
[Collection("sim")]
public class PdmW1LiveSimTests(ITestOutputHelper output)
{
    private const int Msg37A1 = 0x500 + 0x27;
    private static readonly (int Out, PdmLinkLoss Loss, bool Crit)[] Plan =
        [(17, PdmLinkLoss.Off, false), (18, PdmLinkLoss.Hold, false), (19, PdmLinkLoss.On, false), (20, PdmLinkLoss.On, true),
         (21, PdmLinkLoss.Condition, false), (22, PdmLinkLoss.Condition, true)];
    private static readonly string[] Names = ["off", "hold", "on", "on-crit", "cond", "cond-crit", "on-A2"];
    private static readonly string[] Pins = ["B:0", "B:1", "B:2", "B:3", "B:4", "B:5", "B:6"];
    private static readonly string[] NonCrit = ["B:0", "B:1", "B:2", "B:4"];
    private static readonly string[] Crit = ["B:3", "B:5"];

    private static PdmOpsService Service(PdmRig rig) => new(rig.Mgr) { AutoTick = false };

    private void Run(PdmRig rig, PdmOpsService svc, PdmOpKind op)
    {
        var t = rig.SimMs;
        Assert.Null(svc.Start(op, true, rig.Now));
        while (svc.Ops.Busy && rig.SimMs - t < 120000)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }
        output.WriteLine($"{op}: {string.Join(" | ", svc.Ops.Results.Select(r => $"{r.Role} {r.State}"))} ({rig.SimMs - t:F0} ms sim time)");
        Assert.All(svc.Ops.Results, r => Assert.Equal(PdmStepState.Ok, r.State));
    }

    private static void In(SimBus bus, string board, int i, bool on) => bus.Cmd($"IN {board} {i} {(on ? "12v" : "gnd")}");

    // the links made through PdmLinks, written and burnt on the three sim boards
    private (SimBus Bus, string Links) Prepare()
    {
        var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        var svc = Service(rig);
        var v = svc.BuildView();
        var c = PdmFactoryDefaults.VarOf(rig.B, rig.B.DigitalInputs[0]);
        foreach (var (o, loss, crit) in Plan)
            Assert.Null(PdmLinks.Add(v, 1, o, loss, crit, loss == PdmLinkLoss.Condition ? c : 0));
        Assert.Null(PdmLinks.Add(v, 8, 23, PdmLinkLoss.On));
        foreach (var o in v.Outputs.Where(o => o.Number is >= 17 and <= 23)) o.Output.Enabled = true;
        foreach (var i in new[] { 1, 8, 15 }) v.Inputs.Single(r => r.Number == i).Digital!.Enabled = true;
        var links = PdmLinksTests.Text(v);
        output.WriteLine(links);
        output.WriteLine(PdmLinks.Slots(v).Single(s => s.Board == "B").Summary);
        Run(rig, svc, PdmOpKind.WriteAll);
        Run(rig, svc, PdmOpKind.Burn);

        // an app restart: a fresh PC reads the same links back from the boards
        var pc2 = PdmLiveSimTests.Boot(bus);
        var svc2 = Service(pc2);
        Run(pc2, svc2, PdmOpKind.ReadAll);
        Assert.Equal(links, PdmLinksTests.Text(svc2.BuildView()));
        Assert.Empty(PdmLinks.OldLinks(svc2.BuildView()));
        return (bus, links);
    }

    private string Show(SimTrace t, double t0) => string.Join(", ", Pins.Select((p, i) =>
        $"{Names[i]} {string.Join("/", t.Edges[p].Select(e => $"{(e.On ? "+" : "-")}{e.T - t0:F1}"))}"));

    [SimFact]
    public void StartUpWaitsForTheFirstFrameExceptCriticalOutputs()
    {
        var (bus, _) = Prepare();
        using var _bus = bus;
        foreach (var (b, i) in new[] { ("A1", 0), ("A2", 0), ("B", 0) }) In(bus, b, i, true); // P input ON, C ON
        bus.Run(500);

        // (1) P silent through power-up and past the 1 s time-out, then it sends
        bus.Cmd("LINK A1 off");
        var t0 = bus.Restart("A1", "B");
        var silent = bus.Trace(1500, 0.5, [Msg37A1], Pins);
        bus.Cmd("LINK A1 on");
        var back = bus.Trace(800, 0.5, [Msg37A1], Pins);
        var first = back.Frames[Msg37A1].First;
        output.WriteLine($"P silent 1.5 s: {Show(silent, t0)} | first frame at {first - t0:F1} ms: {Show(back, t0)}");
        Assert.False(silent.Frames.ContainsKey(Msg37A1));
        Assert.All(NonCrit, p => Assert.Equal(0, silent.OnMs(p, t0, silent.End) + back.OnMs(p, back.Start, first))); // no blip before the first frame
        foreach (var p in Crit)
        {
            var on = Assert.Single(silent.Changes(p)) - t0;  // ON once, from power-up (main waits 500 ms), and stays
            Assert.InRange(on, 495, 520);
            Assert.Empty(back.Changes(p));
        }
        Assert.InRange(silent.Changes("B:6").Single() - t0, 495, 720);       // A2 keeps sending: on after B's start
        Assert.All(Pins, p => Assert.True(back.At(p, first + 120), $"{p} follows P's input (ON) 120 ms after the first frame"));
        Assert.All(NonCrit, p => Assert.InRange(back.Changes(p).Single() - first, 0, 30));

        // (2) key on: both boards power up together, P input ON: non-critical ON at the first frame, critical no dropout
        var t1 = bus.Restart("A1", "B");
        var keyOn = bus.Trace(1500, 0.5, [Msg37A1], Pins);
        var f1 = keyOn.Frames[Msg37A1].First;
        output.WriteLine($"key on, P input ON: first frame at {f1 - t1:F1} ms: {Show(keyOn, t1)}");
        Assert.All(NonCrit, p => Assert.Equal(0, keyOn.OnMs(p, t1, f1)));
        Assert.All(NonCrit, p => Assert.InRange(Assert.Single(keyOn.Changes(p)) - f1, 0, 30));
        Assert.All(Crit, p => Assert.InRange(Assert.Single(keyOn.Changes(p)) - t1, 495, 520));

        // (3) key on, P input OFF: non-critical never ON; critical ON from power-up until P's first frame says OFF
        In(bus, "A1", 0, false);
        bus.Run(200);
        var t2 = bus.Restart("A1", "B");
        var keyOff = bus.Trace(1500, 0.5, [Msg37A1], Pins);
        var f2 = keyOff.Frames[Msg37A1].First;
        output.WriteLine($"key on, P input OFF: first frame at {f2 - t2:F1} ms: {Show(keyOff, t2)}");
        Assert.All(NonCrit, p => Assert.Equal(0, keyOff.OnMs(p, t2, keyOff.End)));
        foreach (var p in Crit)
        {
            var ch = keyOff.Changes(p);
            Assert.Equal(2, ch.Count);
            Assert.InRange(ch[0] - t2, 495, 520);
            Assert.InRange(ch[1] - f2, 0, 30);
        }
    }

    [SimFact]
    public void LossActsPerModeWithOneCleanChange()
    {
        var (bus, _) = Prepare();
        using var _bus = bus;
        In(bus, "A2", 0, true);
        foreach (var (pOn, cOn) in new[] { (false, true), (true, false) })
        {
            In(bus, "A1", 0, pOn);
            In(bus, "B", 0, cOn);
            bus.Run(500);
            var pre = bus.Trace(300, 0.5, [Msg37A1], Pins);
            Assert.All(Plan.Select((_, i) => Pins[i]), p => Assert.Equal(pOn, pre.At(p, pre.End)));
            var last = pre.Frames[Msg37A1].Last;
            bus.Cmd("LINK A1 off");
            var loss = bus.Trace(2500, 0.5, [Msg37A1], Pins);
            bus.Cmd("LINK A1 on");
            var after = bus.Trace(600, 0.5, [Msg37A1], Pins);
            output.WriteLine($"P input {(pOn ? "ON" : "OFF")}, C {(cOn ? "ON" : "OFF")}, last frame {last:F1}: {Show(loss, last)}");
            bool[] want = [false, pOn, true, true, cOn, cOn, true]; // off, hold, on, on-crit, cond, cond-crit, on-A2 (A2 still sends: its input)
            for (var i = 0; i < Pins.Length; i++)
            {
                var ch = loss.Changes(Pins[i]);
                Assert.True(loss.At(Pins[i], loss.End) == want[i], $"{Names[i]} during the loss");
                if (i == 6 || want[i] == pOn) Assert.Empty(ch); // no blip where nothing changes
                else Assert.InRange(Assert.Single(ch) - last, 850, 1100); // one clean change at the 1 s time-out
            }
            Assert.All(Plan.Select((_, i) => Pins[i]), p => Assert.Equal(pOn, after.At(p, after.End))); // back to P's input
        }
    }
}
