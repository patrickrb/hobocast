#!/usr/bin/env bash
# Real-time BOXCAR transmit to a HackRF: encode video live and modulate on the
# fly. hobocast equivalent of fstv's tx-hackrf.sh.
#
#   ffmpeg (H.264+AAC, CBR TS) -> boxcar.cli stream -> [mbuffer] -> hackrf_transfer
#
# Any-length video, no pre-render. The TS is muxed CBR at the BOXCAR payload
# rate so the modulator self-paces to the radio. If your CPU can't modulate in
# real time (you'll hear hackrf underruns), pre-render instead:
#   scripts/render-iq.sh <video> 0 <dur> out.cs8 && scripts/tx-file.sh out.cs8
#
# Usage:  tx-hackrf.sh [input ...] [--gain N] [--amp]
#   input   video file(s), looped forever. Omit for color bars.
#
# Tune the receiver to 906 MHz. Ctrl-C stops.

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_config.sh"

GAIN=20; AMP=0; INPUTS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --gain) GAIN=$2; shift 2 ;;
        --amp)  AMP=1; shift ;;
        bars)   shift ;;
        -*) echo "Unknown option: $1" >&2; exit 1 ;;
        *)  INPUTS+=("$1"); shift ;;
    esac
done

need_cmd ffmpeg; need_cmd hackrf_transfer
check_hackrf
MUX=$(boxcar_rate)
AMPFLAG=$([[ $AMP -eq 1 ]] && echo "-a 1" || echo "-a 0")

# Build the ffmpeg source: a concat of looping inputs, or color bars.
if (( ${#INPUTS[@]} == 0 )); then
    echo "[src] no input — transmitting color bars + 440 Hz tone"
    SRC=(-f lavfi -i "smptehdbars=size=320x240:rate=30000/1001"
         -f lavfi -i "sine=frequency=440")
else
    for f in "${INPUTS[@]}"; do [[ -f "$f" ]] || { echo "Not found: $f" >&2; exit 1; }; done
    echo "[src] ${#INPUTS[@]} input(s), looped: ${INPUTS[*]}"
    # -stream_loop -1 loops a single input; for a playlist, make a concat list.
    if (( ${#INPUTS[@]} == 1 )); then
        SRC=(-stream_loop -1 -re -i "${INPUTS[0]}")
    else
        LIST=$(mktemp "${TMPDIR:-/tmp}/hobocast-list.XXXXXX")
        trap 'rm -f "$LIST"' EXIT
        for f in "${INPUTS[@]}"; do printf "file '%s'\n" "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")" >> "$LIST"; done
        SRC=(-stream_loop -1 -re -f concat -safe 0 -i "$LIST")
    fi
fi

# Smooth pipe jitter if mbuffer is available (optional).
if command -v mbuffer >/dev/null; then BUF=(mbuffer -q -m 16M); else BUF=(cat); fi

cat <<EOF

  BOXCAR digital TV -> HackRF (real-time)
  freq=$FREQ Hz  rate=$RATE sps  gain=$GAIN dB  amp=$([[ $AMP -eq 1 ]] && echo on || echo off)
  link payload=$((MUX/1000)) kbit/s (CBR)
  Tune your RTL-SDR receiver to $((FREQ/1000000)) MHz. Ctrl-C to stop.

EOF

# For bars there's no -re yet (lavfi is unbounded); add it so it paces to realtime.
RE=(); if (( ${#INPUTS[@]} == 0 )); then RE=(-re); fi

ffmpeg -hide_banner -loglevel error "${RE[@]}" "${SRC[@]}" \
    -vf "scale=320:240:flags=lanczos,setsar=1,fps=30000/1001" -pix_fmt yuv420p \
    -c:v libx264 -profile:v baseline -preset veryfast -g 30 \
    -b:v "$(( MUX * 6 / 10 ))" -maxrate "$(( MUX * 6 / 10 ))" -bufsize "$(( MUX / 3 ))" \
    -c:a aac -b:a 64k -ac 1 -ar 44100 \
    -f mpegts -muxrate "$MUX" - \
  | ( cd "$REPO_ROOT" && "$PY" -m boxcar.cli stream - - --fmt "$TXFMT" $FEC_FLAG --packets "$PACKETS" ) \
  | "${BUF[@]}" \
  | hackrf_transfer -t - -f "$FREQ" -s "$RATE" $AMPFLAG -x "$GAIN"
