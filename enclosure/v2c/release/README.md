# enclosure v2c release record (rev B, F1)

The release itself (STEPs, drawings, checks) is in the OneDrive models folder: `custom-pdm-enclosure-v2c\revB\` (see `docs/enclosure-v2c.md`). Kept here, and locked in `VERIFIED.lock`:
- `MANIFEST-revB.sha256`: copy of the release manifest (sha256 of every released file)
- `BOM-v2c-F1.csv`: the BOM generated from the assembly placements (`build_v2c.py`), as released

Both are generated outputs: change `enclosure/v2c/src/build_v2c.py`, rebuild, re-release as a new rev letter; never edit these by hand.
