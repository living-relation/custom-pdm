using application.Services;
using domain.CustomPdm;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// canboard (Dan, 2026-11-22): the CANBoard preset through the real UI code on the sim boards (real firmware logic,
// sim bridge). PdmCanBoard makes the inputs and the output frames on the PC (New PDM project), the /pdm Write All
// puts them on the three boards, and a simulated CANBoard (sim_bridge.py class CanBoard: the CANBoard's status frames
// as its firmware builds them, firmware/boards/canboard_v2/msg.cpp; its outputs set as PdmCanBoard.SetupSteps says)
// joins the bus. A stand-in, not the CANBoard's firmware: its frame layout is checked against the firmware source
// in PdmCanBoardTests.TheProtocolNumbersAreTheFirmwares.
// B OUT1 (17) = Wheel switch 3; B OUT2 (18) = Wheel analog 2 at 2500 mV or more (off at 2000 or less);
// B OUT3 (19) = Wheel rotary 2 at position 3 or more; A1 OUT1 (1) = Wheel switch 5 (another board hears it too);
// Wheel output 1 follows IN15 (B), output 2 follows IN2 (A1), output 4 follows IN16 (B).
public sealed class CanBoardPdm : IDisposable
{
    public const int Base = 0x6C0;
    private SimBus? _bus;
    public SimBus Bus => _bus ?? throw new InvalidOperationException("not set up");
    public List<string> Log { get; } = [];
    public double LoadBefore, LoadWritten, LoadOne;
    public PdmCanBoardInfo Cb = null!;

    public static double BusLoad(SimBus bus, double ms = 2000)
    {
        var a = bus.Lines($"BUSLOAD {ms}").Single(l => l.StartsWith("B ")).Split(' ');
        return double.Parse(a[1], System.Globalization.CultureInfo.InvariantCulture) / (ms * 1000) * 100;
    }

    public void SetUp()
    {
        if (_bus != null) return;
        _bus = new SimBus();
        var rig = new PdmRig(_bus, newPdm: true);
        rig.Step(1500);
        LoadBefore = BusLoad(_bus);
        var svc = new PdmOpsService(rig.Mgr) { AutoTick = false };
        var v = svc.BuildView();
        Assert.Null(PdmCanBoard.Add(v, Base, "Wheel", rotary: true));
        int On(string role, PdmCanBoardKind k, int n)
        {
            var var = PdmCanBoard.Ensure(v, role, Base, PdmCanBoard.Signal(k, n), out var why);
            Assert.Null(why);
            return var;
        }

        Assert.Null(PdmTriggers.Set(v, 17, PdmTriggerSpec.Input(PdmTerm.Of(On("B", PdmCanBoardKind.Switch, 3)))));
        Assert.Null(PdmTriggers.Set(v, 18, PdmTriggerSpec.Level(new PdmThreshold(On("B", PdmCanBoardKind.Analog, 2), true, 2500, 2000))));
        Assert.Null(PdmTriggers.Set(v, 19, PdmTriggerSpec.Level(new PdmThreshold(On("B", PdmCanBoardKind.Rotary, 2), true, 3, 2))));
        Assert.Null(PdmTriggers.Set(v, 1, PdmTriggerSpec.Input(PdmTerm.Of(On("A1", PdmCanBoardKind.Switch, 5)))));
        var (a1, b) = (rig.A1, rig.B);
        Assert.Null(PdmCanBoard.SetOutput(v, Base, 1, "B", PdmFactoryDefaults.VarOf(b, b.DigitalInputs[0])));
        Assert.Null(PdmCanBoard.SetOutput(v, Base, 2, "A1", PdmFactoryDefaults.VarOf(a1, a1.DigitalInputs[1])));
        Assert.Null(PdmCanBoard.SetOutput(v, Base, 4, "B", PdmFactoryDefaults.VarOf(b, b.DigitalInputs[1])));
        foreach (var o in v.Outputs.Where(o => o.Number is 1 or 17 or 18 or 19)) o.Output.Enabled = true;
        foreach (var i in new[] { 2, 15, 16 }) v.Inputs.Single(r => r.Number == i).Digital!.Enabled = true;
        Assert.Empty(PdmModel.Build(v).Problems);
        Cb = PdmCanBoard.All(v).Single();
        var m = PdmModel.Build(v);
        Log.Add(string.Join("\n", m.Triggers.Where(t => t.Kind != PdmTriggerKind.None).Select(t => $"{t.Out.Number}: {t.Words}")
            .Concat(Cb.Outputs.Select(o => PdmCanBoard.OutWords(m, Cb, o))).Concat(PdmCanBoard.SetupSteps(Cb))));

        var t0 = rig.SimMs;
        Assert.Null(svc.Start(PdmOpKind.WriteAll, true, rig.Now));
        while (svc.Ops.Busy && rig.SimMs - t0 < 180000)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }
        Assert.All(svc.Ops.Results, r => Assert.Equal(PdmStepState.Ok, r.State));
        _bus.Run(500);
        LoadWritten = BusLoad(_bus);                       // the PDM alone, set up for the CANBoard (it is not there yet)

