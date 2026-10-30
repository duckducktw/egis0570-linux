#!/usr/bin/env bash
# Build libfprint with the Egis 0570 touch driver and install it over the
# distribution copy (original kept as a backup). Debian/Ubuntu family.
#   ./install.sh           build + install
#   ./install.sh --revert  restore the distribution library
set -euo pipefail

UPSTREAM=https://gitlab.freedesktop.org/libfprint/libfprint.git
BASE=6f9479c3d55f847c1b3769f28ceb99227f9858cf
LIBDIR=/usr/lib/x86_64-linux-gnu
LIB=libfprint-2.so.2.0.0
BACKUP=/var/backups/$LIB.orig
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${WORK:-$HOME/.cache/egis0570-linux}

if [ "${1:-}" = "--revert" ]; then
  sudo ln -sfn "$LIB" "$LIBDIR/libfprint-2.so.2"
  sudo systemctl restart fprintd || true
  echo "Reverted to the distribution libfprint. Re-enroll your fingerprints."
  exit 0
fi

sudo apt-get install -y git meson ninja-build pkg-config libglib2.0-dev \
  libgusb-dev libpixman-1-dev libnss3-dev libgudev-1.0-dev libopencv-dev \
  libcairo2-dev libudev-dev systemd-dev fprintd libpam-fprintd

mkdir -p "$WORK"
if [ ! -d "$WORK/libfprint/.git" ]; then
  git clone "$UPSTREAM" "$WORK/libfprint"
fi
cd "$WORK/libfprint"
git checkout -q -f "$BASE"
git clean -qfdx
for p in "$HERE"/patches/*.patch; do
  echo "applying $(basename "$p")"
  git apply "$p"
done

meson setup build --prefix=/usr --libdir=lib/x86_64-linux-gnu \
  -Ddoc=false -Dinstalled-tests=false -Dgtk-examples=false -Dintrospection=false
ninja -C build
meson test -C build --suite unit-tests

[ -f "$BACKUP" ] || sudo cp -a "$LIBDIR/$LIB" "$BACKUP"
sudo install -m644 "build/libfprint/$LIB" "$LIBDIR/$LIB.egis"
sudo ln -sfn "$LIB.egis" "$LIBDIR/libfprint-2.so.2"
sudo systemctl restart fprintd || true

echo
echo "Installed. Old fingerprints are not compatible:"
echo "  fprintd-delete \$USER && fprintd-enroll    (20 touches, vary the position)"
echo "Note: a distro update of libfprint replaces the library; re-run this script."
