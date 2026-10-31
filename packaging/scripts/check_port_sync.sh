#!/bin/bash
# Fail if the Ubuntu port (packaging/debian/egis0570touch.patch) carries
# different egis0570touch driver/test sources than patches/0001..00NN.
# Both sets are applied, filtered to those files, onto empty directories:
# the series creates them in 0002 and edits them later; the port adds them.
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
inc=(--include='libfprint/drivers/egis0570touch*' --include='tests/test-egis0570touch*')
mkdir -p "$T/series" "$T/port"
for p in "$R"/patches/0*.patch; do
  (cd "$T/series" && git apply "${inc[@]}" "$p")
done
(cd "$T/port" && git apply "${inc[@]}" "$R/packaging/debian/egis0570touch.patch")
n=$(find "$T/series" -type f | wc -l)
[ "$n" -gt 0 ] || { echo "no egis0570touch files in the series"; exit 1; }
diff -r "$T/series" "$T/port" && echo "port in sync ($n files)"
