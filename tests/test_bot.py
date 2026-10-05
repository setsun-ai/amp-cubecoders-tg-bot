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
    c.handle({"chat": {"id": 42}, "from": friend, "text": "/history"})
    assert "/servers" in sent_to[-1][1] and "/history" not in sent_to[-1][1]  # tylko komendy znajomego

    text, markup = click("srv:Valheim01", friend)
    assert "pw:Valheim01" not in str(markup)  # bez hasel
    n = len(edits)
    click("srv:Mc01", friend)
    click("pw:Valheim01", friend)
    click("frl", friend)
    assert len(edits) == n  # cudzy serwer, hasla i /friends - nic sie nie dzieje

    sent_to.clear()
    click("do!:stop:Valheim01", friend)
    assert any(p == "ADSModule/StopInstance" for p, _ in c.amp.calls)
    assert any(chat is None and "Kumpel" in msg for chat, msg, _ in sent_to)  # admin widzi, co zrobil

    click("con:Valheim01", friend)
    c.handle_text({"chat": {"id": 42}, "from": friend, "text": "say hej", "message_id": 5})
    click("con!:Valheim01", friend)
    assert [pl["message"] for p, pl in c.amp.calls if p.endswith("SendConsoleMessage")][-1] == "say hej"

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
    c.handle({"chat": {"id": 42}, "from": friend, "text": "/unban Bob"})
    assert "ub!:Valheim01" in str(sent_to[-1][2]) and "Mc01" not in str(sent_to[-1][2])  # tylko jego serwery
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
