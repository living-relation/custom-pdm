using application.Services;
using domain.CustomPdm;
using domain.Interfaces;

namespace web.Services;

// uiwalk (2026-11-21): connects the CAN adapter once at start when a --PdmAutoConnect:* launch flag asks for it
// (domain/CustomPdm/PdmAutoConnect.cs; ui/Start-PdmUi.ps1 passes the simulator bridge). Without a flag it does nothing.
public class PdmAutoConnectService(IConfiguration config, ICommsAdapterManager manager, UserPreferencesManager prefs,
    ILogger<PdmAutoConnectService> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var p = prefs.Preferences;
        var (plan, why) = PdmAutoConnect.Plan(config["PdmAutoConnect:Adapter"], config["PdmAutoConnect:Port"],
            config["PdmAutoConnect:BitRate"], string.Equals(config["PdmAutoConnect:Last"], "true", StringComparison.OrdinalIgnoreCase),
            new PdmLastAdapter(p.SelectedAdapter, p.SelectedPort, p.SelectedTcpEndpoint, p.SelectedBitrate));
        if (plan == null)
        {
            if (why != null) logger.LogWarning("{Why}", why);
            return;
        }

        try
        {
            await Task.Delay(500, stoppingToken); // let the pipeline start first
            var (ok, text) = await PdmAutoConnect.RunAsync(manager, plan, tries: 10, gap: TimeSpan.FromSeconds(1), ct: stoppingToken);
            if (ok) logger.LogInformation("{Text}", text);
            else logger.LogWarning("{Text}", text);
            // the remembered adapter (user preferences) is left as the user's last own Connect made it: a second
            // copy started with other flags must not change what the first one shows
        }
        catch (OperationCanceledException) { /* app is stopping */ }
    }
}
