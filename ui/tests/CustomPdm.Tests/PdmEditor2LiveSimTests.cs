using application.Services;
using domain.CustomPdm;
using domain.Enums;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// One-PDM editor phase 2 through the real UI code: presets, ECU outputs, a fan curve, turn signals, the wiper and
// links with their own loss delay are set with PdmPresets / PdmEcu / PdmPwm / PdmFunctions / PdmLinks on the PC (New
// PDM project), the /pdm Write All puts them on the three sim boards (real firmware logic, sim bridge), and the output
// pins (PROFET IN, ground truth) are traced. A second PC (app restart) reads everything back in the same words.
// B: OUT1 radiator fan (ECU byte 0, on at loss 0.5 s, PWM duty curve from ECU coolant), OUT2 condenser fan (byte 1,
// on 0.5 s), OUT3 fuel pump (byte 2, off 1 s), OUT4 fuel pump (byte 3, overcurrent test), OUT5 / OUT6 links from A1 IN1
// (off 0.5 s / on 2 s), OUT7 / OUT8 wiper run / high (switches IN16-18, park cam IN19 = B IN5).
// A2: OUT1 / OUT3 turn signals left / right (IN8 / IN9 on A2, hazard IN15 on B over CAN).
public sealed class Editor2Pdm : IDisposable
{
    public const int Ecu = 0x3F4, Coolant = 0x3F5, Msg37A1 = 0x500 + 0x27;
    private SimBus? _bus;
    public SimBus Bus => _bus ?? throw new InvalidOperationException("not set up");
    public string Words1 = "", Words2 = "";
    public PdmView View2 = null!;
    public readonly byte[] Cmd = new byte[8];
    public double CoolantC = 20;
    public List<string> Log { get; } = [];

    // names live in the project file only (not on the boards): left out
    private static string Words(PdmView v) => System.Text.RegularExpressions.Regex.Replace(WithNames(v), " '[^']*'", "");

    private static string WithNames(PdmView v) =>
        string.Join("\n", PdmModel.Build(v).Triggers.Where(t => t.Kind != PdmTriggerKind.None).Select(t => $"{t.Out.Number}: {t.Words}")
            .Concat(v.Outputs.Where(o => o.Output.PwmEnabled).Select(o => $"{o.Number} PWM: {PdmPwm.Words(PdmModel.Build(v), o)}"))
            .Concat(PdmLinks.Links(v).Select(l => $"link {l.Out.Number}: {l.LossText}")));

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
        var cs = PdmEcu.AddValue(v, "B", "ECU coolant", Coolant, 0, 16, ByteOrder.LittleEndian, false, 0.1, 0, 1000, out var why);
        Assert.Null(why);
        var cool = PdmFactoryDefaults.CanInState(b, cs) + 1;
        Assert.Null(PdmEcu.Set(v, 17, Ecu, 0, PdmLinkLoss.On, 500));
        Assert.Null(PdmEcu.Set(v, 18, Ecu, 1, PdmLinkLoss.On, 500));
        Assert.Null(PdmEcu.Set(v, 19, Ecu, 2, PdmLinkLoss.Off, 1000));
        Assert.Null(PdmEcu.Set(v, 20, Ecu, 3, PdmLinkLoss.Off, 1000));
        foreach (var (o, k) in new[] { (17, PdmDeviceKind.RadiatorFan), (18, PdmDeviceKind.CondenserFan), (19, PdmDeviceKind.FuelPump), (20, PdmDeviceKind.FuelPump) })
            Assert.Null(PdmPresets.Apply(v, o, k));
        Assert.Null(PdmPwm.Set(v, 17, new PdmPwmSpec(true, 200, PdmDutyKind.Curve, Var: cool, Points: [(80, 0), (90, 40), (100, 100)],
            SoftStart: true, SoftStartMs: 1000, MinDuty: 20)));
        Assert.Null(PdmFunctions.SetTurn(v, new PdmTurnSpec(9, 11, PdmTerm.In(8), PdmTerm.In(9), PdmTerm.In(15))));
        Assert.Null(PdmFunctions.SetWiper(v, new PdmWiperSpec(23, 24, PdmTerm.In(16), PdmTerm.In(17), PdmTerm.In(18), 19, true, null, 3, 1500)));
        Assert.Null(PdmLinks.Add(v, 1, 21, PdmLinkLoss.Off, delayMs: 500));
        Assert.Null(PdmLinks.Add(v, 1, 22, PdmLinkLoss.On, delayMs: 2000));
        foreach (var o in v.Outputs.Where(o => o.Number is 9 or 11 or >= 17)) o.Output.Enabled = true;
        foreach (var i in new[] { 1, 8, 9, 15, 16, 17, 18, 19 }) v.Inputs.Single(r => r.Number == i).Digital!.Enabled = true;
        Assert.Empty(PdmModel.Build(v).Problems);
        Words1 = Words(v);
        Log.Add(Words1);
        Log.AddRange(v.Boards.Select(x => PdmModel.Build(v).Use(x.Role).Summary));
        Run(rig, svc, PdmOpKind.WriteAll);
        var pc2 = PdmLiveSimTests.Boot(_bus);
        var svc2 = new PdmOpsService(pc2.Mgr) { AutoTick = false };
        Run(pc2, svc2, PdmOpKind.ReadAll);
        View2 = svc2.BuildView();
        Words2 = Words(View2);
    }

    public void In(string board, int i, bool on) => Bus.Cmd($"IN {board} {i} {(on ? "12v" : "gnd")}");

    // the ECU's two frames: commands (0x3F4) and coolant x 10 (0x3F5 bytes 0-1)
    public void SendEcu()
    {
        var c = (int)Math.Round(CoolantC * 10);
        Bus.Cmd($"T {Ecu:X} {Convert.ToHexString(Cmd)}");
        Bus.Cmd($"T {Coolant:X} {c & 0xFF:X2}{c >> 8:X2}000000000000");
    }

    // run ms with the ECU sending every 50 ms; sample(t) after each step
    public void Pump(double ms, double step = 5, Action<double>? sample = null)
    {
        double t = 0, next = 0;
        while (t < ms)
        {
            if (t >= next) { SendEcu(); next += 50; }
            Bus.Run(step);
            t += step;
            sample?.Invoke(t);
        }
    }

    public void Dispose() => _bus?.Dispose();
}

