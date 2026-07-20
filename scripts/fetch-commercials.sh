#!/usr/bin/env bash
# Populate media/channel/ with a playlist of 1990s TV commercials for the demo
# (demo-hackrf.sh / tx-cycle.sh play everything in that folder). Same source as
# the fstv demo — the Internet Archive "Collection of 90s Commercials".
#
# Clips are hosted by archive.org and remain their owners' copyright; kept out of
# git (see .gitignore) and fetched on demand for a local, low-power bench demo.
#
# Usage:  scripts/fetch-commercials.sh [count]   (default 14)
# Idempotent: existing clips are skipped.

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
DEST="$REPO_ROOT/media/channel"

BASE="https://archive.org/download/Collectionof90sCommercials"
EPISODES=(S01.E1 S01.E2 S01.E3 S01.E4 S01.E5 S01.E6 S01.E7 S01.E8 S01.E9 \
          S01.E10 S01.E11 S01.E12 S01.E16 S01.E29 S01.E30 S01.E31 S02.E4 S02.E8)

COUNT=${1:-14}
command -v curl >/dev/null || { echo "Missing curl" >&2; exit 1; }
mkdir -p "$DEST"

echo "Fetching up to $COUNT 90s commercial(s) into $DEST"
n=0; got=0
for ep in "${EPISODES[@]}"; do
    (( got >= COUNT )) && break
    n=$((n+1))
    out=$(printf "%s/commercial-%02d.mp4" "$DEST" "$n")
    if [[ -s "$out" ]] && (( $(wc -c < "$out") > 100000 )); then
        printf "  skip commercial-%02d.mp4 (already present)\n" "$n"; got=$((got+1)); continue
    fi
    curl -fsSL --max-time 90 -o "$out" "$BASE/90s%20Commercials%20-%20${ep}.mp4" || true
    sz=$( [[ -f "$out" ]] && wc -c < "$out" || echo 0 )
    if (( sz < 100000 )); then
        rm -f "$out"; printf "  skip %s (download failed / too small)\n" "$ep"
    else
        printf "  ok   commercial-%02d.mp4  (%d KB)\n" "$n" $((sz/1024)); got=$((got+1))
    fi
done

echo
echo "$got clip(s) ready in $DEST"
echo "Now run:  ./demo-hackrf.sh   (transmits media/channel/*.mp4 on 906 MHz)"
