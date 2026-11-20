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
| Fan (F1) Sunon MF30101V1-1000U-A99 | `Sunon_MF30101V1-1000U-A99/Sunon_MF30101V1-1000U-A99_259_Doc-0175505-7-0.stp` | [DigiKey models/10441405](https://www.digikey.com/en/models/10441405), "Manufacturer Provided" (Sunon Creo export `MF3010_K201004120G`); file URL `mm.digikey.com/.../259_Doc-0175505-7-0.stp` (new in revC) | DigiKey CAD Model Agreement (click-through, accepted 2026-11-20 for this download; internal business use, no ownership) |
| OUT1-4 ring lug Phoenix Contact 3240083 (C-RC 6/M4 DIN) | `Phoenix_3240083/pxc_3240083_00_00_C-RC-6-M4-DIN_3D.stp` | [phoenixcontact.com product page](https://www.phoenixcontact.com/en-us/products/ring-cable-lug-c-rc-6-m4-din-3240083), Downloads > CAD data, "Simplified 3D model of the item", 2023-11-23, sha256 `7a7b9f8fd0148cfee7f475a3f239ca69eb484a4fba56e3482102c1f6f8a6a762` (new in revC) | Phoenix site terms (direct link, no licence prompt) |
| USB-C bulkhead Amphenol LTW UC-00PMFY-SC7001 | `AmphenolLTW_UC-00PMFY-SC7001/UC-00PMFY-SC7001-STP.stp` (+ `UC-00PMFY-SC7001-2D.pdf`, drawing rev C) | [amphenolltw.com product page](https://amphenolltw.com/product-info/USB/USB-Receptacle/UC-00PMFY-SC7001.html), Download / CAD: (3D STP) zip in `_zips\`, (2D) PDF (new in revC) | Amphenol LTW site terms (direct link, no licence prompt) |
| USB-C bulkhead CnLinko LP-16-C05SX-02-101 (revD; replaces the LTW part, Dan 2026-11-20) | `CnLinko_LP-16-C05SX-02-101/LP-16-C05SX-02-101.step` | Dan's own model, copied unchanged from `models\st185_vendor-parts_1101\cnlinko\LP-16-C05SX-02-101\` (sha256 `012f1637beba9c5f...`); one solid (body, silicone tether ring, dust cap, jam nut) | Dan's file |
| Input-deck standoff M3 x 25 M-F, McMaster-Carr 93655A360 (was CPDM-BUY-301) | `McMaster_93655A360/93655A360_NO_THREADS.STEP` | [mcmaster.com/93655A360](https://www.mcmaster.com/93655A360/), CAD "3-D STEP no threads" (new in revD) | McMaster-Carr site terms (no licence prompt) |
| Carrier standoff M3 x 8 M-F, McMaster-Carr 93655A095 (was CPDM-BUY-302) | `McMaster_93655A095/93655A095_NO_THREADS.STEP` | [mcmaster.com/93655A095](https://www.mcmaster.com/93655A095/), "3-D STEP no threads" (new in revD) | McMaster-Carr site terms |
| Hub spacer M2.5, OD 4.5 x 4, McMaster-Carr 94669A096 (was CPDM-BUY-303) | `McMaster_94669A096/94669A096.STEP` | [mcmaster.com/94669A096](https://www.mcmaster.com/94669A096/), "3-D STEP" (new in revD) | McMaster-Carr site terms |
| Cable-tie mount McMaster-Carr 7566K204 (was CPDM-BUY-304) | `McMaster_7566K204/7566K204.STEP` | [mcmaster.com/7566K204](https://www.mcmaster.com/7566K204/), "3-D STEP" (new in revD); spare candidate `McMaster_7566K23/7566K23.STEP` (V-0, to 82 C, 27 x 17.5) | McMaster-Carr site terms |
| Fan (F2 only) Noctua NF-A6x15 PWM | `noctua_NF-A6x15/NF-A6x15_Public-CAD.stp` | [noctua.at downloads](https://www.noctua.at/en/products/nf-a6x15-pwm/downloads) | Noctua public CAD: rendering and integration only, no flow simulation. Not re-downloaded for v2c (F2 not rebuilt) |

McMaster download tip (2026-11-20, revD): pick the CAD type on the product page, then the `Download` link's `/mvC/Library/CAD2/...STEP` path is fetched from the page (same-origin, the built-in browser on DansPC saves it to Downloads as a `.tmp`; rename by its STEP `FILE_NAME`); curl gets 403 without the site cookie. Wurth (we-online.com STEP), Keystone (keyelco.com: e-mail form), Harwin (TraceParts account), Printables (bot check) and DigiKey (bot check from the built-in browser) were not used.
Still without maker CAD (revD): ruthex RX-M4x8.1 heat-set insert: ruthex publishes no CAD found on its shop pages; the only model seen is a community upload on GrabCAD (account): https://cad.grabcad.com/library/ruthex-threaded-inserts-1. Same size from another maker (CNC Kitchen M4 x 8.1, same 5.6 hole) has its STEP behind a Printables bot check: https://www.printables.com/model/482734-threaded-inserts-heat-set-inserts-by-cnc-kitchen/files.

TE download tip (2026-11-16): `curl` gets HTTP 403 from te.com; in Chrome, open the product page once, then open each `DocumentDelivery/DDEController?...DocNm=CVM_<PN>&DocFormat=3d_stp.zip` link as a page (a script-started second download is blocked by Chrome's multiple-download guard).

## Drawn stand-ins: none left (revC, 2026-11-20)

revB drew the Sunon fan, the LTW USB-C bulkhead and the Phoenix ring lug from drawings; revC uses the maker STEPs above. Notes from the swap:
- Download route (2026-11-20): the DigiKey model page's STEP is a plain `mm.digikey.com` file (curl works); Phoenix's "3D view and CAD download" panel has a Friendly Captcha, but the product page's own Downloads > CAD data list links the STEP directly (no captcha); LTW's `down.php?prod_files=<id>` links work with curl. TraceParts / 3Dfindit need an account; SnapMagic / Mouser show a bot check.
- Sunon STEP is a solid envelope (no bore, no blades), 10.4 thick (spec 10): fit only, not for airflow.
- Phoenix STEP: ring centre to barrel end 14.0 (revB drew 17.5), barrel OD 5.6 (drew 6.0), barrel bottom flush with the tongue.
- LTW STEP: round housing flange dia 25 (catalogue said square 25.4), hex nut AF 25.4 modelled against the flange (the build moves it out by the wall), FPC tail 47 mm ending in a 44-pin Y-beam contact that presses onto PCB pads (drawing "Recommended PCB Layout"): the part has no USB-C socket on the inside.

## Data sheets used for the OUT1-4 risers (2026-11-13)

| Part | Value used | Source |
|---|---|---|
| Wurth REDCUBE THR 74650074R (board B T1-T4) | M4 internal thread, thread length 2.5 mm, height 3 mm | [Wurth WP-THRBU product page](https://www.we-online.com/de/components/products/WP-THRBU_THROUGH-HOLE) |
| Wurth REDCUBE THR 74650074R | max tightening torque 1.2 N*m, 50 A max at 20 C | [74650074R datasheet](https://www.we-online.com/catalog/datasheet/74650074R.pdf) (properties table) |
| ISO 4762 M4 socket head | dk max 7.0 (head clearance to the riser column: v2c seat 8.5 from the T centre) | EN ISO 4762:2004 Table 1 (`src/screw_dimensions.csv`) |
| DIN 974-1 counterbore for M4 SHCS | dia 8.0 (lid screws in the heat sink) | DIN 974-1 series 1 (fine), M4 |
