#!/bin/bash
# Local replay of .github/workflows/release.yml: build + full test suite for
# each distro in Docker, in parallel. Output: .tmp/ci/<k>.txt, packages in .tmp/ci/<k>/
cd "$(dirname "$0")/../.." || exit 1
rm -rf .tmp/ci
for spec in deb:ubuntu:26.04:build_deb.sh rpm:fedora:44:build_rpm.sh arch:archlinux:latest:build_arch.sh; do
  IFS=: read -r k img tag s <<< "$spec"
  mkdir -p ".tmp/ci/$k"
  {
    docker run --rm -v "$PWD:/repo:ro" -v "$PWD/.tmp/ci/$k:/out" "$img:$tag" bash "/repo/packaging/scripts/$s"
    echo "exit=$?"
  } > ".tmp/ci/$k.txt" 2>&1 &
done
wait
for k in deb rpm arch; do
  echo "== $k: $(tail -n 1 .tmp/ci/$k.txt)"
  grep -E "^(Ok|Fail|Timeout):" ".tmp/ci/$k.txt"
done