[Collection("sim")]
public class PdmEditor2LiveSimTests(Editor2Pdm pdm, ITestOutputHelper output) : IClassFixture<Editor2Pdm>
{
    private Editor2Pdm P
    {
        get
        {
            pdm.SetUp();
            foreach (var l in pdm.Log) output.WriteLine(l);
            pdm.Log.Clear();
            return pdm;
        }
    }

    private static double Duty(SimTrace t, string pin, double from, double ms) => 100.0 * t.OnMs(pin, from, from + ms) / ms;

    [SimFact]
    public void EverythingIsReadBackInTheSameWordsByASecondPc()
    {
        var p = P;
        Assert.Equal(p.Words1, p.Words2);
        Assert.Contains("17: ECU 0x3F4 byte 0 = 1 (ECU only; on 0.5 s after the ECU frames stop; off until the first frame)", p.Words2);
        Assert.Contains("9: turn signal LEFT: IN8 or hazard IN15", p.Words2);
        Assert.Contains("23: wiper motor run", p.Words2);
        Assert.Contains("link 21: off 0.5 s after the message stops", p.Words2);
        Assert.Contains("link 22: on 2 s after the message stops", p.Words2);
        var v = p.View2;
        Assert.Equal(PdmDeviceKind.FuelPump, PdmPresets.KindOf(v, v.Outputs.Single(o => o.Number == 19)));  // matched from the board values
        Assert.Contains(PdmPresets.KindOf(v, v.Outputs.Single(o => o.Number == 18)), new[] { PdmDeviceKind.RadiatorFan, PdmDeviceKind.CondenserFan });
        Assert.Empty(PdmModel.Build(v).Problems);
    }

    [SimFact]
    public void FanCurveSetsThePwmDutyFromTheEcuCoolantTemperature()
    {
        var p = P;
        p.Cmd[0] = 1;
        var got = new List<string>();
        foreach (var (c, want) in new[] { (85.0, 20.0), (92.5, 55.0), (97.0, 82.0), (82.0, 20.0) })
        {
            p.CoolantC = c;
            p.Pump(1300, 50);                                      // past the 1 s soft start
            var t = p.Bus.Trace(60, 0.05, [], "B:0");
            var d = Duty(t, "B:0", t.Start + 5, 50);
            got.Add($"{c} C: {d:F1} %");
            Assert.InRange(d, want - 2, want + 2);
        }
        p.CoolantC = 105;
        p.Pump(300, 50);
        var full = p.Bus.Trace(60, 0.05, [], "B:0");
        got.Add($"105 C: {Duty(full, "B:0", full.Start + 5, 50):F1} %");
        output.WriteLine("fan curve (min 20 %): " + string.Join(", ", got));
        Assert.Empty(full.Changes("B:0"));
        Assert.True(full.At("B:0", full.Start + 10));
        p.Cmd[0] = 0;
        p.Pump(100, 50);
        Assert.False(p.Bus.Pin("B", 0));
    }

