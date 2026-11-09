"""Telegram Mini App for amp-cubecoders-tg-bot (stdlib only).

The HTTP listener never accesses the bot's SQLite connection or AMP client.
Authenticated requests are serialized into the existing bot event loop, keeping
Telegram buttons and Mini App controls under one writer and one permission model.
"""
from __future__ import annotations

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

WEB_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_PORT = 8765
MAX_AUTH_AGE = 3600  # Telegram signs a fresh session each time the panel opens
SENSITIVE_ACTIONS = {"off", "stop", "restart", "update"}
GAME_ACTIONS = {"on", "start", "off", "stop", "restart", "update", "backup"}
WEB_FILES = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
RELEASE_FILES = ("bot.py", "miniapp.py", "web/index.html", "web/app.js", "web/style.css",
                 "deploy/update.sh", "deploy/amp-tg-bot.service", "deploy/amp-tg-bot.env.example")


class APIError(Exception):
    """`detail` is a code (bad_signature); the page shows it in the user's language from its err_<code> texts."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def public_url():
    url = os.environ.get("MINIAPP_URL", "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("MINIAPP_URL musi byc adresem HTTPS bez query/fragment")
    return url


def validate_init_data(raw: str, bot_tokens: dict[str, str], now: int | None = None):
    """Validate Telegram HMAC and expiry, without trusting initDataUnsafe."""
    if not isinstance(raw, str) or not raw or len(raw) > 8192:
        raise APIError(401, "open_in_telegram")
    try:
        pairs = urllib.parse.parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=32)
        fields = dict(pairs)
        if len(pairs) != len(fields) or not re.fullmatch(r"[a-fA-F0-9]{64}", fields.get("hash", "")):
            raise ValueError("bad field list")
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        uid = user["id"]
        if type(uid) is not int or uid <= 0:
            raise ValueError("invalid user id")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise APIError(401, "bad_session") from None
    now = int(time.time()) if now is None else now
    if auth_date > now + 30 or now - auth_date > MAX_AUTH_AGE:
        raise APIError(401, "session_expired")
    # core.telegram.org/bots/webapps: the bot-token HMAC covers every field except `hash` - `signature` included
    # (only the Ed25519 check for third parties leaves `signature` out).
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()) if k != "hash")
    for kind, token in bot_tokens.items():
        if not token:
            continue
        key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
        digest = hmac.new(key, check.encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(digest, fields["hash"].lower()):
            return {"id": uid, "user": user, "bot_kind": kind}
    raise APIError(401, "bad_signature")


def ensure_schema(db: sqlite3.Connection):
    """Idempotent migration; reuse the existing players.db and its owner."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS mini_dota_matches (
            account_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            start_time INTEGER NOT NULL DEFAULT 0,
            hero_id INTEGER NOT NULL DEFAULT 0,
            won INTEGER NOT NULL DEFAULT 0,
            payload TEXT NOT NULL,
            PRIMARY KEY(account_id, match_id)
        );
        CREATE INDEX IF NOT EXISTS mini_dota_matches_time ON mini_dota_matches(start_time DESC);
        CREATE TABLE IF NOT EXISTS mini_dota_heroes (
            hero_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL
        );
    """)


def match_won(m):
    # OpenDota player_slot 0..127 = Radiant, 128..255 = Dire.
    return bool(m.get("radiant_win")) == (int(m.get("player_slot") or 0) < 128)


def store_recent_matches(db, account_id, matches):
    """Store the public summaries independently of the notification setting."""
    if not isinstance(matches, list):
        return 0
    rows = []
    for m in matches[:200]:
        if not isinstance(m, dict):
            continue
        try:
            mid = int(m["match_id"])
            if mid <= 0:
                continue
            rows.append((int(account_id), mid, int(m.get("start_time") or 0), int(m.get("hero_id") or 0),
                         int(match_won(m)), json.dumps(m, separators=(",", ":"))))
        except (ValueError, TypeError, KeyError):
            continue
    db.executemany("INSERT INTO mini_dota_matches(account_id, match_id, start_time, hero_id, won, payload) "
                   "VALUES(?,?,?,?,?,?) ON CONFLICT(account_id,match_id) DO UPDATE SET "
                   "start_time=excluded.start_time, hero_id=excluded.hero_id, won=excluded.won, "
                   "payload=excluded.payload", rows)
    db.commit()
    return len(rows)


def store_heroes(db, heroes):
    if not isinstance(heroes, dict):
        return
    rows = []
    for k, h in heroes.items():
        if not isinstance(h, dict):
            continue
        try:
            slug = str(h.get("name") or "").removeprefix("npc_dota_hero_")
            if not re.fullmatch(r"[a-z0-9_]+", slug):
                continue
            rows.append((int(k), str(h.get("localized_name") or slug)[:90], slug))
        except (TypeError, ValueError):
            continue
    db.executemany("INSERT INTO mini_dota_heroes(hero_id, name, slug) VALUES(?,?,?) "
                   "ON CONFLICT(hero_id) DO UPDATE SET name=excluded.name, slug=excluded.slug", rows)
    db.commit()


def dota_notifications_enabled(db):
    row = db.execute("SELECT value FROM meta WHERE key='miniapp:dota_notify'").fetchone()
    return row is None or row[0] != "0"


def serialize_match(m, account_id, name, hero):
    # Keep frontend data stable despite OpenDota's nullable/missing fields.
    return {"account_id": account_id, "player_name": name, "match_id": m.get("match_id"),
            "start_time": m.get("start_time"), "duration": m.get("duration"),
            "hero_id": m.get("hero_id"), "hero_name": hero[0] if hero else f"Hero #{m.get('hero_id', '?')}",
            "hero_slug": hero[1] if hero else "", "win": match_won(m),
            "kills": m.get("kills"), "deaths": m.get("deaths"), "assists": m.get("assists"),
            "gpm": m.get("gold_per_min"), "xpm": m.get("xp_per_min"),
            "game_mode": m.get("game_mode"), "lobby_type": m.get("lobby_type")}


def match_detail_data(raw):
    """Allowlisted detail fields; don't expose arbitrary upstream content."""
    if not isinstance(raw, dict):
        raise APIError(502, "opendota_no_match_data")
    players = []
    for player in (raw.get("players") or [])[:10]:
        if not isinstance(player, dict):
            continue
        players.append({k: player.get(k) for k in (
            "account_id", "personaname", "player_slot", "hero_id", "kills", "deaths", "assists",
            "gold_per_min", "xp_per_min", "last_hits", "denies", "hero_damage", "tower_damage",
            "net_worth", "item_0", "item_1", "item_2", "item_3", "item_4", "item_5", "backpack_0",
            "backpack_1", "backpack_2", "level")})
    return {"match_id": raw.get("match_id"), "radiant_win": raw.get("radiant_win"),
            "duration": raw.get("duration"), "start_time": raw.get("start_time"),
            "radiant_score": raw.get("radiant_score"), "dire_score": raw.get("dire_score"),
            "players": players}


