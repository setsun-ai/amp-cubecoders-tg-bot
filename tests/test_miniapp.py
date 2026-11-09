from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

import miniapp


TOK_MAIN = "10101:main-secret"
TOK_FRIEND = "20202:friends-secret"


def signed(uid=42, token=TOK_MAIN, auth_date=None, tamper=False):
    values = {"auth_date": str(auth_date or int(time.time())),
              "user": json.dumps({"id": uid, "first_name": "Test"}, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(values.items()))
    key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    if tamper:
        values["user"] = json.dumps({"id": 42, "first_name": "Hacker"})
    return urllib.parse.urlencode(values)


class FakeAmp:
    configured = True

    def __init__(self):
        self.actions = []
        self.config_changes = []
        self.console_changes = []

    def instances(self):
        return [{"name": "Mine", "friendly": "Minecraft", "module": "Minecraft", "running": True,
                 "state": 20, "cpu": {"pct": 15, "raw": 15, "max": 100, "units": "%"},
                 "mem": {"pct": 30, "raw": 300, "max": 1000, "units": "MB"}},
                {"name": "Others", "friendly": "Valheim", "module": "Valheim", "running": True,
                 "state": 20, "cpu": None, "mem": None}]

    def find(self, name):
        return next(i for i in self.instances() if i["name"] == name)

    def action(self, act, name):
        self.actions.append((act, name))

    def users(self, name):
        return ["Player 1"] if name == "Mine" else []

    def broadcast_command(self, inst):
        return "say {text}" if inst["name"] == "Mine" else None

    def settings(self, name):
        return [("Game", [
            {"node": "Server.Name", "name": "Server Name", "type": "text", "value": "X", "desc": "",
             "enum": []},
            {"node": "Java.Arguments", "name": "Additional Java Arguments", "type": "text", "value": "", "desc": "",
             "enum": []},
            {"node": "Server.PVP", "name": "PVP", "type": "checkbox", "value": "true", "desc": "",
             "enum": []},
            {"node": "Difficulty", "name": "Difficulty", "type": "select", "value": "easy", "desc": "",
             "enum": [("easy", "Easy"), ("hard", "Hard")]}])]

    def set_config(self, name, node, value):
        self.config_changes.append((name, node, value))

    def console(self, name, command):
        self.console_changes.append((name, command))
        return ["OK"]

    def console_tail(self, name, n=60):
        return ["The server is running"]


class FakeWatcher:
    def __init__(self):
        self.tracked = []
        self.scheduled = []
        self.busy_names = set()

    def busy(self, name):
        return "restart" if name in self.busy_names else None

    def track(self, *args):
        self.tracked.append(args)

    def schedule(self, *args):
        self.scheduled.append(args)


class Bot:
    TOKEN = TOK_MAIN
    FRIENDS_TOKEN = TOK_FRIEND
    ADMINS = {42}
    VERSION = "2.8.0"
    WARN_SECONDS = 60
    WARN_ACTS = ("stop", "restart", "off", "update")
    DOTA_CHECK_MINUTES = 60
    FRIEND_SETTINGS_DENY = __import__("re").compile(
        r"java|arguments|path|port|steam|schedule|backup", __import__("re").I
    )

    def __init__(self, db):
        self.db = db
        self.logs = []
        self.audit_logs = []
        self.commands = type("Commands", (), {})()
        self.commands.db = db
        self.commands.amp = FakeAmp()
        self.commands.watcher = FakeWatcher()
        self.commands.players_on = lambda name: 1 if name == "Mine" else 0
        self.commands.audit = lambda *args: self.audit_logs.append(args)
        self.dota = type("Dota", (), {})()
        self.dota.last = 100
        self.dota.poll = lambda: None

    def log(self, message):
        self.logs.append(message)

    def friend_get(self, db, uid):
        row = db.execute("SELECT instances FROM friends WHERE user_id=?", (uid,)).fetchone()
        return {"instances": json.loads(row[0])} if row else None

    def meta_set(self, db, key, value):
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value))
        db.commit()

    def amp_state(self, inst):
        return ("🟢", "Ready")

    def dota_account_id(self, value):
        return int(value) if value.isdigit() else None

    def opendota(self, path):
        if path.endswith("recentMatches"):
            return [{"match_id": 990, "player_slot": 0, "radiant_win": True, "hero_id": 12,
                     "start_time": 12345, "kills": 12, "deaths": 2, "assists": 4}]
        return {"profile": {"personaname": "Fake player"}, "rank_tier": 55}

    @staticmethod
    def via(token):
        from contextlib import nullcontext
        return nullcontext()


