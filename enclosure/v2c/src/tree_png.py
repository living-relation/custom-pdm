"""Render the Fusion browser tree (text lines from fusion_v2c.tree_lines, one per occurrence) as a review PNG for the release.
Usage: python tree_png.py <tree.txt> <out.png> [title]. Linked parts black, SR Fasteners bodies blue, LOCAL (a fail) red."""
import sys
from PIL import Image, ImageDraw, ImageFont
src, out = sys.argv[1], sys.argv[2]; title = sys.argv[3] if len(sys.argv) > 3 else "Fusion browser tree"
lines = [l.rstrip("\n") for l in open(src, encoding="utf-8") if l.strip()]
try: font = ImageFont.truetype("consola.ttf", 15); tfont = ImageFont.truetype("consolab.ttf", 18)
except OSError: font = tfont = ImageFont.load_default()
LH = 19; cols = 2 if len(lines) > 70 else 1; per = (len(lines) + cols - 1) // cols
W = 1100 * cols; H = 60 + LH * per + 20
img = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(img)
d.text((20, 15), title, fill="black", font=tfont)
for i, l in enumerate(lines):
    c, r = divmod(i, per)
    col = (200, 0, 0) if "[LOCAL]" in l else (20, 70, 180) if "[SR body]" in l else (0, 0, 0)
    d.text((20 + c * 1100, 55 + r * LH), l, fill=col, font=font)
img.save(out); print(out, len(lines), "lines")
