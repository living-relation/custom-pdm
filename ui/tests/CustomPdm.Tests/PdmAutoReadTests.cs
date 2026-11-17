using domain.CustomPdm;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// p2a (Dan, 2026-11-16): /pdm reads a board by itself when it connects; with unsaved PC edits for that board it asks
// first (domain/CustomPdm/PdmAutoRead.cs through PdmOpsService), against FakeBoards. Nothing is written or burned.
public class PdmAutoReadTests
{
    private const PdmStepState Ok = PdmStepState.Ok;

    private static FakePdm Auto(bool newPdm = false)
    {
        var pdm = new FakePdm();
        if (newPdm)
            foreach (var r in PdmOps.Roles) PdmFactoryDefaults.Apply(pdm.Dev(r), r);
        pdm.Service.AutoRead = true;
        return pdm;
    }

    private static int Reads(FakePdm pdm, string role) => pdm.Boards[role].Count(MessageCommand.ReadAll);
    private static string[] Asks(FakePdm pdm) => pdm.Service.ConnectAsks().Select(b => b.Role).ToArray();

    private static void NoWriteNoBurn(FakePdm pdm) =>
        Assert.DoesNotContain(pdm.Sent, s => s.Cmd is MessageCommand.WriteAll or MessageCommand.WriteAllVal or MessageCommand.BurnParams);

    private static void Reconnect(FakePdm pdm, string role)
    {
        pdm.Offline.Add(role);
        pdm.Rounds(2);
        pdm.Offline.Remove(role);
    }

    [Fact]
    public void ConnectWithNoEditsReadsEveryBoardOneAfterAnother()
    {
        var pdm = Auto();
        pdm.Settle();
        Assert.True(pdm.Service.Ops.LastOnConnect);
        Assert.Equal([Ok, Ok, Ok], pdm.States);
        Assert.All(PdmOps.Roles, r => Assert.True(pdm.Dev(r).FullReadDone));
        Assert.Equal(7.5, pdm.Dev("A2").Outputs[0].CurrentLimit);          // the board's value, not the PC default
        Assert.All(PdmOps.Roles, r => Assert.Equal(1, Reads(pdm, r)));
        Assert.Empty(Asks(pdm));
        // one at a time: A2 asked only after A1's result and matching check, B after A2's
        Assert.Equal([0x500, 0x540, 0x580], pdm.Sent.Where(s => s.Cmd == MessageCommand.ReadAll).Select(s => s.Id - 1));
        var a2 = pdm.Sent.First(s => s.Id == 0x541 && s.Cmd == MessageCommand.ReadAll);
        Assert.Contains("A1: Read Successful", a2.Notes);
        Assert.Contains("A1", a2.Matching);
        var b = pdm.Sent.First(s => s.Id == 0x581 && s.Cmd == MessageCommand.ReadAll);
        Assert.Contains("A2: Read Successful", b.Notes);
        // after it the guards are satisfied as after a hand Read All
        Assert.Null(pdm.Blocked(PdmOpKind.WriteAll));
        pdm.Rounds(20);
        Assert.All(PdmOps.Roles, r => Assert.Equal(1, Reads(pdm, r)));     // no second read while they stay connected
        NoWriteNoBurn(pdm);
    }

    [Fact]
    public void OffWhenNotTurnedOn()
    {
        var pdm = new FakePdm();
        pdm.Rounds(20);
        Assert.All(PdmOps.Roles, r => Assert.Equal(0, Reads(pdm, r)));
    }

    [Fact]
    public void ReconnectWithoutEditsReadsAgain()
    {
        var pdm = Auto();
        pdm.Settle();
        pdm.Boards["A2"].Values[(0x1000, 2)] = BitConverter.GetBytes(9.5f); // changed on the board side only
        Reconnect(pdm, "A2");
        pdm.Settle();
        Assert.Equal([1, 2, 1], PdmOps.Roles.Select(r => Reads(pdm, r)));
        Assert.Equal(9.5, pdm.Dev("A2").Outputs[0].CurrentLimit);
        Assert.Equal("Ok: read OK", pdm.Line("A2"));
        Assert.Equal("Ok: read OK", pdm.Line("A1"));   // line of the earlier read on connect kept
        NoWriteNoBurn(pdm);
    }

