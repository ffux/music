#!/bin/sh
set -eu
: "${WRAPPER_SOURCE_DIR:?Set WRAPPER_SOURCE_DIR to the reviewed wrapper-v2 checkout}"
expected=100e0a864e883e03a3ac450a780dd9563fff5271
actual=$(git -C "$WRAPPER_SOURCE_DIR" rev-parse HEAD)
[ "$actual" = "$expected" ] || { echo "Wrapper source differs from reviewed revision" >&2; exit 1; }
git -C "$WRAPPER_SOURCE_DIR" diff --quiet
git -C "$WRAPPER_SOURCE_DIR" diff --cached --quiet
# No service startup, account login, or library access.
cd "$(dirname "$0")"
unset MUSIC_WRAPPER_IMAGE
docker compose --project-name music-wrapper build music-wrapper
