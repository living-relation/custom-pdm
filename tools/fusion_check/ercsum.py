import sys, collections, re
rows = [l.rstrip('\n').split('|') for l in open(sys.argv[1], encoding='utf-8', errors='replace') if l.strip()]
c = collections.Counter(); ex = collections.defaultdict(list)
for r in rows:
    d = r[5]
    k = re.sub(r'(part|Component|pin|net|signal|signals|with) \S+', r'\1 X', d)
    k = re.sub(r'\(.*\)', '(..)', k)
    c[(r[0], r[1], k)] += 1
    ex[(r[0], r[1], k)].append(d)
print('total', len(rows), 'by type (1 warning? 2 error? 3 info?):', collections.Counter(r[1] for r in rows))
for k, n in c.most_common():
    print(n, 'code', k[0], 'type', k[1], k[2], '| e.g.', '; '.join(sorted(set(ex[k]))[:6]))