    [Fact]
    public void ReconnectWithEditsAsksAndKeepPcReadsNothing()
    {
        var pdm = Auto();
        pdm.Settle();
        pdm.Dev("A2").Outputs[3].CurrentLimit = 4.5;   // a PC edit, not written
        Assert.True(pdm.Service.AutoReader.HasEdits(pdm.Dev("A2")));
        Assert.False(pdm.Service.AutoReader.HasEdits(pdm.Dev("A1")));
        Reconnect(pdm, "A2");
        pdm.Rounds(30);
        Assert.Equal(["A2"], Asks(pdm));
        Assert.Equal(1, Reads(pdm, "A2"));
        Assert.Equal(4.5, pdm.Dev("A2").Outputs[3].CurrentLimit);

        pdm.Service.AnswerConnect(pdm.Dev("A2"), PdmConnectAnswer.KeepPc);
        pdm.Rounds(30);
        Assert.Empty(Asks(pdm));
        Assert.Equal(1, Reads(pdm, "A2"));
        Assert.Equal(4.5, pdm.Dev("A2").Outputs[3].CurrentLimit);
        Assert.Null(pdm.Blocked(PdmOpKind.WriteAll));    // "Write All later" stays possible
        NoWriteNoBurn(pdm);

        Reconnect(pdm, "A2");                            // asked again at the next connect
        pdm.Rounds(5);
        Assert.Equal(["A2"], Asks(pdm));
    }

    [Fact]
    public void ReconnectWithEditsAsksAndTakeTheBoardsReads()
    {
        var pdm = Auto();
        pdm.Settle();
        pdm.Dev("B").DigitalInputs[2].DebounceTime = 77;
        Reconnect(pdm, "B");
        pdm.Rounds(5);
        Assert.Equal(["B"], Asks(pdm));
        pdm.Service.AnswerConnect(pdm.Dev("B"), PdmConnectAnswer.TakeBoard);
        pdm.Settle();
        Assert.Empty(Asks(pdm));
        Assert.Equal([1, 1, 2], PdmOps.Roles.Select(r => Reads(pdm, r)));
        Assert.NotEqual(77, pdm.Dev("B").DigitalInputs[2].DebounceTime);
        Assert.False(pdm.Service.AutoReader.HasEdits(pdm.Dev("B")));
        Assert.Equal("Ok: read OK", pdm.Line("B"));
        NoWriteNoBurn(pdm);
    }

    [Fact]
    public void AnEditUndoneIsNoEdit()
    {
        var pdm = Auto();
        pdm.Settle();
        var o = pdm.Dev("A1").Outputs[1];
        var was = o.CurrentLimit;
        o.CurrentLimit = was + 1;
        Assert.True(pdm.Service.AutoReader.HasEdits(pdm.Dev("A1")));
        o.CurrentLimit = was;
        Assert.False(pdm.Service.AutoReader.HasEdits(pdm.Dev("A1")));
    }

    [Fact]
    public void NewPdmAsksInsteadOfWipingTheFactoryConfig()
    {
        var pdm = Auto(newPdm: true);
        pdm.Rounds(30);
        Assert.Equal(PdmOps.Roles, Asks(pdm));
        Assert.All(PdmOps.Roles, r => Assert.Equal(0, Reads(pdm, r)));
        Assert.True(pdm.Dev("A2").CustomPdm!.FactoryNew);

        // Keep for all three, then Write All: written = no edits any more, a reconnect then reads without asking
        foreach (var r in PdmOps.Roles) pdm.Service.AnswerConnect(pdm.Dev(r), PdmConnectAnswer.KeepPc);
        Assert.Null(pdm.Run(PdmOpKind.WriteAll));
        Assert.Equal([Ok, Ok, Ok], pdm.States);
        Assert.All(PdmOps.Roles, r => Assert.False(pdm.Service.AutoReader.HasEdits(pdm.Dev(r))));
        Reconnect(pdm, "A1");
        pdm.Settle();
        Assert.Empty(Asks(pdm));
        Assert.Equal([1, 0, 0], PdmOps.Roles.Select(r => Reads(pdm, r)));
        Assert.Equal(0, pdm.Boards["A1"].Count(MessageCommand.BurnParams));
    }

