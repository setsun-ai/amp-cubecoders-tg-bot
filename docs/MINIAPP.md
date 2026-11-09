# Telegram Mini App — Dota 2 + CubeCoders AMP (v2.8.0)

> **Status:** source release for the repository `setsun-ai/amp-cubecoders-tg-bot`.
> App runs inside Telegram. The Python bot retains notifications, system monitoring, AMP actions,
> existing permissions and the `/update` and `/rollback` commands.

## Features and scope

- **Dota 2:** watched players, public match summaries stored in SQLite, win/loss filters, hero names and portraits, per-player history, scoreboard and item icons for an individual match fetched on demand. Add/remove players and turn off match notifications **without disabling history collection**. Cached match details and items minimize OpenDota requests.
- **AMP:** mobile dashboard for all assigned instances: current status, CPU and RAM, online player count, instance on/off, game start/stop/restart, update, backup, players online and AMP settings. Admin has a console view and can send console commands. Progress notifications continue in Telegram through the existing `AmpWatcher`.
- **Users:** Telegram HMAC validation for the main bot and optional friends' bot; admins see all, friends only the instances granted by `/friends`, with the existing setting restrictions. Admin-only Dota and console.
- **Network:** HTTP server bound only to `127.0.0.1:8765` by default. Publish HTTPS through **Tailscale Serve** (private) or optionally **Tailscale Funnel** (internet). No direct network port opening.
- **No extra runtime dependencies:** Python standard library, SQLite and vanilla HTML/CSS/JS.

The Mini App speaks the language each user picked in the bot (`/lang`: Polish, English, Russian or Ukrainian) and follows the Telegram app's light or dark theme.

This is a mobile **companion to AMP**, not a clone of every CubeCoders tab. AMP's full file manager, schedules, restore wizard, instance creation, mod installation and live console stream remain available through the original AMP panel / Telegram bot where implemented. The Mini App console shows recent updates, not a continuous WebSocket stream.

## Release preparation (developer machine)

A one-time integration is needed because `bot.py` v2.7.0 is a monolithic file and the v2.7 updater only downloads `bot.py`.

1. Clone `https://github.com/setsun-ai/amp-cubecoders-tg-bot` into a working directory.
2. Make sure `bot.py` is **v2.7.0** and your working tree is clean; use a branch rather than editing production directly.
3. Copy the bundle files **into the repository root**, preserving `web/`, `deploy/`, `tests/` and `docs/`. Do **not** overwrite existing `tests/test_bot.py` or `deploy/amp-tg-bot.env.example`. Replace `deploy/update.sh` with the new version. The `apply_miniapp.py` script appends the new settings to the existing `.env.example`.
4. Unpack the `amp-miniapp-v2.8.0-release.zip` archive into the repository root and run the integrator once, then all checks. Replace the archive path with the location you downloaded it to:

```bash
unzip -o /path/to/amp-miniapp-v2.8.0-release.zip -d .
python3 apply_miniapp.py
python3 -m compileall -q bot.py miniapp.py apply_miniapp.py
node --check web/app.js
bash -n deploy/update.sh
python3 bot.py --selftest
python3 -m pytest -q
```

5. Inspect `git diff` and commit only the intended code, docs and tests. Never commit `/etc/amp-tg-bot.env`, databases, a bot token or AMP credentials.
6. Push the feature branch and open a pull request to `main`, where the repository's CI runs (`ruff`, all `pytest`, Python 3.11–3.13 and `shellcheck`). **Do not tag until CI passes, staging checks succeed, and the PR is merged.** Create a **GitHub Release** (not only a Git tag) because the bot's `/update` uses `releases/latest`.

Example commands (on an authenticated machine with `setsun-ai` write permission):

```bash
git add bot.py miniapp.py apply_miniapp.py web deploy/update.sh deploy/amp-tg-bot.env.example docs/MINIAPP.md docs/IMPLEMENTATION_LOG.md RELEASE_BUNDLE.md README.md CHANGELOG.md tests/test_miniapp.py
git commit -m "feat: add Telegram Mini App for AMP and Dota history"
git push -u origin feat/miniapp-v2.8.0
# Open a PR on GitHub or, with the GitHub CLI:
gh pr create --base main --head feat/miniapp-v2.8.0 --fill
# AFTER CI, staging verification and PR merge:
git switch main
git pull --ff-only
git tag v2.8.0
git push origin v2.8.0
gh release create v2.8.0 --title "v2.8.0 · Telegram Mini App" --generate-notes
```

## Installation on the host (initial upgrade from v2.7)

**Back up first**: `/opt/amp-tg-bot/bot.py`, `/etc/amp-tg-bot.env`, `/var/lib/amp-tg-bot/players.db`, and your systemd unit. Use a shell on the host as an administrator. Do not paste credentials into chat.

The Telegram `/update` of v2.7 works for the first upgrade too. It installs only `bot.py`, which starts without the Mini App, downloads the rest of its own release once (`miniapp.py`, `web/`, `deploy/`), passes the selftest and restarts. If that download fails, the bot keeps running without the panel and tells the admin to send `/update force`. A rollback from there uses the `bot.py.bak` that v2.7 left.

Over SSH, the new updater does the same in one step:

```bash
sudo curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/v2.8.0/deploy/update.sh \
    -o /usr/local/bin/amp-tg-bot-update
sudo chmod 755 /usr/local/bin/amp-tg-bot-update
sudo /usr/local/bin/amp-tg-bot-update v2.8.0
```

