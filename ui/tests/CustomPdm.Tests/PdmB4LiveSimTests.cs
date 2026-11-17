using application.Services;
using domain.CustomPdm;
using domain.Devices;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// Route B phase B4 against the real firmware logic (all three boards on one bus, one real DeviceManager): links made
// with PdmLinks reach the boards through the /pdm Write All, the target output follows the source input over CAN
// (ground truth: the PROFET IN pin), and each link's loss setting acts when the source board goes silent.
[Collection("sim")]
public class PdmB4LiveSimTests(ITestOutputHelper output)
{
    private static PdmOpsService Service(PdmRig rig) => new(rig.Mgr) { AutoTick = false };

    private string? Run(PdmRig rig, PdmOpsService svc, PdmOpKind op)
    {
        var t = rig.SimMs;
        var refused = svc.Start(op, true, rig.Now);
        while (refused == null && svc.Ops.Busy && rig.SimMs - t < 120000)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }
        output.WriteLine($"{op}: {refused ?? string.Join(" | ", svc.Ops.Results.Select(r => $"{r.Role} {r.State}: {r.Text}"))} ({rig.SimMs - t:F0} ms sim time)");
        return refused;
    }

    private static readonly PdmStepState[] AllOk = [PdmStepState.Ok, PdmStepState.Ok, PdmStepState.Ok];

    private static void In(SimBus bus, string board, int i, bool on) => bus.Cmd($"IN {board} {i} {(on ? "12v" : "gnd")}");

    // sim ms until output o of board is at `level` (1 ms steps), or -1
    private static double Until(SimBus bus, PdmRig rig, string board, int o, bool level, int maxMs = 3000)
    {
        var t = rig.SimMs;
        while (rig.SimMs - t <= maxMs)
        {
            if (bus.Pin(board, o) == level) return rig.SimMs - t;
            rig.Step(1);
        }
        return -1;
    }

    private static string LinksText(PdmView v) =>
        string.Join("; ", PdmLinks.Links(v).Select(l => $"{l.In.Number}->{l.Out.Number} {l.Loss} {l.SlotText}"));

    // A1 IN1 -> B OUT5 (off), A1 IN2 -> B OUT6 (hold), A1 IN3 -> B OUT7 (on), B IN1 -> B OUT8 (same board),
    // B IN10 -> A1 OUT1 (bit 9: byte 1 of msg 37)
    private static readonly (int In, int Out, PdmLinkLoss Loss)[] Plan =
        [(1, 21, PdmLinkLoss.Off), (2, 22, PdmLinkLoss.Hold), (3, 23, PdmLinkLoss.On), (15, 24, PdmLinkLoss.Off), (24, 1, PdmLinkLoss.Off)];

    private static void MakeLinks(PdmRig rig, PdmView v)
    {
        foreach (var (i, o, loss) in Plan)
        {
            Assert.Null(PdmLinks.Add(v, i, o, loss));
            v.Outputs.Single(r => r.Number == o).Output.Enabled = true;
            v.Inputs.Single(r => r.Number == i).Digital!.Enabled = true;
        }
    }

    [SimFact]
    public void LinksFollowTheInputAndActOnLinkLoss()
    {
        using var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        var svc = Service(rig);
        var v = svc.BuildView();
        MakeLinks(rig, v);
        output.WriteLine(LinksText(v));
        var fanBefore = rig.A2.CanInputs.Skip(24).Take(4).Select(c => (c.Enabled, c.Id, c.Operand)).ToList();
        Assert.Null(Run(rig, svc, PdmOpKind.WriteAll));
        Assert.Equal(AllOk, svc.Ops.Results.Select(r => r.State));
        foreach (var (b, i) in new[] { ("A1", 0), ("A1", 1), ("A1", 2), ("B", 0), ("B", 9) }) In(bus, b, i, false);
        rig.Step(500);
        Assert.False(bus.Pin("B", 4));
        Assert.False(bus.Pin("B", 6)); // 'on' link with its input off: off while the frames arrive

        // the input on board A1 drives B OUT5; reaction time input -> pin over CAN
        var times = new List<double>();
        for (var n = 0; n < 5; n++)
        {
            In(bus, "A1", 0, true);
            var tOn = Until(bus, rig, "B", 4, true);
            Assert.True(tOn >= 0, "B OUT5 did not follow A1 IN1 on");
            Assert.True(rig.A1.DigitalInputs[0].State, "the PC sees A1 IN1 on");
            rig.Step(37 * n % 100 + 1); // shift the next change against the 100 ms status period
            In(bus, "A1", 0, false);
            var tOff = Until(bus, rig, "B", 4, false);
            Assert.True(tOff >= 0, "B OUT5 did not follow A1 IN1 off");
            times.AddRange([tOn, tOff]);
            rig.Step(53);
        }
        output.WriteLine($"cross-board reaction A1 IN1 -> B OUT5 pin: {string.Join(", ", times.Select(t => t.ToString("F0")))} ms (min {times.Min():F0}, max {times.Max():F0})");
        Assert.True(times.Max() <= 160, $"reaction {times.Max()} ms"); // 20 ms debounce + <= 100 ms status period + CAN

        // bit 9 of msg 37 (B IN10, byte 1) -> A1 OUT1; same-board B IN1 -> B OUT8 needs no CAN
        In(bus, "B", 9, true);
        Assert.True(Until(bus, rig, "A1", 0, true) >= 0, "A1 OUT1 did not follow B IN10");
        In(bus, "B", 9, false);
        Assert.True(Until(bus, rig, "A1", 0, false) >= 0);
        In(bus, "B", 0, true);
        var same = Until(bus, rig, "B", 7, true);
        output.WriteLine($"same-board B IN1 -> B OUT8: {same:F0} ms");
        Assert.True(same is >= 0 and < 60);
        In(bus, "B", 0, false);
        Assert.True(Until(bus, rig, "B", 7, false) >= 0);

        // link loss: A1 goes silent. off-link ON -> OFF after 1 s; hold-link ON stays ON; on-link OFF -> ON after 1 s
        In(bus, "A1", 0, true);
        In(bus, "A1", 1, true);
        In(bus, "A1", 2, false);
        rig.Step(300);
        Assert.Equal([true, true, false], new[] { 4, 5, 6 }.Select(o => bus.Pin("B", o)));
        bus.Cmd("LINK A1 off");
        var offAt = Until(bus, rig, "B", 4, false);
        var onAt = Until(bus, rig, "B", 6, true);
        output.WriteLine($"A1 silent: off-link OFF after {offAt:F0} ms, on-link ON {onAt:F0} ms later");
        Assert.InRange(offAt, 850, 1250); // 1 s after the LAST frame heard (status period 100 ms)
        Assert.InRange(onAt, 0, 150);
        rig.Step(1000);
        Assert.Equal([false, true, true], new[] { 4, 5, 6 }.Select(o => bus.Pin("B", o)));
        Assert.False(bus.Pin("B", 7)); // same-board link untouched by A1's loss
        // frames back: every link follows its input again
        bus.Cmd("LINK A1 on");
        Assert.True(Until(bus, rig, "B", 4, true) >= 0);
        Assert.True(Until(bus, rig, "B", 6, false) >= 0, "on-link back to its input (off)");
        In(bus, "A1", 1, false);
        Assert.True(Until(bus, rig, "B", 5, false) >= 0, "hold-link follows again");
        // hold keeps OFF too
        bus.Cmd("LINK A1 off");
        In(bus, "A1", 1, true); // not heard
        rig.Step(1500);
        Assert.False(bus.Pin("B", 5));
        bus.Cmd("LINK A1 on");
        Assert.True(Until(bus, rig, "B", 5, true) >= 0);

        // A fresh PC (as after an app restart) reads the boards: the same links, the fan slots as before
        var pc2 = PdmLiveSimTests.Boot(bus);
        var svc2 = Service(pc2);
        Assert.Null(Run(pc2, svc2, PdmOpKind.ReadAll));
        Assert.Equal(AllOk, svc2.Ops.Results.Select(r => r.State));
        var v2 = svc2.BuildView();
        output.WriteLine(LinksText(v2));
        Assert.Equal(LinksText(v), LinksText(v2));
        Assert.Equal(fanBefore, pc2.A2.CanInputs.Skip(24).Take(4).Select(c => (c.Enabled, c.Id, c.Operand)).ToList());
        Assert.Null(PdmLinked.FanLayoutProblem(pc2.A2));
        Assert.Equal(new PdmFanThresholds(45, 40), PdmLinked.FanThresholds(pc2.A2));
        Assert.All(PdmLinks.Slots(v2).Single(s => s.Board == "A2").CanInputs.Skip(24).Take(4),
            u => Assert.Equal("fan logic (A1 / B board temperature), reserved", u.UsedBy));

        // slot exhaustion: B's free slots taken by hand on the PC -> a new link is refused, nothing is sent
        var sent = pc2.Sent.Count;
        foreach (var c in pc2.B.CanInputs.Where(c => !c.Enabled && c.Id == 0)) (c.Enabled, c.Id) = (true, 0x7F0);
        Assert.Equal("B has too few free CAN inputs: this link needs 1, 0 free (5 used by links, the rest by the fan logic or set by hand).",
            PdmLinks.Add(v2, 4, 17));
        pc2.Step(200);
        Assert.Equal(sent, pc2.Sent.Count);
    }

    // Remove a link: Write All, the slot is free on the board and the output no longer follows the input
    [SimFact]
    public void RemovedLinkFreesTheSlotOnTheBoard()
    {
        using var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        var svc = Service(rig);
        var v = svc.BuildView();
        MakeLinks(rig, v);
        Assert.Null(Run(rig, svc, PdmOpKind.WriteAll));
        In(bus, "A1", 0, true);
        Assert.True(Until(bus, rig, "B", 4, true) >= 0);

        Assert.Null(PdmLinks.Remove(v, 21));
        Assert.Null(Run(rig, svc, PdmOpKind.WriteAll));
        Assert.Equal(AllOk, svc.Ops.Results.Select(r => r.State));
        rig.Step(300);
        Assert.False(bus.Pin("B", 4)); // trigger none: off although A1 IN1 is still on

        var pc2 = PdmLiveSimTests.Boot(bus);
        var svc2 = Service(pc2);
        Assert.Null(Run(pc2, svc2, PdmOpKind.ReadAll));
        var v2 = svc2.BuildView();
        Assert.DoesNotContain(PdmLinks.Links(v2), l => l.Out.Number == 21);
        Assert.True(PdmLinks.IsFreeSlot(v2.Boards.Single(b => b.Role == "B"), 0));
        Assert.Equal(0, pc2.B.Outputs[4].Input);
    }
}