        // the simulated CANBoard, set as the CANBoard card says (the same lines the Simulator panel sends)
        _bus.Cmd(PdmCanBoardSim.AddLine(Base));
        foreach (var l in PdmCanBoardSim.OutputLines(Cb)) _bus.Cmd(l);
        _bus.Run(500);
        LoadOne = BusLoad(_bus);
    }

    public void Sw(int n, bool on) => Bus.Cmd(PdmCanBoardSim.SwitchLine(Base, n, on)!);
    public void An(int n, int mv) => Bus.Cmd(PdmCanBoardSim.AnalogLine(Base, n, mv)!);
    public void Rot(int n, int pos) => Bus.Cmd(PdmCanBoardSim.RotaryLine(Base, n, pos)!);
    public void Link(bool on) => Bus.Cmd(PdmCanBoardSim.LinkLine(Base, on));
    public void In(string board, int i, bool on) => Bus.Cmd($"IN {board} {i} {(on ? "12v" : "gnd")}");
    public string Outs() => Bus.Lines($"CBOUT {Base:X}").Single(l => l.StartsWith("C "))[2..];
    public bool Pin(string board, int o) => Bus.Pin(board, o);

    // everything off and on the bus again
    public void Rest()
    {
        Link(true);
        for (var n = 1; n <= 8; n++) Sw(n, false);
        for (var n = 1; n <= 5; n++) { An(n, 0); Rot(n, 0); }
        In("B", 0, false); In("B", 1, false); In("A1", 1, false);
        Bus.Cmd("LINK B on"); Bus.Cmd("LINK A1 on");
        Bus.Run(400);
    }

    public void Dispose() => _bus?.Dispose();
}

[Collection("sim")]
public class CanBoardLiveSimTests(CanBoardPdm pdm, ITestOutputHelper output) : IClassFixture<CanBoardPdm>
{
    private const int Base = CanBoardPdm.Base;

    private CanBoardPdm P
    {
        get
        {
            pdm.SetUp();
            foreach (var l in pdm.Log) output.WriteLine(l);
            pdm.Log.Clear();
            pdm.Rest();
            return pdm;
        }
    }

    [SimFact]
    public void TheSimulatedCanBoardSendsItsThreeFramesEvery100MsAndTheAppDecodesThem()
    {
        var p = P;
        p.Sw(1, true); p.Sw(8, true); p.An(1, 100); p.An(2, 2600); p.An(5, 4321); p.Rot(2, 3); p.Rot(5, 15);
        p.Bus.Run(150);
        var frames = p.Bus.Run(1000);
        foreach (var id in PdmCanBoardSim.WatchIds(Base)) Assert.Equal(10, frames.Count(f => f.Id == id));
        Assert.DoesNotContain(frames, f => f.Id >= Base && f.Id < Base + PdmCanBoard.StatusIds && !PdmCanBoardSim.WatchIds(Base).Contains(f.Id));
        byte[] Last(int id) => frames.Last(f => f.Id == id).Data;
        Assert.All(frames.Where(f => PdmCanBoardSim.WatchIds(Base).Contains(f.Id)), f => Assert.Equal(8, f.Data.Length));
        var live = PdmCanBoardSim.Decode(Last(Base + 2), Last(Base + 3), Last(Base + 4), true);
        Assert.Equal([true, false, false, false, false, false, false, true], live.Switches);
        Assert.Equal([100, 2600, 0, 0, 4321], live.Mv);
        Assert.Equal([0, 3, 0, 0, 15], live.Rotary);
        var beats = frames.Where(f => f.Id == Base + 4).Select(f => (int)f.Data[7]).ToList();
        Assert.All(beats.Zip(beats.Skip(1)), x => Assert.Equal((x.First + 1) & 255, x.Second));   // heartbeat + 1 per frame
        output.WriteLine($"0x{Base + 2:X} {Convert.ToHexString(Last(Base + 2))}  0x{Base + 3:X} {Convert.ToHexString(Last(Base + 3))}  0x{Base + 4:X} {Convert.ToHexString(Last(Base + 4))}");
    }

