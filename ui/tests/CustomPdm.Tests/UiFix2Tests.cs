using System.Collections.Concurrent;
using application.Services;
using Bunit;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using domain.Models;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using MudBlazor;
using MudBlazor.Services;
using web.Components.Shared;
using web.Services;
using Xunit;

namespace CustomPdm.Tests;

// uifix2 (2026-11-23): the follow-ups of the setup guide (docs/ui-setup-guide.md "Problems found while writing this
// guide", protection row 14) and Dan's drop of the CANBoard.
public class UiFix2Tests
{
    private static DeviceManager Mgr()
    {
        var mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance,
            new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs")), new FwDeviceDefManager());
        mgr.SetBatchTransmitCallback(_ => { });
        return mgr;
    }

    // ---------------- 1. board roles from the base IDs / the role a board was given, not from order ----------------

    // Before: delete A1 on /devices and the board left at 0x540 was labelled A1 (outputs 1-8, X1-H..R pins), and edits made
    // for "A1" went to it
    [Fact]
    public void TheBoardLeftAfterDeletingA1IsNotTakenForA1()
    {
        var pdm = new FakePdm();                                  // three hand-added boards: no role given to any
        Assert.Equal(["A1", "A2", "B"], pdm.View.Boards.Select(b => b.Role));
        pdm.Mgr.RemoveDevice(pdm.Dev("A1").Guid);
        var v = pdm.View;
        var a2 = Assert.Single(v.Unassigned);
        Assert.Equal(0x540, a2.BaseId);
        Assert.True(v.EditsOff);
        Assert.True(v.Any);
        Assert.Equal(["B"], v.Boards.Select(b => b.Role));
        Assert.DoesNotContain(v.Outputs, o => o.Device == a2);
        Assert.Equal(Enumerable.Range(17, 8), v.Outputs.Select(o => o.Number));
        Assert.Contains(v.Problems, p => p.StartsWith("A? (0x540)"));
        Assert.Equal("A2", PdmView.SuggestedRole(a2));            // 0x540 is A2's factory base ID: the recommended answer
        Assert.NotNull(pdm.Blocked(PdmOpKind.WriteAll));

        // the user says which board it is
        Assert.NotNull(PdmView.Confirm(v, a2, "B"));
        Assert.Null(PdmView.Confirm(v, a2, "A2"));
        v = pdm.View;
        Assert.False(v.EditsOff);
        Assert.Equal(["A2", "B"], v.Boards.Select(b => b.Role));
        Assert.Equal(Enumerable.Range(9, 8).Concat(Enumerable.Range(17, 8)), v.Outputs.Select(o => o.Number));
        Assert.Equal("X1-S", v.Outputs.First().Connector);
        Assert.Contains(v.Problems, p => p.StartsWith("No board A1"));
    }

    // A New PDM board keeps its factory role: delete A1 and the board at 0x540 is still A2 (nothing to answer)
    [Fact]
    public void ANewPdmBoardKeepsItsFactoryRole()
    {
        var mgr = Mgr();
        var svc = new PdmOpsService(mgr) { AutoTick = false };
        Assert.Null(svc.NewPdm());
        mgr.RemoveDevice(svc.BuildView().Boards.Single(b => b.Role == "A1").Device.Guid);
        var v = svc.BuildView();
        Assert.Empty(v.Unassigned);
        Assert.Equal(["A2", "B"], v.Boards.Select(b => b.Role));
        Assert.Equal(0x540, v.Boards[0].Device.BaseId);
        Assert.Equal(9, v.Outputs[0].Number);
    }

    // Two A boards: the lower base ID is A1, whatever the names, the order they were added in or their factory roles
    [Fact]
    public void TwoABoardsAreTakenByBaseId()
    {
        var hi = StockTests.MakeDevice(14, 0x540);
        var lo = StockTests.MakeDevice(14, 0x500);
        hi.CustomPdm!.FactoryRole = "A1";
        var v = PdmView.Build([hi, lo, StockTests.MakeDevice(15, 0x580)]);
        Assert.Equal(new[] { ("A1", 0x500), ("A2", 0x540), ("B", 0x580) }, v.Boards.Select(b => (b.Role, b.Device.BaseId)));
        Assert.False(v.EditsOff);
    }