@pytest.fixture
def fixture():
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.executescript("""
      CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
      CREATE TABLE friends(user_id INTEGER PRIMARY KEY, instances TEXT);
      CREATE TABLE dota(account_id INTEGER PRIMARY KEY,name TEXT,last_match INTEGER,added INTEGER,
          rank_tier INTEGER,rank_at INTEGER,matches_at INTEGER,public INTEGER);
      INSERT INTO friends VALUES(50,'["Mine"]');
      INSERT INTO dota VALUES(123,'Alice',0,0,55,0,0,1);
    """)
    miniapp.ensure_schema(db)
    bot = Bot(db)
    server = miniapp.MiniAppServer(bot, bot.commands, bot.dota, port=0)
    yield server, db, bot
    db.close()


def main_user():
    return {"id": 42, "bot_kind": "main", "user": {"id": 42, "first_name": "Owner"}}


def friend_user(token="friends"):
    return {"id": 50, "bot_kind": token, "user": {"id": 50, "first_name": "Friend"}}


def test_authentication_accepts_telegram_signature():
    uid = miniapp.validate_init_data(signed(), {"main": TOK_MAIN})
    assert uid["id"] == 42
    assert uid["bot_kind"] == "main"


@pytest.mark.parametrize('raw', ['', 'x=1&x=2', signed(tamper=True),
                                  signed(auth_date=1700000000), signed(uid=3, token='bad-token')])
def test_authentication_rejects_forged_or_expired(raw):
    with pytest.raises(miniapp.APIError) as exc:
        miniapp.validate_init_data(raw, {"main": TOK_MAIN})
    assert exc.value.status == 401


def test_authentication_rejects_duplicate_fields_and_future_clock():
    with pytest.raises(miniapp.APIError):
        miniapp.validate_init_data(signed() + '&auth_date=999999999', {"main": TOK_MAIN})
    with pytest.raises(miniapp.APIError):
        miniapp.validate_init_data(signed(auth_date=int(time.time()) + 600), {"main": TOK_MAIN})


def test_history_is_idempotent_and_notifications_independent(fixture):
    server, db, bot = fixture
    recent = [{"match_id": 90, "hero_id": 12, "start_time": 1699,
               "radiant_win": False, "player_slot": 129, "kills": 5, "deaths": 3, "assists": 11}]
    assert miniapp.store_recent_matches(db, 123, recent) == 1
    assert miniapp.store_recent_matches(db, 123, recent) == 1
    miniapp.store_heroes(db, {"12": {"localized_name": "Phantom Lancer", "name": "npc_dota_hero_phantom_lancer"}})
    assert len(server.dispatch(main_user(), "GET /api/dota", {})["matches"]) == 1
    assert server.dispatch(main_user(), "GET /api/dota", {})["matches"][0]["win"] is True
    server.dispatch(main_user(), "POST /api/dota/notifications", {"enabled": False})
    assert miniapp.dota_notifications_enabled(db) is False
    assert server.dispatch(main_user(), "GET /api/dota", {})["matches"][0]["hero_name"] == "Phantom Lancer"


