#!/usr/bin/env bash
# Build the fast C++ BOXCAR receiver (native/boxcar_harness). The pure-Python
# receiver is fine for tests but too slow to decode a full clip in a demo; this
# is the same DSP the phone runs, and it decodes in real time.
#
# Usage: scripts/build-native.sh   (needs g++ or clang++)

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

CXX=""
for c in "${CXX_OVERRIDE:-}" c++ g++ clang++; do
    [[ -n "$c" ]] && command -v "$c" >/dev/null && { CXX=$c; break; }
done
[[ -n "$CXX" ]] || { echo "No C++ compiler found (install g++ or clang++)." >&2; exit 1; }

OUT="$REPO_ROOT/native/boxcar_harness"
echo "Building with $CXX -> $OUT"
"$CXX" -O2 -std=c++17 \
    "$REPO_ROOT/native/harness.cpp" "$REPO_ROOT/native/boxcar_rx.cpp" \
    -o "$OUT"
echo "done. The demo RX scripts will now use it automatically."
