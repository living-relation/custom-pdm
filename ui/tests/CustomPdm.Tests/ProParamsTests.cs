using System.Text.Json;
using domain.CustomPdm;
using Xunit;

namespace CustomPdm.Tests;

// PRO_FEATURES settings (docs/feature-parity.md P1 P2 P3 T1) on the PC side: CustomPdmSettings / CustomPdmPro.cs
public class ProParamsTests
{
    // Firmware var map (core/device.cpp InitVarMap + port.h VAR_MAP_PRO_VARS): A 264 + 4 tables + 8 flags, B 273 + 12
    [Theory]
    [InlineData(14, 276)]
    [InlineData(15, 285)]
    public void VarMapEndsWithTablesThenUndercurrentFlags(int type, int size)
    {
        var dev = StockTests.MakeDevice(type);
        Assert.Equal(size, dev.VarMap.Count);
        Assert.Equal(Enumerable.Range(0, size), dev.VarMap.Select(v => v.VariableIndex));
        var tail = dev.VarMap.TakeLast(12).ToList();
        Assert.Equal(["Table 1", "Table 2", "Table 3", "Table 4"], tail.Take(4).Select(v => v.GetName()));
        Assert.All(tail.Take(4), v => Assert.Equal(("Value", "float", true), (v.PropertyName, v.DataType, v.Owner == null)));
        Assert.Equal(dev.Outputs.Cast<object>(), tail.Skip(4).Select(v => (object)v.Owner!));
        Assert.All(tail.Skip(4), v => Assert.Equal(("Undercurrent", "bool"), (v.PropertyName, v.DataType)));
        Assert.Equal(size, dev.CustomPdm!.VarMapSize);
    }

    [Fact]
    public void ResetLimitWording() =>
        Assert.Equal(("3 trips in all (first try + 2 retries)", "2 trips in all (first try + 1 retry)", "1 trip in all (first try + 0 retries)"),
            (CustomPdmSettings.ResetLimitText(3), CustomPdmSettings.ResetLimitText(2), CustomPdmSettings.ResetLimitText(1)));

    // Same results as the firmware's LookupTable::Update (firmware/sim/s3_features.py F6 T1 checks)
    [Fact]
    public void TableEvaluatesLikeTheFirmware()
    {
        var t = new LookupTable { Enabled = true, Points = 5 };
        double[] xs = [80, 85, 90, 95, 100], ys = [0, 30, 40, 70, 100];
        for (var i = 0; i < 5; i++) { t.X[i] = xs[i]; t.Y[i] = ys[i]; }
        Assert.Equal(new double[] { 0, 0, 6, 15, 30, 35, 55, 82, 100, 100 }, new[] { 70, 80, 81, 82.5, 85, 87.5, 92.5, 97, 100, 130 }.Select(x => Math.Round(t.Evaluate(x), 6)));
        Assert.True(t.IsUsable);
        Assert.Null(t.Warning);
        t.X[1] = 75;                                  // not rising: the firmware gives 0
        Assert.False(t.IsUsable);
        Assert.Equal(0, t.Evaluate(90));
        Assert.Equal("X must rise from point to point: this table outputs 0.", t.Warning);
        t.X[1] = 80;                                  // equal x: not rising either
        Assert.Equal(0, t.Evaluate(90));
        t.X[1] = 85; t.Points = 1;
        Assert.Equal(0, t.Evaluate(90));
        Assert.Equal("Needs 2 to 8 points: this table outputs 0.", t.Warning);
        t.Points = 5; t.Enabled = false;
        Assert.Equal(0, t.Evaluate(90));
        Assert.Null(t.Warning);                       // disabled: nothing to warn about
    }

    [Fact]
    public void RangesFollowTheFirmware()
    {
        var c = StockTests.MakeDevice(14).CustomPdm!;
        Assert.True(c.IsValid());
        c.OutputProtection[3].TripTime = 10001; Assert.False(c.IsValid());
        c.OutputProtection[3].TripTime = 10000; Assert.True(c.IsValid());
        c.OutputProtection[0].MinCurrent = -0.1; Assert.False(c.IsValid());
        c.OutputProtection[0].MinCurrent = 100.0; Assert.True(c.IsValid());
        c.OutputProtection[7].MinCurrentTime = 60001; Assert.False(c.IsValid());
        c.OutputProtection[7].MinCurrentTime = 0; Assert.True(c.IsValid());
        c.Tables[2].Points = 9; Assert.False(c.IsValid());
        c.Tables[2].Points = 8; Assert.True(c.IsValid());
        c.Tables[2].Input = 276; Assert.False(c.IsValid());     // var map A = 276 entries
        c.Tables[2].Input = 275; Assert.True(c.IsValid());
        c.MasterRetryInput = 276; Assert.False(c.IsValid());
        c.MasterRetryInput = 275; Assert.True(c.IsValid());
        c.Tables[1].X[0] = 2e9; Assert.False(c.IsValid());
        c.Tables[1].X[0] = 5; c.Tables[1].X[1] = 1; c.Tables[1].Points = 2; c.Tables[1].Enabled = true;
        Assert.True(c.IsValid());                                // unsorted is allowed (the firmware takes it and outputs 0)
    }

    [Fact]
    public void SettingsSavedAndLoadedWithTheProjectFile()
    {
        var dev = StockTests.MakeDevice(15);
        var c = dev.CustomPdm!;
        c.MasterRetryInput = 120; c.OutputProtection[5].TripTime = 250; c.OutputProtection[5].MinCurrent = 0.7;
        c.Tables[3].Enabled = true; c.Tables[3].Points = 3; c.Tables[3].X[2] = 12.5; c.Tables[3].Y[2] = -4;
        var json = JsonSerializer.Serialize(dev);
        var back = JsonSerializer.Deserialize<domain.Devices.FwDevice>(json)!;
        back.ApplyDefinition(dev.Def);
        var b = back.CustomPdm!;
        Assert.Equal((120, 250, 0.7, true, 3, 12.5, -4.0), (b.MasterRetryInput, b.OutputProtection[5].TripTime, b.OutputProtection[5].MinCurrent,
            b.Tables[3].Enabled, b.Tables[3].Points, b.Tables[3].X[2], b.Tables[3].Y[2]));
        Assert.Equal((8, 4, 8), (b.OutputProtection.Count, b.Tables.Count, b.Tables[0].X.Count));
        Assert.Equal(250, back.Params.Single(x => x.Index == 0x7D05 && x.SubIndex == 0).GetValue());
        Assert.Equal(12.5, back.Params.Single(x => x.Index == 0x7E03 && x.SubIndex == 5).GetValue());
    }

    [Fact]
    public void AProjectFileWithShortListsIsPaddedToTheBoard()
    {
        var dev = StockTests.MakeDevice(14);
        var json = JsonSerializer.Serialize(dev).Replace("\"tables\":[", "\"tablesX\":[");   // an older file: no tables at all
        var back = JsonSerializer.Deserialize<domain.Devices.FwDevice>(json)!;
        back.ApplyDefinition(dev.Def);
        Assert.Equal((4, 8), (back.CustomPdm!.Tables.Count, back.CustomPdm.Tables[3].Y.Count));
        Assert.Equal(dev.Params.Select(p => (p.Index, p.SubIndex)), back.Params.Select(p => (p.Index, p.SubIndex)));
    }
}
