"""Regenerate docs/parts-audit.csv from the board schematics.

usage: python tools/gen_parts_audit_csv.py [--kicad-cli PATH] [--offline]

- Exports each board's BOM with kicad-cli (fields Reference, Value, Footprint, DNP, Digi-Key_PN, LCSC, Description).
- Groups parts with the same Value, Footprint (with library), DNP, Digi-Key_PN, LCSC and Description.
- LCSC mpn / brand / stock / price breaks are carried over from the existing CSV for every LCSC number it already has.
- LCSC numbers not in the existing CSV are looked up live on lcsc.com (product page data); on any failure, or with
  --offline, they are written as TBD. The stock column header (with its date) is kept from the existing CSV.
Run from the repo root (or anywhere: paths are relative to this file).
"""
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "parts-audit.csv")
KICAD_CLI = r"C:\Users\danie\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"
BOARDS = [  # (board, root schematic, boards per PDM)
    ("board-a", "hardware/board-a/DingoPDM.kicad_sch", 2),
    ("board-b", "hardware/board-b-max/dingoPDM-Max.kicad_sch", 1),
    ("input", "hardware/input-board/input-board.kicad_sch", 3),
]
FIELDS = ["Reference", "Value", "Footprint", "DNP", "Digi-Key_PN", "LCSC", "Description"]
DEFAULT_HEADER = ["board", "refs", "qty_per_board", "boards_per_pdm", "qty_per_pdm", "value", "footprint", "dnp",
                  "digikey_pn_field", "lcsc_field", "lcsc_mpn", "lcsc_brand", "lcsc_stock", "lcsc_usd_price_breaks"]


def nat(ref):
    m = re.match(r"([A-Za-z#]*)(\d*)", ref)
    return (m.group(1), int(m.group(2) or 0), ref)


def export_bom(cli, sch):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "bom.csv")
        f = ",".join(FIELDS)
        subprocess.run([cli, "sch", "export", "bom", "--fields", f, "--labels", f, "--ref-range-delimiter", "",
                        "-o", out, os.path.join(ROOT, sch)], check=True, capture_output=True)
        with open(out, encoding="utf-8", errors="replace", newline="") as fh:
            rows = list(csv.DictReader(fh))
    parts = []
    for r in rows:
        for ref in [x.strip() for x in r["Reference"].split(",") if x.strip()]:
            parts.append(dict(r, Reference=ref))
    return parts


def group(parts):
    groups = {}
    for p in parts:
        key = tuple(p[k].strip() for k in FIELDS[1:])
        groups.setdefault(key, []).append(p["Reference"])
    out = []
    for key, refs in groups.items():
        refs.sort(key=nat)
        out.append((refs, dict(zip(FIELDS[1:], key))))
    out.sort(key=lambda g: nat(g[0][0]))
    return out


def lcsc_lookup(code):
    """Return (mpn, brand, stock, price_breaks) from the LCSC product page, or None."""
    url = f"https://www.lcsc.com/product-detail/{code}.html"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        t = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    except Exception as e:  # network or HTTP error
        print(f"LCSC {code}: lookup failed ({e})", file=sys.stderr)
        return None
    i = t.find('"webData":{')
    j = t.find(f'"productCode":"{code}"', i if i >= 0 else 0)
    if j < 0:
        print(f"LCSC {code}: product data not found on page", file=sys.stderr)
        return None
    s = t[j:j + 20000]
    def val(name):
        m = re.search(r'"' + name + r'":("((?:[^"\\]|\\.)*)"|-?\d+)', s)
        if not m: return None
        return json.loads(m.group(1)) if m.group(1).startswith('"') else int(m.group(1))
    mpn, brand, stock = val("productModel"), val("brandNameEn"), val("stockNumber")
    pl = re.search(r'"productPriceList":\[(.*?)\]', s)
    breaks = re.findall(r'"ladder":(\d+),"productPrice":"([\d.]+)"', pl.group(1)) if pl else []
    if mpn is None or brand is None or stock is None or not breaks:
        print(f"LCSC {code}: incomplete product data", file=sys.stderr)
        return None
    return mpn, brand, str(stock), " ".join(f"{q}:{p}" for q, p in breaks)


def main(argv):
    cli = argv[argv.index("--kicad-cli") + 1] if "--kicad-cli" in argv else KICAD_CLI
    offline = "--offline" in argv
    header, known = DEFAULT_HEADER, {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            header = next(rd)
            for r in rd:
                if len(r) == len(header) and r[9]:
                    known.setdefault(r[9], r[10:14])
    rows = []
    for board, sch, per_pdm in BOARDS:
        for refs, f in group(export_bom(cli, sch)):
            code = f["LCSC"]
            if not code:
                extra = ["", "", "", ""]
            elif code in known:
                extra = known[code]
            else:
                got = None if offline else lcsc_lookup(code)
                extra = list(got) if got else ["TBD", "TBD", "TBD", "TBD"]
                known[code] = extra
                print(f"LCSC {code}: {'looked up' if got else 'TBD'} {extra}")
            fp = f["Footprint"].split(":", 1)[-1]
            n = len(refs)
            rows.append([board, " ".join(refs), n, per_pdm, n * per_pdm, f["Value"], fp,
                         "DNP" if f["DNP"] else "", f["Digi-Key_PN"], code] + extra)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
