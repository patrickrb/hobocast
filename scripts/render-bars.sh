#!/usr/bin/env bash
# Render color bars + a 440 Hz tone to a BOXCAR IQ file (color AND sound — the
# whole point of going digital). hobocast equivalent of fstv's render-bars.sh.
#
# Usage:   render-bars.sh [out.cs8] [dur_s]
# Example: render-bars.sh media/bars.cs8 10

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_config.sh"

OUT=${1:-media/bars.cs8}
DUR=${2:-10}
need_cmd ffmpeg
mkdir -p "$(dirname "$OUT")"

MUX=$(boxcar_rate)
TMPDIR=$(mktemp -d "${TMPDIR:-/tmp}/hobocast.XXXXXX")
TS="$TMPDIR/bars.ts"
trap 'rm -rf "$TMPDIR"' EXIT

echo "[1/2] color bars + 440 Hz tone -> MPEG-TS @ $((MUX/1000)) kbit/s CBR (${DUR}s)"
ffmpeg_ts "$MUX" \
    -f lavfi -i "smptehdbars=size=320x240:rate=30000/1001:duration=${DUR}" \
    -f lavfi -i "sine=frequency=440:duration=${DUR}" > "$TS"

echo "[2/2] modulate BOXCAR -> $OUT ($TXFMT)"
boxcar tx "$TS" "$OUT" --fmt "$TXFMT" $FEC_FLAG --packets "$PACKETS"
echo "    done: $(du -h "$OUT" | cut -f1) — transmit with: scripts/tx-file.sh $OUT"