    [SimFact]
    public void ASwitchOnTheCanBoardSwitchesAPdmOutputOnEveryBoardThatUsesIt()
    {
        var p = P;
        Assert.False(p.Pin("B", 0));
        Assert.False(p.Pin("A1", 0));
        // switch 3 -> B OUT1, at five different moments inside the CANBoard's 100 ms period
        var on = new List<double>();
        var off = new List<double>();
        foreach (var wait in new[] { 3.0, 27, 51, 77, 96 })
        {
            p.Bus.Run(wait);
            p.Sw(3, true);
            var t = p.Bus.Trace(300, 0.5, [], "B:0");
            on.Add(Assert.Single(t.Changes("B:0")) - t.Start);
            Assert.True(p.Pin("B", 0));
            p.Bus.Run(wait);
            p.Sw(3, false);
            t = p.Bus.Trace(300, 0.5, [], "B:0");
            off.Add(Assert.Single(t.Changes("B:0")) - t.Start);
            Assert.False(p.Pin("B", 0));
        }
        output.WriteLine($"switch -> B OUT1 on after {on.Min():F1}-{on.Max():F1} ms, off after {off.Min():F1}-{off.Max():F1} ms (5 phases of the 100 ms frame)");
        Assert.InRange(on.Max(), 0, 110);        // the next status frame (at most 100 ms away) + the board's own cycle
        Assert.InRange(off.Max(), 0, 110);
        Assert.True(on.Max() - on.Min() > 20);   // the timing really was varied
        // switch 5 -> A1 OUT1 (another board hears the same CANBoard); the other switches do nothing
        p.Sw(5, true); p.Bus.Run(250);
        Assert.Equal((true, false), (p.Pin("A1", 0), p.Pin("B", 0)));
        p.Sw(5, false);
        foreach (var n in new[] { 1, 2, 4, 6, 7, 8 }) p.Sw(n, true);
        p.Bus.Run(250);
        Assert.Equal((false, false), (p.Pin("A1", 0), p.Pin("B", 0)));
    }

    [SimFact]
    public void AnAnalogLevelAndARotaryPositionSwitchOutputsWithHysteresis()
    {
        var p = P;
        var got = new List<string>();
        foreach (var mv in new[] { 2400, 2500, 2100, 2000, 2499, 5000, 0 })
        {
            p.An(2, mv); p.Bus.Run(250);
            got.Add($"{mv}:{(p.Pin("B", 1) ? 1 : 0)}");
        }
        output.WriteLine("analog 2 (on at 2500, off at 2000): " + string.Join(" ", got));
        Assert.Equal("2400:0 2500:1 2100:1 2000:0 2499:0 5000:1 0:0", string.Join(" ", got));
        p.An(1, 5000); p.An(3, 5000); p.Bus.Run(250);                 // the neighbours in the same frame do nothing
        Assert.False(p.Pin("B", 1));
        var rot = new List<string>();
        foreach (var pos in new[] { 2, 3, 15, 2, 0 })
        {
            p.Rot(2, pos); p.Bus.Run(250);
            rot.Add($"{pos}:{(p.Pin("B", 2) ? 1 : 0)}");
        }
        output.WriteLine("rotary 2 (on at 3, off at 2): " + string.Join(" ", rot));
        Assert.Equal("2:0 3:1 15:1 2:0 0:0", string.Join(" ", rot));
        p.Rot(1, 15); p.Rot(3, 15); p.Bus.Run(250);
        Assert.False(p.Pin("B", 2));
    }

    [SimFact]
    public void AnUnpluggedCanBoardReadsOffAndZeroAfterTheTimeOutAndComesBack()
    {
        var p = P;
        p.Sw(3, true); p.Sw(5, true); p.An(2, 3000);
        p.Bus.Run(300);
        Assert.Equal((true, true, true), (p.Pin("B", 0), p.Pin("B", 1), p.Pin("A1", 0)));
        var lost = new List<double>();
        foreach (var wait in new[] { 5.0, 45, 90 })
        {
            p.Bus.Run(wait);
            p.Link(false);                                              // unplugged: silent from now on
            var t = p.Bus.Trace(1500, 1, [Base + 4], "B:0", "B:1", "A1:0");
            Assert.False(t.Frames.ContainsKey(Base + 4));
            foreach (var pin in new[] { "B:0", "B:1", "A1:0" })
            {
                lost.Add(Assert.Single(t.Changes(pin)) - t.Start);       // one clean change, no blip
                Assert.False(t.At(pin, t.End));
            }
            p.Link(true);                                               // plugged in again: back by itself
            p.Bus.Run(300);
            Assert.Equal((true, true, true), (p.Pin("B", 0), p.Pin("B", 1), p.Pin("A1", 0)));
        }
        output.WriteLine($"unplugged: switch and analog-level outputs off {lost.Min():F0}-{lost.Max():F0} ms after the unplug (time-out {pdm.Cb.TimeoutMs} ms after the last frame; 3 phases)");
        Assert.InRange(lost.Min(), pdm.Cb.TimeoutMs - PdmCanBoard.PeriodMs - 5, pdm.Cb.TimeoutMs + 15);
        Assert.InRange(lost.Max(), pdm.Cb.TimeoutMs - PdmCanBoard.PeriodMs - 5, pdm.Cb.TimeoutMs + 15);
    }

