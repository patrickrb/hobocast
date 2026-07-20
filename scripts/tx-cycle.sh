#!/usr/bin/env bash
# Rotate through a directory of clips, each transmitted for HOLD seconds, then
# on to the next, forever. hobocast equivalent of fstv's tx-cycle.sh — but any
# length clips are fine (no cyclic DDR cap). Accepts .cs8 IQ files (looped from
# disk) or videos (rendered on the fly).
#
# Usage:  tx-cycle.sh [dir=media/channel] [hold_s=30] [gain=20]

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_config.sh"

DIR=${1:-$REPO_ROOT/media/channel}
HOLD=${2:-30}
GAIN=${3:-20}
[[ -d "$DIR" ]] || { echo "Directory not found: $DIR (drop .cs8/.mp4 files in it)" >&2; exit 1; }

shopt -s nullglob
CLIPS=("$DIR"/*.cs8 "$DIR"/*.mp4 "$DIR"/*.mkv "$DIR"/*.mov "$DIR"/*.ts)
(( ${#CLIPS[@]} > 0 )) || { echo "No clips in $DIR" >&2; exit 1; }

echo "Cycling ${#CLIPS[@]} clip(s) from $DIR, ${HOLD}s each, forever. Ctrl-C to stop."
CHILD=""
cleanup() { trap - INT TERM; [[ -n "$CHILD" ]] && { kill "$CHILD" 2>/dev/null||true; wait "$CHILD" 2>/dev/null||true; }; exit 0; }
trap cleanup INT TERM

while true; do
    for clip in "${CLIPS[@]}"; do
        echo "[$(date +%H:%M:%S)] $(basename "$clip") for ${HOLD}s"
        "$_CFG_DIR/tx-file.sh" "$clip" --gain "$GAIN" &
        CHILD=$!
        sleep "$HOLD" || true
        kill "$CHILD" 2>/dev/null || true; wait "$CHILD" 2>/dev/null || true; CHILD=""
        sleep 1   # let the USB interface release before the next claim
    done
done
