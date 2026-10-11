"""Testy parserow logow i komend na zmyslonych danych (bez Telegrama i internetu)."""
import json

import pytest

import bot

REAL_SEND = bot.send  # przed podmiana w fixture env

VALHEIM_KVP = [
    "App.DisplayName=Valheim",
    r"Console.UserJoinRegex=^(?:\[[\d\/]+ [\d:]+\] )?Got character ZDOID from (?<username>.+?) : "
    r"(?<userid>-?\d+):\d+$",
    r"Console.UserLeaveRegex=^(?:\[[\d\/]+ [\d:]+\] )?Destroying abandoned non persistent zdo -?\d+:\d+ "
    r"owner (?<userid>-?\d+)$",
]
TERRARIA_KVP = [
    "App.DisplayName=Terraria",
    r"Console.UserJoinRegex=^(?<username>.+?) has joined\.$",
    r"Console.UserLeaveRegex=^(?<username>.+?) has left\.$",
]
SID_A, SID_B = "76500000000000001", "76500000000000002"


@pytest.fixture
def env(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent.append(text))
    monkeypatch.setattr(bot, "DB_PATH", str(tmp_path / "db" / "players.db"))
    monkeypatch.setattr(bot, "CHAT_LANGS", {})
    root = tmp_path / "instances"

    def make(name, kvp_name, kvp_lines):
        d = root / name
        (d / "AMP_Logs").mkdir(parents=True)
        (d / kvp_name).write_text("\n".join(kvp_lines) + "\n", encoding="utf-8")
        (d / "AMP_Logs" / "AMPLOG_1.log").write_text("", encoding="utf-8")
        return d

    make("Panel01", "ADSModule.kvp", ["x=y"])
    make("Valheim01", "GenericModule.kvp", VALHEIM_KVP)
    make("Terraria01", "GenericModule.kvp", TERRARIA_KVP)
    make("Mc01", "MinecraftModule.kvp", ["x=y"])
    make("Unknown01", "GenericModule.kvp", ["App.DisplayName=Something"])
    db = bot.open_db()

    class Env:
        pass

    e = Env()
    e.sent, e.db, e.root = sent, db, root
    e.inst = {d.name: bot.Instance(d.name, str(d) + "/", db, start_at_end=False) for d in root.iterdir()}

    def write(name, *lines, poll=True):
        with open(root / name / "AMP_Logs" / "AMPLOG_1.log", "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        if poll:
            e.inst[name].poll()

    e.write = write
    return e


def test_detects_games(env):
    status = {n: (i.status, i.game) for n, i in env.inst.items()}
    assert status["Panel01"][0] == "skip"
    assert status["Valheim01"] == ("ok", "Valheim")
    assert status["Terraria01"] == ("ok", "Terraria")
    assert status["Mc01"] == ("ok", "Minecraft")
    assert status["Unknown01"] == ("brak", "Something")


def test_valheim_join_death_leave(env):
    env.write("Valheim01",
              f"Got connection SteamID {SID_A}",
              "Got character ZDOID from Alice : 111:1",
              "Got character ZDOID from Alice : 0:0",
              "Got character ZDOID from Alice : 111:50",
              f"Got connection SteamID {SID_B}",
              f"Closing socket {SID_B}",  # zle haslo: polaczenie bez postaci
              f"Closing socket {SID_A}")
    msgs = "\n".join(env.sent)
    assert "NOWY GRACZ" in msgs and SID_A in msgs
    assert "Alice</b> ginie (1. raz dzisiaj)" in msgs
    assert msgs.count("wchodzi na serwer") == 1
    assert "Alice</b> wychodzi" in msgs
    assert not env.inst["Valheim01"].online


def test_valheim_amp_leave_rule(env):
    env.write("Valheim01", f"Got connection SteamID {SID_A}", "Got character ZDOID from Alice : 111:1",
              "Destroying abandoned non persistent zdo 5:6 owner 111")
    assert not env.inst["Valheim01"].online


def test_new_player_only_once(env):
    for _ in range(2):
        env.write("Valheim01", f"Got connection SteamID {SID_A}", "Got character ZDOID from Alice : 111:1",
                  f"Closing socket {SID_A}")
    assert sum("NOWY GRACZ" in m for m in env.sent) == 1


def test_terraria_ignores_chat(env):
    env.write("Terraria01", "Bob has joined.", "<Eve> Mallory has joined.", "Bob has left.")
    joins = [m for m in env.sent if "wchodzi" in m]
    assert len(joins) == 1 and "Bob" in joins[0]


def test_minecraft(env):
    env.write("Mc01",
              "[12:00:00] [User Authenticator #1/INFO]: UUID of player Steve is 069a79f4-44e9-4726-a5be-fca90e38aaf5",
              "[12:00:01] [Server thread/INFO]: Steve[/127.0.0.1:50000] logged in with entity id 1 at (0, 64, 0)",
              "[12:00:01] [Server thread/INFO]: Steve joined the game",
              "[12:00:02] [Server thread/INFO]: <Steve> ]: Alex joined the game",
              "[12:00:03] [Server thread/INFO]: <Steve> Alex was slain by me",
              "[12:00:04] [Server thread/INFO]: Steve fell from a high place",
              "[12:05:00] [Server thread/INFO]: Steve left the game")
    msgs = "\n".join(env.sent)
    assert "069a79f4-44e9-4726-a5be-fca90e38aaf5" in msgs
    assert "127.0.0.1" not in msgs  # adres lokalny (tunel) nie jest pokazywany
    assert "Alex" not in msgs
    assert msgs.count("ginie") == 1
    assert "Steve</b> wychodzi" in msgs


def test_replay_on_startup_finds_online_players(env):
    env.write("Valheim01", f"Got connection SteamID {SID_A}", "Got character ZDOID from Alice : 111:1",
              f"Got connection SteamID {SID_B}", "Got character ZDOID from Bob : 222:1",
              f"Closing socket {SID_B}", poll=False)
    inst = bot.Instance("Valheim01", str(env.root / "Valheim01") + "/", env.db, start_at_end=True)
    inst.poll()
    assert list(inst.online) == ["alice"]
    assert env.sent == []  # odtworzenie po cichu
    assert "Alice" in bot.cmd_online({"Valheim01": inst})
    env.inst["Valheim01"] = inst
    env.write("Valheim01", f"Closing socket {SID_A}")
    assert "co najmniej" in env.sent[-1]


def test_restart_of_instance_closes_sessions(env):
    env.write("Valheim01", f"Got connection SteamID {SID_A}", "Got character ZDOID from Alice : 111:1")
    (env.root / "Valheim01" / "AMP_Logs" / "AMPLOG_2.log").write_text("", encoding="utf-8")
    import os
    import time
    later = time.time() + 5
    os.utime(env.root / "Valheim01" / "AMP_Logs" / "AMPLOG_2.log", (later, later))
    env.inst["Valheim01"].poll()
    assert "restart serwera" in env.sent[-1]


def test_commands(env):
    env.write("Valheim01", f"Got connection SteamID {SID_A}", "Got character ZDOID from Alice : 111:1",
              f"Closing socket {SID_A}")
    env.sent.clear()
    c = bot.Commands(env.db, env.inst)
    for text in ["/online", "/historia 5", "/gracz Alice", "/tydzien", "/pomoc"]:
        c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": text})
    online, hist, gracz, week, help_ = env.sent
    assert "Nikt teraz nie gra" in online
    assert "Alice" in hist and "Alice" in gracz and SID_A in gracz
    assert "Podsumowanie" in week
    assert "/online" in help_ and "/update" in help_


def test_stranger_is_rejected_and_reported_once(env):
    c = bot.Commands(env.db, env.inst)
    for _ in range(2):
        c.handle({"chat": {"id": 9}, "from": {"id": 9, "first_name": "Obcy"}, "text": "/online"})
    assert sum("Ktoś pisze do bota" in m for m in env.sent) == 1
    assert "owner got your request" in env.sent[1]  # obcy bez language_code: po angielsku
    assert env.sent[-1] == "⛔ This is a private bot."  # druga wiadomosc: bez nowej prosby


def test_battery_warning(monkeypatch, env):
    monkeypatch.setattr(bot, "playit_mode", lambda: None)
    monkeypatch.setattr(bot, "cpu_temp", lambda: 50)
    h = bot.HostMonitor()
    for level in [52, 46, 44, 40, 47, 48, 44]:
        monkeypatch.setattr(bot, "power_state", lambda level=level: (True, level))
        h.check()
    assert [m.split("</b>")[0] for m in env.sent if m.startswith("🪫")] == ["🪫 <b>Bateria 44%", "🪫 <b>Bateria 44%"]
    assert any("wróciła do 48%" in m for m in env.sent)


def test_version_compare():
    assert bot.version_tuple("v1.10.0") > bot.version_tuple("1.9.3")


def test_selftest_runs(capsys, monkeypatch, env):
    monkeypatch.setattr(bot, "INSTANCES_DIR", str(env.root))
    bot.selftest()
    assert f"OK {bot.VERSION}" in capsys.readouterr().out


def test_install_release_tests_and_swaps(tmp_path, monkeypatch, env):
    import pathlib
    source = pathlib.Path(bot.__file__).read_bytes()
    target = tmp_path / "opt" / "bot.py"
    target.parent.mkdir()
    target.write_bytes(b"# stara wersja\n")
    monkeypatch.setattr(bot, "BOT_PATH", str(target))
    monkeypatch.setenv("AMP_INSTANCES", str(env.root))

    monkeypatch.setattr(bot, "github_get", lambda url, timeout=20: b"to nie jest python (")
    ok, out = bot.install_release("v9.9.9")
    assert not ok and target.read_bytes() == b"# stara wersja\n"

    monkeypatch.setattr(bot, "github_get", lambda url, timeout=20: source)
    ok, out = bot.install_release("v9.9.9")
    assert ok, out
    assert target.read_bytes() == source
    assert (tmp_path / "opt" / "bot.py.bak").read_bytes() == b"# stara wersja\n"


def test_update_command_sets_restart(monkeypatch, env):
    monkeypatch.setattr(bot, "latest_release", lambda: "v99.0.0")
    monkeypatch.setattr(bot, "install_release", lambda tag: (True, "OK"))
    c = bot.Commands(env.db, env.inst)
    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/update"})
    assert c.restart and bot.meta_get(env.db, "updated_from") == bot.VERSION

    monkeypatch.setattr(bot, "latest_release", lambda: f"v{bot.VERSION}")
    c2 = bot.Commands(env.db, env.inst)
    c2.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/update"})
    assert not c2.restart and "najnowszą" in env.sent[-1]


def test_every_text_in_four_languages_with_same_placeholders():
    import string
    for key, texts in bot.STRINGS.items():
        assert len(texts) == 4 and all(texts), key
        fields = [sorted(f for _, f, _, _ in string.Formatter().parse(x) if f) for x in texts]
        assert all(f == fields[0] for f in fields), key


def test_language_switch(env):
    c = bot.Commands(env.db, env.inst)
    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/lang"})
    assert env.sent[-1] == "🌐 Wybierz język:"
    c.handle_callback({"id": "x", "from": {"id": 1}, "data": "lang:en",
                       "message": {"chat": {"id": 1}, "message_id": 5}})
    assert bot.lang_for(1) == "en" and bot.meta_get(env.db, "lang:1") == "en"
    env.sent.clear()
    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/online"})
    env.write("Valheim01", f"Got connection SteamID {SID_A}", "Got character ZDOID from Alice : 111:1")
    assert "Nobody is playing right now" in env.sent[0]
    assert "joined the server" in env.sent[-1]  # powiadomienia na czacie admina tez po angielsku

    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/lang ua"})
    assert bot.lang_for(1) == "uk"
    env.write("Valheim01", f"Closing socket {SID_A}")
    assert "виходить" in env.sent[-1] and "хв" in env.sent[-1]

    bot.CHAT_LANGS.clear()
    bot.load_langs(env.db)  # po restarcie bota jezyk wraca z bazy
    assert bot.lang_for(1) == "uk"


def test_stranger_gets_answer_in_own_language(env):
    c = bot.Commands(env.db, env.inst)
    c.handle({"chat": {"id": 9}, "from": {"id": 9, "first_name": "X", "language_code": "ru"}, "text": "/x"})
    assert env.sent[-1].startswith("⛔ Это приватный бот")


def test_old_polish_notes_are_translated(env):
    env.db.execute("INSERT INTO sessions(instance, game, username, joined, note) VALUES "
                   "('Valheim01', 'Valheim', 'Alice', 1, 'bot zrestartowany')")
    assert "bot restarted" in bot.cmd_history(env.db, [], "en")


def test_help_and_selftest_in_all_languages():
    for lang in bot.LANG_ORDER:
        text = bot.help_text(lang)
        assert all(f"/{cmd}" in text for cmd, _ in bot.COMMANDS)


class FakeAmp(bot.Amp):
    """AMP bez sieci: zapisuje wywolania, sesja wygasa raz."""

    def __init__(self):
        super().__init__("http://amp.test", "bot", "secret")
        self.calls = []
        self.expire_once = True

    def _post(self, path, payload, timeout=30):
        self.calls.append((path, payload))
        if path.endswith("Core/Login"):
            return {"success": True, "sessionID": f"s{len(self.calls)}"}
        if self.expire_once and path == "ADSModule/GetInstances":
            self.expire_once = False
            return {"Title": "Unauthorized Access", "Message": "session expired"}
        if path == "ADSModule/GetInstances":
            return {"result": [{"AvailableInstances": [
                {"InstanceName": "ADS01", "Module": "ADS", "Running": True, "AppState": 20},
                {"InstanceName": "Valheim01", "InstanceID": "abc", "FriendlyName": "Valheim", "Module": "GenericModule",
                 "ModuleDisplayName": "Valheim", "Running": True, "AppState": 20},
                {"InstanceName": "Mc01", "InstanceID": "def", "FriendlyName": "Minecraft", "Module": "Minecraft",
                 "Running": False, "AppState": 0}]}]}
        if path == "ADSModule/StopInstance":
            return {"Status": True}
        if path.endswith("Core/UpdateApplication"):
            return {"Status": False, "Reason": "Update already running"}
        if path.endswith("Core/GetUserList"):
            return {"result": {"u1": "Alice", "u2": "Bob"}}
        if path.endswith("Core/GetUpdates"):
            sent = any(p.endswith("SendConsoleMessage") for p, _ in self.calls)
            return {"ConsoleEntries": [{"Contents": "Kicked Alice"}] if sent else [{"Contents": "old line"}]}
        if path.endswith("Core/GetSettingsSpec"):
            return {"Server": [{"Name": "Server password", "Node": "GenericModule.App.ServerPassword"},
                               {"Name": "Steam password", "Node": "steamcmdplugin.SteamPassword"}]}
        return {"Status": True}


def test_amp_relogin_and_instances():
    amp = FakeAmp()
    insts = amp.instances()
    assert [i["name"] for i in insts] == ["Mc01", "Valheim01"]  # bez panelu ADS, po nazwie
    assert sum(1 for p, _ in amp.calls if p == "Core/Login") == 2  # wygasla sesja -> drugie logowanie
    assert bot.amp_state(insts[0], "en") == ("⚫", "instance off")
    assert bot.amp_state(insts[1], "pl") == ("🟢", "działa")


def test_servers_flow_with_confirmation(env, monkeypatch):
    edits = []
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((text, markup)))
    monkeypatch.setattr(bot, "tg_api", lambda *a, **k: {})
    monkeypatch.setattr(bot, "CHAT_ID", "1")
    c = bot.Commands(env.db, env.inst)
    c.amp = FakeAmp()
    env.write("Valheim01", f"Got connection SteamID {SID_A}", "Got character ZDOID from Alice : 111:1")
    env.sent.clear()

    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/servers"})
    buttons = [b["text"] for row in c.servers_view("en")[1]["inline_keyboard"] for b in row]
    assert "🟢 Valheim 👥1" in buttons and "⚫ Minecraft" in buttons

    def click(data):
        c.handle_callback({"id": "q", "from": {"id": 1, "first_name": "Admin"}, "data": data,
                           "message": {"chat": {"id": 1}, "message_id": 7}})
        return edits[-1]

    text, markup = click("do:stop:Valheim01")
    assert "1" in text and "⚠️" in text  # ostrzezenie, ze ktos gra
    assert not any(p.endswith("Core/Stop") for p, _ in c.amp.calls)
    text, _ = click("do!:stop:Valheim01")  # stop = sam serwer gry, instancja zostaje wlaczona
    assert any(p.endswith("/API/Core/Stop") for p, _ in c.amp.calls)
    assert not any(p == "ADSModule/StopInstance" for p, _ in c.amp.calls)
    assert "✅" in text
    click("do!:off:Valheim01")  # wylaczenie calej instancji to osobny przycisk
    assert ("ADSModule/StopInstance", {"SESSIONID": c.amp.session, "InstanceName": "Valheim01"}) in c.amp.calls
    text, _ = click("do!:update:Valheim01")
    assert "Update already running" in text
    stranger = len(edits)
    c.handle_callback({"id": "q", "from": {"id": 9}, "data": "do!:stop:Valheim01",
                       "message": {"chat": {"id": 9}, "message_id": 1}})
    assert len(edits) == stranger  # obcy nic nie zrobi


