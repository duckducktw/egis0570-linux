"""Cross-session evaluation of verification strategies (FFT NCC, v3 preprocessing = localnorm).
Sessions (same evening, different enrollments -> weak proxy for cross-day):
  live1: 21 enroll frames (20:54)   live2: 21 enroll frames (21:26)   collect1: A presses (bursts of 10)
Genuine probes: collect1 A_* bursts vs live1/live2 galleries.  Impostor: collect1 B_other (excl. #1) bursts.
"""
import numpy as np, sys, glob, os, itertools
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.argv = [sys.argv[0], os.path.join(HERE, '../datasets/collect1')] + sys.argv[1:]
import acc_harness as h, fftncc as F

def pre(f, b): return h.pre_localnorm(f, b)

def live_gallery(d, n=21):
    fs = sorted(glob.glob(os.path.join(HERE, '../datasets', d, '*_raw.pgm')))[:n]
    A = [h.rd(f) for f in fs]
    return [pre(a[:57], a[57:]) for a in A]

def init():
    global P, GEN, IMP, GAL, GSPEC
    h.init(); P = h.P
    GEN = [k for k in P if k[0] in ('A_same', 'A_move')]
    IMP = [k for k in P if k[0] == 'B_other' and k[1] != 1]
    GAL = {'live1': live_gallery('live1'), 'live2': live_gallery('live2')}
    GSPEC = {g: [F.gallery_spec(x) for x in imgs] for g, imgs in GAL.items()}

def burst_scores(args):
    """score matrix (10 frames x |gallery|) for one probe burst vs one gallery"""
    k, g = args
    frs, b = P[k]
    return np.array([[F.ncc_fft(F.probe_spec(pre(f, b)), G) for G in GSPEC[g]] for f in frs])

if __name__ == '__main__':
    init()
    jobs = [(k, g) for g in ('live1', 'live2') for k in GEN + IMP]
    with Pool(18, initializer=init) as pool:
        res = pool.map(burst_scores, jobs)
    S = {j: r for j, r in zip(jobs, res)}
    np.save(os.path.join(HERE, '../.tmp/xsess.npy'), {'S': S, 'GEN': GEN, 'IMP': IMP}, allow_pickle=True)
    print('cached', len(S))
