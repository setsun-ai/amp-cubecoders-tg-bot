# Security / Bezpieczeństwo / Безопасность / Безпека

🇬🇧 English below · 🇵🇱 [po polsku](#po-polsku) · 🇷🇺 [по-русски](#по-русски) · 🇺🇦 [українською](#українською)

## Your secrets

| Secret | Grants | Lives in |
|---|---|---|
| `TG_TOKEN` | full control of the bot | `/etc/amp-tg-bot.env` (root only, `chmod 600`) |
| `TG_FRIENDS_TOKEN` | the friends' bot (only what friends may do) | `/etc/amp-tg-bot.env` |
| `AMP_PASS` | control of your AMP servers (whatever the bot's AMP role allows) | `/etc/amp-tg-bot.env` |
| `players.db` | player names, SteamIDs, UUIDs, play times | `/var/lib/amp-tg-bot/` |

Never commit, paste or screenshot them. The repository contains no secrets and no player data; the tests use made-up names and IDs.

What the code does for you:
- Only the Telegram users in `TG_ADMINS` (by default the owner of `TG_CHAT_ID`) can use commands. Everyone else gets a refusal, and the admin is told once who wrote.
- Logs never contain the bot token, not even in Telegram errors.
- The bot runs as the unprivileged `amp` user. It changes servers through the AMP API, as its own AMP user. The only files it writes are mods (admin only) inside an instance's mod folder; removed mods go to `.tg-trash`, and archives can't write outside the game folder.
- **Friends** (`/friends`) get only the servers you assign, and on them no console, no passwords, no mods and no settings that could run code or touch the machine (Java/start arguments, paths, download URLs, ports, RCON, Steam, server type and version, backups, schedules). Player names they type are stripped of line breaks before they reach the game console, so a name can't smuggle in a second command. Every action of a friend is reported to you.
- `/update` installs only releases of this repository, runs the new code with `--selftest` first and keeps the previous version for `/rollback`.
- Player names from game logs are HTML-escaped before they are sent, so a nickname can't inject Telegram formatting or links.

- Give the bot its **own AMP user**, never your admin account, so you can revoke it alone.
- Stopping, restarting and updating a server always needs a second tap, with a warning if players are on.

**If the AMP password leaked:** change it in AMP (*Configuration → User Management*) and in `/etc/amp-tg-bot.env`.

**If the token leaked:** @BotFather → `/revoke`, put the new token into `/etc/amp-tg-bot.env`, then `systemctl restart amp-tg-bot`.

## Reporting a vulnerability

Please use **Security → Report a vulnerability** on GitHub (a private advisory), not a public issue.

---

## Po polsku

- `TG_TOKEN` daje pełną kontrolę nad botem; trzymaj go tylko w `/etc/amp-tg-bot.env` (`chmod 600`).
- `players.db` zawiera nicki, SteamID i czasy gry graczy.
- Komend mogą używać tylko osoby z `TG_ADMINS`; bot działa jako użytkownik `amp`, a zapisuje tylko mody (admin) w folderze modów instancji.
- Znajomi: tylko przydzielone serwery, bez konsoli, haseł, modów i ustawień, które mogłyby uruchomić kod albo ruszyć maszynę (argumenty Javy, ścieżki, porty, RCON, typ i wersja serwera). Każda ich akcja przychodzi do ciebie.
- **Wyciek tokena:** @BotFather → `/revoke`, nowy token do `/etc/amp-tg-bot.env`, `systemctl restart amp-tg-bot`.
- **Luki** zgłaszaj prywatnie: GitHub → *Security → Report a vulnerability*.

## По-русски

- `TG_TOKEN` даёт полный контроль над ботом; храните его только в `/etc/amp-tg-bot.env` (`chmod 600`).
- `players.db` содержит ники, SteamID и время игры игроков.
- Команды доступны только пользователям из `TG_ADMINS`; бот работает от пользователя `amp` и записывает только моды (админ) в папку модов инстанса.
- Друзья: только выданные серверы, без консоли, паролей, модов и настроек, способных запустить код или затронуть машину (аргументы Java, пути, порты, RCON, тип и версия сервера). О каждом их действии приходит сообщение.
- **Утечка токена:** @BotFather → `/revoke`, новый токен в `/etc/amp-tg-bot.env`, `systemctl restart amp-tg-bot`.
- **Уязвимости** сообщайте приватно: GitHub → *Security → Report a vulnerability*.

## Українською

- `TG_TOKEN` дає повний контроль над ботом; зберігайте його лише в `/etc/amp-tg-bot.env` (`chmod 600`).
- `players.db` містить ніки, SteamID і час гри гравців.
- Команди доступні лише користувачам із `TG_ADMINS`; бот працює від користувача `amp` і записує лише моди (адмін) у теку модів інстансу.
- Друзі: лише видані сервери, без консолі, паролів, модів і налаштувань, що можуть запустити код чи зачепити машину (аргументи Java, шляхи, порти, RCON, тип і версія сервера). Про кожну їхню дію приходить повідомлення.
- **Витік токена:** @BotFather → `/revoke`, новий токен у `/etc/amp-tg-bot.env`, `systemctl restart amp-tg-bot`.
- **Вразливості** повідомляйте приватно: GitHub → *Security → Report a vulnerability*.