def test_friend_scope_is_enforced_on_every_endpoint(fixture):
    server, db, bot = fixture
    result = server.dispatch(friend_user(), "GET /api/amp/instances", {})
    assert [x["name"] for x in result["instances"]] == ["Mine"]
    with pytest.raises(miniapp.APIError) as exc:
        server.dispatch(friend_user(), "GET /api/dota", {})
    assert exc.value.status == 403
    with pytest.raises(miniapp.APIError):
        server.dispatch(friend_user(), "GET /api/amp/instances/Others/players", {})
    with pytest.raises(miniapp.APIError):
        server.dispatch(friend_user(), "POST /api/amp/instances/Others/action", {
            "action": "restart", "confirmed": True, "request_id": "123456789012"})
    with pytest.raises(miniapp.APIError):
        server.dispatch(friend_user("main"), "GET /api/amp/instances", {})
    assert bot.commands.amp.actions == []


def test_admin_only_console_and_safe_friend_settings(fixture):
    server, db, bot = fixture
    response = server.dispatch(friend_user(), "GET /api/amp/instances/Mine/settings", {})
    keys = [s["node"] for x in response["groups"] for s in x["items"]]
    assert "Java.Arguments" not in keys
    assert "Server.Name" in keys
    with pytest.raises(miniapp.APIError):
        server.dispatch(friend_user(), "GET /api/amp/instances/Mine/console", {})
    with pytest.raises(miniapp.APIError):
        server.dispatch(friend_user(), "POST /api/amp/instances/Mine/settings", {
            "request_id": "123456789012", "node": "Java.Arguments", "value": "-Xmx9G"})
    result = server.dispatch(friend_user(), "POST /api/amp/instances/Mine/settings", {
        "request_id": "abcdefghijkl", "node": "Server.PVP", "value": False})
    assert result["ok"] is True
    assert bot.commands.amp.config_changes == [("Mine", "Server.PVP", "false")]


def test_invalid_setting_value_is_rejected(fixture):
    server, db, bot = fixture
    with pytest.raises(miniapp.APIError):
        server.dispatch(main_user(), "POST /api/amp/instances/Mine/settings", {
            "request_id": "abcdeffedcba", "node": "Difficulty", "value": "impossible"})
    assert not bot.commands.amp.config_changes


def test_confirmation_and_duplicate_actions(fixture):
    server, db, bot = fixture
    with pytest.raises(miniapp.APIError):
        server.dispatch(friend_user(), "POST /api/amp/instances/Mine/action", {
            "request_id": "123456789012", "action": "restart"})
    request = {"request_id": "123456789012", "action": "restart", "confirmed": True, "warn": True}
    assert server.dispatch(friend_user(), "POST /api/amp/instances/Mine/action", request)["ok"]
    assert server.dispatch(friend_user(), "POST /api/amp/instances/Mine/action", request)["ok"]
    assert len(bot.commands.watcher.scheduled) == 1
    assert not bot.commands.amp.actions


def test_start_stop_and_busy(fixture):
    server, db, bot = fixture
    p = {"request_id": "abcdef012345", "action": "start"}
    server.dispatch(main_user(), "POST /api/amp/instances/Mine/action", p)
    assert bot.commands.amp.actions == [("start", "Mine")]
    bot.commands.watcher.busy_names.add("Mine")
    with pytest.raises(miniapp.APIError) as exc:
        server.dispatch(main_user(), "POST /api/amp/instances/Mine/action", {
            "request_id": "newrequest123", "action": "stop", "confirmed": True})
    assert exc.value.status == 409


def test_watch_unwatch_with_history(fixture):
    server, db, bot = fixture
    first = server.dispatch(main_user(), "POST /api/dota/watch", {"account_id": "765", "request_id": "watchplayer765"})
    assert first["name"] == "Fake player"
    assert db.execute("SELECT COUNT(*) FROM mini_dota_matches WHERE account_id=765").fetchone()[0] == 1
    with pytest.raises(miniapp.APIError):
        server.dispatch(main_user(), "POST /api/dota/watch", {"account_id": "765", "request_id": "different123456"})
    server.dispatch(main_user(), "POST /api/dota/unwatch", {"account_id": 765, "request_id": "unwatchplayer765"})
    assert db.execute("SELECT COUNT(*) FROM mini_dota_matches WHERE account_id=765").fetchone()[0] == 0


