#!/usr/bin/env bash
# Receive BOXCAR off an RTL-SDR, decode to MPEG-TS, and play it — color + sound.
# This has no analog equivalent: the fstv demo's picture lived in an analog TV;
# hobocast's receiver is software, so a plain laptop + $30 dongle plays it back.
#
# Captures a chunk, decodes, and plays it (the pure-Python receiver isn't
# real-time at 2.4 Msps — the real-time receiver is the C++ core in the Hobocon
# app / native/). Use --loop to keep grabbing successive chunks.
#
# Usage:  rx-rtlsdr.sh [--seconds N] [--gain N] [--loop] [--keep FILE]
#   --seconds  capture length per chunk (default 6)
#   --gain     RTL-SDR tuner gain dB (default 40; 'auto' for AGC)
#   --loop     capture/decode/play repeatedly until Ctrl-C
#   --keep     also write the recovered .ts to FILE
#
# Tune the transmitter to 906 MHz first (scripts/tx-file.sh / tx-hackrf.sh).

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_config.sh"

SECS=6; GAIN=40; LOOP=0; KEEP=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --seconds) SECS=$2; shift 2 ;;
        --gain) GAIN=$2; shift 2 ;;
        --loop) LOOP=1; shift ;;
        --keep) KEEP=$2; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

need_cmd rtl_sdr; need_cmd ffplay
check_rtlsdr
GAINARG=$([[ "$GAIN" == "auto" ]] && echo "" || echo "-g $GAIN")
NSAMP=$(( RATE * SECS ))

TMPDIR=$(mktemp -d "${TMPDIR:-/tmp}/hobocast.XXXXXX")
trap 'rm -rf "$TMPDIR"' EXIT

grab_and_play() {
    local cap="$TMPDIR/cap.$RXFMT" ts="$TMPDIR/out.ts"
    echo "[rx] capturing ${SECS}s @ $((FREQ/1000000)) MHz ..."
    rtl_sdr -f "$FREQ" -s "$RATE" $GAINARG -n "$NSAMP" "$cap" 2>/dev/null
    echo "[rx] decoding BOXCAR ..."
    boxcar_decode "$cap" "$ts" || { echo "[rx] no frames decoded"; return 1; }
    [[ -n "$KEEP" ]] && cp "$ts" "$KEEP" && echo "[rx] saved -> $KEEP"
    echo "[rx] playing ..."
    ffplay -hide_banner -loglevel warning -autoexit "$ts"
}

if (( LOOP )); then
    echo "Looping capture/decode/play. Ctrl-C to stop."
    while true; do grab_and_play || true; done
else
    grab_and_play
fi
