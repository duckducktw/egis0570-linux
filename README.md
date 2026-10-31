# egis0570-linux

Linux fingerprint support for the **EgisTec `1c7a:0570`** sensor in 2018–2020
Acer Swift laptops.

The stock libfprint `egis0570` driver treats this sensor as a swipe reader:
enrollment succeeds, verification almost never does. This repository is a set
of patches for libfprint that turn it into a working touch reader.

- Tested hardware: Acer Swift 3 **SF314-51** (this repo), Acer Swift 1
  **SF114-32** (keno2003, patches 0001–0004).
- Reported with the same sensor, untested: Swift 3 SF314-52, SF314-57.

## Status

Usable day to day on the tested laptop, but **experimental**:

- All numbers below come from **one person, one evening**: 20 genuine presses
  and 9 presses of a different finger. That is enough to pick a design, not
  enough to claim a false-accept rate.
- Cross-day accuracy is not measured yet.
- Not merged upstream. See [packaging/README.md](packaging/README.md).

| Driver | Genuine accepted (single press) | Different finger, best score | Verify time |
|---|---|---|---|
| Stock `egis0570` | ~0% | n/a | n/a |
| SIFT (patches 0001–0004 only) | ~18% | — | ~0.4 s |
| **This repo (0001–0008)** | **90–95%** | 0.33 (threshold 0.38, 0/9 accepted) | ~0.1 s |

## Install (Debian / Ubuntu)

```sh
git clone https://github.com/duckducktw/egis0570-linux
cd egis0570-linux
./install.sh
fprintd-delete "$USER"
fprintd-enroll          # 20 touches; move the finger a little each time
```

Revert to the distribution library: `./install.sh --revert`.

A distro update of `libfprint` overwrites the installed library. Re-run
`./install.sh` after such an update.

## Patches 0006–0008

- **0006** drops the legacy `egis0570` umockdev replay test: its recording is a
  `1c7a:0570` device, which is now owned by `egis0570touch`. Without this the
  full test suite fails on Ubuntu and Fedora. A touch-path replay test still
  needs to be recorded.
- **0007** includes `opencv2/geometry/2d.hpp` on OpenCV 5 (Arch), where
  `getRotationMatrix2D()` moved out of imgproc.
- **0008** makes verification about 4x faster with bit-identical scores
  (900/900 real probe x sample pairs unchanged; 20-sample gallery 52 ms ->
  13.5 ms on an i5-7200U). The rotation validity mask depends only on image
  size and angle, so its spectrum, overlap counts and admissible shifts are
  computed once and shared; probe-side sums/variances are computed once per
  probe and gallery-side ones from integral images, leaving one inverse FFT
  per rotation per comparison instead of three. The strongest frame is tried
  against every enrolled finger before the remaining frames.

## What patch 0005 changes

1. **Matcher: SIFT → high-pass NCC.** The sensor image is 114×57 px; SIFT finds
   almost no repeatable keypoints between presses. The frame is
   background-subtracted, high-passed, locally contrast-normalised and compared
   by normalised cross-correlation over every translation (≥50% overlap) and
   7 rotations (±15°). It is computed with FFTs (masked NCC, Padfield 2012):
   20 gallery samples take ~46 ms instead of ~750 ms.
2. **Five frames per press.** A press already yields a burst of ~10 frames.
   Five are scored and the best is kept.
3. **Adaptive templates.** A press is learned into a side store
   (`/var/lib/fprint/.egis0570-adaptive/`, max 20, oldest dropped first) only
   if all three conditions hold:
   - it scored ≥ 0.50, well above the 0.38 threshold;
   - it matches the **original** enrollment on its own, so learned samples
     cannot drift away from the real finger;
   - it is not a near-duplicate (≥ 0.85) of a stored sample.

   Disable with `EGIS0570_ADAPT=0` in the fprintd service environment.
4. **Enrollment: 12 → 20 touches.**
5. **Debug dumps.** Every frame of a press is dumped when `EGIS0570_DUMP_DIR`
   is set (off by default).

Template format bumped to v3. Older templates are rejected and need
re-enrollment.

## Tuning

Set these in a fprintd drop-in, e.g.
`/etc/systemd/system/fprintd.service.d/egis.conf`:

```ini
[Service]
Environment=EGIS0570_NCC_THRESHOLD=0.38
Environment=EGIS0570_ADAPT=1
```

## KDE Plasma lock screen

If the fingerprint is accepted but the lock screen stays locked until you press
Enter, remove `pam_kwallet5.so` from the **auth** section of
`/etc/pam.d/kde-fingerprint`. Copy `/usr/lib/pam.d/kde-fingerprint` there
first. KWallet asks for a password the fingerprint path cannot supply, and that
blocks the unlock.

## Tools

`tools/` holds the offline evaluation scripts used to choose the design:

- `fftncc.py`: Python reference for the FFT matcher.
- `xsession_eval.py`: cross-session scores.
- `adapt_sim.py`: adaptive-update simulation.

They need your own captures; set `EGIS0570_DUMP_DIR` to collect them.
**No biometric data is included in this repository.**

## Credits and license

- Touch capture path and patches 0001–0004:
  [keno2003/libfprint-egis0570](https://github.com/keno2003/libfprint-egis0570),
  upstream draft MR
  [libfprint!662](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/662).
- Original matcher scaffolding adapted by keno2003 from
  smox/libfprint-elan-04f3-0c63 (LGPL).
- Calibration discussion:
  [libfprint!548](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/548).

LGPL-2.1-or-later, same as libfprint. See `COPYING`.

## Distribution packages

Tested build recipes for Ubuntu (PPA), Fedora (COPR) and Arch (AUR) are in
[`packaging/`](packaging/README.md); 中文說明見 [`packaging/README.zh-TW.md`](packaging/README.zh-TW.md).
Rebuild everything in clean containers with `packaging/scripts/build-all.sh`.
