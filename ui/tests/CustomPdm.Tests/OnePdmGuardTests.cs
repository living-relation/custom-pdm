using System.Text.Json.Nodes;
using application.Services;
using CarCanDummy;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using domain.Interfaces;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace CustomPdm.Tests;

// uiguide (2026-11-23), "can a user break the one-PDM feel?": every test here is a way in that went through before
// this job, found by driving the app by hand on the simulated boards (docs/ui-setup-guide.md, "How the one-PDM feel is
// protected"). Logic: domain/CustomPdm/PdmIntegrity.cs.
public class OnePdmGuardTests
{
    private static ConfigFileManager Files() => new(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());

    // A New PDM saved by the app (a complete set: writable after File > Open), then edited by hand in a text editor
    private static async Task<List<IDevice>> EditedFile(params (string Board, string Prop, int Value)[] edits)
    {
        var a = new FakePdm();
        foreach (var role in PdmOps.Roles) PdmFactoryDefaults.Apply(a.Dev(role), role);
        var path = Path.Combine(Path.GetTempPath(), $"cpdm-edited-{Guid.NewGuid():N}.json");
        await Files().SaveDevices(a.Mgr.GetDevices(), path);
        var json = JsonNode.Parse(File.ReadAllText(path))!;
        foreach (var (board, prop, value) in edits)
        {
            var d = json["Devices"]!.AsArray().Single(x => (string?)x!["name"] == board)!;
            if (prop.StartsWith("customPdm.")) d["customPdm"]![prop["customPdm.".Length..]] = value;
            else d[prop] = value;
        }

        File.WriteAllText(path, json.ToJsonString());
        return (await Files().LoadDevices(path))!;
    }

    private static FakePdm Opened(List<IDevice> loaded)
    {
        var pdm = new FakePdm();
        pdm.Open(loaded);
        return pdm;
    }

    [Fact]
    public async Task TheUneditedFileIsWritable()
    {
        var pdm = Opened(await EditedFile());
        Assert.Null(pdm.Blocked(PdmOpKind.WriteAll));
        Assert.Null(pdm.Blocked(PdmOpKind.Burn));
        Assert.Empty(PdmIntegrity.WriteProblems(pdm.View));
    }

    // Before: both PC devices were "connected" (A1's frames), Write All wrote 0x500 twice, then the read on connect
    // copied A1's settings into the PC's A2
    [Theory]
    [InlineData(0x500)]   // A2 on A1's base ID
    [InlineData(0x510)]   // A2's block overlapping A1's
    public async Task TwoBoardsOnOneIdBlockGetNothingFromThePc(int a2Base)
    {
        var pdm = Opened(await EditedFile(("A2", "baseId", a2Base)));
        foreach (var op in new[] { PdmOpKind.ReadAll, PdmOpKind.WriteAll, PdmOpKind.Burn })
            Assert.Contains("overlap", pdm.Blocked(op));
        Assert.Contains(pdm.View.Problems, p => p.Contains("A1") && p.Contains("A2") && p.Contains("overlap"));

        // the stock per-board paths send nothing either (also not to the board that owns the ID)
        foreach (var b in pdm.Boards.Values) b.Got.Clear();
        pdm.Mgr.WriteAllDeviceConfig(pdm.Dev("A2").Guid);
        pdm.Mgr.ReadAllDeviceConfig(pdm.Dev("A2").Guid);
        pdm.Mgr.BurnSettings(pdm.Dev("A2").Guid);
        pdm.Mgr.WriteAllDeviceConfig(pdm.Dev("A1").Guid);
        pdm.Pump();
        Assert.All(pdm.Boards.Values, b => Assert.Empty(b.Got));
    }

