using domain.Enums;
using domain.Interfaces;

namespace domain.CustomPdm;

// uiwalk (2026-11-21): connect the CAN adapter when the app starts, so the launcher's "PDM UI" needs no adapter pick
// and no Connect click. Launch flags (ASP.NET configuration, so "--PdmAutoConnect:Adapter x" on the command line):
//   --PdmAutoConnect:Adapter "SLCAN TCP" --PdmAutoConnect:Port localhost:3333 --PdmAutoConnect:BitRate 1000K
//   --PdmAutoConnect:Last true      the adapter, port and bit rate of the last successful Connect (user preferences)
// No flag: nothing is connected by itself (stock behaviour). Used by web/Services/PdmAutoConnectService.cs.
public record PdmAutoConnectPlan(string Adapter, string Port, CanBitRate BitRate);

public record PdmLastAdapter(string? Adapter, string? Port, string? TcpEndpoint, CanBitRate BitRate);

public static class PdmAutoConnect
{
    public const string SlcanTcp = "SLCAN TCP";

    // "1000K", "500k", "BitRate1000K" -> the enum value; null when it is none of them
    public static CanBitRate? ParseBitRate(string? text)
    {
        if (string.IsNullOrWhiteSpace(text)) return null;
        var t = text.Trim();
        if (!t.StartsWith("BitRate", StringComparison.OrdinalIgnoreCase)) t = "BitRate" + t;
        return Enum.TryParse<CanBitRate>(t, ignoreCase: true, out var rate) && Enum.IsDefined(rate) ? rate : null;
    }

    // The port the adapter toolbar would use for this adapter (web/Components/Shared/AdapterToolbarControl.razor)
    public static string? PortOf(string adapter, string? port, string? tcpEndpoint) => adapter switch
    {
        "Sim" => "Simulated",
        "PCAN" => "PCAN_USBBUS1",
        "Kvaser" => "0",
        SlcanTcp => string.IsNullOrWhiteSpace(tcpEndpoint) ? null : tcpEndpoint.Trim(),
        _ => string.IsNullOrWhiteSpace(port) ? null : port.Trim()
    };

    // What to connect at start (Plan), or why nothing is connected (Why; null = no flag given, say nothing)
    public static (PdmAutoConnectPlan? Plan, string? Why) Plan(string? adapter, string? port, string? bitRate, bool last,
        PdmLastAdapter? remembered)
    {
        if (!string.IsNullOrWhiteSpace(adapter))
        {
            var a = adapter.Trim();
            var p = a == SlcanTcp ? PortOf(a, null, port) : PortOf(a, port, null);
            if (p == null) return (null, $"auto-connect: adapter '{a}' needs --PdmAutoConnect:Port.");
            var rate = ParseBitRate(bitRate);
            if (rate == null && !string.IsNullOrWhiteSpace(bitRate))
                return (null, $"auto-connect: '{bitRate}' is not a CAN bit rate (e.g. 500K, 1000K).");
            return (new PdmAutoConnectPlan(a, p, rate ?? CanBitRate.BitRate1000K), null);
        }

        if (!last) return (null, null);
        if (remembered == null || string.IsNullOrWhiteSpace(remembered.Adapter))
            return (null, "auto-connect: no adapter remembered yet (connect once by hand).");
        var ra = remembered.Adapter.Trim();
        var rp = PortOf(ra, remembered.Port, remembered.TcpEndpoint);
        return rp == null
            ? (null, $"auto-connect: no port remembered for adapter '{ra}' (connect once by hand).")
            : (new PdmAutoConnectPlan(ra, rp, remembered.BitRate), null);
    }

    // Tries to connect (the simulator bridge or the adapter may come up a moment after the app). Returns what
    // happened in words; Ok = connected by this call or already connected.
    public static async Task<(bool Ok, string Text)> RunAsync(ICommsAdapterManager manager, PdmAutoConnectPlan plan,
        int tries, TimeSpan gap, Func<TimeSpan, CancellationToken, Task>? delay = null, CancellationToken ct = default)
    {
        delay ??= Task.Delay;
        var what = $"{plan.Adapter} {plan.Port} {plan.BitRate.ToString().Replace("BitRate", "")}";
        string? lastError = null;
        for (var i = 1; i <= Math.Max(1, tries); i++)
        {
            if (manager.IsConnected) return (true, "auto-connect: an adapter is already connected, nothing done.");
            try
            {
                if (await manager.ConnectAsync(manager.ToAdapter(plan.Adapter), plan.Port, plan.BitRate, ct))
                    return (true, $"auto-connect: connected to {what}" + (i > 1 ? $" (try {i})." : "."));
                lastError = null;
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex) { lastError = ex.Message; }

            if (i < tries) await delay(gap, ct);
        }

        return (false, $"auto-connect: {what} did not connect in {Math.Max(1, tries)} tries" +
                       (lastError != null ? $" ({lastError})" : "") + ". Use the Adapter button.");
    }
}
