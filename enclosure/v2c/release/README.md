# enclosure v2c release records (F1)

The releases themselves (STEPs, drawings, checks) are in the OneDrive models folder `custom-pdm-enclosure-rev<current>\rev<letter>\` (now `custom-pdm-enclosure-revF`, holding revF and the previous revE) (see `docs/enclosure-v2c.md`). Kept here, and locked in `VERIFIED.lock`:

| Rev | Date | Manifest copy (sha256 of every released file) | BOM generated from the assembly placements (`build_v2c.py`) |
|---|---|---|---|
| B | 2026-11-20 | `MANIFEST-revB.sha256` | `BOM-v2c-F1.csv` |
| C | 2026-11-20 | `MANIFEST-revC.sha256` | `BOM-v2c-F1-revC.csv` (maker CAD for the Sunon fan, Phoenix 3240083 lug, LTW UC-00PMFY-SC7001 bulkhead; 125 components) |
| D | 2026-11-21 | `MANIFEST-revD.sha256` | `BOM-v2c-F1-revD.csv` (separate feet, gap pads, heat-sink subassembly CPDM-ENC-120-F1, CnLinko USB-C, set-screw studs, screw-on tie mounts, fan-lead cord grip 8183K5; 51 part numbers, 155 components) |
| E | 2026-11-21 | `MANIFEST-revE.sha256` | `BOM-v2c-F1-revE.csv` (real round wires: harness subassembly CPDM-HAR-200) |
| F | 2026-11-22 | `MANIFEST-revF.sha256` | `BOM-v2c-F1-revF.csv` (hub under X2 on M2.5 screws, wire-end parts, loom re-laid; 56 part numbers, 175 components) |

All are generated outputs: change `enclosure/v2c/src/build_v2c.py`, rebuild, re-release as a new rev letter with new file names; never edit or overwrite these.