class MiniAppServer:
    def __init__(self, bot, commands, dota=None, web_dir=WEB_DIR, port=None):
        self.bot, self.commands, self.dota = bot, commands, dota
        self.web_dir = Path(web_dir)
        # Read after bot.load_env_file(), including when run outside systemd.
        self.port = int(os.environ.get("MINIAPP_PORT", str(DEFAULT_PORT))) if port is None else int(port)
        self.jobs = queue.Queue(maxsize=40)
        self.httpd = None
        self.thread = None
        self.replay = {}
        self.last_refresh = None
        self.detail_cache = {}
        self.detail_lock = threading.Lock()
        self.items_cache = None

    def start(self):
        if not self.port or not public_url():
            return False
        if not self.web_dir.joinpath("index.html").is_file():
            raise RuntimeError("Mini App: brak web/index.html")
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                # Never log the initData header; only status/path information.
                pass

            def do_GET(self):
                server.handle(self, "GET")

            def do_POST(self):
                server.handle(self, "POST")

            def do_HEAD(self):
                server.handle(self, "HEAD")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="miniapp-http", daemon=True)
        self.thread.start()
        self.bot.log(f"Mini App 127.0.0.1:{self.port} -> {public_url()}")
        return True

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    @staticmethod
    def respond(handler, code, payload, content_type="application/json; charset=utf-8", head=False):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Referrer-Policy", "no-referrer")
        if not content_type.startswith("text/html"):
            handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' https://telegram.org; "
                            "style-src 'self' 'unsafe-inline'; img-src 'self' https://cdn.cloudflare.steamstatic.com "
                            "https://steamcdn-a.akamaihd.net data:; connect-src 'self'; "
                            "font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'")
        handler.end_headers()
        if not head:
            try:
                handler.wfile.write(body)
            except (ConnectionError, BrokenPipeError):
                pass

    def handle(self, h, method):
        path = urllib.parse.urlsplit(h.path)
        try:
            if path.path in WEB_FILES and method in ("GET", "HEAD"):
                name = WEB_FILES[path.path]
                data = self.web_dir.joinpath(name).read_bytes()
                mime = {".html": "text/html", ".css": "text/css", ".js": "application/javascript"}[Path(name).suffix]
                return self.respond(h, 200, data, mime + "; charset=utf-8", method == "HEAD")
            if path.path == "/api/health" and method in ("GET", "HEAD"):
                return self.respond(h, 200, {"ok": True}, head=method == "HEAD")
            if not path.path.startswith("/api/"):
                raise APIError(404, "not_found")
            if method == "HEAD":
                raise APIError(405, "method_not_allowed")
            tokens = {"main": self.bot.TOKEN, "friends": self.bot.FRIENDS_TOKEN}
            identity = validate_init_data(h.headers.get("X-Telegram-Init-Data", ""), tokens)
            payload = {}
            if method == "POST":
                size = int(h.headers.get("Content-Length", "0"))
                if size <= 0 or size > 65536 or h.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise APIError(400, "bad_request_data")
                payload = json.loads(h.rfile.read(size))
                if not isinstance(payload, dict):
                    raise APIError(400, "json_object_expected")
            if method == "GET" and path.path == "/api/dota/items":
                self.call_main(identity, "authorize_items", {})
                data = self.fetch_items()
            elif method == "GET" and re.fullmatch(r"/api/dota/matches/[0-9]+", path.path):
                # Membership + role must be checked on the main thread first.
                mid = int(path.path.rsplit("/", 1)[1])
                self.call_main(identity, "authorize_match", {"match_id": mid})
                data = self.fetch_match(mid)
            else:
                data = self.call_main(identity, method + " " + path.path, payload)
            self.respond(h, 200, data)
        except APIError as e:
            self.respond(h, e.status, {"error": e.detail})
        except (json.JSONDecodeError, ValueError):
            self.respond(h, 400, {"error": "bad_json"})
        except Exception as e:
            self.bot.log(f"Mini App request failure: {type(e).__name__}: {str(e)[:120]}")
            self.respond(h, 500, {"error": "panel_error"})

    def call_main(self, identity, route, data):
        event = threading.Event()
        job = {"identity": identity, "route": route, "data": data, "event": event}
        try:
            self.jobs.put_nowait(job)
        except queue.Full:
            raise APIError(503, "server_busy") from None
        if not event.wait(45):
            raise APIError(504, "no_reply")
        if "error" in job:
            raise job["error"]
        return job.get("result", {})

    def drain(self, limit=12):
        """Called exclusively by the existing bot main loop (single AMP/SQLite writer)."""
        for _ in range(limit):
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                break
            try:
                job["result"] = self.dispatch(job["identity"], job["route"], job["data"])
            except APIError as e:
                job["error"] = e
            except Exception as e:
                self.bot.log(f"Mini App action {job['route']}: {type(e).__name__}: {str(e)[:180]}")
                job["error"] = APIError(502, "operation_failed")
            finally:
                job["event"].set()
                self.jobs.task_done()

    def access(self, identity):
        uid = identity["id"]
        if uid in self.bot.ADMINS:
            return None  # full access, including Dota.
        if identity["bot_kind"] != "friends" and self.bot.FRIENDS_TOKEN:
            raise APIError(403, "admin_only_bot")
        friend = self.bot.friend_get(self.commands.db, uid)
        if not friend:
            raise APIError(403, "no_access")
        return set(friend["instances"])

    @staticmethod
    def scoped_name(scope, name):
        if not name or (scope is not None and name not in scope):
            raise APIError(403, "no_instance_access")

    @staticmethod
    def admin(scope):
        if scope is not None:
            raise APIError(403, "admin_required")

    def idem(self, identity, payload):
        key = payload.get("request_id")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9-]{12,80}", key):
            raise APIError(400, "no_request_id")
        now = time.time()
        self.replay = {k: v for k, v in self.replay.items() if now - v[0] < 600}
        return (identity["id"], key)

    def operation(self, identity, payload, action):
        key = self.idem(identity, payload)
        if key in self.replay:
            return self.replay[key][1]
        result = action()
        self.replay[key] = (time.time(), result)
        return result

    def dispatch(self, identity, route, payload):
        scope = self.access(identity)
        uid = identity["id"]
        who = identity["user"]
        if route == "GET /api/me":
            return {"id": uid, "name": who.get("first_name") or who.get("username") or "Gracz",
                    "admin": scope is None, "version": self.bot.VERSION, "lang": self.bot.lang_for(uid),
                    "dota_notifications": dota_notifications_enabled(self.commands.db),
                    "warn_seconds": self.bot.WARN_SECONDS}
        if route == "GET /api/dota":
            self.admin(scope)
            return self.get_dota()
        if route == "POST /api/dota/notifications":
            self.admin(scope)
            value = payload.get("enabled")
            if type(value) is not bool:
                raise APIError(400, "enabled_bool")
            self.bot.meta_set(self.commands.db, "miniapp:dota_notify", "1" if value else "0")
            return {"enabled": value}
        if route == "POST /api/dota/watch":
            self.admin(scope)
            return self.operation(identity, payload, lambda: self.watch_dota(payload))
        if route == "POST /api/dota/unwatch":
            self.admin(scope)
            return self.operation(identity, payload, lambda: self.unwatch_dota(payload))
        if route == "POST /api/dota/refresh":
            self.admin(scope)
            now = time.monotonic()
            if self.last_refresh is not None and now - self.last_refresh < 300:
                raise APIError(429, "opendota_rate_limited")
            if self.dota is None or not self.bot.DOTA_CHECK_MINUTES:
                raise APIError(409, "opendota_sync_off")
            self.last_refresh = now
            # Schedule a normal poll on the next main-loop iteration instead of
            # blocking the current web request on several upstream API calls.
            self.dota.last = 0
            return {"ok": True, "scheduled": True}
        if route == "authorize_items":
            self.admin(scope)
            return {"ok": True}
        if route == "authorize_match":
            self.admin(scope)
            mid = payload["match_id"]
            exists = self.commands.db.execute(
                "SELECT 1 FROM mini_dota_matches m JOIN dota d "
                "ON d.account_id=m.account_id WHERE m.match_id=? LIMIT 1", (mid,)
            ).fetchone()
            if not exists:
                raise APIError(404, "match_not_watched")
            return {"ok": True}
        if route == "GET /api/amp/instances":
            return self.amp_instances(scope)
        match = re.fullmatch(r"(GET|POST) /api/amp/instances/([^/]+)/(players|settings|console|action)", route)
        if match:
            method, encoded, item = match.groups()
            name = urllib.parse.unquote(encoded)
            self.scoped_name(scope, name)
            # Verify existence via AMP and never use the user value as an API path/endpoint.
            inst = self.commands.amp.find(name)
            if item == "players" and method == "GET":
                return {"players": self.commands.amp.users(name)}
            if item == "settings" and method == "GET":
                return {"groups": self.get_settings(scope, name)}
            if item == "settings" and method == "POST":
                return self.operation(identity, payload, lambda: self.write_setting(identity, scope, name, payload))
            if item == "console":
                self.admin(scope)
                if method == "GET":
                    return {"lines": self.commands.amp.console_tail(name, n=60)}
                if method == "POST":
                    return self.operation(identity, payload, lambda: self.console(identity, name, payload))
            if item == "action" and method == "POST":
                return self.operation(identity, payload, lambda: self.amp_action(identity, inst, payload))
        raise APIError(404, "unknown_endpoint")

    def get_dota(self):
        db = self.commands.db
        players = [{"account_id": acc, "name": name, "rank_tier": tier, "public": public,
                    "matches_at": matches_at} for acc, name, tier, public, matches_at in
                   db.execute("SELECT account_id,name,rank_tier,public,matches_at FROM dota ORDER BY name")]
        matches = []
        for acc, name, raw, hero_name, hero_slug in db.execute("""
            SELECT m.account_id, d.name, m.payload, h.name, h.slug
            FROM mini_dota_matches m JOIN dota d ON d.account_id=m.account_id
            LEFT JOIN mini_dota_heroes h ON h.hero_id=m.hero_id
            ORDER BY m.start_time DESC, m.match_id DESC LIMIT 600
        """):
            try:
                matches.append(serialize_match(json.loads(raw), acc, name,
                                               (hero_name, hero_slug) if hero_name else None))
            except (ValueError, TypeError):
                continue
        totals = {p["account_id"]: {"wins": 0, "total": 0} for p in players}
        for m in matches:
            t = totals[m["account_id"]]
            t["total"] += 1
            t["wins"] += int(m["win"])
        heroes = {str(hid): {"name": name, "slug": slug} for hid, name, slug in
                  db.execute("SELECT hero_id, name, slug FROM mini_dota_heroes")}
        return {"players": players, "matches": matches, "totals": totals, "heroes": heroes,
                "notifications": dota_notifications_enabled(db)}

    def watch_dota(self, p):
        account = self.bot.dota_account_id(str(p.get("account_id") or ""))
        if account is None:
            raise APIError(400, "bad_friend_id")
        try:
            profile = self.bot.opendota(f"players/{account}")
            matches = self.bot.opendota(f"players/{account}/recentMatches") or []
        except Exception:
            raise APIError(502, "opendota_down") from None
        name = ((profile or {}).get("profile") or {}).get("personaname")
        if not name:
            raise APIError(404, "opendota_unknown_player")
        existing = self.commands.db.execute("SELECT 1 FROM dota WHERE account_id=?", (account,)).fetchone()
        if existing:
            raise APIError(409, "already_watched")
        last = max((int(m.get("match_id", 0)) for m in matches if isinstance(m, dict)), default=0)
        now = int(time.time())
        self.commands.db.execute(
            "INSERT INTO dota(account_id,name,last_match,added,rank_tier,rank_at,matches_at,public) "
            "VALUES(?,?,?,?,?,?,?,?)", (account, name, last, now, profile.get("rank_tier"),
                                        now, now, 1 if matches else 0)
        )
        store_recent_matches(self.commands.db, account, matches)
        return {"account_id": account, "name": name, "matches": len(matches)}

    def unwatch_dota(self, p):
        try:
            account = int(p["account_id"])
        except (KeyError, TypeError, ValueError):
            raise APIError(400, "no_player_id") from None
        self.commands.db.execute("DELETE FROM dota WHERE account_id=?", (account,))
        self.commands.db.execute("DELETE FROM mini_dota_matches WHERE account_id=?", (account,))
        self.commands.db.commit()
        return {"removed": account}

    def amp_instances(self, scope):
        if not self.commands.amp.configured:
            return {"configured": False, "instances": []}
        all_inst = self.commands.amp.instances()
        result = []
        for inst in all_inst:
            if scope is not None and inst["name"] not in scope:
                continue
            state = self.bot.amp_state(inst)[1]
            result.append({**inst, "state_text": state,
                           "busy": self.commands.watcher.busy(inst["name"]) if self.commands.watcher else None,
                           "players": self.commands.players_on(inst["name"])})
        return {"configured": True, "instances": result}

    def get_settings(self, scope, name):
        groups = self.commands.amp.settings(name)
        if scope is not None:
            groups = [(title, [s for s in items if not self.bot.FRIEND_SETTINGS_DENY.search(
                f"{s['node']} {s['name']}")]) for title, items in groups]
        return [{"name": title, "items": [{"name": s["name"], "node": s["node"],
                  "desc": s.get("desc", "")[:240], "type": s["type"], "enum": s["enum"],
                  "value": s["value"]} for s in items]} for title, items in groups if items]

    def write_setting(self, identity, scope, name, p):
        node, value = p.get("node"), p.get("value")
        allowed = {s["node"]: s for group in self.get_settings(scope, name) for s in group["items"]}
        if not isinstance(node, str) or node not in allowed:
            raise APIError(403, "setting_unavailable")
        setting = allowed[node]
        if setting["enum"] and str(value) not in {str(k) for k, _ in setting["enum"]}:
            raise APIError(400, "bad_enum_value")
        if setting["type"] == "checkbox":
            if value not in (True, False, "true", "false"):
                raise APIError(400, "bool_expected")
            value = "true" if str(value).lower() == "true" else "false"
        elif not isinstance(value, (str, int, float)) or len(str(value)) > 1000 or "\x00" in str(value):
            raise APIError(400, "bad_setting_value")
        self.commands.amp.set_config(name, node, value)
        self.audit(identity, f"⚙️ {node}", name)
        return {"ok": True, "node": node, "value": value}

    def amp_action(self, identity, instance, p):
        action = p.get("action")
        name = instance["name"]
        if action not in GAME_ACTIONS:
            raise APIError(400, "unknown_action")
        if self.commands.watcher and self.commands.watcher.busy(name):
            raise APIError(409, "operation_running")
        if action in SENSITIVE_ACTIONS and p.get("confirmed") is not True:
            raise APIError(400, "confirm_required")
        lang = self.bot.lang_for(identity["id"])  # progress messages in the language this person chose
        with self.bot.via(self.bot.FRIENDS_TOKEN if identity["bot_kind"] == "friends" else ""):
            if (p.get("warn") is True and action in self.bot.WARN_ACTS and self.bot.WARN_SECONDS
                    and self.commands.players_on(name) and self.commands.amp.broadcast_command(instance)):
                if self.commands.watcher:
                    self.commands.watcher.schedule(name, action, identity["id"], lang)
            else:
                self.commands.amp.action(action, name)
                if self.commands.watcher:
                    self.commands.watcher.track(name, action, identity["id"], lang)
            self.audit(identity, action, name)
        return {"ok": True, "action": action, "name": name}

    def console(self, identity, name, p):
        command = p.get("command")
        if (not isinstance(command, str) or not command.strip() or len(command) > 200
                or "\n" in command or "\r" in command):
            raise APIError(400, "bad_console_command")
        result = self.commands.amp.console(name, command.strip())
        self.audit(identity, f"💻 {command.strip()[:50]}", name)
        return {"lines": result}

    def audit(self, identity, action, name):
        with self.bot.via(self.bot.FRIENDS_TOKEN if identity["bot_kind"] == "friends" else ""):
            self.commands.audit(identity["user"], identity["id"], action, name)

    def fetch_items(self):
        """Small cached lookup for the item pictures visible in the match scoreboard."""
        now = time.monotonic()
        with self.detail_lock:
            if self.items_cache and now - self.items_cache[0] < 86400:
                return self.items_cache[1]
        request = urllib.request.Request("https://api.opendota.com/api/constants/items",
                                         headers={"User-Agent": "amp-tg-miniapp/2.8"})
        try:
            with urllib.request.urlopen(request, timeout=18) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise APIError(502, "items_too_big")
            payload = json.loads(raw)
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise APIError(502, "items_unavailable") from None
        items = {}
        for key, item in (payload.items() if isinstance(payload, dict) else []):
            if not isinstance(item, dict) or type(item.get("id")) is not int:
                continue
            img = str(item.get("img") or "").split("?", 1)[0]
            if not re.fullmatch(r"/apps/dota2/images/[a-z0-9_/-]+\.png", img):
                img = ""
            items[str(item["id"])] = {"name": str(item.get("dname") or key)[:100], "img": img}
        result = {"items": items}
        with self.detail_lock:
            self.items_cache = (now, result)
        return result

    def fetch_match(self, match_id):
        if match_id <= 0 or match_id >= 2 ** 64:
            raise APIError(400, "bad_match_id")
        now = time.monotonic()
        with self.detail_lock:
            cached = self.detail_cache.get(match_id)
            if cached and now - cached[0] < 21600:
                return cached[1]
        url = f"https://api.opendota.com/api/matches/{match_id}"
        request = urllib.request.Request(url, headers={"User-Agent": "amp-tg-miniapp/2.8"})
        try:
            with urllib.request.urlopen(request, timeout=18) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise APIError(502, "opendota_too_big")
        except (urllib.error.URLError, TimeoutError):
            raise APIError(502, "opendota_unavailable") from None
        try:
            data = match_detail_data(json.loads(raw))
        except (ValueError, TypeError):
            raise APIError(502, "opendota_bad_match_data") from None
        with self.detail_lock:
            if len(self.detail_cache) >= 50:
                oldest = min(self.detail_cache, key=lambda x: self.detail_cache[x][0])
                del self.detail_cache[oldest]
            self.detail_cache[match_id] = (now, data)
        return data


