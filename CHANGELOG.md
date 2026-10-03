# Changelog

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
