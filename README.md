# Floodlight

Floodlight is a macOS launcher built to put the app, file, folder or settings page you typed at
the top, quickly and consistently. This repository also contains a public, reproducible benchmark
that compares Floodlight with Spotlight and Raycast inside a clean macOS virtual machine. The query
lists, scoring rules and analysis plan are locked and published before any results.

## Trying Floodlight

Requires macOS 14 or later and the Xcode command line tools.

```sh
scripts/build_floodlight.sh            # builds app/.build/Floodlight.app (ad-hoc signed)
open app/.build/Floodlight.app
```

Press **Control-Space** to open the search bar, type, use the arrow keys to pick a result, Enter
to open it and Escape to close. It searches installed apps, System Settings panes, and folders and
files in your home folder (not `~/Library`). macOS asks once for access to Desktop, Documents and
Downloads. If Control-Space is already your input-source shortcut, change one of them in
System Settings → Keyboard → Keyboard Shortcuts.

Matching tries, strongest first: the exact name, the start of the name, the start of a later word,
initials, the middle of a word (apps and settings only), a keyword or alternative name, and finally
a typo (one edit for 4–7 letters, two for 8 or more; apps and settings only). Within equally strong
matches, apps come first, then the ones you open most, then shorter names.
