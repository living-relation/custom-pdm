using System.Collections.Concurrent;
using application.Services;
using Microsoft.Extensions.Logging.Abstractions;
using System.Diagnostics;
using domain.CustomPdm;
using domain.Enums;
using domain.Models;
using infrastructure.Adapters;
using infrastructure.Comms;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// uiwalk (2026-11-21): the launcher's sim case for real. The app's own CommsAdapterManager is connected by
// PdmAutoConnect to sim_bridge.py --slcan-tcp (started a moment AFTER the first try, as when the bridge is slow to
// come up), then the bridge's play lines (<so dir>/ctl<port>) are used the way the README says.
[Collection("sim")]
public class UiWalkLiveSimTests(ITestOutputHelper output)
{
    private const int Port = 3392;   // own port: 3333 is the play bridge, 3391 SlcanBridgeTests

    private static string BridgePath()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (!File.Exists(Path.Combine(dir!.FullName, "ui", "tests", "sim_bridge.py"))) dir = dir.Parent;
        var win = Path.Combine(dir.FullName, "ui", "tests", "sim_bridge.py");
        return "/mnt/" + char.ToLowerInvariant(win[0]) + win[2..].Replace('\\', '/');
    }

    private static void Ctl(string so, string lines)
    {
        using var p = Process.Start(new ProcessStartInfo("wsl.exe", $"-e bash -c \"printf '{lines}' > {so}/ctl{Port}\"")
            { UseShellExecute = false })!;
        p.WaitForExit(10000);
    }

    // "Load the ST185 starter" then Write All on fresh boards: the real firmware takes every param of the file
    [SimFact]
    public async Task TheStarterWritesToFreshBoards()
    {
        using var bus = new SimBus();
        var rig = new PdmRig(bus, newPdm: true);
        rig.Step(1500);
        var svc = new PdmOpsService(rig.Mgr, _ => true) { AutoTick = false };   // the rig's bus is always there
        var files = new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager());
        Assert.Null(await PdmStarter.LoadAsync(PdmStarter.Find(AppContext.BaseDirectory)!, files, rig.Mgr, svc.Ops));

        rig.Step(1000);   // the loaded devices hear their boards
        var t = rig.SimMs;
        Assert.Null(svc.Start(PdmOpKind.WriteAll, true, rig.Now));
        while (svc.Ops.Busy && rig.SimMs - t < 300000)
        {
            rig.Step();
            svc.Tick(rig.Now);
        }

        var lines = svc.Ops.Results.Select(r => $"{r.Role} {r.State}: {r.Text}").ToList();
        output.WriteLine($"{string.Join(" | ", lines)} ({rig.SimMs - t:F0} ms sim time)");
        Assert.All(svc.Ops.Results, r => Assert.Equal(PdmStepState.Ok, r.State));
    }

    [SimFact]
    public async Task TheAppConnectsToTheBridgeByItselfAndThePlayLinesAct()
    {
        var so = Environment.GetEnvironmentVariable("CUSTOMPDM_SIM_SO")!;
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddTransient<SlcanTcpAdapter>();
        await using var sp = services.BuildServiceProvider();
        var manager = new CommsAdapterManager(sp, sp.GetRequiredService<ILogger<CommsAdapterManager>>());
        var rx = new ConcurrentQueue<CanFrame>();
        manager.DataReceived += (_, e) => rx.Enqueue(e.Frame);

        var (plan, why) = PdmAutoConnect.Plan("SLCAN TCP", $"localhost:{Port}", "1000K", false, null);
        Assert.Null(why);
        Process? bridge = null;
        try
        {
            // the bridge comes up only after the first try has failed (Windows gives up on a closed local port after
            // about 2 s: with a 1.5 s head start the first try still got through, seen 2026-11-21)
            var connect = PdmAutoConnect.RunAsync(manager, plan!, tries: 20, gap: TimeSpan.FromSeconds(1));
            await Task.Delay(4500);
            Assert.False(connect.IsCompleted);   // (manager.IsConnected is no test here: stock reports true while a try runs)
            bridge = Process.Start(new ProcessStartInfo("wsl.exe", $"-e python3 {BridgePath()} {so} --slcan-tcp {Port}")
                { RedirectStandardOutput = true, UseShellExecute = false })!;
            var (ok, text) = await connect;
            output.WriteLine(text);
            Assert.True(ok, text);
            Assert.True(manager.IsConnected);
            Assert.Matches(@"connected to SLCAN TCP localhost:3392 1000K \(try \d+\)\.$", text);

            async Task<HashSet<int>> Ids(int ms)
            {
                rx.Clear();
                await Task.Delay(ms);
                return rx.Select(f => f.Id).ToHashSet();
            }

            async Task<bool> Until(Func<HashSet<int>, bool> seen, int seconds)
            {
                for (var i = 0; i < seconds * 2; i++)
                    if (seen(await Ids(500))) return true;
                return false;
            }

            // the three boards boot and send their status frames (msg 37 = base + 0x27)
            Assert.True(await Until(ids => ids.Contains(0x527) && ids.Contains(0x567) && ids.Contains(0x5A7), 20));

            // play lines: wrong ones are refused without stopping the bridge; LINK takes A1 off the bus
            Ctl(so, @"BOGUS 1\nLOAD B 99 5\nTEMP nobody 50\nLINK A1 off\nLOAD B 2 30\nTEMP B 60\nTXP 3F4 0100000000000000 50\n");
            Assert.True(await Until(ids => !ids.Contains(0x527) && ids.Contains(0x5A7), 10));
            // RESTART = power cycle of B (it comes back by itself), A1 back on the bus, the repeating frame off
            Ctl(so, @"RESTART B\nLINK A1 on\nTXP 3F4 off\n");
            Assert.True(await Until(ids => ids.Contains(0x527) && ids.Contains(0x5A7), 15));
        }
        finally
        {
            await manager.DisconnectAsync();
            if (bridge is { HasExited: false }) bridge.Kill(true);
            bridge?.Dispose();
        }
    }
}
