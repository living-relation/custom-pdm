# Enclosure v2b vendor models (not in git)

The maker models are downloaded to `.claude/tmp/vendor/` in the checkout (git-ignored) because their licences do not clearly allow redistribution. `build_v2b.py` reads them from `$VENDOR`. Re-download from the sources below.

| Part | File in `$VENDOR` | Source | Licence / terms |
|---|---|---|---|
| X1 receptacle TE HD34-24-21SN | `HD34-24-21SN/c-hd34-24-21sn-p1-3d.stp` | [te.com product page](https://www.te.com/en/product-HD34-24-21SN.html), Customer View Model | TE CVM terms (accepted by Dan, v4a) |
| X1 mating plug TE HD36-24-21PN | `HD36-24-21PN/c-hd36-24-21pn-d1-3d.stp` | [te.com product page](https://www.te.com/en/product-HD36-24-21PN.html) | TE CVM terms |
| X2 receptacle TE HDP24-24-47SE-L017 | `HDP24-24-47SE-L017/c-hdp24-24-47se-l017-b-3d.stp` | [te.com product page](https://www.te.com/en/product-HDP24-24-47SE-L017.html) | TE CVM terms |
| X2 mating plug TE HDP26-24-47PE-L015 | `HDP26-24-47PE-L015/c-hdp26-24-47pe-l015-c-3d.stp` | [te.com product page](https://www.te.com/en/product-HDP26-24-47PE-L015.html) | TE CVM terms |
| Panel cut-out + nut | `spec_0425-021-0000.pdf`, `cd_HD34-24-XXPSX.pdf`, `cd_HDP24-24-XXPSX-L017.pdf` | te.com (same pages, Documents) | TE |
| Fan (F2) Noctua NF-A6x15 PWM | `noctua_NF-A6x15/NF-A6x15_Public-CAD.stp`, spec PDF | [noctua.at downloads](https://www.noctua.at/en/support/downloads) | Noctua public CAD: rendering and integration only, not for flow simulation |
| USB hub Adafruit 5997 (CH334F 4-port) | `adafruit_5997_5997-CH334F-4-Port-Hub.step` | [adafruit/Adafruit_CAD_Parts](https://github.com/adafruit/Adafruit_CAD_Parts) | MIT (repo licence) |

## Modelled from drawings (no maker STEP found)

| Part | Basis | Note |
|---|---|---|
| Fan (F1) Sunon MF30101V1-1000U-A99, 30x30x10 | Sunon spec D03033580G-01 dimensions | No STEP on Sunon or distributor sites (checked 2026-11-12) |
| USB-C bulkhead Amphenol LTW UC-00PMFY-SC7001 | UC series catalog: cut-out 20.8 with 19.4 flat, flange 25.4, panel up to 4.0 | Digi-Key blocked by Cloudflare, LTW site redirect; depths ASSUMED |
| TE panel nut 2411-001-2405 | AF 47.6 from the 1-7/8 in socket in spec 0425-021-0000 | Thickness 6 ASSUMED |
