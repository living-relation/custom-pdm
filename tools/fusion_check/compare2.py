import json, sys, collections
ref = json.load(open(sys.argv[1]))
key, fus = sys.argv[2], sys.argv[3]
k = ref[key]
E, S = {}, {}
for line in open(fus, encoding='utf-8', errors='replace'):
    line = line.rstrip('\n')
    if line.startswith('E '):
        n, pkg, c = line[2:].split('|'); E[n] = (pkg, int(c))
    elif line.startswith('S '):
        n, c, rest = line[2:].split('|', 2); S[n] = set(rest.split())
# kicad pads per ref (numbered + unnumbered), and nets as pin sets
kp = collections.Counter(); kpn = collections.Counter(); knet = collections.defaultdict(set)
for r, num, net, attr in k['padlist']:
    kp[r] += 1
    if num != '':
        kpn[r] += 1
    if net and num != '':
        knet[net].add('%s.%s' % (r, num))
# per element pad count diffs
diff = []
for r in sorted(kp):
    fc = E.get(r, (None, 0))[1]
    if fc != kp[r]:
        diff.append('%s kicad %d (numbered %d) fusion %d' % (r, kp[r], kpn[r], fc))
print('pad count differences (%d parts):' % len(diff))
for d in diff: print('  ' + d)
# kicad pads with same number in one footprint (merged in Fusion?)
dup = collections.Counter((r, num) for r, num, net, attr in k['padlist'] if num != '')
dups = sorted('%s.%s x%d' % (r, n, c) for (r, n), c in dup.items() if c > 1)
print('kicad repeated pad numbers within a footprint: %d groups, %d extra pads' % (len(dups), sum(c - 1 for c in dup.values() if c > 1)))
# connectivity: map each pin to its net, both sides
def norm(pin):
    return pin.upper()
kmap = {}
for n, pins in knet.items():
    for p in pins: kmap[norm(p)] = n
fmap = {}
for n, pins in S.items():
    for p in pins: fmap[norm(p)] = n
# fusion contact names may carry suffixes for duplicate pads (e.g. 1@1): strip @
import re
def base(p):
    return re.sub(r'_\d+$', '', p.split('@')[0])
fmapb = {}
for p, n in fmap.items(): fmapb.setdefault(base(p), set()).add(n)
# compare partitions: for each kicad net with >=2 pins, the fusion nets its pins land in
split, merged, missing = [], collections.defaultdict(set), []
multi = {n: p for n, p in knet.items() if len(p) >= 2}
for n, pins in multi.items():
    fn = set()
    for p in pins:
        s = fmapb.get(norm(p))
        if s: fn |= s
        else: missing.append((n, p))
    if len(fn) > 1: split.append((n, sorted(fn)))
    for f in fn: merged[f].add(n)
merged = {f: sorted(ns) for f, ns in merged.items() if len(ns) > 1}
names_eq = sum(1 for n in multi if any(f.upper() == n.upper() or f.upper() == n.strip('/').replace('/', '_').upper() for f in S))
print('kicad nets with >=2 pads: %d; fusion signals %d' % (len(multi), len(S)))
print('kicad nets split into several fusion signals: %d %s' % (len(split), split[:10]))
print('fusion signals that merge several kicad nets: %d %s' % (len(merged), list(merged.items())[:10]))
print('kicad pins not on any fusion signal: %d %s' % (len(missing), missing[:20]))
fpins = set(base(p) for p in fmap); kpins = set(kmap)
extra = sorted(p for p in fpins if p not in kpins)
print('fusion pins on a signal that kicad has on no multi-pad net: %d %s' % (len(extra), extra[:20]))
named = [n for n in multi if not n.startswith('Net-(')]
print('kicad named multi-pad nets %d; name kept in fusion (exact or /sheet/x -> SHEET_X) %d' % (len(named), names_eq))

un = [(r, attr) for r, num, net, attr in k['padlist'] if num == '']
print('kicad unnumbered pads (ref, attr 0=PTH 1=SMD 2=CONN 3=NPTH):', collections.Counter(un))

