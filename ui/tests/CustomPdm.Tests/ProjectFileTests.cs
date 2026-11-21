using System.Text.RegularExpressions;
using application.Services;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using domain.Interfaces;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace CustomPdm.Tests;

// uipolish (2026-11-21): a project file saved by the app loads as WRITABLE (PdmProjectFile.cs); with a PDM on the bus
// /pdm asks ONE question, and "Keep the PC's settings" writes the file onto a blank or another PDM with no Read All.
public class ProjectFileTests
{
    private static ConfigFileManager Files() => new(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());

    private static string TempFile(string name) => Path.Combine(Path.GetTempPath(), $"cpdm-{name}-{Guid.NewGuid():N}.json");

    // A PDM that was read, given a setup, and saved: the file a user makes with the app
    private static async Task<string> SavedSetup()
    {
        var a = new FakePdm();
        Assert.Null(a.Run(PdmOpKind.ReadAll));
        a.Dev("B").Outputs[4].Name = "Fuel pump";
        a.Dev("B").Outputs[4].CurrentLimit = 12;
        a.Dev("A1").DigitalInputs[2].Name = "Ignition";
        a.Dev("A1").DigitalInputs[2].Enabled = true;
        a.Dev("A2").CustomPdm!.TempCritSoonMargin = 9;
        var path = TempFile("setup");
        await Files().SaveDevices(a.Mgr.GetDevices(), path);
        return path;
    }

    private static byte[] Wire(FwDevice d, int index, int sub) =>
        domain.Common.ParamCodec.ToFrame(MessageCommand.Null, d.Params.Single(p => p.Index == index && p.SubIndex == sub), 0).Payload[4..8];

    // every param of the PC device is what the board now holds
    internal static void AssertBoardHoldsThePcValues(FakePdm pdm, string role)
    {
        var dev = pdm.Dev(role);
        var differ = dev.Params.Where(p => !Wire(dev, p.Index, p.SubIndex).SequenceEqual(pdm.Boards[role].Values[(p.Index, p.SubIndex)]))
            .Select(p => p.Name).ToList();
        Assert.Empty(differ);
    }

    [Fact]
    public async Task ASavedProjectLoadsAsWritableAndGoesOntoABlankPdmWithoutARead()
    {
        var path = await SavedSetup();
        Assert.Equal(3, Regex.Matches(File.ReadAllText(path), "\"completeSettings\": true").Count);

        var b = new FakePdm();   // another PC session, blank boards (factory values)
        b.Open((await Files().LoadDevices(path))!);
        Assert.All(b.View.Boards, x => Assert.True(x.Device.CustomPdm!.FromFile));
        Assert.All(b.View.Boards, x => Assert.False(x.Device.FullReadDone));
        Assert.Null(b.Blocked(PdmOpKind.WriteAll));

        Assert.Null(b.Run(PdmOpKind.WriteAll));
        Assert.All(b.States, s => Assert.Equal(PdmStepState.Ok, s));
        Assert.All(b.Boards.Values, x => Assert.Equal(0, x.Count(MessageCommand.ReadAll)));   // no Read All first
        foreach (var role in PdmOps.Roles) AssertBoardHoldsThePcValues(b, role);
        Assert.Equal(12, b.Dev("B").Outputs[4].CurrentLimit);
        Assert.Equal(("Fuel pump", "Ignition", 9), (b.Dev("B").Outputs[4].Name, b.Dev("A1").DigitalInputs[2].Name, b.Dev("A2").CustomPdm!.TempCritSoonMargin));

        // saved again from the loaded project (still never read): still a complete set
        var again = TempFile("again");
        await Files().SaveDevices(b.Mgr.GetDevices(), again);
        Assert.Equal(3, Regex.Matches(File.ReadAllText(again), "\"completeSettings\": true").Count);
    }

