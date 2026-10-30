#!/bin/bash
# Reproduce every distro package in clean containers (needs docker).
#   packaging/scripts/build-all.sh [deb|rpm|arch ...]   -> out/<distro>/
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
declare -A IMG=([deb]=ubuntu:26.04 [rpm]=fedora:44 [arch]=archlinux:latest)
TARGETS=("$@"); [ ${#TARGETS[@]} -eq 0 ] && TARGETS=(deb rpm arch)
for t in "${TARGETS[@]}"; do
  mkdir -p "$ROOT/out/$t"
  echo "== $t (${IMG[$t]})"
  docker run --rm -v "$ROOT":/repo:ro -v "$ROOT/out/$t":/out "${IMG[$t]}" \
    bash /repo/packaging/scripts/build_$t.sh
done
