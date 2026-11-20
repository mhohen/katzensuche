#!/usr/bin/env bash
set -euo pipefail

# Optionales lokales macOS-Backup via launchd (alle 5 Minuten mit echter Heim-IP).
# Nützlich, falls Willhaben irgendwann Cloud-IPs blockieren sollte.

if [ $# -lt 1 ]; then
  echo "Verwendung: $0 <DEIN_GEHEIMES_NTFY_TOPIC> [willhaben,landwirt,tieranzeigen]"
  echo "Beispiel:   $0 bauernhofkatze-linz-k8m2p9x4"
  exit 1
fi

NTFY_TOPIC="$1"
ONLY_PLATFORMS="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/at.linz.katzenwatcher.plist"
PYTHON_BIN="$(which python3)"
LOG_DIR="$SCRIPT_DIR/state/logs"
mkdir -p "$LOG_DIR"

EXTRA_ARGS=""
if [ -n "$ONLY_PLATFORMS" ]; then
  EXTRA_ARGS="      <string>--only</string>
      <string>${ONLY_PLATFORMS}</string>"
fi

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>at.linz.katzenwatcher</string>

  <key>ProgramArguments</key>
  <array>
      <string>${PYTHON_BIN}</string>
      <string>-m</string>
      <string>src.main</string>
      <string>--state-file</string>
      <string>${SCRIPT_DIR}/state/seen_local.json</string>
${EXTRA_ARGS}
  </array>

  <key>WorkingDirectory</key>
  <string>${SCRIPT_DIR}</string>

  <key>EnvironmentVariables</key>
  <dict>
      <key>NTFY_TOPIC</key>
      <string>${NTFY_TOPIC}</string>
  </dict>

  <key>StartInterval</key>
  <integer>300</integer>

  <key>RunAtLoad</key>
  <true/>

  <key>StandardOutPath</key>
  <string>${LOG_DIR}/stdout.log</string>

  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/stderr.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "Fertig! Der lokale Mac-Wächter läuft ab jetzt alle 5 Minuten."
echo "Logs: $LOG_DIR/stdout.log"
echo "Zum Stoppen: $SCRIPT_DIR/scripts/uninstall_mac_launchd.sh"
