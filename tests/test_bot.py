"""Testy parserow logow i komend na zmyslonych danych (bez Telegrama i internetu)."""
import pytest

import bot

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
    assert env.sent.count("⛔ This is a private bot.") == 2  # obcy bez language_code: po angielsku


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
    assert env.sent[-1] == "⛔ Это приватный бот."


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
    assert not any(p == "ADSModule/StopInstance" for p, _ in c.amp.calls)
    text, _ = click("do!:stop:Valheim01")
    assert ("ADSModule/StopInstance", {"SESSIONID": c.amp.session, "InstanceName": "Valheim01"}) in c.amp.calls
    assert "✅" in text
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
