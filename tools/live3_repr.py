"""Candidate representations on live3 (impostor = 4 unenrolled fingers + 2 slips).
Each variant changes preprocessing; matching stays FFT masked NCC so the
driver keeps its fast path. Reports d' and genuine accept at 0 FAR (+0.02).
Variants are evaluated on a common gallery built from enrollment dumps of
fingers 6 and 8 (finger 7 has no raw dumps), probes = 5 frames."""
import os, sys, pickle, numpy as np, cv2
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(__file__))
import live3_eval as E
import fftncc
R = E.R
SL = set(E.L.get('slips', []))  # genuine-labelled presses that were really another finger
B = 3
def base(f, b, hp=3.0, lp=0.8, ln=4.0):
    x = (f - b)[B:-B, B:-B]
    x = x - cv2.GaussianBlur(x, (0, 0), hp)
    if lp > 0: x = cv2.GaussianBlur(x, (0, 0), lp)
    if ln > 0:
        sd = np.sqrt(cv2.GaussianBlur(x * x, (0, 0), ln)) + 1e-3 * x.std(); x = x / sd
    return x
def z(x): return (x - x.mean()) / (x.std() + 1e-9)
def half(x): return cv2.resize(x, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_LINEAR)
def orient_field(x, s=2.0):
    gx = cv2.Sobel(x, cv2.CV_64F, 1, 0, ksize=3); gy = cv2.Sobel(x, cv2.CV_64F, 0, 1, ksize=3)
    gxx = cv2.GaussianBlur(gx * gx, (0, 0), s); gyy = cv2.GaussianBlur(gy * gy, (0, 0), s)
    gxy = cv2.GaussianBlur(gx * gy, (0, 0), s)
    th = 0.5 * np.arctan2(2 * gxy, gxx - gyy) + np.pi / 2
    coh = np.sqrt((gxx - gyy) ** 2 + 4 * gxy ** 2) / (gxx + gyy + 1e-9)
    return th, coh
def v_cur(f, b): return z(half(z(base(f, b))))
def v_full(f, b): return z(base(f, b))
def v_orient(f, b):
    th, coh = orient_field(base(f, b), 2.0)
    return np.hstack([z(half(np.cos(2 * th) * coh)), z(half(np.sin(2 * th) * coh))])
def v_gabor(f, b, period=7.0, nang=12):
    x = z(base(f, b, ln=0)); th, coh = orient_field(x, 2.0)
    out = np.zeros_like(x); bins = np.round(th / np.pi * nang).astype(int) % nang
    for k in range(nang):
        ker = cv2.getGaborKernel((13, 13), 2.2, k * np.pi / nang + np.pi / 2, period, 0.6, 0, ktype=cv2.CV_64F)
        ker -= ker.mean(); r = cv2.filter2D(x, cv2.CV_64F, ker); out[bins == k] = r[bins == k]
    return z(half(out))
def v_binar(f, b):
    x = base(f, b); return z(half(np.tanh(2.0 * z(x))))
def v_lp15(f, b): return z(half(z(base(f, b, lp=1.5))))
def v_hp5(f, b): return z(half(z(base(f, b, hp=5.0))))
VARS = dict(cur=v_cur, full=v_full, orient=v_orient, gabor=v_gabor, binar=v_binar, lp15=v_lp15, hp5=v_hp5)
IMPDIR = {t: lab for lab, tss in E.L['impostor'].items() for t in tss}
def items():
    out = []
    for p in E.L['probes']:
        w, t = p['winner'], p['ts']
        if w == 1:  # finger index 1 == print 7: no raw enrollment dumps, cannot rebuild
            continue
        out.append(('imp' if t in SL else ('acc' if (w is not None and w >= 0) else 'rej'), t, E.D))
    for t, lab in IMPDIR.items(): out.append(('imp', t, f'{R}/impostor/{lab}'))
    return out
_V = None; _G = None
def _init(name):
    global _V, _G
    cv2.setNumThreads(1); _V = VARS[name]
    _G = {}
    for fid, tss in E.GAL.items():
        _G[fid] = []
        for t in tss:
            fr = E.frames(t, 'e'); f, b = max(fr, key=lambda x: E.strength(*x))
            _G[fid].append(fftncc.gallery_spec(_V(f, b)))
def _job(it):
    c, t, d = it
    fr = E.frames(t, 'v', d)
    if len(fr) < 10: return None
    P = [fftncc.probe_spec(_V(*fr[k])) for k in E.VF]
    return c, t, {f: max(fftncc.ncc_fft(p, g) for p in P for g in G) for f, G in _G.items()}
def run(name):
    with Pool(20, _init, (name,)) as pool:
        return [r for r in pool.map(_job, items()) if r]
def report(name, res):
    D = {'imp': [], 'acc': [], 'rej': []}
    for c, t, s in res: D[c].append(max(s.values()))
    I, A, J = map(np.array, (D['imp'], D['acc'], D['rej']))
    thr = I.max() + 0.02
    dp = (A.mean() - I.mean()) / np.sqrt((A.var() + I.var()) / 2)
    print(f"{name:8s} d'={dp:.2f} imp max {I.max():.3f} mean {I.mean():.3f} | thr {thr:.3f}: acc {(A>=thr).mean():.0%} rej {(J>=thr).mean():.0%}", flush=True)
if __name__ == '__main__':
    for n in (sys.argv[1:] or VARS):
        res = run(n); pickle.dump(res, open(f'{R}/repr_{n}.pkl', 'wb')); report(n, res)
