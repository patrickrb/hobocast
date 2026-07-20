#!/usr/bin/env bash
# One command to receive the demo on an RTL-SDR and play it. hobocast has a real
# receiver (the fstv analog demo relied on a physical TV), so this closes the loop
# on a laptop: capture -> decode BOXCAR -> color + sound.
#
#   ./demo-rx.sh          # capture a few seconds, decode, play
#   ./demo-rx.sh --loop   # keep grabbing successive chunks
#
# Point a transmitter at 906 MHz first (./demo-hackrf.sh on another machine).

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec "$SCRIPT_DIR/scripts/rx-rtlsdr.sh" "$@"