def test_match_detail_allowlist_and_limit():
    raw = {"match_id": 123, "radiant_win": True, "players": [{"personaname": "P", "secret": "no"}] * 30}
    data = miniapp.match_detail_data(raw)
    assert len(data["players"]) == 10
    assert "secret" not in data["players"][0]


def test_url_requires_https(monkeypatch):
    monkeypatch.setenv("MINIAPP_URL", "http://localhost:8765")
    with pytest.raises(ValueError):
        miniapp.public_url()
    monkeypatch.setenv("MINIAPP_URL", "https://tailnet.ts.net")
    assert miniapp.public_url() == "https://tailnet.ts.net"


def test_queue_timeout_path_is_bounded(fixture):
    server, db, bot = fixture
    result = []
    thread = threading.Thread(target=lambda: result.append(server.call_main(main_user(), "GET /api/me", {})))
    thread.start()
    for _ in range(100):
        if server.jobs.qsize():
            break
        time.sleep(.002)
    server.drain()
    thread.join(timeout=2)
    assert result[0]["id"] == 42


def test_http_requires_signed_header(fixture, monkeypatch, tmp_path):
    server, db, bot = fixture
    web = tmp_path / 'web'
    web.mkdir()
    for file in ('index.html', 'app.js', 'style.css'):
        (web / file).write_text('TEST '+file)
    server.web_dir = web
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server.port = port
    monkeypatch.setenv('MINIAPP_URL', 'https://example.ts.net')
    assert server.start()
    running = True
    def drain():
        while running:
            server.drain()
            time.sleep(.004)
    t = threading.Thread(target=drain, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/') as result:
            assert result.read() == b'TEST index.html'
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/me')
        assert exc.value.code == 401
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/me',
                                         headers={'X-Telegram-Init-Data': signed()})
        with urllib.request.urlopen(request) as result:
            assert json.loads(result.read())['admin'] is True
    finally:
        running = False
        server.stop()
        t.join(timeout=1)


def test_release_rolls_back_failed_candidate(tmp_path, monkeypatch):
    # The self-test fails in staging, so no installed file can change.
    (tmp_path / 'bot.py').write_text('print("original")')
    monkeypatch.setattr(
        miniapp, 'download_release_file',
        lambda *a: b'raise SystemExit(1)' if a[2] == 'bot.py' else b'test',
    )
    ok, reason = miniapp.install_release('v2.8.0', 'org/repo', str(tmp_path / 'bot.py'))
    assert not ok and 'Selftest' in reason
    assert (tmp_path / 'bot.py').read_text() == 'print("original")'


def test_release_success_and_rollback(tmp_path, monkeypatch):
    (tmp_path / 'bot.py').write_text('print("original")')
    candidate = {"bot.py": b'import sys\nprint("OK")\n',
                 "miniapp.py": b'print("miniapp")\n'}
    monkeypatch.setattr(miniapp, 'download_release_file', lambda *a: candidate.get(a[2], b'asset'))
    ok, reason = miniapp.install_release('v2.8.0', 'org/repo', str(tmp_path / 'bot.py'))
    assert ok, reason
    assert (tmp_path / 'web' / 'index.html').read_bytes() == b'asset'
    assert (tmp_path / 'bot.py').read_bytes() == candidate['bot.py']
    ok, reason = miniapp.rollback_release(str(tmp_path / 'bot.py'))
    assert ok, reason
    assert (tmp_path / 'bot.py').read_text() == 'print("original")'
    assert not (tmp_path / 'web' / 'index.html').exists()