    [SimFact]
    public void TurnSignalsFlashInStepAndHazardsComeFromAnotherBoard()
    {
        var p = P;
        p.In("A2", 0, true);
        p.Bus.Run(100);
        var left = p.Bus.Trace(2100, 0.5, [], "A2:0", "A2:2");
        p.In("A2", 0, false);
        var e = left.Changes("A2:0");
        var gaps = e.Zip(e.Skip(1), (a, b) => b - a).ToList();
        output.WriteLine($"left: {e.Count} edges, gaps {string.Join(" ", gaps.Select(g => $"{g:F0}"))}");
        Assert.True(e.Count >= 4);
        Assert.All(gaps, g => Assert.InRange(g, 340, 365));
        Assert.Equal(0, left.OnMs("A2:2", left.Start, left.End));
        p.Bus.Run(800);
        p.In("B", 0, true);                                         // hazard on B IN1 = IN15, to A2 over CAN
        p.Bus.Run(200);
        var haz = p.Bus.Trace(2100, 0.5, [], "A2:0", "A2:2");
        p.In("B", 0, false);
        output.WriteLine($"hazard: left {string.Join(" ", haz.Changes("A2:0").Select(x => $"{x - haz.Start:F1}"))} | right {string.Join(" ", haz.Changes("A2:2").Select(x => $"{x - haz.Start:F1}"))}");
        Assert.True(haz.Changes("A2:0").Count >= 4);
        Assert.Equal(haz.Changes("A2:0"), haz.Changes("A2:2"));      // one flasher: same 0.5 ms sample
        p.Bus.Run(1200);
        Assert.False(p.Bus.Pin("A2", 0) || p.Bus.Pin("A2", 2));
    }

    // wiper motor + park cam (as s3 F8): one turn 1.0 s slow / 0.6 s fast, park contact closed in the first 10 %
    private sealed class Motor(Editor2Pdm p)
    {
        public double Pos = 0.02;
        public int Parks;
        private bool _park = true;
        public bool InPark => Pos % 1 < 0.1;

        public void Step(double ms)
        {
            p.Bus.Run(ms);
            bool run = p.Bus.Pin("B", 6), fast = p.Bus.Pin("B", 7);
            if (run) Pos += ms / (fast ? 600.0 : 1000.0);
            if (InPark != _park)
            {
                _park = InPark;
                if (_park) Parks++;
                p.In("B", 4, _park);
            }
        }
    }

    [SimFact]
    public void WiperRunsSlowParksOnTheCamAndPausesWhenIntermittent()
    {
        var p = P;
        p.In("B", 4, true);
        var m = new Motor(p);
        for (var i = 0; i < 40; i++) m.Step(5);
        p.In("B", 1, true);                                         // slow
        for (var i = 0; i < 500; i++) m.Step(5);                    // 2.5 s
        p.In("B", 1, false);
        var at = m.Pos;
        for (var i = 0; i < 400; i++) m.Step(5);
        output.WriteLine($"slow: {m.Parks} park passes, switched off at {at:F2} turns, stopped at {m.Pos:F2}");
        Assert.InRange(m.Parks, 2, 3);
        Assert.True(m.InPark, $"stopped at {m.Pos:F3}");
        Assert.InRange(m.Pos - at, 0, 1.0);
        Assert.False(p.Bus.Pin("B", 6));
        // intermittent: one wipe, a 1.5 s pause in park, the next wipe
        var starts = new List<double>();
        var was = false;
        p.In("B", 3, true);
        for (var i = 0; i < 1000; i++)
        {
            m.Step(5);
            var on = p.Bus.Pin("B", 6);
            if (on && !was) starts.Add(i * 5.0);
            was = on;
        }
        p.In("B", 3, false);
        for (var i = 0; i < 300; i++) m.Step(5);
        var gaps = starts.Zip(starts.Skip(1), (a, b) => b - a).ToList();
        output.WriteLine($"intermittent: wipe starts {string.Join(" ", starts)} ms, gaps {string.Join(" ", gaps)}");
        Assert.True(starts.Count >= 2);
        Assert.All(gaps, g => Assert.InRange(g, 1000 + 1400, 1000 + 1700));   // one turn + the 1.5 s pause
        Assert.True(m.InPark);
    }

