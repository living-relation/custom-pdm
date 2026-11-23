using application.Services;
using domain.Common;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace CustomPdm.Tests;

// drivecycle (2026-11-23): the ST185 starter as the wire values the app writes (Write All), so the firmware drive-cycle
// simulation (firmware/sim/s5_drive_cycle.py) loads exactly what the app would put on the three boards, with no second
// copy of the dingoConfig param map in Python. The file is checked here: a change to the starter or to a param of the
// app turns this test RED until the file is written again (CUSTOMPDM_WRITE_STARTER_PARAMS=1 dotnet test ...).
public class StarterParamsExportTests
{
    public const string RelPath = "firmware/sim/data/st185-starter.params.dummy.tsv";

    private static string Root()
    {
        var starter = PdmStarter.Find(AppContext.BaseDirectory);
        Assert.NotNull(starter);
        return Path.GetFullPath(Path.Combine(Path.GetDirectoryName(starter)!, "..", ".."));
    }

    public static async Task<List<string>> Lines()
    {
        var mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance,
            new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs")), new FwDeviceDefManager());
        mgr.SetBatchTransmitCallback(_ => { });
        var service = new PdmOpsService(mgr, _ => true) { AutoTick = false };
        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
        Assert.Null(await PdmStarter.LoadAsync(PdmStarter.Find(AppContext.BaseDirectory)!, files, mgr, service.Ops));
        var lines = new List<string>
        {
            "# DUMMY TEST COPY - not a source of truth: the wire values (4 bytes, as Write All sends them) of ui/examples/st185-starter.json "
            + "(itself a dummy starter, ui/examples/README.md), written by ui/tests/CustomPdm.Tests/StarterParamsExportTests.cs",
            "# role\tindex\tsub\tbytes\tname"
        };
        foreach (var role in PdmOps.Roles)
        {
            var d = service.BuildView().Boards.Single(b => b.Role == role).Device;
            lines.AddRange(d.Params.Select(p =>
                $"{role}\t0x{p.Index:X4}\t{p.SubIndex}\t{Convert.ToHexString(ParamCodec.ToFrame(MessageCommand.Write, p, 0).Payload, 4, 4)}\t{p.Name}"));
        }

        return lines;
    }

    [Fact]
    public async Task TheDriveCycleParamFileIsTheStarter()
    {
        var path = Path.Combine(Root(), RelPath);
        var want = await Lines();
        if (Environment.GetEnvironmentVariable("CUSTOMPDM_WRITE_STARTER_PARAMS") == "1")
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, string.Join("\n", want) + "\n");
        }

        Assert.True(File.Exists(path), $"{RelPath} missing: run the tests once with CUSTOMPDM_WRITE_STARTER_PARAMS=1");
        var got = File.ReadAllText(path).Replace("\r\n", "\n").TrimEnd('\n').Split('\n');
        Assert.Equal(want, got);
        // three boards, each with its full table (the drive cycle checks it against the board's own Read All too)
        Assert.Equal(PdmOps.Roles, want.Skip(2).Select(l => l.Split('\t')[0]).Distinct());
    }
}
