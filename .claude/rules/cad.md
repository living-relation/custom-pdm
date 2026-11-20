# CAD (enclosure, models, drawings)

Enforcer: the enclosure build checks (overlaps, clearances incl. same-net screw heads, lugcheck, BOM / part-file check, CNC check); Fusion lock script; none yet for the rest.

- All CAD (models and engineering drawings) follows the Handbuilt-CAD repo rules, whether built with Fusion or handbuilt-CAD tools (claude.ai project instructions, 2026-11-17).
- Models and drawings are saved in the OneDrive models folder (`C:\Users\danie\.personal OneDrive\OneDrive\Desktop\models\`), as versioned, hash-verified release folders (publish-to-models). Never edit assembly drawings directly: models first, drawings generated from the models, parts lists and BOM generated from those.
- Every part is its own external model file inserted into the assembly (Fusion linked components, one design per part; one STEP per part); no part exists only inside an assembly. Every part carries its correct part number and description (bought: maker part number; made: project part number + revision + material) so the BOM populates; the build check fails on a missing one (Dan, 2026-11-16).
- Purchased parts use the maker's real CAD (connectors, bulkheads, fans, terminals), not placeholder shapes. Downloading maker drawings / CAD is always OK; TE ECAD terms are accepted.
- Clearance: insulated wire may touch plastic; only bare metal (lugs, screws, risers) needs real clearance, same-net bare metal included (machining). CNC curves are smooth continuous sweeps, not facets.
- Claude owns the enclosure design (Dan, 2026-11-16); board STEPs are exported from our own KiCad files.
- Fusion on DansPC: hold the Fusion lock per `C:\projects\active\workstation\agents\projects-AGENTS.md` section 5 (`fusion-lock.ps1`: check status first, check in every 10 min, release when done); only one agent drives Fusion at a time.
