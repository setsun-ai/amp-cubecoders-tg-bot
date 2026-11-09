#!/usr/bin/env bash
# Transactional updater for AMP Telegram Bot >= v2.8.0: bot.py + miniapp.py + web assets.
set -euo pipefail
REPO=setsun-ai/amp-cubecoders-tg-bot
DIR=/opt/amp-tg-bot
SERVICE=amp-tg-bot
USER_NAME=amp

if [[ "${1:-}" == "--rollback" ]]; then
  [[ -f "$DIR/miniapp.py" ]] || { echo "Brak miniapp.py; sprawdz recznie stan instalacji" >&2; exit 1; }
  sudo -u "$USER_NAME" python3 "$DIR/miniapp.py" --rollback --dir "$DIR"
  systemctl restart "$SERVICE"
  systemctl is-active --quiet "$SERVICE"
  echo "Poprzednia wersja przywrocona"
  exit 0
fi

TAG=${1:-$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | grep -m1 '"tag_name"' | cut -d'"' -f4)}
[[ "$TAG" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+([-A-Za-z0-9.]*)?$ ]] || { echo "Niepoprawny tag: $TAG" >&2; exit 1; }
[[ -f "$DIR/bot.py" ]] || { echo "Najpierw zainstaluj oryginalnego bota w $DIR" >&2; exit 1; }

TMP=$(mktemp /tmp/amp-tg-miniapp.XXXXXXXX.py)
trap 'rm -f "$TMP"' EXIT
curl -fsSL "https://raw.githubusercontent.com/$REPO/$TAG/miniapp.py" -o "$TMP"
chmod 644 "$TMP" # unprivileged amp must read the staging updater
sudo -u "$USER_NAME" python3 "$TMP" --install "$TAG" --dir "$DIR" --repo "$REPO"

if systemctl restart "$SERVICE" && systemctl is-active --quiet "$SERVICE"; then
  echo "Gotowe: $TAG. Sprawdz: systemctl status $SERVICE"
else
  echo "Nieudany restart; przywracam poprzednia wersje" >&2
  sudo -u "$USER_NAME" python3 "$DIR/miniapp.py" --rollback --dir "$DIR" || true
  systemctl restart "$SERVICE" || true
  exit 1
fi
