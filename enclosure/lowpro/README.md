# Enclosure low-profile v1 (build123d)

Our own enclosure 3D model, built from the decisions in `DECISIONS.md` (2026-11-11 / 2026-11-12). Grok's TEST 2 pack was the visual direction only (read-only). Design note, sizes, parts and open questions: `docs/enclosure-3d.md`. Heat: `docs/heat-analysis.md` section 6.

## Files
| Path | What |
|---|---|
| `src/build_lowpro.py` | builds every part (base / heat sink, duct cover, fan, lid, bars, straps, studs, connector envelopes, USB hub) and places the boards; writes STEP, BREP and `meta.json` to `RUN_DIR` |
| `src/check_lowpro.py` | interference check of every part pair, solid by solid; writes `check.json` (expect `unexpected: 0`) |
| `src/render_lowpro.py` | smooth renders and capped sections (handbuilt-cad `tools/render/section.py`) |
| `src/export_lowpro.py` | copies the committed outputs into `step/` and `docs/diagrams/` |
| `src/run.sh` | WSL runner (handbuilt-cad venv; strips CR from the CRLF checkout) |
| `src/measure_boards.py`, `src/fp_find.py` | helpers from the first low-profile attempt (tallest parts per board STEP, connector footprint list); kept for reuse (h1a) |
| `step/` | part STEPs and the assembly without board models (`custom-pdm-enclosure-lowpro-v1-noboards.step`), `meta.json`, `check.json` |

## Re-run (WSL on DansPC, from the repo root)
```bash
export LP_SRC=$PWD/enclosure/lowpro/src RENDER_DIR=~/scratch/encl-lowpro/renders
tr -d '\r' < enclosure/lowpro/src/run.sh > /tmp/run_lp.sh
bash /tmp/run_lp.sh build_lowpro.py      # about 1 min; prints the overall size and the masses
bash /tmp/run_lp.sh check_lowpro.py      # interference check
bash /tmp/run_lp.sh render_lowpro.py     # about 10 min
bash /tmp/run_lp.sh export_lowpro.py $PWD
```
Board models: `REF_BOARDS` (default `~/scratch/encl-lowpro/work/reference/boards`) holds `board-A.step`, `board-B.step`, `input-board.step`, KiCad STEP exports of the board-fix-era boards; the build drops the DT15 (J3) and Micro-Fit (J6) bodies, which PR #41 replaced with wire pads. A fresh `kicad-cli pcb export step --subst-models` export on DansPC (2026-11-12) came out without most 3D models (library paths), so the older exports are used. The full assembly with board models (about 110 MB) stays in `RUN_DIR`.

Frame: X along the length (left end, BATT / GND, to right end, OUT1-4), Y across (front wall at -Y), Z up, Z = 0 = base plate top. Boards are turned 180 degrees so their front edge (PCB -Y) faces the front wall.
