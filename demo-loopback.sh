#!/usr/bin/env bash
# The whole demo with NO radio: encode a clip, push it through BOXCAR, decode it
# back, and play the result. Proves the digital chain end-to-end on any laptop —
# the same bytes come out that went in. Great for a talk when you can't (or
# shouldn't) transmit.
#
#   ffmpeg -> MPEG-TS -> boxcar.cli tx -> IQ -> boxcar.cli rx -> MPEG-TS -> ffplay
#
# Usage:  ./demo-loopback.sh [input.mp4]   (color bars + tone if omitted)

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/scripts/_config.sh"

need_cmd ffmpeg
INPUT=${1:-}
MUX=$(boxcar_rate)
OUT="$REPO_ROOT/out"; mkdir -p "$OUT"
SRC="$OUT/loopback_src.ts"; IQ="$OUT/loopback.$RXFMT"; GOT="$OUT/loopback_out.ts"

cat <<EOF
────────────────────────────────────────────────────────────────
  hobocast loopback  ·  digital color TV through BOXCAR, no radio
  link payload = $((MUX/1000)) kbit/s
────────────────────────────────────────────────────────────────
EOF

echo "[1/4] encode source -> MPEG-TS"
if [[ -n "$INPUT" ]]; then
    [[ -f "$INPUT" ]] || { echo "Not found: $INPUT" >&2; exit 1; }
    ffmpeg_ts "$MUX" -t 6 -i "$INPUT" > "$SRC"
else
    ffmpeg_ts "$MUX" \
        -f lavfi -i "smptehdbars=size=320x240:rate=30000/1001:duration=6" \
        -f lavfi -i "sine=frequency=440:duration=6" > "$SRC"
fi

echo "[2/4] modulate BOXCAR  ($SRC -> $IQ)"
boxcar tx "$SRC" "$IQ" --fmt "$RXFMT" $FEC_FLAG --packets "$PACKETS"

echo "[3/4] demodulate BOXCAR  ($IQ -> $GOT)"
boxcar_decode "$IQ" "$GOT"

if cmp -s "$SRC" "$GOT"; then
    echo "[4/4] recovered byte-exact ($(wc -c < "$GOT") bytes). Playing ..."
else
    echo "[4/4] recovered with differences (channel-free, so unexpected) — playing anyway."
fi
command -v ffplay >/dev/null && ffplay -hide_banner -loglevel warning -autoexit "$GOT" \
    || echo "(install ffplay to watch; recovered stream is at $GOT)"
