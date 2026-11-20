# Enclosure v2c inputs: vendor models and board STEPs (not in git)

`build_v2c.py` reads two git-ignored folders. `run.sh` points at them by default; both sit in the MAIN checkout's `.claude\cache\enclosure\`, outside every worktree, so `git worktree remove` (which deletes ignored files inside a worktree) cannot take them.

| Env | Default | What | How to (re)make |
|---|---|---|---|
| `BOARDS` | `<repo root>\.claude\cache\enclosure\boards\` | `board-A.step`, `board-B.step`, `input-board.step` + `export.log` | `powershell -ExecutionPolicy Bypass -File enclosure\v2c\src\export_boards.ps1` (KiCad 10.0.7 kicad-cli from this checkout's `hardware\`, which is only read) |
| `VENDOR` | `<repo root>\.claude\cache\enclosure\vendor\` | maker CAD below | download per the table; zips kept in `_zips\` |

Board export notes: the boards are exported from a scratch copy whose model paths point at KiCad 10's own STEP library (KiCad 10 ships no `.wrl` and kicad-cli does not expand the old `KICAD6/9_3DMODEL_DIR` names); board A's `Models\` comes from `reference\dingoPDM\DingoPDM\Models` (stock dingoPDM, MIT). Known gap: stock dingoPDM-Max points the 4 BTS70012 (PG-TSDSO-24-32) models at a path on Cory Grant's PC; no copy exists, so those 4 packages (about 1 mm tall, board top) have no body. The input-board J2 Micro-Fit has no KiCad library model either; the build places Molex's own STEP as a separate part.

## Maker CAD (`$VENDOR`)

Downloading maker CAD is a standing OK (Dan, 2026-11-09); TE's ECAD model terms are accepted (Dan, v4a, 2026-11-12). The licences do not clearly allow redistribution, so the files stay out of git.

| Part | File in `$VENDOR` | Source | Licence / terms |
|---|---|---|---|
| X1 receptacle TE HD34-24-21SN | `HD34-24-21SN/c-hd34-24-21sn-p1-3d.stp` | [te.com](https://www.te.com/en/product-HD34-24-21SN.html), Customer View Model STEP (`CVM_HD34-24-21SN`) | TE CVM terms |
| X1 mating plug TE HD36-24-21PN | `HD36-24-21PN/c-hd36-24-21pn-d1-3d.stp` | [te.com](https://www.te.com/en/product-HD36-24-21PN.html) | TE CVM terms |
| X2 receptacle TE HDP24-24-47SE-L017 | `HDP24-24-47SE-L017/c-hdp24-24-47se-l017-b-3d.stp` | [te.com](https://www.te.com/en/product-HDP24-24-47SE-L017.html) | TE CVM terms |
| X2 mating plug TE HDP26-24-47PE-L015 | `HDP26-24-47PE-L015/c-hdp26-24-47pe-l015-c-3d.stp` | [te.com](https://www.te.com/en/product-HDP26-24-47PE-L015.html) | TE CVM terms |
| Panel nut TE 2411-001-2405 | `2411-001-2405/c-2411-001-2405-h-3d.stp` | te.com `CVM_2411-001-2405` (new in v2c; v2b drew it) | TE CVM terms |
| Lock washer TE 2414-001-2486 | `2414-001-2486/c-2414-001-2486-99-3d.stp` | te.com `CVM_2414-001-2486` (new in v2c) | TE CVM terms |
| Input-board J2 Molex 43045-1200 | `Molex_43045-1200/430451200.stp` | [molex.com part 430451200](https://www.molex.com/en-us/products/part-detail/430451200), 3D model STEP AP242 | Molex site terms |
| USB hub Adafruit 5997 (CH334F 4-port) | `adafruit_5997_5997-CH334F-4-Port-Hub.step` | [adafruit/Adafruit_CAD_Parts](https://github.com/adafruit/Adafruit_CAD_Parts) `5997 CH334F 4-Port Hub/` | MIT |
| Fan (F2 only) Noctua NF-A6x15 PWM | `noctua_NF-A6x15/NF-A6x15_Public-CAD.stp` | [noctua.at downloads](https://www.noctua.at/en/products/nf-a6x15-pwm/downloads) | Noctua public CAD: rendering and integration only, no flow simulation. Not re-downloaded for v2c (F2 not rebuilt) |

TE download tip (2026-11-16): `curl` gets HTTP 403 from te.com; in Chrome, open the product page once, then open each `DocumentDelivery/DDEController?...DocNm=CVM_<PN>&DocFormat=3d_stp.zip` link as a page (a script-started second download is blocked by Chrome's multiple-download guard).

## Still drawn from maker drawings (no maker CAD reached)

| Part | Basis | Why no maker CAD |
|---|---|---|
| Fan (F1) Sunon MF30101V1-1000U-A99 | Sunon spec D03033580G-01 (30 x 30 x 10, holes 3.4 at 24, hub 12) | maker model exists on DigiKey ([models/10441405](https://www.digikey.com/en/models/10441405), "Manufacturer Provided") behind DigiKey's model-download agreement, not accepted (Dan to accept or download) |
| USB-C bulkhead Amphenol LTW UC-00PMFY-SC7001 | UC series catalog: cut-out 20.8 with 19.4 flat, flange 25.4, panel up to 4.0; depths ASSUMED | DigiKey lists only a SnapMagic symbol / footprint; the LTW site has no CAD download |
| OUT1-4 ring lug Phoenix Contact 3240083 (C-RC 6/M4 DIN) | catalogue dims 8.0 x 17.5 x 0.99, barrel OD 6 ASSUMED | phoenixcontact.com "3D view and CAD download" sits behind an anti-robot check (not passed by an agent: Dan to download) |

## Data sheets used for the OUT1-4 risers (2026-11-13)

| Part | Value used | Source |
|---|---|---|
| Wurth REDCUBE THR 74650074R (board B T1-T4) | M4 internal thread, thread length 2.5 mm, height 3 mm | [Wurth WP-THRBU product page](https://www.we-online.com/de/components/products/WP-THRBU_THROUGH-HOLE) |
| Wurth REDCUBE THR 74650074R | max tightening torque 1.2 N*m, 50 A max at 20 C | [74650074R datasheet](https://www.we-online.com/catalog/datasheet/74650074R.pdf) (properties table) |
| ISO 4762 M4 socket head | dk max 7.0 (head clearance to the riser column: v2c seat 8.5 from the T centre) | EN ISO 4762:2004 Table 1 (`src/screw_dimensions.csv`) |
| DIN 974-1 counterbore for M4 SHCS | dia 8.0 (lid screws in the heat sink) | DIN 974-1 series 1 (fine), M4 |
