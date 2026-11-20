#!/usr/bin/env bash
set -euo pipefail

PLIST_PATH="$HOME/Library/LaunchAgents/at.linz.katzenwatcher.plist"
if [ -f "$PLIST_PATH" ]; then
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  rm -f "$PLIST_PATH"
  echo "Lokaler Mac-Wächter gestoppt und entfernt."
else
  echo "Kein lokaler Mac-Wächter installiert ($PLIST_PATH nicht gefunden)."
fi