def test_servers_without_amp_config(env):
    c = bot.Commands(env.db, env.inst)
    c.amp = bot.Amp("", "", "")
    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/servers"})
    assert "AMP_URL" in env.sent[-1]


class TaskAmp(bot.Amp):
    """AMP z zadaniami: panel ADS i jedna instancja; testy zmieniaja self.ads_tasks / self.inst_tasks."""

    def __init__(self):
        super().__init__("http://amp.test", "bot", "secret")
        self.ads_tasks, self.inst_tasks = [], []
        self.app_state, self.running = 20, True

    def _post(self, path, payload, timeout=30):
        if path.endswith("Core/Login"):
            return {"success": True, "sessionID": "s"}
        if path == "ADSModule/GetInstances":
            inst = {"InstanceName": "Valheim01", "InstanceID": "abc", "FriendlyName": "Valheim",
                    "Module": "GenericModule", "Running": self.running, "AppState": self.app_state}
            return [{"AvailableInstances": [inst]}]
        if path == "Core/GetTasks":
            return self.ads_tasks
        if path == "ADSModule/Servers/abc/API/Core/GetTasks":
            return {"result": self.inst_tasks}
        return {}


@pytest.fixture
def watcher(env, monkeypatch):
    edits = []
    ids = iter(range(100, 200))

    def fake_send(text, chat_id=None, markup=None):
        env.sent.append(text)
        return next(ids)

    monkeypatch.setattr(bot, "send", fake_send)
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((mid, text)))
    w = bot.AmpWatcher(TaskAmp())
    w.check_states()  # pierwsze odczytanie stanow nic nie wysyla
    return w, edits


def test_task_progress_is_one_message_edited_in_place(watcher, env, monkeypatch):
    w, edits = watcher
    clock = [1000.0]
    monkeypatch.setattr(bot.time, "time", lambda: clock[0])
    w.amp.inst_tasks = [{"Id": "t1", "Name": "Updating Valheim", "Description": "Downloading", "ProgressPercent": 20}]
    w.check_tasks()
    assert env.sent == []  # dopiero gdy trwa dluzej niz AMP_TASK_MIN_SECONDS
    clock[0] += 20
    w.check_tasks()
    assert env.sent == ["⏳ <b>Valheim</b>: Updating Valheim\nDownloading\n▓▓░░░░░░░░ 20%"]
    w.amp.inst_tasks[0]["ProgressPercent"] = 60
    clock[0] += 3
    w.check_tasks()
    assert edits == []  # za wczesnie na kolejna edycje
    clock[0] += 10
    w.check_tasks()
    assert edits[-1] == (100, "⏳ <b>Valheim</b>: Updating Valheim\nDownloading\n▓▓▓▓▓▓░░░░ 60%")
    w.amp.inst_tasks = []
    w.check_tasks()
    assert edits[-1] == (100, "✅ <b>Valheim</b>: Updating Valheim – gotowe")
    assert len(env.sent) == 1


def test_failed_panel_task_and_indeterminate(watcher, env, monkeypatch):
    w, edits = watcher
    clock = [1000.0]
    monkeypatch.setattr(bot.time, "time", lambda: clock[0])
    w.amp.ads_tasks = [{"Id": "b", "Name": "Backup", "IsIndeterminate": True, "ProgressPercent": 0, "State": "Failed"}]
    w.check_tasks()
    clock[0] += 20
    w.check_tasks()
    assert env.sent[-1] == "⏳ <b>panel AMP</b>: Backup"
    w.amp.ads_tasks = []
    w.check_tasks()
    assert edits[-1] == (100, "❌ <b>panel AMP</b>: Backup – nie powiodło się")


def test_short_and_routine_tasks_are_silent(watcher, env, monkeypatch):
    w, edits = watcher
    clock = [1000.0]
    monkeypatch.setattr(bot.time, "time", lambda: clock[0])
    w.amp.ads_tasks = [{"Id": "r", "Name": "Updating remote sources"}, {"Id": "q", "Name": "Quick job"}]
    w.check_tasks()
    clock[0] += 60
    w.amp.ads_tasks = [{"Id": "r", "Name": "Updating remote sources"}]
    w.check_tasks()  # "Quick job" skonczyl sie po chwili, "remote sources" jest ignorowane
    clock[0] += 60
    w.amp.ads_tasks = []
    w.check_tasks()
    assert env.sent == [] and edits == []


APT = """Listing... Done
openssl/jammy-updates,jammy-security 3.0.2-0ubuntu1.15 amd64 [upgradable from: 3.0.2-0ubuntu1.14]
tailscale/unknown 1.82.0 amd64 [upgradable from: 1.80.2]
vim/jammy-updates 2:8.2.3995-1ubuntu2.18 amd64 [upgradable from: 2:8.2.3995-1ubuntu2.17]
"""


def test_updates_report_and_monitor(env, monkeypatch):
    pkgs = bot.parse_apt(APT)
    assert [(p["name"], p["security"]) for p in pkgs] == [("openssl", True), ("tailscale", False), ("vim", False)]
    amp = FakeAmp()
    text = bot.updates_report(amp, "pl", pkgs=pkgs, reboot=["linux-image-6.8"], amp_info=(True, "2.6.1"))
    assert "Pakiety do aktualizacji: 3 (bezpieczeństwa: 1)" in text and "openssl" in text and "🛡" in text
    assert "tailscale" in text and "…i 1 zwykłych" in text and "linux-image-6.8" in text and "2.6.1" in text

    monkeypatch.setattr(bot, "apt_upgradable", lambda: pkgs)
    monkeypatch.setattr(bot, "reboot_required", lambda: None)
    monkeypatch.setattr(bot, "amp_update_info", lambda a: (False, None))
    m = bot.UpdateMonitor(amp, env.db)
    m.poll()
    assert len(env.sent) == 1 and "openssl" in env.sent[0]
    m.last = 0
    m.poll()
    assert len(env.sent) == 1  # nic nowego - bez powtorki
    monkeypatch.setattr(bot, "apt_upgradable", lambda: bot.parse_apt(APT.replace("ubuntu1.15", "ubuntu1.16")))
    m.last = 0
    m.poll()
    assert len(env.sent) == 2


def test_state_changes_from_the_panel(watcher, env):
    w, _ = watcher
    w.amp.app_state = 10  # uruchamia sie - stan przejsciowy, bez wiadomosci
    w.check_states()
    assert env.sent == []
    w.amp.app_state = 0
    w.check_states()
    w.amp.app_state = 100
    w.check_states()
    assert env.sent == ["🔴 <b>Valheim</b>: zatrzymany", "❌ <b>Valheim</b>: błąd"]


