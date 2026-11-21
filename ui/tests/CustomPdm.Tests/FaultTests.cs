using domain.CustomPdm;
using domain.Enums;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// uipolish (2026-11-21): the fault line at the top of /pdm, the Reset faults button and the log words (PdmFaults.cs)
public class FaultTests
{
    [Fact]
    public void AFaultIsSaidInPlainWordsWithTheOutputsNameAndPlace()
    {
        var pdm = new FakePdm();
        Assert.Empty(PdmFaults.Lines(pdm.View, _ => true));

        var pump = pdm.Dev("B").Outputs[4];
        (pump.Name, pump.State, pump.ResetCount, pump.ResetMode, pump.ResetCountLimit) = ("Fuel pump", OutState.Fault, 3, ResetMode.Count, 3);
        var lamp = pdm.Dev("A1").Outputs[1];   // stock name: said by its PDM number
        (lamp.State, lamp.ResetCount, lamp.ResetMode, lamp.ResetCountLimit, lamp.ResetTime) = (OutState.Overcurrent, 1, ResetMode.Count, 3, 1500);
        var horn = pdm.Dev("A2").Outputs[0];
        (horn.Name, horn.State, horn.ResetCount, horn.ResetMode, horn.ResetTime) = (" Horn ", OutState.Overcurrent, 4, ResetMode.Endless, 2000);
        var once = pdm.Dev("B").Outputs[7];
        (once.Name, once.State, once.ResetCount, once.ResetMode) = ("Wiper", OutState.Fault, 1, ResetMode.None);

        Assert.Equal(
        [
            "Output 2 (A1 OUT2): overcurrent, trip 1 of 3, off for 1.5 s then it tries again",
            "Horn (A2 OUT1): overcurrent, 4 trips, off for 2 s then it tries again",
            "Fuel pump (B OUT5): overcurrent, 3 trips, off until reset",
            "Wiper (B OUT8): overcurrent, 1 trip, off until reset"
        ], PdmFaults.Lines(pdm.View, _ => true).Select(l => l.Text));
        Assert.All(PdmFaults.Lines(pdm.View, _ => true), l => Assert.True(l.Reset));

        // a board that is off the bus shows its last values: no fault line from those
        Assert.Equal(["Output 2 (A1 OUT2)", "Horn (A2 OUT1)"],
            PdmFaults.Lines(pdm.View, d => d.Name != "B").Select(l => l.Text.Split(':')[0]));
        Assert.Empty(PdmFaults.Lines(pdm.View));   // FakePdm devices have heard no cyclic frame: not connected
        Assert.Null(PdmFaults.OutputFault(pdm.Dev("A1").Outputs[0]));
        pdm.Dev("A1").Outputs[0].State = OutState.On;
        Assert.Null(PdmFaults.OutputFault(pdm.Dev("A1").Outputs[0]));
    }

    [Fact]
    public void BoardTemperatureFlagsAreSaidOncePerBoardWorstFirst()
    {
        var pdm = new FakePdm();
        pdm.Dev("B").CustomPdm!.ThermalFlags = 1 | 2 | 4;
        (pdm.Dev("B").CustomPdm!.TempCrit, pdm.Dev("B").CustomPdm!.TempCritHyst) = (104, 6);
        pdm.Dev("A1").CustomPdm!.ThermalFlags = 1 | 2;
        pdm.Dev("A1").CustomPdm!.TempCrit = 80;
        pdm.Dev("A2").CustomPdm!.ThermalFlags = 1;
        pdm.Dev("A2").CustomPdm!.TempWarn = 55;
        var lines = PdmFaults.Lines(pdm.View, _ => true);
        Assert.Equal(
        [
            "Board A1: close to its critical temperature (sensor 0 C, critical at 80 C): its outputs go off there",
            "Board A2: hot (0 C, warning from 55 C)",
            "Board B: over temperature (sensor 0 C, critical at 104 C): its outputs are off until it has cooled by 6 C"
        ], lines.Select(l => l.Text));
        Assert.All(lines, l => Assert.False(l.Reset));   // nothing for the Reset faults button to clear
    }

    [Fact]
    public void TheResetIsThreeLiveWritesOfTheMasterRetryInput()
    {
        var pdm = new FakePdm();
        var frames = PdmFaults.ResetFrames(pdm.Dev("A2"), 0x0123);
        Assert.Equal(3, frames.Count);
        Assert.All(frames, f => Assert.Equal((0x541, 8, true), (f.Frame.Id, f.Frame.Len, f.SendOnly)));
        byte w = (byte)MessageCommand.Write;
        Assert.Equal(new byte[] { w, 0x00, 0x7F, 6, 0, 0, 0, 0 }, frames[0].Frame.Payload);      // always false
        Assert.Equal(new byte[] { w, 0x00, 0x7F, 6, 1, 0, 0, 0 }, frames[1].Frame.Payload);      // always true: the edge
        Assert.Equal(new byte[] { w, 0x00, 0x7F, 6, 0x23, 0x01, 0, 0 }, frames[2].Frame.Payload); // what it had
    }