    // The safety that stays: a hand-added board that was never read holds stock PC defaults (500K, A2 = A1's values)
    [Fact]
    public async Task AHandAddedNeverReadProjectStaysBlockedAlsoAfterSaveAndLoad()
    {
        var a = new FakePdm();   // hand-added, never read
        Assert.Contains("not read yet", a.Blocked(PdmOpKind.WriteAll));
        var path = TempFile("stock");
        await Files().SaveDevices(a.Mgr.GetDevices(), path);
        Assert.Equal(3, Regex.Matches(File.ReadAllText(path), "\"completeSettings\": false").Count);

        var b = new FakePdm();
        b.Open((await Files().LoadDevices(path))!);
        Assert.All(b.View.Boards, x => Assert.False(x.Device.CustomPdm!.FromFile));
        Assert.Equal("A1: not read yet (Read All first); A2: not read yet (Read All first); B: not read yet (Read All first).",
            b.Blocked(PdmOpKind.WriteAll));
        Assert.False(b.Mgr.WriteAllDeviceConfig(b.Dev("A1").Guid));   // the stock per-board Write All is refused too
        b.Pump();
        Assert.All(b.Boards.Values, x => Assert.Equal(0, x.Count(MessageCommand.WriteAll)));

        // one board read, the others not: only that one is saved as complete
        Assert.Null(a.Run(PdmOpKind.ReadAll));
        a.Mgr.AddDevice("fwD:14", "extra", 0x600);
        await Files().SaveDevices(a.Mgr.GetDevices(), path);
        var loaded = (await Files().LoadDevices(path))!.OfType<FwDevice>().ToDictionary(d => d.Name, d => d.CustomPdm!.FromFile);
        Assert.Equal((true, true, true, false), (loaded["A1"], loaded["A2"], loaded["B"], loaded["extra"]));
    }

    // Files saved before the marker existed: complete when on our factory 1000K with a valid 0x7F00 block
    [Fact]
    public async Task AFileFromBeforeTheMarkerIsJudgedByItsBitRate()
    {
        static string Strip(string path)
        {
            var text = Regex.Replace(File.ReadAllText(path), ",\\s*\"completeSettings\": (true|false)", "");
            Assert.DoesNotContain("completeSettings", text);
            File.WriteAllText(path, text);
            return path;
        }

        var good = (await Files().LoadDevices(Strip(await SavedSetup())))!.OfType<FwDevice>().ToList();
        Assert.Equal(3, good.Count);
        Assert.All(good, d => Assert.True(d.CustomPdm!.FromFile));

        var stock = TempFile("old-stock");
        await Files().SaveDevices(new FakePdm().Mgr.GetDevices(), stock);
        var bad = (await Files().LoadDevices(Strip(stock)))!.OfType<FwDevice>().ToList();
        Assert.Equal(3, bad.Count);
        Assert.All(bad, d => Assert.Equal(CanBitRate.BitRate500K, d.BitRate));
        Assert.All(bad, d => Assert.False(d.CustomPdm!.FromFile));

        // 1000K but a broken 0x7F00 block: not complete
        var broken = (await Files().LoadDevices(Strip(await SavedSetup())))!.OfType<FwDevice>().First();
        broken.CustomPdm!.CompleteSettings = null;
        broken.CustomPdm.TempCritHyst = 0;
        Assert.Empty(PdmProjectFile.MarkLoaded([broken]));
        Assert.False(broken.CustomPdm.FromFile);
    }

    // With the PDM on the bus the opened project is not read over: ONE question, and Keep writes it
    [Fact]
    public async Task AnOpenedProjectAsksOneQuestionAndKeepWritesItToThePdm()
    {
        var path = await SavedSetup();
        var b = new FakePdm();
        b.Service.AutoRead = true;
        b.Open((await Files().LoadDevices(path))!);
        b.Rounds(5);
        var asks = b.Service.ConnectAsks();
        Assert.Equal(["A1", "A2", "B"], asks.Select(x => x.Role));
        Assert.Equal(PdmAskKind.ProjectFile, PdmPageText.AskKind(asks));
        Assert.False(b.Service.Ops.Busy);
        Assert.All(b.Boards.Values, x => Assert.Equal(0, x.Count(MessageCommand.ReadAll)));   // nothing read over the file

        Assert.Null(b.Service.KeepPcAndWrite(asks, true, b.Clock));
        Assert.Equal(PdmOpKind.WriteAll, b.Service.Ops.LastOp);
        b.Settle();
        Assert.All(b.States, s => Assert.Equal(PdmStepState.Ok, s));
        foreach (var role in PdmOps.Roles) AssertBoardHoldsThePcValues(b, role);
        b.Rounds(5);
        Assert.Empty(b.Service.ConnectAsks());                                                // written: nothing to ask
        Assert.All(b.Boards.Values, x => Assert.Equal(0, x.Count(MessageCommand.ReadAll)));
        Assert.Equal(12, b.Dev("B").Outputs[4].CurrentLimit);
    }

    [Fact]
    public async Task TakeThePdmsSettingsReadsTheBoardsOverTheFile()
    {
        var path = await SavedSetup();
        var b = new FakePdm();
        b.Service.AutoRead = true;
        b.Open((await Files().LoadDevices(path))!);
        b.Rounds(5);
        foreach (var ask in b.Service.ConnectAsks()) b.Service.AnswerConnect(ask.Device, PdmConnectAnswer.TakeBoard);
        b.Settle();
        b.Rounds(3);
        Assert.All(b.View.Boards, x => Assert.True(x.Device.FullReadDone));
        Assert.Empty(b.Service.ConnectAsks());
        Assert.NotEqual(12, b.Dev("B").Outputs[4].CurrentLimit);   // the blank board's value, not the file's
        Assert.All(b.Boards.Values, x => Assert.Equal(0, x.Count(MessageCommand.WriteAll)));
    }

