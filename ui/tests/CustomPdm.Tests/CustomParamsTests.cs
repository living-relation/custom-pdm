using System.Text.Json;
using domain.CustomPdm;
using Xunit;

namespace CustomPdm.Tests;

// Param block 0x7F00 (firmware/core/param_defs.h DEVICE_THERMAL_PARAMS + DEVICE_WAKE_PARAMS) on types 14 / 15 only
public class CustomParamsTests
{
    [Theory]
    [InlineData(14)]
    [InlineData(15)]
    public void BlockFollowsDeviceBlockInFirmwareOrder(int type)
    {
        var p = StockTests.MakeDevice(type).Params;
        // device block 0x0000 sub 0-9, then 0x7F00 sub 0-6, 0x7D00 + o sub 0-2, 0x7E00 + n sub 0-18
        // (param_registry.cpp stParams: thermal, wake, PRO_FEATURES), then outputs 0x1000
        Assert.Equal(Enumerable.Range(0, 10).Select(s => (0x0000, s)), p.Take(10).Select(x => (x.Index, x.SubIndex)));
        var block = p.Skip(10).Take(7).ToList();
        Assert.Equal(Enumerable.Range(0, 7).Select(s => (0x7F00, s)), block.Select(x => (x.Index, x.SubIndex)));
        // defaults: warn 55, critical 80, hysteresis 6, exempt mask 0 (A2 firmware: 2), margin 5, wake mask 0, master retry 0 (off)
        Assert.Equal([55, 80, 6, 0, 5, 0, 0], block.Select(x => (int)x.DefaultValue));
        Assert.All(block, x => Assert.Equal((typeof(int), false), (x.ValueType, x.IsSignedInt)));
        var ext = p.Skip(17).Take(24).ToList();
        Assert.Equal(Enumerable.Range(0, 8).SelectMany(o => Enumerable.Range(0, 3).Select(s => (0x7D00 + o, s))), ext.Select(x => (x.Index, x.SubIndex)));
        Assert.Equal(Enumerable.Repeat(new object[] { 50, 0.0, 500 }, 8).SelectMany(x => x), ext.Select(x => x.DefaultValue));
        Assert.Equal(Enumerable.Repeat(new[] { typeof(int), typeof(double), typeof(int) }, 8).SelectMany(x => x), ext.Select(x => x.ValueType));
        var tab = p.Skip(41).Take(76).ToList();
        Assert.Equal(Enumerable.Range(0, 4).SelectMany(n => Enumerable.Range(0, 19).Select(s => (0x7E00 + n, s))), tab.Select(x => (x.Index, x.SubIndex)));
        Assert.All(tab.Where(x => x.SubIndex == 0), x => Assert.Equal((typeof(bool), (object)false), (x.ValueType, x.DefaultValue)));
        Assert.All(tab.Where(x => x.SubIndex is 1 or 2), x => Assert.Equal((typeof(int), (object)0), (x.ValueType, x.DefaultValue)));
        Assert.All(tab.Where(x => x.SubIndex >= 3), x => Assert.Equal((typeof(double), (object)0.0), (x.ValueType, x.DefaultValue)));
        Assert.Equal(0x1000, p[117].Index);
        Assert.Equal(7, p.Count(x => x.Index == CustomPdmSettings.BaseIndex));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    public void StockTypesHaveNoBlock(int type)
    {
        var dev = StockTests.MakeDevice(type);
        Assert.Null(dev.CustomPdm);
        Assert.DoesNotContain(dev.Params, x => x.Index == CustomPdmSettings.BaseIndex);
        Assert.DoesNotContain(dev.Params, x => (x.Index & 0xFF00) is CustomPdmSettings.OutputExtBaseIndex or CustomPdmSettings.TableBaseIndex);
        Assert.DoesNotContain(dev.VarMap, v => v.PropertyName == "Undercurrent" || v.GetName().StartsWith("Table "));
        Assert.DoesNotContain("customPdm", JsonSerializer.Serialize(dev));
    }

    [Fact]
    public void SettingsSavedAndLoadedWithTheProjectFile()
    {
        var dev = StockTests.MakeDevice(15);
        dev.CustomPdm!.TempWarn = 61; dev.CustomPdm.WakeInputMask = 0x0C;
        var json = JsonSerializer.Serialize(dev);
        var back = JsonSerializer.Deserialize<domain.Devices.FwDevice>(json)!;
        back.ApplyDefinition(dev.Def);   // what ConfigFileManager.LoadDevices does
        Assert.Equal((61, 0x0C, 10), (back.CustomPdm!.TempWarn, back.CustomPdm.WakeInputMask, back.CustomPdm.NumDigitalInputs));
        Assert.Equal(61, back.Params.Single(x => x.Index == 0x7F00 && x.SubIndex == 0).GetValue());
    }

    // firmware/core/sleep.cpp WakeInputMaskBadBits with the pins of firmware/boards/custompdm_*/board.h
    [Theory]
    [InlineData(14, 0b0000101, 0b0000101)]   // A DI1 PA10 + DI3 PC10: same line 10
    [InlineData(14, 0b0001000, 0b0001000)]   // A DI4 PC11 = USB D- PA11
    [InlineData(14, 0b1110110, 0)]           // A DI2, DI3, DI5-7: all on own lines
    [InlineData(14, 0b1111111, 0b0001101)]
    [InlineData(15, 0x101, 0x101)]           // B DI1 PA10 + DI9 PC10
    [InlineData(15, 0x200, 0x200)]           // B DI10 PC11 = USB D-
    [InlineData(15, 0x0FF, 0)]               // B DI1-8: own lines (B_IN5 on PC13 since B1)
    [InlineData(15, 0x3FF, 0x301)]
    [InlineData(0, 0xFF, 0)]                 // stock types: no rule (they never get the block)
    public void WakeRule(int type, int mask, int bad) =>
        Assert.Equal(bad, CustomPdmSettings.WakeInputMaskBadBits(type, mask));

    [Fact]
    public void WakeCheckboxesBlockPartnersAndUsbLine()
    {
        var s = StockTests.MakeDevice(14).CustomPdm!;
        Assert.True(s.WakeInputNeverAllowed(3));                       // DI4 on the USB D- line
        Assert.False(s.WakeInputNeverAllowed(0));
        s.WakeInputMask = 0b0000001;                                   // DI1 selected
        Assert.True(s.WakeInputBlocked(2));                            // so DI3 (same line) is greyed out
        Assert.False(s.WakeInputBlocked(0));                           // DI1 itself can be unticked
        Assert.False(s.WakeInputBlocked(1));
        Assert.True(s.IsValid());
        s.WakeInputMask = 0b0000101;
        Assert.False(s.IsValid());
        s.WakeInputMask = 0; s.CritExemptMask = 0x100;                 // 9 outputs: out of range (NUM_OUTPUTS 8)
        Assert.False(s.IsValid());
    }
}
