using System.Text.Json;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using application.Services;
using CarCanDummy;
using domain.CustomPdm;
using domain.Models;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// Dan, 2026-11-16 (L2): the DUMMY TEST COPY car-CAN files in docs/car-can-dummy, made or checked by ui/tools/CarCanDummy
// (run by ui/tools/DbcGen). The st185 repo is read only: nothing from it is run or copied as code. Helpers here are
// shared with LinkDummyTests (L1a) and BusLoadDummyTests (L3a).
public class CarCanDummyTests(ITestOutputHelper output)
{
    internal static readonly FwDeviceDefManager Mgr = new();

    internal static List<DbcBoard> Boards() => DbcExport.RepoDbcBoards(Mgr.GetByDeviceType, Mgr.GetDeviceCyclicSigsConfig);

    internal static string DummyDir => Path.Combine(DbcExportTests.RepoRoot(), "docs", "car-can-dummy");

    internal static string Read(string path) => File.ReadAllText(path).Replace("\r\n", "\n");

    internal static string Table() => Read(Path.Combine(DummyDir, CanIdTableDummy.FileName));

    internal static List<DbcSignal> PdmDbc() =>
        DbcExportTests.Parse(Read(Path.Combine(DbcExportTests.RepoRoot(), "firmware", "dbc", DbcExport.PdmFileName)));

    internal static string Firmware(string rel) => Read(Path.Combine(DbcExportTests.RepoRoot(), "firmware", rel));

    // AGENTS.md "Other repos": every copy is a dummy, says so in its name and on its first line, with its real source
    [Fact]
    public void EveryDummyFileIsMarked()
    {
        var files = Directory.GetFiles(DummyDir);
        Assert.NotEmpty(files);
        foreach (var f in files)
        {
            Assert.Contains("dummy", Path.GetFileName(f));
            var first = Read(f).Split('\n')[0];
            Assert.Matches(@"DUMMY TEST COPY - not a source of truth; real source: \S.* @ [0-9a-f]{8}.*; never use alone to decide a design change \(Dan, 2026-11-16\)", first);
        }
    }

    // ---------------- L2: ID table and clash check ----------------

    [Fact]
    public void IdTableHasNoClash()
    {
        var rows = CanIdTableDummy.Parse(Table());
        Assert.Empty(CanIdTableDummy.Check(rows));
        Assert.Equal(9, rows.Count(r => r.Kind == IdKind.Pdm));
        output.WriteLine($"{rows.Count} rows: {rows.Count(r => r.Kind == IdKind.Used)} used, {rows.Count(r => r.Kind == IdKind.Free)} free, " +
                         $"{rows.Count(r => r.Kind == IdKind.Pdm)} pdm, {rows.Count(r => r.Kind == IdKind.Planned)} planned");
    }

    [Theory]
    [InlineData("| 0x510 | planted | x | 8 | 10 | 10 | 1 | used | |", "CLASH 0x502-0x527")]            // inside A1's block
    [InlineData("| 0x3E8 | planted twin | x | 8 | 10 | 10 | 1 | used | |", "CLASH 0x3E8")]             // two used rows
    [InlineData("| 0x5A7 | planted | x | 8 | 10 | 10 | 1 | planned | |", "CLASH 0x582-0x5A7")]        // planned on B's msg 37
    [InlineData("| 0x641 | planted | x | 8 | 10 | 10 | 1 | planned | |", "CLASH 0x641")]              // planned on the CSB3
    public void PlantedClashIsCaught(string row, string expected)
    {
        var text = Table().Replace("| 0x644-0x7FF |", row + "\n| 0x644-0x7FF |");
        var errors = CanIdTableDummy.Check(CanIdTableDummy.Parse(text));
        Assert.Contains(errors, e => e.StartsWith(expected));
    }

    [Fact]
    public void PdmOutsideFreeRangeOrMissingRowIsCaught()
    {
        var shrunk = Table().Replace("| 0x3F2-0x63F |", "| 0x3F2-0x4FF |");
        Assert.Contains(CanIdTableDummy.Check(CanIdTableDummy.Parse(shrunk)), e => e.Contains("0x500 is not inside a free range"));
        var noRow = string.Join("\n", Table().Split('\n').Where(l => !l.StartsWith("| 0x542-0x567 |")));
        var errors = CanIdTableDummy.Check(CanIdTableDummy.Parse(noRow));
        Assert.Contains(errors, e => e.Contains("0x542 has no pdm row"));
        Assert.Contains(errors, e => e.StartsWith("pdm rows ") && e.Contains("differ from the firmware blocks"));
    }

    // The PDM blocks follow the firmware: config offsets, cyclic offset, NUM_TX_MSGS, and hold every DBC message ID
    [Fact]
    public void PdmBlocksFollowFirmware()
    {
        var cfg = Firmware(Path.Combine("core", "device_config.h"));
        Assert.Matches(@"#define CONFIG_TX_OFFSET 0\b", cfg);
        Assert.Matches(@"#define CONFIG_RX_OFFSET 1\b", cfg);
        Assert.Matches(@"#define CYCLIC_TX_OFFSET 2\b", cfg);
        foreach (var b in new[] { "custompdm_a", "custompdm_b" })
            Assert.Matches($@"#define NUM_TX_MSGS {CanIdTableDummy.NumTxMsgs}\b", Firmware(Path.Combine("boards", b, "port.h")));
        var ids = CanIdTableDummy.PdmIds().ToHashSet();
        Assert.Equal(3 * (2 + CanIdTableDummy.NumTxMsgs), ids.Count);
        Assert.All(PdmDbc().Select(s => s.Id).Distinct(), id => Assert.Contains(id, ids));
    }
}
