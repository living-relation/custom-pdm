using domain.Devices;
using domain.Interfaces;

namespace domain.CustomPdm;

// custom-pdm (not upstream): config operations that are unsafe on device types 14 / 15. Stock types: always allowed.
// Why: dingoConfig's defaults for a new device are stock ones, not our firmware's factory defaults (1000K, reset mode
// Count, fan / load-shed config, A2 base ID 0x540 and exempt mask), so
// - Read Modified fills every param the board does not send with the PC default (on A2 this moves the PC device to
//   base ID 0x500 = board A1, so the next write goes to the wrong board), and Write Modified skips values equal to the
//   PC default: both are off for types 14 / 15;
// - Write All before any Read All would write those PC defaults (e.g. 500K): it is refused until a full Read All of
//   that device succeeded in this session (FwDevice.FullReadDone), or the PC values are a complete set from a New PDM
//   or from a project file saved with one (PdmProjectFile, uipolish 2026-11-21; a hand-added board that was never
//   read stays blocked, also after a save and a load).
public static class CustomPdmGuards
{
    public const string ModifiedOffReason =
        "custom-pdm boards: Read / Write Modified are off (PC defaults are not our factory defaults). Use Read All / Write All.";

    public const string WriteAllNeedsReadReason =
        "custom-pdm boards: do a Read All of this device first (a Write All before it would write stock PC defaults, e.g. 500K).";

    private static bool IsCustom(IDeviceConfigurable device) => device is FwDevice { CustomPdm: not null };

    public static bool ModifiedOpsAllowed(IDeviceConfigurable device) => !IsCustom(device);

    public static string? WriteAllBlockedReason(IDeviceConfigurable device) =>
        IsCustom(device) && !ReadOrFactoryNew((FwDevice)device) ? WriteAllNeedsReadReason : null;

    // B3 (u2a): a board of a "New PDM" project holds our factory defaults on the PC (PdmFactoryDefaults, proven equal
    // to the firmware's against the sim), so its Write All is as safe as one after a Read All.
    // uipolish: so does a board loaded from a project file that was saved with a complete set (PdmProjectFile).
    public static bool ReadOrFactoryNew(FwDevice device) => PdmProjectFile.Complete(device);

    // Why a config operation must not run (null = allowed). allParams false = the Modified variants.
    public static string? ReadBlockedReason(IDeviceConfigurable device, bool allParams) =>
        !allParams && !ModifiedOpsAllowed(device) ? ModifiedOffReason : null;

    public static string? WriteBlockedReason(IDeviceConfigurable device, bool allParams) =>
        !allParams && !ModifiedOpsAllowed(device) ? ModifiedOffReason : allParams ? WriteAllBlockedReason(device) : null;
}
