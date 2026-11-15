# Run in the guest with bash; reads app paths on stdin and prints each app's names from its own
# bundle (Info.plist and English localizations) plus the guest locale. No python in the guest.
echo "LOCALE	$(defaults read -g AppleLocale 2>&1)"
echo "LANGS	$(defaults read -g AppleLanguages 2>&1 | tr -d ' \n')"
while IFS= read -r app; do
  info="$app/Contents/Info.plist"
  for k in CFBundleDisplayName CFBundleName; do
    v=$(plutil -extract $k raw -o - "$info" 2>/dev/null) && printf 'NAME\t%s\tInfo.plist\t%s\t%s\n' "$app" "$k" "$v"
  done
  for f in "$app"/Contents/Resources/*.lproj/InfoPlist.strings; do
    [ -f "$f" ] || continue
    lang=$(basename "$(dirname "$f")" .lproj)
    case "$lang" in en|en_GB|en-GB|en_US|en-US|English|Base|en_AU|en_IN) ;; *) continue;; esac
    for k in CFBundleDisplayName CFBundleName; do
      v=$(plutil -extract $k raw -o - "$f" 2>/dev/null) && printf 'NAME\t%s\t%s.lproj\t%s\t%s\n' "$app" "$lang" "$k" "$v"
    done
  done
  lt="$app/Contents/Resources/InfoPlist.loctable"
  if [ -f "$lt" ]; then
    for lang in en en_GB en-GB en_US en_AU; do
      for k in CFBundleDisplayName CFBundleName; do
        v=$(plutil -extract "$lang.$k" raw -o - "$lt" 2>/dev/null) && printf 'NAME\t%s\tloctable:%s\t%s\t%s\n' "$app" "$lang" "$k" "$v"
      done
    done
  fi
done
