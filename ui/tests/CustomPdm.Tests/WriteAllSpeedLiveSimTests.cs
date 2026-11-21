using System.Globalization;
using domain.Enums;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// uipolish (2026-11-21): how close together the firmware takes the frames of a Write All (bus time, real dingoFW
// param thread in the host sim). The PC sends them 2 ms apart (SlcanAdapter + PdmPacer); every shorter gap here is margin.
[Collection("sim")]
public class WriteAllSpeedLiveSimTests(ITestOutputHelper output)
{
    [SimTheory]
    [InlineData("A1", 14, 0x500, 2.0)]
    [InlineData("A1", 14, 0x500, 1.0)]
    [InlineData("A1", 14, 0x500, 0.5)]
    [InlineData("A1", 14, 0x500, 0.25)]
    [InlineData("B", 15, 0x580, 2.0)]
    [InlineData("B", 15, 0x580, 1.0)]
    [InlineData("B", 15, 0x580, 0.5)]
    [InlineData("B", 15, 0x580, 0.25)]
    public void TheFirmwareTakesAWriteAllWithThisGapBetweenFrames(string board, int type, int baseId, double gapMs)
    {
        using var bus = new SimBus();
        bus.Run(1500);
        var pc = PcTool.For(bus, type, baseId);
        Assert.True(pc.ReadAll());

        // a change in the first, a middle and the last param block, so a dropped frame anywhere shows
        var c = pc.Dev.CustomPdm!;
        c.TempWarn = 61;
        foreach (var d in pc.Dev.DigitalInputs) d.Enabled = true;
        pc.Dev.Outputs[^1].CurrentLimit = 3;
        var sent = type == 15 ? WriteAllSpeedTests.WriteFramesB : WriteAllSpeedTests.WriteFramesA;

        pc.GapMs = gapMs;
        Assert.True(pc.WriteAll(), "no CRC check reply after Write All");
        pc.GapMs = 2;
        Assert.Contains("dev: Write Successful", pc.Notes);
        Assert.False(pc.Dev.ConfigMismatch, "config CRC check after Write All");
        Assert.Equal(0, pc.CountCmd(MessageCommand.WriteAllMissing));
        Assert.Equal(1, pc.CountCmd(MessageCommand.WriteAllComplete));   // taken at the first try

        var pc2 = PcTool.For(bus, type, baseId);
        Assert.True(pc2.ReadAll());
        Assert.Equal(61, pc2.Dev.CustomPdm!.TempWarn);
        Assert.All(pc2.Dev.DigitalInputs, d => Assert.True(d.Enabled));
        Assert.Equal(3, pc2.Dev.Outputs[^1].CurrentLimit);
        output.WriteLine(string.Create(CultureInfo.InvariantCulture,
            $"MEASURE {board}: Write All of {sent} frames {gapMs} ms apart = {sent * gapMs / 1000:F1} s bus time, taken at the first try"));
    }
}