    // A board that reconnects while a Write All runs is read only after the run ended
    [Fact]
    public void ReconnectMidWriteAllWaitsForTheRunToEnd()
    {
        var pdm = Auto();
        pdm.Settle();
        pdm.MaxFramesPerPump = 200;                      // a slow bus: the write of one board takes several rounds
        Assert.Null(pdm.Service.Start(PdmOpKind.WriteAll, true, pdm.Clock));
        pdm.Rounds(3);
        Assert.True(pdm.Service.Ops.Busy);
        Reconnect(pdm, "A1");                            // A1 has no edits: a plain read on connect, later
        DateTime? ended = null;
        for (var i = 0; i < 6000 && ended == null; i++)
        {
            pdm.Rounds(1);
            if (i < 3) Assert.Equal(["A1"], pdm.Service.ConnectWaiting().Select(b => b.Role));
            if (pdm.Service.Ops.LastOp != PdmOpKind.WriteAll) ended = pdm.Clock;
        }
        Assert.NotNull(ended);
        pdm.Settle();
        var a1Reads = pdm.SentAt.Where(s => s.Id == 0x501 && s.Cmd == MessageCommand.ReadAll).Select(s => s.At).ToList();
        var lastWrite = pdm.SentAt.Where(s => s.Cmd == MessageCommand.WriteAllVal).Max(s => s.At);
        Assert.Equal(2, a1Reads.Count);                  // the first read on connect + the one after the run
        Assert.True(a1Reads[1] > lastWrite, "A1 read while the Write All was still running");
        Assert.True(pdm.Service.Ops.LastOnConnect);
        Assert.Equal([2, 1, 1], PdmOps.Roles.Select(r => Reads(pdm, r)));
        Assert.Empty(pdm.Service.ConnectWaiting());
    }

    // With edits: asked at once, even while the Write All runs. "Take the board's" waits for the run to end.
    [Fact]
    public void AskDuringWriteAllAndTakeWaitsForTheRun()
    {
        var pdm = Auto();
        pdm.Settle();
        pdm.MaxFramesPerPump = 200;
        pdm.Boards["B"].NoWriteResult = true;            // B never confirms its write: the run fails at B
        pdm.Dev("B").DigitalInputs[0].DebounceTime = 66;
        Assert.Null(pdm.Service.Start(PdmOpKind.WriteAll, true, pdm.Clock));
        pdm.Rounds(3);
        Reconnect(pdm, "B");
        pdm.Rounds(2);
        Assert.True(pdm.Service.Ops.Busy);
        Assert.Equal(["B"], Asks(pdm));
        pdm.Service.AnswerConnect(pdm.Dev("B"), PdmConnectAnswer.TakeBoard);
        pdm.Rounds(1);
        Assert.Equal(["B"], pdm.Service.ConnectWaiting().Select(b => b.Role));
        var readsBefore = Reads(pdm, "B");
        while (pdm.Service.Ops.LastOp == PdmOpKind.WriteAll && pdm.Service.Ops.Busy)
        {
            Assert.Equal(readsBefore, Reads(pdm, "B"));
            pdm.Rounds(1);
        }
        pdm.Settle();
        Assert.Equal(readsBefore + 1, Reads(pdm, "B"));
        Assert.NotEqual(66, pdm.Dev("B").DigitalInputs[0].DebounceTime);
        Assert.Equal(0, pdm.Boards["B"].Count(MessageCommand.BurnParams));
    }

    // The three boards connect at once, a while after the app started (first look = connect)
    [Fact]
    public void BoardsThatComeOnlineLaterAreReadOneAtATime()
    {
        var pdm = new FakePdm();
        foreach (var r in PdmOps.Roles) pdm.Offline.Add(r);
        pdm.Service.AutoRead = true;
        pdm.Rounds(10);
        Assert.All(PdmOps.Roles, r => Assert.Equal(0, Reads(pdm, r)));
        pdm.Offline.Clear();
        pdm.Settle();
        Assert.Equal([1, 1, 1], PdmOps.Roles.Select(r => Reads(pdm, r)));
        var order = pdm.Sent.Where(s => s.Cmd is MessageCommand.ReadAll or MessageCommand.CheckCrc).Select(s => (s.Id - 1, s.Cmd)).ToList();
        // each board's read is followed by its own check before the next board is asked
        var reads = order.Select((x, i) => (x, i)).Where(p => p.x.Cmd == MessageCommand.ReadAll).Select(p => p.i).ToList();
        Assert.Equal(3, reads.Count);
        Assert.Contains(order.Skip(reads[0]).Take(reads[1] - reads[0]), x => x == (0x500, MessageCommand.CheckCrc));
        Assert.Contains(order.Skip(reads[1]).Take(reads[2] - reads[1]), x => x == (0x540, MessageCommand.CheckCrc));
        NoWriteNoBurn(pdm);
    }
}
