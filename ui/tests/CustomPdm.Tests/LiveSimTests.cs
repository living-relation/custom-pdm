using domain.Enums;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// dingoConfig's own device / param code (FwDevice, ParamProtocol, CRC) against our real firmware logic (host sim of
// custompdm_a unit 1 / 2 and custompdm_b, factory-fresh FRAM), over the stock dingoFW parameter protocol.
[Collection("sim")] // the sim tests run one after another (WSL processes, real-time bridge)
public class LiveSimTests(ITestOutputHelper output)
{
    public static TheoryData<string, int, int> Boards => new() { { "A1", 14, 0x500 }, { "A2", 14, 0x540 }, { "B", 15, 0x580 } };

    private static PcTool Boot(SimBus bus, int type, int baseId)
    {
        var pc = PcTool.For(bus, type, baseId);
        pc.Run(1500);
        return pc;
    }

    [SimTheory]
    [MemberData(nameof(Boards))]
    public void ReadAllWriteAllAndCrcCheck(string board, int type, int baseId)
    {
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
        Assert.Equal((type == 15 ? 98 : 55, type == 15 ? 104 : 80, 6, board == "A2" ? 2 : 0, 5, 0),   // board B: its own limits (fwsafety)
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

    // Status page values decoded from the firmware's real cyclic frames: DIs (msg 0 / 37), analog (msg 37),
    // board temperature (msg 0), die temperature (msg 37), thermal flags (msg 3 byte 7)
    [SimTheory]
    [MemberData(nameof(Boards))]
    public void StatusDecode(string board, int type, int baseId)
    {
        using var bus = new SimBus();
        var pc = Boot(bus, type, baseId);
        // Read first: a new project's PC defaults are not our factory defaults (bit rate 500K vs 1000K, fan config)
        Assert.True(pc.ReadAll());
        foreach (var d in pc.Dev.DigitalInputs) d.Enabled = true;
        pc.Dev.AnalogInputs[0].Enabled = true;
        Assert.True(pc.WriteAll());
        var n = pc.Dev.DigitalInputs.Count;
        for (var i = 0; i < n; i++) bus.Cmd($"IN {board} {i} {(i % 3 == 0 ? "12v" : "gnd")} off");
        bus.Cmd($"AN {board} 3.0");

        byte[] Last(int offset) => pc.Seen.Last(s => s.Id == baseId + offset).Data;
        int flags = 0;
        // factory limits: A 55 / 80, B 98 / 104 (fwsafety): warn, critical soon (critical - 5), critical
        foreach (var (temp, expectBit) in type == 15 ? new[] { (98.5, 1), (101.0, 2), (105.0, 4) } : new[] { (62.5, 1), (77.0, 2), (81.0, 4) })
        {
            bus.Cmd($"TEMP {board} {temp} 41");
            pc.Run(1500);
            var m37 = Last(0x27);
            var di = BitConverter.ToUInt16(m37, 0);
            Assert.True(di != 0 && di != (1 << n) - 1, $"input pattern not seen by the firmware: {di:X}");
            for (var i = 0; i < n; i++) Assert.Equal(((di >> i) & 1) == 1, pc.Dev.DigitalInputs[i].State);
            Assert.Equal(BitConverter.ToUInt16(m37, 2), pc.Dev.AnalogInputs[0].Millivolts);
            Assert.Equal(BitConverter.ToUInt16(m37, 4), pc.Dev.CustomPdm!.AnalogRaw);
            Assert.True(pc.Dev.AnalogInputs[0].Millivolts > 0);
            Assert.Equal(BitConverter.ToInt16(m37, 6) / 10.0, pc.Dev.CustomPdm.DieTempC, 3);
            // what the firmware sends for a 41 C die in the sim (firmware/sim/pdmsim.py die_temp_can: sensor model, one
            // 12-bit sample, GetTemperature() with the sim's calibration values) = 45.6 C
            var raw = (int)((0.76 + (41 - 25.0) * 0.0025) / 3.3 * 4095.0 + 0.5);
            Assert.Equal((int)((30.0 + (raw - 943) / (1199.0 - 943) * 80.0) * 10.0) / 10.0, pc.Dev.CustomPdm.DieTempC, 3);
            Assert.Equal(temp, pc.Dev.BoardTempC, 3);
            flags = Last(5)[7];
            Assert.Equal(flags, pc.Dev.CustomPdm.ThermalFlags);
            Assert.True((flags & expectBit) != 0, $"{temp} C: flags {flags}");
            output.WriteLine($"{board} {temp} C: flags {flags} (warn {pc.Dev.CustomPdm.OverWarn}, soon {pc.Dev.CustomPdm.CriticalSoon}, crit {pc.Dev.CustomPdm.Critical}), die {pc.Dev.CustomPdm.DieTempC}, DI {di:X}, AN {pc.Dev.AnalogInputs[0].Millivolts} mV / raw {pc.Dev.CustomPdm.AnalogRaw}");
        }
        Assert.True(pc.Dev.CustomPdm!.Critical);
    }

    // The checkbox rule (CustomPdmSettings.WakeInputMaskBadBits) accepts exactly the masks the firmware accepts
    [SimTheory]
    [InlineData("A1", 14, 0x500)]
    [InlineData("B", 15, 0x580)]
    public void WakeRuleMatchesFirmware(string board, int type, int baseId)
    {
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

    // The two cases found in the route A review, on A2 (base 0x540, not the type default 0x500):
    // Read Modified would move the PC device to 0x500 (A1); Write All before a read would set the board to 500K.
    [SimFact]
    public void GuardsStopTheA2Hazards()
    {
        using var bus = new SimBus();
        var pc = Boot(bus, 14, 0x540);
        Assert.Empty(pc.Dev.GetReadMsgs(false));             // Read Modified: nothing to send
        Assert.Empty(pc.Dev.GetWriteMsgs(true));             // Write All before Read All: nothing to send
        pc.Send(pc.Dev.GetWriteMsgs(true));
        pc.Run(500);
        Assert.Equal(0, pc.CountCmd(MessageCommand.WriteAll));
        Assert.Equal(0x540, pc.Dev.BaseId);

        Assert.True(pc.ReadAll());
        Assert.True(pc.Dev.FullReadDone);
        Assert.Equal((0x540, CanBitRate.BitRate1000K, 2), (pc.Dev.BaseId, pc.Dev.BitRate, pc.Dev.CustomPdm!.CritExemptMask));
        pc.Dev.CustomPdm.TempWarn = 57;
        Assert.True(pc.WriteAll());                          // allowed now, and writes what was read
        Assert.Contains("dev: Write Successful", pc.Notes);
        var pc2 = PcTool.For(bus, 14, 0x540);
        Assert.True(pc2.ReadAll());
        Assert.Equal((CanBitRate.BitRate1000K, 57, 2, true), (pc2.Dev.BitRate, pc2.Dev.CustomPdm!.TempWarn,
            pc2.Dev.CustomPdm.CritExemptMask, pc2.Dev.Outputs[1].Enabled)); // board still 1000K, fan config kept
    }

}
