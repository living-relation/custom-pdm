"""Regenerate docs/parts-audit.csv from the board schematics, with LCSC, Mouser and Digi-Key data.

usage: python tools/gen_parts_audit_csv.py [--kicad-cli PATH] [--offline] [--refresh-lcsc] [--dist TSV [--over TSV]]
                                           [--date YYYY-MM-DD]

- Exports each board's BOM with kicad-cli (fields Reference, Value, Footprint, DNP, Manufacturer, MPN, Digi-Key_PN,
  LCSC, Description) and groups parts with the same fields.
- LCSC (mpn / brand / stock / USD price breaks): carried over from the existing CSV per LCSC number. Numbers not in
  it, or every number with --refresh-lcsc, are read live from the LCSC product page (lcsc_read = --date or today);
  on failure, or with --offline, a new number is written as TBD.
- Mouser and Digi-Key (part number, stock, USD price breaks, note): carried over from the existing CSV per MPN, or
  taken from --dist, a TSV made from the authorized-distributor listing on trustedparts.com (ECIA), read in a browser
  because mouser.com and digikey.com refuse scripted reads. --dist columns: mpn, mouser_pn, mouser_mfr, mouser_stock,
  mouser_breaks, dk_pn, dk_mpn_if_other, dk_stock, dk_breaks (one row per schematic MPN; empty = not listed).
  --over corrections (mpn, field, values...): field mouser_note | dk_note (text), mouser (pn, mpn, stock, breaks,
  note: a Mouser part for an approved alternate or the same part under the maker's full number), dk (pn, mpn, stock,
  breaks: the Digi-Key part that was priced when the exact MPN is not listed there). A Mouser row whose maker is not
  the schematic maker is never used (the --over file names the replacement).
- Digi-Key: digikey_pn_field is the schematic's Digi-Key_PN field; digikey_priced_pn is the Digi-Key part the price
  belongs to (the exact MPN when Digi-Key lists it, else the field's part); digikey_priced_mpn is filled only when it
  differs from the schematic MPN.
Run from the repo root (or anywhere: paths are relative to this file). Data notes: docs/parts-audit.md section 18.
"""
import csv
import datetime
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "parts-audit.csv")
KICAD_CLI = r"C:\Users\danie\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"
BOARDS = [  # (board, root schematic, boards per PDM)
    ("board-a", "hardware/board-a/DingoPDM.kicad_sch", 2),
    ("board-b", "hardware/board-b-max/dingoPDM-Max.kicad_sch", 1),
    ("input", "hardware/input-board/input-board.kicad_sch", 3),
]
FIELDS = ["Reference", "Value", "Footprint", "DNP", "Manufacturer", "MPN", "Digi-Key_PN", "LCSC", "Description"]
LCSC_COLS = ["lcsc_mpn", "lcsc_brand", "lcsc_stock", "lcsc_usd_price_breaks", "lcsc_read"]
DIST_COLS = ["mouser_pn", "mouser_mpn", "mouser_stock", "mouser_usd_price_breaks", "mouser_note",
             "digikey_priced_pn", "digikey_priced_mpn", "digikey_stock", "digikey_usd_price_breaks", "digikey_note",
             "dist_read"]
HEADER = (["board", "refs", "qty_per_board", "boards_per_pdm", "qty_per_pdm", "value", "footprint", "dnp",
           "manufacturer", "mpn", "digikey_pn_field", "lcsc_field"] + LCSC_COLS + DIST_COLS +
          ["lcsc_url", "mouser_url", "digikey_url", "dist_read_url"])
MAKER_SAME = {  # distributor maker name -> schematic maker it is the same company as
    "royal ohm": "uni-royal", "ams osram": "osram", "murata manufacturing": "murata",
    "murata power solutions": "murata", "infineon technologies": "infineon", "global connector technology": "gct",
    "microchip technology": "microchip", "ecs international": "ecs inc.", "wÃ¼rth elektronik": "wurth elektronik",
    "nidec components": "nidec components", "texas instruments": "texas instruments",
}


