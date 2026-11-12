"""Copy the committed outputs of a low-profile run into the repo.
Usage: $CAD_PY export_lowpro.py <repo_root>   (env RUN_DIR, RENDER_DIR as for build / render)
- RUN_DIR/parts/*.step and the assembly STEP without the board models -> enclosure/lowpro/step/
  (the full assembly with the KiCad board models stays in RUN_DIR: about 110 MB, rebuildable)
- RENDER_DIR/enclosure-lowpro-*.png -> docs/diagrams/
- RUN_DIR/meta.json and check.json -> enclosure/lowpro/step/ (sizes, masses, positions, interference result)"""
import os, sys, glob, shutil
RUN = os.environ.get("RUN_DIR", os.path.expanduser("~/scratch/encl-lowpro/runs/v1"))
RD = os.environ.get("RENDER_DIR", os.path.join(RUN, "renders"))
repo = sys.argv[1]
dst = os.path.join(repo, "enclosure", "lowpro", "step"); os.makedirs(dst, exist_ok=True)
for f in glob.glob(os.path.join(RUN, "parts", "*.step")) + [os.path.join(RUN, "custom-pdm-enclosure-lowpro-v1-noboards.step")]:
    shutil.copy2(f, dst); print("step", os.path.basename(f))
for f in ("meta.json", "check.json"):
    shutil.copy2(os.path.join(RUN, f), os.path.join(dst, f))
for f in glob.glob(os.path.join(RD, "enclosure-lowpro-*.png")):
    shutil.copy2(f, os.path.join(repo, "docs", "diagrams")); print("png", os.path.basename(f))
