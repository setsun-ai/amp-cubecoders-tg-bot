#!/bin/bash
# Aktualizacja amp-tg-bot z najnowszego wydania na GitHubie.
# Instalacja:  curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/deploy/update.sh \
#                -o /usr/local/bin/amp-tg-bot-update && chmod +x /usr/local/bin/amp-tg-bot-update
# Uzycie (jako root):
#   amp-tg-bot-update             - najnowsze wydanie
#   amp-tg-bot-update v1.2.0      - konkretna wersja
#   amp-tg-bot-update --rollback  - powrot do poprzedniej wersji
set -euo pipefail

REPO=setsun-ai/amp-cubecoders-tg-bot
DIR=/opt/amp-tg-bot
SERVICE=amp-tg-bot
USER_NAME=amp

restart_and_check() {
  systemctl restart "$SERVICE"
  sleep 5
  systemctl is-active --quiet "$SERVICE"
}

if [ "${1:-}" = "--rollback" ]; then
  [ -f "$DIR/bot.py.bak" ] || { echo "Brak kopii $DIR/bot.py.bak"; exit 1; }
  cp -p "$DIR/bot.py.bak" "$DIR/bot.py"
  restart_and_check && echo "Przywrocono poprzednia wersje: $(python3 "$DIR/bot.py" --version)"
  exit 0
fi

TAG=${1:-$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | grep -m1 '"tag_name"' | cut -d'"' -f4)}
[ -n "$TAG" ] || { echo "Nie udalo sie sprawdzic najnowszej wersji na GitHubie"; exit 1; }

mkdir -p "$DIR"
echo "Pobieram $TAG..."
curl -fsSL "https://raw.githubusercontent.com/$REPO/$TAG/bot.py" -o "$DIR/bot.py.new"
chown "$USER_NAME:$USER_NAME" "$DIR" "$DIR/bot.py.new"

echo "Testuje nowa wersje..."
if ! sudo -u "$USER_NAME" python3 "$DIR/bot.py.new" --selftest; then
  rm -f "$DIR/bot.py.new"
  echo "Test nie przeszedl, nic nie zmieniam."
  exit 1
fi

[ -f "$DIR/bot.py" ] && cp -p "$DIR/bot.py" "$DIR/bot.py.bak"
mv "$DIR/bot.py.new" "$DIR/bot.py"

if restart_and_check; then
  echo "Gotowe: dziala $TAG."
else
  echo "Bot nie wstal po aktualizacji, wracam do poprzedniej wersji."
  journalctl -u "$SERVICE" -n 15 --no-pager || true
  if [ -f "$DIR/bot.py.bak" ]; then
    cp -p "$DIR/bot.py.bak" "$DIR/bot.py"
    restart_and_check || true
  fi
  exit 1
fi