    // Keep with a board missing: the settings are kept (nothing read over them), the write waits for the user
    [Fact]
    public async Task KeepWithABoardOfflineKeepsTheSettingsAndSaysWhyNothingWasWritten()
    {
        var path = await SavedSetup();
        var b = new FakePdm();
        b.Service.AutoRead = true;
        b.Open((await Files().LoadDevices(path))!);
        b.Offline.Add("B");
        b.Rounds(5);
        var asks = b.Service.ConnectAsks();
        Assert.Equal(["A1", "A2"], asks.Select(x => x.Role));
        Assert.Equal("B: offline.", b.Service.KeepPcAndWrite(asks, true, b.Clock));
        b.Rounds(5);
        Assert.Empty(b.Service.ConnectAsks());
        Assert.All(b.Boards.Values, x => Assert.Equal((0, 0), (x.Count(MessageCommand.ReadAll), x.Count(MessageCommand.WriteAll))));
        Assert.Equal(12, b.Dev("B").Outputs[4].CurrentLimit);
    }

    [Fact]
    public void TheQuestionSaysWhatThePcHolds()
    {
        var pdm = new FakePdm();
        var boards = pdm.View.Boards;
        Assert.Equal(PdmAskKind.Edits, PdmPageText.AskKind(boards));          // hand-added: plain edits
        foreach (var x in boards) x.Device.CustomPdm!.FactoryNew = true;
        Assert.Equal(PdmAskKind.NewPdm, PdmPageText.AskKind(boards));
        (boards[0].Device.CustomPdm!.FromFile, boards[0].Device.CustomPdm.FactoryNew) = (true, false);
        Assert.Equal(PdmAskKind.Edits, PdmPageText.AskKind(boards));          // mixed: no single story
        foreach (var x in boards) x.Device.CustomPdm!.FromFile = true;
        Assert.Equal(PdmAskKind.ProjectFile, PdmPageText.AskKind(boards));
        Assert.Equal(PdmAskKind.Edits, PdmPageText.AskKind([]));
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        Assert.Equal(PdmAskKind.Edits, PdmPageText.AskKind(pdm.View.Boards)); // read: what differs now are edits
    }
}

// The same on the real firmware (host sim): a file saved by the app, opened in a fresh session, written onto blank boards
[Collection("sim")]
public class ProjectFileLiveSimTests
{
    [SimFact]
    public async Task AFileSavedByTheAppGoesOntoBlankBoardsWithoutARead()
    {
        using var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);   // the rig's own devices are replaced by the opened file below
        rig.Step(1500);
        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());

        // a setup (the ST185 example), saved by the app as the user would
        var setup = (await files.LoadDevices(PdmStarter.Find(AppContext.BaseDirectory)!))!;
        var path = Path.Combine(Path.GetTempPath(), $"cpdm-live-{Guid.NewGuid():N}.json");
        await files.SaveDevices(setup, path);
        Assert.Equal(3, Regex.Matches(File.ReadAllText(path), "\"completeSettings\": true").Count);

        // File > Open in a session that has read nothing
        var opened = (await files.LoadDevices(path))!;
        rig.Mgr.ClearDevices();
        rig.Mgr.AddDevices(opened);
        var svc = new PdmOpsService(rig.Mgr, _ => true) { AutoTick = false };
        rig.Step(1000);
        Assert.All(svc.BuildView().Boards, b => Assert.False(b.Device.FullReadDone));
        var t = rig.SimMs;
        Assert.Null(svc.Start(PdmOpKind.WriteAll, true, rig.Now));
        while (svc.Ops.Busy && rig.SimMs - t < 300000)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }

        Assert.All(svc.Ops.Results, r => Assert.Equal(PdmStepState.Ok, r.State));
        Assert.All(new[] { 0x500, 0x540, 0x580 }, id => Assert.Equal(0, rig.CountSent(id, MessageCommand.ReadAll)));

        // a fresh PC reads board B: the file's fuel pump limit (25 A on B OUT3), not the blank board's 31 A
        var pc2 = PcTool.For(bus, 15, 0x580);
        Assert.True(pc2.ReadAll());
        Assert.Equal(25.0, pc2.Dev.Outputs[2].CurrentLimit);
        Assert.Equal(25.0, opened.OfType<FwDevice>().Single(d => d.DeviceTypeId == 15).Outputs[2].CurrentLimit);
    }
}
