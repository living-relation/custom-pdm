import sys, collections, re, math, json
errf, geof, outf = sys.argv[1], sys.argv[2], sys.argv[3]
objs = []
for l in open(geof, encoding='utf-8', errors='replace'):
    p = l.rstrip('\n').split('|')
    if p[0] == 'PAD': objs.append(('%s.%s' % (p[1], p[2]), p[3], float(p[4]), float(p[5]), 'pth d%.2f h%.2f' % (float(p[6]), float(p[7]))))
    elif p[0] == 'SMD': objs.append(('%s.%s' % (p[1], p[2]), p[3], float(p[4]), float(p[5]), 'smd'))
    elif p[0] == 'VIA': objs.append(('via', p[1], float(p[2]), float(p[3]), 'via d%.2f h%.2f' % (float(p[4]), float(p[5]))))
    elif p[0] in ('PH',): objs.append(('%s.hole' % p[1], '', float(p[2]), float(p[3]), 'npth %.2f' % float(p[4])))
    elif p[0] == 'BH': objs.append(('boardhole', '', float(p[1]), float(p[2]), 'npth %.2f' % float(p[3])))
    elif p[0] == 'AIR': objs.append(('airwire', p[1], float(p[2]), float(p[3]), 'air to %s,%s' % (p[4], p[5])))
def near(x, y, n=3, r=2.0):
    d = sorted((math.hypot(o[2] - x, o[3] - y), o) for o in objs if o[0] != 'airwire')
    return ['%s[%s]%s@%.2f' % (o[0], o[1], ' ' + o[4] if o[4] != 'smd' else '', dd) for dd, o in d[:n] if dd <= r]
rows = [l.rstrip('\n').split('|') for l in open(errf, encoding='utf-8', errors='replace') if l.strip()]
out = []
for r in rows:
    x, y = float(r[3]), float(r[4])
    out.append(dict(code=int(r[0]), type=int(r[1]), layer=int(r[2]), x=x, y=y, desc=r[5], near=near(x, y)))
json.dump(out, open(outf, 'w'), indent=0)
g = collections.defaultdict(list)
for e in out:
    g[(e['code'], re.sub(r'[\d.]+ ?mil', 'N', e['desc']))].append(e)
for k, es in sorted(g.items(), key=lambda kv: -len(kv[1])):
    print('== %d x code %d %s' % (len(es), k[0], k[1]))
    refs = collections.Counter()
    for e in es:
        for n in e['near'][:2]:
            refs[n.split('[')[0].split('.')[0]] += 1
    print('   near parts:', refs.most_common(25))
    for e in es[:3]:
        print('   e.g. L%d (%.2f,%.2f) %s' % (e['layer'], e['x'], e['y'], e['near']))
for o in objs:
    if o[0] == 'airwire':
        print('AIR', o[1], (o[2], o[3]), o[4], near(o[2], o[3], 2))
