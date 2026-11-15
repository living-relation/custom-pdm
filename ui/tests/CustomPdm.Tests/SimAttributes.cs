using Xunit;

namespace CustomPdm.Tests;

// Live tests need the firmware host-sim builds in WSL (ui/README.md). Without CUSTOMPDM_SIM_SO they are reported as
// Skipped, not as passed.
internal static class Sim
{
    public const string SkipReason = "CUSTOMPDM_SIM_SO not set (WSL folder with the firmware host-sim .so files, ui/README.md)";
    public static bool Missing => string.IsNullOrEmpty(Environment.GetEnvironmentVariable("CUSTOMPDM_SIM_SO"));
}

public sealed class SimFactAttribute : FactAttribute
{
    public SimFactAttribute() { if (Sim.Missing) Skip = Sim.SkipReason; }
}

public sealed class SimTheoryAttribute : TheoryAttribute
{
    public SimTheoryAttribute() { if (Sim.Missing) Skip = Sim.SkipReason; }
}