    [SimFact]
    public void EcuOutputsActOnLossAfterTheirOwnDelay()
    {
        var p = P;
        (p.Cmd[1], p.Cmd[2]) = (0, 1);                              // condenser fan off, fuel pump on
        p.Pump(600, 50);
        Assert.False(p.Bus.Pin("B", 1));
        Assert.True(p.Bus.Pin("B", 2));
        var loss = p.Bus.Trace(1600, 0.5, [], "B:1", "B:2");        // the ECU stops (no frames)
        var last = loss.Start - 50;                                  // the last frame was sent 50 ms before (Pump step)
        var fanOn = loss.Changes("B:1").First() - last;              // then its soft start (PWM ramp, fan preset)
        var pumpOff = loss.Changes("B:2").Single() - last;
        output.WriteLine($"ECU silent: condenser fan ON after {fanOn:F1} ms (on at loss, 0.5 s), fuel pump OFF after {pumpOff:F1} ms (off at loss, 1 s)");
        Assert.InRange(fanOn, 500, 600);                            // first pulse of the 1 s soft start ramp
        // full on once the ramp is done: + one PWM period (board B fan soft start at 22 Hz, the freewheel-diode limit, fwsafety)
        Assert.Empty(loss.Changes("B:1").Where(x => x - last > 500 + 1000 + 1000.0 / 22 + 5));
        Assert.InRange(pumpOff, 1000, 1060);
        Assert.True(loss.At("B:1", loss.End));
        (p.Cmd[1], p.Cmd[2]) = (0, 0);
        p.Pump(200, 50);
        Assert.False(p.Bus.Pin("B", 1) || p.Bus.Pin("B", 2));
    }

    [SimFact]
    public void EachLinkActsOnLossAfterItsOwnDelay()
    {
        var p = P;
        foreach (var pOn in new[] { true, false })
        {
            p.In("A1", 0, pOn);
            p.Bus.Run(400);
            var pre = p.Bus.Trace(300, 0.5, [Editor2Pdm.Msg37A1], "B:4", "B:5");
            Assert.Equal(pOn, pre.At("B:4", pre.End));
            Assert.Equal(pOn, pre.At("B:5", pre.End));
            var last = pre.Frames[Editor2Pdm.Msg37A1].Last;
            p.Bus.Cmd("LINK A1 off");
            var loss = p.Bus.Trace(2600, 0.5, [], "B:4", "B:5");
            p.Bus.Cmd("LINK A1 on");
            p.Bus.Run(400);
            var (off, on) = (loss.Changes("B:4"), loss.Changes("B:5"));
            output.WriteLine($"A1 IN1 {(pOn ? "ON" : "OFF")}, A1 silent: OUT5 (off 0.5 s) {string.Join(" ", off.Select(x => $"{x - last:F1}"))} | OUT6 (on 2 s) {string.Join(" ", on.Select(x => $"{x - last:F1}"))} ms after the last frame");
            if (pOn)
            {
                Assert.InRange(Assert.Single(off) - last, 500, 520);  // off after 0.5 s
                Assert.Empty(on);                                      // on mode: stays on, no blip
            }
            else
            {
                Assert.Empty(off);
                Assert.InRange(Assert.Single(on) - last, 2000, 2020); // on after 2 s
            }
        }
        p.In("A1", 0, false);
    }

    [SimFact]
    public void FuelPumpPresetTripsAfterItsTripTimeThreeTimesInAll()
    {
        var p = P;
        p.Bus.Cmd("LOAD B 3 30");                                    // 30 A > the 25 A limit, < the 100 A inrush limit
        p.Cmd[3] = 1;
        var on = new List<(double T, bool On)>();
        p.Pump(5000, 5, t => on.Add((t, p.Bus.Pin("B", 3))));
        p.Cmd[3] = 0;
        p.Bus.Cmd("LOAD B 3 0");
        var spans = new List<(double Start, double Ms)>();
        for (var i = 1; i < on.Count; i++)
            if (on[i].On && !on[i - 1].On || i == 1 && on[0].On) spans.Add((on[i].T, 0));
            else if (!on[i].On && on[i - 1].On) spans[^1] = (spans[^1].Start, on[i].T - spans[^1].Start);
        output.WriteLine($"fuel pump at 30 A: on spans {string.Join(", ", spans.Select(s => $"{s.Start:F0}+{s.Ms:F0} ms"))}");
        Assert.Equal(3, spans.Count);                                // 3 trips in all
        Assert.All(spans, s => Assert.InRange(s.Ms, 590, 625));     // 500 ms inrush window + 100 ms trip time
        Assert.All(spans.Zip(spans.Skip(1), (a, b) => b.Start - (a.Start + a.Ms)), g => Assert.InRange(g, 990, 1025)); // 1 s retry
        Assert.False(on[^1].On);
        p.Pump(100, 50);
    }
}