    [Fact]
    public async Task ResetFaultsWritesEveryConnectedBoardInStepsAndPutsTheValueBack()
    {
        var pdm = new FakePdm();
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        pdm.Dev("A1").CustomPdm!.MasterRetryInput = 9;   // the user's own master retry input
        pdm.Offline.Add("A2");
        var gaps = new List<TimeSpan>();
        var seenAtStep = new List<int>();
        Task Delay(TimeSpan t)
        {
            gaps.Add(t);
            pdm.Pump();
            seenAtStep.Add(pdm.Boards["A1"].Writes.Count);
            return Task.CompletedTask;
        }

        Assert.Null(await pdm.Service.ResetFaultsAsync(true, Delay));
        Assert.Equal([PdmFaults.ResetStepGap, PdmFaults.ResetStepGap, PdmFaults.ResetStepGap], gaps);
        Assert.Equal(TimeSpan.FromMilliseconds(50), PdmFaults.ResetStepGap);
        Assert.Equal([1, 2, 3], seenAtStep);   // one write per step: the board sees each value before the next
        Assert.Equal([(0x7F00, 6, 0), (0x7F00, 6, 1), (0x7F00, 6, 9)], pdm.Boards["A1"].Writes);
        Assert.Equal([(0x7F00, 6, 0), (0x7F00, 6, 1), (0x7F00, 6, 0)], pdm.Boards["B"].Writes);
        Assert.Empty(pdm.Boards["A2"].Writes);  // offline: nothing sent
        Assert.Equal((9, 0), (pdm.Dev("A1").CustomPdm!.MasterRetryInput, pdm.Dev("B").CustomPdm!.MasterRetryInput));
        Assert.All(pdm.Boards.Values, b => Assert.Equal((0, 0), (b.Count(MessageCommand.WriteAll), b.Burns)));

        // refused: adapter off, no board on the bus, a PDM run in work
        Assert.Equal(PdmOps.AdapterOffReason, await pdm.Service.ResetFaultsAsync(false, Delay));
        pdm.Offline.UnionWith(["A1", "B"]);
        Assert.Equal(PdmOps.NoBoardReason, await pdm.Service.ResetFaultsAsync(true, Delay));
        pdm.Offline.Clear();
        Assert.Null(pdm.Service.Start(PdmOpKind.ReadAll, true, pdm.Clock));
        Assert.Equal(PdmOps.BusyReason, await pdm.Service.ResetFaultsAsync(true, Delay));
        Assert.Equal(3, pdm.Boards["A1"].Writes.Count);
    }

    [Fact]
    public async Task TheKeptValueGoesBackAlsoWhenTheSendFails()
    {
        var pdm = new FakePdm();
        pdm.Dev("B").CustomPdm!.MasterRetryInput = 12;
        await Assert.ThrowsAsync<InvalidOperationException>(() => pdm.Service.ResetFaultsAsync(true, _ =>
        {
            pdm.Dev("B").CustomPdm!.MasterRetryInput = 1;   // as the board's reply to the "always true" write would
            throw new InvalidOperationException("adapter gone");
        }));
        Assert.Equal(12, pdm.Dev("B").CustomPdm!.MasterRetryInput);
    }

    [Fact]
    public void StockLogLinesGetWords()
    {
        var pdm = new FakePdm();
        var b = pdm.Dev("B");
        b.Outputs[2].Name = "Fuel pump";
        string? W(MessageType t, MessageSrc s, int d0 = 0, int d1 = 0, int d2 = 0) => PdmFaults.LogWords(b, t, s, d0, d1, d2);
        Assert.Equal("Fuel pump (OUT3): overcurrent trip at 39 A (it tries again by its reset setting)", W(MessageType.Warning, MessageSrc.OverCurrent, 2, 39));
        Assert.Equal("Fuel pump (OUT3): overcurrent fault at 39 A, off until reset (Reset faults on the PDM page, the master retry input, or a power cycle)",
            W(MessageType.Error, MessageSrc.OverCurrent, 2, 39));
        Assert.StartsWith("output 8 (OUT8): overcurrent trip at 20 A", W(MessageType.Warning, MessageSrc.OverCurrent, 7, 20));
        Assert.StartsWith("output 9: overcurrent trip", W(MessageType.Warning, MessageSrc.OverCurrent, 8, 20));   // not an output of this board
        Assert.Equal("over temperature: board at 100 C", W(MessageType.Error, MessageSrc.StateOvertemp, 1000));
        Assert.Equal("critical temperature: board at 104.5 C, limit 104 C, outputs off (but the ones kept on at critical)", W(MessageType.Error, MessageSrc.OverTemp, 1045, 1040));
        Assert.Equal("close to critical temperature: board at 99 C, critical at 104 C (warned 5 C before)", W(MessageType.Warning, MessageSrc.OverTemp, 990, 1040, 5));
        Assert.Equal("board temperature sensor not answering (5 failed reads in a row, 17 in all)", W(MessageType.Error, MessageSrc.TempSensor, 5, 17));
        Assert.Equal("the board stopped in its error state", W(MessageType.Error, MessageSrc.StateError, 250, 30));
        Assert.Equal("battery voltage 16.4 V is above 16 V", W(MessageType.Warning, MessageSrc.BatteryVoltage, 164));
        Assert.Equal("battery voltage 9.2 V is below 10 V", W(MessageType.Warning, MessageSrc.BatteryVoltage, 92));
        Assert.Equal(("running", "going to sleep"), (W(MessageType.Info, MessageSrc.StateRun), W(MessageType.Info, MessageSrc.StateSleep)));
        Assert.Null(W(MessageType.Warning, MessageSrc.Init, 1));       // our boot warnings: CustomPdmBootMessages
        Assert.Null(W(MessageType.Info, MessageSrc.OverCurrent, 2, 39));
        Assert.Null(W(MessageType.Warning, MessageSrc.Config, 3, 1));
    }
}

