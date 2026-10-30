#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
sed -i "s/^Types: deb$/Types: deb deb-src/" /etc/apt/sources.list.d/ubuntu.sources
apt-get update -qq >/dev/null
apt-get install -y -qq dpkg-dev devscripts equivs quilt >/dev/null 2>&1
mkdir -p /b && cd /b
apt-get source -qq libfprint >/dev/null 2>&1
cd libfprint-*/
/repo/packaging/debian/apply.sh /repo/packaging/debian/egis0570touch.patch
mk-build-deps -i -r -t "apt-get -y -qq --no-install-recommends" debian/control >/dev/null 2>&1
dpkg-buildpackage -us -uc -S -d > /out/deb-src.log 2>&1 && cp ../libfprint_*egis1* /out/ 2>/dev/null || true
AS_VALIDATE_NONET=1 dpkg-buildpackage -us -uc -b -j"$(nproc)" > /out/deb-build.log 2>&1 || { tail -60 /out/deb-build.log; exit 1; }
grep -E "^(Ok|Expected Fail|Fail|Unexpected Pass|Skipped|Timeout):" /out/deb-build.log | tail -8
cp ../*.deb /out/
ls -1 /out/*.deb