def test_players_console_and_password(env, monkeypatch):
    edits, deleted = [], []
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((text, markup)))

    def fake_api(method, params=None, **kw):
        if method == "deleteMessage":
            deleted.append(params)
        return {}

    monkeypatch.setattr(bot, "tg_api", fake_api)
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    c = bot.Commands(env.db, env.inst)
    c.amp = FakeAmp()
    c.amp.expire_once = False

    def click(data):
        c.handle_callback({"id": "q", "from": {"id": 1, "first_name": "Admin"}, "data": data,
                           "message": {"chat": {"id": 1}, "message_id": 7}})
        return edits[-1]

    def console_sent():
        return [pl["message"] for p, pl in c.amp.calls if p.endswith("SendConsoleMessage")]

    text, markup = click("pl:Valheim01")
    assert "Alice" in str(markup) and "Bob" in str(markup)
    text, _ = click("pa:kick:0:Valheim01")
    assert "Alice" in text and "❓" in text and console_sent() == []
    text, _ = click("pa!:kick:0:Valheim01")
    assert console_sent() == ["kick Alice"] and "Kicked Alice" in text and "old line" not in text

    click("con:Valheim01")
    c.handle_text({"chat": {"id": 1}, "from": {"id": 1}, "text": "say hi", "message_id": 50})
    assert "say hi" in env.sent[-1] and console_sent() == ["kick Alice"]  # najpierw potwierdzenie
    click("con!:Valheim01")
    assert console_sent()[-1] == "say hi"

    text, markup = click("pw:Valheim01")
    assert "Server password" in str(markup) and "Steam" not in str(markup)
    click("pws:0:Valheim01")
    c.handle_text({"chat": {"id": 1}, "from": {"id": 1}, "text": "sekret123", "message_id": 51})
    assert deleted[-1]["message_id"] == 51 and "sekret123" not in env.sent[-1]
    text, _ = click("pw!:Valheim01")
    sets = [pl for p, pl in c.amp.calls if p.endswith("Core/SetConfig")]
    assert sets[-1]["node"] == "GenericModule.App.ServerPassword" and sets[-1]["value"] == "sekret123"
    assert "✅" in text


def test_stranger_cannot_type_into_console(env, monkeypatch):
    c = bot.Commands(env.db, env.inst)
    c.amp = FakeAmp()
    c.awaiting["9"] = {"kind": "console", "name": "Valheim01"}
    c.handle_text({"chat": {"id": 9}, "from": {"id": 9}, "text": "stop", "message_id": 1})
    assert not any(p.endswith("SendConsoleMessage") for p, _ in c.amp.calls)


def test_friend_gets_only_assigned_servers(env, monkeypatch):
    edits, menus, sent_to = [], [], []
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((text, markup)))
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent_to.append((chat_id, text, markup)))
    monkeypatch.setattr(bot, "set_menu", lambda chat, commands=None: menus.append((chat, commands)))
    monkeypatch.setattr(bot, "tg_api", lambda *a, **k: {})
    monkeypatch.setattr(bot, "CHAT_ID", "1")
    c = bot.Commands(env.db, env.inst)
    c.amp = FakeAmp()
    c.amp.expire_once = False
    friend = {"id": 42, "first_name": "Kumpel", "username": "kumpel", "language_code": "uk"}

    def click(data, user):
        c.handle_callback({"id": "q", "from": user, "data": data, "message": {"chat": {"id": user["id"]},
                                                                              "message_id": 7}})
        return edits[-1]

    c.handle({"chat": {"id": 42}, "from": friend, "text": "/start"})
    request = next(m for chat, _, m in sent_to if chat is None)
    assert request["inline_keyboard"][0][0]["callback_data"] == "fr:42"  # prosba do admina z przyciskiem

    admin = {"id": 1, "first_name": "Admin"}
    text, markup = click("fr:42", admin)
    assert "Kumpel @kumpel" in text and "⬜ Valheim" in str(markup)
    click("frt:42:1", admin)  # Valheim (po nazwie: Mc01, Valheim01)
    text, _ = click("frs:42", admin)
    assert bot.friend_get(env.db, 42)["instances"] == ["Valheim01"] and "Valheim" in text
    assert any(chat == 42 and "/servers" in msg for chat, msg, _ in sent_to)  # znajomy dostal wiadomosc...
    assert (42, bot.FRIEND_COMMANDS) in menus and bot.lang_for(42) == "uk"  # ...i swoje menu, po ukrainsku

    sent_to.clear()
    c.handle({"chat": {"id": 42}, "from": friend, "text": "/servers"})
    buttons = [b["text"] for row in sent_to[-1][2]["inline_keyboard"] for b in row]
    assert any("Valheim" in b for b in buttons) and not any("Minecraft" in b for b in buttons)
    env.db.execute("INSERT INTO sessions(instance, game, username, joined, left) VALUES "
                   "('Valheim01','Valheim','Viking',1,2), ('Mc01','Minecraft','Steve',3,4)")
    c.handle({"chat": {"id": 42}, "from": friend, "text": "/history"})
    assert "Viking" in sent_to[-1][1] and "Steve" not in sent_to[-1][1]  # tylko jego serwery
    c.handle({"chat": {"id": 42}, "from": friend, "text": "/player Steve"})
    assert "☰" in sent_to[-1][1] and "Steve" not in sent_to[-1][1]  # komendy admina - nie dla znajomego

    text, markup = click("srv:Valheim01", friend)
    assert "pw:Valheim01" not in str(markup)  # bez hasel
    n = len(edits)
    click("srv:Mc01", friend)
    click("pw:Valheim01", friend)
    click("frl", friend)
    assert len(edits) == n  # cudzy serwer, hasla i /friends - nic sie nie dzieje

    sent_to.clear()
    click("do!:stop:Valheim01", friend)
    assert any(p.endswith("/API/Core/Stop") for p, _ in c.amp.calls)
    assert any(chat is None and "Kumpel" in msg for chat, msg, _ in sent_to)  # admin widzi, co zrobil

    assert "con:Valheim01" not in str(click("srv:Valheim01", friend)[1])  # konsola tylko dla admina
    c.awaiting["42"] = {"kind": "console", "name": "Valheim01"}
    c.handle_text({"chat": {"id": 42}, "from": friend, "text": "op Kumpel", "message_id": 5})
    click("con!:Valheim01", friend)
    assert not [p for p, _ in c.amp.calls if p.endswith("SendConsoleMessage")]

    click("fr:42", admin)
    click("frd:42", admin)
    assert bot.friend_get(env.db, 42) is None
    n = len(edits)
    click("srv:Valheim01", friend)
    assert len(edits) == n  # po usunieciu - znowu obcy


class SettingsAmp(FakeAmp):
    def __init__(self):
        super().__init__()
        self.expire_once = False

    def _post(self, path, payload, timeout=30):
        if path.endswith("Core/GetSettingsSpec"):
            self.calls.append((path, payload))
            return {"result": {
                "Minecraft:Server": [
                    {"Name": "Difficulty", "Node": "MinecraftModule.Game.Difficulty", "InputType": "enum",
                     "EnumValues": {"0": "Peaceful", "1": "Easy", "2": "Normal", "3": "Hard"}, "CurrentValue": "2"},
                    {"Name": "PvP", "Node": "MinecraftModule.Game.PVP", "InputType": "checkbox", "CurrentValue": True},
                    {"Name": "Message of the day", "Node": "MinecraftModule.Server.MOTD", "InputType": "text",
                     "CurrentValue": "Hello"},
                    {"Name": "Server password", "Node": "MinecraftModule.Server.Password", "InputType": "password"}],
                "AMP:Instance": [{"Name": "Web port", "Node": "Core.Webserver.Port", "InputType": "number"}],
                "Minecraft:Version": [
                    {"Name": "Server type", "Node": "MinecraftModule.Minecraft.ServerType", "InputType": "enum",
                     "EnumValues": {"Vanilla": "Vanilla", "Forge": "Forge"}, "CurrentValue": "Forge"}]}}
        return super()._post(path, payload, timeout)


def test_settings_editor(env, monkeypatch):
    edits, sent_to = [], []
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((text, markup)))
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent_to.append((chat_id, text, markup)))
    monkeypatch.setattr(bot, "tg_api", lambda *a, **k: {})
    monkeypatch.setattr(bot, "CHAT_ID", "1")
    c = bot.Commands(env.db, env.inst)
    c.amp = SettingsAmp()
    bot.friend_set(env.db, 42, "Kumpel", ["Valheim01"])
    admin = {"id": 1, "first_name": "Admin"}
    friend = {"id": 42, "first_name": "Kumpel"}

    def click(data, user=admin):
        c.handle_callback({"id": "q", "from": user, "data": data, "message": {"chat": {"id": user["id"]},
                                                                              "message_id": 7}})
        return edits[-1]

    def sets():
        return [(pl["node"], pl["value"]) for p, pl in c.amp.calls if p.endswith("Core/SetConfig")]

    text, markup = click("srv:Valheim01")
    assert "st:Valheim01" in str(markup)
    text, markup = click("st:Valheim01")
    labels = [b["text"] for row in markup["inline_keyboard"] for b in row]
    assert "Minecraft › Server (3)" in labels and not any("AMP" in x for x in labels)  # bez hasel i Core.*
    text, markup = click("stc:0:0:Valheim01")
    assert "Difficulty: Normal" in str(markup) and "PvP: ✅" in str(markup)

    text, markup = click("sti:0:0:Valheim01")
    assert "• Normal" in str(markup)
    text, _ = click("stv:0:0:3:Valheim01")
    assert sets()[-1] == ("MinecraftModule.Game.Difficulty", "3") and "Normal → Hard" in text

    click("sti:0:1:Valheim01")
    click("stv:0:1:0:Valheim01")
    assert sets()[-1] == ("MinecraftModule.Game.PVP", "false")

    click("stw:0:2:Valheim01")
    c.handle_text({"chat": {"id": 1}, "from": admin, "text": "Witajcie!", "message_id": 9})
    assert sets()[-1] == ("MinecraftModule.Server.MOTD", "Witajcie!") and "Hello → Witajcie!" in sent_to[-1][1]

    text, _ = click("stv:1:0:0:Valheim01")  # Forge -> Vanilla
    assert sets()[-1] == ("MinecraftModule.Minecraft.ServerType", "Vanilla") and "⬆️" in text

    click("sts:Valheim01", friend)  # znajomy na swoim serwerze: tak
    c.handle_text({"chat": {"id": 42}, "from": friend, "text": "motd", "message_id": 10})
    assert "Message of the day" in str(sent_to[-1][2])
    assert len(sets()) == 4  # wyszukiwanie niczego nie zmienia
    n = len(edits)
    click("st:Mc01", friend)  # cudzy serwer: nie
    assert len(edits) == n


HELD = """Reading package lists... Done
Calculating upgrade... Done
The following upgrades have been deferred due to phasing:
  tailscale
The following packages have been kept back:
  linux-image-generic linux-generic
The following packages will be upgraded:
  openssl vim
"""


def test_updates_fresh_lists_and_held_packages(env, monkeypatch, tmp_path):
    calls = []

    class Done:
        def __init__(self, out="", code=0):
            self.stdout, self.returncode = out, code

    def fake_run(args, **kw):
        calls.append(args)
        if args[:2] == ["apt-get", "update"]:
            return Done()
        if args[:2] == ["apt", "list"]:
            return Done(APT)
        return Done(HELD)

    monkeypatch.setattr(bot, "APT_DIR", str(tmp_path / "apt"))
    monkeypatch.setattr(bot.subprocess, "run", fake_run)
    pkgs = bot.apt_upgradable()
    assert calls[0][:2] == ["apt-get", "update"] and f"Dir::State::Lists={tmp_path / 'apt'}/lists" in calls[0]
    assert all(f"Dir::State::Lists={tmp_path / 'apt'}/lists" in c for c in calls)  # list i symulacja z tych list
    assert [(p["name"], p["held"]) for p in pkgs] == [("openssl", False), ("tailscale", True), ("vim", False)]
    text = bot.updates_report(FakeAmp(), "pl", pkgs=pkgs, reboot=None, amp_info=(False, None))
    assert "Pakiety do aktualizacji: 2 (bezpieczeństwa: 1)" in text and "⏸" in text and "tailscale" in text
    assert "⚠️" not in text

    monkeypatch.setattr(bot, "apt_refresh", lambda: False)  # bez sieci: dane systemowe, z data
    bot.apt_upgradable()
    assert "⚠️" in bot.updates_report(FakeAmp(), "pl", pkgs=pkgs, reboot=None, amp_info=(False, None))


