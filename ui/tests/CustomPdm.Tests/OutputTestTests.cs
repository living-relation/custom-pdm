using application.Services;
using domain.CustomPdm;
using domain.Enums;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// uifix2 (2026-11-23): the /pdm Output test (domain/CustomPdm/PdmOutputTest.cs, application/Services/PdmOutputTestService.cs)
// on the stand-in boards: what goes on the bus, what is refused, and that the board's own values always come back.
public class OutputTestTests
{
    private const int BOut3 = 19;                        // B OUT3 = board B output index 2 = param index 0x1002
    private static readonly (int, int) En = (0x1002, 0), In = (0x1002, 1);

    private sealed class Rig
    {
        public FakePdm Pdm { get; } = new();
        public PdmOutputTestService Test { get; }

        public Rig()
        {
            Pdm.Service.AutoReader.Watch(Pdm.View);       // as the app (AutoRead on): read / write snapshots
            Assert.Null(Pdm.Run(PdmOpKind.ReadAll));
            Test = new PdmOutputTestService(Pdm.Mgr, Pdm.Service, d => !Pdm.Offline.Contains(d.Name))
                { AutoTick = false, AdapterConnected = () => Pdm.Adapter, Wait = _ => { } };
        }

        public FakeBoard B => Pdm.Boards["B"];
        public domain.Devices.Functions.Output Out => Pdm.Dev("B").Outputs[2];

        public void Round(int n = 1)
        {
            for (var i = 0; i < n; i++)
            {
                Pdm.Rounds(1);
                Test.Tick(Pdm.Clock);
            }
        }

        public List<(int, int, int)> Writes(int from) => B.Writes.Skip(from).Select(w => (w.Index, w.Sub, w.Value)).ToList();
    }

    [Fact]
    public void OneOutputGoesOnForTheTimeThenItsOwnValuesGoBack()
    {
        var r = new Rig();
        var before = (r.B.Values[En].ToArray(), r.B.Values[In].ToArray());
        Assert.Equal((false, 0), (r.Out.Enabled, r.Out.Input));
        Assert.Null(r.Test.Start(BOut3, 2, false, r.Pdm.Clock));
        r.Round();
        // input = always true first, then enabled: live single-param writes, nothing else
        Assert.Equal([(0x1002, 1, PdmFaults.AlwaysTrueVar), (0x1002, 0, 1)], r.Writes(0));
        Assert.Equal((false, 0), (r.Out.Enabled, r.Out.Input));   // the PC keeps the saved values (the board's replies are not taken)
        Assert.Equal(PdmOutputTestState.On, r.Test.Active!.State);
        foreach (var op in Enum.GetValues<PdmOpKind>()) Assert.Contains("Output test running", r.Pdm.Blocked(op));
        Assert.Contains("Output test running", r.Test.Check(1, false));   // one test at a time

        r.Round(18);
        Assert.Equal(PdmOutputTestState.On, r.Test.Active!.State);
        r.Round();                                                 // 2 s: time up
        r.Pdm.Pump();
        Assert.Equal([(0x1002, 0, 0), (0x1002, 1, 0)], r.Writes(2)); // enabled back first, then its own trigger
        Assert.Equal(before.Item1, r.B.Values[En]);
        Assert.Equal(before.Item2, r.B.Values[In]);
        r.Round(4);                                                // settle
        Assert.Null(r.Test.Active);
        Assert.Equal("time up", r.Test.Last!.Why);
        Assert.Null(r.Pdm.Blocked(PdmOpKind.WriteAll));
        Assert.Equal(4, r.B.Writes.Count);
        Assert.All(r.Pdm.Boards.Values, b => Assert.Equal(0, b.Burns + b.Count(MessageCommand.WriteAll) + b.Count(MessageCommand.BurnParams)));
        Assert.Empty(r.Pdm.Boards["A1"].Writes);
        Assert.True(r.Pdm.Service.AutoReader.InSync(r.Pdm.Dev("B")));
    }

