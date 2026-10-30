"""Simulate adaptive template update + enrollment-dedup stats (FFT NCC, v3 preprocessing).
Gallery = live1 enrollment (21). Adapt stream = live2 enroll frames (other session, genuine) used as if they were
successful unlocks. Test = collect1 A bursts (genuine, f5 frames) and B_other (impostor, excl #1)."""
import numpy as np, os, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.argv = [sys.argv[0], os.path.join(HERE, '../datasets/collect1')]
import acc_harness as h, fftncc as F
h.init(); P = h.P
pre = h.pre_localnorm
def live(d):
    fs = sorted(glob.glob(os.path.join(HERE, '../datasets', d, '*_raw.pgm')))[:21]
    return [pre(a[:57], a[57:]) for a in (h.rd(f) for f in fs)]
L1, L2 = live('live1'), live('live2')
F5 = [1, 3, 5, 7, 9]
GEN = [k for k in P if k[0] in ('A_same', 'A_move')]; IMP = [k for k in P if k[0] == 'B_other' and k[1] != 1]
probes = {k: [F.probe_spec(pre(P[k][0][i], P[k][1])) for i in F5] for k in GEN + IMP}

def score(pspecs, gal_specs):
    return max(F.ncc_fft(p, g) for p in pspecs for g in gal_specs)

# enrollment dedup: max pairwise score within each enrollment
for name, L in (('live1', L1), ('live2', L2)):
    sp = [F.gallery_spec(x) for x in L]; pp = [F.probe_spec(x) for x in L]
    M = np.array([[F.ncc_fft(pp[i], sp[j]) if i != j else np.nan for j in range(len(L))] for i in range(len(L))])
    print(name, 'enroll pairwise max per sample:', np.round(np.nanmax(M, 1), 2), 'overall max %.2f' % np.nanmax(M))

base = [F.gallery_spec(x) for x in L1]
def evaluate(gal, label, thr=0.38):
    g = np.array([score(probes[k], gal) for k in GEN]); i = np.array([score(probes[k], gal) for k in IMP])
    print(f'{label:34s} TAR@{thr} {np.mean(g >= thr):4.0%}  gen_med {np.median(g):.3f} gen_min {g.min():.3f} | imp_max {i.max():.3f}')
evaluate(base, 'live1 only')
for ADAPT in (0.45, 0.50, 0.55):
    gal = list(base); adapt = []; added = 0
    for x in L2:
        s = score([F.probe_spec(x)], gal + adapt)
        if s >= ADAPT:
            dup = adapt and score([F.probe_spec(x)], adapt) >= 0.85
            if not dup and len(adapt) < 20:
                adapt.append(F.gallery_spec(x)); added += 1
    evaluate(gal + adapt, f'live1 + adapt(thr {ADAPT}, +{added})')
evaluate(base + [F.gallery_spec(x) for x in L2], 'live1 + ALL live2 (upper bound)')
