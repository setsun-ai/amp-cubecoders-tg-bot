# amp-cubecoders-tg-bot 🎮

[![CI](https://github.com/setsun-ai/amp-cubecoders-tg-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/setsun-ai/amp-cubecoders-tg-bot/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/setsun-ai/amp-cubecoders-tg-bot)](https://github.com/setsun-ai/amp-cubecoders-tg-bot/releases/latest)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
[![Licencja: MIT](https://img.shields.io/badge/licencja-MIT-green)](LICENSE)

🇬🇧 **[English](README.md)** · 🇷🇺 **[Русский](README.ru.md)** · 🇺🇦 **[Українська](README.uk.md)**

**Bot na Telegramie dla serwerów gier w [AMP (CubeCoders)](https://cubecoders.com/AMP).** Pisze, kto wchodzi i wychodzi, prowadzi historię graczy, wysyła podsumowanie tygodnia i pilnuje maszyny, na której stoją serwery. Jeden plik Pythona, sama biblioteka standardowa, bez wtyczek do AMP. Po polsku, angielsku, rosyjsku i ukraińsku.

```
🆕 NOWY GRACZ!
🟢 Alice wchodzi na serwer
🎮 Valheim (Valheim01)
🆔 SteamID: 76561198000000000
👥 Online: 1
```

## Co umie

- **Wejścia i wyjścia graczy** na wszystkich instancjach AMP, z czasem gry. Valheim: SteamID z linkiem do profilu. Minecraft: UUID.
- **Nowe gry bez konfiguracji**: bot bierze reguły rozpoznawania graczy, które AMP ma już w pliku `.kvp` każdej instancji (`Console.UserJoinRegex` / `Console.UserLeaveRegex`). Gdy gra ich nie ma, dostajesz ⚠️ z prośbą o przykładową linię z logu.
- **🆕 Nowy gracz**: alert, gdy wchodzi ktoś, kogo bot jeszcze nie widział.
- **💀 Śmierci** (Valheim, Minecraft) z licznikiem na dziś.
- **Podsumowanie tygodnia** w niedzielę wieczorem: czas gry na każdym serwerze, ranking, godzina największego ruchu.
- **Maszyna**: alert, gdy bateria laptopa spadnie poniżej progu, gdy CPU się przegrzewa albo gdy padnie tunel [playit.gg](https://playit.gg).
- **Komendy** (tylko dla admina, pod przyciskiem *Menu* w Telegramie): `/online`, `/status`, `/history [N]`, `/player NICK`, `/week`, `/lang`, `/version`, `/update`, `/rollback`, `/help`. Stare polskie nazwy (`/historia`, `/gracz`, `/tydzien`, `/wersja`, `/pomoc`) też działają.
- **Języki**: `/lang` z przyciskami, zapamiętywany osobno dla każdego czatu.
- **Sam się aktualizuje**: `/update` instaluje najnowsze wydanie z GitHuba po sprawdzeniu go na twoim serwerze; `/rollback` wraca do poprzedniego.

Bot czyta na bieżąco `AMP_Logs/AMPLOG_*.log` każdej instancji. Fałszywe wejścia wpisane na czacie gry (`<Bob> Alice joined the game`) są ignorowane. Prawdziwe IP graczy widać tylko przy bezpośrednim połączeniu; przez tunel (np. playit.gg) wszyscy łączą się z adresu tunelu.

## Instalacja (Linux, AMP w `/home/amp/.ampdata`)

1. Utwórz bota u [@BotFather](https://t.me/BotFather) (`/newbot`) i napisz do niego cokolwiek.
2. Jako root zainstaluj skrypt aktualizacji i pobierz bota:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/deploy/update.sh -o /usr/local/bin/amp-tg-bot-update
   chmod +x /usr/local/bin/amp-tg-bot-update
   mkdir -p /opt/amp-tg-bot && chown amp:amp /opt/amp-tg-bot
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/bot.py -o /opt/amp-tg-bot/bot.py
   ```

3. Zapisz token (przy wklejaniu go nie widać) i odczytaj swój chat ID:

   ```bash
   read -rsp "Token: " T && printf 'TG_TOKEN=%s\n' "$T" > /etc/amp-tg-bot.env && chmod 600 /etc/amp-tg-bot.env
   python3 /opt/amp-tg-bot/bot.py --chatid
   echo 'TG_CHAT_ID=123456789' >> /etc/amp-tg-bot.env
   python3 /opt/amp-tg-bot/bot.py --test
   ```

4. Usługa systemd:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/deploy/amp-tg-bot.service -o /etc/systemd/system/amp-tg-bot.service
   systemctl daemon-reload && systemctl enable --now amp-tg-bot
   amp-tg-bot-update
   ```

## Ustawienia

Wszystko w `/etc/amp-tg-bot.env` ([przykład](deploy/amp-tg-bot.env.example)); po zmianie `systemctl restart amp-tg-bot`.

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `TG_TOKEN` | – | token bota od @BotFather |
| `TG_CHAT_ID` | – | gdzie idą powiadomienia (twój prywatny czat albo grupa) |
| `TG_ADMINS` | `TG_CHAT_ID` | ID użytkowników Telegrama, którzy mogą używać komend, po przecinku |
| `BOT_LANG` | `pl` | domyślny język: `pl`, `en`, `ru`, `uk` (`/lang` zmienia go dla czatu) |
| `RETENTION_DAYS` | `180` | jak długo trzymać historię graczy |
| `BATTERY_WARN` | `45` | alert, gdy bateria spadnie poniżej tylu %; `0` wyłącza |
| `TEMP_ALERT` | `85` | alert temperatury CPU, °C |
| `PLAYIT_SERVICE` | `playit` | usługa systemd agenta playit.gg |
| `WEEKLY_DAY`, `WEEKLY_HOUR` | `6`, `20` | podsumowanie tygodnia: dzień (0 = poniedziałek) i godzina |
| `AMP_INSTANCES` | `/home/amp/.ampdata/instances` | gdzie AMP trzyma instancje |
| `DB_PATH` | `/var/lib/amp-tg-bot/players.db` | historia graczy |

## Aktualizacja

- Na Telegramie: `/update`. Bot pobiera najnowsze wydanie, uruchamia je raz z `--selftest`, podmienia się i restartuje. Gdy test nie przejdzie, zostaje stara wersja. `/rollback` przywraca poprzednią.
- W terminalu, gdy bot nie odpowiada: `amp-tg-bot-update` albo `amp-tg-bot-update --rollback`.

Plik ustawień i historia graczy zostają nietknięte.

## Rozwój

```bash
pip install -r requirements-dev.txt
ruff check . && pytest -q
```

Zobacz [CONTRIBUTING.md](CONTRIBUTING.md). Prywatność: [PRIVACY.md](PRIVACY.md). Bezpieczeństwo: [SECURITY.md](SECURITY.md).

## Licencja

[MIT](LICENSE)
