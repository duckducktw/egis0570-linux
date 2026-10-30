import numpy as np, os
HERE = os.path.dirname(os.path.abspath(__file__))
D = np.load(os.path.join(HERE, '../.tmp/xsess.npy'), allow_pickle=True).item()
S, GEN, IMP = D['S'], D['GEN'], D['IMP']

def agg(M, frames, rule):
    """M: (10 frames, G). returns scalar decision score"""
    X = M[frames]
    if rule == 'max': return X.max()
    if rule == 'top2mean_gallery':   # per frame: mean of two best gallery matches; then max over frames
        s = np.sort(X, 1)[:, -2:].mean(1); return s.max()
    if rule == 'frame_vote2':        # 2nd best frame's best score (needs 2 frames agreeing)
        s = np.sort(X.max(1)); return s[-2] if len(s) > 1 else s[-1]
    if rule == 'mean_frames':
        return X.max(1).mean()

FR = {'last': [9], 'f3': [3, 6, 9], 'f5': [1, 3, 5, 7, 9], 'all10': list(range(10))}
print(f"{'strategy':28s} {'gal':5s} {'imp_max':>7s} {'imp_mu':>6s} {'sd':>5s} {'thr(+6.6sd)':>11s} {'TAR':>5s} {'d_prime':>7s}")
for g in ('live1', 'live2'):
    for fr, rule in [('last', 'max'), ('f3', 'max'), ('f5', 'max'), ('all10', 'max'),
                     ('f3', 'top2mean_gallery'), ('all10', 'top2mean_gallery'), ('f5', 'frame_vote2'), ('all10', 'frame_vote2')]:
        gen = np.array([agg(S[(k, g)], FR[fr], rule) for k in GEN])
        imp = np.array([agg(S[(k, g)], FR[fr], rule) for k in IMP])
        # impostor null from ALL impostor frame-gallery pairs (more samples) for scale
        null = np.concatenate([S[(k, g)].ravel() for k in IMP])
        mu, sd = null.mean(), null.std()
        thr = max(imp.max() + 0.03, mu + 6.6 * sd)
        dp = (gen.mean() - imp.mean()) / np.sqrt((gen.var() + imp.var()) / 2)
        print(f"{fr + '/' + rule:28s} {g:5s} {imp.max():7.3f} {mu:6.3f} {sd:5.3f} {thr:11.3f} {np.mean(gen >= thr):5.0%} {dp:7.2f}")
