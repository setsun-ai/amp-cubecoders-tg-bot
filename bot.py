#!/usr/bin/env python3
"""AMP -> Telegram: gracze, komendy i pilnowanie laptopa z serwerami.

Czyta na biezaco AMP_Logs/AMPLOG_*.log kazdej instancji AMP.
Reguly rozpoznawania graczy bierze z pliku .kvp instancji (Console.UserJoinRegex /
Console.UserLeaveRegex), Minecraft i dodatki dla Valheima (SteamID) sa wbudowane.
Do tego: komendy na Telegramie, alert o nowym graczu, smierci, podsumowanie tygodnia,
zasilanie/bateria, temperatura CPU i tunel playit.gg.

Uzycie:
  bot.py              - praca ciagla (uruchamiane przez systemd)
  bot.py --test       - wysyla wiadomosc testowa na Telegram
  bot.py --chatid     - pokazuje chat ID osob/grup, ktore napisaly do bota
  bot.py --historia [N]       - ostatnie N sesji graczy (domyslnie 30)
  bot.py --gracz NAZWA        - sesje danego gracza (nick, SteamID lub UUID)
  bot.py --host       - stan laptopa (zasilanie, temperatura, playit)
  bot.py --selftest   - sprawdza, czy ta wersja dziala na tym serwerze (uzywane przy aktualizacji)
  bot.py --version    - numer wersji
"""
import collections
import glob
import html
import ipaddress
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

VERSION = "1.0.0"
ENV_FILE = "/etc/amp-tg-bot.env"
BOT_PATH = os.path.abspath(__file__)


def load_env_file():
    # systemd podaje zmienne sam; przy recznym uruchomieniu czytamy plik
    try:
        with open(ENV_FILE) as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass


load_env_file()
INSTANCES_DIR = os.environ.get("AMP_INSTANCES", "/home/amp/.ampdata/instances")
DB_PATH = os.environ.get("DB_PATH", "/var/lib/amp-tg-bot/players.db")
TOKEN = os.environ.get("TG_TOKEN", "")
CHAT_ID = os.environ.get("TG_CHAT_ID", "")
# kto moze uzywac komend; domyslnie wlasciciel prywatnego czatu z TG_CHAT_ID
ADMINS = {int(x) for x in re.findall(r"-?\d+", os.environ.get("TG_ADMINS", "")) if int(x) > 0}
if not ADMINS and CHAT_ID.lstrip("-").isdigit() and int(CHAT_ID) > 0:
    ADMINS = {int(CHAT_ID)}
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "180"))
TEMP_ALERT = float(os.environ.get("TEMP_ALERT", "85"))
BATTERY_WARN = int(os.environ.get("BATTERY_WARN", "45"))  # 0 = bez alertu baterii
PLAYIT_SERVICE = os.environ.get("PLAYIT_SERVICE", "playit")
WEEKLY_DAY = int(os.environ.get("WEEKLY_DAY", "6"))  # 0 = poniedzialek, 6 = niedziela
WEEKLY_HOUR = int(os.environ.get("WEEKLY_HOUR", "20"))
GITHUB_REPO = os.environ.get("GITHUB_REPO", "setsun-ai/amp-cubecoders-tg-bot")
POLL_SECONDS = 2
RESCAN_SECONDS = 30
HOST_CHECK_SECONDS = 30
SKIP_MODULES = {"ADSModule"}

# AMP moze dopisywac przed linia konsoli prefiks "[12:00:00] [Console:Info] : "
AMP_PREFIX = re.compile(r"^\[\d{1,2}:\d{2}:\d{2}\] \[[^\]]*\]\s*:\s?")


def log(msg):
    print(msg, flush=True)


def esc(s):
    return html.escape(str(s), quote=False)