    [Fact]
    public void AnOutputThatWasOnWithItsOwnTriggerGetsThatTriggerBack()
    {
        var r = new Rig();
        (r.Out.Enabled, r.Out.Input) = (true, 7);
        Assert.Null(r.Pdm.Run(PdmOpKind.WriteAll));
        Assert.Null(r.Test.Start(BOut3, 0.5, false, r.Pdm.Clock));
        r.Round(10);
        Assert.Equal([(0x1002, 1, 1), (0x1002, 0, 1), (0x1002, 0, 1), (0x1002, 1, 7)], r.Writes(0));
        Assert.Null(r.Test.Active);
        Assert.Equal((true, 7), (r.Out.Enabled, r.Out.Input));
    }

    [Fact]
    public void TimeIsHalfASecondToTenSecondsDefaultTwo()
    {
        Assert.Equal(2, PdmOutputTest.Seconds(double.NaN));
        Assert.Equal(10, PdmOutputTest.Seconds(60));
        Assert.Equal(0.5, PdmOutputTest.Seconds(0));
        var r = new Rig();
        Assert.Null(r.Test.Start(BOut3, 60, false, r.Pdm.Clock));
        Assert.Equal(TimeSpan.FromSeconds(10), r.Test.Active!.Until - r.Test.Active.Started);
    }

    [Fact]
    public void StopPutsTheValuesBackAtOnce()
    {
        var r = new Rig();
        Assert.Null(r.Test.Start(BOut3, 10, false, r.Pdm.Clock));
        r.Round();
        r.Test.Stop(r.Pdm.Clock);
        r.Round();
        Assert.Equal([(0x1002, 0, 0), (0x1002, 1, 0)], r.Writes(2));
        Assert.Equal("stopped", r.Test.Last!.Why);
    }

    [Fact]
    public void RefusedWhenItCouldNotPutTheBoardsOwnValuesBackOrIsNotSafe()
    {
        var r = new Rig();
        r.Pdm.Adapter = false;
        Assert.Equal(PdmOutputTest.AdapterOff, r.Test.Start(BOut3, 2, false, r.Pdm.Clock));
        r.Pdm.Adapter = true;
        r.Pdm.Offline.Add("B");
        Assert.Contains("B is offline", r.Test.Start(BOut3, 2, false, r.Pdm.Clock));
        r.Pdm.Offline.Clear();
        Assert.Equal("Pick an output of the PDM.", r.Test.Start(99, 2, false, r.Pdm.Clock));

        // a safety-related function needs the tick: fuel pump (preset or name), EPS enable, starter
        foreach (var (name, what) in new[] { ("Fuel pump", "fuel pump"), ("EPS enable", "EPS / power steering"), ("Starter relay", "starter"), ("crank", "starter") })
        {
            r.Out.Name = name;                                     // names live on the PC only: still in step with the board
            Assert.Equal(what, r.Test.SafetyFunction(BOut3));
            Assert.Contains($"runs the {what}", r.Test.Start(BOut3, 2, false, r.Pdm.Clock));
        }
        r.Out.Name = "Fog lamps";
        Assert.Null(r.Test.SafetyFunction(BOut3));
        r.Out.Name = "Fuel pump";
        Assert.Null(r.Test.Start(BOut3, 0.5, true, r.Pdm.Clock));
        r.Round(10);
        Assert.Null(r.Test.Active);

        // a PC change not on the board: the test would put the PC's value, not the board's, back
        r.Pdm.Dev("B").Outputs[5].CurrentLimit = 3;
        Assert.Contains("not on the board", r.Test.Start(BOut3, 2, true, r.Pdm.Clock));
        r.Pdm.Dev("B").Outputs[5].CurrentLimit = 15;
        Assert.Null(r.Test.Check(BOut3, true));

        // a paired follower: test its primary
        var pair = new Rig();
        pair.Pdm.Dev("B").Outputs[1].PrimaryOutput = 0;
        Assert.Contains("test OUT1", pair.Test.Start(18, 2, false, pair.Pdm.Clock));

        // never while a Read All / Write All / Burn runs
        var busy = new Rig();
        Assert.Null(busy.Pdm.Service.Start(PdmOpKind.ReadAll, true, busy.Pdm.Clock));
        Assert.Equal(PdmOutputTest.Running, busy.Test.Start(BOut3, 2, false, busy.Pdm.Clock));
    }

