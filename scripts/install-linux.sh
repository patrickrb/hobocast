#!/usr/bin/env bash
# One-time toolchain install for the hobocast demo on Linux / WSL2.
#
# Much lighter than the analog demo — no hacktv, no libiio. Just:
#   ffmpeg          encode/decode/play (ffplay) H.264+AAC
#   hackrf tools    transmit IQ (hackrf_transfer)
#   rtl-sdr tools   receive IQ (rtl_sdr)
#   python3 + numpy the BOXCAR modem itself
#   mbuffer         (optional) smooth the real-time transmit pipe
#
# Idempotent. Usage: scripts/install-linux.sh

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

echo "=== [1/3] apt install ==="
sudo apt-get update
sudo apt-get install -y \
    ffmpeg \
    hackrf libhackrf-dev \
    rtl-sdr librtlsdr-dev \
    python3 python3-numpy \
    mbuffer curl

echo "=== [2/3] python deps ==="
"${PYTHON:-python3}" -c "import numpy; print('numpy', numpy.__version__)"

echo "=== [3/3] blacklist the kernel DVB driver (so rtl_sdr can claim the dongle) ==="
BL=/etc/modprobe.d/blacklist-rtlsdr.conf
if [[ ! -f "$BL" ]]; then
    sudo tee "$BL" >/dev/null <<'EOF'
# hobocast: keep the DVB-T driver off the RTL2832U so SDR tools can use it.
blacklist dvb_usb_rtl28xxu
EOF
    echo "wrote $BL (unplug/replug the dongle, or reboot, to take effect)"
else
    echo "$BL already present"
fi

cat <<EOF

Install complete.
  ffmpeg / ffplay : $(command -v ffmpeg)
  hackrf_transfer : $(command -v hackrf_transfer || echo 'not found')
  rtl_sdr         : $(command -v rtl_sdr || echo 'not found')
  python3 numpy   : ok

Try it with no radio:   ./demo-loopback.sh
Transmit (HackRF):      ./demo-hackrf.sh
Receive  (RTL-SDR):     ./demo-rx.sh
EOF
