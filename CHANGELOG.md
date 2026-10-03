# Changelog

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