def test_unban(env, monkeypatch):
    edits, sent_to = [], []
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((text, markup)))
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent_to.append((chat_id, text, markup)))
    monkeypatch.setattr(bot, "tg_api", lambda *a, **k: {})
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    monkeypatch.setattr(bot, "CHAT_ID", "1")
    c = bot.Commands(env.db, env.inst)
    c.amp = FakeAmp()
    c.amp.expire_once = False
    admin = {"id": 1, "first_name": "Admin"}

    def click(data, user=admin):
        c.handle_callback({"id": "q", "from": user, "data": data, "message": {"chat": {"id": user["id"]},
                                                                              "message_id": 7}})
        return edits[-1]

    def console_sent():
        return [pl["message"] for p, pl in c.amp.calls if p.endswith("SendConsoleMessage")]

    text, markup = click("pl:Valheim01")
    assert "ub:Valheim01" in str(markup)
    click("ub:Valheim01")
    c.handle_text({"chat": {"id": 1}, "from": admin, "text": "Griefer", "message_id": 3})
    assert "Griefer" in sent_to[-1][1] and console_sent() == []  # najpierw potwierdzenie
    click("ub!:Valheim01")
    assert console_sent() == ["unban Griefer"]

    c.amp.instances()  # Mc01 = Minecraft -> pardon
    c.handle({"chat": {"id": 1}, "from": admin, "text": "/unban Steve"})
    assert "ub!:Mc01" in str(sent_to[-1][2])
    click("ub!:Mc01")
    assert console_sent()[-1] == "pardon Steve"

    bot.friend_set(env.db, 42, "Kumpel", ["Valheim01"])
    friend = {"id": 42, "first_name": "Kumpel"}
    c.handle({"chat": {"id": 42}, "from": friend, "text": "/unban Bob"})  # wpisana komenda dalej dziala
    assert "ub!:Valheim01" in str(sent_to[-1][2]) and "Mc01" not in str(sent_to[-1][2])  # tylko jego serwery
    assert "unban" not in [c for c, _ in bot.COMMANDS + bot.FRIEND_COMMANDS]  # ale nie ma jej w menu
    n = len(console_sent())
    click("ub!:Mc01", friend)
    assert len(console_sent()) == n



def test_dota_ids():
    assert bot.dota_account_id("86745912") == 86745912
    assert bot.dota_account_id("76561198047011640") == 86745912  # SteamID64
    assert bot.dota_account_id("https://www.opendota.com/players/86745912/matches") == 86745912
    assert bot.dota_account_id("https://steamcommunity.com/profiles/76561198047011640/") == 86745912
    assert bot.dota_account_id("https://steamcommunity.com/id/somename") is None
    assert bot.dota_rank({"rank_tier": 54}) == "Legend 4"
    assert bot.dota_rank({"rank_tier": 80, "leaderboard_rank": 812}) == "Immortal #812"
    assert bot.dota_rank({}, "en") == "unranked"


def test_dota_watch(env, monkeypatch):
    matches = [{"match_id": 100, "player_slot": 1, "radiant_win": True, "hero_id": 1, "kills": 1, "deaths": 2,
                "assists": 3, "gold_per_min": 400, "xp_per_min": 500, "duration": 1800, "game_mode": 22,
                "lobby_type": 7, "start_time": 1_700_000_000}]
    api = {"players/42": {"profile": {"personaname": "Pudge Fan"}, "rank_tier": 35},
           "players/42/recentMatches": matches, "constants/heroes": {"1": {"localized_name": "Anti-Mage"}},
           "players/7": {"profile": None}, "players/7/recentMatches": [],
           "players/9": {"profile": {"personaname": "Private"}}, "players/9/recentMatches": []}
    monkeypatch.setattr(bot, "opendota", lambda path: api[path])
    c = bot.Commands(env.db, env.inst)
    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/dota"})
    assert "Friend ID" in env.sent[-1]
    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/dota add https://www.opendota.com/players/42"})
    assert "Pudge Fan" in env.sent[-1] and "Crusader 5" in env.sent[-1]
    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/dota add 7"})
    assert "7" in env.sent[-1] and "❌" in env.sent[-1]
    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/dota add 9"})
    assert "Expose Public Match Data" in env.sent[-1]

    w = bot.DotaWatcher(env.db)
    env.sent.clear()
    w.poll()
    assert env.sent == []  # mecz sprzed dodania nie jest nowy
    matches.append({**matches[0], "match_id": 101, "player_slot": 130, "kills": 9})  # Dire, Radiant wygrywa
    w.last = 0
    w.poll()
    assert len(env.sent) == 1 and "Pudge Fan" in env.sent[0] and "Przegrana" in env.sent[0]
    assert "Anti-Mage" in env.sent[0]
    assert "KDA 9/2/3" in env.sent[0] and "rankingowy" in env.sent[0] and "matches/101" in env.sent[0]
    w.last = 0
    w.poll()
    assert len(env.sent) == 1  # bez powtorki



def test_separate_friends_bot(env, monkeypatch):
    """Z TG_FRIENDS_TOKEN glowny bot jest tylko admina, a znajomi pisza do drugiego bota."""
    api_calls, edits = [], []
    monkeypatch.setattr(bot, "FRIENDS_TOKEN", "FRIENDS")
    monkeypatch.setattr(bot, "TOKEN", "MAIN")
    monkeypatch.setattr(bot, "CHAT_ID", "1")
    monkeypatch.setattr(bot, "send", REAL_SEND)
    monkeypatch.setattr(bot, "tg_api", lambda method, params=None, timeout=10, token=None: api_calls.append(
        (method, (params or {}).get("chat_id"), token or bot.BOT["token"] or bot.TOKEN, (params or {}).get("text", "")))
        or {"result": {"message_id": 1}})
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((text, markup)))
    c = bot.Commands(env.db, env.inst)
    c.amp = FakeAmp()
    c.amp.expire_once = False
    friend = {"id": 42, "first_name": "Kumpel", "language_code": "pl"}
    admin = {"id": 1, "first_name": "Admin"}

    c.handle({"chat": {"id": 42}, "from": friend, "text": "/start"})  # do glownego bota: nic
    sent = [(chat, token, text) for m, chat, token, text in api_calls if m == "sendMessage"]
    assert ("➕" not in str(api_calls)) and any(chat == 42 and token == "MAIN" and "prywatny" in text
                                                for chat, token, text in sent)

    api_calls.clear()
    with bot.via("FRIENDS"):
        c.friend_bot = True
        c.handle({"chat": {"id": 42}, "from": friend, "text": "/start"})  # do bota znajomych: najpierw jezyk
        assert "Choose a language" in api_calls[-1][3] and not any(chat == "1" for _, chat, _, _ in api_calls)
        c.handle_callback({"id": "q", "from": friend, "data": "lang:uk", "message": {"chat": {"id": 42},
                                                                                   "message_id": 3}})
        c.friend_bot = False
    assert bot.lang_for(42) == "uk" and json.loads(bot.meta_get(env.db, "who:42"))["lang"] == "uk"
    sent = [(chat, token, text) for m, chat, token, text in api_calls if m == "sendMessage"]
    assert any(chat == 42 and "власник" in text for chat, _, text in sent)  # prosba potwierdzona po ukrainsku
    assert any(chat == "1" and token == "MAIN" for chat, token, _ in sent)  # prosba do admina glownym botem
    assert any(chat == 42 and token == "FRIENDS" for chat, token, _ in sent)  # odpowiedz botem znajomych

    api_calls.clear()
    c.handle_callback({"id": "q", "from": admin, "data": "fr:42", "message": {"chat": {"id": 1}, "message_id": 7}})
    c.handle_callback({"id": "q", "from": admin, "data": "frt:42:1", "message": {"chat": {"id": 1}, "message_id": 7}})
    c.handle_callback({"id": "q", "from": admin, "data": "frs:42", "message": {"chat": {"id": 1}, "message_id": 7}})
    granted = [(chat, token) for m, chat, token, text in api_calls if m == "sendMessage" and "/servers" in text]
    assert granted == [(42, "FRIENDS")]  # wiadomosc o dostepie przychodzi od bota znajomych
    assert any(m == "setMyCommands" and token == "FRIENDS" for m, _, token, _ in api_calls)

    c.handle({"chat": {"id": 42}, "from": friend, "text": "/servers"})  # glowny bot dalej nie jego
    assert not any("Valheim" in text for m, chat, token, text in api_calls if token == "MAIN" and chat == 42)


def test_dota_rank_daily_and_private_players(env, monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(bot.time, "time", lambda: clock[0])
    calls = []
    api = {"players/5": {"profile": {"personaname": "Hidden"}, "rank_tier": 44}, "players/5/recentMatches": [],
           "players/5/refresh": {}}

    def fake(path, post=False):
        calls.append(path)
        return api[path]

    monkeypatch.setattr(bot, "opendota", fake)
    c = bot.Commands(env.db, env.inst)
    c.handle({"chat": {"id": 1}, "from": {"id": 1}, "text": "/dota add 5"})
    w = bot.DotaWatcher(env.db)
    calls.clear()
    clock[0] += 3600
    w.poll()
    assert calls == []  # bez publicznych meczow i ranga sprawdzona przy dodaniu: nic przez dobe
    api["players/5"] = {"profile": {"personaname": "Hidden"}, "rank_tier": 45}
    env.sent.clear()
    clock[0] += 86400
    w.poll()
    assert "players/5/refresh" in calls and "players/5/recentMatches" in calls
    assert env.sent == ["📈 <b>Hidden</b>: Archon 4 → Archon 5"]


def test_same_task_twice_is_one_message(watcher, env, monkeypatch):
    w, edits = watcher
    clock = [1000.0]
    monkeypatch.setattr(bot.time, "time", lambda: clock[0])
    task = {"Name": "Starting Instance", "Description": "Starting Valheim", "IsIndeterminate": True}
    w.amp.ads_tasks = [{**task, "Id": "a"}, {**task, "Id": "b"}]
    w.check_tasks()
    clock[0] += 20
    w.amp.ads_tasks = [{**task, "Id": "c"}]  # i jeszcze nowe Id w trakcie
    w.check_tasks()
    assert sum("Starting Instance" in m for m in env.sent) == 1



class StateAmp(FakeAmp):
    """Instancja, ktorej stan zmienia test: running + AppState."""

    def __init__(self):
        super().__init__()
        self.expire_once = False
        self.running, self.app_state = False, -1

    def _post(self, path, payload, timeout=30):
        if path == "ADSModule/GetInstances":
            self.calls.append((path, payload))
            return {"result": [{"AvailableInstances": [
                {"InstanceName": "Valheim01", "InstanceID": "abc", "FriendlyName": "Valheim", "Module": "GenericModule",
                 "Running": self.running, "AppState": self.app_state}]}]}
        if path.endswith("Core/GetTasks"):
            return {"result": []}
        return super()._post(path, payload, timeout)


def test_start_from_offline_with_progress_message(env, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(bot.time, "time", lambda: clock[0])
    edits, sent_to = [], []
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((chat, mid, text)))
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent_to.append((chat_id, text)) or 77)
    monkeypatch.setattr(bot, "tg_api", lambda *a, **k: {})
    c = bot.Commands(env.db, env.inst)
    c.amp = StateAmp()
    w = bot.AmpWatcher(c.amp)
    c.watcher = w

    def click(data):
        c.handle_callback({"id": "q", "from": {"id": 1, "first_name": "Admin"}, "data": data,
                           "message": {"chat": {"id": 1}, "message_id": 7}})
        return edits[-1][2]

    view = click("srv:Valheim01")
    assert "do:start:Valheim01" not in view  # widok to tekst; przyciski sprawdzamy nizej
    _, markup = c.server_view("Valheim01", "pl")
    labels = [b["text"] for row in markup["inline_keyboard"] for b in row]
    assert "▶️ Uruchom serwer" in labels and "⏻ Włącz instancję" in labels  # offline: serwer albo sama instancja

    click("do:start:Valheim01")
    assert ("ADSModule/StartInstance", {"SESSIONID": c.amp.session, "InstanceName": "Valheim01"}) in c.amp.calls
    assert sent_to[-1][0] == 1 and "Uruchom serwer" in sent_to[-1][1]  # wiadomosc z postepem
    click("do:start:Valheim01")  # drugie klikniecie
    assert "Już trwa" in edits[-1][2]
    assert sum(1 for p, _ in c.amp.calls if p == "ADSModule/StartInstance") == 1

    c.amp.running, c.amp.app_state = True, 0  # instancja wstala, gra jeszcze nie
    clock[0] += 10
    w.poll()
    assert any(p.endswith("/API/Core/Start") for p, _ in c.amp.calls)  # bot sam uruchamia gre
    c.amp.app_state = 20
    clock[0] += 30
    w.poll()
    assert "✅" in edits[-1][2] and edits[-1][1] == 77 and "Valheim" in edits[-1][2]
    assert w.ops == {}

    _, markup = c.server_view("Valheim01", "pl")
    labels = [b["text"] for row in markup["inline_keyboard"] for b in row]
    assert "⏹ Zatrzymaj serwer" in labels and "⏻ Wyłącz instancję" in labels


