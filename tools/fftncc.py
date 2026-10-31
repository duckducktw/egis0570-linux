"""FFT masked NCC (Padfield 2012) — exact re-implementation of acc_harness.ncc_shift semantics:
a fixed (probe), b rotated about centre with NaN border (gallery), every (dy,dx) with |dy|<=h//2, |dx|<=rx,
overlap >= min_overlap*h*w valid pixels; returns max Pearson r over all shifts and angles."""
import numpy as np, cv2

ANGLES = (-15, -10, -5, 0, 5, 10, 15)

def _shape(h, w):
    return cv2.getOptimalDFTSize(2 * h), cv2.getOptimalDFTSize(2 * w)

def _fft(x, H, W):
    p = np.zeros((H, W)); p[:x.shape[0], :x.shape[1]] = x
    return np.fft.rfft2(p)

def probe_spec(a):
    h, w = a.shape; H, W = _shape(h, w)
    a = a.astype(np.float64); one = np.ones_like(a)
    return dict(h=h, w=w, H=H, W=W, A1=_fft(one, H, W), A=_fft(a, H, W), A2=_fft(a * a, H, W))

def gallery_spec(b, angles=ANGLES):
    h, w = b.shape; H, W = _shape(h, w); out = []
    for ang in angles:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        br = cv2.warpAffine(b.astype(np.float32), M, (w, h), flags=cv2.INTER_LINEAR, borderValue=np.nan).astype(np.float64)
        m = ~np.isnan(br); bz = np.where(m, br, 0.0)
        out.append((_fft(m.astype(np.float64), H, W), _fft(bz, H, W), _fft(bz * bz, H, W)))
    return out

def _xcorr(FX, FY, H, W):
    # c(s) = sum_p X(p) Y(p - s)  -> index s mod size ; computed as ifft(FX * conj(FY))  gives sum_p X(p+s)Y(p)
    # we want shift s = (dy,dx) with a region at ya=max(0,dy) and b at yb=max(0,-dy): pairs a[p] with b[p - (dy,dx)]
    return np.fft.irfft2(FX * np.conj(FY), s=(H, W))

def ncc_fft(P, G, rx=None, min_overlap=0.5):
    h, w, H, W = P['h'], P['w'], P['H'], P['W']
    rx = w // 2 if rx is None else rx
    dys = np.arange(-(h // 2), h // 2 + 1); dxs = np.arange(-rx, rx + 1)
    iy = dys % H; ix = dxs % W
    best = -1.0
    need = min_overlap * h * w
    for (M, B, B2) in G:
        n = _xcorr(P['A1'], M, H, W)[np.ix_(iy, ix)]
        Sa = _xcorr(P['A'], M, H, W)[np.ix_(iy, ix)]
        Saa = _xcorr(P['A2'], M, H, W)[np.ix_(iy, ix)]
        Sb = _xcorr(P['A1'], B, H, W)[np.ix_(iy, ix)]
        Sbb = _xcorr(P['A1'], B2, H, W)[np.ix_(iy, ix)]
        Sab = _xcorr(P['A'], B, H, W)[np.ix_(iy, ix)]
        n = np.round(n)
        geo = (h - np.abs(dys))[:, None] * (w - np.abs(dxs))[None, :]
        ok = (n >= need) & (geo >= need)
        with np.errstate(invalid='ignore', divide='ignore'):
            cov = Sab - Sa * Sb / n
            va = np.maximum(Saa - Sa * Sa / n, 0); vb = np.maximum(Sbb - Sb * Sb / n, 0)
            r = cov / np.sqrt(va * vb + 1e-9)
        r = np.where(ok, r, -1.0)
        best = max(best, float(r.max()))
    return best

def ncc_pair(a, b, rx=None):
    return ncc_fft(probe_spec(a), gallery_spec(b), rx=rx)

def ncc_fft_arg(P, G, min_overlap=0.5):
    """Like ncc_fft but also returns (angle_index, dy, dx) of the best alignment."""
    h, w, H, W = P['h'], P['w'], P['H'], P['W']
    rx = w // 2
    dys = np.arange(-(h // 2), h // 2 + 1); dxs = np.arange(-rx, rx + 1)
    iy = dys % H; ix = dxs % W
    best, arg = -1.0, (0, 0, 0)
    need = min_overlap * h * w
    geo = (h - np.abs(dys))[:, None] * (w - np.abs(dxs))[None, :]
    for ai, (M, B, B2) in enumerate(G):
        n = np.round(_xcorr(P['A1'], M, H, W)[np.ix_(iy, ix)])
        Sa = _xcorr(P['A'], M, H, W)[np.ix_(iy, ix)]
        Saa = _xcorr(P['A2'], M, H, W)[np.ix_(iy, ix)]
        Sb = _xcorr(P['A1'], B, H, W)[np.ix_(iy, ix)]
        Sbb = _xcorr(P['A1'], B2, H, W)[np.ix_(iy, ix)]
        Sab = _xcorr(P['A'], B, H, W)[np.ix_(iy, ix)]
        ok = (n >= need) & (geo >= need)
        with np.errstate(invalid='ignore', divide='ignore'):
            cov = Sab - Sa * Sb / n
            va = np.maximum(Saa - Sa * Sa / n, 0); vb = np.maximum(Sbb - Sb * Sb / n, 0)
            r = np.where(ok, cov / np.sqrt(va * vb + 1e-9), -1.0)
        k = np.unravel_index(np.argmax(r), r.shape)
        if r[k] > best:
            best, arg = float(r[k]), (ai, int(dys[k[0]]), int(dxs[k[1]]))
    return best, arg
