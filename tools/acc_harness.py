"""Fast, parallel accuracy harness for matcher variants.
Metrics (LOO; gallery = other genuine presses, strongest frame each):
  d'      = separation of genuine vs impostor score distributions (higher = more accurate)
  TAR@0.50 with impostors as-is; TAR@FAR0 = genuine accepted at threshold = impostor max + 0.05 margin
Impostors exclude B_other/1 (suspected mis-press)."""
import numpy as np, sys, os, glob, cv2, time, itertools
from multiprocessing import Pool
ROOT = sys.argv[1]; ONLY = sys.argv[2:] 
H, B = 57, 3

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
            A = [rd(f) for f in fs][-10:]
            P[(lab, int(pr))] = (np.array([a[:H] for a in A]), A[-1][H:])
    return P

def strength(f, b): return float((f - b)[B:-B, B:-B].std())

# ---------------- preprocessing variants ----------------
def pre_base(f, b, scale=0.5, hp=3.0, lp=0.8):
    x = (f - b)[B:-B, B:-B]
    x = x - cv2.GaussianBlur(x, (0, 0), hp)
    if lp > 0: x = cv2.GaussianBlur(x, (0, 0), lp)
    x = (x - x.mean()) / (x.std() + 1e-9)
    return cv2.resize(x, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR) if scale != 1 else x

def pre_localnorm(f, b, scale=0.5, hp=3.0, lp=0.8, ln=4.0):
    x = (f - b)[B:-B, B:-B]
    x = x - cv2.GaussianBlur(x, (0, 0), hp)
    if lp > 0: x = cv2.GaussianBlur(x, (0, 0), lp)
    sd = np.sqrt(cv2.GaussianBlur(x * x, (0, 0), ln)) + 1e-3 * x.std()
    x = x / sd
    x = (x - x.mean()) / (x.std() + 1e-9)
    return cv2.resize(x, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR) if scale != 1 else x

