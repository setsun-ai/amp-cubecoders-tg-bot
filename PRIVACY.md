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
| Friends' subscriptions (Telegram ID, server, "server up" / "someone joins") | buttons in the friends' bot | until they turn it off or lose access |
| Chat bridge: group chat ID ↔ Minecraft instance | `/bridge` | until `/bridge off` |

Everything is in one SQLite file, `/var/lib/amp-tg-bot/players.db`. It is **not encrypted**; protect the machine.

## What goes where

| Destination | What |
|---|---|
| **Telegram** | the bot's messages to your chat: player names, IDs, play times, server status; to friends who subscribed: player names on their servers (no IDs) |
| **Telegram group with a chat bridge** | the bridged Minecraft server's chat (nick and message); the other way, the group members' first names and messages go into the game chat |
| **GitHub** | only for `/update` and `/version`: an ordinary request for the latest release, no personal data |
| **Modrinth** | mod searches, and for update checks the SHA-1 of each `.jar` in `mods/` with the loader and Minecraft version |
| **Thunderstore** | mod searches and the names of installed BepInEx packages (update checks) |
| **api.steamcmd.net**, **Mojang** | the Steam app IDs of your games and an ordinary request for Minecraft's version list (game version checks) |
| **OpenDota** | the Dota account IDs you watch with `/dota` |
| **`HC_URL`** (if set, e.g. healthchecks.io) | a ping with the bot version and whether the AMP panel answers |
| **Your servers' public addresses** (🌐 Tunnel) | a status request, the same one a game client sends |

Nothing else leaves the server. The automatic checks can be turned off: `MOD_CHECK_HOURS=0`, `GAME_CHECK_HOURS=0`, `DOTA_CHECK_MINUTES=0`.

## Things to know

Player names, game IDs and IP addresses can be personal data (in the EU under the GDPR). Keep the history only as long as you need it (`RETENTION_DAYS`) and tell your players, for example in the server rules, that joins are logged.

---

## Po polsku

Bot działa na **twoim** serwerze, bez żadnej telemetrii. W `/var/lib/amp-tg-bot/players.db` (bez szyfrowania) trzyma: nicki, SteamID/UUID, publiczne IP (tylko przy bezpośrednim połączeniu), czasy wejść i wyjść, śmierci – przez `RETENTION_DAYS` (180 dni). Na zewnątrz trafiają tylko: wiadomości na Telegramie (twój czat, znajomi z subskrypcjami – same nicki, grupa z mostem czatu – czat gry w obie strony), zapytania o nową wersję do GitHuba oraz sprawdzanie modów i gier: Modrinth (SHA-1 plików modów), Thunderstore (nazwy paczek), api.steamcmd.net i Mojang (wersje gier), OpenDota (obserwowane konta Doty), `HC_URL` (wersja bota i czy AMP odpowiada) oraz zapytania o status na publiczne adresy twoich serwerów (🌐 Tunel). Automatyczne sprawdzanie wyłączysz: `MOD_CHECK_HOURS=0`, `GAME_CHECK_HOURS=0`, `DOTA_CHECK_MINUTES=0`. Nicki, ID graczy i IP mogą być danymi osobowymi w rozumieniu RODO: trzymaj je tylko tak długo, jak trzeba, i poinformuj graczy (np. w regulaminie serwera), że wejścia są zapisywane.

## По-русски

Бот работает на **вашем** сервере, без телеметрии. В `/var/lib/amp-tg-bot/players.db` (без шифрования) хранятся: ники, SteamID/UUID, публичный IP (только при прямом подключении), время входов и выходов, смерти – в течение `RETENTION_DAYS` (180 дней). Наружу уходят только: сообщения в Telegram (ваш чат, друзья с подписками – только ники, группа с мостом чата – чат игры в обе стороны), запросы новой версии к GitHub и проверки модов и игр: Modrinth (SHA-1 файлов модов), Thunderstore (названия пакетов), api.steamcmd.net и Mojang (версии игр), OpenDota (отслеживаемые аккаунты Dota), `HC_URL` (версия бота и отвечает ли AMP) и запросы статуса на публичные адреса ваших серверов (🌐 Туннель). Автопроверки выключаются: `MOD_CHECK_HOURS=0`, `GAME_CHECK_HOURS=0`, `DOTA_CHECK_MINUTES=0`. Ники, игровые ID и IP могут быть персональными данными (в ЕС – по GDPR): храните их не дольше нужного и предупредите игроков (например, в правилах сервера), что входы записываются.

## Українською

Бот працює на **вашому** сервері, без телеметрії. У `/var/lib/amp-tg-bot/players.db` (без шифрування) зберігаються: ніки, SteamID/UUID, публічна IP (лише при прямому підключенні), час входів і виходів, смерті – протягом `RETENTION_DAYS` (180 днів). Назовні йдуть лише: повідомлення в Telegram (ваш чат, друзі з підписками – лише ніки, група з мостом чату – чат гри в обидва боки), запити нової версії до GitHub і перевірки модів та ігор: Modrinth (SHA-1 файлів модів), Thunderstore (назви пакетів), api.steamcmd.net і Mojang (версії ігор), OpenDota (акаунти Dota, за якими стежите), `HC_URL` (версія бота й чи відповідає AMP) і запити статусу на публічні адреси ваших серверів (🌐 Тунель). Автоперевірки вимикаються: `MOD_CHECK_HOURS=0`, `GAME_CHECK_HOURS=0`, `DOTA_CHECK_MINUTES=0`. Ніки, ігрові ID та IP можуть бути персональними даними (в ЄС – за GDPR): зберігайте їх не довше, ніж потрібно, і попередьте гравців (наприклад, у правилах сервера), що входи записуються.