def nat(ref):
    m = re.match(r"([A-Za-z#]*)(\d*)", ref)
    return (m.group(1), int(m.group(2) or 0), ref)


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


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


def read_dist(path, over, date):
    """{norm(mpn): dict of DIST_COLS} from the --dist TSV and the --over corrections."""
    out = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            d = dict.fromkeys(DIST_COLS, "")
            if r["mouser_pn"] and not r["mouser_pn"].startswith("REJECT"):
                d.update(mouser_pn=r["mouser_pn"], mouser_stock=r["mouser_stock"],
                         mouser_usd_price_breaks=r["mouser_breaks"], mouser_maker=r["mouser_mfr"])
            if r["dk_pn"]:
                d.update(digikey_priced_pn=r["dk_pn"], digikey_priced_mpn=r["dk_mpn_if_other"],
                         digikey_stock=r["dk_stock"], digikey_usd_price_breaks=r["dk_breaks"])
            d["dist_read"] = date
            out[norm(r["mpn"])] = d
    if over:
        with open(over, encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh, delimiter="\t")
            next(rd)
            for r in rd:
                d = out.setdefault(norm(r[0]), dict.fromkeys(DIST_COLS, "") | {"dist_read": date})
                if r[1] == "mouser_note":
                    d["mouser_note"] = r[2]
                elif r[1] == "dk_note":
                    d["digikey_note"] = r[2]
                elif r[1] == "mouser":
                    d.update(mouser_pn=r[2], mouser_mpn=r[3], mouser_stock=r[4], mouser_usd_price_breaks=r[5],
                             mouser_note=r[6], mouser_maker="")
                elif r[1] == "dk":
                    d.update(digikey_priced_pn=r[2], digikey_priced_mpn=r[3], digikey_stock=r[4],
                             digikey_usd_price_breaks=r[5])
    return out


def maker_ok(dist_maker, sch_maker):
    a, b = (dist_maker or "").lower(), (sch_maker or "").lower()
    if not a or not b:
        return True
    a = MAKER_SAME.get(a, a)
    return a.split()[0] in b or b.split()[0] in a


def urls(row):
    q = urllib.parse.quote
    return [f"https://www.lcsc.com/product-detail/{row['lcsc_field']}.html" if re.match(r"C\d+$", row["lcsc_field"]) else "",
            f"https://www.mouser.com/ProductDetail/{q(row['mouser_pn'], safe='')}" if row["mouser_pn"] else "",
            f"https://www.digikey.com/en/products/result?keywords={q(row['digikey_priced_pn'] or row['digikey_pn_field'], safe='')}"
            if (row["digikey_priced_pn"] or row["digikey_pn_field"]) else "",
            f"https://www.trustedparts.com/en/search/{q(row['mpn'], safe='')}" if row["dist_read"] else ""]


def buy(breaks, qty):
    """(quantity bought, cost) for qty parts: at least the first break, at the price of the largest break reached."""
    b = sorted((int(q), float(p)) for q, p in (x.split(":") for x in (breaks or "").split() if ":" in x and x[0] != ":"))
    if not b:
        return None
    n = max(qty, b[0][0])
    return n, n * [p for q, p in b if q <= n][-1]


def set_cost(path=OUT):
    """Print the cost of exactly one PDM set of fitted parts per source (rule: buy())."""
    tot = {"lcsc": 0.0, "mouser": 0.0, "digikey": 0.0, "best_us": 0.0}
    miss = {"lcsc": [], "mouser": [], "digikey": []}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["dnp"] or not r["mpn"] or r["mpn"] == "7461084":   # DNP, non-parts, press-fit terminals (Dan's)
            continue
        q = int(r["qty_per_pdm"])
        got = {"lcsc": buy(r["lcsc_usd_price_breaks"], q), "mouser": buy(r["mouser_usd_price_breaks"], q),
               "digikey": buy(r["digikey_usd_price_breaks"], q)}
        for k, v in got.items():
            if v:
                tot[k] += v[1]
            else:
                miss[k].append(r["mpn"])
        us = [v[1] for k, v in got.items() if k != "lcsc" and v]
        tot["best_us"] += min(us) if us else (got["lcsc"][1] if got["lcsc"] else 0.0)
    for k, v in tot.items():
        print(f"{k}: ${v:.2f}" + (f" (no price for {len(miss[k])} lines: {', '.join(sorted(set(miss[k])))})"
                                   if miss.get(k) else ""))
    return tot


