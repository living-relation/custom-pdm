using domain.CustomPdm;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// Route B phase B2: one Read All / Write All / Burn for the three boards (domain/CustomPdm/PdmOps.cs through
// application/Services/PdmOpsService.cs and the real DeviceManager / FwDevice / ParamProtocol), against FakeBoards.
public class PdmOpsTests
{
    private const PdmStepState Ok = PdmStepState.Ok, Failed = PdmStepState.Failed, NotDone = PdmStepState.NotDone;

    private static FakePdm ReadPdm()
    {
        var pdm = new FakePdm();
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        Assert.Equal([Ok, Ok, Ok], pdm.States);
        return pdm;
    }

    private static void Edit(FakePdm pdm)
    {
        pdm.Dev("A1").Outputs[2].CurrentLimit = 5.5;
        pdm.Dev("A2").Outputs[4].CurrentLimit = 6.5;
        pdm.Dev("B").DigitalInputs[8].DebounceTime = 55;
    }

    private static float F(FakeBoard b, int index, int sub) => BitConverter.ToSingle(b.Values[(index, sub)]);
    private static int I(FakeBoard b, int index, int sub) => BitConverter.ToInt32(b.Values[(index, sub)]);

    // (A1 OUT3 limit, A2 OUT5 limit, B IN9 debounce) as the boards hold them
    private static (float, float, int) OnBoards(FakePdm pdm) =>
        (F(pdm.Boards["A1"], 0x1002, 2), F(pdm.Boards["A2"], 0x1004, 2), I(pdm.Boards["B"], 0x1208, 3));

    private static List<int> OrderOf(FakePdm pdm, MessageCommand cmd) =>
        pdm.Sent.Where(s => s.Cmd == cmd).Select(s => s.Id - 1).ToList();

    [Fact]
    public void ReadAllReadsTheThreeBoardsOneAfterAnother()
    {
        var pdm = new FakePdm();
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        Assert.Equal(PdmOpKind.ReadAll, pdm.Service.Ops.LastOp);
        Assert.False(pdm.Service.Ops.Busy);
        Assert.Equal(["Ok: read OK", "Ok: read OK", "Ok: read OK"], PdmOps.Roles.Select(pdm.Line));
        Assert.All(PdmOps.Roles, r => Assert.True(pdm.Dev(r).FullReadDone && !pdm.Dev(r).ConfigMismatch));
        Assert.Equal([0x500, 0x540, 0x580], OrderOf(pdm, MessageCommand.ReadAll));
        Assert.Equal((CanBitRate.BitRate1000K, 7.5), (pdm.Dev("A2").BitRate, pdm.Dev("A2").Outputs[0].CurrentLimit));
        // A2 was asked only after A1's read result and matching config check, B only after A2's
        AssertAfter(pdm, 0x541, MessageCommand.ReadAll, "A1", "Read Successful");
        AssertAfter(pdm, 0x581, MessageCommand.ReadAll, "A2", "Read Successful");
    }

    // when the PC sent this frame, the board before had already given its result and a matching config check
    private static void AssertAfter(FakePdm pdm, int id, MessageCommand cmd, string roleBefore, string note)
    {
        var sent = pdm.Sent.First(s => s.Id == id && s.Cmd == cmd);
        Assert.Contains($"{roleBefore}: {note}", sent.Notes);
        Assert.Contains(roleBefore, sent.Matching);
    }

    [Fact]
    public void ReadAllGoesOnPastASilentBoardAndAnOfflineBoard()
    {
        var pdm = new FakePdm();
        pdm.Boards["A2"].Silent = true;
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        Assert.Equal([Ok, Failed, Ok], pdm.States);
        Assert.Equal("Failed: no reply (no complete read in 10 s)", pdm.Line("A2"));
        Assert.False(pdm.Dev("A2").FullReadDone);

        pdm.Boards["A2"].Silent = false;
        pdm.Offline.Add("A1");
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        Assert.Equal([Failed, Ok, Ok], pdm.States);
        Assert.Equal("Failed: offline: nothing sent", pdm.Line("A1"));
        Assert.Equal(1, pdm.Boards["A1"].Count(MessageCommand.ReadAll)); // only the first run asked A1
    }