    // ---------------- 5. no "offline" for the board the running operation handles ----------------

    // Before: during Write All the board being written dropped off the bus for a moment and the page said "A1 is offline"
    [Fact]
    public void TheBoardInWorkIsNotSaidOffline()
    {
        var pdm = new FakePdm();
        Assert.Null(pdm.Run(PdmOpKind.ReadAll));
        Assert.Null(pdm.Service.Start(PdmOpKind.WriteAll, true, pdm.Clock));   // A1 first
        pdm.Offline.UnionWith(["A1", "B"]);
        var ops = pdm.Service.Ops;
        bool Conn(FwDevice d) => !pdm.Offline.Contains(d.Name);
        bool Handling(string role) => PdmPageText.Handling(role, ops.Busy, ops.Results);
        Assert.True(Handling("A1"));
        Assert.False(Handling("B"));                                            // waiting, not in work
        Assert.StartsWith("A1, B are offline", PdmPageText.OfflineLine(pdm.View, true, Conn));   // the line before
        Assert.StartsWith("B is offline", PdmPageText.OfflineLine(pdm.View, true, Conn, Handling));
        Assert.Equal("Writing", PdmPageText.LinkText(false, true, PdmOpKind.WriteAll));
        Assert.Equal("Offline", PdmPageText.LinkText(false, false, PdmOpKind.WriteAll));
        Assert.Equal("Connected", PdmPageText.LinkText(true, true, PdmOpKind.WriteAll));
        pdm.Offline.Clear();
        pdm.Settle();
        pdm.Offline.Add("A1");
        Assert.StartsWith("A1 is offline", PdmPageText.OfflineLine(pdm.View, true, Conn, Handling));   // no run: said again
    }

    // ---------------- CANBoard dropped (Dan, 2026-11-23) ----------------

    internal static string Repo()
    {
        var d = new DirectoryInfo(AppContext.BaseDirectory);
        while (d != null && !(File.Exists(Path.Combine(d.FullName, "AGENTS.md")) && Directory.Exists(Path.Combine(d.FullName, "ui", "tests"))))
            d = d.Parent;
        return d?.FullName ?? throw new DirectoryNotFoundException("repo root");
    }