The new updater stages **all application files**, executes `bot.py --selftest` against the staged tree, takes a snapshot of the previous version, replaces the files and restarts systemd. It checks the service 5 seconds after the restart, and if it has failed by then it attempts a rollback. From v2.8.0 onward, `/update` and `/rollback` use the same multi-file mechanism (though manual server-side health checks are still required).

### Configure Tailscale Serve (private by default)

Confirm Tailscale is installed and connected on the server and phone, with MagicDNS/HTTPS enabled for the tailnet. As root on the server:

```bash
sudo tailscale serve --bg --https=443 http://127.0.0.1:8765
sudo tailscale serve status
```

Use the HTTPS URL shown by `tailscale serve status`. For example (not a real URL):

```text
https://my-host.my-tailnet.ts.net
```

Add to `/etc/amp-tg-bot.env` (keep existing variables unchanged):

```bash
MINIAPP_URL=https://my-host.my-tailnet.ts.net
MINIAPP_PORT=8765
```

Restart the bot to load the new environment and register the **📱 Panel** menu button:

```bash
sudo systemctl restart amp-tg-bot
sudo systemctl status amp-tg-bot --no-pager
curl -fsS http://127.0.0.1:8765/api/health
# Must return HTTP 401 unless a valid Telegram initData is supplied:
curl -i http://127.0.0.1:8765/api/me
```

Open the **main bot** in Telegram, tap **📱 Panel**, verify Dota and AMP. For a separate friends' bot, its menu is registered on existing friends' private chats during startup. Add/remove permissions through the existing `/friends` flow.

> Telegram's in-app browser must be able to reach your *private* Serve HTTPS address through the phone's Tailscale connection. Test on the actual phone. If the Telegram client cannot access Serve, switch to Funnel or use a compatible authenticated HTTPS ingress; this is not something unit tests can prove.

### Switch to Funnel (optional, public HTTPS)

Only if a public endpoint is needed:

```bash
sudo tailscale funnel --bg --https=443 http://127.0.0.1:8765
sudo tailscale funnel status
```

To return to private mode, reapply Serve for the same port:

```bash
sudo tailscale serve --bg --https=443 http://127.0.0.1:8765
sudo tailscale serve status
```

Tailscale's **last configuration wins** on the same HTTPS port. Funnel exposes the website and API to the internet, but **does not authenticate users**: the API enforces the Telegram signature and per-user permissions on every request. Do not use HTTP, expose port 8765 directly or embed `AMP_PASS` in frontend files. The HTML and CSS can be viewed publicly in Funnel mode; all privileged API operations still require valid Telegram `initData`.

## Operational constraints and safety

- **OpenDota public data only:** matches can be missing or delayed if *Expose Public Match Data* is disabled, the API is behind, or no replay is parsed. The initial backfill uses `recentMatches`; older history accumulates as new matches arrive. Detail pages are retrieved on demand and do not imply that every stat is available.
- **Polling and alerts:** `DOTA_CHECK_MINUTES` controls collection. Setting it to `0` stops collection. Use the toggle **inside the Mini App** instead if you want to silence Telegram match notifications but continue saving matches.
- **DB ownership:** both Mini App and bot use the same existing SQLite DB. The HTTP worker passes all DB/AMP actions through a queue consumed by the bot's main loop; external API lookups for details do not touch that connection. All AMP requests use the bot's existing `Amp` session and watcher.
- **Idempotency:** modifying requests carry a `request_id`; retries within 10 minutes return the same result. The watcher also blocks operations already in progress on an instance. Destructive actions require explicit confirmation and can use existing in-game player warnings where supported.
- **Friends:** Telegram friend ID and bot origin are validated. Friends cannot see Dota 2, another friend's instances, console, mods, passwords or unsafe settings. The existing `/friends` permissions are re-checked on every call.
- **Secrets:** `TG_TOKEN`, `TG_FRIENDS_TOKEN`, and AMP credentials never enter HTML/JS or logs. Public HTTP responses include only authorized data.
- **Failures:** Mini App startup failure is logged and leaves the original bot running; an AMP outage does not prevent Dota history from rendering. OpenDota detailed match display can fail independently.
- **Versioning:** after v2.8.0 the app's full release manifest must stay in sync with `RELEASE_FILES` in `miniapp.py`. Any new runtime file must be added there before tagging.

## Verification before production

Check from the actual Telegram mobile client:

1. With Serve active and Funnel inactive, Mini App opens, displays Dota history and AMP. Browser-only direct opening cannot log in. A forged/expired `initData` yields HTTP 401.
2. The friend account sees only granted instances, cannot use Dota or console, and cannot edit restricted settings.
3. Start/stop/restart respects different AMP instance/game states, warns active players where the game supports it and sends progress to Telegram.
4. Adding a Dota player immediately saves currently available recent matches; disabling match notifications does not stop updating history.
5. Force AMP offline: Dota continues to render. Force OpenDota offline: AMP still works, and the error is visible rather than a silent failure.
6. Restart the service; confirm SQLite migration is idempotent, records persist and Mini App is available again.
7. Verify `amp-tg-bot-update --rollback` on a staging instance. Confirm previous bot version starts, that no secrets were modified and the player database is intact.

## External documentation

- [Telegram Mini Apps / validating initData](https://core.telegram.org/bots/webapps)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [Tailscale Funnel](https://tailscale.com/docs/reference/tailscale-cli/funnel)
- [OpenDota API](https://opendota.apidocumentation.com/)
