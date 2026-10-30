#!/bin/bash
set -euo pipefail
pacman -Syu --noconfirm --needed base-devel git pacman-contrib >/dev/null 2>&1
useradd -m b; echo "b ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/b
mkdir -p /w && cp /repo/packaging/arch/PKGBUILD /repo/patches/*.patch /w/ && chown -R b /w
cd /w
sudo -S -p '' -u b updpkgsums >/dev/null 2>&1
sudo -S -p '' -u b makepkg -s --noconfirm > /out/arch-build.log 2>&1 || { tail -40 /out/arch-build.log; exit 1; }
grep -E "^(Ok|Fail|Skipped|Expected Fail):" /out/arch-build.log
cp /w/*.pkg.tar.zst /out/
cp /w/PKGBUILD /out/PKGBUILD.withsums
sudo -S -p '' -u b makepkg --printsrcinfo > /out/SRCINFO
ls -1 /out/*.pkg.tar.zst
pacman -U --noconfirm /w/*.pkg.tar.zst >/dev/null 2>&1 && pacman -Q libfprint-egis0570touch
ldd /usr/lib/libfprint-2.so.2 | grep opencv
