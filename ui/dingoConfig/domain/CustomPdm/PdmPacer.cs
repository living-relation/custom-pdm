using System.Diagnostics;

namespace domain.CustomPdm;

// custom-pdm uipolish (2026-11-21): the gap between the frames of one batch, on the high-resolution clock.
// Why: a Write All is one WriteAll request; when the board answers it, FwDevice hands every param frame (2646 for a
// board A, 2667 for board B) to the adapter as ONE batch, and the stock SLCAN adapter waited Thread.Sleep(2) between
// the frames of a batch. On Windows a Sleep lasts a whole timer tick (15.6 ms by default), so one board took
// 2646 x 15.6 ms = 41 s: all of it on the PC, nothing waited on the board (the firmware sends no reply to a WriteAllVal
// frame, firmware/core/param_protocol.cpp). With this pacer the gap is the 2 ms the stock code asks for
// (SlcanAdapter.InterFrameDelayMs, "what common SLCAN firmware can reliably drain"): about 5.3 s per board.
// The gap itself is not shortened: the firmware sim takes a Write All down to 0.25 ms between frames
// (WriteAllSpeedLiveSimTests), so 2 ms keeps a factor 8 in hand for a real adapter.
public sealed class PdmPacer(TimeSpan gap)
{
    private long _last = long.MinValue;   // the first Wait returns at once

    // Returns when the gap has passed since the last Sent (at once when it already has, or nothing was sent yet)
    public void Wait()
    {
        if (_last == long.MinValue) return;
        var due = _last + (long)(gap.TotalSeconds * Stopwatch.Frequency);
        while (true)
        {
            var left = due - Stopwatch.GetTimestamp();
            if (left <= 0) break;
            // a Sleep is only as fine as the system timer (15.6 ms on Windows): use it for long waits only
            if (left > Stopwatch.Frequency / 25) Thread.Sleep(1);
            else Thread.SpinWait(64);
        }
    }

    // Call when the frame has gone out: the gap counts from here, so two frames are never closer than the gap
    public void Sent() => _last = Stopwatch.GetTimestamp();
}