    [Fact]
    public void AdapterGoneMidTestTheValuesGoBackWhenItIsBack()
    {
        var r = new Rig();
        Assert.Null(r.Test.Start(BOut3, 5, false, r.Pdm.Clock));
        r.Round();
        r.Pdm.Adapter = false;                                    // cable pulled: nothing can be sent
        r.Round(3);
        Assert.Equal(PdmOutputTestState.Restoring, r.Test.Active!.State);
        Assert.Equal(2, r.B.Writes.Count);
        Assert.Contains("not back on B yet", r.Test.HoldReason());
        Assert.Contains("not back on B yet", r.Pdm.Blocked(PdmOpKind.ReadAll) ?? "adapter");
        r.Pdm.Adapter = true;
        r.Round();
        r.Pdm.Pump();
        Assert.Equal([(0x1002, 0, 0), (0x1002, 1, 0)], r.Writes(2));
        r.Round(4);
        Assert.Null(r.Test.Active);
    }

    [Fact]
    public void BoardGoneMidTestTheValuesGoBackWhenItIsBack()
    {
        var r = new Rig();
        Assert.Null(r.Test.Start(BOut3, 5, false, r.Pdm.Clock));
        r.Round();
        r.Pdm.Offline.Add("B");
        r.Round();
        Assert.Equal("B went offline", r.Test.Last!.Why);
        Assert.Equal(PdmOutputTestState.Restoring, r.Test.Active!.State);   // sent anyway, sent again until B is seen
        r.Round(12);
        Assert.Equal(PdmOutputTestState.Restoring, r.Test.Active!.State);
        r.Pdm.Offline.Clear();
        r.Round(12);
        Assert.Null(r.Test.Active);
        Assert.Equal((0x1002, 1, 0), r.Writes(0).Last());
    }

    // adapter Disconnect button / app close (Program.cs: CommsAdapterManager.BeforeDisconnect, ApplicationStopping)
    [Fact]
    public void DisconnectOrAppCloseSendsTheValuesBackFirstAndAgainLater()
    {
        var r = new Rig();
        Assert.Null(r.Test.Start(BOut3, 10, false, r.Pdm.Clock));
        r.Round();
        r.Test.StopNow("app closing");
        r.Pdm.Pump();
        Assert.Equal([(0x1002, 0, 0), (0x1002, 1, 0)], r.Writes(2));
        Assert.Equal("app closing", r.Test.Last!.Why);
        r.Round(15);                // the adapter stayed: sent again at once and once more 1 s later (board seen), then done
        Assert.Null(r.Test.Active);
        Assert.Equal(8, r.B.Writes.Count);
        r.Test.StopNow("again");                                 // nothing running: nothing sent
        r.Pdm.Pump();
        Assert.Equal(8, r.B.Writes.Count);
    }
}

// The same on the real firmware (host sim): pin on, current read, back to the saved behaviour, nothing burned
[Collection("sim")]
public class OutputTestLiveSimTests(ITestOutputHelper output)
{
    private static void WriteAll(PdmRig rig, PdmOpsService svc)
    {
        var t = rig.SimMs;
        Assert.Null(svc.Start(PdmOpKind.WriteAll, true, rig.Now));
        while (svc.Ops.Busy && rig.SimMs - t < 300000)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }

