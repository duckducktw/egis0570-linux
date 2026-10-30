# Getting this into distributions

How `1c7a:0570` could work out of the box, from best to worst.

## Route 1: upstream libfprint (the real fix)

Every distribution builds libfprint from freedesktop GitLab. Once a release
containing this driver ships, Ubuntu, Fedora and Arch pick it up on their
normal schedule, with no extra packaging.

Current state:

- keno2003 has draft MR
  [!662](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/662)
  open (touch path + SIFT, i.e. patches 0001–0004). No reviewer comments yet.
- Patch 0005 should go to that MR as follow-up commits, coordinated with its
  author. A second competing MR for the same device would split review.

What maintainers will likely ask for before merging:

1. A recorded USB replay test (`tests/egis0570touch/`, umockdev), like the
   other drivers have. It needs a capture from real hardware and must not
   contain a real fingerprint image the owner is unwilling to publish.
2. A justification of the threshold with more than one person's data.
3. An answer on the OpenCV dependency. libfprint core avoids heavy deps; the
   NCC matcher only needs `GaussianBlur`, `resize`, `warpAffine` and `dft`, so
   it could be rewritten on top of pixman/FFTW or plain C to drop OpenCV.
4. A decision on adaptive templates. libfprint has no API for a driver to
   update stored prints, so the side store is a driver-private file. Upstream
   may want it off by default or designed through fprintd instead.

Realistic timeline: months. libfprint review is slow and maintainers are few.

## Route 2: distribution package (stop-gap)

- **Ubuntu PPA**: a `libfprint-2-2` build with these patches and a higher
  version number. Users run `add-apt-repository`, then `apt upgrade`.
- **Arch AUR**: `libfprint-egis0570-git` with `provides/conflicts=libfprint`.
- **Fedora COPR**: same idea.

Downside: whoever maintains the package must rebase it on every libfprint
update, or users end up running an old libfprint.

## Route 3: this repo's install.sh

Works today, but replaces a system library outside the package manager. The
next distro update of `libfprint` silently undoes it. Fine for testers, not
for "everyone".
