#!/bin/bash
# Refuses any tool call that references macOS's hidden Spotlight/FSEvents index folders.
input=$(cat)
if printf '%s' "$input" | grep -qiE '\.Spotlight-V100|\.fseventsd'; then
  echo "BLOCKED: this project forbids touching the hidden Spotlight/FSEvents index folders (.Spotlight-V100, .fseventsd). See CLAUDE.md > Privacy." >&2
  exit 2
fi
exit 0
