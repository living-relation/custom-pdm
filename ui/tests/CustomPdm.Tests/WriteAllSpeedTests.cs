using System.Collections.Concurrent;
using System.Diagnostics;
using application.Services;
using domain.CustomPdm;
using domain.Devices;
using domain.Enums;
using domain.Models;
using infrastructure.Adapters;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// uipolish (2026-11-21): why a /pdm Write All took 41 s per board, and the fix (domain/CustomPdm/PdmPacer.cs).
// The board answers the WriteAll request, then FwDevice hands every param frame to the adapter as ONE batch, and the
// stock SLCAN adapter waited Thread.Sleep(2) between the frames of a batch: 15.6 ms each on Windows.
public class WriteAllSpeedTests(ITestOutputHelper output)
{
    [Fact]
    public void ThePacerWaitsItsGapOnTheFineClock()
    {
        var pacer = new PdmPacer(TimeSpan.FromMilliseconds(2));
        pacer.Sent();
        var sw = Stopwatch.StartNew();
        for (var i = 0; i < 100; i++) { pacer.Wait(); pacer.Sent(); }
        var ms = sw.Elapsed.TotalMilliseconds;
        output.WriteLine($"MEASURE 100 waits of 2 ms: {ms:F0} ms");
        Assert.InRange(ms, 199, 600);   // 100 x Thread.Sleep(2) on Windows: about 1560 ms
    }

    [Fact]
    public void ThePacerDoesNotWaitWhenTheGapHasPassed()
    {
        var pacer = new PdmPacer(TimeSpan.FromMilliseconds(50));
        var sw = Stopwatch.StartNew();
        pacer.Wait();
        Assert.InRange(sw.Elapsed.TotalMilliseconds, 0, 20);   // nothing sent yet: the first one is free
        pacer.Sent();
        Thread.Sleep(80);
        sw.Restart();
        pacer.Wait();
        Assert.InRange(sw.Elapsed.TotalMilliseconds, 0, 20);   // the gap has passed already
        pacer.Sent();
        pacer.Wait();   // and this one waits the gap from the last frame
        Assert.InRange(sw.Elapsed.TotalMilliseconds, 49, 150);
    }

    // records when each SLCAN frame reaches the transport
    private sealed class TimedStream : Stream
    {
        public readonly List<long> Times = [];
        public override void Write(byte[] buffer, int offset, int count) => Times.Add(Stopwatch.GetTimestamp());
        public override bool CanRead => false;
        public override bool CanSeek => false;
        public override bool CanWrite => true;
        public override long Length => 0;
        public override long Position { get; set; }
        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count) => 0;
        public override long Seek(long offset, SeekOrigin origin) => 0;
        public override void SetLength(long value) { }
    }

    private sealed class RecordingSlcan : SlcanAdapter
    {
        public readonly TimedStream Out = new();
        protected override Task<Stream> OpenTransportAsync(string port, CancellationToken ct) => Task.FromResult<Stream>(Out);
    }

    // The frames of one board's Write All, as FwDevice hands them over when the board has answered the request
    public static List<DeviceCanFrame> WriteAllFrames(string role)
    {
        var mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance,
            new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs")), new FwDeviceDefManager());
        Assert.Null(new PdmOpsService(mgr).NewPdm());
        var dev = mgr.GetDevicesByType<FwDevice>().Single(d => d.Name == role);
        var queue = new ConcurrentDictionary<(int BaseId, int Index, int SubIndex), DeviceCanFrame>();
        var frames = new List<DeviceCanFrame>();
        var request = dev.GetWriteMsgs(true);
        Assert.Single(request);
        queue[(dev.BaseId, 0, 0)] = request[0];
        dev.Read(dev.BaseId, [(byte)MessageCommand.WriteAll, 0, 0, 0, 0, 0, 0, 0], ref queue, frames);
        return frames;
    }

    public const int WriteFramesA = 2646, WriteFramesB = 2667;   // one frame per param + WriteAllComplete

    [Theory]
    [InlineData("A1", WriteFramesA)]
    [InlineData("B", WriteFramesB)]
    public async Task TheSlcanAdapterSendsAWriteAllTwoMsPerFrame(string role, int count)
    {
        var frames = WriteAllFrames(role);
        Assert.Equal(count, frames.Count);
        Assert.Equal((byte)MessageCommand.WriteAllComplete, frames[^1].Frame.Payload[0]);
        Assert.All(frames.Take(frames.Count - 1), f => Assert.Equal((byte)MessageCommand.WriteAllVal, f.Frame.Payload[0]));

        var slcan = new RecordingSlcan();
        Assert.True(await slcan.InitAsync("test", CanBitRate.BitRate1000K, CancellationToken.None));
        var sw = Stopwatch.StartNew();
        Assert.True(await slcan.WriteBatchAsync(frames.Select(f => f.Frame).ToList(), CancellationToken.None));
        var ms = sw.Elapsed.TotalMilliseconds;
        var t = slcan.Out.Times;
        var gaps = t.Zip(t.Skip(1), (a, b) => (b - a) * 1000.0 / Stopwatch.Frequency).Order().ToList();
        output.WriteLine($"MEASURE Write All {role}: {t.Count} frames out in {ms:F0} ms, gap min {gaps[0]:F2} / median {gaps[gaps.Count / 2]:F2} / max {gaps[^1]:F2} ms");

        Assert.Equal(count, t.Count);
        // never closer than the stock 2 ms ("what common SLCAN firmware can reliably drain") ...
        Assert.True(gaps[0] >= 1.96, $"shortest gap {gaps[0]:F3} ms");
        // ... and no slower than that needs: with Thread.Sleep(2) one board took count x 15.6 ms = about 40 s on Windows
        Assert.InRange(ms, (count - 1) * 2.0 * 0.98, count * 2.0 * 1.6);
    }
}
