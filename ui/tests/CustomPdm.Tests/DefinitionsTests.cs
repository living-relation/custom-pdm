using System.Collections.Concurrent;
using application.Services;
using domain.Devices;
using domain.Models;
using Xunit;

namespace CustomPdm.Tests;

// Board types 14 (custom-pdm board A) and 15 (board B): counts from firmware/boards/custompdm_*/port.h, cyclic layout
// from firmware/boards/custompdm_*/msg.cpp (frames below are built the way TxMsg0 / TxMsg3 / TxMsg37 build them).
public class DefinitionsTests
{
    public static TheoryData<int, int, int> Boards => new() { { 14, 7, 0x500 }, { 15, 10, 0x580 } };

    [Theory]
    [MemberData(nameof(Boards))]
    public void DefinitionMatchesFirmwarePortH(int type, int numDi, int defaultId)
    {
        var def = new FwDeviceDefManager().GetByDeviceType(type)!;
        Assert.NotNull(def);
        // NUM_OUTPUTS 8, NUM_DIG_OUTPUTS 0, NUM_DIG_INPUTS 7 / 10, NUM_ANALOG_INPUTS 1, NUM_CAN_INPUTS / OUTPUTS 32,
        // NUM_VIRT_INPUTS 16, NUM_FLASHERS 4, NUM_COUNTERS 4, NUM_CONDITIONS 32, NUM_KEYPADS 2, NUM_TIMERS 8, NUM_MATH 8
        Assert.Equal((8, 0, numDi, 1, 32, 32, 16, 4, 4, 32, 2, 8, 8, 1),
            (def.NumOutputs, def.NumDigitalOutputs, def.NumDigitalInputs, def.NumAnalogInputs, def.NumCanInputs,
             def.NumCanOutputs, def.NumVirtualInputs, def.NumFlashers, def.NumCounters, def.NumConditions,
             def.NumKeypads, def.NumTimers, def.NumMath, def.NumCanBuses));
        Assert.True(def.HasWipers && def.HasStarterDisable && def.HasBattVoltSense && def.HasUsb && def.HasExtTempSensor
                    && def.CanSleep && def.CanBootloader);
        Assert.Equal(defaultId, Convert.ToInt32(def.DefaultId, 16)); // DEFAULT_BASE_ID (board A unit 1; unit 2 = 0x540)
        Assert.NotNull(new FwDeviceDefManager().GetDeviceCyclicSigsConfig(type));
    }

    [Theory]
    [MemberData(nameof(Boards))]
    public void VarMapSizeMatchesFirmware(int type, int numDi, int _)
    {
        // port.h VAR_MAP_SIZE: 5 sys + DI*3 + AN*4 + DO + CAN*2 + VI + OUT*4 + FL + COND + CNT + TIMERS*2 + MATH + 6 wiper
        //                      + KEYPADS*(20 buttons + 2 dials + 4 analog) + VAR_MAP_PRO_VARS (4 tables + OUT undercurrent flags)
        var expected = 5 + numDi * 3 + 4 + 0 + 64 + 16 + 32 + 4 + 32 + 4 + 16 + 8 + 6 + 2 * 26 + 4 + 8;
        Assert.Equal(expected, StockTests.MakeDevice(type).VarMap.Count);
    }

    internal static void Feed(FwDevice dev, int id, byte[] data)
    {
        var q = new ConcurrentDictionary<(int BaseId, int Index, int SubIndex), DeviceCanFrame>();
        dev.Read(id, data, ref q, []);
    }

    [Theory]
    [MemberData(nameof(Boards))]
    public void CyclicFramesDecode(int type, int numDi, int baseId)
    {
        var dev = StockTests.MakeDevice(type, baseId);
        // msg 0 (base + 2): byte 0 DI 1-8, byte 1 state + type << 4, total current, batt x10, board temp x10
        ushort diMask = (ushort)(numDi == 7 ? 0b1010101 : 0b10_1010_1101);
        var m0 = new byte[8];
        m0[0] = (byte)(diMask & 0xFF); m0[1] = (byte)(1 + (type << 4));
        BitConverter.GetBytes((ushort)12).CopyTo(m0, 2); BitConverter.GetBytes((ushort)138).CopyTo(m0, 4);
        BitConverter.GetBytes((ushort)412).CopyTo(m0, 6);
        Feed(dev, baseId + 2, m0);
        Assert.Equal((12.0, 13.8, 41.2), (dev.TotalCurrent, Math.Round(dev.BatteryVoltage, 1), Math.Round(dev.BoardTempC, 1)));
        for (var i = 0; i < Math.Min(8, numDi); i++)
            Assert.Equal(((diMask >> i) & 1) == 1, dev.DigitalInputs[i].State);

        // msg 37 (base + 0x27): data16[0] all DIs, data16[1] analog mV, data16[2] raw ADC, data16[3] die temp x10 signed
        var m37 = new byte[8];
        BitConverter.GetBytes(diMask).CopyTo(m37, 0); BitConverter.GetBytes((ushort)3210).CopyTo(m37, 2);
        BitConverter.GetBytes((ushort)2600).CopyTo(m37, 4); BitConverter.GetBytes((short)-123).CopyTo(m37, 6);
        foreach (var d in dev.DigitalInputs) d.State = false;
        Feed(dev, baseId + 0x27, m37);
        for (var i = 0; i < numDi; i++)
            Assert.Equal(((diMask >> i) & 1) == 1, dev.DigitalInputs[i].State);
        Assert.Equal(3210.0, dev.AnalogInputs[0].Millivolts);
        Assert.True(dev.InIdRange(baseId + 0x27));
        Assert.Equal((2600.0, -12.3), (dev.CustomPdm!.AnalogRaw, Math.Round(dev.CustomPdm.DieTempC, 1)));

        // msg 3 (base + 5): bytes 0-3 output states, byte 7 thermal flags (bit 0 warn, 1 critical soon, 2 critical)
        var m3 = new byte[8];
        m3[0] = 0x21; m3[7] = 0b101;
        Feed(dev, baseId + 5, m3);
        Assert.Equal((5, true, false, true), (dev.CustomPdm.ThermalFlags, dev.CustomPdm.OverWarn, dev.CustomPdm.CriticalSoon, dev.CustomPdm.Critical));
        Assert.Equal((domain.Enums.OutState)1, dev.Outputs[0].State);
        Assert.Equal((domain.Enums.OutState)2, dev.Outputs[1].State);
    }
}
