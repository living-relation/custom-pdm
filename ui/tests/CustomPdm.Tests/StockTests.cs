using System.Security.Cryptography;
using System.Text;
using application.Services;
using domain.Devices;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Xunit.Abstractions;

namespace CustomPdm.Tests;

// Stock device types must behave exactly as before our changes. The fingerprint covers what the device type
// drives: the parameter list (order, index, sub-index, type, sign, default = Read All / Write All / CRC check),
// the variable map and the cyclic signal decode. Expected values were taken from the unmodified import
// (dingoConfig development @ 01134ad, ui/dingoConfig import commit) with this same code.
public class StockTests(ITestOutputHelper output)
{
    internal static FwDevice MakeDevice(int deviceType, int baseId = 0x100)
    {
        var mgr = new FwDeviceDefManager();
        var def = mgr.GetByDeviceType(deviceType) ?? throw new InvalidOperationException($"no device type {deviceType}");
        var dev = new FwDevice("dev", baseId, def, mgr.GetDeviceCyclicSigsConfig(deviceType));
        dev.SetLogger(NullLogger<FwDevice>.Instance);
        return dev;
    }

    internal static string Fingerprint(FwDevice dev)
    {
        var sb = new StringBuilder();
        foreach (var p in dev.Params)
            sb.Append($"P {p.Index:X4}:{p.SubIndex}:{p.ValueType.Name}:{p.IsSignedInt}:{p.DefaultValue}\n");
        foreach (var v in dev.VarMap)
            sb.Append($"V {v.VariableIndex}:{v.DataType}:{v.GetName()}\n");
        foreach (var (id, s) in dev.GetCyclicSigs().OrderBy(x => x.MessageId).ThenBy(x => x.Signal.StartBit))
            sb.Append($"S {id:X3}:{s.Name}:{s.StartBit}:{s.Length}:{s.IsSigned}:{s.Factor}:{s.Unit}\n");
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(sb.ToString())))[..16];
    }

    [Theory]
    [InlineData(0, "4C4D9D570F27B19D")]
    [InlineData(1, "993602331A6CA0B8")]
    [InlineData(2, "173C06D05BD1115E")]
    [InlineData(3, "B297A5C00FC43AAD")]
    public void StockTypeUnchanged(int deviceType, string expected)
    {
        var dev = MakeDevice(deviceType);
        var fp = Fingerprint(dev);
        output.WriteLine($"type {deviceType}: {fp} ({dev.Params.Count} params, {dev.VarMap.Count} vars)");
        Assert.Equal(expected, fp);
    }
}