def fmt_duration(seconds):
    minutes = max(0, int(seconds // 60))
    h, m = divmod(minutes, 60)
    return f"{h} h {m} min" if h else f"{m} min"


def ts(t):
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t else "-"


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


# ---------- Telegram ----------

def tg_api(method, params=None, timeout=10):
    data = urllib.parse.urlencode(params or {}).encode()
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    with urllib.request.urlopen(url, data, timeout=timeout) as r:
        return json.loads(r.read().decode())


def send(text, chat_id=None, markup=None):
    chat_id = chat_id or CHAT_ID
    if not TOKEN or not chat_id:
        log("[brak TG_TOKEN/TG_CHAT_ID] " + text)
        return
    if len(text) > 4000:
        text = text[:3990] + "\n…"
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": "true"}
    if markup:
        params["reply_markup"] = json.dumps(markup)
    for attempt in range(3):
        try:
            tg_api("sendMessage", params)
            return
        except Exception as e:  # nie logujemy URL-a, bo zawiera token
            log(f"Blad Telegrama ({getattr(e, 'code', type(e).__name__)}), proba {attempt + 1}/3")
            time.sleep(3 * (attempt + 1))


# ---------- reguly dla gier ----------

def read_kvp(path):
    out = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "=" in line:
                    k, v = line.rstrip("\r\n").split("=", 1)
                    out[k.strip()] = v
    except OSError:
        pass
    return out


def dotnet_regex(pattern):
    """AMP pisze regexy w skladni .NET: (?<nazwa>...) -> w Pythonie (?P<nazwa>...)."""
    if not pattern:
        return None
    return re.compile(re.sub(r"\(\?<(?![=!])", "(?P<", pattern))


def public_ip(addr):
    host = addr.lstrip("/")
    if host.startswith("["):  # [ipv6]:port
        host = host[1:].split("]")[0]
    elif host.count(":") == 1:  # ipv4:port
        host = host.split(":")[0]
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None
    return str(ip) if ip.is_global else None


class GenericRules:
    """Reguly z pliku .kvp instancji AMP."""
    # linie czatu wygladaja zwykle jak "<Nick> tekst" - gracz moglby wpisac "X has joined."
    CHAT = re.compile(r"^\s*<[^>]+>")

    def __init__(self, join_re, leave_re):
        self.join_re = dotnet_regex(join_re)
        self.leave_re = dotnet_regex(leave_re)

    def feed(self, line, inst):
        if self.CHAT.match(line):
            return
        if self.join_re:
            m = self.join_re.search(line)
            if m:
                g = m.groupdict()
                inst.on_join(g.get("username"), userid=g.get("userid"))
                return
        if self.leave_re:
            m = self.leave_re.search(line)
            if m:
                g = m.groupdict()
                inst.on_leave(name=g.get("username"), userid=g.get("userid"))


class ValheimRules(GenericRules):
    """Valheim: reguly AMP + SteamID z 'Got connection', wyjscie z 'Closing socket', smierc z ZDOID 0:0."""
    CONN = re.compile(r"Got connection SteamID (\d{17})")
    CLOSE = re.compile(r"Closing socket (\d{17})")

    def __init__(self, join_re, leave_re):
        super().__init__(join_re, leave_re)
        self.pending = collections.deque()

    def feed(self, line, inst):
        if self.CHAT.match(line):
            return
        m = self.CONN.search(line)
        if m:
            self.pending.append(m.group(1))
            return
        m = self.CLOSE.search(line)
        if m:
            sid = m.group(1)
            if sid in self.pending:  # polaczenie bez wejscia postacia (np. zle haslo)
                self.pending.remove(sid)
            inst.on_leave(steamid=sid)
            return
        if self.join_re:
            m = self.join_re.search(line)
            if m:
                g = m.groupdict()
                name = g.get("username")
                if g.get("userid") in ("0", None):  # ZDOID 0:0 = smierc postaci
                    if inst.is_online(name):
                        inst.on_death(name)
                    return
                if inst.is_online(name):
                    inst.on_join(name, userid=g.get("userid"))  # respawn: tylko aktualizacja ID
                    return
                sid = self.pending.popleft() if self.pending else None
                inst.on_join(name, userid=g.get("userid"), steamid=sid)
                return
        if self.leave_re:
            m = self.leave_re.search(line)
            if m:
                inst.on_leave(userid=m.groupdict().get("userid"))


class MinecraftRules:
    # przed nickiem moga byc tylko prefiksy w nawiasach, np. "[12:00:00] [Server thread/INFO]: ",
    # zeby wiadomosc na czacie typu "<Bob> Alice joined the game" nie udawala wejscia
    PRE = r"^(?:(?:\[[^\]]*\]\s*)+:\s*)?"
    UUID = re.compile(PRE + r"UUID of player (\w{1,16}) is ([0-9a-fA-F-]{32,36})\s*$")
    LOGIN = re.compile(PRE + r"(\w{1,16})\[(/?[^\]]+)\] logged in with entity id")
    JOIN = re.compile(PRE + r"(\w{1,16}) joined the game\s*$")
    LEFT = re.compile(PRE + r"(\w{1,16}) left the game\s*$")
    DEATH = re.compile(PRE + r"(\w{1,16}) (?:was |were |walked into|drowned|died|blew up|hit the ground|"
                       r"fell |experienced kinetic|went up in flames|went off with a bang|burned to death|"
                       r"tried to swim|discovered the floor|starved|suffocated|froze to death|"
                       r"withered away|left the confines|didn't want to live)")

    def __init__(self):
        self.uuids = {}
        self.ips = {}

    def feed(self, line, inst):
        m = self.UUID.search(line)
        if m:
            self.uuids[m.group(1)] = m.group(2)
            return
        m = self.LOGIN.search(line)
        if m:
            ip = public_ip(m.group(2))
            if ip:
                self.ips[m.group(1)] = ip
            return
        m = self.JOIN.search(line)
        if m:
            name = m.group(1)
            inst.on_join(name, userid=self.uuids.pop(name, None), ip=self.ips.pop(name, None))
            return
        m = self.LEFT.search(line)
        if m:
            inst.on_leave(name=m.group(1))
            return
        m = self.DEATH.search(line)
        if m and inst.is_online(m.group(1)):
            inst.on_death(m.group(1))


def detect_rules(path):
    """Zwraca (status, nazwa_gry, reguly); status: ok / skip / brak."""
    kvps = sorted(glob.glob(os.path.join(path, "*Module.kvp")))
    if not kvps:
        return "brak", None, None
    module = os.path.basename(kvps[0])[:-len(".kvp")]
    if module in SKIP_MODULES:
        return "skip", None, None
    if "minecraft" in module.lower():
        return "ok", "Minecraft", MinecraftRules()
    kvp = read_kvp(kvps[0])
    game = kvp.get("App.DisplayName") or kvp.get("Meta.DisplayName") or module
    join, leave = kvp.get("Console.UserJoinRegex"), kvp.get("Console.UserLeaveRegex")
    if not join:
        return "brak", game, None
    try:
        rules = ValheimRules(join, leave) if game.lower() == "valheim" else GenericRules(join, leave)
    except re.error as e:
        log(f"{path}: nie umiem przetlumaczyc regexa AMP: {e}")
        return "brak", game, None
    return "ok", game, rules


# ---------- instancja ----------

class Instance:
    def __init__(self, name, path, db, start_at_end):
        self.name, self.path, self.db = name, path, db
        self.start_at_end = start_at_end
        self.logfile, self.pos, self.buf = None, 0, b""
        self.silent = False
        self.online = {}  # klucz: nick (male litery)
        self.detect()

    def detect(self):
        self.status, self.game, self.rules = detect_rules(self.path)

    @property
    def label(self):
        return f"{self.game or '?'} ({self.name})"

    def is_online(self, name):
        return bool(name) and name.lower() in self.online

    def seen_before(self, name, userid, steamid):
        if steamid:
            q = ("SELECT 1 FROM sessions WHERE steamid=? LIMIT 1", (steamid,))
        elif userid and self.game == "Minecraft":
            q = ("SELECT 1 FROM sessions WHERE userid=? LIMIT 1", (userid,))
        else:  # gry bez stalego ID: po nicku w tej samej grze
            q = ("SELECT 1 FROM sessions WHERE username=? AND game=? LIMIT 1", (name, self.game))
        return self.db.execute(*q).fetchone() is not None

    def on_join(self, name, userid=None, steamid=None, ip=None):
        if not name:
            return
        key = name.lower()
        if key in self.online:
            if userid:
                self.online[key]["userid"] = userid
            return
        if self.silent:  # odtwarzanie logu przy starcie bota: tylko zapamietujemy, kto jest online
            self.online[key] = {"name": name, "userid": userid, "steamid": steamid, "ip": ip}
            return
        new_player = not self.seen_before(name, userid, steamid)
        now = int(time.time())
        cur = self.db.execute(
            "INSERT INTO sessions(instance, game, username, userid, steamid, ip, joined) VALUES (?,?,?,?,?,?,?)",
            (self.name, self.game, name, userid, steamid, ip, now))
        self.db.commit()
        self.online[key] = {"name": name, "userid": userid, "steamid": steamid, "since": now, "row": cur.lastrowid}
        lines = ["🆕 <b>NOWY GRACZ!</b>"] if new_player else []
        lines += [f"🟢 <b>{esc(name)}</b> wchodzi na serwer", f"🎮 {esc(self.label)}"]
        if steamid:
            lines.append(f'🆔 SteamID: <a href="https://steamcommunity.com/profiles/{steamid}">{steamid}</a>')
        elif userid and self.game == "Minecraft":
            lines.append(f"🆔 UUID: <code>{esc(userid)}</code>")
        if ip:
            lines.append(f"🌍 IP: <code>{esc(ip)}</code>")
        lines.append(f"👥 Online: {len(self.online)}")
        send("\n".join(lines))

    def on_leave(self, name=None, userid=None, steamid=None, note=None):
        key = None
        if name and name.lower() in self.online:
            key = name.lower()
        else:
            for k, p in self.online.items():
                if (userid and p["userid"] == userid) or (steamid and p["steamid"] == steamid):
                    key = k
                    break
        if key is None:  # gracz wszedl zanim bot wystartowal albo juz wyszedl
            return
        p = self.online.pop(key)
        if self.silent:
            return
        now = int(time.time())
        self.db.execute("UPDATE sessions SET left=?, note=? WHERE id=?", (now, note, p["row"]))
        self.db.commit()
        extra = f" ({note})" if note else ""
        atleast = "co najmniej " if p.get("partial") else ""
        send(f"🔴 <b>{esc(p['name'])}</b> wychodzi{esc(extra)}\n🎮 {esc(self.label)}\n"
             f"⏱ Czas gry: {atleast}{fmt_duration(now - p['since'])}\n👥 Online: {len(self.online)}")

    def finish_replay(self):
        """Gracze, ktorzy weszli przed startem bota: sesja liczona od teraz, bez powiadomienia."""
        self.silent = False
        now = int(time.time())
        for p in self.online.values():
            cur = self.db.execute(
                "INSERT INTO sessions(instance, game, username, userid, steamid, ip, joined, note) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (self.name, self.game, p["name"], p["userid"], p["steamid"], p.get("ip"), now,
                 "przed startem bota"))
            p.update(since=now, row=cur.lastrowid, partial=True)
        self.db.commit()
        if self.online:
            log(f"{self.name}: online przed startem bota: {', '.join(p['name'] for p in self.online.values())}")

    def on_death(self, name):
        if self.silent:
            return
        now = int(time.time())
        self.db.execute("INSERT INTO deaths(instance, game, username, ts) VALUES (?,?,?,?)",
                        (self.name, self.game, name, now))
        self.db.commit()
        midnight = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        n = self.db.execute("SELECT COUNT(*) FROM deaths WHERE username=? AND game=? AND ts>=?",
                            (name, self.game, midnight)).fetchone()[0]
        send(f"💀 <b>{esc(name)}</b> ginie ({n}. raz dzisiaj)\n🎮 {esc(self.label)}")

    def newest_log(self):
        files = glob.glob(os.path.join(self.path, "AMP_Logs", "AMPLOG_*.log"))
        return max(files, key=os.path.getmtime) if files else None

    def poll(self):
        if self.status != "ok":
            return
        newest = self.newest_log()
        if not newest:
            self.start_at_end = False
            return
        if newest != self.logfile:
            if self.logfile is not None:  # nowy plik logu = restart instancji
                for p in list(self.online.values()):
                    self.on_leave(name=p["name"], note="restart serwera")
                self.rules = detect_rules(self.path)[2] or self.rules
            self.logfile, self.buf, self.pos = newest, b"", 0
            # przy starcie bota czytamy biezacy log po cichu, zeby wiedziec, kto juz gra
            self.silent = self.start_at_end
        self.start_at_end = False
        size = os.path.getsize(self.logfile)
        if size < self.pos:  # plik przyciety
            self.pos, self.buf = 0, b""
        if size == self.pos:
            if self.silent:
                self.finish_replay()
            return
        with open(self.logfile, "rb") as f:
            f.seek(self.pos)
            chunk = f.read(size - self.pos)
            self.pos = f.tell()
        data = self.buf + chunk
        *lines, self.buf = data.split(b"\n")
        for raw in lines:
            line = AMP_PREFIX.sub("", raw.decode("utf-8", errors="replace").rstrip("\r"))
            try:
                self.rules.feed(line, self)
            except Exception as e:
                log(f"{self.name}: blad przy linii {line[:120]!r}: {e}")
        if self.silent:
            self.finish_replay()


# ---------- baza ----------

def open_db(readonly=False):
    if readonly:
        return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions(
            id INTEGER PRIMARY KEY, instance TEXT, game TEXT, username TEXT,
            userid TEXT, steamid TEXT, ip TEXT, joined INTEGER, left INTEGER, note TEXT);
        CREATE INDEX IF NOT EXISTS sessions_joined ON sessions(joined);
        CREATE TABLE IF NOT EXISTS deaths(id INTEGER PRIMARY KEY, instance TEXT, game TEXT, username TEXT, ts INTEGER);
        CREATE TABLE IF NOT EXISTS warned(instance TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
    """)
    # sesje niezamkniete przy poprzednim wylaczeniu bota
    db.execute("UPDATE sessions SET note='bot zrestartowany' WHERE left IS NULL AND note IS NULL")
    db.commit()
    return db


def meta_get(db, key):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def meta_set(db, key, value):
    db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", (key, str(value)))
    db.commit()


def warn_once(db, inst):
    if db.execute("SELECT 1 FROM warned WHERE instance=?", (inst.name,)).fetchone():
        return
    db.execute("INSERT INTO warned(instance) VALUES (?)", (inst.name,))
    db.commit()
    send(f"⚠️ Nie wiem, jak rozpoznać graczy w instancji <b>{esc(inst.name)}</b> "
         f"({esc(inst.game or 'nieznana gra')}). Podeślij linię z logu z wejściem gracza.")


# ---------- laptop: zasilanie, temperatura, playit ----------

def power_state():
    """(zasilacz_podlaczony, bateria_procent) - None, gdy brak danych."""
    ac, bat = None, None
    for d in glob.glob("/sys/class/power_supply/*"):
        kind = read(d + "/type")
        if kind == "Mains":
            ac = read(d + "/online") == "1"
        elif kind == "Battery" and read(d + "/present", "1") == "1":
            cap = read(d + "/capacity")
            if cap and cap.isdigit():
                bat = int(cap)
    return ac, bat


def cpu_temp():
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        if read(d + "/name") in ("coretemp", "k10temp", "zenpower"):
            v = read(d + "/temp1_input")
            if v and v.isdigit():
                return int(v) / 1000
    best = None
    for d in glob.glob("/sys/class/thermal/thermal_zone*"):
        v = read(d + "/temp")
        if v and v.lstrip("-").isdigit():
            c = int(v) / 1000
            if read(d + "/type") == "x86_pkg_temp":
                return c
            if 0 < c < 130:
                best = c if best is None else max(best, c)
    return best


def playit_mode():
    """'service' gdy jest usluga systemd, 'process' gdy dziala jako proces, None gdy nie znaleziono."""
    if PLAYIT_SERVICE:
        try:
            r = subprocess.run(["systemctl", "show", "-p", "LoadState", PLAYIT_SERVICE],
                               capture_output=True, text=True, timeout=10)
            if "LoadState=loaded" in r.stdout:
                return "service"
        except (OSError, subprocess.SubprocessError):
            pass
    return "process" if playit_process_running() else None


def playit_process_running():
    for p in glob.glob("/proc/[0-9]*/comm"):
        if "playit" in (read(p, "") or ""):
            return True
    return False


def playit_ok(mode):
    if mode == "service":
        try:
            r = subprocess.run(["systemctl", "is-active", PLAYIT_SERVICE],
                               capture_output=True, text=True, timeout=10)
            return r.stdout.strip() == "active"
        except (OSError, subprocess.SubprocessError):
            return None
    if mode == "process":
        return playit_process_running()
    return None


def host_report():
    ac, bat = power_state()
    temp = cpu_temp()
    lines = []
    if ac is not None or bat is not None:
        src = "sieć 🔌" if ac else ("BATERIA ⚡" if ac is False else "?")
        lines.append(f"Zasilanie: {src}" + (f", bateria {bat}%" if bat is not None else ", brak baterii"))
    if temp is not None:
        lines.append(f"CPU: {temp:.0f}°C")
    try:
        mem = dict(row.split(":", 1) for row in open("/proc/meminfo").read().splitlines())
        total = int(mem["MemTotal"].split()[0]) / 1048576
        avail = int(mem["MemAvailable"].split()[0]) / 1048576
        lines.append(f"RAM: {total - avail:.1f} / {total:.1f} GB")
    except (OSError, KeyError, ValueError):
        pass
    try:
        du = shutil.disk_usage("/")
        lines.append(f"Dysk /: {du.used * 100 // du.total}% zajęte, wolne {du.free / 1e9:.0f} GB")
    except OSError:
        pass
    try:
        lines.append(f"Obciążenie: {os.getloadavg()[0]:.2f}")
    except (OSError, AttributeError):
        pass
    up = read("/proc/uptime")
    if up:
        lines.append(f"Uptime: {fmt_duration(float(up.split()[0]))}")
    mode = playit_mode()
    ok = playit_ok(mode)
    lines.append("playit: " + ("działa ✅" if ok else "NIE DZIAŁA ❌" if ok is False else "nie znaleziono"))
    return "\n".join(lines)


class HostMonitor:
    def __init__(self):
        self.bat_alerted = False
        self.temp_alerted = False
        self.playit_mode = playit_mode()
        self.playit_fails = 0
        self.playit_down = False

    def startup_notes(self):
        notes = []
        if self.playit_mode is None:
            notes.append(f"⚠️ Nie znalazłem playit (usługa '{PLAYIT_SERVICE}' ani proces) – nie pilnuję tunelu.")
        return notes

    def check(self):
        # laptop stoi na zasilaczu z limitem ladowania 50%, wiec spadek ponizej progu = cos nie tak
        _, bat = power_state()
        if bat is not None and BATTERY_WARN:
            if bat < BATTERY_WARN and not self.bat_alerted:
                self.bat_alerted = True
                send(f"🪫 <b>Bateria {bat}%</b> – spadła poniżej {BATTERY_WARN}%. Sprawdź zasilacz.")
            elif bat >= BATTERY_WARN + 3 and self.bat_alerted:
                self.bat_alerted = False
                send(f"🔋 Bateria wróciła do {bat}%.")

        temp = cpu_temp()
        if temp is not None:
            if temp >= TEMP_ALERT and not self.temp_alerted:
                self.temp_alerted = True
                send(f"🌡 <b>CPU {temp:.0f}°C</b> – laptop się grzeje!")
            elif temp < TEMP_ALERT - 10 and self.temp_alerted:
                self.temp_alerted = False
                send(f"✅ Temperatura CPU spadła do {temp:.0f}°C.")

        if self.playit_mode is None:
            return
        ok = playit_ok(self.playit_mode)
        if ok is False:
            self.playit_fails += 1
            if self.playit_fails >= 2 and not self.playit_down:  # 2 kolejne sprawdzenia = ok. minuta
                self.playit_down = True
                send("❌ <b>Tunel playit.gg nie działa!</b> Serwery chodzą, ale nikt z zewnątrz nie wejdzie.")
        elif ok:
            self.playit_fails = 0
            if self.playit_down:
                self.playit_down = False
                send("✅ Tunel playit.gg znowu działa.")


# ---------- statystyki ----------

def player_key(row):
    username, steamid, userid, game = row
    return steamid or (userid if game == "Minecraft" else None) or f"{game}:{username}"


def weekly_summary(db, days=7):
    now = int(time.time())
    since = now - days * 86400
    rows = db.execute("SELECT game, username, steamid, userid, joined, left FROM sessions "
                      "WHERE left IS NOT NULL AND left > ?", (since,)).fetchall()
    if not rows:
        return f"📊 <b>Podsumowanie {days} dni</b>\nNikt nie grał. 😴"
    per_game = collections.defaultdict(lambda: [0, set(), 0])
    per_player = collections.defaultdict(int)
    names = {}
    per_hour = collections.Counter()
    for game, user, sid, uid, joined, left in rows:
        start = max(joined, since)
        dur = left - start
        key = player_key((user, sid, uid, game))
        g = per_game[game]
        g[0] += dur
        g[1].add(key)
        g[2] += 1
        per_player[key] += dur
        names[key] = user
        t = start
        while t < left:  # rozklad czasu gry na godziny doby
            nxt = min(left, (t // 3600 + 1) * 3600)
            per_hour[datetime.fromtimestamp(t).hour] += nxt - t
            t = nxt
    lines = [f"📊 <b>Podsumowanie {days} dni</b>", ""]
    for game, (dur, players, sessions) in sorted(per_game.items(), key=lambda x: -x[1][0]):
        lines.append(f"🎮 <b>{esc(game)}</b>: {fmt_duration(dur)}, graczy: {len(players)}, sesji: {sessions}")
    lines += ["", "🏆 <b>Najwięcej grali:</b>"]
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    for medal, (key, dur) in zip(medals, sorted(per_player.items(), key=lambda x: -x[1])[:5], strict=False):
        lines.append(f"{medal} {esc(names[key])} – {fmt_duration(dur)}")
    if per_hour:
        h = per_hour.most_common(1)[0][0]
        lines += ["", f"🕗 Największy ruch: {h:02d}:00–{(h + 1) % 24:02d}:00"]
    deaths = db.execute("SELECT username, COUNT(*) c FROM deaths WHERE ts > ? GROUP BY username "
                        "ORDER BY c DESC LIMIT 1", (since,)).fetchone()
    if deaths:
        lines.append(f"💀 Najczęściej ginie: {esc(deaths[0])} ({deaths[1]}×)")
    return "\n".join(lines)


def maybe_weekly(db):
    now = datetime.now()
    if now.weekday() != WEEKLY_DAY or now.hour < WEEKLY_HOUR:
        return
    week = now.strftime("%G-%V")
    if meta_get(db, "weekly_sent") == week:
        return
    meta_set(db, "weekly_sent", week)
    send(weekly_summary(db))


# ---------- komendy na Telegramie ----------

# (komenda, opis w menu Telegrama, opis w /pomoc)
COMMANDS = [
    ("online", "Kto teraz gra", "kto teraz gra"),
    ("status", "Stan laptopa i serwerów", "stan laptopa i serwerów"),
    ("historia", "Ostatnie sesje graczy", "/historia [N] – ostatnie sesje (domyślnie 15)"),
    ("gracz", "Historia gracza: /gracz NICK", "/gracz NICK – historia gracza (nick, SteamID albo UUID)"),
    ("tydzien", "Podsumowanie 7 dni", "podsumowanie ostatnich 7 dni"),
    ("wersja", "Wersja bota", "wersja bota i najnowsza dostępna"),
    ("update", "Aktualizacja bota z GitHuba", "aktualizacja do najnowszej wersji"),
    ("rollback", "Powrót do poprzedniej wersji", "powrót do poprzedniej wersji bota"),
    ("pomoc", "Lista komend", "ta lista"),
]
HELP = f"🤖 <b>Bot AMP {VERSION}</b> – komendy:\n" + "\n".join(
    esc(desc) if desc.startswith("/") else f"/{cmd} – {esc(desc)}" for cmd, _, desc in COMMANDS)
KEYBOARD = {"keyboard": [["/online", "/status"], ["/historia", "/tydzien"]], "resize_keyboard": True,
            "is_persistent": True}


def set_menu():
    """Menu komend (przycisk 'Menu' w Telegramie) widoczne tylko na czatach adminow."""
    commands = json.dumps([{"command": c, "description": d} for c, d, _ in COMMANDS])
    for admin in ADMINS:
        try:
            tg_api("setMyCommands", {"commands": commands,
                                     "scope": json.dumps({"type": "chat", "chat_id": admin})})
        except Exception as e:
            log(f"setMyCommands: {getattr(e, 'code', type(e).__name__)}")


# ---------- aktualizacja z GitHuba ----------

def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def github_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": f"amp-tg-bot/{VERSION}",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_release():
    data = json.loads(github_get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"))
    return data["tag_name"]


def install_release(tag):
    """Pobiera bot.py z wydania, testuje i podmienia. Zwraca (ok, komunikat)."""
    code = github_get(f"https://raw.githubusercontent.com/{GITHUB_REPO}/{tag}/bot.py", timeout=30)
    new = BOT_PATH + ".new"
    with open(new, "wb") as f:
        f.write(code)
    r = subprocess.run([sys.executable, new, "--selftest"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        os.remove(new)
        return False, (r.stdout + r.stderr).strip()[-800:]
    shutil.copy2(BOT_PATH, BOT_PATH + ".bak")
    os.replace(new, BOT_PATH)
    return True, r.stdout.strip()


def selftest():
    """Uruchamiane na nowej wersji przed podmiana: czy kod startuje i rozumie instancje."""
    for d in sorted(glob.glob(os.path.join(INSTANCES_DIR, "*", ""))):
        status, game, _ = detect_rules(d)
        print(f"{os.path.basename(os.path.normpath(d))}: {status} {game or ''}")
    sample = Instance.__new__(Instance)  # szybka proba parsera bez bazy i Telegrama
    events = []
    sample.is_online = lambda name: False
    sample.on_join = lambda name, **kw: events.append(name)
    MinecraftRules().feed("[12:00:00] [Server thread/INFO]: Steve joined the game", sample)
    if events != ["Steve"]:
        raise SystemExit("parser Minecrafta nie dziala")
    print(f"OK {VERSION}")


def cmd_online(instances):
    now = time.time()
    lines = []
    for inst in instances.values():
        if inst.status != "ok":
            continue
        players = sorted(inst.online.values(), key=lambda p: p["since"])
        if players:
            lines.append(f"🎮 <b>{esc(inst.label)}</b> ({len(players)})")
            lines += [f"  • {esc(p['name'])} – {fmt_duration(now - p['since'])}" for p in players]
    return "\n".join(lines) if lines else "Nikt teraz nie gra. 😴"


def format_sessions(rows):
    out = []
    for game, user, _sid, _uid, joined, left, note in rows:
        dur = fmt_duration(left - joined) if left else (note or "w grze")
        out.append(f"{ts(joined)[5:]} {game[:9]:<9} {user[:16]:<16} {dur}")
    return "<pre>" + esc("\n".join(out)) + "</pre>" if out else "Brak sesji."


def cmd_historia(db, args):
    n = min(int(args[0]), 50) if args and args[0].isdigit() else 15
    rows = db.execute("SELECT game, username, steamid, userid, joined, left, note FROM sessions "
                      "ORDER BY joined DESC LIMIT ?", (n,)).fetchall()
    return f"📜 <b>Ostatnie {n} sesji</b>\n" + format_sessions(rows)


def cmd_gracz(db, args):
    if not args:
        return "Użycie: /gracz NICK (albo SteamID / UUID)"
    q = " ".join(args)
    rows = db.execute("SELECT game, username, steamid, userid, joined, left, note FROM sessions "
                      "WHERE username LIKE ? OR steamid=? OR userid=? ORDER BY joined DESC",
                      (f"%{q}%", q, q)).fetchall()
    if not rows:
        return f"Nie znam gracza „{esc(q)}”."
    total = sum(r[5] - r[4] for r in rows if r[5])
    names = sorted({r[1] for r in rows})
    sids = sorted({r[2] for r in rows if r[2]})
    uuids = sorted({r[3] for r in rows if r[3] and r[0] == "Minecraft"})
    games = collections.Counter(r[0] for r in rows)
    lines = [f"👤 <b>{esc(', '.join(names))}</b>"]
    lines += [f'🆔 SteamID: <a href="https://steamcommunity.com/profiles/{s}">{s}</a>' for s in sids]
    lines += [f"🆔 UUID: <code>{esc(u)}</code>" for u in uuids]
    lines += [f"⏱ Łącznie: {fmt_duration(total)} w {len(rows)} sesjach",
              "🎮 " + ", ".join(f"{esc(g)} ({c})" for g, c in games.most_common()),
              f"📅 Pierwszy raz: {ts(rows[-1][4])}, ostatnio: {ts(rows[0][4])}",
              "", format_sessions(rows[:10])]
    return "\n".join(lines)


def cmd_status(instances):
    tracked = [i.label for i in instances.values() if i.status == "ok"]
    online = sum(len(i.online) for i in instances.values())
    return (f"🖥 <b>Laptop</b>\n{esc(host_report())}\n\n"
            f"🎮 Śledzę: {esc(', '.join(tracked) or 'nic')}\n👥 Online: {online}")


class Commands:
    def __init__(self, db, instances):
        self.db, self.instances = db, instances
        self.offset = None
        self.restart = False

    def poll(self, timeout):
        """Czeka na wiadomosci do `timeout` sekund (zastepuje sleep w glownej petli)."""
        if not TOKEN:
            time.sleep(timeout)
            return
        params = {"timeout": timeout, "allowed_updates": json.dumps(["message"])}
        if self.offset is not None:
            params["offset"] = self.offset
        try:
            res = tg_api("getUpdates", params, timeout=timeout + 10)
        except Exception as e:
            log(f"getUpdates: {getattr(e, 'code', type(e).__name__)}")
            time.sleep(timeout)
            return
        for upd in res.get("result", []):
            self.offset = upd["update_id"] + 1
            msg = upd.get("message")
            if msg and msg.get("text", "").startswith("/") and time.time() - msg.get("date", 0) < 120:
                try:
                    self.handle(msg)
                except Exception as e:
                    log(f"Blad komendy {msg.get('text')!r}: {e}")
                    send("❌ Coś poszło nie tak, szczegóły w logu bota.", msg["chat"]["id"])
        if self.restart:
            # potwierdzamy odebrane wiadomosci, zeby po restarcie /update nie wykonal sie drugi raz
            try:
                tg_api("getUpdates", {"offset": self.offset, "timeout": 0})
            except Exception:
                pass
            log("Restart po aktualizacji")
            sys.exit(0)  # systemd (Restart=always) uruchomi nowa wersje

    def handle(self, msg):
        chat = msg["chat"]["id"]
        user = msg.get("from", {})
        if user.get("id") not in ADMINS:
            key = f"stranger:{user.get('id')}"
            if not meta_get(self.db, key):  # informujemy admina tylko raz o kazdej osobie
                meta_set(self.db, key, int(time.time()))
                who = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x)
                nick = f" @{user['username']}" if user.get("username") else ""
                send(f"👤 Ktoś pisze do bota: {esc(who)}{esc(nick)} (ID <code>{user.get('id')}</code>)")
            send("⛔ To prywatny bot.", chat)
            return
        parts = msg["text"].split()
        cmd, args = parts[0].split("@")[0].lower(), parts[1:]
        if cmd == "/online":
            send("👥 <b>Online</b>\n" + cmd_online(self.instances), chat)
        elif cmd == "/historia":
            send(cmd_historia(self.db, args), chat)
        elif cmd == "/gracz":
            send(cmd_gracz(self.db, args), chat)
        elif cmd in ("/tydzien", "/tydzień"):
            send(weekly_summary(self.db), chat)
        elif cmd == "/status":
            send(cmd_status(self.instances), chat)
        elif cmd == "/wersja":
            try:
                latest = latest_release()
            except Exception as e:
                latest = f"nie udało się sprawdzić ({getattr(e, 'code', type(e).__name__)})"
            send(f"🤖 Wersja: <b>{VERSION}</b>\n📦 Najnowsza na GitHubie: {esc(latest)}", chat)
        elif cmd == "/update":
            self.update(chat, force="force" in args)
        elif cmd == "/rollback":
            self.rollback(chat)
        else:
            send(HELP, chat, markup=KEYBOARD)

    def update(self, chat, force=False):
        send("🔎 Sprawdzam GitHuba…", chat)
        tag = latest_release()
        if version_tuple(tag) <= version_tuple(VERSION) and not force:
            send(f"✅ Masz najnowszą wersję ({VERSION}).", chat)
            return
        send(f"⬇️ Pobieram i testuję {esc(tag)}…", chat)
        ok, out = install_release(tag)
        if not ok:
            send(f"❌ Nowa wersja nie przeszła testu, zostaję przy {VERSION}.\n<pre>{esc(out)}</pre>", chat)
            return
        meta_set(self.db, "updated_from", VERSION)
        send(f"♻️ Zainstalowano {esc(tag)}, restartuję się (ok. 10 s)…", chat)
        self.restart = True

    def rollback(self, chat):
        bak = BOT_PATH + ".bak"
        if not os.path.exists(bak):
            send("Nie ma poprzedniej wersji do przywrócenia.", chat)
            return
        os.replace(bak, BOT_PATH)
        meta_set(self.db, "updated_from", VERSION)
        send("⏪ Przywracam poprzednią wersję, restartuję się (ok. 10 s)…", chat)
        self.restart = True


# ---------- glowna petla ----------

def run():
    db = open_db()
    instances = {}
    host = HostMonitor()
    commands = Commands(db, instances)
    startup = True
    last_scan = last_clean = last_host = 0
    log(f"Start, katalog instancji: {INSTANCES_DIR}, admini: {sorted(ADMINS) or 'brak'}")
    while True:
        now = time.time()
        if now - last_scan >= RESCAN_SECONDS:
            for d in sorted(glob.glob(os.path.join(INSTANCES_DIR, "*", ""))):
                name = os.path.basename(os.path.normpath(d))
                inst = instances.get(name)
                if inst is None:
                    inst = instances[name] = Instance(name, d, db, start_at_end=startup)
                    if inst.status != "skip":
                        log(f"Instancja {inst.label}: {inst.status}")
                        if not startup and inst.status == "ok":
                            send(f"🆕 Nowa instancja: <b>{esc(inst.label)}</b>, śledzę graczy.")
                elif inst.status == "brak":
                    inst.detect()
                if inst.status == "brak":
                    warn_once(db, inst)
                elif inst.status == "ok":
                    db.execute("DELETE FROM warned WHERE instance=?", (name,))
                    db.commit()
            if startup:
                tracked = ", ".join(esc(i.label) for i in instances.values() if i.status == "ok") or "nic"
                old = meta_get(db, "updated_from")
                head = (f"✅ Zaktualizowano: {esc(old)} → <b>{VERSION}</b>" if old
                        else f"🤖 Bot AMP {VERSION} działa.")
                if old:
                    db.execute("DELETE FROM meta WHERE key='updated_from'")
                    db.commit()
                send("\n".join([head, f"Śledzę: {tracked}", "Komendy: /pomoc"] + host.startup_notes()))
                set_menu()
            startup = False
            last_scan = now
        for inst in instances.values():
            try:
                inst.poll()
            except Exception as e:
                log(f"{inst.name}: blad odczytu logu: {e}")
        if now - last_host >= HOST_CHECK_SECONDS:
            try:
                host.check()
            except Exception as e:
                log(f"Blad sprawdzania laptopa: {e}")
            maybe_weekly(db)
            last_host = now
        if RETENTION_DAYS > 0 and now - last_clean > 86400:
            cutoff = int(now) - RETENTION_DAYS * 86400
            db.execute("DELETE FROM sessions WHERE joined < ?", (cutoff,))
            db.execute("DELETE FROM deaths WHERE ts < ?", (cutoff,))
            db.commit()
            last_clean = now
        commands.poll(POLL_SECONDS)


# ---------- komendy reczne ----------

def print_rows(rows):
    for game, _inst, user, uid, sid, ip, joined, left, note in rows:
        dur = fmt_duration(left - joined) if left else (note or "online?")
        ids = " ".join(x for x in (sid and f"SteamID:{sid}", uid and f"ID:{uid}", ip and f"IP:{ip}") if x)
        print(f"{ts(joined)}  {game:<10} {user:<20} {dur:<18} {ids}")


def main():
    args = sys.argv[1:]
    cols = "game, instance, username, userid, steamid, ip, joined, left, note"
    if not args:
        run()
    elif args[0] == "--test":
        send("✅ Test: bot AMP ma połączenie z Telegramem.")
        print("Wyslano (jesli nie przyszlo, sprawdz TG_TOKEN i TG_CHAT_ID).")
    elif args[0] == "--chatid":
        res = tg_api("getUpdates")
        chats = {}
        for u in res.get("result", []):
            msg = u.get("message") or u.get("channel_post") or {}
            c = msg.get("chat")
            if c:
                chats[c["id"]] = c.get("title") or c.get("username") or c.get("first_name")
        if not chats:
            print("Brak wiadomosci. Napisz cos do bota na Telegramie i uruchom ponownie.")
        for cid, who in chats.items():
            print(f"chat ID: {cid}   ({who})")
    elif args[0] == "--historia":
        n = int(args[1]) if len(args) > 1 else 30
        print_rows(open_db(readonly=True).execute(
            f"SELECT {cols} FROM sessions ORDER BY joined DESC LIMIT ?", (n,)).fetchall())
    elif args[0] == "--gracz" and len(args) > 1:
        q = " ".join(args[1:])
        print_rows(open_db(readonly=True).execute(
            f"SELECT {cols} FROM sessions WHERE username LIKE ? OR steamid=? OR userid=? ORDER BY joined DESC",
            (f"%{q}%", q, q)).fetchall())
    elif args[0] == "--host":
        print(host_report())
        print(f"playit tryb: {playit_mode()}")
    elif args[0] == "--selftest":
        selftest()
    elif args[0] == "--version":
        print(VERSION)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
