# amp-cubecoders-tg-bot 🎮

[![CI](https://github.com/setsun-ai/amp-cubecoders-tg-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/setsun-ai/amp-cubecoders-tg-bot/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/setsun-ai/amp-cubecoders-tg-bot)](https://github.com/setsun-ai/amp-cubecoders-tg-bot/releases/latest)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

🇵🇱 **[Polski](README.pl.md)** · 🇷🇺 **[Русский](README.ru.md)** · 🇺🇦 **[Українська](README.uk.md)**

**A Telegram bot for game servers run by [AMP (CubeCoders)](https://cubecoders.com/AMP).** It tells you who joins and leaves, keeps a history of players, sends a weekly summary and watches the machine the servers run on. One Python file, standard library only, no AMP plugins. Polish, English, Russian and Ukrainian.

```
🆕 NEW PLAYER!
🟢 Alice joined the server
🎮 Valheim (Valheim01)
🆔 SteamID: 76561198000000000
👥 Online: 1
```

## Features

- **Joins and leaves** on every AMP instance, with play time. Valheim: SteamID with a link to the profile. Minecraft: UUID.
- **New games without configuration**: the bot reads the player detection rules AMP already has in each instance's `.kvp` file (`Console.UserJoinRegex` / `Console.UserLeaveRegex`). If a game has none, you get a ⚠️ asking for a sample log line.
- **🆕 New player**: an alert when someone the bot has never seen joins.
- **💀 Deaths** (Valheim, Minecraft) with a daily counter.
- **Weekly summary** on Sunday evening: play time per game, top players, the busiest hour.
- **The machine**: alerts when the laptop battery drops below a threshold, the CPU overheats or the [playit.gg](https://playit.gg) tunnel goes down.
- **Commands** (admin only, in the Telegram *Menu* button): `/online`, `/servers`, `/friends`, `/updates`, `/status`, `/history [N]`, `/player NAME`, `/unban NAME`, `/week`, `/dota`, `/lang`, `/version`, `/update`, `/rollback`, `/help`.
- **Server control** (`/servers`): start, stop, restart, game update and backup of AMP instances, the list of players online with kick and ban, the game console (with the server's answer) and the server password – all with buttons, with a confirmation and a warning when someone is playing. Needs a separate AMP user for the bot (`AMP_URL`, `AMP_USER`, `AMP_PASS`); check it with `python3 /opt/amp-tg-bot/bot.py --amp-test`. The instance and the game server are separate: ⏻ turns the AMP instance on or off, ▶️/⏹ start and stop just the game (the instance stays on, so you can update it), and ▶️ on an instance that is off does both. Every action gets one message that follows it to the end – state, time, progress bar – and ends with ✅, ❌ with the last console lines, or ⚠️ when AMP waits for a click in its panel. A second click while it runs does nothing.
- **Dota 2** (`/dota`): `/dota add ID` (Friend ID from the Dota profile or an OpenDota/Dotabuff/Steam profile link) - after every new match of a watched player you get one message: win/loss, hero, KDA, GPM/XPM, mode and rank, with a link to OpenDota. Free OpenDota API, no key; the player needs *Expose Public Match Data* on (the bot checks it). Checked every hour (`DOTA_CHECK_MINUTES`, `0` = off).
- **Unban** (`/unban NAME` or 👥 Players → ♻️): pick the server and the bot sends the game's unban command (`pardon` in Minecraft, `unban` elsewhere). Friends can do it on their servers.
- **Settings** (`/servers` → a server → ⚙️): every setting of the instance as in the AMP panel - groups, search (e.g. `motd`, `difficulty`), lists as buttons, on/off with one tap, text typed in. Game type and version (e.g. Forge or Vanilla) too, with a reminder to run the game update. Without passwords (🔑 is separate) and AMP's own settings (ports, logins).
- **Friends** (`/friends`): a friend sends `/start` to the bot, you get the request with a button and tick the servers they may manage. They see only those, with start, stop, restart, game update, backup, players (kick/ban) and the console - no passwords, no player alerts, no history. Every action they take is reported to you. 🗑 removes the access. With `TG_FRIENDS_TOKEN` friends use a separate bot (same process and database) and the main bot stays yours only. Friends can't use the console or upload mods.
- **AMP panel on Telegram**: updates, backups and downloads started from the bot or the panel show up as one message with a live progress bar (▓▓▓▓░░░░░░ 40%), edited in place until ✅ done or ❌ failed; servers that start, stop or crash are reported too (`AMP_NOTIFY=0` turns it off).
- **Updates** (`/updates`): every few hours the bot checks system packages (apt) and tells you when there are security updates or important ones (Tailscale, playit, Webmin, AMP's own package, kernel), when the machine needs a restart, and when a new AMP version is out - only when something new appears. The bot refreshes the package lists itself first (into its own folder, no root needed), so it shows what Webmin shows; packages Ubuntu holds back (phased updates, kept back) are listed separately, because `apt upgrade` won't install them yet.
- **Languages**: `/lang` with buttons, remembered per chat.
- **Self-update**: `/update` installs the newest GitHub release after testing it on your server; `/rollback` goes back.

The bot follows `AMP_Logs/AMPLOG_*.log` of each instance. Fake joins typed in the game chat (`<Bob> Alice joined the game`) are ignored. Real player IPs are only visible on direct connections; through a tunnel such as playit.gg everyone comes from the tunnel's address.

## Install (Linux, AMP in `/home/amp/.ampdata`)

1. Create a bot with [@BotFather](https://t.me/BotFather) (`/newbot`) and send it any message.
2. As root, install the update script and download the bot:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/deploy/update.sh -o /usr/local/bin/amp-tg-bot-update
   chmod +x /usr/local/bin/amp-tg-bot-update
   mkdir -p /opt/amp-tg-bot && chown amp:amp /opt/amp-tg-bot
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/bot.py -o /opt/amp-tg-bot/bot.py
   ```

3. Save the token (it stays hidden while you paste it) and find your chat ID:

   ```bash
   read -rsp "Token: " T && printf 'TG_TOKEN=%s\n' "$T" > /etc/amp-tg-bot.env && chmod 600 /etc/amp-tg-bot.env
   python3 /opt/amp-tg-bot/bot.py --chatid
   echo 'TG_CHAT_ID=123456789' >> /etc/amp-tg-bot.env
   python3 /opt/amp-tg-bot/bot.py --test
   ```

4. Run it as a systemd service:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/deploy/amp-tg-bot.service -o /etc/systemd/system/amp-tg-bot.service
   systemctl daemon-reload && systemctl enable --now amp-tg-bot
   amp-tg-bot-update
   ```

## Settings

All in `/etc/amp-tg-bot.env` ([example](deploy/amp-tg-bot.env.example)); restart with `systemctl restart amp-tg-bot` after a change.

| Variable | Default | Meaning |
|---|---|---|
| `TG_TOKEN` | – | bot token from @BotFather |
| `TG_CHAT_ID` | – | where notifications go (your private chat or a group) |
| `TG_ADMINS` | `TG_CHAT_ID` | Telegram user IDs allowed to use commands, comma-separated |
| `TG_FRIENDS_TOKEN` | – | A second bot (from BotFather) for friends: they write to it, you manage access from the main bot, which then is yours only |
| `BOT_LANG` | `pl` | default language: `pl`, `en`, `ru`, `uk` (`/lang` changes it per chat) |
| `AMP_URL` | – | AMP panel address, e.g. `http://127.0.0.1:8080` (for `/servers`) |
| `AMP_USER`, `AMP_PASS` | – | a separate AMP user for the bot (no 2FA) |
| `AMP_NOTIFY` | `1` | AMP tasks with progress and server state changes on Telegram; `0` = off |
| `AMP_TASK_MIN_SECONDS` | `15` | AMP tasks shorter than this stay silent |
| `AMP_TASK_IGNORE` | `remote sources\|refreshing\|checking for` | AMP tasks never shown (regular expression) |
| `UPDATES_CHECK_HOURS` | `6` | how often to check for updates; `0` = never |
| `RETENTION_DAYS` | `180` | how long the player history is kept |
| `BATTERY_WARN` | `45` | alert when the battery drops below this %; `0` turns it off |
| `TEMP_ALERT` | `85` | CPU temperature alert, °C |
| `PLAYIT_SERVICE` | `playit` | systemd service of the playit.gg agent |
| `WEEKLY_DAY`, `WEEKLY_HOUR` | `6`, `20` | weekly summary: day (0 = Monday) and hour |
| `AMP_INSTANCES` | `/home/amp/.ampdata/instances` | where AMP keeps its instances |
| `DB_PATH` | `/var/lib/amp-tg-bot/players.db` | player history |

## Updating

- In Telegram: `/update`. The bot downloads the newest release, runs it once with `--selftest`, swaps itself and restarts. If the test fails, the old version keeps running. `/rollback` restores the previous version.
- In a terminal, when the bot doesn't answer: `amp-tg-bot-update` or `amp-tg-bot-update --rollback`.

The settings file and the player history are never touched.

## Development

```bash
pip install -r requirements-dev.txt
ruff check . && pytest -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Privacy: [PRIVACY.md](PRIVACY.md). Security: [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