def test_failed_start_shows_console(env, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(bot.time, "time", lambda: clock[0])
    edits = []
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append(text))
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: 5)
    amp = StateAmp()
    amp.running, amp.app_state = True, 0
    w = bot.AmpWatcher(amp)
    w.track("Valheim01", "update", 1, "pl")
    amp.app_state = 100
    clock[0] += 10
    w.poll()
    assert "❌" in edits[-1] and "konsoli" in edits[-1] and w.ops == {}



@pytest.fixture
def mod_instances(tmp_path, monkeypatch):
    """Instancje jak na serwerze: Minecraft z Forge i Valheim z BepInEx."""
    root = tmp_path / "amp"
    (root / "Mc01" / "Minecraft" / "mods").mkdir(parents=True)
    (root / "Mc01" / "Minecraft" / "libraries" / "net" / "minecraftforge" / "forge" / "1.20.1-47.2.0").mkdir(
        parents=True)
    (root / "Mc01" / "Minecraft" / "mods" / "jei-1.20.1.jar").write_bytes(b"jar")
    plugins = root / "Valheim01" / "Valheim" / "896660" / "BepInEx" / "plugins"
    plugins.mkdir(parents=True)
    (root / "Terraria01" / "Plugins").mkdir(parents=True)
    monkeypatch.setattr(bot, "INSTANCES_DIR", str(root))
    return root, plugins


def test_mod_targets(mod_instances):
    root, plugins = mod_instances
    mc = bot.mod_target("Mc01")
    assert (mc["loader"], mc["version"], mc["dir"]) == ("forge", "1.20.1", str(root / "Mc01" / "Minecraft" / "mods"))
    v = bot.mod_target("Valheim01")
    assert v["dir"] == str(plugins) and v["community"] == "valheim"
    assert bot.mod_target("Terraria01") is None
    assert bot.installed_mods(mc) == [("jei-1.20.1", "jei-1.20.1.jar")]


def test_bepinex_zip_layout(mod_instances, tmp_path):
    _, plugins = mod_instances
    bepinex = plugins.parent
    (bepinex / "config").mkdir()
    (bepinex / "config" / "mine.cfg").write_text("my settings")
    z = tmp_path / "pkg.zip"
    import zipfile
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("manifest.json", '{"name": "EpicLoot", "version_number": "0.14.13"}')
        f.writestr("icon.png", "x")
        f.writestr("plugins/EpicLoot.dll", "dll")
        f.writestr("config/mine.cfg", "theirs")
        f.writestr("config/new.cfg", "new")
        f.writestr("../evil.txt", "no")
    bot.install_bepinex_zip(str(z), str(plugins), "RandyKnapp-EpicLoot")
    assert (plugins / "RandyKnapp-EpicLoot" / "EpicLoot.dll").read_text() == "dll"
    assert (bepinex / "config" / "mine.cfg").read_text() == "my settings"  # twoja konfiguracja zostaje
    assert (bepinex / "config" / "new.cfg").exists() and not (plugins / "RandyKnapp-EpicLoot" / "icon.png").exists()
    assert not (bepinex.parent.parent / "evil.txt").exists()
    assert bot.installed_mods(bot.mod_target("Valheim01")) == [("EpicLoot 0.14.13", "RandyKnapp-EpicLoot")]


def test_mod_sources_with_dependencies(monkeypatch, mod_instances):
    api = {
        "/project/jei/version": [{"name": "JEI 15", "files": [{"filename": "jei.jar", "url": "u1", "primary": True}],
                                  "dependencies": [{"project_id": "lib", "dependency_type": "required"},
                                                   {"project_id": "opt", "dependency_type": "optional"}]}],
        "/project/lib/version": [{"name": "Lib", "files": [{"filename": "lib.jar", "url": "u2", "primary": True}],
                                  "dependencies": []}],
        "/package/RandyKnapp/EpicLoot/": {"latest": {"download_url": "z1", "version_number": "0.14",
                                                     "dependencies": ["denikson-BepInExPack_Valheim-5.4",
                                                                      "ValheimModding-Jotunn-2.30"]}},
        "/package/ValheimModding/Jotunn/": {"latest": {"download_url": "z2", "version_number": "2.30",
                                                       "dependencies": ["denikson-BepInExPack_Valheim-5.4"]}},
    }

    def fake(url, timeout=30):
        key = next(k for k in api if k in url)
        if "version" in key:
            assert "forge" in url and "1.20.1" in url  # pod loader i wersje serwera
        return api[key]

    monkeypatch.setattr(bot, "http_json", fake)
    target = bot.mod_target("Mc01")
    assert bot.modrinth_files("jei", target) == [("jei.jar", "u1", "JEI 15"), ("lib.jar", "u2", "Lib")]
    assert [p for p, _, _ in bot.thunderstore_files("RandyKnapp/EpicLoot")] == [
        "RandyKnapp-EpicLoot", "ValheimModding-Jotunn"]  # bez BepInExPack - instaluje go AMP
    assert bot.mod_from_text("https://thunderstore.io/c/valheim/p/RandyKnapp/EpicLoot/", bot.mod_target(
        "Valheim01")) == ("id", "RandyKnapp/EpicLoot")
    assert bot.mod_from_text("https://modrinth.com/mod/jei", target) == ("id", "jei")


def test_mods_admin_only_with_upload_and_bin(env, mod_instances, monkeypatch):
    root, _ = mod_instances
    edits, sent_to = [], []
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((text, markup)))
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent_to.append((chat_id, text, markup)))
    monkeypatch.setattr(bot, "tg_api", lambda method, params=None, timeout=10, token=None: {
        "result": {"file_path": "documents/f.jar"}} if method == "getFile" else {})
    monkeypatch.setattr(bot, "http_download", lambda url, dest: open(dest, "wb").write(b"newjar"))
    c = bot.Commands(env.db, env.inst)
    c.amp = FakeAmp()
    c.amp.expire_once = False
    admin = {"id": 1, "first_name": "Admin"}
    friend = {"id": 42, "first_name": "Kumpel"}
    bot.friend_set(env.db, 42, "Kumpel", ["Mc01"])

    def click(data, user=admin):
        c.handle_callback({"id": "q", "from": user, "data": data, "message": {"chat": {"id": user["id"]},
                                                                              "message_id": 7}})
        return edits[-1]

    assert "md:Mc01" in str(click("srv:Mc01")[1])
    n = len(edits)
    assert "md:Mc01" not in str(click("srv:Mc01", friend)[1])  # znajomy nie widzi modow...
    click("md:Mc01", friend)
    click("mda:Mc01", friend)
    assert len(edits) == n + 1  # ...i nie wejdzie w nie przyciskiem

    text, markup = click("md:Mc01")
    assert "Minecraft 1.20.1 · forge" in text and "jei-1.20.1" in str(markup)
    click("mda:Mc01")
    c.handle_document({"chat": {"id": 1}, "from": admin, "document": {"file_id": "F", "file_name": "create.jar"}})
    assert (root / "Mc01" / "Minecraft" / "mods" / "create.jar").read_bytes() == b"newjar"
    assert "create.jar" in sent_to[-1][1] and "🔁" in sent_to[-1][1]

    text, markup = click("md:Mc01")
    idx = next(i for i, row in enumerate(markup["inline_keyboard"]) if "jei" in row[0]["text"])
    click(f"mdr:{idx}:Mc01")
    assert not (root / "Mc01" / "Minecraft" / "mods" / "jei-1.20.1.jar").exists()
    assert len(list((root / "Mc01" / "Minecraft" / ".tg-trash").iterdir())) == 1  # do kosza, nie na zawsze



def test_friend_settings_and_console_injection(env, monkeypatch):
    edits, sent_to = [], []
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((text, markup)))
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent_to.append((chat_id, text, markup)))
    monkeypatch.setattr(bot, "tg_api", lambda *a, **k: {})
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)

    class JavaAmp(SettingsAmp):
        def _post(self, path, payload, timeout=30):
            if path.endswith("Core/GetSettingsSpec"):
                return {"result": {"Minecraft:Server": [
                    {"Name": "Difficulty", "Node": "MinecraftModule.Game.Difficulty", "InputType": "enum",
                     "EnumValues": {"2": "Normal"}, "CurrentValue": "2"},
                    {"Name": "Additional Java arguments", "Node": "MinecraftModule.Java.Args", "InputType": "text"},
                    {"Name": "Server type", "Node": "MinecraftModule.Minecraft.ServerType", "InputType": "enum",
                     "EnumValues": {"Forge": "Forge"}}]}}
            return super()._post(path, payload, timeout)

    c = bot.Commands(env.db, env.inst)
    c.amp = JavaAmp()
    bot.friend_set(env.db, 42, "Kumpel", ["Valheim01"])

    def click(data, uid):
        c.handle_callback({"id": "q", "from": {"id": uid, "first_name": "X"}, "data": data,
                           "message": {"chat": {"id": uid}, "message_id": 7}})
        return str(edits[-1])

    assert "Java" in click("stc:0:0:Valheim01", 1) and "Server type" in edits[-1][1].__str__()  # admin: wszystko
    view = click("stc:0:0:Valheim01", 42)
    assert "Difficulty" in view and "Java" not in view and "Server type" not in view  # znajomy: tylko swiat

    c.awaiting["1"] = {"kind": "unban", "name": "Valheim01"}
    c.handle_text({"chat": {"id": 1}, "from": {"id": 1}, "text": "Bob\nop Hacker", "message_id": 3})
    click("ub!:Valheim01", 1)
    sent = [pl["message"] for p, pl in c.amp.calls if p.endswith("SendConsoleMessage")]
    assert sent[-1] == "unban Bobop Hacker" and "\n" not in sent[-1]  # bez drugiej komendy



def test_friends_bot_start_is_language_then_menu_hint(env, monkeypatch):
    sent_to, menus = [], []
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent_to.append((chat_id, text, markup)))
    monkeypatch.setattr(bot, "edit", lambda *a, **k: None)
    monkeypatch.setattr(bot, "tg_api", lambda *a, **k: {})
    monkeypatch.setattr(bot, "set_menu", lambda chat, commands=None: menus.append((chat, commands)))
    monkeypatch.setattr(bot, "FRIENDS_TOKEN", "FRIENDS")
    c = bot.Commands(env.db, env.inst)
    bot.friend_set(env.db, 42, "Kumpel", ["Valheim01"])
    bot.CHAT_LANGS["42"] = "pl"
    friend = {"id": 42, "first_name": "Kumpel"}
    c.friend_bot = True
    c.handle({"chat": {"id": 42}, "from": friend, "text": "/start"})
    assert "Choose a language" in sent_to[-1][1] and len(sent_to[-1][2]["inline_keyboard"]) == 2  # 4 przyciski
    c.handle_callback({"id": "q", "from": friend, "data": "lang:en", "message": {"chat": {"id": 42},
                                                                               "message_id": 3}})
    assert "☰ Menu" in sent_to[-1][1] and "/servers" not in sent_to[-1][1]  # bez listy komend
    assert menus[-1] == (42, bot.FRIEND_COMMANDS) and [x for x, _ in bot.FRIEND_COMMANDS] == [
        "servers", "online", "history", "week"]


