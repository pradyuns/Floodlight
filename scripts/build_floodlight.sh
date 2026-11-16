#!/bin/bash
# Builds Floodlight.app (release, ad-hoc signed) into app/.build/Floodlight.app and prints its sha256.
set -euo pipefail
cd "$(dirname "$0")/../app"
swift build -c release --product Floodlight >/dev/null
out=.build/Floodlight.app
rm -rf "$out"
mkdir -p "$out/Contents/MacOS"
cp .build/release/Floodlight "$out/Contents/MacOS/Floodlight"
cat > "$out/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>app.floodlight.Floodlight</string>
  <key>CFBundleName</key><string>Floodlight</string>
  <key>CFBundleExecutable</key><string>Floodlight</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$out" >/dev/null 2>&1
shasum -a 256 "$out/Contents/MacOS/Floodlight" | cut -d' ' -f1
