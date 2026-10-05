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
- **Komendy** (tylko dla admina, pod przyciskiem *Menu* w Telegramie): `/online`, `/servers`, `/friends`, `/updates`, `/status`, `/history [N]`, `/player NICK`, `/week`, `/dota`, `/lang`, `/version`, `/update`, `/rollback`, `/help`. Stare polskie nazwy (`/historia`, `/gracz`, `/tydzien`, `/wersja`, `/pomoc`) też działają.
- **Sterowanie serwerami** (`/servers`): start, stop, restart, aktualizacja gry i backup instancji AMP, lista graczy online z kick i ban, konsola gry (z odpowiedzią serwera) i hasło serwera – wszystko przyciskami, z potwierdzeniem i ostrzeżeniem, gdy ktoś gra. Wymaga osobnego konta AMP dla bota (`AMP_URL`, `AMP_USER`, `AMP_PASS`); sprawdzisz je komendą `python3 /opt/amp-tg-bot/bot.py --amp-test`. Instancja i serwer gry to osobne rzeczy: ⏻ włącza i wyłącza instancję AMP, ▶️/⏹ uruchamiają i zatrzymują sam serwer gry (instancja zostaje włączona, więc można aktualizować), a ▶️ przy wyłączonej instancji robi jedno i drugie. Każda akcja dostaje jedną wiadomość, która śledzi ją do końca – stan, czas, pasek postępu – i kończy się ✅, ❌ z ostatnimi liniami konsoli albo ⚠️, gdy AMP czeka na kliknięcie w panelu. Drugie kliknięcie w trakcie nic nie robi.
- **Mody** (tylko admin: `/servers` → serwer → 🧩): Minecraft (Forge, NeoForge, Fabric – loader i wersja gry odczytane z serwera) z Modrinth oraz gry z BepInEx, np. Valheim, z Thunderstore – po nazwie albo linku, z wymaganymi zależnościami; albo wyślij plik (.jar albo .zip/.dll dla BepInEx, do 20 MB). Usunięte mody trafiają do folderu `.tg-trash`, nie znikają na zawsze; twoje pliki konfiguracji BepInEx nigdy nie są nadpisywane.
- **Dota 2** (`/dota`): `/dota add ID` (Friend ID z profilu w Docie albo link do profilu OpenDota/Dotabuff/Steam) - po każdym nowym meczu obserwowanego gracza dostajesz jedną wiadomość: wygrana/przegrana, bohater, KDA, GPM/XPM, tryb i ranga, z linkiem do OpenDota. Darmowe API OpenDota, bez klucza; gracz musi mieć włączone *Expose Public Match Data* (bot to sprawdza). Sprawdzane co godzinę (`DOTA_CHECK_MINUTES`, `0` = wyłączone).
- **Unban** (👥 Gracze → ♻️): wybierasz serwer, a bot wysyła komendę odbanowania gry (`pardon` w Minecrafcie, `unban` w innych). Znajomi mogą to robić na swoich serwerach.
- **Ustawienia** (`/servers` → serwer → ⚙️): wszystkie ustawienia instancji jak w panelu AMP – grupy, wyszukiwarka (np. `motd`, `difficulty`), listy jako przyciski, wł./wył. jednym kliknięciem, tekst wpisywany. Także typ i wersja gry (np. Forge albo Vanilla), z przypomnieniem o aktualizacji gry. Bez haseł (🔑 jest osobno) i ustawień samego AMP (porty, loginy).
- **Znajomi** (`/friends`): znajomy pisze do bota `/start`, ty dostajesz prośbę z przyciskiem i zaznaczasz serwery, którymi może zarządzać. Widzi tylko je: start, stop, restart, aktualizacja gry, backup, gracze (kick/ban) i konsola – bez haseł, bez powiadomień o graczach i bez historii. O każdej jego akcji dostajesz wiadomość. 🗑 zabiera dostęp. Z `TG_FRIENDS_TOKEN` znajomi korzystają z osobnego bota (ten sam proces i baza), a główny zostaje tylko twój. Znajomi nie mają konsoli ani wgrywania modów.
- **Panel AMP na Telegramie**: aktualizacje, backupy i pobieranie uruchomione z bota albo z panelu pojawiają się jako jedna wiadomość z paskiem postępu (▓▓▓▓░░░░░░ 40%), edytowana na bieżąco aż do ✅ gotowe albo ❌ błąd; start, stop i awaria serwera też trafiają na czat (`AMP_NOTIFY=0` wyłącza).
- **Aktualizacje** (`/updates`): co kilka godzin bot sprawdza pakiety systemu (apt) i pisze, gdy są łatki bezpieczeństwa albo ważne aktualizacje (Tailscale, playit, Webmin, pakiet AMP, jądro), gdy trzeba zrestartować maszynę i gdy wyszła nowa wersja AMP – tylko wtedy, gdy pojawi się coś nowego. Bot najpierw sam odświeża listy pakietów (do własnego folderu, bez roota), więc pokazuje to samo co Webmin; pakiety wstrzymywane przez Ubuntu (phased updates, kept back) są osobno, bo `apt upgrade` jeszcze ich nie zainstaluje.
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
| `TG_FRIENDS_TOKEN` | – | Drugi bot (od BotFathera) dla znajomych: oni piszą do niego, ty zarządzasz dostępem z głównego, który jest wtedy tylko twój |
| `BOT_LANG` | `pl` | domyślny język: `pl`, `en`, `ru`, `uk` (`/lang` zmienia go dla czatu) |
| `AMP_URL` | – | adres panelu AMP, np. `http://127.0.0.1:8080` (dla `/servers`) |
| `AMP_USER`, `AMP_PASS` | – | osobne konto AMP dla bota (bez 2FA) |
| `AMP_NOTIFY` | `1` | zadania AMP z postępem i zmiany stanu serwerów na Telegramie; `0` = wyłączone |
| `AMP_TASK_MIN_SECONDS` | `15` | zadania AMP krótsze niż tyle sekund nie trafiają na czat |
| `AMP_TASK_IGNORE` | `remote sources\|refreshing\|checking for` | zadania AMP, których bot nigdy nie pokazuje (wyrażenie regularne) |
| `UPDATES_CHECK_HOURS` | `6` | jak często sprawdzać aktualizacje; `0` = nigdy |
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
