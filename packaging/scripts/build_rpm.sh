#!/bin/bash
set -euo pipefail
dnf -q -y install rpm-build rpmdevtools dnf-plugins-core git >/dev/null 2>&1
rpmdev-setuptree
cd ~/rpmbuild/SRPMS && dnf -q download --source libfprint >/dev/null 2>&1
rpm -i --nodeps libfprint-*.src.rpm 2>/dev/null
cp /repo/patches/*.patch ~/rpmbuild/SOURCES/
cd ~/rpmbuild/SPECS
python3 /repo/packaging/fedora/patch_spec.py libfprint.spec
dnf -q -y builddep libfprint.spec >/dev/null 2>&1
rpmbuild -bs libfprint.spec >/dev/null 2>&1 && cp ~/rpmbuild/SRPMS/libfprint-*egis1*.src.rpm /out/
rpmbuild -bb --noclean libfprint.spec > /out/rpm-build.log 2>&1 || { tail -40 /out/rpm-build.log; exit 1; }
# run the full test suite on the built tree (Fedora's spec skips %check)
cd ~/rpmbuild/BUILD/libfprint-*-build/libfprint-v*/
B=$(dirname $(find . -name build.ninja | head -1))
dnf -q -y install umockdev python3-gobject python3-cairo appstream >/dev/null 2>&1 || true
AS_VALIDATE_NONET=1 meson test -C "$B" --timeout-multiplier 5 > /out/rpm-test.log 2>&1 || true
grep -E "^(Ok|Expected Fail|Fail|Skipped|Timeout):" /out/rpm-test.log
grep -E " FAIL " /out/rpm-test.log | head || true
# hard gate: any failed or timed-out test fails the build
if ! grep -qE "^Fail: +0 *$" /out/rpm-test.log || grep -qE "^Timeout: +[1-9]" /out/rpm-test.log; then
  echo "Fedora test suite failed"; exit 1
fi
find ~/rpmbuild/RPMS -name "*.rpm" -exec cp {} /out/ \;
ls -1 /out/*.rpm
