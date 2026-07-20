#!/usr/bin/env bash
# Trim + encode an MP4 to a BOXCAR IQ file for looped HackRF transmit.
#
# hobocast equivalent of fstv's render-iq.sh — but there is NO cyclic DDR size
# cap here: hackrf_transfer streams the IQ from disk, so clips can be any length.
# The TS is muxed CBR at the BOXCAR payload rate so looped playback stays in sync.
#
# Usage:   render-iq.sh <input> <start_s> <dur_s> <out.cs8>
# Example: render-iq.sh media/bbb-trailer.mp4 10 30 media/bbb.cs8

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_config.sh"

if [[ $# -lt 4 ]]; then
    echo "Usage: $(basename "$0") <input> <start_s> <dur_s> <out.cs8>" >&2
    exit 1
fi
INPUT=$1; START=$2; DUR=$3; OUT=$4

need_cmd ffmpeg
[[ -f "$INPUT" ]] || { echo "Input not found: $INPUT" >&2; exit 1; }
mkdir -p "$(dirname "$OUT")"

MUX=$(boxcar_rate)
TMPDIR=$(mktemp -d "${TMPDIR:-/tmp}/hobocast.XXXXXX")
TS="$TMPDIR/clip.ts"
trap 'rm -rf "$TMPDIR"' EXIT

echo "[1/2] encode $INPUT [${START}s +${DUR}s] -> MPEG-TS @ $((MUX/1000)) kbit/s CBR"
ffmpeg_ts "$MUX" -ss "$START" -t "$DUR" -i "$INPUT" > "$TS"

echo "[2/2] modulate BOXCAR -> $OUT ($TXFMT)"
boxcar tx "$TS" "$OUT" --fmt "$TXFMT" $FEC_FLAG --packets "$PACKETS"
echo "    done: $(du -h "$OUT" | cut -f1) — loop it with: scripts/tx-file.sh $OUT"