    [Fact]
    public void TheCanBoardFeatureIsGone()
    {
        var names = typeof(PdmView).Assembly.GetTypes().Concat(typeof(web.Components.CustomPdm.PdmPage).Assembly.GetTypes())
            .Select(t => t.Name).ToList();
        Assert.DoesNotContain(names, n => n.StartsWith("PdmCanBoard") || n == "PdmCarIds");
        Assert.DoesNotContain(Enum.GetNames<PdmValueKind>(), n => n == "CanBoard");
        var bridge = File.ReadAllText(Path.Combine(Repo(), "ui", "tests", "sim_bridge.py"));
        Assert.DoesNotContain("class CanBoard", bridge);
        Assert.DoesNotContain("'CB'", bridge);
        // our docs say nothing of it any more (the stock dingoConfig / dingoFW texts are upstream's and stay)
        Assert.DoesNotContain("CANBoard", File.ReadAllText(Path.Combine(Repo(), "docs", "ui-setup-guide.md")), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("CANBoard", File.ReadAllText(Path.Combine(Repo(), "ui", "README.md")), StringComparison.OrdinalIgnoreCase);
    }
}

// ---------------- 2. the stock RX race: "Error processing RX frame: 505" ----------------
// Two threads flat out for up to 1 s: run alone, so the real-clock timing tests (WriteAllSpeedTests) are not slowed
[CollectionDefinition("cpu-heavy", DisableParallelization = true)]
public class CpuHeavyCollection;

[Collection("cpu-heavy")]
public class RxRaceTests
{
    // Before: DeviceManager kept its devices in a Dictionary; CommsDataPipeline's RX thread walks it in OnCanDataReceived
    // (A1's frame 0x505 on the bus) while File > Open / the starter replace the devices on the UI thread:
    // InvalidOperationException "Collection was modified", logged as "Error processing RX frame: 505".
    [Fact]
    public void RxFramesWhileTheDevicesAreReplacedNeverThrow()
    {
        var mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance,
            new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs")), new FwDeviceDefManager());
        mgr.SetBatchTransmitCallback(_ => { });
        mgr.AddDevice("fwD:14", "A1", 0x500);
        mgr.AddDevice("fwD:14", "A2", 0x540);
        mgr.AddDevice("fwD:15", "B", 0x580);
        var devices = mgr.GetDevices();
        var errors = new ConcurrentQueue<Exception>();
        var stop = DateTime.UtcNow.AddSeconds(1);
        var frame = new CanFrame(0x505, 8, new byte[8]);
        var rx = new Thread(() =>
        {
            while (DateTime.UtcNow < stop && errors.IsEmpty)
                try { mgr.OnCanDataReceived(frame); }
                catch (Exception e) { errors.Enqueue(e); }
        });
        rx.Start();
        var swaps = 0;
        while (DateTime.UtcNow < stop && errors.IsEmpty && swaps < 20000)
        {
            mgr.ClearDevices();            // as MainLayout.HandleOpen (File > Open) and the starter
            mgr.AddDevices(devices);
            swaps++;
        }

        rx.Join();
        Assert.True(errors.IsEmpty, $"after {swaps} swaps: {errors.FirstOrDefault()}");
    }
}

// ---------------- 4. File > Open: Enter on a typed path opens the file ----------------
public class FileOpenEnterTests : BunitContext, IAsyncLifetime
{
    public FileOpenEnterTests()
    {
        JSInterop.Mode = JSRuntimeMode.Loose;
        Services.AddMudServices();
        Services.AddSingleton(new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs")));
        Services.AddScoped<NotificationService>();
        Render<MudPopoverProvider>();
    }

    Task IAsyncLifetime.InitializeAsync() => Task.CompletedTask;
    Task IAsyncLifetime.DisposeAsync() => DisposeAsync().AsTask();

    private (IRenderedComponent<FileSystemBrowser> Cut, List<string> Picked, List<string> Opened, string Dir) Browser()
    {
        var dir = Path.Combine(Path.GetTempPath(), $"cpdm-open-{Guid.NewGuid():N}");
        Directory.CreateDirectory(Path.Combine(dir, "sub"));
        var picked = new List<string>();
        var opened = new List<string>();
        var cut = Render<FileSystemBrowser>(p => p
            .Add(x => x.InitialPath, dir)
            .Add(x => x.SelectedFileChanged, f => picked.Add(f))
            .Add(x => x.FileConfirmed, f => opened.Add(f)));
        return (cut, picked, opened, dir);
    }

    // Before: the typed file was only picked ("Selected: ..."), the user still had to click Open
    [Fact]
    public void EnterOnATypedFilePathOpensIt()
    {
        var (cut, picked, opened, dir) = Browser();
        var file = Path.Combine(dir, "sub", "my-pdm.json");
        File.WriteAllText(file, "{}");
        var input = cut.Find("input");
        input.Input($"\"{file}\"");                                  // pasted with "Copy as path" quotes
        input.KeyDown(new KeyboardEventArgs { Key = "Enter" });
        Assert.Equal([file], picked);
        Assert.Equal([file], opened);
    }

    [Fact]
    public void EnterOnAFolderOnlyGoesThere()
    {
        var (cut, picked, opened, dir) = Browser();
        File.WriteAllText(Path.Combine(dir, "sub", "x.json"), "{}");
        var input = cut.Find("input");
        input.Input(Path.Combine(dir, "sub"));
        input.KeyDown(new KeyboardEventArgs { Key = "Enter" });
        Assert.Empty(opened);
        Assert.Empty(picked);
        Assert.Contains("x.json", cut.Markup);
    }
}