def main(argv):
    arg = lambda k: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else None
    if "--set-cost" in argv:
        set_cost(arg("--set-cost") or OUT)
        return 0
    cli = arg("--kicad-cli") or KICAD_CLI
    offline, refresh = "--offline" in argv, "--refresh-lcsc" in argv
    date = arg("--date") or datetime.date.today().isoformat()
    lcsc_known, dist_known = {}, {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                stock = next((v for k, v in r.items() if k.startswith("lcsc_stock")), "")
                old_date = next((k[len("lcsc_stock_"):] for k in r if k.startswith("lcsc_stock_")), "")
                if r.get("lcsc_field"):
                    lcsc_known.setdefault(r["lcsc_field"], [r.get("lcsc_mpn", ""), r.get("lcsc_brand", ""), stock,
                                                            r.get("lcsc_usd_price_breaks", ""),
                                                            r.get("lcsc_read") or old_date])
                if r.get("mpn") and r.get("dist_read"):
                    dist_known.setdefault(norm(r["mpn"]), {k: r.get(k, "") for k in DIST_COLS})
    if arg("--dist"):
        dist_known.update(read_dist(arg("--dist"), arg("--over"), date))
    rows, looked = [], {}
    for board, sch, per_pdm in BOARDS:
        for refs, f in group(export_bom(cli, sch)):
            code = f["LCSC"] if re.match(r"C\d+$", f["LCSC"]) else ""
            if not code:
                lc = ["", "", "", "", ""]
            elif code in looked:
                lc = looked[code]
            elif code in lcsc_known and not refresh:
                lc = lcsc_known[code]
            else:
                got = None if offline else lcsc_lookup(code)
                kept = lcsc_known.get(code) if (lcsc_known.get(code) or [""])[0] else None
                lc = list(got) + [date] if got else (kept or ["TBD", "TBD", "TBD", "TBD", ""])
                print(f"LCSC {code}: {'read ' + date if got else 'kept / TBD'} {lc[:4]}")
            looked[code] = lc
            mpn = f["MPN"] if not f["MPN"].startswith("(") else ""
            n = len(refs)
            row = dict(zip(HEADER, [board, " ".join(refs), n, per_pdm, n * per_pdm, f["Value"],
                                    f["Footprint"].split(":", 1)[-1], "DNP" if f["DNP"] else "", f["Manufacturer"],
                                    mpn, f["Digi-Key_PN"], f["LCSC"] if code else ""] + lc))
            d = dict(dist_known.get(norm(mpn), {})) if mpn else {}
            maker = d.pop("mouser_maker", "")
            if d.get("mouser_pn") and not maker_ok(maker, f["Manufacturer"]):
                print(f"{mpn}: Mouser {d['mouser_pn']} is made by {maker}, not {f['Manufacturer']}: not used")
                d.update(mouser_pn="", mouser_stock="", mouser_usd_price_breaks="",
                         mouser_note=d.get("mouser_note") or f"Mouser lists this number only for {maker}")
            if d.get("mouser_pn") and not d.get("mouser_note"):
                d["mouser_note"] = "exact MPN"
            if mpn and d.get("dist_read") and not d.get("mouser_pn") and not d.get("mouser_note"):
                d["mouser_note"] = "not listed at Mouser"
            for k in DIST_COLS:
                row[k] = d.get(k, "")
            if norm(row["digikey_priced_mpn"]) == norm(mpn):
                row["digikey_priced_mpn"] = ""
            row.update(zip(["lcsc_url", "mouser_url", "digikey_url", "dist_read_url"], urls(row)))
            rows.append(row)
    buf = io.StringIO()
    w = csv.DictWriter(buf, HEADER, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
