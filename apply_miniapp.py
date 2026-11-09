#!/usr/bin/env python3
"""One-time, assertion-checked integration into amp-cubecoders-tg-bot v2.7.0.

Run from a *local checkout of the original repository*, after copying the files
from this release bundle. It never touches the current server installation.
"""
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
BOT = ROOT / "bot.py"


def replace_once(text, before, after, why):
    n = text.count(before)
    if n != 1:
        raise RuntimeError(f"{why}: expected one anchor, found {n}")
    return text.replace(before, after, 1)


def patch_bot(text):
    text = replace_once(text, 'VERSION = "2.7.0"', 'VERSION = "2.8.0"', 'release version')
    text = replace_once(text, 'import threading\n', 'import threading\nimport miniapp\n', 'new module')
    text = replace_once(text,
                        '    db.commit()\n    return db\n\n\ndef meta_get(db, key):',
                        '    db.commit()\n    miniapp.ensure_schema(db)\n    return db\n\n\ndef meta_get(db, key):',
                        'database migration at open_db')
    text = replace_once(text, '    dota = DotaWatcher(db)\n', '''    dota = DotaWatcher(db)
    mini_ui = miniapp.MiniAppServer(sys.modules[__name__], commands, dota)
    try:
        mini_ui.start()  # opt-in: MINIAPP_URL must be configured
    except Exception as e:
        log(f"Mini App not started: {type(e).__name__}: {e}")
        mini_ui = None
''', 'web server startup')
    text = replace_once(text,
                        ('    while True:\n        now = time.time()\n'
                         '        if now - last_scan'),
                        ('    while True:\n        now = time.time()\n'
                         '        if mini_ui is not None:\n            mini_ui.drain()\n'
                         '        if now - last_scan'),
                        'web dispatch through bot main loop')
    text = replace_once(text,
                        ('                self.heroes = '
                         '{str(k): v.get("localized_name", "?") for k, v in data.items()}\n'),
                        ('                self.heroes = '
                         '{str(k): v.get("localized_name", "?") for k, v in data.items()}\n'
                         '                miniapp.store_heroes(self.db, data)\n'),
                        'hero metadata cache')
    text = replace_once(text,
                        '            self.db.execute("UPDATE dota SET matches_at=?, public=? WHERE account_id=?",\n',
                        '            miniapp.store_recent_matches(self.db, account, matches)\n'
                        '            if matches and not self.heroes:\n'
                        '                self.hero_names()\n'
                        '            self.db.execute("UPDATE dota SET matches_at=?, public=? WHERE account_id=?",\n',
                        'Dota persistence independent of notifications')
    text = replace_once(text, '                send(dota_match_text(name, m, heroes, rank))\n',
                        '                if miniapp.dota_notifications_enabled(self.db):\n'
                        '                    send(dota_match_text(name, m, heroes, rank))\n',
                        'notification toggle')
    text = replace_once(text,
                        '        self.db.commit()\n        when = ts(max(m.get("start_time", 0) for m in matches))',
                        '        self.db.commit()\n        miniapp.store_recent_matches(self.db, account, matches)\n'
                        '        when = ts(max(m.get("start_time", 0) for m in matches))',
                        'Dota initial-history backfill')
    text = replace_once(text, '            self.db.execute("DELETE FROM dota WHERE account_id=?", (acc,))\n',
                        '            self.db.execute("DELETE FROM dota WHERE account_id=?", (acc,))\n'
                        '            self.db.execute("DELETE FROM mini_dota_matches WHERE account_id=?", (acc,))\n',
                        'history deletion from Telegram')
    text = replace_once(text,
                        ('        tg_api("setMyCommands", {"commands": commands, '
                         '"scope": json.dumps({"type": "chat", "chat_id": chat_id})})\n'),
                        ('        tg_api("setMyCommands", {"commands": commands, '
                         '"scope": json.dumps({"type": "chat", "chat_id": chat_id})})\n'
                         '        if miniapp.public_url():\n'
                         '            tg_api("setChatMenuButton", {"chat_id": chat_id, "menu_button": json.dumps({\n'
                         '                "type": "web_app", "text": "📱 Panel", '
                         '"web_app": {"url": miniapp.public_url()}})})\n'),
                        'Telegram web app menu button')
    start = text.index('def install_release(tag):\n')
    stop = text.index('\ndef selftest():\n', start)
    text = text[:start] + '''def install_release(tag):
    """All release files must pass --selftest together before replacing any files."""
    return miniapp.install_release(tag, GITHUB_REPO, BOT_PATH)

''' + text[stop:]
    start = text.index('    def rollback(self, chat, lang):\n')
    stop = text.index('\n\n# ---------- glowna petla ----------', start)
    text = text[:start] + '''    def rollback(self, chat, lang):
        ok, note = miniapp.rollback_release(BOT_PATH)
        if not ok:
            send(t("rb_none", lang) + "\\n" + esc(note), chat)
            return
        meta_set(self.db, "updated_from", VERSION)
        send(t("rb_restart", lang), chat)
        self.restart = True
''' + text[stop:]
    text = replace_once(text,
                        '    print(f"OK {VERSION}")\n',
                        '''    for asset in ("index.html", "app.js", "style.css"):
        if not (miniapp.WEB_DIR / asset).is_file():
            raise SystemExit(f"Brak Mini App: {asset}")
    print(f"OK {VERSION}")
''', 'complete-install selftest')
    return text


