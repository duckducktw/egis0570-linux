"""Online adaptive-learning simulation on live3 (owner presses in time order).
Learn rule: s_orig >= ANCHOR and best >= LEARN and best < 0.85, cap 20.
Accept rule: s_orig >= THR or s_learned >= T_L. Reports impostor max vs the
final grown gallery and the owner's online accept rate."""
import sys, pickle, numpy as np
from multiprocessing import Pool
import live3_eval as E, fftncc, cv2

SL = set(E.L.get('slips', []))  # genuine-labelled presses that were really another finger
IMPDIR = {t: lab for lab, tss in E.L['impostor'].items() for t in tss}
def imgs(t, kind, d):
    fr = E.frames(t, kind, d)
    if len(fr) < 10: return None
    return [E.pre(*fr[k]) for k in E.VF]
def load():
    G = {f: [E.pre(*max(E.frames(t, 'e'), key=lambda x: E.strength(*x))) for t in tss]
         for f, tss in E.GAL.items()}
    gen, imp = [], []
    for p in sorted(E.L['probes'], key=lambda p: p['ts']):
        if p['winner'] == 1: continue
        P = imgs(p['ts'], 'v', E.D)
        if P is None: continue
        (imp if p['ts'] in SL else gen).append((p['ts'], P))
    for t, lab in IMPDIR.items():
        P = imgs(t, 'v', f'{E.R}/impostor/{lab}')
        if P is not None: imp.append((t, P))
    return G, gen, imp
def best(P, gal):
    """max NCC over probe frames x gallery images; returns (score, frame idx)."""
    b, k = -1.0, 0
    for i, p in enumerate(P):
        ps = fftncc.probe_spec(p)
        for g in gal:
            s = fftncc.ncc_fft(ps, fftncc.gallery_spec(g))
            if s > b: b, k = s, i
    return b, k
def simulate(G, gen, cfg):
    """Owner presses in time order. Returns learned galleries and online stats."""
    thr, anchor, learn, tl = cfg['thr'], cfg['anchor'], cfg['learn'], cfg['tl']
    Lrn = {f: [] for f in G}; acc = 0
    for t, P in gen:
        so = {f: best(P, G[f]) for f in G}
        sl = {f: best(P, Lrn[f]) if Lrn[f] else (-1.0, 0) for f in G}
        ok = any(so[f][0] >= thr or sl[f][0] >= tl for f in G)
        acc += ok
        f = max(G, key=lambda f: so[f][0])
        b = max(so[f][0], sl[f][0])
        if so[f][0] >= anchor and b >= learn and b < 0.85:
            Lrn[f].append(P[so[f][1]]); Lrn[f] = Lrn[f][-20:]
    return Lrn, acc / len(gen)
def imp_scores(G, Lrn, imp):
    """per impostor: (max vs original, max vs learned)"""
    out = []
    for t, P in imp:
        so = max(best(P, G[f])[0] for f in G)
        sl = max((best(P, Lrn[f])[0] for f in G if Lrn[f]), default=-1.0)
        out.append((so, sl))
    return np.array(out)
CFGS = {
  'driver_now': dict(thr=0.49, anchor=0.49, learn=0.50, tl=0.49),
  'anchor55':   dict(thr=0.49, anchor=0.55, learn=0.60, tl=0.49),
  'anchor60':   dict(thr=0.49, anchor=0.60, learn=0.65, tl=0.49),
  'anchor55_tl55': dict(thr=0.49, anchor=0.55, learn=0.60, tl=0.55),
}
def _run(name):
    cv2.setNumThreads(1)
    G, gen, imp = load()
    Lrn, onl = simulate(G, gen, CFGS[name])
    S = imp_scores(G, Lrn, imp)
    return name, onl, {f: len(v) for f, v in Lrn.items()}, S
if __name__ == '__main__':
    names = sys.argv[1:] or list(CFGS)
    with Pool(len(names)) as pool:
        for name, onl, nl, S in pool.map(_run, names):
            pickle.dump(S, open(f'{E.R}/adapt_{name}.pkl', 'wb'))
            print(f"{name:14s} owner online {onl:.0%} learned {nl} | imp max orig {S[:,0].max():.3f} learned {S[:,1].max():.3f}", flush=True)

def trace(G, gen, cfg):
    """Like simulate, but returns per-press (orig best, learned best) at press time."""
    anchor, learn = cfg['anchor'], cfg['learn']
    Lrn = {f: [] for f in G}; rows = []
    for t, P in gen:
        so = {f: best(P, G[f]) for f in G}
        sl = {f: best(P, Lrn[f]) if Lrn[f] else (-1.0, 0) for f in G}
        rows.append((max(v[0] for v in so.values()), max(v[0] for v in sl.values())))
        f = max(G, key=lambda f: so[f][0]); b = max(so[f][0], sl[f][0])
        if so[f][0] >= anchor and b >= learn and b < 0.85:
            Lrn[f].append(P[so[f][1]]); Lrn[f] = Lrn[f][-20:]
    return np.array(rows), Lrn
