using application.Services;
using domain.CustomPdm;
using domain.Enums;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// One-PDM editor phase 2b through the real UI code: PdmValues makes counters, math, levels, an other-board value, a
// keypad button, the starter interlock, the master retry and a CAN output frame on the PC (New PDM project), the
// /pdm Write All puts them on the three sim boards (real firmware logic, sim bridge), the output pins (PROFET IN) and
// the frames on the bus are checked; a second PC reads everything back in the same words.
// B OUT1 = counter of IN15 presses >= 2; OUT2 = math (B board temperature x 2) >= 100; OUT3 = keypad node 0x2A
// button 3; OUT4 = IN16 AND level (B board temperature >= 50); OUT5 = level of A1's board temperature (over CAN) >= 50;
// OUT6 = IN18, A1 OUT1 = IN2: both shed while IN17 (crank) is on; OUT7 = IN20, no retry, master retry IN19;
// OUT8 = IN21 with the fuel-pump preset (open-load 1 A), B's open-load flags sent on 0x6A0 every 100 ms.
public sealed class Editor2bPdm : IDisposable
{
    private SimBus? _bus;
    public SimBus Bus => _bus ?? throw new InvalidOperationException("not set up");
    public string Words1 = "", Words2 = "";
    public List<string> Log { get; } = [];

    private static string Words(PdmView v)
    {
        var m = PdmModel.Build(v);
        var w = m.Triggers.Where(t => t.Kind != PdmTriggerKind.None).Select(t => $"{t.Out.Number}: {t.Words}")
            .Concat(PdmValues.All(m).Select(f => $"{f.Main.Text}: {f.Words}"));
        return System.Text.RegularExpressions.Regex.Replace(string.Join("\n", w), " '[^']*'", "");   // names: project file only
    }

    private void Run(PdmRig rig, PdmOpsService svc, PdmOpKind op)
    {
        var t = rig.SimMs;
        Assert.Null(svc.Start(op, true, rig.Now));
        while (svc.Ops.Busy && rig.SimMs - t < 180000)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }
        Log.Add($"{op}: {string.Join(" | ", svc.Ops.Results.Select(r => $"{r.Role} {r.State}"))} ({rig.SimMs - t:F0} ms sim time)");
        Assert.All(svc.Ops.Results, r => Assert.Equal(PdmStepState.Ok, r.State));
    }

    public void SetUp()
    {
        if (_bus != null) return;
        _bus = new SimBus();
        var rig = new PdmRig(_bus, newPdm: true);
        rig.Step(1500);
        var svc = new PdmOpsService(rig.Mgr) { AutoTick = false };
        var v = svc.BuildView();
        var b = rig.B;
        var temp = PdmFactoryDefaults.BoardTempVar(b);
        Assert.Null(PdmValues.AddCounter(v, new PdmCounterSpec("B", PdmTerm.In(15), Max: 3), out var ci));
        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Level(new PdmThreshold(PdmFactoryDefaults.VarOf(b, b.Counters[ci]), true, 2, 1))));
        Assert.Null(PdmValues.AddMath(v, new PdmMathSpec("B", MathOp.Mul, temp, ConstB: 2), out var mi));
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Level(new PdmThreshold(PdmFactoryDefaults.VarOf(b, b.MathBlocks[mi]), true, 100, 90))));
        var kb = PdmValues.AddKeypadButton(v, "B", 0x2A, 3, out var why);
        Assert.Null(why);
        Assert.Null(PdmTriggers.Set(v, 19, PdmTriggerSpec.Input(PdmTerm.Of(PdmFactoryDefaults.CanInState(b, kb)))));
        Assert.Null(PdmValues.AddLevel(v, "B", new PdmThreshold(temp, true, 50, 45), out var lv));
        Assert.Null(PdmTriggers.Set(v, 20, PdmTriggerSpec.Logic(PdmLogicOp.And, PdmTerm.In(16), PdmTerm.Of(lv))));
        var rv = PdmValues.AddRemoteValue(v, "B", "A1", "A1_BoardTemp", out why);
        Assert.Null(why);
        Assert.Null(PdmTriggers.Set(v, 21, PdmTriggerSpec.Level(new PdmThreshold(PdmFactoryDefaults.CanInState(b, rv) + 1, true, 50, 45))));
        Assert.Null(PdmTriggers.Set(v, 22, PdmTriggerSpec.Input(PdmTerm.In(18))));
        Assert.Null(PdmTriggers.Set(v, 1, PdmTriggerSpec.Input(PdmTerm.In(2))));
        Assert.Null(PdmValues.SetStarter(v, PdmTerm.In(17), [22, 1]));
        Assert.Null(PdmTriggers.Set(v, 23, PdmTriggerSpec.Input(PdmTerm.In(20))));
        b.Outputs[6].ResetMode = ResetMode.None;                               // latches off at its first trip
        Assert.Null(PdmValues.SetRetry(v, PdmTerm.In(19)));
        Assert.Null(PdmTriggers.Set(v, 24, PdmTriggerSpec.Input(PdmTerm.In(21))));
        Assert.Null(PdmPresets.Apply(v, 24, PdmDeviceKind.FuelPump));
        Assert.Null(PdmValues.AddOpenLoadFrame(v, "B", 0x6A0, 100));
        foreach (var o in v.Outputs.Where(o => o.Number is 1 or >= 17)) o.Output.Enabled = true;
        foreach (var i in new[] { 2, 15, 16, 17, 18, 19, 20, 21 }) v.Inputs.Single(r => r.Number == i).Digital!.Enabled = true;
        Assert.Empty(PdmModel.Build(v).Problems);
        Words1 = Words(v);
        Log.Add(Words1);
        Run(rig, svc, PdmOpKind.WriteAll);
        var pc2 = PdmLiveSimTests.Boot(_bus);
        var svc2 = new PdmOpsService(pc2.Mgr) { AutoTick = false };
        Run(pc2, svc2, PdmOpKind.ReadAll);
        Words2 = Words(svc2.BuildView());
        foreach (var bd in new[] { "A1", "A2", "B" }) _bus.Cmd($"TEMP {bd} 30");
        _bus.Run(300);
    }

    public void In(string board, int i, bool on) => Bus.Cmd($"IN {board} {i} {(on ? "12v" : "gnd")}");
    public bool Pin(string board, int o) => Bus.Pin(board, o);

    public void Dispose() => _bus?.Dispose();
}

