#!/usr/bin/env bash
# Shared configuration + helpers for the hobocast demo scripts. Sourced, not run.
#
# hobocast transmits the digital BOXCAR waveform (color H.264 + AAC in an
# MPEG-TS) instead of analog NTSC. The transmit chain is:
#
#   ffmpeg (H.264+AAC -> MPEG-TS) -> boxcar.cli -> IQ -> hackrf_transfer
#
# and — unlike the analog demo — there is a real receiver:
#
#   rtl_sdr -> boxcar.cli rx -> MPEG-TS -> ffplay   (color + sound)
#
# Override any constant from the environment, e.g.  HOBOCAST_FREQ=915000000 ...

# --- constants -------------------------------------------------------------
FREQ=${HOBOCAST_FREQ:-906000000}   # 906 MHz, inside the 902-928 MHz ISM band
RATE=${HOBOCAST_RATE:-2400000}     # 2.4 Msps — the RTL-SDR's reliable rate
TXFMT=${HOBOCAST_TXFMT:-cs8}       # HackRF transmits signed 8-bit IQ
RXFMT=${HOBOCAST_RXFMT:-cu8}       # RTL-SDR delivers unsigned 8-bit IQ
PACKETS=${HOBOCAST_PACKETS:-7}     # TS packets per BOXCAR frame
# FEC + soft-decision + a coarse carrier search are the shipping receiver
# defaults (soft/cfo-search matter on the RX side).
FEC_FLAG=${HOBOCAST_FEC:-"--fec"}
CFO_SEARCH=${HOBOCAST_CFO_SEARCH:-30000}   # ±Hz coarse carrier search on RX

# --- repo + python ---------------------------------------------------------
_CFG_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$_CFG_DIR/.." && pwd)
PY=${PYTHON:-}
if [[ -z "$PY" ]]; then
    # Pick the first interpreter that actually runs (skips the Windows Store
    # `python3` stub, which resolves but errors out).
    for _cand in python3 python py; do
        if "$_cand" -c 'import sys' >/dev/null 2>&1; then PY=$_cand; break; fi
    done
    PY=${PY:-python3}
fi

# Run the BOXCAR CLI from the repo root (so `boxcar` imports resolve).
boxcar() { ( cd "$REPO_ROOT" && "$PY" -m boxcar.cli "$@" ); }

# The fast C++ receiver, if built (scripts/build-native.sh). Decoding a full clip
# in pure Python is too slow for a demo; this is the same DSP the phone runs.
HARNESS=""
for _h in "$REPO_ROOT/native/boxcar_harness" "$REPO_ROOT/native/boxcar_harness.exe" \
          "$REPO_ROOT/out/boxcar_harness.exe"; do
    [[ -f "$_h" ]] && { HARNESS=$_h; break; }
done

# Decode an IQ capture ($1) to a transport stream ($2). Uses the C++ harness when
# available (fast), else the pure-Python CLI (correct but slow — warns once).
_boxcar_decode_warned=0
boxcar_decode() {
    local in=$1 out=$2
    if [[ -n "$HARNESS" ]]; then
        local a=("$in" "$out")
        [[ "$RXFMT" == cs8 ]] && a+=(--cs8)
        [[ -n "$FEC_FLAG" ]] && a+=(--fec)
        a+=(--soft --cfo-search "$CFO_SEARCH" --packets "$PACKETS")
        "$HARNESS" "${a[@]}"
    else
        if [[ $_boxcar_decode_warned -eq 0 ]]; then
            echo "[note] using the pure-Python decoder (slow). For a fast demo run: scripts/build-native.sh" >&2
            _boxcar_decode_warned=1
        fi
        boxcar rx "$in" "$out" --fmt "$RXFMT" $FEC_FLAG --packets "$PACKETS" \
            --soft --cfo-search "$CFO_SEARCH"
    fi
}

# The payload (transport-stream) bitrate the link carries, for CBR muxing.
boxcar_rate() { boxcar rate $FEC_FLAG --packets "$PACKETS"; }

need_cmd() { command -v "$1" >/dev/null || { echo "Missing '$1' — run scripts/install-linux.sh (Linux) or scripts/install-mac.sh (macOS)." >&2; exit 1; }; }

# hackrf present? (non-fatal check so filename errors surface first)
check_hackrf() {
    command -v hackrf_info >/dev/null || { echo "Missing hackrf tools." >&2; exit 1; }
    if ! hackrf_info 2>/dev/null | grep -q 'Serial number'; then
        echo "ERROR: no HackRF detected. Plug it in (TX via ANT port), check: hackrf_info" >&2
        exit 1
    fi
}

# rtl-sdr present?
check_rtlsdr() {
    command -v rtl_sdr >/dev/null || { echo "Missing rtl_sdr (rtl-sdr tools)." >&2; exit 1; }
    if command -v rtl_test >/dev/null && ! rtl_test -t 2>&1 | grep -qiE 'Found|tuner'; then
        echo "WARN: no RTL-SDR detected (rtl_test found none). Plug it in." >&2
    fi
}

# ffmpeg encode of one-or-more inputs to a CBR MPEG-TS on stdout, sized to the
# BOXCAR link. $1=muxrate(bit/s); remaining args = ffmpeg input options/files.
# Video is 320x240 so a comfortable H.264 bitrate fits under the link.
ffmpeg_ts() {
    local mux=$1; shift
    local vbr=$(( mux * 6 / 10 ))   # ~60% video, leaving room for audio + TS overhead
    ffmpeg -hide_banner -loglevel error "$@" \
        -vf "scale=320:240:flags=lanczos,setsar=1,fps=30000/1001" -pix_fmt yuv420p \
        -c:v libx264 -profile:v baseline -preset veryfast -g 30 \
        -b:v "${vbr}" -maxrate "${vbr}" -bufsize "$(( vbr / 2 ))" \
        -c:a aac -b:a 64k -ac 1 -ar 44100 \
        -f mpegts -muxrate "$mux" -
}
