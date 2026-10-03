# amp-cubecoders-tg-bot

Bot na Telegramie dla serwerów gier w [AMP (CubeCoders)](https://cubecoders.com/AMP):
powiadomienia o graczach, historia, statystyki i pilnowanie maszyny, na której stoją serwery.
Jeden plik Pythona, bez zależności spoza biblioteki standardowej.

```
🆕 NOWY GRACZ!
🟢 Alice wchodzi na serwer
🎮 Valheim (Valheim01)
🆔 SteamID: 76561198000000000
👥 Online: 1
```

## Co umie

- **Wejścia i wyjścia graczy** na wszystkich instancjach AMP, z czasem gry. Valheim: SteamID
  z linkiem do profilu. Minecraft: UUID.
- **Nowe gry bez konfiguracji**: bot bierze reguły rozpoznawania graczy z plików `.kvp`
  instancji AMP (`Console.UserJoinRegex` / `Console.UserLeaveRegex`). Gdy gra ich nie ma, admin
  dostaje ⚠️ z prośbą o przykładową linię z logu.
- **🆕 Nowy gracz**: alert, gdy wchodzi ktoś, kogo bot jeszcze nie widział.
- **💀 Śmierci** (Valheim, Minecraft) z licznikiem na dziś.
- **Podsumowanie tygodnia** w niedzielę wieczorem: czas gry, ranking, godziny największego ruchu.
- **Maszyna**: alert, gdy bateria laptopa spadnie poniżej progu, gdy CPU się przegrzewa
  albo gdy padnie tunel playit.gg.
- **Komendy** (tylko dla admina, z menu i klawiaturą):
  `/online`, `/status`, `/history [N]`, `/player NICK`, `/week`, `/lang`, `/version`, `/update`,
  `/rollback`, `/help`.
- **Języki**: polski, English, русский, українська – `/lang`, osobno dla każdego czatu.

Bot czyta logi z `AMP_Logs/AMPLOG_*.log` każdej instancji. Prawdziwe IP graczy widać tylko
przy bezpośrednim połączeniu; przez tunel (np. playit.gg) wszyscy łączą się z adresu tunelu.

## Instalacja (Linux, AMP w `/home/amp/.ampdata`)

1. Utwórz bota u [@BotFather](https://t.me/BotFather) (`/newbot`) i napisz do niego `hej`.
2. Jako root zainstaluj skrypt aktualizacji i pobierz bota:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/deploy/update.sh -o /usr/local/bin/amp-tg-bot-update
   chmod +x /usr/local/bin/amp-tg-bot-update
   mkdir -p /opt/amp-tg-bot && chown amp:amp /opt/amp-tg-bot
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/bot.py -o /opt/amp-tg-bot/bot.py
   ```

3. Zapisz token (nie będzie widoczny przy wklejaniu) i odczytaj swój chat ID:

   ```bash
   read -rsp "Token: " T && printf 'TG_TOKEN=%s\n' "$T" > /etc/amp-tg-bot.env && chmod 600 /etc/amp-tg-bot.env
   python3 /opt/amp-tg-bot/bot.py --chatid
   echo 'TG_CHAT_ID=123456789' >> /etc/amp-tg-bot.env
   python3 /opt/amp-tg-bot/bot.py --test
   ```

   Pozostałe ustawienia: [deploy/amp-tg-bot.env.example](deploy/amp-tg-bot.env.example).

4. Usługa systemd:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/deploy/amp-tg-bot.service -o /etc/systemd/system/amp-tg-bot.service
   systemctl daemon-reload && systemctl enable --now amp-tg-bot
   amp-tg-bot-update
   ```

## Aktualizacja

- Na Telegramie: `/update`. Bot pobiera najnowsze wydanie, uruchamia na nim `--selftest`,
  podmienia się i restartuje. `/rollback` wraca do poprzedniej wersji.
- W terminalu (gdy bot nie odpowiada): `amp-tg-bot-update` albo `amp-tg-bot-update --rollback`.

Konfiguracja (`/etc/amp-tg-bot.env`) i historia graczy (`/var/lib/amp-tg-bot/players.db`)
zostają nietknięte.

## Rozwój

```bash
pip install -r requirements-dev.txt
ruff check . && pytest -q
```

Wydanie: podbij `VERSION` w `bot.py`, dopisz sekcję w `CHANGELOG.md`, potem
`git tag vX.Y.Z && git push origin vX.Y.Z`. GitHub Actions sprawdzi testy i opublikuje release.

## Licencja

MIT
