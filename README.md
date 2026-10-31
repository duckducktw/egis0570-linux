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

Usable day to day on the tested laptop, but **experimental**, and
**not a security boundary** — keep a password:

- All numbers come from **one person, one laptop** (SF314-51).
- An earlier release claimed "different finger best 0.33, threshold 0.38".
  That came from 9 presses of a single finger and was **wrong**: in the field,
  two unenrolled fingers unlocked the screen. A later collection of 41 presses
  from 4 unenrolled fingers scored up to **0.468**, and 12 of them were
  above 0.38. Patch 0010 raises the threshold to **0.49** and turns adaptive
  learning off by default.
- At 0.49 none of those 41 presses is accepted, and about **78%** of the
  owner's single presses pass. The lock screen retries without limit, so a
  second press usually unlocks. 41 impostor presses cannot establish a
  false-accept rate; they only show that 0.38 was too low.
- Not merged upstream. See [packaging/README.md](packaging/README.md).

| Driver | Genuine accepted (single press) | Unenrolled fingers (41 presses) | Verify time |
|---|---|---|---|
| Stock `egis0570` | ~0% | n/a | n/a |
| SIFT (patches 0001–0004 only) | ~18% | — | ~0.4 s |
| 0001–0009, threshold 0.38 | ~92% | max 0.468, **12 accepted** | ~0.1 s |
| **0001–0013, threshold 0.49** | **~78%** | max 0.468, 0 accepted | ~0.1 s |

## Install from a release (Ubuntu 26.04 / Fedora 44 / Arch)

