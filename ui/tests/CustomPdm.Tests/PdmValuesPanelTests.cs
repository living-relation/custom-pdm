using application.Services;
using Bunit;
using domain.CustomPdm;
using domain.Models;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using MudBlazor;
using MudBlazor.Services;
using web.Components.CustomPdm;
using web.Services;
using Xunit;

namespace CustomPdm.Tests;

// uifix (BACKLOG 2026-11-21): the /pdm "Values and system" panel itself (bUnit), for every board set its view can hold:
// another /pdm tab refreshes while New PDM adds A1, A2 and B one by one (A1, then A1 + A2), or a project without B.
// Before the fix it threw "Sequence contains no matching element" (default board "B"). Logic: PdmPartialViewTests.
public class PdmValuesPanelTests : BunitContext, IAsyncLifetime
{
    public PdmValuesPanelTests()
    {
        JSInterop.Mode = JSRuntimeMode.Loose;
        Services.AddMudServices();
        var log = new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs"));
        var mgr = new DeviceManager(NullLogger<DeviceManager>.Instance, NullLoggerFactory.Instance, log, new FwDeviceDefManager());
        Services.AddSingleton(log);
        Services.AddSingleton(new PdmOpsService(mgr));
        Services.AddScoped<NotificationService>();
        Render<MudPopoverProvider>();   // as MainLayout: the panel's MudSelects need it
    }

    // MudBlazor's PopoverService is IAsyncDisposable only
    Task IAsyncLifetime.InitializeAsync() => Task.CompletedTask;
    Task IAsyncLifetime.DisposeAsync() => DisposeAsync().AsTask();

    private IRenderedComponent<PdmValuesPanel> Panel(PdmView v) => Render<PdmValuesPanel>(p => p.Add(x => x.View, v));

    [Theory]
    [InlineData("A1", "A1")]
    [InlineData("A1,A2", "A1")]
    [InlineData("B", "B")]
    [InlineData("A1,A2,B", "B")]
    public void RendersForEveryBoardSet(string roles, string shown)
    {
        var cut = Panel(PdmPartialViewTests.View(roles.Split(',')));
        Assert.Contains($"{shown}: CAN inputs", cut.Markup);   // the board summary (PdmModel.Use) of the board shown
    }

    [Fact]
    public void ShowsBAgainOnceNewPdmHasAddedIt()
    {
        var cut = Panel(PdmPartialViewTests.View("A1", "A2"));
        Assert.Contains("A1: CAN inputs", cut.Markup);
        cut.Render(p => p.Add(x => x.View, PdmPartialViewTests.View("A1", "A2", "B")));   // the next 10 Hz refresh
        Assert.Contains("B: CAN inputs", cut.Markup);
    }
}