// The same on the real firmware (host sim): a latched fault, the line, the reset, with the step gap varied
[Collection("sim")]
public class FaultLiveSimTests(ITestOutputHelper output)
{
    private static void WriteAll(PdmRig rig, application.Services.PdmOpsService svc)
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

    [SimTheory]
    [InlineData(10, 0)]
    [InlineData(50, 0)]
    [InlineData(200, 0)]
    [InlineData(50, 1)]    // the board's master retry input is a var that is ON all the time: the "0" write makes the edge
    public async Task ResetFaultsClearsLatchedFaultsOnTheBoards(int gapMs, int keptInput)
    {
        using var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        var svc = new application.Services.PdmOpsService(rig.Mgr, _ => true) { AutoTick = false };
        var pump = rig.B.Outputs[4];
        (pump.Name, pump.Enabled, pump.Input, pump.CurrentLimit) = ("Fuel pump", true, PdmFaults.AlwaysTrueVar, 10);
        (pump.ResetMode, pump.ResetCountLimit, pump.ResetTime, pump.InrushTime) = (ResetMode.Count, 2, 300, 200);
        var lamp = rig.A1.Outputs[2];
        (lamp.Enabled, lamp.Input, lamp.CurrentLimit, lamp.ResetMode, lamp.InrushTime) = (true, PdmFaults.AlwaysTrueVar, 5, ResetMode.None, 200);
        foreach (var d in rig.All) d.CustomPdm!.MasterRetryInput = keptInput;
        WriteAll(rig, svc);
        rig.Step(500);
        Assert.Equal((OutState.On, OutState.On), (pump.State, lamp.State));
        Assert.Empty(PdmFaults.Lines(svc.BuildView(), _ => true));

        bus.Cmd("LOAD B 4 20");    // 20 A on a 10 A limit
        bus.Cmd("LOAD A1 2 7");    // 7 A on a 5 A limit
        rig.Step(3000);
        Assert.Equal((OutState.Fault, OutState.Fault), (pump.State, lamp.State));
        Assert.False(bus.Pin("B", 4));
        var lines = PdmFaults.Lines(svc.BuildView(), _ => true).Select(l => l.Text).ToList();
        output.WriteLine(string.Join(" | ", lines));
        Assert.Equal(["Output 3 (A1 OUT3): overcurrent, 1 trip, off until reset", "Fuel pump (B OUT5): overcurrent, 2 trips, off until reset"], lines);

        // the overload is gone, but a latched fault stays (firmware: "Fault requires power cycle")
        bus.Cmd("LOAD B 4 5");
        bus.Cmd("LOAD A1 2 2");
        rig.Step(2000);
        Assert.Equal((OutState.Fault, OutState.Fault), (pump.State, lamp.State));

        Assert.Null(await svc.ResetFaultsAsync(true, t => { rig.Step(t.TotalMilliseconds); return Task.CompletedTask; }, TimeSpan.FromMilliseconds(gapMs)));
        rig.Step(600);
        Assert.Equal((OutState.On, OutState.On), (pump.State, lamp.State));
        Assert.True(bus.Pin("B", 4));
        Assert.True(bus.Pin("A1", 2));
        Assert.Empty(PdmFaults.Lines(svc.BuildView(), _ => true));
        Assert.All(rig.All, d => Assert.Equal(keptInput, d.CustomPdm!.MasterRetryInput));

        // the boards hold the kept value again (a fresh PC reads it), and nothing was burned
        var pc2 = PcTool.For(bus, 15, 0x580);
        Assert.True(pc2.ReadAll());
        Assert.Equal(keptInput, pc2.Dev.CustomPdm!.MasterRetryInput);

        // an output that is still overloaded trips again after the reset
        bus.Cmd("LOAD A1 2 7");
        rig.Step(1500);
        Assert.Equal(OutState.Fault, lamp.State);
        Assert.Null(await svc.ResetFaultsAsync(true, t => { rig.Step(t.TotalMilliseconds); return Task.CompletedTask; }, TimeSpan.FromMilliseconds(gapMs)));
        rig.Step(1500);
        Assert.Equal((OutState.On, OutState.Fault), (pump.State, lamp.State));
    }
}
