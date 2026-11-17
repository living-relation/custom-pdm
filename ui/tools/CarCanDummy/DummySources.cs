namespace CarCanDummy;

// The read-only st185-link-ecu-config files these dummy copies model, at the commit that was read
// (`git -C <st185> log -1 --format=%h -- <file>`, 2026-11-16). Copies are DUMMY TEST COPIES (Dan, 2026-11-16, AGENTS.md
// "Other repos"): never a source of truth, never the only reason for a design change.
public static class DummySources
{
    public const string Repo = "st185-link-ecu-config";
    public const string IdTable = "CAN-BUS-ID-ALLOCATION-TABLE.md @ 3df293f2";
    public const string MasterDesign = "CAN-BUS-MASTER-DESIGN.md @ a6f5f328";
    public const string LinkJson = "link_g4x_can_setup.json @ 60fd99c4";
    public const string LinkLcs = "link_g4x_can_setup.lcs @ 60fd99c4";
    public const string Switchboard = "switchboard_frames.json @ 3df293f2";
    public const string Parity = "bench/check_parity.py @ c2ddf1ab";

    public const string Folder = "docs/car-can-dummy";

    // First line of every dummy file
    public static string Banner(string realSource) =>
        $"DUMMY TEST COPY - not a source of truth; real source: {realSource}; never use alone to decide a design change (Dan, 2026-11-16)";
}