[Collection("sim")]
public class PdmEditor2bLiveSimTests(Editor2bPdm pdm, ITestOutputHelper output) : IClassFixture<Editor2bPdm>
{
    private Editor2bPdm P
    {
        get
        {
            pdm.SetUp();
            foreach (var l in pdm.Log) output.WriteLine(l);
            pdm.Log.Clear();
            return pdm;
        }
    }

    [SimFact]
    public void ValuesAreReadBackInTheSameWordsByASecondPc()
    {
        var p = P;
        Assert.Equal(p.Words1, p.Words2);
        Assert.Contains("B counter 1: counter: up on IN15, 0 to 3 (wraps)", p.Words2);
        Assert.Contains("20: IN16 AND level (B board temperature (C) on at 50 or more, off at 45 or less)", p.Words2);
        Assert.Contains("B starter block: starter interlock: while IN17 is on, outputs 22 are held off", p.Words2);
    }

    [SimFact]
    public void CounterCountsPressesAndALevelOnItSwitchesTheOutput()
    {
        var p = P;
        var seq = new List<string>();
        for (var k = 0; k < 4; k++)
        {
            p.In("B", 0, true); p.Bus.Run(80); p.In("B", 0, false); p.Bus.Run(80);
            seq.Add(p.Pin("B", 0) ? "1" : "0");
        }
        output.WriteLine("counter 1, 2, 3, 0 (wrap): OUT1 " + string.Join("", seq));
        Assert.Equal("0110", string.Join("", seq));
    }

    [SimFact]
    public void MathLevelsAndOtherBoardValuesFollowTheTemperatures()
    {
        var p = P;
        p.In("B", 1, true);
        var got = new List<string>();
        foreach (var (b, a1) in new[] { (30, 30), (55, 30), (47, 55), (40, 40) })
        {
            p.Bus.Cmd($"TEMP B {b}"); p.Bus.Cmd($"TEMP A1 {a1}"); p.Bus.Run(400);
            got.Add($"B {b} C / A1 {a1} C: math {(p.Pin("B", 1) ? 1 : 0)} and {(p.Pin("B", 3) ? 1 : 0)} A1 {(p.Pin("B", 4) ? 1 : 0)}");
        }
        p.In("B", 1, false);
        output.WriteLine(string.Join(" | ", got));
        Assert.Equal(["B 30 C / A1 30 C: math 0 and 0 A1 0", "B 55 C / A1 30 C: math 1 and 1 A1 0",
                      "B 47 C / A1 55 C: math 1 and 1 A1 1", "B 40 C / A1 40 C: math 0 and 0 A1 0"], got);  // 47 C: both still on (hysteresis)
        p.Bus.Cmd("TEMP B 30"); p.Bus.Cmd("TEMP A1 30");
    }