    // Before: a stock "dingoPDM" device added on the Devices page at 0x500 wrote stock settings (500K) onto A1 with its
    // own Write All, and its Burn / Modify / Bootloader / Sleep went to A1 too
    [Fact]
    public void AStockDeviceOnABoardsIdIsSentNothing()
    {
        var pdm = new FakePdm();
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        pdm.Mgr.AddDevice("fwD:0", "stockpdm", 0x500);
        var stock = pdm.Mgr.GetDevices().OfType<FwDevice>().Single(d => d.Name == "stockpdm");
        foreach (var b in pdm.Boards.Values) b.Got.Clear();

        pdm.Mgr.WriteAllDeviceConfig(stock.Guid);
        pdm.Mgr.BurnSettings(stock.Guid);
        pdm.Mgr.RequestBootloader(stock.Guid);
        pdm.Mgr.RequestSleep(stock.Guid);
        pdm.Mgr.ResetDevice(stock.Guid);
        pdm.Pump();
        Assert.Empty(pdm.Boards["A1"].Got);
        Assert.Contains(pdm.View.Problems, p => p.Contains("stockpdm") && p.Contains("A1"));
        Assert.Contains("stockpdm", pdm.Blocked(PdmOpKind.WriteAll));

        // deleted again: the PDM works as before
        pdm.Mgr.RemoveDevice(stock.Guid);
        Assert.Null(pdm.Blocked(PdmOpKind.WriteAll));
        Assert.Null(pdm.Run(PdmOpKind.WriteAll));
        Assert.All(pdm.States, s => Assert.Equal(PdmStepState.Ok, s));
    }

    // A stock device elsewhere on the bus (not on a board's IDs) is left alone
    [Fact]
    public void AStockDeviceOffThePdmIdsIsNotTouched()
    {
        var pdm = new FakePdm();
        pdm.Mgr.AddDevice("fwD:0", "stockpdm", 0x700);
        Assert.Empty(PdmIntegrity.IdClashes(pdm.Mgr.GetDevices()));
        Assert.Null(PdmIntegrity.ClashReason(0x700, pdm.Mgr.GetDevices()));
    }

    // Before: a file with A1's and A2's base IDs exchanged wrote A2's settings (the fan logic on OUT2) onto board A1
    [Fact]
    public async Task SwappedBoardSettingsAreRefused()
    {
        var pdm = Opened(await EditedFile(("A1", "baseId", 0x540), ("A2", "baseId", 0x500)));
        var why = pdm.Blocked(PdmOpKind.WriteAll);
        Assert.Contains("A1 CAN input 25 listens to 0x502", why);
        Assert.Contains("its own ID block", why);
        Assert.Contains("swapped", why);
        Assert.Contains("own ID block", pdm.Blocked(PdmOpKind.Burn));
        Assert.Null(pdm.Blocked(PdmOpKind.ReadAll));   // reading the boards over the file is the way out
    }

    // Before: a file with A2 on 500K was written (CAN bit rate is a critical setting: Unlock dialog only)
    [Fact]
    public async Task ABitRateFromAFileIsRefusedUntilSetWithUnlock()
    {
        var pdm = Opened(await EditedFile(("A2", "bitrate", (int)CanBitRate.BitRate500K)));
        var why = pdm.Blocked(PdmOpKind.WriteAll);
        Assert.Contains("CAN bit rate differs (A1 1000K, A2 500K, B 1000K)", why);
        Assert.Contains("A2: CAN bit rate 500K from the project file", why);
        Assert.Null(PdmCritical.Apply(pdm.View, PdmCriticalKind.BitRate, "1000K"));
        Assert.Null(pdm.Blocked(PdmOpKind.WriteAll));

        // all three on 500K in the file: the same on every board, but not our factory rate: confirm it with Unlock
        var all = Opened(await EditedFile(("A1", "bitrate", 1), ("A2", "bitrate", 1), ("B", "bitrate", 1)));
        Assert.DoesNotContain("differs", all.Blocked(PdmOpKind.WriteAll));
        Assert.Contains("A1: CAN bit rate 500K from the project file", all.Blocked(PdmOpKind.WriteAll));
        Assert.Null(PdmCritical.Apply(all.View, PdmCriticalKind.BitRate, "500K"));
        Assert.Null(all.Blocked(PdmOpKind.WriteAll));
    }

