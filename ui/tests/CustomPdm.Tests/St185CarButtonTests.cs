using application.Services;
using Bunit;
using domain.CustomPdm;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Logging.Abstractions;
using MudBlazor;
using MudBlazor.Services;
using web.Components.CustomPdm;
using web.Services;
using Xunit;

namespace CustomPdm.Tests;

// carconfig: the empty /pdm page shows "Load the ST185 car config" next to the starter (bUnit), and the button
// loads the car config like a New PDM (writable).
public class St185CarButtonTests : BunitContext, IAsyncLifetime
{
    private sealed class Env : IWebHostEnvironment
    {
        public string WebRootPath { get; set; } = AppContext.BaseDirectory;
        public IFileProvider WebRootFileProvider { get; set; } = new NullFileProvider();
        public string ApplicationName { get; set; } = "web";
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
        public string ContentRootPath { get; set; } = AppContext.BaseDirectory;
        public string EnvironmentName { get; set; } = "Test";
    }

    private readonly DeviceManager _devices;
    private readonly PdmOpsService _pdm;

    public St185CarButtonTests()
    {
        JSInterop.Mode = JSRuntimeMode.Loose;
        Services.AddMudServices();
        var log = new SystemLogger(Path.Combine(Path.GetTempPath(), "cpdm-ui-test-logs"));
        (_devices, _pdm) = St185CarTests.NewApp();
        Services.AddSingleton(log);
        Services.AddSingleton(_devices);
        Services.AddSingleton(_pdm);
        Services.AddSingleton(new ConfigFileManager(NullLogger<ConfigFileManager>.Instance, new FwDeviceDefManager()));
        Services.AddSingleton<IWebHostEnvironment>(new Env());
        Services.AddScoped<NotificationService>();
        Render<MudPopoverProvider>();
    }

    Task IAsyncLifetime.InitializeAsync() => Task.CompletedTask;
    Task IAsyncLifetime.DisposeAsync() => DisposeAsync().AsTask();

    [Fact]
    public void TheCarConfigButtonSitsNextToTheStarterAndLoadsTheCar()
    {
        var cut = Render<PdmNewProject>();
        Assert.Contains("Load the ST185 starter", cut.Find("#pdm-load-starter").TextContent);
        Assert.Contains("Load the ST185 car config", cut.Find("#pdm-load-car").TextContent);
        Assert.Contains("install config", cut.Markup);

        cut.Find("#pdm-load-car").Click();
        cut.WaitForAssertion(() => Assert.Equal(3, _pdm.BuildView().Boards.Count));
        var v = _pdm.BuildView();
        Assert.Equal(("CAN-Lambda", "Power windows"), (v.Outputs.Single(o => o.Number == 1).Output.Name, v.Outputs.Single(o => o.Number == 17).Output.Name));
        Assert.All(v.Boards, b => Assert.True(b.Device.CustomPdm!.FactoryNew));
        Assert.Null(_pdm.BlockedReason(PdmOpKind.WriteAll, v, true));
    }
}