def main():
    if not BOT.is_file() or not (ROOT / "miniapp.py").is_file():
        print("Najpierw skopiuj te pliki do checkoutu setsun-ai/amp-cubecoders-tg-bot v2.7.0.", file=sys.stderr)
        return 1
    orig = BOT.read_text(encoding="utf-8")
    if 'VERSION = "2.8.0"' in orig and 'miniapp.ensure_schema(db)' in orig:
        print("Wersja 2.8.0 juz zintegrowana; niczego nie zmieniam.")
        return 0
    try:
        patched = patch_bot(orig)
    except (ValueError, RuntimeError) as exc:
        print("Nie zmieniono plikow: " + str(exc), file=sys.stderr)
        return 2
    documents = {BOT: patched}
    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        if "docs/MINIAPP.md" not in text:
            documents[readme] = (text + "\n## Telegram Mini App (v2.8.0)\n\n"
                                 "Dota history and AMP controls in Telegram: "
                                 "[setup and security](docs/MINIAPP.md).\n")
    changelog = ROOT / "CHANGELOG.md"
    if changelog.exists():
        text = changelog.read_text(encoding="utf-8")
        if "## 2.8.0" not in text:
            documents[changelog] = text.replace("# Changelog\n", """# Changelog

## 2.8.0 (2026-11)

- Telegram Mini App: Dota match history and details, player watchlist and notification toggle.
- Mobile AMP dashboard: instance metrics, lifecycle actions, players, editable safe settings, admin console.
- Telegram initData authentication, friend instance access restrictions, idempotent commands and single-writer queue.
- Optional HTTPS via Tailscale Serve/Funnel; multi-file release update and rollback.

""", 1)
    env = ROOT / "deploy" / "amp-tg-bot.env.example"
    if env.exists():
        text = env.read_text(encoding="utf-8")
        if "MINIAPP_URL=" not in text:
            documents[env] = text + """
# Telegram Mini App (v2.8.0): optional, HTTPS address from tailscale serve/funnel status
# MINIAPP_URL=https://your-host.your-tailnet.ts.net
# MINIAPP_PORT=8765       # listens only on 127.0.0.1; do not expose directly
"""
    # Plan all writes before touching a file; all anchors were asserted above.
    for path, content in documents.items():
        path.write_text(content, encoding="utf-8")
        print(f"Zmodyfikowano: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