    [Fact]
    public void WriteAllAndBurnAreRefusedUntilAllThreeBoardsAreReadWithTheReason()
    {
        var pdm = new FakePdm();
        Assert.Equal("A1: not read yet (Read All first); A2: not read yet (Read All first); B: not read yet (Read All first).",
            pdm.Blocked(PdmOpKind.WriteAll));
        Assert.Equal(pdm.Blocked(PdmOpKind.WriteAll), pdm.Run(PdmOpKind.WriteAll));
        Assert.Equal(pdm.Blocked(PdmOpKind.Burn), pdm.Run(PdmOpKind.Burn));
        Assert.Null(pdm.Blocked(PdmOpKind.ReadAll));

        pdm.Boards["B"].Silent = true;                 // two of three read
        pdm.Run(PdmOpKind.ReadAll);
        Assert.Equal("B: not read yet (Read All first).", pdm.Run(PdmOpKind.WriteAll));
        Assert.Equal("B: not read yet (Read All first).", pdm.Run(PdmOpKind.Burn));

        pdm.Boards["B"].Silent = false;
        pdm.Run(PdmOpKind.ReadAll);
        Assert.Null(pdm.Blocked(PdmOpKind.WriteAll));
        Assert.Null(pdm.Blocked(PdmOpKind.Burn));

        pdm.Offline.Add("A2");
        Assert.Equal("A2: offline.", pdm.Run(PdmOpKind.WriteAll));
        Assert.Equal("A2: offline.", pdm.Blocked(PdmOpKind.Burn));
        pdm.Offline.Clear();
        pdm.Adapter = false;
        Assert.All(Enum.GetValues<PdmOpKind>(), op => Assert.Equal(PdmOps.AdapterOffReason, pdm.Run(op)));

        // nothing but reads ever went to a board
        Assert.All(pdm.Boards.Values, b => Assert.Equal(0, b.Count(MessageCommand.WriteAll) + b.Count(MessageCommand.BurnParams)));
    }

    [Fact]
    public void AMissingBoardBlocksWriteAndBurnButNotRead()
    {
        var pdm = new FakePdm("A1", "B");
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        Assert.Equal(["Ok: read OK", "NotDone: not in the project", "Ok: read OK"], PdmOps.Roles.Select(pdm.Line));
        Assert.Equal("A2: not in the project.", pdm.Run(PdmOpKind.WriteAll));
        Assert.Equal("A2: not in the project.", pdm.Run(PdmOpKind.Burn));
        Assert.All(pdm.Boards.Values, b => Assert.Equal(0, b.Count(MessageCommand.WriteAll) + b.Count(MessageCommand.BurnParams)));

        var none = new FakePdm();
        none.Offline.UnionWith(PdmOps.Roles);
        Assert.Equal(PdmOps.NoBoardReason, none.Run(PdmOpKind.ReadAll));
    }

    [Fact]
    public void WriteAllWritesEachBoardInTurnAndNeverBurns()
    {
        var pdm = ReadPdm();
        var before = OnBoards(pdm);
        Edit(pdm);
        Assert.Null(pdm.Run(PdmOpKind.WriteAll));
        Assert.Equal([Ok, Ok, Ok], pdm.States);
        Assert.StartsWith("Ok: written OK", pdm.Line("A2"));
        Assert.NotEqual((5.5f, 6.5f, 55), before);
        Assert.Equal((5.5f, 6.5f, 55), OnBoards(pdm));
        Assert.Equal([0x500, 0x540, 0x580], OrderOf(pdm, MessageCommand.WriteAll));
        AssertAfter(pdm, 0x541, MessageCommand.WriteAll, "A1", "Write Successful");
        AssertAfter(pdm, 0x581, MessageCommand.WriteAll, "A2", "Write Successful");
        Assert.All(pdm.Boards.Values, b => Assert.Equal(0, b.Count(MessageCommand.BurnParams)));
    }

    [Fact]
    public void WriteAllStopsAtTheBoardThatDoesNotAnswer()
    {
        var pdm = ReadPdm();
        var before = OnBoards(pdm);
        Edit(pdm);
        pdm.Boards["A2"].Silent = true;                // still "connected" for the PC: it stops answering mid-way
        Assert.Null(pdm.Run(PdmOpKind.WriteAll));
        Assert.Equal([Ok, Failed, NotDone], pdm.States);
        Assert.Equal("Failed: no reply (write not confirmed in 90 s)", pdm.Line("A2"));
        Assert.Equal("NotDone: not written (run stopped at A2)", pdm.Line("B"));
        Assert.Equal((5.5f, before.Item2, before.Item3), OnBoards(pdm));
        Assert.Equal(0, pdm.Boards["B"].Count(MessageCommand.WriteAll));
        Assert.False(pdm.Service.Ops.Busy);

        // A1 fails: A2 and B are not touched
        var pdm2 = ReadPdm();
        Edit(pdm2);
        pdm2.Boards["A1"].Silent = true;
        pdm2.Run(PdmOpKind.WriteAll);
        Assert.Equal([Failed, NotDone, NotDone], pdm2.States);
        Assert.Equal(0, pdm2.Boards["A2"].Count(MessageCommand.WriteAll) + pdm2.Boards["B"].Count(MessageCommand.WriteAll));
    }

    [Fact]
    public void WriteAllNeedsTheMatchingConfigCheckOfEachBoard()
    {
        var pdm = ReadPdm();
        Edit(pdm);
        pdm.Boards["A2"].WrongCheckCrc = true;
        Assert.Null(pdm.Run(PdmOpKind.WriteAll));
        Assert.Equal([Ok, Failed, NotDone], pdm.States);
        Assert.Equal("Failed: written, but the config check after it did not confirm a match", pdm.Line("A2"));
        Assert.Equal(0, pdm.Boards["B"].Count(MessageCommand.WriteAll));

        // a burn now: the fresh check of A2 fails, so no board is burned
        Assert.Null(pdm.Run(PdmOpKind.Burn));
        Assert.Equal([NotDone, Failed, NotDone], pdm.States);
        Assert.All(pdm.Boards.Values, b => Assert.Equal(0, b.Count(MessageCommand.BurnParams)));
    }