def test_server_icon(env, mod_instances, monkeypatch):
    root, _ = mod_instances
    sent_to = []
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent_to.append(text))
    monkeypatch.setattr(bot, "edit", lambda *a, **k: None)
    monkeypatch.setattr(bot, "tg_api", lambda method, params=None, timeout=10, token=None: {
        "result": {"file_path": "x.png"}})
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (64).to_bytes(4, "big") + (64).to_bytes(4, "big")
           + b"rest")
    monkeypatch.setattr(bot, "http_download", lambda url, dest: open(dest, "wb").write(png))
    c = bot.Commands(env.db, env.inst)
    c.amp = FakeAmp()
    c.amp.expire_once = False
    bot.friend_set(env.db, 42, "Kumpel", ["Mc01"])
    friend = {"id": 42, "first_name": "Kumpel"}
    _, markup = c.server_view("Mc01", "pl")
    assert "ic:Mc01" in str(markup)
    c.scope = {"Mc01"}
    _, markup = c.server_view("Mc01", "pl")
    assert "ic:Mc01" in str(markup) and "md:Mc01" not in str(markup)  # znajomy: ikona tak, mody nie
    c.awaiting["42"] = {"kind": "icon", "name": "Mc01"}
    c.handle_document({"chat": {"id": 42}, "from": friend, "document": {"file_id": "F", "file_name": "i.png"}})
    assert (root / "Mc01" / "Minecraft" / "server-icon.png").read_bytes() == png
    assert bot.png_size(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (32).to_bytes(4, "big") * 2) == (32, 32)
    monkeypatch.setattr(bot, "can_resize", lambda: False)
    try:
        bot.make_icon(b"\xff\xd8 jpeg")
        raise AssertionError("JPEG without Pillow must be refused")
    except bot.ModError as e:
        assert "64×64" in str(e)


# ---------- 2.4.0: ostrzezenia graczy, padniecia, kopie, nowe instancje, aktualizacje, subskrypcje, most ----------

class GameAmp(bot.Amp):
    """AMP bez sieci z ustawianymi instancjami, konsola, kopiami i lista gier; zapisuje wywolania."""

    def __init__(self):
        super().__init__("http://amp.test", "bot", "secret")
        self.calls = []
        self.insts = {"Valheim01": {"id": "abc", "friendly": "Valheim", "module": "Valheim", "running": True,
                                    "state": 20},
                      "Mc01": {"id": "def", "friendly": "Minecraft", "module": "Minecraft", "running": True,
                               "state": 20}}
        self.console_lines = ["old line"]
        self.backup_list, self.apps_list = [], []

    def _post(self, path, payload, timeout=30):
        self.calls.append((path, payload))
        if path.endswith("Core/Login"):
            return {"success": True, "sessionID": "s"}
        if path == "ADSModule/GetInstances":
            return {"result": [{"InstanceId": "ads-guid", "CanCreate": True, "AvailableInstances": [
                {"InstanceName": n, "InstanceID": i["id"], "FriendlyName": i["friendly"], "Module": "GenericModule",
                 "ModuleDisplayName": i["module"], "Running": i["running"], "AppState": i["state"],
                 "Metrics": i.get("metrics", {})}
                for n, i in self.insts.items()]}]}
        if path.endswith("Core/GetUpdates"):
            return {"ConsoleEntries": [{"Contents": x} for x in self.console_lines]}
        if path.endswith("Core/GetTasks"):
            return {"result": []}
        if path.endswith("LocalFileBackupPlugin/GetBackups"):
            return {"result": self.backup_list}
        if path == "ADSModule/GetSupportedApplications":
            return {"result": self.apps_list}
        if path == "ADSModule/GetApplicationEndpoints":
            return {"result": [{"DisplayName": "Game", "Endpoint": "0.0.0.0:2456"}]}
        return {"Status": True}

    def sent(self, method):
        return [(p, pl) for p, pl in self.calls if p.endswith(method)]

    def console(self, *a, **k):  # konsola bez czekania 2 s
        return super().console(*a, **{**k, "wait": 0})


@pytest.fixture
def ui(env, monkeypatch):
    """Commands + AmpWatcher na GameAmp, zegar, przechwycone edycje i wiadomosci (z czatem i przyciskami)."""
    clock = [1000.0]
    monkeypatch.setattr(bot.time, "time", lambda: clock[0])
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    edits, sent_to = [], []
    ids = iter(range(500, 900))
    monkeypatch.setattr(bot, "edit", lambda chat, mid, text, markup=None: edits.append((chat, mid, text, markup)))
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent_to.append(
        (chat_id, text, markup)) or next(ids))
    monkeypatch.setattr(bot, "tg_api", lambda *a, **k: {})
    monkeypatch.setattr(bot, "CHAT_ID", "1")
    monkeypatch.setattr(bot, "FRIENDLY", {})
    c = bot.Commands(env.db, env.inst)
    c.amp = GameAmp()
    c.watcher = bot.AmpWatcher(c.amp, env.db)

    class UI:
        pass

    u = UI()
    u.c, u.amp, u.w, u.clock, u.edits, u.sent = c, c.amp, c.watcher, clock, edits, sent_to

    def click(data, user=None):
        user = user or {"id": 1, "first_name": "Admin"}
        c.handle_callback({"id": "q", "from": user, "data": data, "message": {"chat": {"id": user["id"]},
                                                                              "message_id": 7}})
        return edits[-1][2], edits[-1][3]

    def say():
        return [pl["message"] for _, pl in u.amp.sent("SendConsoleMessage")]

    u.click, u.say = click, say
    return u


def test_players_get_warning_and_countdown_before_restart(env, ui):
    env.write("Mc01", "[12:00:00] [Server thread/INFO]: Steve joined the game")
    env.write("Valheim01", f"Got connection SteamID {SID_A}", "Got character ZDOID from Alice : 111:1")
    text, markup = ui.click("do:restart:Mc01")
    assert "dw:restart:Mc01" in str(markup) and "do!:restart:Mc01" in str(markup)  # z ostrzezeniem albo od razu
    text, markup = ui.click("do:restart:Valheim01")
    assert "nie przyjmuje" in text and "dw:" not in str(markup)  # serwer Valheima nie ma konsoli

    text, _ = ui.click("dw:restart:Mc01")
    assert ui.say() == ["say [Serwer] Restart serwera za 60 s – zaraz wracamy."]
    assert not ui.amp.sent("Core/Restart") and "60 s" in text
    progress = ui.sent[-1]
    assert "dc:Mc01" in str(progress[2])  # wiadomosc z odliczaniem ma "Anuluj"
    text, _ = ui.click("dw:restart:Mc01")
    assert "Już trwa" in text and len(ui.say()) == 1  # drugie klikniecie nic nie robi

    ui.clock[0] += 35
    ui.w.check_ops()
    assert ui.say()[-1].endswith("za 25 s – zaraz wracamy.")
    ui.clock[0] += 20
    ui.w.check_ops()
    assert ui.say()[-1].endswith("za 5 s – zaraz wracamy.") and len(ui.say()) == 3
    ui.clock[0] += 6
    ui.w.check_ops()
    assert len(ui.amp.sent("Core/Restart")) == 1 and "Mc01" in ui.w.ops  # po odliczaniu - restart i dalej postep

    ui.w.ops.clear()
    ui.click("dw:stop:Mc01")
    text, _ = ui.click("dc:Mc01")
    assert "Odwołane" in text and ui.say()[-1] == "say [Serwer] Odwołane – gramy dalej."
    ui.clock[0] += 120
    ui.w.check_ops()
    assert not ui.amp.sent("Core/Stop") and not ui.w.ops
    text, _ = ui.click("dc:Mc01")
    assert "Za późno" in text


def test_crash_alert_and_single_auto_restart(env, ui, monkeypatch):
    w, amp = ui.w, ui.amp
    w.check_states()
    amp.insts["Valheim01"]["state"] = 0
    amp.console_lines = ["Shutting down", "World saved"]
    w.check_states()
    assert ui.sent[-1][1] == "🔴 <b>Valheim</b>: zatrzymany"  # zwykly stop z panelu - nie padniecie

    amp.insts["Valheim01"]["state"] = 20
    w.check_states()
    monkeypatch.setattr(bot, "CRASH_RESTART", True)
    amp.insts["Valheim01"]["state"] = 0
    amp.console_lines = ["NullReferenceException: Object reference not set", "Exited with code 139"]
    w.check_states()
    alert = ui.sent[-2]
    assert "❗" in alert[1] and "NullReferenceException" in alert[1] and "do:start:Valheim01" in str(alert[2])
    assert "jeden raz" in alert[1] and ui.amp.sent("Core/Start") and "Valheim01" in w.ops  # sam startuje i sledzi

    w.ops.clear()
    amp.insts["Valheim01"]["state"] = 20
    w.check_states()
    ui.clock[0] += 600
    amp.insts["Valheim01"]["state"] = 100
    w.check_states()
    assert "drugi raz" in ui.sent[-1][1] and len(ui.amp.sent("Core/Start")) == 1  # drugi raz w 30 min - bez startu

    amp.insts["Valheim01"]["state"] = 20
    w.check_states()
    w.done_at["Valheim01"] = ui.clock[0]  # stop z bota (np. restart): to nie padniecie
    amp.insts["Valheim01"]["state"] = 0
    w.check_states()
    assert ui.sent[-1][1] == "🔴 <b>Valheim</b>: zatrzymany"


def test_charger_and_disk_alerts(env, monkeypatch):
    from collections import namedtuple
    monkeypatch.setattr(bot, "playit_mode", lambda: None)
    monkeypatch.setattr(bot, "cpu_temp", lambda: 50)
    monkeypatch.setattr(bot, "INSTANCES_DIR", "/")
    usage = namedtuple("usage", "total used free")
    disk = [usage(100e9, 95e9, 5e9)]
    monkeypatch.setattr(bot.shutil, "disk_usage", lambda path: disk[0])
    h = bot.HostMonitor()
    for ac, bat in [(True, 50), (False, 50), (False, 49), (False, 48), (True, 48)]:
        monkeypatch.setattr(bot, "power_state", lambda ac=ac, bat=bat: (ac, bat))
        h.check()
    power = [m for m in env.sent if m.startswith("🔌")]
    assert power == ["🔌 <b>Zasilacz odłączony</b> – laptop działa na baterii (49%).",
                     "🔌 Zasilacz znowu podłączony."]  # dopiero drugie sprawdzenie z rzedu, raz
    assert sum("Mało miejsca" in m for m in env.sent) == 1 and "wolne 5.0 GB (95% zajęte)" in env.sent[0]
    disk[0] = usage(100e9, 50e9, 50e9)
    h.check()
    assert env.sent[-1] == "💽 Dysk /: znowu wolne 50 GB."


