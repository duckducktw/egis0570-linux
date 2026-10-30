"""Evaluate matchers on collected presses.
Layout: <root>/<label>/<press>/*_raw.pgm  (each raw = frame(57 rows) + background(57 rows), 114 wide)
Prints genuine (A vs A) and impostor (A vs B) score distributions per method."""
import numpy as np, glob, sys, os, itertools, cv2
ROOT = sys.argv[1]
W, H, B = 114, 57, 3

def rd(p):
    with open(p, 'rb') as f:
        f.readline(); w, h = map(int, f.readline().split()); mx = int(f.readline()); d = f.read()
    return np.frombuffer(d, dtype='>u2' if mx > 255 else np.uint8).reshape(h, w).astype(np.float32)

def load():
    P = {}
    for lab in sorted(os.listdir(ROOT)):
        for pr in sorted(os.listdir(os.path.join(ROOT, lab)), key=int):
            fs = sorted(glob.glob(os.path.join(ROOT, lab, pr, '*_raw.pgm')))
            if not fs: continue
            A = [rd(f) for f in fs]
            # last 10 frames = the final (accepted) attempt of this press
            A = A[-10:]
            P[(lab, int(pr))] = (np.array([a[:H] for a in A]), A[-1][H:])
    return P

def prep(f, b, up=2, clahe=3.0, hp=0.0):
    s = (f - b)[B:-B, B:-B]
    if hp > 0: s = s - cv2.GaussianBlur(s, (0, 0), hp)
    lo, hi = np.percentile(s, 1), np.percentile(s, 99)
    s = (np.clip((s - lo) / (hi - lo + 1e-9), 0, 1) * 255).astype(np.uint8)
    if up != 1: s = cv2.resize(s, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
    if clahe > 0: s = cv2.createCLAHE(clahe, (8, 8)).apply(s)
    return s

SIFT = cv2.SIFT_create(0, 3, 0.04, 12, 1.2)
def feats(img): return SIFT.detectAndCompute(img, None)

def sift_score(fa, fb, ratio=0.7, rep=3.0):
    (ka, da), (kb, db) = fa, fb
    if da is None or db is None or len(ka) < 2 or len(kb) < 2: return 0
    m = cv2.BFMatcher(cv2.NORM_L2).knnMatch(da, db, k=2)
    src, dst = [], []
    for p in m:
        if len(p) == 2 and p[0].distance < ratio * p[1].distance:
            src.append(ka[p[0].queryIdx].pt); dst.append(kb[p[0].trainIdx].pt)
    if len(src) < 4: return 0
    M, inl = cv2.estimateAffinePartial2D(np.float32(src), np.float32(dst), method=cv2.RANSAC,
                                         ransacReprojThreshold=rep, maxIters=3000, confidence=0.99)
    return 0 if inl is None else int(inl.sum())

def sym(fa, fb, **k): return min(sift_score(fa, fb, **k), sift_score(fb, fa, **k))

def hpimg(f, b, s=3.0):
    x = (f - b)[B:-B, B:-B]
    x = x - cv2.GaussianBlur(x, (0, 0), s)
    x = cv2.GaussianBlur(x, (0, 0), 0.8)
    return (x - x.mean()) / (x.std() + 1e-9)

def ncc_shift(a, b, r=40, min_overlap=0.25):
    """max normalized cross-correlation over translations (overlap >= min_overlap of area)."""
    h, w = a.shape; best = -1.0
    # also small rotations
    for ang in (-15, -10, -5, 0, 5, 10, 15):
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        br = cv2.warpAffine(b, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=np.nan)
        for dy in range(-h // 2, h // 2 + 1, 1):
            for dx in range(-r, r + 1, 1):
                ya, yb = max(0, dy), max(0, -dy); xa, xb = max(0, dx), max(0, -dx)
                hh, ww = h - abs(dy), w - abs(dx)
                if hh * ww < min_overlap * h * w: continue
                A_ = a[ya:ya + hh, xa:xa + ww]; B_ = br[yb:yb + hh, xb:xb + ww]
                m = ~np.isnan(B_)
                if m.sum() < min_overlap * h * w: continue
                x1 = A_[m] - A_[m].mean(); x2 = B_[m] - B_[m].mean()
                v = (x1 * x2).sum() / np.sqrt((x1 * x1).sum() * (x2 * x2).sum() + 1e-9)
                if v > best: best = v
    return best

def summarize(name, gen_same, gen_move, imp):
    g = np.array(gen_same); gm = np.array(gen_move); im = np.array(imp)
    thr = im.max()
    print(f'{name:28s} same-spot med={np.median(g):6.2f} max={g.max():6.2f} | moved med={np.median(gm):6.2f} | '
          f'impostor med={np.median(im):6.2f} max={im.max():6.2f} | genuine>imp.max: same {np.mean(g > thr):.0%} moved {np.mean(gm > thr):.0%}')

if __name__ == '__main__':
    P = load()
    keys = list(P)
    A_s = [k for k in keys if k[0] == 'A_same']; A_m = [k for k in keys if k[0] == 'A_move']; Bo = [k for k in keys if k[0] == 'B_other']
    print('presses:', len(A_s), len(A_m), len(Bo))
    # sanity: per-press background consistency
    bgs = np.array([P[k][1] for k in keys]); print('bg mean per press:', np.round(bgs.mean((1, 2)), 1)[:12], '...')
    method = sys.argv[2] if len(sys.argv) > 2 else 'sift'
    if method == 'sift':
        F = {k: feats(prep(P[k][0][-1], P[k][1])) for k in keys}
        gs = [sym(F[a], F[b]) for a, b in itertools.combinations(A_s, 2)]
        gm = [sym(F[a], F[b]) for a in A_s for b in A_m]
        im = [sym(F[a], F[b]) for a in A_s + A_m for b in Bo]
        summarize('sift driver params', gs, gm, im)
        gs = [sym(F[a], F[b], ratio=0.8) for a, b in itertools.combinations(A_s, 2)]
        gm = [sym(F[a], F[b], ratio=0.8) for a in A_s for b in A_m]
        im = [sym(F[a], F[b], ratio=0.8) for a in A_s + A_m for b in Bo]
        summarize('sift ratio .8', gs, gm, im)
    elif method == 'ncc':
        I = {k: cv2.resize(hpimg(P[k][0][-1], P[k][1]), None, fx=0.5, fy=0.5) for k in keys}
        gs = [ncc_shift(I[a], I[b], r=20) for a, b in itertools.combinations(A_s, 2)]
        gm = [ncc_shift(I[a], I[b], r=20) for a in A_s for b in A_m[:5]]
        im = [ncc_shift(I[a], I[b], r=20) for a in A_s[:5] for b in Bo]
        summarize('ncc shift+rot (half-res)', gs, gm, im)