def test_items_metadata_allowlist_and_cache(fixture, monkeypatch):
    server, _, _ = fixture
    data = {"blink": {"id": 1, "dname": "Blink Dagger", "img": "/apps/dota2/images/dota_react/items/blink.png"},
            "strange": {"id": 2, "dname": "Bad", "img": "https://attacker.example/tracking.png"}}
    calls = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *exc): pass
        def read(self, n): return json.dumps(data).encode()

    def fake(req, **kwargs):
        calls.append(req.full_url)
        return Response()

    monkeypatch.setattr(miniapp.urllib.request, "urlopen", fake)
    item = server.fetch_items()
    assert item["items"]["1"]["name"] == "Blink Dagger"
    assert item["items"]["2"]["img"] == ""
    assert server.fetch_items() == item
    assert len(calls) == 1


def test_match_detail_requires_existing_watched_match(fixture):
    server, db, _ = fixture
    with pytest.raises(miniapp.APIError) as exc:
        server.dispatch(main_user(), "authorize_match", {"match_id": 44})
    assert exc.value.status == 404
    miniapp.store_recent_matches(db, 123, [{"match_id": 44, "radiant_win": True}])
    assert server.dispatch(main_user(), "authorize_match", {"match_id": 44})["ok"]
    with pytest.raises(miniapp.APIError):
        server.dispatch(friend_user(), "authorize_match", {"match_id": 44})
    with pytest.raises(miniapp.APIError):
        server.dispatch(friend_user(), "authorize_items", {})


def test_detail_is_fetched_on_demand_and_cached(fixture, monkeypatch):
    server, _, _ = fixture
    called = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *exc): pass
        def read(self, n): return json.dumps({"match_id": 66, "players": [{"kills": 5}]}).encode()

    def fake(req, **kwargs):
        called.append(req.full_url)
        return Response()
    monkeypatch.setattr(miniapp.urllib.request, "urlopen", fake)
    assert server.fetch_match(66)["players"][0]["kills"] == 5
    assert server.fetch_match(66)["match_id"] == 66
    assert len(called) == 1
    assert called[0].endswith("/matches/66")


def test_manual_refresh_schedules_poll_without_blocking(fixture, monkeypatch):
    clock = [42.0]
    monkeypatch.setattr(miniapp.time, 'monotonic', lambda: clock[0])
    server, _, bot = fixture
    assert server.dispatch(main_user(), "POST /api/dota/refresh", {})["scheduled"]
    assert bot.dota.last == 0
    with pytest.raises(miniapp.APIError) as exc:
        server.dispatch(main_user(), "POST /api/dota/refresh", {})
    assert exc.value.status == 429
    clock[0] += 301
    assert server.dispatch(main_user(), 'POST /api/dota/refresh', {})['scheduled']


def test_http_bad_post_does_not_reach_amp(fixture, monkeypatch, tmp_path):
    server, db, bot = fixture
    web = tmp_path / 'web'
    web.mkdir()
    for file in ('index.html', 'app.js', 'style.css'):
        (web / file).write_text('OK')
    server.web_dir = web
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        server.port = sock.getsockname()[1]
    monkeypatch.setenv('MINIAPP_URL', 'https://my.ts.net')
    server.start()
    try:
        request = urllib.request.Request(f'http://127.0.0.1:{server.port}/api/amp/instances/Mine/action',
                                         data=b'{broken', headers={
                                             'Content-Type': 'application/json', 'X-Telegram-Init-Data': signed()})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request)
        assert exc.value.code == 400
        assert not bot.commands.amp.actions
    finally:
        server.stop()


def test_http_port_loaded_after_environment_file(monkeypatch, fixture):
    _, db, bot = fixture
    monkeypatch.setenv("MINIAPP_PORT", "9432")
    server = miniapp.MiniAppServer(bot, bot.commands, bot.dota)
    assert server.port == 9432


def test_corrupt_opendota_match_response_is_upstream_error(fixture, monkeypatch):
    server, _, _ = fixture

    class Response:
        def __enter__(self): return self
        def __exit__(self, *exc): pass
        def read(self, size): return b"not JSON"

    monkeypatch.setattr(miniapp.urllib.request, "urlopen", lambda *a, **kw: Response())
    with pytest.raises(miniapp.APIError) as exc:
        server.fetch_match(123)
    assert exc.value.status == 502