def test_friend_subscriptions(env, ui):
    bot.friend_set(env.db, 42, "Kumpel", ["Valheim01"])
    friend = {"id": 42, "first_name": "Kumpel"}
    text, markup = ui.click("srv:Valheim01", friend)
    assert "🔕 Gdy serwer wstanie" in str(markup) and "sub:join:Valheim01" in str(markup)
    text, markup = ui.click("sub:join:Valheim01", friend)
    assert "🔔 Dam znać" in text and "🔔 Gdy ktoś wejdzie" in str(markup)
    ui.click("sub:up:Valheim01", friend)
    n = len(ui.edits)
    ui.click("sub:up:Mc01", friend)  # cudzy serwer
    assert len(ui.edits) == n and bot.subs_of(env.db, 42, "Mc01") == set()
    ui.c.scope, ui.c.uid = None, 1
    assert "sub:" not in str(ui.c.server_view("Valheim01", "pl")[1])  # admin ma wszystko i tak

    env.write("Valheim01", f"Got connection SteamID {SID_A}", "Got character ZDOID from Alice : 111:1")
    to_friend = [text for chat, text, _ in ui.sent if chat == 42]
    assert to_friend and "Alice" in to_friend[-1] and SID_A not in to_friend[-1]  # bez SteamID dla znajomego

    ui.w.check_states()
    ui.amp.insts["Valheim01"]["state"] = 0
    ui.w.check_states()
    ui.amp.insts["Valheim01"]["state"] = 20
    ui.w.check_states()
    assert [text for chat, text, _ in ui.sent if chat == 42][-1] == "🟢 <b>Valheim</b> działa – można wchodzić!"

    bot.friend_remove(env.db, 42)
    ui.sent.clear()
    env.write("Valheim01", f"Got connection SteamID {SID_B}", "Got character ZDOID from Bob : 222:1")
    assert not [1 for chat, _, _ in ui.sent if chat == 42]


def test_amp_time_formats():
    assert bot.amp_time("/Date(1700000000000)/") == 1_700_000_000
    assert bot.amp_time("2023-11-14T22:13:20.1234567Z") == 1_700_000_000  # 7 cyfr ulamka z .NET
    assert bot.amp_time("2023-11-14T23:13:20+01:00") == 1_700_000_000
    assert bot.amp_time("nonsense") is None and bot.amp_time(None) is None


def test_backup_list_and_restore_in_steps(env, ui):
    ui.amp.backup_list = [
        {"Id": "old-1", "Name": "Weekly", "Timestamp": "/Date(1600000000000)/", "Sticky": True},
        {"Id": "new-2", "Name": "Telegram 2023-11-14", "Timestamp": "2023-11-14T22:13:20Z"}]
    text, markup = ui.click("bk:Valheim01")
    labels = [b["text"] for row in markup["inline_keyboard"] for b in row]
    assert labels[0].endswith("Telegram 2023-11-14") and labels[1].startswith("📌")  # najnowsza u gory
    text, markup = ui.click("bkr:0:Valheim01")
    assert "❓" in text and "bk!:0:Valheim01" in str(markup) and not ui.amp.sent("RestoreBackup")

    ui.click("bk!:0:Valheim01")
    assert ui.amp.sent("/API/Core/Stop")  # 1/4: gra dzialala - najpierw stop
    ui.amp.insts["Valheim01"]["state"] = 0
    ui.clock[0] += 5
    ui.w.check_ops()
    safety = ui.amp.sent("TakeBackup")[-1][1]
    assert safety["Title"].startswith("Przed przywróceniem")  # 2/4: kopia obecnego stanu
    ui.clock[0] += 31
    ui.w.check_ops()
    restore = ui.amp.sent("RestoreBackup")[-1][1]
    assert restore["BackupId"] == "new-2" and restore["DeleteExistingData"] is False  # 3/4
    ui.clock[0] += 31
    ui.w.check_ops()
    assert ui.amp.sent("/API/Core/Start")  # 4/4: dzialala przed przywroceniem - start
    ui.amp.insts["Valheim01"]["state"] = 20
    ui.clock[0] += 5
    ui.w.check_ops()
    assert "✅" in ui.edits[-1][2] and "Przywracanie kopii" in ui.edits[-1][2] and not ui.w.ops

    bot.friend_set(env.db, 42, "Kumpel", ["Valheim01"])
    friend = {"id": 42, "first_name": "Kumpel"}
    assert "bk:" not in str(ui.click("srv:Valheim01", friend)[1])  # znajomy nie przywraca kopii
    n = len(ui.edits)
    ui.click("bk!:0:Valheim01", friend)
    assert len(ui.edits) == n


def test_new_instance_from_telegram(env, ui):
    ui.amp.apps_list = [
        {"Id": "spec-valheim", "FriendlyName": "Valheim", "ModuleName": "GenericModule", "SupportedPlatforms": 3},
        {"Id": "spec-old", "FriendlyName": "Valheim Legacy", "DeprecatedReason": "old"},
        {"Id": "spec-win", "FriendlyName": "Valheim Windows Tools", "SupportedPlatforms": 1}]
    text, markup = ui.c.servers_view("pl")
    assert '"new"' in json.dumps(markup)
    ui.click("new")
    ui.c.handle_text({"chat": {"id": 1}, "from": {"id": 1}, "text": "valh", "message_id": 2})
    picks = [b["text"] for row in ui.sent[-1][2]["inline_keyboard"] for b in row]
    assert "Valheim" in picks and not any("Legacy" in p or "Windows" in p for p in picks)
    ui.click("nw:0")
    ui.c.handle_text({"chat": {"id": 1}, "from": {"id": 1}, "text": "Ekipa\nZimowa", "message_id": 3})
    assert "nw!:go" in str(ui.sent[-1][2]) and not ui.amp.sent("CreateInstanceFromSpec")
    ui.click("nw!:go")
    _, params = ui.amp.sent("CreateInstanceFromSpec")[-1]
    assert (params["SpecId"], params["TargetADSInstance"], params["FriendlyName"], params["PostCreate"]) == (
        "spec-valheim", "ads-guid", "Ekipa Zimowa", 1)

    ui.amp.insts["EkipaZimowa01"] = {"id": "ghi", "friendly": "Ekipa Zimowa", "module": "Valheim", "running": False,
                                     "state": 0}
    ui.clock[0] += 5
    ui.w.check_ops()
    assert "0.0.0.0:2456" in ui.edits[-1][2] and "playit" in ui.edits[-1][2] and not ui.w.ops

    bot.friend_set(env.db, 42, "Kumpel", ["Valheim01"])
    friend = {"id": 42, "first_name": "Kumpel"}
    assert "new" not in json.dumps(ui.c.servers_view("pl")[1]) or ui.c.scope is None
    ui.c.scope = {"Valheim01"}
    assert '"new"' not in json.dumps(ui.c.servers_view("pl")[1])
    n = len(ui.edits)
    ui.click("new", friend)
    assert len(ui.edits) == n


def test_mod_updates_modrinth(env, ui, mod_instances, monkeypatch):
    import hashlib
    root, _ = mod_instances
    old_sha = hashlib.sha1(b"jar").hexdigest()
    asked = []

    def fake_json(url, timeout=30, data=None):
        asked.append((url, data))
        if url.endswith("/version_files/update"):
            return {old_sha: {"project_id": "jei", "version_number": "15.62", "dependencies": [
                {"project_id": "lib", "dependency_type": "required"},
                {"project_id": "x", "dependency_type": "optional"}],
                "files": [{"filename": "jei-new.jar", "url": "u-new", "primary": True, "hashes": {"sha1": "ffff"}}]}}
        if "/project/lib/version" in url:
            return [{"name": "Lib 2", "files": [{"filename": "lib.jar", "url": "u-lib", "primary": True}],
                     "dependencies": []}]
        raise AssertionError(url)

    monkeypatch.setattr(bot, "http_json", fake_json)
    monkeypatch.setattr(bot, "http_download", lambda url, dest: open(dest, "wb").write(url.encode()))
    target = bot.mod_target("Mc01")
    updates, projects, found = bot.mod_updates(target)
    assert [(u["entry"], u["new"]) for u in updates] == [("jei-1.20.1.jar", "15.62")] and found == 1
    assert asked[0][1]["loaders"] == ["forge"] and asked[0][1]["game_versions"] == ["1.20.1"]

    text, markup = ui.click("mdu:Mc01")
    assert "15.62" in text and "mdx:0:Mc01" in str(markup) and "mdU:Mc01" in str(markup)
    text, _ = ui.click("mdU:Mc01")
    mods = root / "Mc01" / "Minecraft" / "mods"
    assert (mods / "jei-new.jar").read_bytes() == b"u-new" and (mods / "lib.jar").read_bytes() == b"u-lib"
    assert not (mods / "jei-1.20.1.jar").exists() and len(list((root / "Mc01" / "Minecraft" / ".tg-trash").iterdir()))
    assert "Zaktualizowano" in text and "🔁" in text


def test_mod_updates_thunderstore(env, mod_instances, monkeypatch, tmp_path):
    import zipfile
    _, plugins = mod_instances
    (plugins / "RandyKnapp-EpicLoot").mkdir()
    (plugins / "RandyKnapp-EpicLoot" / "manifest.json").write_text('{"name": "EpicLoot", "version_number": "0.14.0"}')
    (plugins / "RandyKnapp-EpicLoot" / "Old.dll").write_text("old")
    (plugins / "Handmade").mkdir()  # bez manifestu - pomijamy
    api = {"/package/RandyKnapp/EpicLoot/": {"latest": {"download_url": "z-epic", "version_number": "0.15.1",
                                                         "dependencies": ["ValheimModding-Jotunn-2.30"]}},
           "/package/ValheimModding/Jotunn/": {"latest": {"download_url": "z-jotunn", "version_number": "2.30",
                                                          "dependencies": []}}}
    monkeypatch.setattr(bot, "http_json", lambda url, timeout=30, data=None: api[next(k for k in api if k in url)])

    def fake_download(url, dest):
        with zipfile.ZipFile(dest, "w") as z:
            z.writestr("plugins/New.dll", url)

    monkeypatch.setattr(bot, "http_download", fake_download)
    target = bot.mod_target("Valheim01")
    updates, projects, found = bot.mod_updates(target)
    assert [(u["entry"], u["new"]) for u in updates] == [("RandyKnapp-EpicLoot", "0.15.1")] and found == 1
    done = bot.apply_mod_update(target, updates[0], projects)
    assert (plugins / "RandyKnapp-EpicLoot" / "New.dll").read_text() == "z-epic"
    assert not (plugins / "RandyKnapp-EpicLoot" / "Old.dll").exists()  # stara wersja w koszu, nie pomieszana
    assert (plugins / "ValheimModding-Jotunn" / "New.dll").exists() and len(done) == 2  # brakujaca zaleznosc


def test_mod_watcher_notifies_once(env, mod_instances, monkeypatch):
    sent_to = []
    monkeypatch.setattr(bot, "send", lambda text, chat_id=None, markup=None: sent_to.append((text, markup)))
    found = [{"entry": "jei.jar", "title": "jei", "new": "2"}]
    monkeypatch.setattr(bot, "mod_updates", lambda target: (
        (found, set(), 1) if target["game"] == "minecraft" else ([], set(), 0)))
    w = bot.ModWatcher(env.db)
    w.last = 0
    w.poll()
    assert len(sent_to) == 1 and "jei" in sent_to[0][0] and "mdu:Mc01" in str(sent_to[0][1])
    w.last = 0
    w.poll()
    assert len(sent_to) == 1  # ten sam zestaw - bez powtorki


