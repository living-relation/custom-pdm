"""List the nets on one part's pins from a KiCad netlist (.net, s-expression).

usage: python tools/netlist_pins.py <file.net> <REF>
"""
import re
import sys


def parse(path):
    text = open(path, encoding="utf-8").read()
    nets = {}
    for block in re.split(r"\(net \(code ", text)[1:]:
        m = re.search(r'\(name "([^"]*)"\)', block)
        if not m:
            continue
        name = m.group(1)
        for ref, pin, fn in re.findall(
            r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)(?: \(pinfunction "([^"]*)"\))?', block
        ):
            nets.setdefault(ref, []).append((pin, fn, name))
    return nets


if __name__ == "__main__":
    nets = parse(sys.argv[1])
    for pin, fn, name in sorted(nets.get(sys.argv[2], []), key=lambda r: int(r[0]) if r[0].isdigit() else 999):
        print(f"{pin:>4} {fn:<22} {name}")
