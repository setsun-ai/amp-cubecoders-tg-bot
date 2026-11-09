# Release bundle for `setsun-ai/amp-cubecoders-tg-bot` v2.8.0

This archive is an **overlay** for the original repository at v2.7.0. It does not contain the original `bot.py`, any secrets, or any player data.

## 1. Merge into the repository

```bash
git clone https://github.com/setsun-ai/amp-cubecoders-tg-bot.git
cd amp-cubecoders-tg-bot
git switch -c feat/miniapp-v2.8.0
unzip -o /path/to/amp-miniapp-v2.8.0-release.zip -d .
python3 apply_miniapp.py
python3 -m pytest -q
python3 bot.py --selftest
```

All source files must be placed in the repository root (not inside a nested folder).

## 2. Review / release

See `docs/MINIAPP.md` for tests, `v2.8.0` tag and GitHub Release steps, initial update command, Tailscale Serve / Funnel, configuration and full verification checklist. Do not tag if tests or live staging checks fail.

The archive intentionally overwrites `deploy/update.sh`; it preserves the existing `deploy/amp-tg-bot.env.example` and `tests/test_bot.py` until the integration script appends relevant settings. It never contains `/etc/amp-tg-bot.env` or databases.