def test_game_updates_steam_and_minecraft(env, ui, mod_instances, monkeypatch):
    import zipfile
    root, _ = mod_instances
    apps = root / "Valheim01" / "Valheim" / "896660" / "steamapps"
    apps.mkdir(parents=True)
    (apps / "appmanifest_896660.acf").write_text('"AppState"\n{\n\t"appid"\t\t"896660"\n\t"buildid"\t\t"100"\n}\n')
    (apps / "appmanifest_1007.acf").write_text('"AppState"\n{\n\t"appid"\t\t"1007"\n\t"buildid"\t\t"1"\n}\n')
    vanilla = root / "Vanilla01" / "Minecraft"
    vanilla.mkdir(parents=True)
    with zipfile.ZipFile(vanilla / "minecraft_server.jar", "w") as z:
        z.writestr(zipfile.ZipInfo("version.json", (2024, 1, 1, 0, 0, 0)), '{"id": "1.21.1"}')
    api = {"/896660": {"data": {"896660": {"depots": {"branches": {"public": {"buildid": "200"}}}}}},
           "version_manifest": {"latest": {"release": "1.21.4", "snapshot": "x"}}}
    monkeypatch.setattr(bot, "http_json", lambda url, timeout=30, data=None: api[next(k for k in api if k in url)])
    assert bot.steam_manifests("Valheim01") == [("896660", "100", "public")]  # bez redystrybucji Steama
    assert bot.game_update("Valheim01") == ("build 100", "build 200")
    assert bot.game_update("Vanilla01") == ("1.21.1", "1.21.4")
    assert bot.game_update("Mc01") is None  # Forge: wersje trzymaja mody

    g = bot.GameWatcher(env.db, ui.amp, ui.w, env.inst)
    g.check()
    notes = [(text, markup) for _, text, markup in ui.sent if "nowa wersja gry" in text]
    assert len(notes) == 2 and "do:update:Valheim01" in str(notes[0][1]) and "przypiętą" in notes[1][0]
    g.check()
    assert len([1 for _, text, _ in ui.sent if "nowa wersja gry" in text]) == 2  # bez powtorki

    monkeypatch.setattr(bot, "GAME_AUTO_UPDATE", True)
    (apps / "appmanifest_896660.acf").write_text('"AppState"\n{\n\t"appid"\t\t"896660"\n\t"buildid"\t\t"150"\n}\n')
    env.write("Valheim01", f"Got connection SteamID {SID_A}", "Got character ZDOID from Alice : 111:1")
    g.check()
    g.auto_update()
    assert not ui.amp.sent("UpdateApplication")  # ktos gra - czekamy
    env.write("Valheim01", f"Closing socket {SID_A}")
    g.auto_update()
    assert len(ui.amp.sent("UpdateApplication")) == 1 and ui.w.busy("Valheim01") == "update" \
        and "Valheim01" not in g.pending


def test_minecraft_chat_bridge(env, ui):
    ui.c.handle({"chat": {"id": -100}, "from": {"id": 1}, "text": "/bridge Valheim01"})
    assert "❌" in ui.sent[-1][1] and not bot.BRIDGES  # tylko Minecraft
    ui.c.handle({"chat": {"id": -100}, "from": {"id": 7, "first_name": "Obcy"}, "text": "/bridge Mc01"})
    assert not bot.BRIDGES  # nie-admin nie wlacza mostu
    ui.c.handle({"chat": {"id": -100}, "from": {"id": 1}, "text": "/bridge Mc01"})
    assert bot.BRIDGES == {"Mc01": "-100"} and bot.meta_get(env.db, "bridge:-100") == "Mc01"

    env.write("Mc01", "[12:00:00] [Server thread/INFO]: <Steve> czesc <b>",
              "[12:00:01] [Server thread/INFO]: [Not Secure] <Alex> hi")
    chat = [(c, text) for c, text, _ in ui.sent if c == "-100"]
    assert chat == [("-100", "💬 <b>Steve</b>: czesc &lt;b&gt;"), ("-100", "💬 <b>Alex</b>: hi")]

    ui.c.handle_updates([{"update_id": 5, "message": {
        "chat": {"id": -100}, "from": {"id": 7, "first_name": "Ola"}, "date": ui.clock[0],
        "text": 'hej "x"\n/op Ola'}}], "")
    line = ui.say()[-1]
    assert line.startswith("tellraw @a ") and "\n" not in line
    parts = json.loads(line[len("tellraw @a "):])
    assert parts[1]["text"] == "[TG] " and parts[2]["text"] == "Ola: " and parts[3]["text"] == 'hej "x" /op Ola'

    bot.load_bridges(env.db)  # po restarcie bota most wraca z bazy
    assert bot.BRIDGES == {"Mc01": "-100"}
    ui.c.handle({"chat": {"id": -100}, "from": {"id": 1}, "text": "/bridge off"})
    assert not bot.BRIDGES


def test_server_metrics_and_memory_alert(env, ui, monkeypatch):
    def metrics(mem_pct):
        return {"CPU Usage": {"RawValue": 12, "MaxValue": 100, "Percent": 12, "Units": "%"},
                "Memory Usage": {"RawValue": 8192 * mem_pct // 100, "MaxValue": 8192, "Percent": mem_pct,
                                 "Units": "MB"}}

    ui.amp.insts["Mc01"]["metrics"] = metrics(25)
    text, _ = ui.c.server_view("Mc01", "pl")
    assert "📊 CPU 12% · RAM 2.0 / 8.0 GB (25%)" in text
    ui.amp.insts["Mc01"]["running"] = False
    assert "📊" not in ui.c.server_view("Mc01", "pl")[0]  # wylaczona instancja - bez metryk
    ui.amp.insts["Mc01"]["running"] = True

    ui.amp.insts["Mc01"]["metrics"] = metrics(97)
    for _ in range(3):
        ui.w.check_states()
    alerts = [text for _, text, _ in ui.sent if text.startswith("🧠")]
    assert len(alerts) == 1 and "97%" in alerts[0] and "7.8 / 8.0 GB" in alerts[0]  # po 2 sprawdzeniach, raz
    ui.amp.insts["Mc01"]["metrics"] = metrics(80)
    ui.w.check_states()
    assert ui.sent[-1][1] == "🧠 <b>Minecraft</b>: pamięć znowu 80%."


def test_healthcheck_ping_and_fail(env, monkeypatch):
    pings = []

    class Resp:
        def close(self):
            pass

    monkeypatch.setattr(bot, "HC_URL", "https://hc.test/ping/abc")
    monkeypatch.setattr(bot.urllib.request, "urlopen", lambda req, timeout=10: pings.append(
        (req.full_url, req.data.decode())) or Resp())
    amp = GameAmp()
    h = bot.Healthcheck(amp)
    h.poll()
    assert pings == [("https://hc.test/ping/abc", f"amp-tg-bot {bot.VERSION}, AMP ok (2)")]
    h.poll()
    assert len(pings) == 1  # nie czesciej niz co HC_MINUTES

    def broken(*a, **k):
        raise bot.AmpError("login: bad password")

    amp._post = broken
    h.last = 0
    h.poll()
    assert pings[-1][0] == "https://hc.test/ping/abc/fail" and "bad password" in pings[-1][1]


def test_address_checks_minecraft_and_steam_query():
    import socket
    import threading

    assert bot.parse_address("abc.joinmc.link:25565") == ("abc.joinmc.link", 25565, "")
    assert bot.parse_address("1.2.3.4:2457 udp") == ("1.2.3.4", 2457, "udp")
    assert bot.parse_address("abc") is None and bot.parse_address("x:70000") is None

    mc = socket.socket()
    mc.bind(("127.0.0.1", 0))
    mc.listen(1)

    def minecraft():
        conn, _ = mc.accept()
        with conn:
            conn.recv(1024)  # handshake + prosba o status
            status = json.dumps({"version": {"name": "1.20.1"}, "players": {"online": 2, "max": 20}}).encode()
            payload = b"\x00" + bot._varint(len(status)) + status
            conn.sendall(bot._varint(len(payload)) + payload)

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("127.0.0.1", 0))

    def steam():
        data, addr = udp.recvfrom(1400)
        udp.sendto(b"\xff\xff\xff\xffA\x01\x02\x03\x04", addr)  # challenge
        data, addr = udp.recvfrom(1400)
        assert data.endswith(b"\x01\x02\x03\x04")
        udp.sendto(b"\xff\xff\xff\xffI\x11Viking\x00Map\x00valheim\x00Valheim\x00\x00\x00" + bytes([3, 10]), addr)

    threads = [threading.Thread(target=minecraft, daemon=True), threading.Thread(target=steam, daemon=True)]
    for th in threads:
        th.start()
    assert bot.check_address(f"127.0.0.1:{mc.getsockname()[1]}", "Minecraft") == (True, " – 2/20, 1.20.1")
    assert bot.check_address(f"127.0.0.1:{udp.getsockname()[1]} udp") == (True, " – 3/10")
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    assert bot.check_address(f"127.0.0.1:{port}")[0] is False  # nikt nie slucha
    mc.close()
    udp.close()


def test_tunnel_setting_and_watcher(env, ui, monkeypatch):
    results = [(False, "timed out")] * 4 + [(True, " – 1/20")]  # 1. przy zapisie adresu, 3 z watchera
    monkeypatch.setattr(bot, "check_address", lambda addr, game=None: results.pop(0))
    monkeypatch.setattr(bot, "TUNNEL_STATE", {})
    text, markup = ui.click("tn:Mc01")
    assert "joinmc" in text and "tnc:" not in str(markup)  # jeszcze bez adresu
    ui.c.handle_text({"chat": {"id": 1}, "from": {"id": 1}, "text": "nie adres", "message_id": 2})
    assert "❌" in ui.sent[-1][1] and bot.meta_get(env.db, "tunnel:Mc01") is None
    ui.c.handle_text({"chat": {"id": 1}, "from": {"id": 1}, "text": "abc.joinmc.link:25565", "message_id": 3})
    assert bot.meta_get(env.db, "tunnel:Mc01") == "abc.joinmc.link:25565" and "nie odpowiada" in ui.sent[-1][1]

    w = bot.TunnelWatcher(env.db, ui.amp, env.inst)
    for _ in range(3):
        w.last = 0
        w.poll()
    downs = [text for _, text, _ in ui.sent if "z zewnątrz nie odpowiada" in text]
    assert len(downs) == 1 and "abc.joinmc.link:25565" in downs[0]  # przy 3. bledzie z rzedu, raz
    w.last = 0
    w.poll()
    assert ui.sent[-1][1] == "🌐 <b>Minecraft</b> znowu odpowiada z zewnątrz."
    assert "✅ odpowiada – 1/20" in ui.c.server_view("Mc01", "pl")[0]

    ui.amp.insts["Mc01"]["state"] = 0
    results.append((False, "x"))
    w.last = 0
    w.poll()
    assert len(results) == 1  # serwer zatrzymany - nie sprawdzamy

    bot.friend_set(env.db, 42, "Kumpel", ["Mc01"])
    friend = {"id": 42, "first_name": "Kumpel"}
    assert "tn:" not in str(ui.click("srv:Mc01", friend)[1])
    n = len(ui.edits)
    ui.click("tn:Mc01", friend)
    assert len(ui.edits) == n


def test_minecraft_whitelist(env, ui, mod_instances):
    root, _ = mod_instances
    mc = root / "Mc01" / "Minecraft"
    (mc / "whitelist.json").write_text('[{"uuid": "00000000-0000-4000-8000-000000000001", "name": "Steve"}]')
    (mc / "server.properties").write_text("motd=Hi\nwhite-list=true\n")
    text, markup = ui.click("pl:Mc01")
    assert "wl:Mc01" in str(markup)
    assert "wl:" not in str(ui.click("pl:Valheim01")[1])  # tylko Minecraft
    text, markup = ui.click("wl:Mc01")
    assert "włączona" in text and "🗑 Steve" in str(markup) and "🔓" in str(markup)
    ui.click("wlr:0:Mc01")
    assert ui.say()[-1] == "whitelist remove Steve"
    ui.click("wla:Mc01")
    ui.c.handle_text({"chat": {"id": 1}, "from": {"id": 1}, "text": "Alex; op Alex", "message_id": 4})
    assert "❌" in ui.sent[-1][1] and ui.say()[-1] == "whitelist remove Steve"  # zly nick - nic do konsoli
    ui.c.handle_text({"chat": {"id": 1}, "from": {"id": 1}, "text": "Alex_2", "message_id": 5})
    assert ui.say()[-1] == "whitelist add Alex_2"
    ui.click("wlt:Mc01")
    assert ui.say()[-1] == "whitelist off"

    bot.friend_set(env.db, 42, "Kumpel", ["Mc01"])
    friend = {"id": 42, "first_name": "Kumpel"}
    ui.click("wla:Mc01", friend)  # znajomy na swoim serwerze: tak
    ui.c.handle_text({"chat": {"id": 42}, "from": friend, "text": "Builder_7", "message_id": 6})
    assert ui.say()[-1] == "whitelist add Builder_7"
    ui.amp.insts["Mc01"]["state"] = 0
    text, _ = ui.click("wlt:Mc01")
    assert "musi działać" in text and ui.say()[-1] == "whitelist add Builder_7"
