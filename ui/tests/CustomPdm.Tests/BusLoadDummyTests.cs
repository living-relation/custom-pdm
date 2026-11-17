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

using static CustomPdm.Tests.CarCanDummyTests;

// Dan, 2026-11-16 (L3a): bus-load estimate docs/car-can-dummy/bus-load.dummy.md (DUMMY TEST COPY).
public class BusLoadDummyTests(ITestOutputHelper output)
{
    // ---------------- L3a: bus load ----------------

    // Davis et al. 2007 bound for 11-bit IDs: 55 + 10 n bits with worst-case stuffing; 47 + 8 n without
    [Fact]
    public void FrameBitsKnownValues()
    {
        for (var n = 0; n <= 8; n++)
        {
            Assert.Equal(55 + 10 * n, BusLoadDummy.FrameBits(n, true));
            Assert.Equal(47 + 8 * n, BusLoadDummy.FrameBits(n, false));
        }
    }

    // A hand-worked table: one used frame at 10 ms (100 / s) plus the PDM (typical 3 x 6 msgs, worst 3 x 38, every 100 ms)
    [Fact]
    public void BusLoadHandWorked()
    {
        var text = string.Join("\n", Table().Split('\n').Where(l => !Regex.IsMatch(l, @"^\| 0x[0-9A-F]{3}(-0x[0-9A-F]{3})? \|.*\| (used|planned) \|")))
                   + "\n| 0x100 | test | a -> b | 8 | 10 | 20 | 1 | used | |\n| 0x101 | test 2 | a -> b | 1 | event | 100 | 1 | used | |\n";
        var lines = BusLoadDummy.Lines(CanIdTableDummy.Parse(text));
        var (nominal, typical, worst) = BusLoadDummy.Totals(lines);
        Assert.Equal((100 * 111 + 180 * 111) / 1e4, nominal, 9);                 // 3.108 %
        Assert.Equal((100 * 135 + 180 * 135) / 1e4, typical, 9);                 // 3.78 %
        Assert.Equal((50 * 135 + 10 * 65 + 1140 * 135) / 1e4, worst, 9);          // 16.13 %
        Assert.Equal(new[] { 0, 1, 2, 3, 4, 37 }, Enumerable.Range(0, 38).Where(BusLoadDummy.AlwaysSent));
    }

    [Fact]
    public void BusLoadOfDummyTableBelowFlag()
    {
        var (nominal, typical, worst) = BusLoadDummy.Totals(BusLoadDummy.Lines(CanIdTableDummy.Parse(Table())));
        output.WriteLine($"typical {typical:0.0} % ({nominal:0.0} % no stuffing), worst {worst:0.0} %");
        Assert.InRange(typical, 1, worst);
        Assert.True(worst < BusLoadDummy.FlagPercent, $"worst case {worst:0.0} % is above {BusLoadDummy.FlagPercent} %");
    }

    // PDM transmit facts used by the estimate, read from the firmware
    [Fact]
    public void PdmTxFactsFromFirmware()
    {
        Assert.Matches($@"#define CAN_TX_CYCLIC_MSG_DELAY {BusLoadDummy.PdmCycleMs} ", Firmware(Path.Combine("core", "device_config.h")));
        foreach (var b in new[] { "custompdm_a", "custompdm_b" })
        {
            var msg = Firmware(Path.Combine("boards", b, "msg.cpp"));
            Assert.Equal(CanIdTableDummy.NumTxMsgs, Regex.Matches(msg, @"^CANTxMsg TxMsg\d+\(\)", RegexOptions.Multiline).Count);
            var dlcs = Regex.Matches(msg, @"frame\.DLC = (\d+);").Select(m => int.Parse(m.Groups[1].Value)).ToList();
            Assert.Equal(CanIdTableDummy.NumTxMsgs, dlcs.Count);
            Assert.All(dlcs, d => Assert.Equal(BusLoadDummy.PdmDlc, d));
        }
    }
}
