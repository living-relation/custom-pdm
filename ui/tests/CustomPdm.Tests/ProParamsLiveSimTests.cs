using domain.CustomPdm;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// PRO_FEATURES params (0x7F00 sub 6, 0x7D00 + o, 0x7E00 + n) through dingoConfig's Read All / Write All against our real
// firmware logic (host sim, factory-fresh FRAM): same list and order as the firmware, factory values = PC defaults,
// new values written, read back by a second PC, and the CRC check sees a changed table point.
[Collection("sim")]
public class ProParamsLiveSimTests(ITestOutputHelper output)
{
    public static TheoryData<string, int, int> Boards => new() { { "A1", 14, 0x500 }, { "B", 15, 0x580 } };

    [SimTheory]
    [MemberData(nameof(Boards))]
    public void WriteAllReadAllRoundTrip(string board, int type, int baseId)
    {
        using var bus = new SimBus();
        var pc = PcTool.For(bus, type, baseId);
        pc.Run(1500);
        Assert.True(pc.ReadAll(), "no CRC check reply");
        Assert.False(pc.Dev.ConfigMismatch, "config CRC check after Read All");
        bool Pro(domain.Models.DeviceParameter p) =>
            (p.Index == CustomPdmSettings.BaseIndex && p.SubIndex == CustomPdmSettings.MasterRetrySub) ||
            (p.Index & 0xFF00) is CustomPdmSettings.OutputExtBaseIndex or CustomPdmSettings.TableBaseIndex;
        var pro = pc.Dev.Params.Where(Pro).ToList();
        Assert.Equal(1 + 8 * 3 + 4 * 19, pro.Count);
        Assert.Empty(pro.Where(p => p.IsModified).Select(p => p.Name));   // firmware factory values = PC defaults

        var c = pc.Dev.CustomPdm!;
        var tableVar = pc.Dev.VarMap.First(v => v.GetName() == "Table 2").VariableIndex;
        c.MasterRetryInput = tableVar;                               // any var can drive it; here table 2's output
        for (var o = 0; o < 8; o++)
        {
            c.OutputProtection[o].TripTime = 100 + 10 * o;
            c.OutputProtection[o].MinCurrent = 0.25 * (o + 1);
            c.OutputProtection[o].MinCurrentTime = 1000 + o;
        }
        var t = c.Tables[1];
        t.Enabled = true; t.Input = 4; t.Points = 8;                 // battery voltage -> any curve
        for (var i = 0; i < 8; i++) { t.X[i] = 8 + i * 1.5; t.Y[i] = 100 - i * 12.5; }
        c.Tables[3].Points = 2; c.Tables[3].X[0] = 5; c.Tables[3].X[1] = 1;   // unsorted: accepted by the firmware (outputs 0)
        Assert.True(c.IsValid());
        Assert.True(pc.WriteAll(), "no CRC check reply after Write All");
        Assert.Contains("dev: Write Successful", pc.Notes);
        Assert.False(pc.Dev.ConfigMismatch, "config CRC check after Write All");

        var pc2 = PcTool.For(bus, type, baseId);
        Assert.True(pc2.ReadAll());
        Assert.False(pc2.Dev.ConfigMismatch);
        var c2 = pc2.Dev.CustomPdm!;
        Assert.Equal(tableVar, c2.MasterRetryInput);
        Assert.Equal(Enumerable.Range(0, 8).Select(o => (100 + 10 * o, 0.25 * (o + 1), 1000 + o)),
            c2.OutputProtection.Select(p => (p.TripTime, p.MinCurrent, p.MinCurrentTime)));
        Assert.Equal((true, 4, 8), (c2.Tables[1].Enabled, c2.Tables[1].Input, c2.Tables[1].Points));
        Assert.Equal(t.X, c2.Tables[1].X);
        Assert.Equal(t.Y, c2.Tables[1].Y);
        Assert.Equal((2, 5.0, 1.0), (c2.Tables[3].Points, c2.Tables[3].X[0], c2.Tables[3].X[1]));
        Assert.Equal(pc.Dev.Params.Select(p => p.GetValue()), pc2.Dev.Params.Select(p => p.GetValue()));

        c2.Tables[1].Y[7] = 1.5;                                     // the PC now differs from the board in one table point
        pc2.Send([pc2.Dev.GetCheckMsg()]);
        pc2.RunUntil(() => pc2.Dev.ConfigMismatch, 1000);
        Assert.True(pc2.Dev.ConfigMismatch, "CRC check must see a changed table value");
        output.WriteLine($"{board}: {pro.Count} PRO_FEATURES params round-tripped; table 2 var index {tableVar}");
    }
}