def orient_field(x, s=3.0):
    gx = cv2.Sobel(x, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(x, cv2.CV_32F, 0, 1, ksize=3)
    gxx = cv2.GaussianBlur(gx * gx, (0, 0), s); gyy = cv2.GaussianBlur(gy * gy, (0, 0), s); gxy = cv2.GaussianBlur(gx * gy, (0, 0), s)
    theta = 0.5 * np.arctan2(2 * gxy, gxx - gyy) + np.pi / 2  # ridge direction
    coh = np.sqrt((gxx - gyy) ** 2 + 4 * gxy ** 2) / (gxx + gyy + 1e-9)
    return theta, coh

def pre_gabor(f, b, scale=0.5, hp=3.0, period=None, nang=16, sigma=2.0):
    """Orientation-adaptive Gabor enhancement (Hong/Wan/Jain 1998 style)."""
    x = (f - b)[B:-B, B:-B]
    x = x - cv2.GaussianBlur(x, (0, 0), hp); x = (x - x.mean()) / (x.std() + 1e-9)
    theta, coh = orient_field(x)
    if period is None: period = 7.0
    out = np.zeros_like(x); bins = (np.round(theta / np.pi * nang).astype(int)) % nang
    for k in range(nang):
        ang = k * np.pi / nang
        # kernel oscillates across ridges: getGaborKernel theta = normal direction
        ker = cv2.getGaborKernel((15, 15), sigma, ang + np.pi / 2, period, 0.7, 0, ktype=cv2.CV_32F)
        ker -= ker.mean()
        r = cv2.filter2D(x, cv2.CV_32F, ker)
        out[bins == k] = r[bins == k]
    out = (out - out.mean()) / (out.std() + 1e-9)
    return cv2.resize(out, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR) if scale != 1 else out

def pre_orient(f, b, scale=0.5):
    """Orientation-field representation (cos2θ, sin2θ weighted by coherence) — pressure-invariant."""
    x = (f - b)[B:-B, B:-B]
    x = x - cv2.GaussianBlur(x, (0, 0), 3.0)
    theta, coh = orient_field(x, s=2.0)
    c = np.cos(2 * theta) * coh; s = np.sin(2 * theta) * coh
    c = cv2.resize(c, None, fx=scale, fy=scale); s = cv2.resize(s, None, fx=scale, fy=scale)
    return np.stack([c, s])

# ---------------- scorers ----------------
def ncc_shift(a, b, angles=(-15, -10, -5, 0, 5, 10, 15), min_overlap=0.5, r=None):
    h, w = a.shape[-2:]; best = -1.0
    multi = a.ndim == 3
    for ang in angles:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        if multi:
            br = np.stack([cv2.warpAffine(c, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=np.nan) for c in b])
        else:
            br = cv2.warpAffine(b, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=np.nan)
        rx = w // 2 if r is None else r
        for dy in range(-h // 2, h // 2 + 1):
            for dx in range(-rx, rx + 1):
                ya, yb = max(0, dy), max(0, -dy); xa, xb = max(0, dx), max(0, -dx)
                hh, ww = h - abs(dy), w - abs(dx)
                if hh * ww < min_overlap * h * w: continue
                A_ = a[..., ya:ya + hh, xa:xa + ww]; B_ = br[..., yb:yb + hh, xb:xb + ww]
                m = ~np.isnan(B_)
                if multi: m = m.all(0)
                if m.sum() < min_overlap * h * w: continue
                if multi:
                    x1 = A_[:, m]; x2 = B_[:, m]
                    v = (x1 * x2).sum() / np.sqrt((x1 * x1).sum() * (x2 * x2).sum() + 1e-9)  # orientation: no mean removal
                else:
                    x1 = A_[m] - A_[m].mean(); x2 = B_[m] - B_[m].mean()
                    v = (x1 * x2).sum() / np.sqrt((x1 * x1).sum() * (x2 * x2).sum() + 1e-9)
                if v > best: best = v
    return best

def poc(a, b, angles=(-15, -10, -5, 0, 5, 10, 15), band=0.5):
    """Band-limited phase-only correlation peak (Ito et al. 2004), max over rotations."""
    h, w = a.shape
    win = np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)
    Fa = np.fft.fft2(a * win)
    fy = np.fft.fftfreq(h)[:, None]; fx = np.fft.fftfreq(w)[None, :]
    mask = (np.abs(fy) <= band * 0.5) & (np.abs(fx) <= band * 0.5)
    best = 0.0
    for ang in angles:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        br = cv2.warpAffine(b, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
        Fb = np.fft.fft2(br * win)
        R = Fa * np.conj(Fb); R = R / (np.abs(R) + 1e-9); R = R * mask
        r = np.real(np.fft.ifft2(R)) / mask.sum()
        # sum of top-2 neighbours peak energy for robustness
        best = max(best, float(r.max()))
    return best

# ---------------- variants ----------------
VARIANTS = {
    'base':          (lambda f, b: pre_base(f, b), lambda a, g: ncc_shift(a, g)),
    'fullres':       (lambda f, b: pre_base(f, b, scale=1.0), lambda a, g: ncc_shift(a, g)),
    'base_rot2.5':   (lambda f, b: pre_base(f, b), lambda a, g: ncc_shift(a, g, angles=np.arange(-15, 15.1, 2.5))),
    'localnorm':     (lambda f, b: pre_localnorm(f, b), lambda a, g: ncc_shift(a, g)),
    'ln_full':       (lambda f, b: pre_localnorm(f, b, scale=1.0), lambda a, g: ncc_shift(a, g)),
    'ln2':           (lambda f, b: pre_localnorm(f, b, ln=2.5), lambda a, g: ncc_shift(a, g)),
    'ln_hp2':        (lambda f, b: pre_localnorm(f, b, hp=2.0), lambda a, g: ncc_shift(a, g)),
    'ln_hp4':        (lambda f, b: pre_localnorm(f, b, hp=4.0), lambda a, g: ncc_shift(a, g)),
    'gabor':         (lambda f, b: pre_gabor(f, b), lambda a, g: ncc_shift(a, g)),
    'orient':        (lambda f, b: pre_orient(f, b), lambda a, g: ncc_shift(a, g)),
    'poc_base':      (lambda f, b: pre_base(f, b, scale=1.0, lp=0), lambda a, g: poc(a, g)),
    'poc_gabor':     (lambda f, b: pre_gabor(f, b, scale=1.0), lambda a, g: poc(a, g)),
}

P = None; G = None; Bo = None
def init():
    global P, G, Bo
    P = load(); keys = list(P)
    G = [k for k in keys if k[0] in ('A_same', 'A_move')]
    Bo = [k for k in keys if k[0] == 'B_other' and k[1] != 1]

def job(args):
    name, p = args
    pre, sc = VARIANTS[name]
    frs, b = P[p]
    probe = pre(frs[-1], b)
    out = []
    for g in G:
        if g == p: continue
        gf, gb = P[g]; i = int(np.argmax([strength(f, gb) for f in gf]))
        out.append(sc(probe, pre(gf[i], gb)))
    return max(out)

def dprime(g, i): return (g.mean() - i.mean()) / np.sqrt((g.var() + i.var()) / 2 + 1e-12)

if __name__ == '__main__':
    init()
    names = ONLY or list(VARIANTS)
    with Pool(18, initializer=init) as pool:
        for name in names:
            t = time.time()
            gen = np.array(pool.map(job, [(name, p) for p in G]))
            imp = np.array(pool.map(job, [(name, p) for p in Bo]))
            thr0 = imp.max() + 0.05 * (gen.mean() - imp.mean())
            print(f"{name:13s} d'={dprime(gen, imp):5.2f} | gen med {np.median(gen):.3f} min {gen.min():.3f} | "
                  f"imp med {np.median(imp):.3f} max {imp.max():.3f} | TAR@FAR0(+margin) {np.mean(gen > thr0):4.0%} "
                  f"| {time.time() - t:4.0f}s", flush=True)