    [SimFact]
    public void KeypadButtonSwitchesItsOutputAndGoesOffWhenTheKeypadIsSilent()
    {
        var p = P;
        p.Bus.Cmd("T 1AA 0400000000"); p.Bus.Run(50);
        Assert.True(p.Pin("B", 2));
        p.Bus.Cmd("T 1AA 0000000001"); p.Bus.Run(50);
        Assert.False(p.Pin("B", 2));
        p.Bus.Cmd("T 1AA 0400000002"); p.Bus.Run(50);
        var t = p.Bus.Trace(1300, 0.5, [], "B:2");
        var off = t.Changes("B:2").Single() - t.Start;
        output.WriteLine($"keypad button 3 on, keypad silent: off after {off:F0} ms");
        Assert.InRange(off, 950, 1060);
    }

    [SimFact]
    public void StarterInterlockHoldsTheChosenOutputsOffWhileCranking()
    {
        var p = P;
        p.In("B", 3, true); p.In("A1", 1, true); p.Bus.Run(300);
        Assert.True(p.Pin("B", 5) && p.Pin("A1", 0));
        p.In("B", 2, true); p.Bus.Run(300);                                    // crank
        var during = (p.Pin("B", 5), p.Pin("A1", 0), p.Pin("B", 0));
        p.In("B", 2, false); p.Bus.Run(300);
        output.WriteLine($"cranking: B OUT6 {during.Item1}, A1 OUT1 {during.Item2} (over CAN); after: {p.Pin("B", 5)} {p.Pin("A1", 0)}");
        Assert.False(during.Item1 || during.Item2);
        Assert.True(p.Pin("B", 5) && p.Pin("A1", 0));
        p.In("B", 3, false); p.In("A1", 1, false);
    }

    [SimFact]
    public void MasterRetryClearsALatchedFault()
    {
        var p = P;
        p.Bus.Cmd("LOAD B 6 20");                                               // 20 A > 15 A limit
        p.In("B", 5, true); p.Bus.Run(1600);                                    // past the 1 s inrush window
        var tripped = p.Pin("B", 6);
        p.Bus.Cmd("LOAD B 6 5"); p.Bus.Run(1500);
        var still = p.Pin("B", 6);
        p.In("B", 4, true); p.Bus.Run(100); p.In("B", 4, false); p.Bus.Run(200); // master retry pulse
        var back = p.Pin("B", 6);
        output.WriteLine($"OUT7 at 20 A: {(tripped ? "on" : "off (fault)")}, load gone: {(still ? "on" : "still off")}, after the retry pulse: {(back ? "on" : "off")}");
        Assert.False(tripped);
        Assert.False(still);
        Assert.True(back);
        p.In("B", 5, false); p.Bus.Cmd("LOAD B 6 0");
    }

    [SimFact]
    public void OpenLoadFlagsGoOutInOneCanFrame()
    {
        var p = P;
        p.Bus.Cmd("LOAD B 7 0");
        p.In("B", 6, true);                                                     // OUT8 on, nothing connected
        p.Bus.Run(900);
        var frames = p.Bus.Run(300).Where(f => f.Id == 0x6A0).ToList();
        output.WriteLine($"0x6A0 frames in 300 ms: {frames.Count}, data {string.Join(" ", frames.Select(f => Convert.ToHexString(f.Data)))}");
        Assert.InRange(frames.Count, 2, 4);                                     // every 100 ms
        Assert.All(frames, f => Assert.Equal(0x80, f.Data[0] & 0x80));          // bit 7 = OUT8 open load
        p.Bus.Cmd("LOAD B 7 5"); p.Bus.Run(300);
        Assert.Equal(0, p.Bus.Run(300).Last(f => f.Id == 0x6A0).Data[0] & 0x80); // a load: flag clear
        p.In("B", 6, false); p.Bus.Cmd("LOAD B 7 0");
    }
}
