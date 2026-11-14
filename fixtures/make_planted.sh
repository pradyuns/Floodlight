#!/bin/sh
# Plants one app bundle per display name read from stdin, identically for public and secret names.
# Usage (in the guest): make_planted.sh EXECUTABLE DEST_DIR < names.txt
# Prints counts only, so secret names never appear in output or logs.
# Names are ASCII, optionally with U+200E (left-to-right mark). Like WhatsApp's bundle, the mark is
# kept only in CFBundleDisplayName; the bundle file and CFBundleName use the name without it.
set -u
exe=$1
dest=$2
planted=0
failed=0
while IFS= read -r name; do
  [ -n "$name" ] || continue
  display=$name
  name=$(printf '%s' "$display" | LC_ALL=C tr -d '\342\200\216')
  slug=$(printf '%s' "$name" | LC_ALL=C tr -cd 'A-Za-z0-9' | tr 'A-Z' 'a-z')
  app="$dest/$name.app"
  plist="$app/Contents/Info.plist"
  if mkdir -p "$app/Contents/MacOS" \
    && cp "$exe" "$app/Contents/MacOS/$slug" \
    && plutil -create xml1 "$plist" \
    && plutil -insert CFBundleExecutable -string "$slug" "$plist" \
    && plutil -insert CFBundleIdentifier -string "org.floodlight.planted.$slug" "$plist" \
    && plutil -insert CFBundleName -string "$name" "$plist" \
    && plutil -insert CFBundleDisplayName -string "$display" "$plist" \
    && plutil -insert CFBundlePackageType -string APPL "$plist" \
    && plutil -insert CFBundleShortVersionString -string 1.0 "$plist" \
    && plutil -insert CFBundleVersion -string 1 "$plist" \
    && codesign --force --sign - "$app" >/dev/null 2>&1; then
    planted=$((planted + 1))
  else
    failed=$((failed + 1))
  fi
done
echo "planted=$planted failed=$failed"
[ "$failed" -eq 0 ]
