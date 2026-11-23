using application.Services;
using infrastructure.Adapters;
using infrastructure.BackgroundServices;
using infrastructure.Comms;
using infrastructure.Logging;
using web.Components;
using web.Services;
using MudBlazor.Services;
using domain.Interfaces;
using Microsoft.AspNetCore.Components;
using MudBlazor;
using Microsoft.AspNetCore.Connections;
using System.Runtime.InteropServices;
using Microsoft.AspNetCore.DataProtection;

// Hide console window on Windows
if (OperatingSystem.IsWindows())
{
    HideConsoleWindow();
}

var builder = WebApplication.CreateBuilder(args);

// Configure host shutdown timeout
builder.Host.ConfigureHostOptions(opts =>
{
    opts.ShutdownTimeout = TimeSpan.FromSeconds(5);
});

// Add Blazor services
builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents(options =>
    {
        options.DetailedErrors = true;
    });
builder.Services.AddMudServices(config =>
{
    config.SnackbarConfiguration.PositionClass = Defaults.Classes.Position.BottomRight;

    config.SnackbarConfiguration.PreventDuplicates = true;
    config.SnackbarConfiguration.NewestOnTop = true;
    config.SnackbarConfiguration.ShowCloseIcon = true;
    config.SnackbarConfiguration.SnackbarVariant = Variant.Outlined;
});

// Add HttpClient for Blazor Server to call local API
builder.Services.AddScoped(sp =>
{
    var navigationManager = sp.GetRequiredService<NavigationManager>();
    return new HttpClient { BaseAddress = new Uri(navigationManager.BaseUri) };
});

// Add NotificationService for combined Snackbar + GlobalLogger calls
builder.Services.AddScoped<NotificationService>();

// Add API services
builder.Services.AddTransient<UsbAdapter>();
builder.Services.AddTransient<SlcanAdapter>();
builder.Services.AddTransient<SlcanTcpAdapter>();
builder.Services.AddTransient<KvaserAdapter>();
#if LINUX
builder.Services.AddTransient<SocketCanAdapter>();
#endif
builder.Services.AddTransient<PcanAdapter>();
builder.Services.AddTransient<SimAdapter>();

builder.Services.AddSingleton<ICommsAdapterManager, CommsAdapterManager>();
builder.Services.AddSingleton<FwDeviceDefManager>();
builder.Services.AddSingleton<ConfigFileManager>();
builder.Services.AddSingleton<DeviceManager>();
builder.Services.AddSingleton<PdmOpsService>(sp => new PdmOpsService(sp.GetRequiredService<DeviceManager>()) // custom-pdm: /pdm Read All / Write All / Burn
    { AdapterConnected = () => sp.GetRequiredService<ICommsAdapterManager>().IsConnected, AutoRead = true }); // custom-pdm p2a: read boards on connect
builder.Services.AddSingleton<PdmSimService>(); // custom-pdm: /pdm Simulator panel (only with the simulator bridge)
builder.Services.AddSingleton<PdmOutputTestService>(sp => new PdmOutputTestService(sp.GetRequiredService<DeviceManager>(), sp.GetRequiredService<PdmOpsService>()) // custom-pdm uifix2: /pdm Output test
    { AdapterConnected = () => sp.GetRequiredService<ICommsAdapterManager>().IsConnected });
builder.Services.AddSingleton<CanMsgLogger>();
builder.Services.AddSingleton<SystemLogger>();
builder.Services.AddSingleton<SimPlayback>();
builder.Services.AddSingleton<DevicePlotService>();
builder.Services.AddSingleton<PlotService>();
builder.Services.AddSingleton<DeviceSignalService>();
builder.Services.AddSingleton<UserPreferencesManager>();

// Add background services
builder.Services.AddHostedService<CommsDataPipeline>();
builder.Services.AddHostedService<web.Services.PdmAutoConnectService>(); // custom-pdm: --PdmAutoConnect:* launch flags (uiwalk)

// Add GlobalLogger to logging pipeline using factory to avoid creating duplicate singleton
builder.Logging.Services.AddSingleton<ILoggerProvider>(sp =>
    new SystemLoggerProvider(sp.GetRequiredService<SystemLogger>()));

var app = builder.Build();

_ = app.Services.GetRequiredService<DevicePlotService>();
// Start sampling immediately so dashboard sparklines have history when first opened
_ = app.Services.GetRequiredService<PlotService>();

// Initialize user preferences
var userPrefsManager = app.Services.GetRequiredService<UserPreferencesManager>();
userPrefsManager.Initialize();

// Configure the HTTP request pipeline.
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    app.UseHsts();
}

app.UseHttpsRedirection();

app.UseStaticFiles();
app.UseAntiforgery();

app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

// custom-pdm uifix2: an output test puts its values back before the adapter disconnects and when the app closes
var pdmOutputTest = app.Services.GetRequiredService<PdmOutputTestService>();
if (app.Services.GetRequiredService<ICommsAdapterManager>() is infrastructure.Comms.CommsAdapterManager pdmAdapters)
    pdmAdapters.BeforeDisconnect = () => pdmOutputTest.StopNow("adapter disconnect");
app.Lifetime.ApplicationStopping.Register(() => pdmOutputTest.StopNow("app closing"));

// Open browser on launch in non-Development environments (e.g., published Release builds)
var isDevelopment = app.Environment.IsDevelopment();
if (!isDevelopment)
{
    var lifetime = app.Services.GetRequiredService<IHostApplicationLifetime>();
    lifetime.ApplicationStarted.Register(() => OpenBrowser("http://localhost:5000"));
}

try
{
    app.Run();
}
catch (IOException ex) when (ex.InnerException is AddressInUseException)
{
    // Port is already in use - app is already running, just open browser
    if (!isDevelopment)
    {
        OpenBrowser("http://localhost:5000");
    }
}

static void OpenBrowser(string url)
{
    try
    {
        if (OperatingSystem.IsWindows())
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true
            });
        }
        else if (OperatingSystem.IsLinux())
        {
            System.Diagnostics.Process.Start("xdg-open", url);
        }
        else if (OperatingSystem.IsMacOS())
        {
            System.Diagnostics.Process.Start("open", url);
        }
    }
    catch
    {
        // Browser launch failed - app will still run
    }
}

[DllImport("kernel32.dll")]
static extern IntPtr GetConsoleWindow();

[DllImport("user32.dll")]
static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

static void HideConsoleWindow()
{
    const int SW_HIDE = 0;
    var handle = GetConsoleWindow();
    ShowWindow(handle, SW_HIDE);
}
