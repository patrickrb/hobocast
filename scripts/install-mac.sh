#!/usr/bin/env bash
# One-time toolchain install for the hobocast demo on macOS (Homebrew).
#
# No hacktv, no libiio — just ffmpeg, the HackRF + RTL-SDR tools, and python.
# Idempotent. Requires Homebrew (https://brew.sh).
#
# Usage: scripts/install-mac.sh

set -euo pipefail
command -v brew >/dev/null || { echo "Homebrew required: https://brew.sh" >&2; exit 1; }

echo "=== brew install ==="
brew install ffmpeg hackrf librtlsdr python numpy mbuffer || true

echo "=== python deps ==="
"${PYTHON:-python3}" -m pip install --user numpy >/dev/null 2>&1 || true
"${PYTHON:-python3}" -c "import numpy; print('numpy', numpy.__version__)"

cat <<EOF

Install complete.
  ffmpeg / ffplay : $(command -v ffmpeg)
  hackrf_transfer : $(command -v hackrf_transfer || echo 'not found')
  rtl_sdr         : $(command -v rtl_sdr || echo 'not found')

Try it with no radio:   ./demo-loopback.sh
Transmit (HackRF):      ./demo-hackrf.sh
Receive  (RTL-SDR):     ./demo-rx.sh
EOF
