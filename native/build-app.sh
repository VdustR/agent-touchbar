#!/bin/bash
set -euo pipefail

NATIVE_ROOT=$(cd "$(dirname "$0")" && pwd)
OUTPUT=${1:?output app path is required}
swift build --package-path "$NATIVE_ROOT" -c release --arch arm64 --arch x86_64
BUILD_PATH="$NATIVE_ROOT/.build/apple/Products/Release"

rm -rf "$OUTPUT"
mkdir -p "$OUTPUT/Contents/MacOS"
cp "$NATIVE_ROOT/Info.plist" "$OUTPUT/Contents/Info.plist"
cp "$BUILD_PATH/agent-touchbar-host" "$OUTPUT/Contents/MacOS/agent-touchbar-host"
chmod 755 "$OUTPUT/Contents/MacOS/agent-touchbar-host"

echo "$OUTPUT"
