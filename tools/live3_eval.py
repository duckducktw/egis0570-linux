"""Offline accuracy on datasets/live3: genuine probes vs 3 enrolled galleries,
impostor probes (unenrolled fingers). Usage: live3_eval.py [variant...]"""
import json, os, sys, numpy as np, cv2
from multiprocessing import Pool
import fftncc
R = os.path.join(os.path.dirname(__file__), '..', 'datasets', 'live3')
D = R + '/egisdump'
H, B = 57, 3
def rd(p):
    with open(p, 'rb') as f:
        f.readline(); w, h = map(int, f.readline().split()); f.readline(); d = f.read()
    a = np.frombuffer(d, dtype='>u2').reshape(h, w).astype(np.float32)
    return a[:H], a[H:]
def frames(t, kind, d=D):
    out = []
    for k in range(10):
        p = f'{d}/{t}_{kind}_f{k:02d}_raw.pgm'
        if os.path.exists(p): out.append(rd(p))
    return out
def strength(f, b):
    return float(np.maximum((f - b)[B:-B, B:-B], 0).sum())
def pre(f, b, hp=3.0, lp=0.8, ln=4.0, scale=0.5, **_):
    x = (f - b)[B:-B, B:-B]
    x = x - cv2.GaussianBlur(x, (0, 0), hp)
    if lp > 0: x = cv2.GaussianBlur(x, (0, 0), lp)
    if ln > 0:
        x = x / (np.sqrt(cv2.GaussianBlur(x * x, (0, 0), ln)) + 1e-3 * x.std())
    x = (x - x.mean()) / (x.std() + 1e-9)
    return cv2.resize(x, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
L = json.load(open(R + '/labels.json'))
V = dict(base=dict(ln=0), ln=dict())
def stored(fid):
    """The driver's own stored templates (half-res, preprocessed) for print fid."""
    import re, struct
    d = open(f'{R}/prints/{fid}', 'rb').read(); out = []
    for m in re.finditer(re.escape(struct.pack('<I', 0x45543032)), d):
        i = m.start(); _, v, w, h, _, sc, q = struct.unpack('<IHHHHff', d[i:i+20])
        out.append(np.frombuffer(d[i+20:i+20+w*h*2], '<i2').reshape(h, w).astype(np.float64) / q)
    return out
GAL = {6: L['gallery']['enrB'], 8: L['gallery']['enrA']}
def gallery_imgs(cfg=None):
    cfg = cfg or {}
    out = {}
    for fid, tss in GAL.items():
        G = []
        for t in tss:
            fr = frames(t, 'e')
            f, b = max(fr, key=lambda x: strength(*x))
            G.append(pre(f, b, **cfg))
        out[fid] = G
    out[7] = stored(7)
    return out
def gallery(cfg):
    out = {}
    for fid, tss in GAL.items():
        G = []
        for t in tss:
            fr = frames(t, 'e')
            f, b = max(fr, key=lambda x: strength(*x))
            G.append(fftncc.gallery_spec(pre(f, b, **cfg)))
        out[fid] = G
    if cfg.get('scale', 0.5) == 0.5 and cfg.get('hp', 3.0) == 3.0:
        out[7] = [fftncc.gallery_spec(x) for x in stored(7)]
    return out
VF = (1, 3, 5, 7, 9)
def probe_specs(t, kind, d, cfg):
    fr = frames(t, kind, d)
    if len(fr) < 10: return []
    return [fftncc.probe_spec(pre(*fr[k], **cfg)) for k in VF]
def score(P, G):
    mo = _CFG.get('mo', 0.5)
    if _CFG.get('arg'):
        # per gallery sample: list of (score, angle, dy, dx) for each probe frame
        return [[(lambda r: (r[0],) + r[1])(fftncc.ncc_fft_arg(p, g, min_overlap=mo)) for p in P] for g in G]
    if _CFG.get('all'):
        return sorted((max(fftncc.ncc_fft(p, g, min_overlap=mo) for p in P) for g in G), reverse=True)
    return max((fftncc.ncc_fft(p, g, min_overlap=mo) for p in P for g in G), default=-1.0)
def items():
    out = [('gen', p['winner'], p['ts'], 'v', D) for p in L['probes']]
    for lab, tss in L['impostor'].items():
        out += [('imp', lab, t, 'v', f'{R}/impostor/{lab}') for t in tss]
    return out
_G = None
def _init(cfg, use_stored):
    global _G, _CFG
    _CFG = cfg
    if use_stored:
        _G = {f: [fftncc.gallery_spec(x) for x in stored(f)] for f in (6, 7, 8)}
    else:
        _G = gallery(cfg)
def _job(it):
    kind, lab, t, k, d = it
    P = probe_specs(t, k, d, _CFG)
    if not P: return None
    return (kind, lab, t, {f: score(P, G) for f, G in _G.items()})
def run(cfg, use_stored=False):
    with Pool(16, _init, (cfg, use_stored)) as pool:
        return [r for r in pool.map(_job, items()) if r]
def summary(name, res, thr=0.38):
    imp = np.array([max(s.values()) for k, _, _, s in res if k == 'imp'])
    gen = np.array([max(s.values()) for k, w, _, s in res if k == 'gen' and w is not None and w >= 0])
    rej = np.array([max(s.values()) for k, w, _, s in res if k == 'gen' and w == -1])
    t0 = imp.max() + 0.02
    print(f'{name:14s} imp n={len(imp)} max={imp.max():.3f} >={thr}:{(imp>=thr).sum():2d} | '
          f'gen(acc) n={len(gen)} @{thr}:{(gen>=thr).mean():.0%} @imp+.02({t0:.2f}):{(gen>=t0).mean():.0%} | '
          f'gen(rej) n={len(rej)} @imp+.02:{(rej>=t0).mean():.0%}')
if __name__ == '__main__':
    import pickle
    VAR = {
        'cur': dict(),
        'all': dict(all=1),
        'arg': dict(arg=1, all=1),
        'all.mo.6': dict(all=1, mo=0.6),
        'mo.65': dict(mo=0.65),
        'mo.75': dict(mo=0.75),
        'full': dict(scale=1.0),
        'full.mo.65': dict(scale=1.0, mo=0.65),
        'full.mo.75': dict(scale=1.0, mo=0.75),
        'hp2': dict(hp=2.0),
        'hp2.full.mo.65': dict(hp=2.0, scale=1.0, mo=0.65),
    }
    pick = sys.argv[1:] or list(VAR)
    for n in pick:
        res = run(VAR[n])
        pickle.dump(res, open(f'{R}/res_{n}.pkl', 'wb'))
        if VAR[n].get('all'):
            continue
        summary(n, res)
