#!/usr/bin/env bash
# Broadcast a LIVE OBS feed as digital BOXCAR TV on the HackRF.
#
#   OBS --(MPEG-TS over local UDP)--> ffmpeg (re-mux CBR) --> boxcar.cli stream
#       --> hackrf_transfer
#
# hobocast equivalent of fstv's tx-obs.sh. Start THIS first, then start OBS's
# UDP output. Because BOXCAR carries a normal MPEG-TS, OBS can feed H.264+AAC
# straight through — color and sound.
#
# Usage:  tx-obs.sh [--port N] [--gain N] [--amp] [--record [FILE]]
#
# OBS: Settings -> Output (Advanced, Recording tab):
#   Type: Custom Output (FFmpeg);  Output to URL: udp://127.0.0.1:1234?pkt_size=1316
#   Container: mpegts;  Video: h264 ~500 kbps;  Keyframe interval: 30
#   Audio: aac 64k;  Rescale: 320x240;  Video FPS: 30000/1001
# Then click Start Recording.  Ctrl-C here to stop.

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_config.sh"

PORT=1234; GAIN=20; AMP=0; RECORD=0; RECFILE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) PORT=$2; shift 2 ;;
        --gain) GAIN=$2; shift 2 ;;
        --amp)  AMP=1; shift ;;
        --record) RECORD=1; if [[ -n "${2:-}" && "${2:0:1}" != "-" ]]; then RECFILE=$2; shift 2; else shift; fi ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

need_cmd ffmpeg; need_cmd hackrf_transfer
check_hackrf
MUX=$(boxcar_rate)
AMPFLAG=$([[ $AMP -eq 1 ]] && echo "-a 1" || echo "-a 0")
IN="udp://127.0.0.1:${PORT}?fifo_size=1000000&overrun_nonfatal=1"

cat <<EOF

  OBS -> HackRF live  ·  BOXCAR digital TV on $((FREQ/1000000)) MHz
  Listening for OBS on udp://127.0.0.1:${PORT}  (Custom FFmpeg output, mpegts)
  freq=$FREQ Hz  rate=$RATE sps  gain=$GAIN dB  link=$((MUX/1000)) kbit/s
  Tune your RTL-SDR receiver. Ctrl-C to stop.

EOF

# Re-mux OBS's TS to the exact CBR the link wants, then modulate + transmit.
REC=(); if (( RECORD )); then
    RECFILE=${RECFILE:-"obs-broadcast-$(date +%Y%m%d-%H%M%S).ts"}
    echo "[rec] byte-exact copy -> $RECFILE"
    REC=(-map 0 -c copy -f mpegts "$RECFILE")
fi

ffmpeg -hide_banner -loglevel error -i "$IN" \
    "${REC[@]}" \
    -vf "scale=320:240:flags=lanczos,setsar=1,fps=30000/1001" -pix_fmt yuv420p \
    -c:v libx264 -profile:v baseline -preset veryfast -g 30 \
    -b:v "$(( MUX * 6 / 10 ))" -maxrate "$(( MUX * 6 / 10 ))" -bufsize "$(( MUX / 3 ))" \
    -c:a aac -b:a 64k -ac 1 -ar 44100 \
    -f mpegts -muxrate "$MUX" - \
  | ( cd "$REPO_ROOT" && "$PY" -m boxcar.cli stream - - --fmt "$TXFMT" $FEC_FLAG --packets "$PACKETS" ) \
  | hackrf_transfer -t - -f "$FREQ" -s "$RATE" $AMPFLAG -x "$GAIN"
