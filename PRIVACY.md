# Privacy / Prywatność / Приватность / Приватність

🇬🇧 English below · 🇵🇱 [po polsku](#po-polsku) · 🇷🇺 [по-русски](#по-русски) · 🇺🇦 [українською](#українською)

**Short version:** the bot runs on **your** server. The project has no servers, no analytics and no telemetry; its authors never receive any data.

## What is stored

| Data | Source | Kept |
|---|---|---|
| Player name, SteamID / UUID, public IP (only on direct connections), join and leave time, server | AMP game logs | `RETENTION_DAYS` (180 days), then deleted |
| Deaths (name, time, server) | AMP game logs | `RETENTION_DAYS` |
| Telegram ID of people who wrote to the bot without access (their name only goes to your chat) | Telegram | until you delete the database |
| Language chosen per chat | `/lang` | until you delete the database |

Everything is in one SQLite file, `/var/lib/amp-tg-bot/players.db`. It is **not encrypted**; protect the machine.

## What goes where

| Destination | What |
|---|---|
| **Telegram** | the bot's messages to your chat: player names, IDs, play times, server status |
| **GitHub** | only for `/update` and `/version`: an ordinary request for the latest release, no personal data |

Nothing else leaves the server.

## Things to know

Player names, game IDs and IP addresses can be personal data (in the EU under the GDPR). Keep the history only as long as you need it (`RETENTION_DAYS`) and tell your players, for example in the server rules, that joins are logged.

---

## Po polsku

Bot działa na **twoim** serwerze, bez żadnej telemetrii. W `/var/lib/amp-tg-bot/players.db` (bez szyfrowania) trzyma: nicki, SteamID/UUID, publiczne IP (tylko przy bezpośrednim połączeniu), czasy wejść i wyjść, śmierci – przez `RETENTION_DAYS` (180 dni). Na zewnątrz trafiają tylko wiadomości do twojego czatu na Telegramie i zapytania o nową wersję do GitHuba. Nicki, ID graczy i IP mogą być danymi osobowymi w rozumieniu RODO: trzymaj je tylko tak długo, jak trzeba, i poinformuj graczy (np. w regulaminie serwera), że wejścia są zapisywane.

## По-русски

Бот работает на **вашем** сервере, без телеметрии. В `/var/lib/amp-tg-bot/players.db` (без шифрования) хранятся: ники, SteamID/UUID, публичный IP (только при прямом подключении), время входов и выходов, смерти – в течение `RETENTION_DAYS` (180 дней). Наружу уходят только сообщения в ваш чат Telegram и запросы новой версии к GitHub. Ники, игровые ID и IP могут быть персональными данными (в ЕС – по GDPR): храните их не дольше нужного и предупредите игроков (например, в правилах сервера), что входы записываются.

## Українською

Бот працює на **вашому** сервері, без телеметрії. У `/var/lib/amp-tg-bot/players.db` (без шифрування) зберігаються: ніки, SteamID/UUID, публічна IP (лише при прямому підключенні), час входів і виходів, смерті – протягом `RETENTION_DAYS` (180 днів). Назовні йдуть лише повідомлення у ваш чат Telegram і запити нової версії до GitHub. Ніки, ігрові ID та IP можуть бути персональними даними (в ЄС – за GDPR): зберігайте їх не довше, ніж потрібно, і попередьте гравців (наприклад, у правилах сервера), що входи записуються.
