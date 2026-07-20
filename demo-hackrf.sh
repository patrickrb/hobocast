#!/usr/bin/env bash
# One command to transmit the demo on a HackRF. hobocast equivalent of fstv's
# demo-hackrf.sh — digital color+sound instead of analog B&W.
#
#   ./demo-hackrf.sh            # color bars, or media/channel/* if present
#   ./demo-hackrf.sh 30         # HackRF VGA gain override (0-47 dB)
#
# Receive with an RTL-SDR: ./demo-rx.sh   (or the Hobocon app). Ctrl-C stops.

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/scripts/_config.sh"
GAIN=${1:-20}

cat <<EOF
────────────────────────────────────────────────────────────────
  hobocast (HackRF)  ·  BOXCAR digital color TV on $((FREQ/1000000)) MHz
  Point an RTL-SDR receiver here (./demo-rx.sh).   Ctrl-C to stop.
────────────────────────────────────────────────────────────────
EOF

shopt -s nullglob
CLIPS=(media/channel/*.mp4 media/channel/*.mkv media/channel/*.mov media/channel/*.ts media/channel/*.cs8)
if (( ${#CLIPS[@]} > 0 )); then
    echo "[channel] ${#CLIPS[@]} clip(s) in media/channel — streaming on loop"
    exec "$SCRIPT_DIR/scripts/tx-hackrf.sh" "${CLIPS[@]}" --gain "$GAIN"
else
    echo "[channel] no clips in media/channel — transmitting color bars"
    echo "[tip]     drop any .mp4 into media/channel/ (or run scripts/fetch-commercials.sh)"
    exec "$SCRIPT_DIR/scripts/tx-hackrf.sh" bars --gain "$GAIN"
fi