    [Fact]
    public void BurnChecksAllThreeBoardsFirstThenBurnsEachInTurn()
    {
        var pdm = ReadPdm();
        Edit(pdm);
        pdm.Run(PdmOpKind.WriteAll);
        Assert.Null(pdm.Run(PdmOpKind.Burn));
        Assert.Equal(["Ok: burned OK (the board confirmed)", "Ok: burned OK (the board confirmed)", "Ok: burned OK (the board confirmed)"],
            PdmOps.Roles.Select(pdm.Line));
        Assert.Equal([1, 1, 1], pdm.Boards.Values.Select(b => b.Burns));
        Assert.Equal([0x500, 0x540, 0x580], OrderOf(pdm, MessageCommand.BurnParams));
        // every board's fresh config check went out before the first burn
        var firstBurn = pdm.Sent.FindIndex(s => s.Cmd == MessageCommand.BurnParams);
        var lastWrite = pdm.Sent.FindLastIndex(s => s.Cmd == MessageCommand.WriteAllComplete);
        Assert.All(new[] { 0x501, 0x541, 0x581 }, id =>
            Assert.Contains(pdm.Sent.Skip(lastWrite).Take(firstBurn - lastWrite), s => s.Id == id && s.Cmd == MessageCommand.CheckCrc));
    }

    [Fact]
    public void BurnIsRefusedForAllWhenOneBoardDiffersFromThePc()
    {
        var pdm = ReadPdm();
        pdm.Dev("A2").Outputs[4].CurrentLimit = 6.5;   // edited on the PC, not written: the old flag still says "match"
        Assert.Null(pdm.Blocked(PdmOpKind.Burn));
        Assert.Null(pdm.Run(PdmOpKind.Burn));
        Assert.Equal([NotDone, Failed, NotDone], pdm.States);
        Assert.Equal("Failed: PC settings differ from the board, or no reply to the config check: nothing burned", pdm.Line("A2"));
        Assert.Equal("NotDone: not burned (run stopped at A2)", pdm.Line("A1"));
        Assert.All(pdm.Boards.Values, b => Assert.Equal(0, b.Count(MessageCommand.BurnParams)));

        // value put back: the same button works, no read or write needed in between
        pdm.Dev("A2").Outputs[4].CurrentLimit = 20.0;
        Assert.Null(pdm.Run(PdmOpKind.Burn));
        Assert.Equal([Ok, Ok, Ok], pdm.States);
        Assert.Equal([1, 1, 1], pdm.Boards.Values.Select(b => b.Burns));
    }

    [Fact]
    public void BurnStopsAtTheBoardThatReportsAFailedBurn()
    {
        var pdm = ReadPdm();
        pdm.Boards["A2"].BurnResult = 0;               // the firmware's own "burn failed" answer
        Assert.Null(pdm.Run(PdmOpKind.Burn));
        Assert.Equal([Ok, Failed, NotDone], pdm.States);
        Assert.Equal("Failed: no \"burn successful\" reply in 8 s (burn failed or no answer)", pdm.Line("A2"));
        Assert.Equal("NotDone: not burned (run stopped at A2)", pdm.Line("B"));
        Assert.Equal([1, 0, 0], pdm.Boards.Values.Select(b => b.Burns));
        Assert.Equal(0, pdm.Boards["B"].Count(MessageCommand.BurnParams));
    }

    [Fact]
    public void OneRunAtATime()
    {
        var pdm = ReadPdm();
        pdm.Boards["A1"].Silent = true;
        Assert.Null(pdm.Service.Start(PdmOpKind.WriteAll, true, pdm.Clock));
        Assert.True(pdm.Service.Ops.Busy);
        Assert.Equal(PdmStepState.Running, pdm.Service.Ops.Results[0].State);
        Assert.All(Enum.GetValues<PdmOpKind>(), op => Assert.Equal(PdmOps.BusyReason, pdm.Service.Start(op, true, pdm.Clock)));
        Assert.Equal(PdmOps.BusyReason, pdm.Blocked(PdmOpKind.Burn));
    }

    // The per-board pages keep their own buttons: the stock calls work next to the PDM service
    [Fact]
    public void PerBoardCallsStillWork()
    {
        var pdm = ReadPdm();
        var a2 = pdm.Dev("A2");
        a2.Outputs[4].CurrentLimit = 6.5;
        Assert.True(pdm.Mgr.WriteAllDeviceConfig(a2.Guid));
        pdm.Pump();
        Assert.Equal(6.5f, F(pdm.Boards["A2"], 0x1004, 2));
        Assert.False(a2.ConfigMismatch);
        Assert.True(pdm.Mgr.BurnSettings(a2.Guid));
        pdm.Pump();
        Assert.Equal([0, 1, 0], pdm.Boards.Values.Select(b => b.Burns));
    }
}
