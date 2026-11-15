using System.Collections.Concurrent;
using System.Diagnostics;
using domain.Enums;
using domain.Models;
using infrastructure.Adapters;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// The live path Dan uses (ui/README.md): sim_bridge.py --slcan-tcp in WSL, dingoConfig's own SlcanTcpAdapter on Windows
[Collection("sim")] // the sim tests run one after another (WSL processes, real-time bridge)
public class SlcanBridgeTests(ITestOutputHelper output)
{
    [SimFact]
    public async Task DingoConfigSlcanTcpAdapterTalksToTheSim()
    {
        var so = Environment.GetEnvironmentVariable("CUSTOMPDM_SIM_SO");
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (!File.Exists(Path.Combine(dir!.FullName, "ui", "tests", "sim_bridge.py"))) dir = dir.Parent;
        var win = Path.Combine(dir.FullName, "ui", "tests", "sim_bridge.py");
        var wsl = "/mnt/" + char.ToLowerInvariant(win[0]) + win[2..].Replace('\\', '/');
        const int port = 3391;
        using var p = Process.Start(new ProcessStartInfo("wsl.exe", $"-e python3 {wsl} {so} --slcan-tcp {port}")
            { RedirectStandardOutput = true, UseShellExecute = false })!;
        try
        {
            Assert.StartsWith("SLCAN TCP on port", await p.StandardOutput.ReadLineAsync());
            var rx = new ConcurrentQueue<CanFrame>();
            var adapter = new SlcanTcpAdapter();
            adapter.DataReceived += (_, e) => rx.Enqueue(e.Frame);
            Assert.True(await adapter.InitAsync($"localhost:{port}", CanBitRate.BitRate1000K, CancellationToken.None));
            Assert.True(await adapter.StartAsync(CancellationToken.None));
            // boards boot (about 1.5 s of sim time, real time here) and send their cyclic frames
            for (var t = 0; t < 15000 && !rx.Any(f => f.Id == 0x5A7); t += 100) await Task.Delay(100);
            await adapter.WriteAsync(new CanFrame(0x501, 8, [(byte)MessageCommand.Version, 0, 0, 0, 0, 0, 0, 0]), CancellationToken.None);
            for (var t = 0; t < 5000 && !rx.Any(f => f.Id == 0x500 && f.Payload[0] == (byte)MessageCommand.Version); t += 100)
                await Task.Delay(100);
            await adapter.StopAsync();
            var ids = rx.Select(f => f.Id).ToHashSet();
            output.WriteLine($"{rx.Count} frames, ids {string.Join(' ', ids.Order().Select(i => i.ToString("X3")))}");
            Assert.Contains(0x502, ids);   // A1 msg 0
            Assert.Contains(0x567, ids);   // A2 msg 37 (0x540 + 0x27)
            Assert.Contains(0x5A7, ids);   // B msg 37
            Assert.Contains(rx, f => f.Id == 0x500 && f.Payload[0] == (byte)MessageCommand.Version && f.Payload[4] == 0 && f.Payload[5] == 6);
        }
        finally
        {
            if (!p.HasExited) p.Kill(true);
        }
    }
}