# --- Transactional multi-file release updates ---

def download_release_file(repo: str, tag: str, name: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid repo")
    if not re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+(?:[-A-Za-z0-9.]*)?", tag):
        raise ValueError("invalid tag")
    url = f"https://raw.githubusercontent.com/{repo}/{tag}/{name}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "amp-tg-release"}),
                                timeout=30) as response:
        return response.read(3_000_000)


def install_release(tag: str, repo: str, bot_path: str):
    """Stage, self-test and replace all release files, rolling back on any local failure.

    Uses a complete previous version snapshot; bot restart is handled by existing supervisor.
    """
    base = Path(bot_path).resolve().parent
    staging = Path(tempfile.mkdtemp(prefix=".miniapp-stage-", dir=base))
    prev = base / ".miniapp-previous"
    try:
        for name in RELEASE_FILES:
            dest = staging / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            payload = download_release_file(repo, tag, name)
            if len(payload) == 0 or len(payload) == 3_000_000:
                raise RuntimeError(f"empty or oversized {name}")
            dest.write_bytes(payload)
        test = subprocess.run([sys.executable, str(staging / "bot.py"), "--selftest"],
                              capture_output=True, text=True, timeout=75)
        if test.returncode:
            return False, "Selftest: " + (test.stdout + test.stderr)[-900:]
        # Never delete the working previous snapshot until the candidate is verified.
        new_previous = base / ".miniapp-previous.new"
        if new_previous.exists():
            shutil.rmtree(new_previous)
        new_previous.mkdir()
        for name in RELEASE_FILES:
            target = base / name
            if target.is_file():
                snap = new_previous / name
                snap.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, snap)
        for name in RELEASE_FILES:
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / name, target)
        if prev.exists():
            shutil.rmtree(prev)
        os.replace(new_previous, prev)
        return True, "OK " + tag
    except Exception as e:
        # If partial replacement happened, restore every file from the saved snapshot.
        snap = base / ".miniapp-previous.new"
        if snap.is_dir():
            for name in RELEASE_FILES:
                old = snap / name
                if old.is_file():
                    dest = base / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(old, dest)
                elif (base / name).is_file():
                    (base / name).unlink()
            shutil.rmtree(snap, ignore_errors=True)
        return False, f"Update failed: {type(e).__name__}: {str(e)[:350]}"
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def rollback_release(bot_path: str):
    base = Path(bot_path).resolve().parent
    prev = base / ".miniapp-previous"
    if not prev.is_dir() or not (prev / "bot.py").is_file():
        return False, "Brak poprzedniej wersji"
    # Copy to a staging directory, so a rollback can itself be rolled forward manually.
    try:
        for name in RELEASE_FILES:
            old = prev / name
            dest = base / name
            if old.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, dest)
            elif dest.is_file():
                dest.unlink()
        shutil.rmtree(prev)
        return True, "Przywrocono poprzednia wersje"
    except OSError as e:
        return False, f"Rollback: {e}"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", metavar="TAG")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--dir", default="/opt/amp-tg-bot")
    parser.add_argument("--repo", default="setsun-ai/amp-cubecoders-tg-bot")
    args = parser.parse_args()
    if args.install:
        ok, message = install_release(args.install, args.repo, os.path.join(args.dir, "bot.py"))
    elif args.rollback:
        ok, message = rollback_release(os.path.join(args.dir, "bot.py"))
    else:
        parser.error("Choose --install or --rollback")
    print(message)
    sys.exit(0 if ok else 1)
