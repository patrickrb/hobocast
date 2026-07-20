#!/usr/bin/env bash
# Transmit a BOXCAR IQ file (or any video) on a loop via HackRF.
#
# hobocast equivalent of fstv's tx-file.sh. A pre-rendered .cs8 is looped
# straight off disk by hackrf_transfer -R — rock-solid, no real-time Python.
# Anything else (a .ts or a video) is rendered to IQ first.
#
# Usage:  tx-file.sh <file.cs8 | file.ts | video.mp4> [--gain N] [--amp]
#   --gain  HackRF TX VGA gain 0-47 dB (default 20).
#   --amp   Enable the +~11 dB TX amp (off by default — keep power low).
#
# Tune your receiver (RTL-SDR + the Hobocon app, or scripts/rx-rtlsdr.sh) to
# 906 MHz. Ctrl-C stops.

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_config.sh"

GAIN=20; AMP=0; INPUT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --gain) GAIN=$2; shift 2 ;;
        --amp)  AMP=1; shift ;;
        -*) echo "Unknown option: $1" >&2; exit 1 ;;
        *)  INPUT=$1; shift ;;
    esac
done
[[ -n "$INPUT" && -f "$INPUT" ]] || { echo "Usage: $(basename "$0") <file.cs8|file.ts|video> [--gain N] [--amp]" >&2; exit 1; }

need_cmd hackrf_transfer
check_hackrf

TMPDIR=""; trap '[[ -n "$TMPDIR" ]] && rm -rf "$TMPDIR"' EXIT
IQ="$INPUT"
case "$INPUT" in
    *.cs8|*.cu8) ;;                                   # already IQ
    *)                                                # render .ts / video -> IQ
        need_cmd ffmpeg
        TMPDIR=$(mktemp -d "${TMPDIR:-/tmp}/hobocast.XXXXXX")
        IQ="$TMPDIR/tx.$TXFMT"
        MUX=$(boxcar_rate)
        echo "[render] $INPUT -> $IQ"
        case "$INPUT" in
            *.ts) boxcar tx "$INPUT" "$IQ" --fmt "$TXFMT" $FEC_FLAG --packets "$PACKETS" ;;
            *)    ffmpeg_ts "$MUX" -i "$INPUT" > "$TMPDIR/x.ts"
                  boxcar tx "$TMPDIR/x.ts" "$IQ" --fmt "$TXFMT" $FEC_FLAG --packets "$PACKETS" ;;
        esac ;;
esac

AMPFLAG=$([[ $AMP -eq 1 ]] && echo "-a 1" || echo "-a 0")
cat <<EOF

  BOXCAR digital TV -> HackRF (looping from disk)
  file=$(basename "$IQ")  freq=$FREQ Hz  rate=$RATE sps  gain=$GAIN dB  amp=$([[ $AMP -eq 1 ]] && echo on || echo off)
  Tune your RTL-SDR receiver to $((FREQ/1000000)) MHz. Ctrl-C to stop.

EOF
# -R repeats the file forever; hackrf streams it from disk (no length cap).
exec hackrf_transfer -t "$IQ" -f "$FREQ" -s "$RATE" $AMPFLAG -x "$GAIN" -R
