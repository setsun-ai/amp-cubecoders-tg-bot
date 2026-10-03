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
    assert env.sent.count("⛔ To prywatny bot.") == 2


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