    [Fact]
    public async Task ACriticalTemperatureFromAFileIsRefusedUntilSetWithUnlock()
    {
        // board A has no thermal model: only "back to factory" (Unlock, type factory) clears it
        var a = Opened(await EditedFile(("A2", "customPdm.tempCrit", 120)));
        Assert.Contains("A2: critical temperature 120 C from the project file", a.Blocked(PdmOpKind.WriteAll));
        Assert.Null(PdmCritical.Apply(a.View, PdmCriticalKind.CritTemp, "125"));   // the hot-spot set changes board B only
        Assert.Contains("A2: critical temperature 120 C", a.Blocked(PdmOpKind.WriteAll));
        PdmThermal.RestoreFactory(a.View);
        Assert.Null(a.Blocked(PdmOpKind.WriteAll));

        // board B: the hot-spot value typed in the Unlock dialog confirms it, also when it is the file's value
        var b = Opened(await EditedFile(("B", "customPdm.tempCrit", 110)));
        Assert.Contains("B: critical temperature 110 C from the project file", b.Blocked(PdmOpKind.WriteAll));
        Assert.Null(PdmCritical.Apply(b.View, PdmCriticalKind.CritTemp, $"{110 + PdmThermal.BoardBOffsetK}"));
        Assert.Equal(110, b.Dev("B").CustomPdm!.TempCrit);
        Assert.Null(b.Blocked(PdmOpKind.WriteAll));
    }

    [Fact]
    public async Task OutputsKeptOnAtCriticalFromAFileAreRefusedUntilSetWithUnlock()
    {
        var pdm = Opened(await EditedFile(("A1", "customPdm.critExemptMask", 255)));
        Assert.Contains("A1: outputs kept on at critical temperature 1, 2, 3, 4, 5, 6, 7, 8 from the project file", pdm.Blocked(PdmOpKind.WriteAll));
        Assert.Null(PdmCritical.Apply(pdm.View, PdmCriticalKind.KeptOn, "10"));
        Assert.Null(pdm.Blocked(PdmOpKind.WriteAll));
    }

    // Take the PDM's settings (a Read All) replaces the file's values: nothing left to confirm
    [Fact]
    public async Task ReadingTheBoardsClearsTheFilesCriticalValues()
    {
        var pdm = Opened(await EditedFile(("A2", "bitrate", 1)));
        Assert.NotNull(pdm.Blocked(PdmOpKind.WriteAll));
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        Assert.Null(pdm.Blocked(PdmOpKind.WriteAll));
    }

    // Before: a board's own device page had Write All and Burn for that board alone (Burn without the check that all
    // three boards hold the PC settings)
    [Fact]
    public void PerBoardWriteAllAndBurnAreOnThePdmPageOnly()
    {
        var pdm = new FakePdm();
        foreach (var role in PdmOps.Roles) Assert.Contains("PDM page", CustomPdmGuards.PerBoardOpReason(pdm.Dev(role)));
        Assert.Null(CustomPdmGuards.PerBoardOpReason(StockTests.MakeDevice(0, 0x700)));
    }

    // carconfig (PR #137): the CANBoard's factory base 0x640 is the car's CSB3 switchboard (0x640-0x643)
    [Fact]
    public void TheCanBoardKeepsOffTheCarsIds()
    {
        var v = PdmLinkedTests.NewPdm();
        Assert.Equal(0x660, PdmCanBoard.FreeBase(v));
        Assert.Contains("CSB3", PdmCanBoard.Add(v, 0x640, null));
        Assert.Contains("e.g. 0x660", PdmCanBoard.Add(v, 0x630, null));   // 0x630-0x642 reaches 0x640
        Assert.Contains("0x3E8", PdmCanBoard.Add(v, 0x3E0, null));          // the ECU -> cluster streams
        Assert.Null(PdmCanBoard.Add(v, 0x660, null));
    }

    // the car's IDs in the code are the used and planned rows of the dummy CAN ID table
    [Fact]
    public void TheKnownCarIdsAreTheTablesUsedRows()
    {
        var rows = CanIdTableDummy.Parse(CarCanDummyTests.Table()).Where(r => r.Kind is IdKind.Used or IdKind.Planned)
            .Select(r => (r.First, r.Last)).OrderBy(x => x).ToList();
        Assert.Equal(rows, PdmCarIds.Known.Select(k => (k.First, k.Last)).OrderBy(x => x).ToList());
    }
}
