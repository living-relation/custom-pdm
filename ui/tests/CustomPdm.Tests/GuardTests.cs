using domain.CustomPdm;
using domain.Enums;
using Xunit;

namespace CustomPdm.Tests;

// Read / Write Modified off and Write All only after a Read All, for types 14 / 15 only (CustomPdmGuards). The device
// buttons (web/Components/Devices/Shared/DeviceControl.razor) take Disabled from these same calls; DeviceManager and
// FwDevice.GetReadMsgs / GetWriteMsgs refuse the same operations, so no path sends them.
public class GuardTests
{
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    public void StockTypesKeepEveryButton(int type)
    {
        var dev = StockTests.MakeDevice(type);
        Assert.True(CustomPdmGuards.ModifiedOpsAllowed(dev));        // Read, Write buttons on
        Assert.Null(CustomPdmGuards.WriteAllBlockedReason(dev));      // Write All on without a read
        Assert.NotEmpty(dev.GetReadMsgs(false));
        Assert.NotEmpty(dev.GetReadMsgs(true));
        Assert.NotEmpty(dev.GetWriteMsgs(false));
        Assert.NotEmpty(dev.GetWriteMsgs(true));
    }

    [Theory]
    [InlineData(14)]
    [InlineData(15)]
    public void CustomTypesModifiedOffAndWriteAllNeedsRead(int type)
    {
        var dev = StockTests.MakeDevice(type);
        Assert.False(CustomPdmGuards.ModifiedOpsAllowed(dev));       // Read, Write buttons off
        Assert.Equal(CustomPdmGuards.WriteAllNeedsReadReason, CustomPdmGuards.WriteAllBlockedReason(dev)); // Write All off
        Assert.Empty(dev.GetReadMsgs(false));
        Assert.Empty(dev.GetWriteMsgs(false));
        Assert.Empty(dev.GetWriteMsgs(true));
        Assert.Contains(dev.GetReadMsgs(true), f => f.Frame.Payload[0] == (byte)MessageCommand.ReadAll); // Read All on
        Assert.False(dev.FullReadDone);
    }
}
