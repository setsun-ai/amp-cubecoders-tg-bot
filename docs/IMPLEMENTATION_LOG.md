# Implementation log — Telegram Mini App v2.8.0

Project: `setsun-ai/amp-cubecoders-tg-bot`, based on the upstream `main` snapshot inspected on 2026-11-09, version 2.7.0.

| Change | Why / verification |
|---|---|
| Examined README, CHANGELOG, SECURITY, bot.py, deployment, tests and CI | Preserve existing bot behavior, roles and the v2.7 release path |
| Added separate `miniapp.py` and vanilla `web/` | Keep dependencies at zero and avoid expanding the 5800-line bot further |
| Added signed Telegram `initData` verification, per-friend scopes and fixed write routing | Prevent unauthorized operations; serialize all SQLite/AMP writes in the original main loop |
| Added SQLite Dota history and replay-safe actions | Keep match collection independent from Telegram alerts and prevent duplicate operations |
| Reused existing AMP state/action API and `AmpWatcher` | Keep instance/game states distinct and continue progress/notification behavior |
| Added staged multi-file updater/rollback and bootstrap updater | Old updater moved only `bot.py`, leaving new app assets absent |
| Added admin/friend mobile views and Tailscale deployment notes | Deliver usable Dota and AMP screens while using private HTTPS by default |
| Mobile Chromium smoke test with synthetic data | Dota, AMP and instance-control screens rendered; JavaScript page error list empty |
| Python tests + syntax checks | 27 module/API tests passed locally; Node JS parse and shell syntax passed |

## Constraints / next gating checks

- The GitHub connection has no push permission to `setsun-ai/amp-cubecoders-tg-bot`; no commit, tag, release, or production deployment was made.
- The full upstream repository cannot be materialized in this isolated environment. Integration anchors were checked against the current remote `bot.py`, but **existing upstream tests / full `bot.py --selftest` were not run locally**. Run the project's complete CI in a real checkout before tagging.
- Ruff and ShellCheck were not installed in the isolated environment. Static checks here used Python `compileall`, test execution, `node --check`, and `bash -n`; the project's own CI includes Ruff and ShellCheck.
- OpenDota and AMP real accounts, bot tokens, Tailscale, physical Telegram clients, and network routing were **not** tested here; validate on a staging host before production.
- The full CubeCoders AMP panel is not cloned; this release adds common mobile operations as described in `MINIAPP.md`.
