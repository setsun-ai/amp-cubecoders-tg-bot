# Changelog

## 1.9.0 (2026-10)

- **Dota 2 matches** (`/dota`): watch players through the free OpenDota API (no key). `/dota add ID` takes the Friend ID, a SteamID64 or an OpenDota/Dotabuff/Steam profile link, checks the player and warns when *Expose Public Match Data* looks off. After each new match: one message with win/loss, hero, KDA, GPM/XPM, duration, mode (ranked marked) and rank. `/dota` lists the players with 🗑. Every 10 min (`DOTA_CHECK_MINUTES`; `0` turns it off).

## 1.8.0 (2026-10)

- **Unban:** `/unban NAME` (pick the server) or 👥 Players → ♻️ (type the name) - the game's own command, `pardon` in Minecraft, `unban` elsewhere; with a confirmation, for friends on their servers too.
- **`/updates` no longer reports a stale state.** The bot refreshes the package lists itself before checking (`apt-get update` into its own folder next to the database - it runs without root), so it matches what Webmin shows after its refresh. Packages Ubuntu holds back (phased updates, kept back) are listed separately and don't count as "to install" or trigger alerts. If the refresh fails, the report says how old the system's lists are.

## 1.7.0 (2026-10)

- **⚙️ Settings** of an instance from Telegram (`/servers` → a server): every setting AMP shows in its panel, in its groups, with search; lists as buttons (difficulty, game type such as Forge or Vanilla, version...), on/off switches, typed values (world name, message of the day...). After a version or type change the bot reminds you to run the game update. Passwords stay under 🔑 and AMP's own settings (ports, logins) are left out. Friends can use it on their servers; every change is reported to the admin as "old → new".

## 1.6.0 (2026-10)

- **Friends** (`/friends`): someone who writes to the bot becomes a request with a ➕ button; you tick the servers they may manage. A friend gets their own menu (`/servers`, `/lang`, `/help`) and only those servers - start, stop, restart, game update, backup, players with kick/ban, console; no passwords, no player alerts, no history or system commands. Their every action is reported to you with their name; 🗑 removes the access.
- The admin sees the Telegram @username of whoever did something on a server.

## 1.5.0 (2026-10)

- **Less noise from AMP:** a task shows up only when it runs longer than 15 s (`AMP_TASK_MIN_SECONDS`), and routine ones such as the hourly "Updating remote sources" never do (`AMP_TASK_IGNORE`). Short tasks that fail are still reported.
- **Updates** (`/updates`): system packages from apt with security updates marked 🛡 and the important ones listed (Tailscale, playit, Webmin, AMP's package, kernel, OpenSSL, OpenSSH), "restart required" with the packages that need it, and a new AMP version. Checked every 6 h (`UPDATES_CHECK_HOURS`); a message only when something new appears.

## 1.4.0 (2026-10)

- `/servers` → a server: **💾 Backup** (AMP local backup), **👥 Players** (who is online according to AMP, with 👢 kick and 🚫 ban through the game console), **⌨️ Console** (type a command, confirm, see the server's answer) and **🔑 Password** (the game's password settings; your message with the new password is deleted from the chat right away).
- **⬆️ Game update** now updates the game itself (AMP's `UpdateApplication`, e.g. SteamCMD) instead of upgrading the AMP instance.
- Start starts the instance or, if it's already up, the game; restart restarts the game. Every action asks for confirmation (except start) and is shown with live progress.

## 1.3.0 (2026-10)

- **AMP panel on Telegram.** Running tasks of the panel and of every running instance (updates, backups, downloads – whether started from the bot or from AMP) appear as one message with a progress bar, edited in place (at most every 10 s) until it turns into ✅ done or ❌ failed.
- Servers that start, stop, go to sleep or crash are reported to the admin chat; transitional states are skipped.
- `AMP_NOTIFY=0` turns both off.

## 1.2.0 (2026-10)

- **`/servers`**: AMP instances with their state (🟢 running, 🔴 stopped, ⚫ instance off, …) and the number of players; tap one to **start, stop, restart or update** it. Everything except start asks for confirmation and warns when someone is playing. Actions taken from another chat are reported to the admin chat.
- Talks to the AMP panel API with a separate AMP user (`AMP_URL`, `AMP_USER`, `AMP_PASS`); the session is renewed automatically.
- **`--amp-test`**: checks the login, lists the instances and prints the API functions of your AMP version that the next features (backups, password, kick/ban, console) will use.

## 1.1.1 (2026-10)

- Commands live only in the Telegram **Menu** button: the button keyboard under the message field is gone (the bot removes the old one on its next start or `/help`).
- Documentation in four languages: README in English, Polish, Russian and Ukrainian; new PRIVACY.md, SECURITY.md and CONTRIBUTING.md.

## 1.1.0 (2026-10)

- **Languages**: Polish, English, Russian and Ukrainian. `/lang` shows buttons; the choice is remembered per chat. Notifications follow the language of the admin chat, and the command menu changes with it. Default: `BOT_LANG` (`pl`).
- Commands have language-neutral names: `/history`, `/player`, `/week`, `/version`, `/help`; the old Polish ones (`/historia`, `/gracz`, `/tydzien`, `/wersja`, `/pomoc`) still work.
- Strangers are turned away in the language of their Telegram app.

## 1.0.0 (2026-10)

First release.

- Telegram notifications when players join or leave AMP (CubeCoders) instances: name, play time, SteamID (Valheim), UUID (Minecraft).
- Player detection rules are read from each instance's AMP `.kvp` file, so new games usually work right away; Minecraft and Valheim extras are built in. A warning when a new game can't be recognised.
- 🆕 alert for a player the bot has never seen, 💀 deaths (Valheim, Minecraft).
- On start the bot reads the current log, so it knows who is already playing.
- Admin-only commands with a Telegram menu; strangers are refused and the admin learns once who wrote.
- Weekly summary on Sunday evening.
- Machine watch: battery below a threshold, CPU temperature, playit.gg tunnel.
- Updates from GitHub: `/update` in Telegram or `amp-tg-bot-update` in a terminal; the new version is tested before the swap and the old one is kept for `/rollback`.