        Assert.All(svc.Ops.Results, r => Assert.Equal(PdmStepState.Ok, r.State));
    }

    // (number, board, board output index, enabled before, input before, seconds): B OUT3 enabled with "always off" as
    // its trigger, B OUT4 disabled, A1 OUT2 disabled
    [SimTheory]
    [InlineData(19, "B", 2, true, 0, 1.0, 5.0)]
    [InlineData(20, "B", 3, false, 0, 2.0, 5.0)]
    [InlineData(2, "A1", 1, false, 0, 0.5, 2.0)]
    [InlineData(3, "A1", 2, false, 0, 1.0, 5.0)]
    public void TheOutputIsOnForTheTestWithItsCurrentThenBackAsSaved(int number, string board, int o, bool enabled, int input, double seconds, double amps)
    {
        using var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        var svc = new PdmOpsService(rig.Mgr, _ => true) { AutoTick = false };
        svc.AutoReader.Watch(svc.BuildView());
        var dev = board == "B" ? rig.B : rig.A1;
        var outp = dev.Outputs[o];
        (outp.Enabled, outp.Input) = (enabled, input);
        WriteAll(rig, svc);
        rig.Step(500);
        Assert.False(bus.Pin(board, o));
        Assert.True(svc.AutoReader.InSync(dev));
        bus.Cmd($"LOAD {board} {o} {amps}");

        var test = new PdmOutputTestService(rig.Mgr, svc, _ => true) { AutoTick = false, Wait = _ => { } };
        Assert.Null(test.Start(number, seconds, false, rig.Now));
        var t0 = rig.SimMs;
        double? on = null, off = null;
        var maxA = 0.0;
        while (test.Active != null && rig.SimMs - t0 < 15000)
        {
            rig.Step(20);
            test.Tick(rig.Now);
            var pin = bus.Pin(board, o);
            if (pin && on == null) on = rig.SimMs - t0;
            if (!pin && on != null && off == null) off = rig.SimMs - t0;
            maxA = Math.Max(maxA, outp.Current);
            if (test.Active?.State == PdmOutputTestState.On)
                Assert.Contains("Output test running", svc.BlockedReason(PdmOpKind.Burn, svc.BuildView(), true));
        }

        rig.Step(500);
        var last = test.Last!;
        output.WriteLine($"OUT{number}: pin on at {on} ms, off at {off} ms, peak {last.PeakA:0.00} A (PC saw {maxA:0.00} A), {last.Why}");
        Assert.Null(test.Active);
        Assert.NotNull(on);
        Assert.InRange(on!.Value, 0, 200);
        Assert.NotNull(off);
        Assert.InRange(off!.Value - on.Value, seconds * 1000 - 100, seconds * 1000 + 300);
        // board B reads the load (5.00 A); board A reads about 1 A low in the host sim (2 A -> 1.00 A, 5 A -> 4.00 A,
        // measured here; its current-sense chain, not the test: reported, BACKLOG)
        if (board == "B") Assert.InRange(last.PeakA, amps * 0.9, amps * 1.1);
        else Assert.InRange(last.PeakA, amps - 1.1, amps + 0.2);
        Assert.False(bus.Pin(board, o));
        Assert.Equal((enabled, input), (outp.Enabled, outp.Input));       // PC values unchanged

        // the board holds its own values again (a fresh PC reads them) and nothing was burned
        var pc2 = PcTool.For(bus, dev.DeviceTypeId, dev.BaseId);
        Assert.True(pc2.ReadAll());
        Assert.Equal((enabled, input), (pc2.Dev.Outputs[o].Enabled, pc2.Dev.Outputs[o].Input));
        Assert.Equal(0, rig.CountSent(dev.BaseId, MessageCommand.BurnParams));
        Assert.True(svc.AutoReader.InSync(dev));
        Assert.Null(svc.BlockedReason(PdmOpKind.Burn, svc.BuildView(), true));

        // back to its saved behaviour: a power cycle (burned = factory) and the trigger it had keep it off
        bus.Restart(board);
        rig.Step(1500);
        Assert.False(bus.Pin(board, o));
    }
}
