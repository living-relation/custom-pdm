"""Write JLCPCB rule sets (EAGLE / Fusion .dru) from the imported rule file: same limits as tools/gen_fab_jlcpcb.py JLC_LIMITS."""
import re, sys
src = open(sys.argv[1], encoding='latin-1').read()
LIM = {
    4: dict(track=0.09, clearance=0.09, smd_gap=0.15, hole=0.15, via_ring=0.05, pth_ring=0.15, h2h=0.2, edge=0.2,
            iso='0.2104mm 1.065mm 0.2104mm', name='JLCPCB 4-layer 1 oz / 1 oz, 1.6 mm (custom-pdm)'),
    2: dict(track=0.10, clearance=0.10, smd_gap=0.15, hole=0.15, via_ring=0.05, pth_ring=0.18, h2h=0.2, edge=0.2,
            iso='1.53mm', name='JLCPCB 2-layer 1 oz, 1.6 mm (custom-pdm)'),
}
for n, L in [(int(sys.argv[3]), LIM[int(sys.argv[3])])]:
    t = src
    def s(key, val):
        global t
        t2, k = re.subn(r'(?m)^%s = .*$' % re.escape(key), '%s = %s' % (key, val), t)
        if k != 1:
            raise SystemExit('key %s found %d times' % (key, k))
        t = t2
    c = '%gmm' % L['clearance']
    for key in ('mdWireWire', 'mdWirePad', 'mdWireVia', 'mdPadPad', 'mdPadVia', 'mdViaVia', 'mdSmdPad', 'mdSmdVia'):
        s(key, c)
    s('mdSmdSmd', '%gmm' % L['smd_gap'])
    s('mdCopperDimension', '%gmm' % L['edge'])
    s('mdDrill', '%gmm' % L['h2h'])
    s('mdViaViaSameLayer', c)
    s('msWidth', '%gmm' % L['track'])
    s('msDrill', '%gmm' % L['hole'])
    for key in ('rlMinPadTop', 'rlMinPadInner', 'rlMinPadBottom'):
        s(key, '%gmm' % L['pth_ring'])
    for key in ('rlMinViaOuter', 'rlMinViaInner'):
        s(key, '%gmm' % L['via_ring'])
    s('mtCopper', ' '.join(['0.035mm'] * 16))
    s('mtIsolate', L['iso'] + ' ' + ' '.join(['0.15mm'] * (15 - len(L['iso'].split()))))
    for key in ('rvPadTop', 'rvPadInner', 'rvPadBottom', 'rvViaOuter', 'rvViaInner'):
        s(key, '0.000000')
    s('maxErrors', '100000')
    s('description[en]', '<b>%s</b>' % L['name'])
    open(sys.argv[2] % n, 'w', encoding='latin-1').write(t)
    print('wrote', sys.argv[2] % n)



