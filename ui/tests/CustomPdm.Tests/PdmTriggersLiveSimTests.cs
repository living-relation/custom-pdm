using application.Services;
using domain.CustomPdm;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// One-PDM editor phase 1 through the real UI code: PdmTriggers sets the triggers on the PC (New PDM project), the
// /pdm Write All puts them on the three sim boards (real firmware logic, sim bridge), the output pins (PROFET IN,
// ground truth) follow the inputs; a second PC (app restart) reads the same triggers back in words.
// B OUT1 = IN15 AND NOT IN16, OUT2 = IN16 OR IN17, OUT3 = NOT (IN15 OR IN16), OUT4 = IN27 voltage on >= 3000 mV /
// off <= 2000 mV, OUT5 = IN17 on-delay 500 ms, OUT6 = IN18 flashing 200 / 200 ms, OUT7 = IN1 (A1) AND IN15;
// A1 OUT1 = NOT IN15 (B, over CAN).
[Collection("sim")]
public class PdmTriggersLiveSimTests(ITestOutputHelper output)
{
    private static PdmOpsService Service(PdmRig rig) => new(rig.Mgr) { AutoTick = false };

    private void Run(PdmRig rig, PdmOpsService svc, PdmOpKind op)
    {
        var t = rig.SimMs;
        Assert.Null(svc.Start(op, true, rig.Now));
        while (svc.Ops.Busy && rig.SimMs - t < 180000)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }
        output.WriteLine($"{op}: {string.Join(" | ", svc.Ops.Results.Select(r => $"{r.Role} {r.State}"))} ({rig.SimMs - t:F0} ms sim time)");
        Assert.All(svc.Ops.Results, r => Assert.Equal(PdmStepState.Ok, r.State));
    }

    private static string Words(PdmView v) =>
        string.Join("\n", PdmModel.Build(v).Triggers.Where(t => t.Kind != PdmTriggerKind.None).Select(t => $"{t.Out.Number}: {t.Words}"));

    private static void In(SimBus bus, string board, int i, bool on) => bus.Cmd($"IN {board} {i} {(on ? "12v" : "gnd")}");

    private string Pins(SimBus bus) => string.Join("", Enumerable.Range(0, 7).Select(o => bus.Pin("B", o) ? '1' : '0')) + "|" + (bus.Pin("A1", 0) ? '1' : '0');

    [SimFact]
    public void TriggersBuiltOnThePdmPageSwitchTheOutputsOnTheBoards()
    {
        using var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        var svc = Service(rig);
        var v = svc.BuildView();
        var b = rig.B;
        var mv = PdmFactoryDefaults.VarOf(b, b.AnalogInputs[0]) + 1;
        var plan = new (int Out, PdmTriggerSpec Spec)[]
        {
            (17, PdmTriggerSpec.Logic(PdmLogicOp.And, PdmTerm.In(15), PdmTerm.In(16, true))),
            (18, PdmTriggerSpec.Logic(PdmLogicOp.Or, PdmTerm.In(16), PdmTerm.In(17))),
            (19, PdmTriggerSpec.Logic(PdmLogicOp.Nor, PdmTerm.In(15), PdmTerm.In(16))),
            (20, PdmTriggerSpec.Level(new PdmThreshold(mv, true, 3000, 2000))),
            (21, PdmTriggerSpec.Input(PdmTerm.In(17)).WithTimer(PdmTimerKind.OnDelay, 500)),
            (22, PdmTriggerSpec.Input(PdmTerm.In(18)).WithFlash(200, 200)),
            (23, PdmTriggerSpec.Logic(PdmLogicOp.And, PdmTerm.In(1), PdmTerm.In(15))),
            (1, PdmTriggerSpec.Input(PdmTerm.In(15, true)))
        };
        foreach (var (o, s) in plan) Assert.Null(PdmTriggers.Set(v, o, s));
        foreach (var o in v.Outputs.Where(o => plan.Any(p => p.Out == o.Number))) o.Output.Enabled = true;
        foreach (var i in new[] { 1, 15, 16, 17, 18 }) v.Inputs.Single(r => r.Number == i).Digital!.Enabled = true;
        b.AnalogInputs[0].Enabled = true;
        var words = Words(v);
        output.WriteLine(words);
        Assert.Empty(PdmModel.Build(v).Problems);
        output.WriteLine(string.Join("\n", v.Boards.Select(x => PdmModel.Build(v).Use(x.Role).Summary)));
        Run(rig, svc, PdmOpKind.WriteAll);

        // AND / OR / NOR / NOT, same board and across boards
        bus.Cmd("AN B 0");
        bus.Run(300);
        Assert.Equal("0010000|1", Pins(bus));                  // all off: NOR on; A1 OUT1 = NOT IN15 (B) on
        In(bus, "B", 0, true); bus.Run(200);
        Assert.Equal("1000000|0", Pins(bus));                  // IN15: AND NOT on, NOR off, A1 OUT1 off over CAN
        In(bus, "B", 1, true); bus.Run(200);
        Assert.Equal("0100000|0", Pins(bus));                  // + IN16: AND NOT off, OR on
        In(bus, "A1", 0, true); bus.Run(300);
        Assert.Equal("0100001|0", Pins(bus));                  // + IN1 on A1: OUT7 = IN1 AND IN15 on (over CAN)
        In(bus, "B", 0, false); bus.Run(200);
        Assert.Equal("0100000|1", Pins(bus));
        In(bus, "B", 1, false); In(bus, "A1", 0, false); bus.Run(300);
        Assert.Equal("0010000|1", Pins(bus));

        // threshold with hysteresis on the analog input (mV)
        var seq = new List<string>();
        foreach (var volts in new[] { 2.5, 3.1, 2.5, 1.9, 2.5, 3.2 })
        {
            bus.Cmd(FormattableString.Invariant($"AN B {volts}"));
            bus.Run(100);
            seq.Add($"{volts}:{(bus.Pin("B", 3) ? 1 : 0)}");
        }
        output.WriteLine("threshold: " + string.Join(" ", seq));
        Assert.Equal(["2.5:0", "3.1:1", "2.5:1", "1.9:0", "2.5:0", "3.2:1"], seq);

        // on-delay 500 ms (input debounce 20 ms)
        In(bus, "B", 2, true);
        var tr = bus.Trace(800, 0.5, [], "B:4", "B:1");
        var on = Assert.Single(tr.Changes("B:4")) - tr.Start;
        output.WriteLine($"on-delay: OUT5 on {on:F1} ms after IN17, OUT2 (no delay) {tr.Changes("B:1").Single() - tr.Start:F1} ms");
        Assert.InRange(on, 500, 540);
        Assert.InRange(tr.Changes("B:1").Single() - tr.Start, 0, 40);
        In(bus, "B", 2, false);
        bus.Run(100);
        Assert.False(bus.Pin("B", 4));

        // flasher 200 / 200 ms
        In(bus, "B", 3, true);
        var fl = bus.Trace(1500, 0.5, [], "B:5");
        var edges = fl.Changes("B:5");
        var gaps = edges.Zip(edges.Skip(1), (a, c) => c - a).ToList();
        output.WriteLine($"flasher edges: {string.Join(" ", edges.Select(e => $"{e - fl.Start:F0}"))}");
        Assert.True(edges.Count >= 6, $"{edges.Count} edges");
        Assert.All(gaps, g => Assert.InRange(g, 195, 215));
        In(bus, "B", 3, false);
        bus.Run(100);
        Assert.False(bus.Pin("B", 5));

        // app restart: a fresh PC reads the same triggers back from the boards
        var pc2 = PdmLiveSimTests.Boot(bus);
        var svc2 = Service(pc2);
        Run(pc2, svc2, PdmOpKind.ReadAll);
        var v2 = svc2.BuildView();
        Assert.Equal(words, Words(v2));
        foreach (var (o, s) in plan) Assert.Equal(s, PdmTriggers.Of(PdmModel.Build(v2), o).Spec);
    }
}
