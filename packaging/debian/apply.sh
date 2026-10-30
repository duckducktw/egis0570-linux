#!/bin/bash
# Turn Ubuntu's libfprint source package into an egis0570touch-enabled one.
# Run inside the unpacked source dir (the one containing debian/).
#   apply.sh <egis0570touch.patch> [version-suffix]
set -euo pipefail
PATCH=$(readlink -f "$1")
SUFFIX=${2:-egis1}
[ -d debian/patches ] || { echo "run inside the unpacked libfprint source"; exit 1; }

cp "$PATCH" debian/patches/egis0570touch-add-touch-driver.patch
grep -qx egis0570touch-add-touch-driver.patch debian/patches/series ||
  echo egis0570touch-add-touch-driver.patch >> debian/patches/series

# OpenCV (core + imgproc only) is the one new build dependency
grep -q 'libopencv-imgproc-dev' debian/control ||
  sed -i 's/^\(Build-Depends:.*\)$/\1\n               libopencv-imgproc-dev,/' debian/control

# Bump version so apt prefers it over the archive build, keep epoch
CUR=$(dpkg-parsechangelog -S Version)
DIST=$(dpkg-parsechangelog -S Distribution)
NEW="${CUR}+${SUFFIX}"
{
  printf 'libfprint (%s) %s; urgency=medium\n\n' "$NEW" "$DIST"
  printf '  * Add egis0570touch driver for EgisTec 1c7a:0570 (full-frame touch\n'
  printf '    capture, NCC matcher, multi-frame verify, adaptive templates).\n'
  printf '    https://github.com/duckducktw/egis0570-linux\n\n'
  printf ' -- %s  %s\n\n' "${DEBFULLNAME:-egis0570-linux} <${DEBEMAIL:-noreply@example.invalid}>" "$(date -R)"
  cat debian/changelog
} > debian/changelog.new && mv debian/changelog.new debian/changelog
echo "prepared $NEW"