Prebuilt packages are on the [Releases](https://github.com/duckducktw/egis0570-linux/releases)
page, built and tested by GitHub Actions (each distribution's full libfprint
test suite must pass):

- Ubuntu: `sudo apt install ./libfprint-2-2_*egis1*_amd64.deb`
- Fedora: `sudo dnf install ./libfprint-1.94.100-*egis1*.x86_64.rpm`
- Arch: `sudo pacman -U libfprint-egis0570touch-*.pkg.tar.zst`

Then `sudo systemctl restart fprintd` and `fprintd-enroll`.

## Build from source (Debian / Ubuntu)

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

## Patches 0006–0013

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
- **0009** captures a finger that is already resting on the sensor when a
  verification starts. The screen locker restarts verification on wake and
  after each attempt; the driver used to treat that resting finger as the
  previous touch and wait for a lift, costing seconds per unlock. Enrollment
  still requires a lift between stages. Decoded galleries (with their FFT
  spectra) are now cached across operations, keyed by the template's SHA-256
  and invalidated when the adaptive side store changes.
- **0010** safe defaults: threshold 0.38 -> 0.49, adaptive learning opt-in,
  no thermal model (see Status and the KDE section).
- **0011** removes an unused `kDefaultThreshold = 0.38` constant from the
  matcher so nobody mistakes it for the live threshold.
  `packaging/scripts/check_port_sync.sh` (run in CI) fails when the Ubuntu
  port drifts from `patches/`.
- **0012** stricter adaptive learning: learned samples accept at 0.60,
  learning needs 0.60 overall and 0.55 against the original enrollment.
- **0013** fixes "no fingerprint after resume" when a finger (or a bad first
  read) was on the sensor as it reopened: the empty-sensor reference was then
  too high and every touch read as empty. A reference that the empty sensor
  reads clearly below is now retaken automatically.

## What patch 0005 changes

1. **Matcher: SIFT → high-pass NCC.** The sensor image is 114×57 px; SIFT finds
   almost no repeatable keypoints between presses. The frame is
   background-subtracted, high-passed, locally contrast-normalised and compared
   by normalised cross-correlation over every translation (≥50% overlap) and
   7 rotations (±15°). It is computed with FFTs (masked NCC, Padfield 2012):
   20 gallery samples take ~46 ms instead of ~750 ms.
2. **Five frames per press.** A press already yields a burst of ~10 frames.
   Five are scored and the best is kept.
3. **Adaptive templates (off by default since 0010).** With
   `EGIS0570_ADAPT=1`, a press is learned into a side store
   (`/var/lib/fprint/.egis0570-adaptive/`, max 20, oldest dropped first) only
   if all three conditions hold:
   - it scored ≥ 0.60;
   - it scores ≥ 0.55 against the **original** enrollment on its own, so
     learned samples cannot drift away from the real finger;
   - it is not a near-duplicate (≥ 0.85) of a stored sample.

   Learned samples are genuine, but each one covers another part of the
   finger, which gives an unenrolled finger more chances to line up by
   coincidence. Both field false accepts came through learned samples, so
   since 0012 a press that only matches a learned sample must reach **0.60**
   (threshold + 0.11) instead of 0.49. Replaying the owner's presses in time
   order (`tools/live3_adapt.py`), unenrolled fingers reached up to 0.498
   against the grown gallery: 0/41 pass 0.60. Still opt-in.
4. **Enrollment: 12 → 20 touches.**
5. **No thermal model.** libfprint by default disables a reader after about
   3 minutes of continuous use ("too hot"). The KDE lock screen keeps
   identify running for as long as the screen is locked, so the default
   model silently disabled the reader. This sensor does not heat up.
6. **Debug dumps.** Every frame of a press is dumped when `EGIS0570_DUMP_DIR`
   is set (off by default).

Template format bumped to v3. Older templates are rejected and need
re-enrollment.

## Tuning

Set these in a fprintd drop-in, e.g.
`/etc/systemd/system/fprintd.service.d/egis.conf`:

```ini
[Service]
# default 0.49; lower = easier for you, and for other fingers too
Environment=EGIS0570_NCC_THRESHOLD=0.49
# opt-in adaptive learning (see above for the trade-off)
#Environment=EGIS0570_ADAPT=1
```

## KDE Plasma lock screen

Four separate problems, all in the lock screen rather than the driver. A
ready-made `/etc/pam.d/kde-fingerprint` for Debian/Ubuntu covering 1, 2 and 4
is in `lockscreen/pam.d/kde-fingerprint`.

1. **Fingerprint accepted but still locked until Enter.** Copy
   `/usr/lib/pam.d/kde-fingerprint` to `/etc/pam.d/` and remove
   `pam_kwallet5.so` from its **auth** section. KWallet asks for a password the
   fingerprint path cannot supply, and that blocks the unlock.
2. **Fingerprint stops working after a few tries or a minute.** In the same
   file, use `pam_fprintd.so max-tries=1000000 timeout=-1`. When a
   non-interactive PAM attempt fails, the KDE greeter does not restart it.
3. **Fingerprint does nothing on the clock screen or right after locking.**
   Stock Plasma only starts fingerprint auth when the password view is shown.
   `lockscreen/lockscreen_keys_patch.py` starts it as soon as the lock screen
   loads, so a finger works from the clock view and with the screen off. It also
   makes the key that wakes the clock view not get typed into the password box.
   It is idempotent and keeps pristine copies in `/root/*.qml.orig`. Re-run it
   after Plasma upgrades, for example from an apt hook:
   `DPkg::Post-Invoke { "/usr/local/sbin/lockscreen-keys-patch || true"; };`
4. **Fingerprint dead after suspend/resume** ([KDE bug 508247](https://bugs.kde.org/show_bug.cgi?id=508247)).
   The reader is re-enumerated on resume and fprintd restarts, so the running
   `pam_fprintd` returns `PAM_AUTHINFO_UNAVAIL`. The greeter treats that code
   as "this authenticator does not exist" and never runs it again for that
   lock. Two parts fix it: the PAM file maps every non-success to `pam_deny`
   (`[success=done default=ignore] pam_fprintd.so` then `requisite pam_deny.so`),
   and the QML patch retries a failed fingerprint attempt after 2 s.
   The retry only re-runs PAM; only a PAM success unlocks.

## sudo / polkit

Not recommended. sudo gives root, the reader has no liveness detection, and 41
impostor presses do not bound the false-accept rate. If you enable it anyway:

- `sudo pam-auth-update --enable fprintd` (Debian/Ubuntu) puts
  `[success=end default=ignore] pam_fprintd.so max-tries=1 timeout=10` before
  `pam_unix`: one press, 10 s, then the password prompt.
- Keep `max-tries` low there. The unlimited retries are only for the lock
  screen, where nobody waits at a prompt.
- `pam_fprintd` refuses remote sessions (`PAM_RHOST` set or a remote logind
  session), so sudo over ssh still asks for the password.

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
