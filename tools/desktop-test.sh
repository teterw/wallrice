#!/usr/bin/env bash
# Try wallrice on another desktop, headless, in a throwaway container (rootless podman): nothing is
# installed on this machine. Screenshots of the themed desktop, the transitions, the picker and the
# review land in OUTDIR.
#
#   tools/desktop-test.sh xfce|sway|kde OUTDIR [WALLS_DIR]
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DESKTOP=${1:?usage: tools/desktop-test.sh xfce|sway|kde OUTDIR [WALLS_DIR]}
OUT=$(mkdir -p "${2:?OUTDIR}" && cd "$2" && pwd)
WALLS=${3:-$(xdg-user-dir PICTURES 2>/dev/null || echo "$HOME/Pictures")/walls}
IMAGE=wallrice-test-$DESKTOP

podman image exists "$IMAGE" || podman build --build-arg DESKTOP="$DESKTOP" -t "$IMAGE" \
    -f "$REPO/tools/desktops/Containerfile" "$REPO/tools/desktops"
podman run --rm --network none --security-opt label=disable \
    -v "$REPO:/src:ro" -v "$WALLS:/walls:ro" -v "$OUT:/out" \
    --timeout 420 "$IMAGE" bash /src/tools/desktops/run.sh "$DESKTOP"
