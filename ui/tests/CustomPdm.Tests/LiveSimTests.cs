using domain.Enums;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// dingoConfig's own device / param code (FwDevice, ParamProtocol, CRC) against our real firmware logic (host sim of
// custompdm_a unit 1 / 2 and custompdm_b, factory-fresh FRAM), over the stock dingoFW parameter protocol.
public class LiveSimTests(ITestOutputHelper output)
{
    public static TheoryData<string, int, int> Boards => new() { { "A1", 14, 0x500 }, { "A2", 14, 0x540 }, { "B", 15, 0x580 } };

    private static PcTool Boot(SimBus bus, int type, int baseId)
    {
        var pc = PcTool.For(bus, type, baseId);
        pc.Run(1500);
        return pc;
    }

    [Theory]
    [MemberData(nameof(Boards))]
    public void ReadAllWriteAllAndCrcCheck(string board, int type, int baseId)
    {
        if (SkipNoSim()) return;
        using var bus = new SimBus();
        var pc = Boot(bus, type, baseId);

        // 1. Read All: every reply is a known param, CRC of the replies matches, then the full-config CRC check matches
        Assert.True(pc.ReadAll(), "no CRC check reply");
        Assert.Contains("dev: Read Successful", pc.Notes);
        Assert.False(pc.Dev.ConfigMismatch, "config CRC check after Read All");
        // the firmware sends its params in stParams order: same list, same order as the PC (CRC order)
        var fw = pc.Seen.Where(s => s.Id == baseId && s.Data[0] == (byte)MessageCommand.ReadAllRsp)
            .Select(s => (s.Data[2] << 8 | s.Data[1], (int)s.Data[3])).ToList();
        Assert.Equal(pc.Dev.Params.Select(p => (p.Index, p.SubIndex)), fw);
        var c = pc.Dev.CustomPdm!;
        Assert.Equal((55, 80, 6, board == "A2" ? 2 : 0, 5, 0),
            (c.TempWarn, c.TempCrit, c.TempCritHyst, c.CritExemptMask, c.TempCritSoonMargin, c.WakeInputMask));
        var differ = pc.Dev.Params.Where(p => p.IsModified).Select(p => p.Name).ToList();
        output.WriteLine($"{board}: {fw.Count} params; firmware factory values that differ from the PC defaults: {differ.Count}: {string.Join(", ", differ.Take(40))}");

        // 2. Write All with new 0x7F00 values (and every digital input enabled), applied, CRC check matches
        c.TempWarn = 60; c.TempCrit = 90; c.TempCritHyst = 4; c.CritExemptMask = 0x81; c.TempCritSoonMargin = 7;
        c.WakeInputMask = type == 14 ? 0x12 : 0x0C;
        foreach (var d in pc.Dev.DigitalInputs) d.Enabled = true;
        Assert.True(c.IsValid());
        Assert.True(pc.WriteAll(), "no CRC check reply after Write All");
        Assert.Contains("dev: Write Successful", pc.Notes);
        Assert.False(pc.Dev.ConfigMismatch, "config CRC check after Write All");

        // 3. A second PC (fresh project) reads the values back
        var pc2 = PcTool.For(bus, type, baseId);
        Assert.True(pc2.ReadAll());
        Assert.False(pc2.Dev.ConfigMismatch);
        var c2 = pc2.Dev.CustomPdm!;
        Assert.Equal((60, 90, 4, 0x81, 7, type == 14 ? 0x12 : 0x0C),
            (c2.TempWarn, c2.TempCrit, c2.TempCritHyst, c2.CritExemptMask, c2.TempCritSoonMargin, c2.WakeInputMask));
        Assert.All(pc2.Dev.DigitalInputs, d => Assert.True(d.Enabled));

        // 4. The PC now differs from the board in one value: the CRC check must say so
        c2.TempWarn = 61;
        pc2.Send([pc2.Dev.GetCheckMsg()]);
        pc2.RunUntil(() => pc2.Dev.ConfigMismatch, 1000);
        Assert.True(pc2.Dev.ConfigMismatch, "CRC check must see a changed 0x7F00 value");
    }

    // The checkbox rule (CustomPdmSettings.WakeInputMaskBadBits) accepts exactly the masks the firmware accepts
    [Theory]
    [InlineData("A1", 14, 0x500)]
    [InlineData("B", 15, 0x580)]
    public void WakeRuleMatchesFirmware(string board, int type, int baseId)
    {
        if (SkipNoSim()) return;
        using var bus = new SimBus();
        bus.Run(1500);
        var n = type == 14 ? 7 : 10;
        var wrong = new List<int>();
        for (var mask = 0; mask < 1 << n; mask++)
        {
            var frame = new domain.Models.CanFrame(baseId + 1, 8,
                [(byte)MessageCommand.Write, 0x00, 0x7F, 5, (byte)mask, (byte)(mask >> 8), 0, 0]);
            var rx = bus.Tx([frame], 5);
            var accepted = rx.Any(f => f.Id == baseId && f.Data[0] == (byte)MessageCommand.Write && f.Data[3] == 5);
            var allowed = domain.CustomPdm.CustomPdmSettings.WakeInputMaskBadBits(type, mask) == 0;
            if (accepted != allowed) wrong.Add(mask);
        }
        output.WriteLine($"{board}: {1 << n} masks, {wrong.Count} disagree");
        Assert.Empty(wrong);
    }

    private bool SkipNoSim()
    {
        if (!string.IsNullOrEmpty(Environment.GetEnvironmentVariable("CUSTOMPDM_SIM_SO"))) return false;
        output.WriteLine("skipped: CUSTOMPDM_SIM_SO not set");
        return true;
    }
}