    [SimFact]
    public void ThePdmsCommandFramesDriveTheCanBoardsOutputsAndASilentPdmSwitchesThemOff()
    {
        var p = P;
        Assert.Equal("0000", p.Outs());
        // B sends 0x6D2 (4 bytes: outputs 1 and 4 are its), A1 sends 0x6D0 (2 bytes: output 2), every 100 ms
        var idle = p.Bus.Run(1000);
        Assert.Equal((10, 10, 0), (idle.Count(f => f.Id == 0x6D2), idle.Count(f => f.Id == 0x6D0), idle.Count(f => f.Id == 0x6D1)));
        Assert.All(idle.Where(f => f.Id == 0x6D2), f => Assert.Equal("00000000", Convert.ToHexString(f.Data)));
        Assert.All(idle.Where(f => f.Id == 0x6D0), f => Assert.Equal("0000", Convert.ToHexString(f.Data)));
        var seen = new List<string>();
        foreach (var (in15, in16, in2) in new[] { (true, false, false), (true, true, false), (false, true, true), (false, false, true), (false, false, false) })
        {
            p.In("B", 0, in15); p.In("B", 1, in16); p.In("A1", 1, in2);
            p.Bus.Run(300);
            var f = p.Bus.Run(200);
            var (b, a) = (Convert.ToHexString(f.Last(x => x.Id == 0x6D2).Data), Convert.ToHexString(f.Last(x => x.Id == 0x6D0).Data));
            var reported = PdmCanBoardSim.Decode(null, null, f.Last(x => x.Id == Base + 4).Data, true).Outputs;
            seen.Add($"{b} {a} {p.Outs()}");
            Assert.Equal(p.Outs(), string.Concat(reported.Select(x => x ? '1' : '0')));     // its status frame says the same
        }
        output.WriteLine("0x6D2 / 0x6D0 / CANBoard outputs 1-4: " + string.Join(" | ", seen));
        Assert.Equal(["01000000 0000 1000", "01000001 0000 1001", "00000001 0001 0101", "00000000 0001 0100", "00000000 0000 0000"], seen);

        // the PDM board that drives outputs 1 and 4 goes silent: the CANBoard drops them after its own time-out, output 2 (A1) stays
        p.In("B", 0, true); p.In("B", 1, true); p.In("A1", 1, true);
        p.Bus.Run(400);
        Assert.Equal("1101", p.Outs());
        p.Bus.Cmd("LINK B off");
        p.Bus.Run(pdm.Cb.TimeoutMs - 150);
        Assert.Equal("1101", p.Outs());
        p.Bus.Run(300);
        Assert.Equal("0100", p.Outs());
        p.Bus.Cmd("LINK B on");
        p.Bus.Run(300);
        Assert.Equal("1101", p.Outs());
    }

    [SimFact]
    public void BusLoadWithOneAndTwoCanBoardsStaysSmall()
    {
        var p = P;
        // a second CANBoard on the bus (frames only: the PDM is not set up for it)
        p.Bus.Cmd(PdmCanBoardSim.AddLine(0x660));
        p.Bus.Run(300);
        var two = CanBoardPdm.BusLoad(p.Bus);
        p.Bus.Cmd(PdmCanBoardSim.RemoveLine(0x660));
        var estimate = PdmCanBoard.BusLoadPercent(pdm.Cb);
        output.WriteLine(FormattableString.Invariant(
            $"bus load at 1 Mbit/s: PDM alone {pdm.LoadBefore:F2} %, PDM set up for the CANBoard {pdm.LoadWritten:F2} %, + the CANBoard {pdm.LoadOne:F2} %, + a second CANBoard's frames {two:F2} %; the UI's estimate for this CANBoard: +{estimate:F2} %"));
        // the CANBoard's own three 8-byte frames every 100 ms: 0.39 %
        Assert.InRange(pdm.LoadOne - pdm.LoadWritten, 0.37, 0.41);
        Assert.InRange(two - pdm.LoadOne, 0.37, 0.41);
        // the UI's figure for the CANBoard is close to the whole addition (this setup also has 3 triggers on it: the
        // level conditions make B send its msg 6 as well, 0.13 %, which is the triggers' cost, not the CANBoard's)
        Assert.InRange(estimate - (pdm.LoadOne - pdm.LoadBefore), -0.3, 0.3);
        Assert.True(two < 30, $"bus load {two:F1} %");   // far below the usual 30 % design limit
    }
}
