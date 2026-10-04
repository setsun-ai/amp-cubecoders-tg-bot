#!/usr/bin/env python3
"""AMP -> Telegram: gracze, komendy i pilnowanie laptopa z serwerami.

Czyta na biezaco AMP_Logs/AMPLOG_*.log kazdej instancji AMP.
Reguly rozpoznawania graczy bierze z pliku .kvp instancji (Console.UserJoinRegex /
Console.UserLeaveRegex), Minecraft i dodatki dla Valheima (SteamID) sa wbudowane.
Do tego: komendy na Telegramie, alert o nowym graczu, smierci, podsumowanie tygodnia,
bateria, temperatura CPU i tunel playit.gg. Jezyki: pl, en, ru, uk (/lang).

Uzycie:
  bot.py              - praca ciagla (uruchamiane przez systemd)
  bot.py --test       - wysyla wiadomosc testowa na Telegram
  bot.py --chatid     - pokazuje chat ID osob/grup, ktore napisaly do bota
  bot.py --historia [N]       - ostatnie N sesji graczy (domyslnie 30)
  bot.py --gracz NAZWA        - sesje danego gracza (nick, SteamID lub UUID)
  bot.py --host       - stan laptopa (zasilanie, temperatura, playit)
  bot.py --amp-test   - logowanie do AMP, lista instancji i funkcje API
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

VERSION = "1.5.0"
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
# panel AMP (ADS) i osobne konto dla bota; bez nich /servers jest wylaczone
AMP_URL = os.environ.get("AMP_URL", "").rstrip("/")
AMP_USER = os.environ.get("AMP_USER", "")
AMP_PASS = os.environ.get("AMP_PASS", "")
AMP_NOTIFY = os.environ.get("AMP_NOTIFY", "1") != "0"  # zadania i zmiany stanu z panelu AMP na Telegram
AMP_TASK_SECONDS = 5
AMP_STATE_SECONDS = 30
# krotkie, rutynowe zadania panelu (np. "Updating remote sources" co godzine) nie trafiaja na czat
AMP_TASK_MIN_SECONDS = int(os.environ.get("AMP_TASK_MIN_SECONDS", "15"))
AMP_TASK_IGNORE = re.compile(os.environ.get("AMP_TASK_IGNORE", r"remote sources|refreshing|checking for"), re.I)
UPDATES_CHECK_HOURS = float(os.environ.get("UPDATES_CHECK_HOURS", "6"))  # 0 = bez sprawdzania aktualizacji
IMPORTANT_PACKAGES = ("tailscale", "playit", "webmin", "ampinstmgr", "openssh", "openssl", "linux-image", "sudo")
POLL_SECONDS = 2
RESCAN_SECONDS = 30
HOST_CHECK_SECONDS = 30
SKIP_MODULES = {"ADSModule"}

# AMP moze dopisywac przed linia konsoli prefiks "[12:00:00] [Console:Info] : "
AMP_PREFIX = re.compile(r"^\[\d{1,2}:\d{2}:\d{2}\] \[[^\]]*\]\s*:\s?")


# ---------- jezyki ----------

LANGS = {"pl": "🇵🇱 Polski", "en": "🇬🇧 English", "ru": "🇷🇺 Русский", "uk": "🇺🇦 Українська"}
LANG_ORDER = ("pl", "en", "ru", "uk")

# klucz: (pl, en, ru, uk)
STRINGS = {
    "dur_hm": ("{h} h {m} min", "{h} h {m} min", "{h} ч {m} мин", "{h} год {m} хв"),
    "dur_m": ("{m} min", "{m} min", "{m} мин", "{m} хв"),
    # gracze
    "new_player": ("🆕 <b>NOWY GRACZ!</b>", "🆕 <b>NEW PLAYER!</b>", "🆕 <b>НОВЫЙ ИГРОК!</b>",
                   "🆕 <b>НОВИЙ ГРАВЕЦЬ!</b>"),
    "joined": ("🟢 <b>{name}</b> wchodzi na serwer", "🟢 <b>{name}</b> joined the server",
               "🟢 <b>{name}</b> заходит на сервер", "🟢 <b>{name}</b> заходить на сервер"),
    "left": ("🔴 <b>{name}</b> wychodzi{extra}", "🔴 <b>{name}</b> left{extra}",
             "🔴 <b>{name}</b> выходит{extra}", "🔴 <b>{name}</b> виходить{extra}"),
    "online_count": ("👥 Online: {n}", "👥 Online: {n}", "👥 Онлайн: {n}", "👥 Онлайн: {n}"),
    "playtime": ("⏱ Czas gry: {dur}", "⏱ Play time: {dur}", "⏱ Время в игре: {dur}", "⏱ Час у грі: {dur}"),
    "at_least": ("co najmniej {dur}", "at least {dur}", "не меньше {dur}", "щонайменше {dur}"),
    "death": ("💀 <b>{name}</b> ginie ({n}. raz dzisiaj)", "💀 <b>{name}</b> died ({n}× today)",
              "💀 <b>{name}</b> погибает ({n}-й раз за сегодня)", "💀 <b>{name}</b> гине ({n}-й раз за сьогодні)"),
    "note_restart": ("restart serwera", "server restart", "перезапуск сервера", "перезапуск сервера"),
    "note_prestart": ("przed startem bota", "before bot start", "до запуска бота", "до запуску бота"),
    "note_botrestart": ("bot zrestartowany", "bot restarted", "бот перезапущен", "бот перезапущено"),
    "in_game": ("w grze", "playing", "в игре", "у грі"),
    "warn_unknown": (
        "⚠️ Nie wiem, jak rozpoznać graczy w instancji <b>{inst}</b> ({game}). "
        "Podeślij linię z logu z wejściem gracza.",
        "⚠️ I don't know how to detect players on instance <b>{inst}</b> ({game}). "
        "Send me a log line with a player joining.",
        "⚠️ Не знаю, как распознавать игроков на инстансе <b>{inst}</b> ({game}). "
        "Пришли строку из лога со входом игрока.",
        "⚠️ Не знаю, як розпізнавати гравців на інстансі <b>{inst}</b> ({game}). "
        "Надішли рядок із логу зі входом гравця."),
    "unknown_game": ("nieznana gra", "unknown game", "неизвестная игра", "невідома гра"),
    "new_instance": ("🆕 Nowa instancja: <b>{label}</b>, śledzę graczy.",
                     "🆕 New instance: <b>{label}</b>, tracking players.",
                     "🆕 Новый инстанс: <b>{label}</b>, слежу за игроками.",
                     "🆕 Новий інстанс: <b>{label}</b>, стежу за гравцями."),
    # start i aktualizacja
    "startup": ("🤖 Bot AMP {v} działa.", "🤖 AMP bot {v} is running.", "🤖 Бот AMP {v} работает.",
                "🤖 Бот AMP {v} працює."),
    "updated": ("✅ Zaktualizowano: {old} → <b>{v}</b>", "✅ Updated: {old} → <b>{v}</b>",
                "✅ Обновлено: {old} → <b>{v}</b>", "✅ Оновлено: {old} → <b>{v}</b>"),
    "tracking": ("Śledzę: {list}", "Tracking: {list}", "Слежу: {list}", "Стежу: {list}"),
    "nothing": ("nic", "nothing", "ничего", "нічого"),
    "commands_hint": ("Komendy: /help", "Commands: /help", "Команды: /help", "Команди: /help"),
    "test_msg": ("✅ Test: bot AMP ma połączenie z Telegramem.", "✅ Test: the AMP bot can reach Telegram.",
                 "✅ Тест: бот AMP на связи с Telegram.", "✅ Тест: бот AMP на зв'язку з Telegram."),
    "version": ("🤖 Wersja: <b>{v}</b>\n📦 Najnowsza na GitHubie: {latest}",
                "🤖 Version: <b>{v}</b>\n📦 Latest on GitHub: {latest}",
                "🤖 Версия: <b>{v}</b>\n📦 Последняя на GitHub: {latest}",
                "🤖 Версія: <b>{v}</b>\n📦 Остання на GitHub: {latest}"),
    "check_failed": ("nie udało się sprawdzić ({err})", "check failed ({err})", "не удалось проверить ({err})",
                     "не вдалося перевірити ({err})"),
    "upd_checking": ("🔎 Sprawdzam GitHuba…", "🔎 Checking GitHub…", "🔎 Проверяю GitHub…", "🔎 Перевіряю GitHub…"),
    "upd_latest": ("✅ Masz najnowszą wersję ({v}).", "✅ You have the latest version ({v}).",
                   "✅ У тебя последняя версия ({v}).", "✅ У тебе остання версія ({v})."),
    "upd_downloading": ("⬇️ Pobieram i testuję {tag}…", "⬇️ Downloading and testing {tag}…",
                        "⬇️ Скачиваю и тестирую {tag}…", "⬇️ Завантажую й тестую {tag}…"),
    "upd_failed": ("❌ Nowa wersja nie przeszła testu, zostaję przy {v}.",
                   "❌ The new version failed the test, staying on {v}.",
                   "❌ Новая версия не прошла тест, остаюсь на {v}.",
                   "❌ Нова версія не пройшла тест, лишаюся на {v}."),
    "upd_restart": ("♻️ Zainstalowano {tag}, restartuję się (ok. 10 s)…",
                    "♻️ Installed {tag}, restarting (about 10 s)…",
                    "♻️ Установлено {tag}, перезапускаюсь (около 10 с)…",
                    "♻️ Встановлено {tag}, перезапускаюся (близько 10 с)…"),
    "rb_none": ("Nie ma poprzedniej wersji do przywrócenia.", "There is no previous version to restore.",
                "Нет предыдущей версии для восстановления.", "Немає попередньої версії для відновлення."),
    "rb_restart": ("⏪ Przywracam poprzednią wersję, restartuję się (ok. 10 s)…",
                   "⏪ Restoring the previous version, restarting (about 10 s)…",
                   "⏪ Возвращаю предыдущую версию, перезапускаюсь (около 10 с)…",
                   "⏪ Повертаю попередню версію, перезапускаюся (близько 10 с)…"),
    # laptop
    "no_playit": ("⚠️ Nie znalazłem playit (usługa '{svc}' ani proces) – nie pilnuję tunelu.",
                  "⚠️ playit not found (no '{svc}' service or process) – not watching the tunnel.",
                  "⚠️ Не нашёл playit (ни службы '{svc}', ни процесса) – туннель не отслеживаю.",
                  "⚠️ Не знайшов playit (ні служби '{svc}', ні процесу) – тунель не відстежую."),
    "bat_low": ("🪫 <b>Bateria {bat}%</b> – spadła poniżej {th}%. Sprawdź zasilacz.",
                "🪫 <b>Battery {bat}%</b> – dropped below {th}%. Check the charger.",
                "🪫 <b>Батарея {bat}%</b> – упала ниже {th}%. Проверь зарядку.",
                "🪫 <b>Батарея {bat}%</b> – впала нижче {th}%. Перевір зарядку."),
    "bat_ok": ("🔋 Bateria wróciła do {bat}%.", "🔋 Battery back at {bat}%.", "🔋 Батарея снова {bat}%.",
               "🔋 Батарея знову {bat}%."),
    "temp_hot": ("🌡 <b>CPU {t}°C</b> – laptop się grzeje!", "🌡 <b>CPU {t}°C</b> – the laptop is overheating!",
                 "🌡 <b>CPU {t}°C</b> – ноутбук перегревается!", "🌡 <b>CPU {t}°C</b> – ноутбук перегрівається!"),
    "temp_ok": ("✅ Temperatura CPU spadła do {t}°C.", "✅ CPU temperature down to {t}°C.",
                "✅ Температура CPU снизилась до {t}°C.", "✅ Температура CPU знизилася до {t}°C."),
    "playit_down": ("❌ <b>Tunel playit.gg nie działa!</b> Serwery chodzą, ale nikt z zewnątrz nie wejdzie.",
                    "❌ <b>The playit.gg tunnel is down!</b> Servers are running, but nobody from outside can join.",
                    "❌ <b>Туннель playit.gg не работает!</b> Серверы работают, но снаружи никто не зайдёт.",
                    "❌ <b>Тунель playit.gg не працює!</b> Сервери працюють, але ззовні ніхто не зайде."),
    "playit_up": ("✅ Tunel playit.gg znowu działa.", "✅ The playit.gg tunnel is back up.",
                  "✅ Туннель playit.gg снова работает.", "✅ Тунель playit.gg знову працює."),
    "h_title": ("🖥 <b>Laptop</b>", "🖥 <b>Laptop</b>", "🖥 <b>Ноутбук</b>", "🖥 <b>Ноутбук</b>"),
    "h_power": ("Zasilanie: {src}", "Power: {src}", "Питание: {src}", "Живлення: {src}"),
    "h_mains": ("sieć 🔌", "mains 🔌", "сеть 🔌", "мережа 🔌"),
    "h_on_battery": ("BATERIA ⚡", "BATTERY ⚡", "БАТАРЕЯ ⚡", "БАТАРЕЯ ⚡"),
    "h_bat": (", bateria {bat}%", ", battery {bat}%", ", батарея {bat}%", ", батарея {bat}%"),
    "h_nobat": (", brak baterii", ", no battery", ", нет батареи", ", немає батареї"),
    "h_ram": ("RAM: {used} / {total} GB", "RAM: {used} / {total} GB", "RAM: {used} / {total} ГБ",
              "RAM: {used} / {total} ГБ"),
    "h_disk": ("Dysk /: {pct}% zajęte, wolne {free} GB", "Disk /: {pct}% used, {free} GB free",
               "Диск /: занято {pct}%, свободно {free} ГБ", "Диск /: зайнято {pct}%, вільно {free} ГБ"),
    "h_load": ("Obciążenie: {load}", "Load: {load}", "Нагрузка: {load}", "Навантаження: {load}"),
    "h_uptime": ("Uptime: {dur}", "Uptime: {dur}", "Аптайм: {dur}", "Аптайм: {dur}"),
    "h_playit_ok": ("playit: działa ✅", "playit: running ✅", "playit: работает ✅", "playit: працює ✅"),
    "h_playit_down": ("playit: NIE DZIAŁA ❌", "playit: DOWN ❌", "playit: НЕ РАБОТАЕТ ❌", "playit: НЕ ПРАЦЮЄ ❌"),
    "h_playit_none": ("playit: nie znaleziono", "playit: not found", "playit: не найден", "playit: не знайдено"),
    # podsumowanie tygodnia
    "w_title": ("📊 <b>Podsumowanie {days} dni</b>", "📊 <b>Last {days} days</b>", "📊 <b>Итоги за {days} дней</b>",
                "📊 <b>Підсумки за {days} днів</b>"),
    "w_nobody": ("Nikt nie grał. 😴", "Nobody played. 😴", "Никто не играл. 😴", "Ніхто не грав. 😴"),
    "w_game": ("🎮 <b>{game}</b>: {dur}, graczy: {players}, sesji: {sessions}",
               "🎮 <b>{game}</b>: {dur}, players: {players}, sessions: {sessions}",
               "🎮 <b>{game}</b>: {dur}, игроков: {players}, сессий: {sessions}",
               "🎮 <b>{game}</b>: {dur}, гравців: {players}, сесій: {sessions}"),
    "w_top": ("🏆 <b>Najwięcej grali:</b>", "🏆 <b>Top players:</b>", "🏆 <b>Больше всех играли:</b>",
              "🏆 <b>Найбільше грали:</b>"),
    "w_peak": ("🕗 Największy ruch: {hours}", "🕗 Busiest hour: {hours}", "🕗 Пик активности: {hours}",
               "🕗 Пік активності: {hours}"),
    "w_deaths": ("💀 Najczęściej ginie: {name} ({n}×)", "💀 Dies the most: {name} ({n}×)",
                 "💀 Чаще всех погибает: {name} ({n}×)", "💀 Найчастіше гине: {name} ({n}×)"),
    # komendy
    "online_title": ("👥 <b>Online</b>", "👥 <b>Online</b>", "👥 <b>Онлайн</b>", "👥 <b>Онлайн</b>"),
    "nobody_online": ("Nikt teraz nie gra. 😴", "Nobody is playing right now. 😴", "Сейчас никто не играет. 😴",
                      "Зараз ніхто не грає. 😴"),
    "no_sessions": ("Brak sesji.", "No sessions.", "Нет сессий.", "Немає сесій."),
    "hist_title": ("📜 <b>Ostatnie sesje ({n})</b>", "📜 <b>Last sessions ({n})</b>",
                   "📜 <b>Последние сессии ({n})</b>", "📜 <b>Останні сесії ({n})</b>"),
    "player_usage": ("Użycie: /player NICK (albo SteamID / UUID)", "Usage: /player NAME (or SteamID / UUID)",
                     "Использование: /player НИК (или SteamID / UUID)",
                     "Використання: /player НІК (або SteamID / UUID)"),
    "player_unknown": ("Nie znam gracza „{q}”.", "I don't know player “{q}”.", "Не знаю игрока «{q}».",
                       "Не знаю гравця «{q}»."),
    "p_total": ("⏱ Łącznie: {dur}, sesje: {n}", "⏱ Total: {dur}, sessions: {n}", "⏱ Всего: {dur}, сессий: {n}",
                "⏱ Усього: {dur}, сесій: {n}"),
    "p_seen": ("📅 Pierwszy raz: {first}, ostatnio: {last}", "📅 First seen: {first}, last: {last}",
               "📅 Впервые: {first}, последний раз: {last}", "📅 Уперше: {first}, востаннє: {last}"),
    "stranger": ("👤 Ktoś pisze do bota: {who} (ID <code>{id}</code>)",
                 "👤 Someone wrote to the bot: {who} (ID <code>{id}</code>)",
                 "👤 Боту пишет: {who} (ID <code>{id}</code>)", "👤 Боту пише: {who} (ID <code>{id}</code>)"),
    "private": ("⛔ To prywatny bot.", "⛔ This is a private bot.", "⛔ Это приватный бот.", "⛔ Це приватний бот."),
    "error": ("❌ Coś poszło nie tak, szczegóły w logu bota.", "❌ Something went wrong, see the bot log.",
              "❌ Что-то пошло не так, подробности в логе бота.", "❌ Щось пішло не так, подробиці в лозі бота."),
    "lang_choose": ("🌐 Wybierz język:", "🌐 Choose a language:", "🌐 Выбери язык:", "🌐 Обери мову:"),
    "lang_set": ("✅ Język: {name}", "✅ Language: {name}", "✅ Язык: {name}", "✅ Мова: {name}"),
    "help_title": ("🤖 <b>Bot AMP {v}</b> – komendy:", "🤖 <b>AMP bot {v}</b> – commands:",
                   "🤖 <b>Бот AMP {v}</b> – команды:", "🤖 <b>Бот AMP {v}</b> – команди:"),
    # opisy komend (menu i /help)
    "c_online": ("Kto teraz gra", "Who's playing now", "Кто сейчас играет", "Хто зараз грає"),
    "c_status": ("Stan laptopa i serwerów", "Laptop and server status", "Состояние ноутбука и серверов",
                 "Стан ноутбука і серверів"),
    "c_history": ("Ostatnie sesje graczy", "Recent player sessions", "Последние сессии игроков",
                  "Останні сесії гравців"),
    "c_player": ("Historia gracza (nick, SteamID, UUID)", "Player history (name, SteamID, UUID)",
                 "История игрока (ник, SteamID, UUID)", "Історія гравця (нік, SteamID, UUID)"),
    "c_week": ("Podsumowanie 7 dni", "7-day summary", "Итоги за 7 дней", "Підсумки за 7 днів"),
    "c_lang": ("Język / Language", "Language", "Язык / Language", "Мова / Language"),
    "c_version": ("Wersja bota", "Bot version", "Версия бота", "Версія бота"),
    "c_update": ("Aktualizacja z GitHuba", "Update from GitHub", "Обновление с GitHub", "Оновлення з GitHub"),
    "c_rollback": ("Powrót do poprzedniej wersji", "Back to the previous version", "Вернуть предыдущую версию",
                   "Повернути попередню версію"),
    "c_help": ("Lista komend", "Command list", "Список команд", "Список команд"),
    "upd_checking_now": ("🔎 Sprawdzam aktualizacje…", "🔎 Checking for updates…", "🔎 Проверяю обновления…",
                         "🔎 Перевіряю оновлення…"),
    "c_updates": ("Aktualizacje systemu i AMP", "System and AMP updates", "Обновления системы и AMP",
                  "Оновлення системи та AMP"),
    "upd_title": ("🛡 <b>Aktualizacje</b>", "🛡 <b>Updates</b>", "🛡 <b>Обновления</b>", "🛡 <b>Оновлення</b>"),
    "upd_apt": ("📦 Pakiety do aktualizacji: {n} (bezpieczeństwa: {sec})",
                "📦 Packages to update: {n} (security: {sec})",
                "📦 Пакетов для обновления: {n} (безопасность: {sec})",
                "📦 Пакетів для оновлення: {n} (безпека: {sec})"),
    "upd_more": ("  …i {n} zwykłych", "  …and {n} regular ones", "  …и ещё {n} обычных", "  …і ще {n} звичайних"),
    "upd_apt_none": ("📦 System aktualny.", "📦 The system is up to date.", "📦 Система обновлена.",
                     "📦 Система оновлена."),
    "upd_apt_unknown": ("📦 Nie udało się sprawdzić pakietów (apt).", "📦 Couldn't check packages (apt).",
                        "📦 Не удалось проверить пакеты (apt).", "📦 Не вдалося перевірити пакети (apt)."),
    "upd_reboot": ("🔁 <b>Wymagany restart systemu</b> (po: {pkgs})",
                   "🔁 <b>System restart required</b> (after: {pkgs})",
                   "🔁 <b>Нужна перезагрузка</b> (после: {pkgs})",
                   "🔁 <b>Потрібне перезавантаження</b> (після: {pkgs})"),
    "upd_amp": ("🆕 Nowa wersja AMP: {version} (panel → Aktualizacje)",
                "🆕 New AMP version: {version} (panel → Updates)",
                "🆕 Новая версия AMP: {version} (панель → Обновления)",
                "🆕 Нова версія AMP: {version} (панель → Оновлення)"),
    "upd_how": ("Instalacja: Webmin → System → Software Package Updates albo <code>sudo apt upgrade</code>.",
                "Install: Webmin → System → Software Package Updates or <code>sudo apt upgrade</code>.",
                "Установка: Webmin → System → Software Package Updates или <code>sudo apt upgrade</code>.",
                "Встановлення: Webmin → System → Software Package Updates або <code>sudo apt upgrade</code>."),
    "c_servers": ("Serwery: start, stop, restart, aktualizacja", "Servers: start, stop, restart, update",
                  "Серверы: старт, стоп, перезапуск, обновление", "Сервери: старт, стоп, перезапуск, оновлення"),
    # zarzadzanie AMP
    "amp_off": ("AMP nie jest skonfigurowany: dopisz AMP_URL, AMP_USER i AMP_PASS do /etc/amp-tg-bot.env.",
                "AMP is not configured: add AMP_URL, AMP_USER and AMP_PASS to /etc/amp-tg-bot.env.",
                "AMP не настроен: добавь AMP_URL, AMP_USER и AMP_PASS в /etc/amp-tg-bot.env.",
                "AMP не налаштовано: додай AMP_URL, AMP_USER і AMP_PASS до /etc/amp-tg-bot.env."),
    "amp_error": ("❌ AMP: {err}", "❌ AMP: {err}", "❌ AMP: {err}", "❌ AMP: {err}"),
    "srv_title": ("🖥 <b>Serwery</b> – wybierz:", "🖥 <b>Servers</b> – pick one:", "🖥 <b>Серверы</b> – выбери:",
                  "🖥 <b>Сервери</b> – обери:"),
    "srv_none": ("Brak instancji w AMP.", "No instances in AMP.", "В AMP нет инстансов.", "В AMP немає інстансів."),
    "srv_players": ("👥 Gracze: {n}", "👥 Players: {n}", "👥 Игроков: {n}", "👥 Гравців: {n}"),
    "srv_confirm": ("❓ Na pewno <b>{action}</b> – {name}?", "❓ Really <b>{action}</b> – {name}?",
                    "❓ Точно <b>{action}</b> – {name}?", "❓ Точно <b>{action}</b> – {name}?"),
    "srv_confirm_players": ("⚠️ Na serwerze gra teraz {n} os.!", "⚠️ {n} player(s) are on the server now!",
                            "⚠️ Сейчас на сервере игроков: {n}!", "⚠️ Зараз на сервері гравців: {n}!"),
    "srv_working": ("⏳ {action}: {name}…", "⏳ {action}: {name}…", "⏳ {action}: {name}…", "⏳ {action}: {name}…"),
    "srv_done": ("✅ {action}: {name} – wysłane do AMP.", "✅ {action}: {name} – sent to AMP.",
                 "✅ {action}: {name} – отправлено в AMP.", "✅ {action}: {name} – надіслано до AMP."),
    "srv_audit": ("🛠 {who}: {action} – {name}", "🛠 {who}: {action} – {name}", "🛠 {who}: {action} – {name}",
                  "🛠 {who}: {action} – {name}"),
    "btn_yes": ("✅ Tak", "✅ Yes", "✅ Да", "✅ Так"),
    "btn_back": ("↩️ Wróć", "↩️ Back", "↩️ Назад", "↩️ Назад"),
    "btn_refresh": ("🔄 Odśwież", "🔄 Refresh", "🔄 Обновить", "🔄 Оновити"),
    "act_start": ("▶️ Start", "▶️ Start", "▶️ Запуск", "▶️ Запуск"),
    "act_stop": ("⏹ Stop", "⏹ Stop", "⏹ Стоп", "⏹ Стоп"),
    "act_restart": ("🔁 Restart", "🔁 Restart", "🔁 Перезапуск", "🔁 Перезапуск"),
    "act_update": ("⬆️ Aktualizacja gry", "⬆️ Game update", "⬆️ Обновление игры", "⬆️ Оновлення гри"),
    "act_backup": ("💾 Backup", "💾 Backup", "💾 Бэкап", "💾 Бекап"),
    "act_kick": ("👢 Kick", "👢 Kick", "👢 Кик", "👢 Кік"),
    "act_ban": ("🚫 Ban", "🚫 Ban", "🚫 Бан", "🚫 Бан"),
    "btn_players": ("👥 Gracze", "👥 Players", "👥 Игроки", "👥 Гравці"),
    "btn_console": ("⌨️ Konsola", "⌨️ Console", "⌨️ Консоль", "⌨️ Консоль"),
    "btn_password": ("🔑 Hasło", "🔑 Password", "🔑 Пароль", "🔑 Пароль"),
    "btn_cancel": ("✖️ Anuluj", "✖️ Cancel", "✖️ Отмена", "✖️ Скасувати"),
    "srv_need_running": ("Najpierw uruchom instancję.", "Start the instance first.", "Сначала запусти инстанс.",
                         "Спочатку запусти інстанс."),
    "pl_title": ("👥 <b>{name}</b> – gracze online:", "👥 <b>{name}</b> – players online:",
                 "👥 <b>{name}</b> – игроки онлайн:", "👥 <b>{name}</b> – гравці онлайн:"),
    "pl_none": ("Nikt nie gra.", "Nobody is playing.", "Никто не играет.", "Ніхто не грає."),
    "pl_confirm": ("❓ <b>{action}</b>: {player} na {name}?", "❓ <b>{action}</b>: {player} on {name}?",
                   "❓ <b>{action}</b>: {player} на {name}?", "❓ <b>{action}</b>: {player} на {name}?"),
    "con_prompt": ("⌨️ <b>{name}</b>: napisz komendę konsoli (np. <code>say Cześć</code>).",
                   "⌨️ <b>{name}</b>: type a console command (e.g. <code>say Hello</code>).",
                   "⌨️ <b>{name}</b>: напиши команду консоли (например, <code>say Привет</code>).",
                   "⌨️ <b>{name}</b>: напиши команду консолі (наприклад, <code>say Привіт</code>)."),
    "con_confirm": ("❓ Wysłać do konsoli {name}?\n<code>{cmd}</code>",
                    "❓ Send to the {name} console?\n<code>{cmd}</code>",
                    "❓ Отправить в консоль {name}?\n<code>{cmd}</code>",
                    "❓ Надіслати в консоль {name}?\n<code>{cmd}</code>"),
    "con_sent": ("⌨️ Wysłano. Odpowiedź serwera:", "⌨️ Sent. Server output:", "⌨️ Отправлено. Ответ сервера:",
                 "⌨️ Надіслано. Відповідь сервера:"),
    "con_silent": ("⌨️ Wysłano (serwer nic nie odpisał).", "⌨️ Sent (no output from the server).",
                   "⌨️ Отправлено (сервер ничего не ответил).", "⌨️ Надіслано (сервер нічого не відповів)."),
    "pw_title": ("🔑 <b>{name}</b> – które hasło zmienić?", "🔑 <b>{name}</b> – which password?",
                 "🔑 <b>{name}</b> – какой пароль изменить?", "🔑 <b>{name}</b> – який пароль змінити?"),
    "pw_none": ("Nie znalazłem ustawienia hasła dla tej gry.", "No password setting found for this game.",
                "Не нашёл настройки пароля для этой игры.", "Не знайшов налаштування пароля для цієї гри."),
    "pw_prompt": ("🔑 Napisz nowe hasło dla „{setting}” (wiadomość z hasłem od razu usunę z czatu). "
                  "Kropka <code>.</code> = bez hasła.",
                  "🔑 Type the new value of \"{setting}\" (I'll delete your message right away). "
                  "A dot <code>.</code> = no password.",
                  "🔑 Напиши новый пароль для «{setting}» (сообщение сразу удалю). Точка <code>.</code> = без пароля.",
                  "🔑 Напиши новий пароль для «{setting}» (повідомлення одразу видалю). "
                  "Крапка <code>.</code> = без пароля."),
    "pw_confirm": ("❓ Ustawić nowe hasło „{setting}” na {name}? ({n} znaków)",
                   "❓ Set the new \"{setting}\" on {name}? ({n} characters)",
                   "❓ Установить новый пароль «{setting}» на {name}? ({n} символов)",
                   "❓ Встановити новий пароль «{setting}» на {name}? ({n} символів)"),
    "pw_done": ("✅ Hasło zmienione. Zwykle trzeba zrestartować serwer.",
                "✅ Password changed. The server usually needs a restart.",
                "✅ Пароль изменён. Обычно нужен перезапуск сервера.",
                "✅ Пароль змінено. Зазвичай потрібен перезапуск сервера."),
    "st_ready": ("działa", "running", "работает", "працює"),
    "st_stopped": ("zatrzymany", "stopped", "остановлен", "зупинено"),
    "st_starting": ("uruchamia się", "starting", "запускается", "запускається"),
    "st_stopping": ("zatrzymuje się", "stopping", "останавливается", "зупиняється"),
    "st_updating": ("aktualizuje się", "updating", "обновляется", "оновлюється"),
    "st_sleeping": ("uśpiony", "sleeping", "спит", "спить"),
    "st_failed": ("błąd", "failed", "ошибка", "помилка"),
    "st_off": ("instancja wyłączona", "instance off", "инстанс выключен", "інстанс вимкнено"),
    "st_other": ("stan {n}", "state {n}", "состояние {n}", "стан {n}"),
    # powiadomienia z panelu AMP
    "task_running": ("⏳ <b>{inst}</b>: {name}", "⏳ <b>{inst}</b>: {name}", "⏳ <b>{inst}</b>: {name}",
                     "⏳ <b>{inst}</b>: {name}"),
    "task_done": ("✅ <b>{inst}</b>: {name} – gotowe", "✅ <b>{inst}</b>: {name} – done",
                  "✅ <b>{inst}</b>: {name} – готово", "✅ <b>{inst}</b>: {name} – готово"),
    "task_failed": ("❌ <b>{inst}</b>: {name} – nie powiodło się", "❌ <b>{inst}</b>: {name} – failed",
                    "❌ <b>{inst}</b>: {name} – не удалось", "❌ <b>{inst}</b>: {name} – не вдалося"),
    "state_change": ("{emoji} <b>{inst}</b>: {state}", "{emoji} <b>{inst}</b>: {state}",
                     "{emoji} <b>{inst}</b>: {state}", "{emoji} <b>{inst}</b>: {state}"),
    "panel": ("panel AMP", "AMP panel", "панель AMP", "панель AMP"),
}


def norm_lang(code):
    code = (code or "").lower()[:2]
    code = "uk" if code == "ua" else code
    return code if code in LANGS else None


DEFAULT_LANG = norm_lang(os.environ.get("BOT_LANG")) or "pl"
CHAT_LANGS = {}  # str(chat_id) -> jezyk, wczytywane z bazy


def lang_for(chat_id=None):
    return CHAT_LANGS.get(str(chat_id or CHAT_ID), DEFAULT_LANG)


def t(key, lang=None, **kw):
    text = STRINGS[key][LANG_ORDER.index(lang or lang_for())]
    return text.format(**kw) if kw else text


# notatki w bazie: kody, a dla starych wpisow z 1.0.0 polskie teksty
NOTE_KEYS = {"restart": "note_restart", "restart serwera": "note_restart",
             "prestart": "note_prestart", "przed startem bota": "note_prestart",
             "botrestart": "note_botrestart", "bot zrestartowany": "note_botrestart"}


def note_text(note, lang=None):
    return t(NOTE_KEYS[note], lang) if note in NOTE_KEYS else note


# ---------- drobiazgi ----------

def log(msg):
    print(msg, flush=True)


def esc(s):
    return html.escape(str(s), quote=False)


def fmt_duration(seconds, lang=None):
    minutes = max(0, int(seconds // 60))
    h, m = divmod(minutes, 60)
    return t("dur_hm", lang, h=h, m=m) if h else t("dur_m", lang, m=m)


def ts(stamp):
    return datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M") if stamp else "-"


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


# ---------- Telegram ----------

def edit(chat_id, message_id, text, markup=None):
    params = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": "true"}
    if markup:
        params["reply_markup"] = json.dumps(markup)
    try:
        tg_api("editMessageText", params)
    except Exception as e:  # np. "message is not modified" po odswiezeniu bez zmian
        log(f"editMessageText: {getattr(e, 'code', type(e).__name__)}")


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
            return (tg_api("sendMessage", params).get("result") or {}).get("message_id")
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
        lines = [t("new_player")] if new_player else []
        lines += [t("joined", name=esc(name)), f"🎮 {esc(self.label)}"]
        if steamid:
            lines.append(f'🆔 SteamID: <a href="https://steamcommunity.com/profiles/{steamid}">{steamid}</a>')
        elif userid and self.game == "Minecraft":
            lines.append(f"🆔 UUID: <code>{esc(userid)}</code>")
        if ip:
            lines.append(f"🌍 IP: <code>{esc(ip)}</code>")
        lines.append(t("online_count", n=len(self.online)))
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
        extra = f" ({esc(note_text(note))})" if note else ""
        dur = fmt_duration(now - p["since"])
        if p.get("partial"):
            dur = t("at_least", dur=dur)
        send("\n".join([t("left", name=esc(p["name"]), extra=extra), f"🎮 {esc(self.label)}",
                        t("playtime", dur=dur), t("online_count", n=len(self.online))]))

    def finish_replay(self):
        """Gracze, ktorzy weszli przed startem bota: sesja liczona od teraz, bez powiadomienia."""
        self.silent = False
        now = int(time.time())
        for p in self.online.values():
            cur = self.db.execute(
                "INSERT INTO sessions(instance, game, username, userid, steamid, ip, joined, note) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (self.name, self.game, p["name"], p["userid"], p["steamid"], p.get("ip"), now, "prestart"))
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
        send(t("death", name=esc(name), n=n) + f"\n🎮 {esc(self.label)}")

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
                    self.on_leave(name=p["name"], note="restart")
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
    db.execute("UPDATE sessions SET note='botrestart' WHERE left IS NULL AND note IS NULL")
    db.commit()
    return db


def meta_get(db, key):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def meta_set(db, key, value):
    db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", (key, str(value)))
    db.commit()


def load_langs(db):
    CHAT_LANGS.clear()
    for key, value in db.execute("SELECT key, value FROM meta WHERE key LIKE 'lang:%'"):
        if norm_lang(value):
            CHAT_LANGS[key[len("lang:"):]] = norm_lang(value)


def warn_once(db, inst):
    if db.execute("SELECT 1 FROM warned WHERE instance=?", (inst.name,)).fetchone():
        return
    db.execute("INSERT INTO warned(instance) VALUES (?)", (inst.name,))
    db.commit()
    send(t("warn_unknown", inst=esc(inst.name), game=esc(inst.game or t("unknown_game"))))


# ---------- laptop: bateria, temperatura, playit ----------

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


def host_report(lang=None):
    ac, bat = power_state()
    temp = cpu_temp()
    lines = []
    if ac is not None or bat is not None:
        src = t("h_mains", lang) if ac else (t("h_on_battery", lang) if ac is False else "?")
        src += t("h_bat", lang, bat=bat) if bat is not None else t("h_nobat", lang)
        lines.append(t("h_power", lang, src=src))
    if temp is not None:
        lines.append(f"CPU: {temp:.0f}°C")
    try:
        mem = dict(row.split(":", 1) for row in open("/proc/meminfo").read().splitlines())
        total = int(mem["MemTotal"].split()[0]) / 1048576
        avail = int(mem["MemAvailable"].split()[0]) / 1048576
        lines.append(t("h_ram", lang, used=f"{total - avail:.1f}", total=f"{total:.1f}"))
    except (OSError, KeyError, ValueError):
        pass
    try:
        du = shutil.disk_usage("/")
        lines.append(t("h_disk", lang, pct=du.used * 100 // du.total, free=f"{du.free / 1e9:.0f}"))
    except OSError:
        pass
    try:
        lines.append(t("h_load", lang, load=f"{os.getloadavg()[0]:.2f}"))
    except (OSError, AttributeError):
        pass
    up = read("/proc/uptime")
    if up:
        lines.append(t("h_uptime", lang, dur=fmt_duration(float(up.split()[0]), lang)))
    ok = playit_ok(playit_mode())
    lines.append(t("h_playit_ok" if ok else "h_playit_down" if ok is False else "h_playit_none", lang))
    return "\n".join(lines)


class HostMonitor:
    def __init__(self):
        self.bat_alerted = False
        self.temp_alerted = False
        self.playit_mode = playit_mode()
        self.playit_fails = 0
        self.playit_down = False

    def startup_notes(self):
        return [t("no_playit", svc=PLAYIT_SERVICE)] if self.playit_mode is None else []

    def check(self):
        # laptop stoi na zasilaczu z limitem ladowania 50%, wiec spadek ponizej progu = cos nie tak
        _, bat = power_state()
        if bat is not None and BATTERY_WARN:
            if bat < BATTERY_WARN and not self.bat_alerted:
                self.bat_alerted = True
                send(t("bat_low", bat=bat, th=BATTERY_WARN))
            elif bat >= BATTERY_WARN + 3 and self.bat_alerted:
                self.bat_alerted = False
                send(t("bat_ok", bat=bat))

        temp = cpu_temp()
        if temp is not None:
            if temp >= TEMP_ALERT and not self.temp_alerted:
                self.temp_alerted = True
                send(t("temp_hot", t=f"{temp:.0f}"))
            elif temp < TEMP_ALERT - 10 and self.temp_alerted:
                self.temp_alerted = False
                send(t("temp_ok", t=f"{temp:.0f}"))

        if self.playit_mode is None:
            return
        ok = playit_ok(self.playit_mode)
        if ok is False:
            self.playit_fails += 1
            if self.playit_fails >= 2 and not self.playit_down:  # 2 kolejne sprawdzenia = ok. minuta
                self.playit_down = True
                send(t("playit_down"))
        elif ok:
            self.playit_fails = 0
            if self.playit_down:
                self.playit_down = False
                send(t("playit_up"))


# ---------- statystyki ----------

def player_key(row):
    username, steamid, userid, game = row
    return steamid or (userid if game == "Minecraft" else None) or f"{game}:{username}"


def weekly_summary(db, days=7, lang=None):
    now = int(time.time())
    since = now - days * 86400
    rows = db.execute("SELECT game, username, steamid, userid, joined, left FROM sessions "
                      "WHERE left IS NOT NULL AND left > ?", (since,)).fetchall()
    if not rows:
        return t("w_title", lang, days=days) + "\n" + t("w_nobody", lang)
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
        moment = start
        while moment < left:  # rozklad czasu gry na godziny doby
            nxt = min(left, (moment // 3600 + 1) * 3600)
            per_hour[datetime.fromtimestamp(moment).hour] += nxt - moment
            moment = nxt
    lines = [t("w_title", lang, days=days), ""]
    for game, (dur, players, sessions) in sorted(per_game.items(), key=lambda x: -x[1][0]):
        lines.append(t("w_game", lang, game=esc(game), dur=fmt_duration(dur, lang), players=len(players),
                       sessions=sessions))
    lines += ["", t("w_top", lang)]
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    for medal, (key, dur) in zip(medals, sorted(per_player.items(), key=lambda x: -x[1])[:5], strict=False):
        lines.append(f"{medal} {esc(names[key])} – {fmt_duration(dur, lang)}")
    if per_hour:
        h = per_hour.most_common(1)[0][0]
        lines += ["", t("w_peak", lang, hours=f"{h:02d}:00–{(h + 1) % 24:02d}:00")]
    deaths = db.execute("SELECT username, COUNT(*) c FROM deaths WHERE ts > ? GROUP BY username "
                        "ORDER BY c DESC LIMIT 1", (since,)).fetchone()
    if deaths:
        lines.append(t("w_deaths", lang, name=esc(deaths[0]), n=deaths[1]))
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


# ---------- AMP: API panelu ----------

class AmpError(Exception):
    pass


def amp_unwrap(r):
    # nowsze AMP opakowuja wynik w {"result": ...}; bledy wygladaja jak {"Title": ..., "Message": ...}
    if isinstance(r, dict) and set(r) == {"result"}:
        r = r["result"]
    if isinstance(r, dict) and "Title" in r and "StackTrace" in r:
        raise AmpError(r.get("Message") or r["Title"])
    return r


class Amp:
    """Klient API AMP (ADS). Loguje sie przy pierwszym wywolaniu i ponownie, gdy sesja wygasnie."""

    def __init__(self, url=None, user=None, password=None):
        self.url = (url if url is not None else AMP_URL).rstrip("/")
        self.user = user if user is not None else AMP_USER
        self.password = password if password is not None else AMP_PASS
        self.session = None
        self.sessions = {}  # prefiks instancji -> sesja (API instancji przez panel ADS)

    @property
    def configured(self):
        return bool(self.url and self.user and self.password)

    def _post(self, path, payload, timeout=30):
        req = urllib.request.Request(f"{self.url}/API/{path}", data=json.dumps(payload).encode(),
                                     headers={"Accept": "application/json", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace").strip()
        return json.loads(body) if body else None

    def login(self, prefix=""):
        r = amp_unwrap(self._post(f"{prefix}Core/Login", {"username": self.user, "password": self.password,
                                                          "token": "", "rememberMe": False}))
        if not isinstance(r, dict) or not r.get("success"):
            reason = r.get("resultReason") if isinstance(r, dict) else r
            raise AmpError(f"login: {reason}")
        return r["sessionID"]

    def call(self, method, **params):
        for _ in range(2):
            if not self.session:
                self.session = self.login()
            r = self._post(method, {"SESSIONID": self.session, **params})
            if isinstance(r, dict) and r.get("Title") == "Unauthorized Access":
                self.session = None  # sesja wygasla: logujemy sie jeszcze raz
                continue
            r = amp_unwrap(r)
            if isinstance(r, dict) and r.get("Status") is False:
                raise AmpError(r.get("Reason") or method)
            return r
        raise AmpError("Unauthorized Access")

    def instances(self):
        """Instancje gier (bez samego panelu ADS): name, friendly, module, running, state."""
        out = []
        for target in self.call("ADSModule/GetInstances") or []:
            for i in target.get("AvailableInstances") or []:
                if i.get("Module") == "ADS":
                    continue
                out.append({"name": i.get("InstanceName"), "id": i.get("InstanceID"),
                            "friendly": i.get("FriendlyName") or i.get("InstanceName"),
                            "module": i.get("ModuleDisplayName") or i.get("Module"),
                            "running": bool(i.get("Running")), "state": i.get("AppState")})
        return sorted(out, key=lambda x: (x["friendly"] or "").lower())

    def instance_call(self, inst_id, method, **params):
        """Wywolanie API konkretnej instancji przez panel (ADSModule/Servers/<id>/API/...)."""
        prefix = f"ADSModule/Servers/{inst_id}/API/"
        for _ in range(2):
            if not self.sessions.get(prefix):
                self.sessions[prefix] = self.login(prefix)
            r = self._post(prefix + method, {"SESSIONID": self.sessions[prefix], **params})
            if isinstance(r, dict) and r.get("Title") == "Unauthorized Access":
                self.sessions.pop(prefix, None)
                continue
            r = amp_unwrap(r)
            if isinstance(r, dict) and r.get("Status") is False:
                raise AmpError(r.get("Reason") or method)
            return r
        raise AmpError("Unauthorized Access")

    def find(self, name):
        inst = next((i for i in self.instances() if i["name"] == name), None)
        if inst is None:
            raise AmpError(name)
        return inst

    def users(self, name):
        """Gracze online wedlug AMP: lista nickow."""
        inst = self.find(name)
        if not inst["running"]:
            return []
        r = self.instance_call(inst["id"], "Core/GetUserList")
        if isinstance(r, dict):
            names = list(r.values())
        else:
            names = [u.get("Name") if isinstance(u, dict) else u for u in r or []]
        return sorted(str(n) for n in names if n)

    def console(self, name, command, wait=2.0):
        """Komenda do konsoli gry; zwraca linie, ktore serwer wypisal w ciagu `wait` sekund."""
        inst = self.find(name)
        self.instance_call(inst["id"], "Core/GetUpdates")  # odbieramy zalegle wpisy, zeby pokazac tylko odpowiedz
        self.instance_call(inst["id"], "Core/SendConsoleMessage", message=command)
        time.sleep(wait)
        updates = self.instance_call(inst["id"], "Core/GetUpdates") or {}
        entries = updates.get("ConsoleEntries") if isinstance(updates, dict) else None
        return [str(e.get("Contents", "")) for e in entries or [] if isinstance(e, dict)][-12:]

    def password_settings(self, name):
        """Ustawienia z haslem gry (nie logowania do Steama ani AMP): [(nazwa, node)]."""
        inst = self.find(name)
        spec = self.instance_call(inst["id"], "Core/GetSettingsSpec") or {}
        found = []
        for settings in (spec.values() if isinstance(spec, dict) else []):
            for item in settings or []:
                node, label = str(item.get("Node", "")), str(item.get("Name", ""))
                text = f"{node} {label}".lower()
                if "password" in text and not any(x in text for x in ("steam", "login", "core.", "rcon", "admin")):
                    found.append((label or node, node))
        return found

    def set_config(self, name, node, value):
        inst = self.find(name)
        return self.instance_call(inst["id"], "Core/SetConfig", node=node, value=value)

    @staticmethod
    def norm_tasks(raw):
        """RunningTask z AMP -> {"id", "name", "desc", "pct", "failed"}; brakujace pola sa tolerowane."""
        out = []
        for task in raw or []:
            if not isinstance(task, dict):
                continue
            name = task.get("Name") or task.get("Description") or "?"
            desc = task.get("Description") if task.get("Description") != name else ""
            pct = task.get("ProgressPercent")
            if task.get("IsIndeterminate") or not isinstance(pct, (int, float)) or pct < 0:
                pct = None
            state = str(task.get("State", "")).lower()
            out.append({"id": str(task.get("Id") or name), "name": name, "desc": desc or "",
                        "pct": pct, "failed": state in ("failed", "faulted", "error", "-1")})
        return out

    def tasks(self, instances=None):
        """Zadania w toku: panelu i dzialajacych instancji. Zwraca {(zrodlo, id zadania): zadanie}."""
        found = {}
        sources = [("", None)] + [(i["friendly"], i["id"]) for i in instances or [] if i["running"] and i["id"]]
        for label, inst_id in sources:
            try:
                raw = self.call("Core/GetTasks") if inst_id is None else self.instance_call(inst_id, "Core/GetTasks")
            except Exception as e:  # jedna instancja bez odpowiedzi nie moze zatrzymac reszty
                log(f"AMP GetTasks {label or 'ADS'}: {e}")
                continue
            for task in self.norm_tasks(raw):
                found[(label, task["id"])] = task
        return found

    ACTIONS = ("start", "stop", "restart", "update", "backup")
    # komendy konsoli dla kick/ban; {player} = nick
    GAME_COMMANDS = {"default": {"kick": "kick {player}", "ban": "ban {player}"}}

    def action(self, act, name):
        """
        start: wlacza instancje (ADS), a gdy juz dziala - sama gre; stop: cala instancja;
        restart: gra (albo instancja, gdy wylaczona); update: aktualizacja gry (SteamCMD itp.);
        backup: kopia zapasowa instancji. Postep widac w zadaniach (AmpWatcher).
        """
        inst = self.find(name)
        if act == "stop":
            return self.call("ADSModule/StopInstance", InstanceName=name)
        if not inst["running"]:
            if act in ("start", "restart"):
                return self.call("ADSModule/StartInstance", InstanceName=name)
            raise AmpError(t("srv_need_running"))
        if act == "start":
            return self.instance_call(inst["id"], "Core/Start")
        if act == "restart":
            return self.instance_call(inst["id"], "Core/Restart")
        if act == "update":
            return self.instance_call(inst["id"], "Core/UpdateApplication")
        title = datetime.now().strftime("Telegram %Y-%m-%d %H:%M")
        return self.instance_call(inst["id"], "LocalFileBackupPlugin/TakeBackup", Title=title,
                                  Description="amp-tg-bot", Sticky=False)

    def player_action(self, act, name, player):
        commands = self.GAME_COMMANDS.get(self.find(name)["module"], self.GAME_COMMANDS["default"])
        return self.console(name, commands[act].format(player=player))


# AppState z AMP -> (emoji, klucz tekstu)
AMP_STATES = {0: ("🔴", "st_stopped"), 5: ("🟡", "st_starting"), 7: ("🟡", "st_starting"), 10: ("🟡", "st_starting"),
              20: ("🟢", "st_ready"), 30: ("🟡", "st_starting"), 40: ("🟠", "st_stopping"), 45: ("🟠", "st_stopping"),
              50: ("💤", "st_sleeping"), 70: ("⬆️", "st_updating"), 75: ("⬆️", "st_updating"),
              100: ("❌", "st_failed")}


def amp_state(inst, lang=None):
    if not inst["running"]:
        return "⚫", t("st_off", lang)
    emoji, key = AMP_STATES.get(inst["state"], ("⚪", None))
    return emoji, t(key, lang) if key else t("st_other", lang, n=inst["state"])


def progress_bar(pct):
    filled = int(round(pct / 10))
    return "▓" * filled + "░" * (10 - filled) + f" {pct:.0f}%"


class AmpWatcher:
    """
    Panel AMP na Telegramie: zadania w toku (aktualizacja, backup, pobieranie) jako jedna wiadomosc
    z paskiem postepu, edytowana w miejscu, oraz zmiany stanu instancji (start, stop, awaria).
    """

    def __init__(self, amp):
        self.amp = amp
        self.tasks = {}  # (zrodlo, id) -> {"msg": message_id, "text": ostatni tekst, "edited": czas}
        self.states = None  # nazwa -> (running, AppState); None = jeszcze nie znamy
        self.instances = []
        self.last_tasks = self.last_states = 0

    def task_text(self, label, task, final=None):
        inst = esc(label or t("panel"))
        if final:
            return t(final, inst=inst, name=esc(task["name"]))
        lines = [t("task_running", inst=inst, name=esc(task["name"]))]
        if task["desc"]:
            lines.append(esc(task["desc"]))
        if task["pct"] is not None:
            lines.append(progress_bar(task["pct"]))
        return "\n".join(lines)

    def check_tasks(self):
        current = {k: v for k, v in self.amp.tasks(self.instances).items() if not AMP_TASK_IGNORE.search(v["name"])}
        now = time.time()
        for key, task in current.items():
            text = self.task_text(key[0], task)
            known = self.tasks.setdefault(key, {"msg": None, "text": None, "edited": 0, "seen": now, "task": task})
            known["task"] = task
            if known["msg"] is None:
                # wiadomosc dopiero, gdy zadanie trwa dluzej - krotkie konczy sie po cichu
                if now - known["seen"] >= AMP_TASK_MIN_SECONDS:
                    known.update(msg=send(text), text=text, edited=now)
            elif text != known["text"] and now - known["edited"] >= 10:  # Telegram nie lubi czestych edycji
                edit(CHAT_ID, known["msg"], text)
                known.update(text=text, edited=now)
        for key in [k for k in self.tasks if k not in current]:  # zadanie zniknelo = skonczone
            known = self.tasks.pop(key)
            if known["msg"] is None and not known["task"]["failed"]:
                continue  # krotkie i udane: bez wiadomosci
            final = "task_failed" if known["task"]["failed"] else "task_done"
            text = self.task_text(key[0], known["task"], final)
            if known["msg"]:
                edit(CHAT_ID, known["msg"], text)
            else:
                send(text)

    def check_states(self):
        self.instances = self.amp.instances()
        states = {i["name"]: (i["running"], i["state"]) for i in self.instances}
        if self.states is not None:
            for inst in self.instances:
                before = self.states.get(inst["name"])
                if before is not None and before != states[inst["name"]] and self.stable(inst):
                    emoji, state = amp_state(inst)
                    send(t("state_change", emoji=emoji, inst=esc(inst["friendly"]), state=esc(state)))
        self.states = states

    @staticmethod
    def stable(inst):
        # stany przejsciowe (uruchamia sie, zatrzymuje sie) widac w zadaniach; tu tylko wynik
        return not inst["running"] or inst["state"] in (0, 20, 50, 100)

    def poll(self):
        if not (AMP_NOTIFY and self.amp.configured):
            return
        now = time.time()
        try:
            if now - self.last_states >= AMP_STATE_SECONDS:
                self.last_states = now
                self.check_states()
            if now - self.last_tasks >= AMP_TASK_SECONDS:
                self.last_tasks = now
                self.check_tasks()
        except Exception as e:  # AMP chwilowo niedostepny: sprobujemy przy nastepnym obrocie
            log(f"AMP watcher: {e}")


def apt_upgradable():
    """Pakiety do aktualizacji wedlug apt: [{"name", "new", "old", "security"}] (bez roota)."""
    try:
        out = subprocess.run(["apt", "list", "--upgradable"], capture_output=True, text=True, timeout=120,
                             env={**os.environ, "LANG": "C"}).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_apt(out)


def parse_apt(text):
    pkgs = []
    for line in text.splitlines():
        m = re.match(r"^([^/\s]+)/(\S+)\s+(\S+)\s+\S+\s+\[upgradable from:\s*([^\]]+)\]", line)
        if m:
            pkgs.append({"name": m.group(1), "new": m.group(3), "old": m.group(4).strip(),
                         "security": "-security" in m.group(2)})
    return pkgs


def reboot_required():
    """None = restart niepotrzebny, inaczej lista pakietow, ktore go wymagaja."""
    if not os.path.exists("/var/run/reboot-required"):
        return None
    return sorted(set((read("/var/run/reboot-required.pkgs") or "").split()))


def amp_update_info(amp):
    """(jest_aktualizacja, wersja) panelu AMP albo (False, None), gdy nie wiadomo."""
    try:
        info = amp.call("Core/GetUpdateInfo") if amp.configured else None
    except Exception as e:
        log(f"AMP GetUpdateInfo: {e}")
        return False, None
    if not isinstance(info, dict):
        return False, None
    lowered = {k.lower(): v for k, v in info.items()}
    available = bool(lowered.get("updateavailable") or lowered.get("isupdateavailable"))
    return available, lowered.get("version") or lowered.get("newversion")


def updates_report(amp, lang=None, pkgs=None, reboot=None, amp_info=None):
    pkgs = apt_upgradable() if pkgs is None else pkgs
    reboot = reboot_required() if reboot is None else reboot
    amp_available, amp_version = amp_update_info(amp) if amp_info is None else amp_info
    lines = []
    if pkgs is None:
        lines.append(t("upd_apt_unknown", lang))
    elif pkgs:
        security = [p for p in pkgs if p["security"]]
        lines.append(t("upd_apt", lang, n=len(pkgs), sec=len(security)))
        important = [p for p in pkgs if p["security"] or p["name"].startswith(IMPORTANT_PACKAGES)]
        for p in important[:15]:
            mark = " 🛡" if p["security"] else ""
            lines.append(f"  • <code>{esc(p['name'])}</code> {esc(p['old'])} → {esc(p['new'])}{mark}")
        if len(pkgs) > len(important[:15]):
            lines.append(t("upd_more", lang, n=len(pkgs) - len(important[:15])))
    else:
        lines.append(t("upd_apt_none", lang))
    if reboot is not None:
        lines.append(t("upd_reboot", lang, pkgs=esc(", ".join(reboot[:8]) or "?")))
    if amp_available:
        lines.append(t("upd_amp", lang, version=esc(amp_version or "?")))
    if pkgs:
        lines.append(t("upd_how", lang))
    return t("upd_title", lang) + "\n" + "\n".join(lines)


class UpdateMonitor:
    """Co kilka godzin: aktualizacje apt (z bezpieczenstwem), restart systemu, nowa wersja AMP."""

    def __init__(self, amp, db):
        self.amp, self.db = amp, db
        self.last = 0

    def poll(self):
        if not UPDATES_CHECK_HOURS or time.time() - self.last < UPDATES_CHECK_HOURS * 3600:
            return
        self.last = time.time()
        pkgs, reboot = apt_upgradable(), reboot_required()
        amp_info = amp_update_info(self.amp)
        if pkgs is None:
            return
        # powiadomienie tylko o czyms nowym: bezpieczenstwo, restart, wazne pakiety, AMP
        keys = sorted(f"{p['name']}={p['new']}" for p in pkgs
                      if p["security"] or p["name"].startswith(IMPORTANT_PACKAGES))
        signature = json.dumps([keys, reboot, amp_info[0] and amp_info[1]])
        if signature == meta_get(self.db, "updates_seen"):
            return
        meta_set(self.db, "updates_seen", signature)
        if keys or reboot is not None or amp_info[0]:
            send(updates_report(self.amp, pkgs=pkgs, reboot=reboot, amp_info=amp_info))


def amp_test():
    """--amp-test: logowanie, lista instancji i funkcje API przydatne dla bota."""
    amp = Amp()
    if not amp.configured:
        print("Brak AMP_URL / AMP_USER / AMP_PASS w " + ENV_FILE)
        return 1
    print(f"Logowanie do {amp.url} jako {amp.user}...")
    amp.session = amp.login()
    print("OK, zalogowano.\n\nInstancje:")
    insts = amp.instances()
    for i in insts:
        print(f"  {amp_state(i, 'pl')[0]} {i['name']:<20} {i['module'] or '':<14} running={i['running']} "
              f"state={i['state']}")
    keywords = re.compile(r"start|stop|restart|upgrade|update|backup|user|kick|ban|console|config|setting|"
                          r"password|status|schedule|task", re.I)

    def show(spec, title):
        print(f"\n{title}:")
        for module, methods in sorted((spec or {}).items()):
            names = sorted(m for m in (methods or {}) if keywords.search(m))
            if names:
                print(f"  {module}: {', '.join(names)}")

    show(amp.call("Core/GetAPISpec"), "API panelu (ADS)")
    running = next((i for i in insts if i["running"] and i["id"]), None)
    if running:
        prefix = f"ADSModule/Servers/{running['id']}/API/"
        try:
            sid = amp.login(prefix)
            spec = amp_unwrap(amp._post(prefix + "Core/GetAPISpec", {"SESSIONID": sid}))
            show(spec, f"API instancji {running['name']}")
        except Exception as e:
            print(f"\nAPI instancji {running['name']}: blad {e}")
    else:
        print("\nZadna instancja nie dziala - uruchom jedna i powtorz, zeby zobaczyc API instancji.")
    return 0


# ---------- komendy na Telegramie ----------

# (komenda, argumenty w /help); opisy w STRINGS["c_<komenda>"]
COMMANDS = [("online", ""), ("servers", ""), ("updates", ""), ("status", ""), ("history", " [N]"), ("player", " NICK"),
            ("week", ""), ("lang", ""), ("version", ""), ("update", ""), ("rollback", ""), ("help", "")]
# stare polskie nazwy z 1.0.0 dalej dzialaja
ALIASES = {"historia": "history", "gracz": "player", "tydzien": "week", "tydzień": "week", "wersja": "version",
           "pomoc": "help", "start": "help", "jezyk": "lang", "język": "lang", "language": "lang"}
# komendy sa tylko pod przyciskiem "Menu"; to chowa klawiature z przyciskami z wersji 1.0.0-1.1.0
NO_KEYBOARD = {"remove_keyboard": True}
LANG_BUTTONS = {"inline_keyboard": [[{"text": LANGS[c], "callback_data": f"lang:{c}"} for c in ("pl", "en")],
                                    [{"text": LANGS[c], "callback_data": f"lang:{c}"} for c in ("ru", "uk")]]}


def help_text(lang):
    lines = [t("help_title", lang, v=VERSION)]
    lines += [f"/{cmd}{esc(args)} – {t('c_' + cmd, lang)}" for cmd, args in COMMANDS]
    return "\n".join(lines)


def set_menu(chat_id):
    """Menu komend (przycisk 'Menu' w Telegramie) na czacie admina, w jego jezyku."""
    lang = lang_for(chat_id)
    commands = json.dumps([{"command": c, "description": t("c_" + c, lang)} for c, _ in COMMANDS])
    try:
        tg_api("setMyCommands", {"commands": commands, "scope": json.dumps({"type": "chat", "chat_id": chat_id})})
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
    for lang in LANG_ORDER:  # wszystkie teksty daja sie sformatowac w kazdym jezyku
        help_text(lang)
        fmt_duration(3700, lang)
    print(f"OK {VERSION}")


def cmd_online(instances, lang=None):
    now = time.time()
    lines = []
    for inst in instances.values():
        if inst.status != "ok":
            continue
        players = sorted(inst.online.values(), key=lambda p: p["since"])
        if players:
            lines.append(f"🎮 <b>{esc(inst.label)}</b> ({len(players)})")
            lines += [f"  • {esc(p['name'])} – {fmt_duration(now - p['since'], lang)}" for p in players]
    return "\n".join(lines) if lines else t("nobody_online", lang)


def format_sessions(rows, lang=None):
    out = []
    for game, user, _sid, _uid, joined, left, note in rows:
        dur = fmt_duration(left - joined, lang) if left else (note_text(note, lang) or t("in_game", lang))
        out.append(f"{ts(joined)[5:]} {game[:9]:<9} {user[:16]:<16} {dur}")
    return "<pre>" + esc("\n".join(out)) + "</pre>" if out else t("no_sessions", lang)


def cmd_history(db, args, lang=None):
    n = min(int(args[0]), 50) if args and args[0].isdigit() else 15
    rows = db.execute("SELECT game, username, steamid, userid, joined, left, note FROM sessions "
                      "ORDER BY joined DESC LIMIT ?", (n,)).fetchall()
    return t("hist_title", lang, n=len(rows)) + "\n" + format_sessions(rows, lang)


def cmd_player(db, args, lang=None):
    if not args:
        return t("player_usage", lang)
    q = " ".join(args)
    rows = db.execute("SELECT game, username, steamid, userid, joined, left, note FROM sessions "
                      "WHERE username LIKE ? OR steamid=? OR userid=? ORDER BY joined DESC",
                      (f"%{q}%", q, q)).fetchall()
    if not rows:
        return t("player_unknown", lang, q=esc(q))
    total = sum(r[5] - r[4] for r in rows if r[5])
    names = sorted({r[1] for r in rows})
    sids = sorted({r[2] for r in rows if r[2]})
    uuids = sorted({r[3] for r in rows if r[3] and r[0] == "Minecraft"})
    games = collections.Counter(r[0] for r in rows)
    lines = [f"👤 <b>{esc(', '.join(names))}</b>"]
    lines += [f'🆔 SteamID: <a href="https://steamcommunity.com/profiles/{s}">{s}</a>' for s in sids]
    lines += [f"🆔 UUID: <code>{esc(u)}</code>" for u in uuids]
    lines += [t("p_total", lang, dur=fmt_duration(total, lang), n=len(rows)),
              "🎮 " + ", ".join(f"{esc(g)} ({c})" for g, c in games.most_common()),
              t("p_seen", lang, first=ts(rows[-1][4]), last=ts(rows[0][4])),
              "", format_sessions(rows[:10], lang)]
    return "\n".join(lines)


def cmd_status(instances, lang=None):
    tracked = [i.label for i in instances.values() if i.status == "ok"]
    online = sum(len(i.online) for i in instances.values())
    return "\n".join([t("h_title", lang), esc(host_report(lang)), "",
                      "🎮 " + t("tracking", lang, list=esc(", ".join(tracked) or t("nothing", lang))),
                      t("online_count", lang, n=online)])


class Commands:
    def __init__(self, db, instances):
        self.db, self.instances = db, instances
        self.offset = None
        self.restart = False
        self.amp = Amp()
        self.awaiting = {}  # chat -> {"kind": "console"/"password", ...}: nastepna wiadomosc to dane
        self.cache = {}  # chat -> listy (gracze, ustawienia), do ktorych odwoluja sie przyciski po numerze

    def poll(self, timeout):
        """Czeka na wiadomosci do `timeout` sekund (zastepuje sleep w glownej petli)."""
        if not TOKEN:
            time.sleep(timeout)
            return
        params = {"timeout": timeout, "allowed_updates": json.dumps(["message", "callback_query"])}
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
            try:
                if upd.get("callback_query"):
                    self.handle_callback(upd["callback_query"])
                elif msg and msg.get("text", "").startswith("/") and time.time() - msg.get("date", 0) < 120:
                    self.awaiting.pop(str(msg["chat"]["id"]), None)  # nowa komenda przerywa czekanie na dane
                    self.handle(msg)
                elif msg and msg.get("text") and str(msg["chat"]["id"]) in self.awaiting:
                    self.handle_text(msg)
            except Exception as e:
                log(f"Blad obslugi {upd.get('update_id')}: {e}")
                chat = (msg or upd.get("callback_query", {}).get("message", {})).get("chat", {}).get("id")
                if chat:
                    send(t("error", lang_for(chat)), chat)
        if self.restart:
            # potwierdzamy odebrane wiadomosci, zeby po restarcie /update nie wykonal sie drugi raz
            try:
                tg_api("getUpdates", {"offset": self.offset, "timeout": 0})
            except Exception:
                pass
            log("Restart po aktualizacji")
            sys.exit(0)  # systemd (Restart=always) uruchomi nowa wersje

    def reject(self, user, chat):
        key = f"stranger:{user.get('id')}"
        if not meta_get(self.db, key):  # informujemy admina tylko raz o kazdej osobie
            meta_set(self.db, key, int(time.time()))
            who = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x)
            if user.get("username"):
                who += f" @{user['username']}"
            send(t("stranger", who=esc(who), id=user.get("id")))
        send(t("private", norm_lang(user.get("language_code")) or "en"), chat)

    def handle(self, msg):
        chat = msg["chat"]["id"]
        user = msg.get("from", {})
        if user.get("id") not in ADMINS:
            self.reject(user, chat)
            return
        lang = lang_for(chat)
        parts = msg["text"].split()
        cmd, args = parts[0][1:].split("@")[0].lower(), parts[1:]
        cmd = ALIASES.get(cmd, cmd)
        if cmd == "online":
            send(t("online_title", lang) + "\n" + cmd_online(self.instances, lang), chat)
        elif cmd == "history":
            send(cmd_history(self.db, args, lang), chat)
        elif cmd == "player":
            send(cmd_player(self.db, args, lang), chat)
        elif cmd == "week":
            send(weekly_summary(self.db, lang=lang), chat)
        elif cmd == "status":
            send(cmd_status(self.instances, lang), chat)
        elif cmd in ("updates", "aktualizacje"):
            send(t("upd_checking_now", lang), chat)
            send(updates_report(self.amp, lang), chat)
        elif cmd in ("servers", "serwery", "server"):
            text, markup = self.servers_view(lang)
            send(text, chat, markup=markup)
        elif cmd == "lang":
            if args and norm_lang(args[0]):
                self.set_lang(chat, norm_lang(args[0]))
            else:
                send(t("lang_choose", lang), chat, markup=LANG_BUTTONS)
        elif cmd == "version":
            try:
                latest = esc(latest_release())
            except Exception as e:
                latest = t("check_failed", lang, err=getattr(e, "code", type(e).__name__))
            send(t("version", lang, v=VERSION, latest=latest), chat)
        elif cmd == "update":
            self.update(chat, lang, force="force" in args)
        elif cmd == "rollback":
            self.rollback(chat, lang)
        else:
            send(help_text(lang), chat, markup=NO_KEYBOARD)

    def handle_callback(self, cq):
        user = cq.get("from", {})
        chat = cq.get("message", {}).get("chat", {}).get("id")
        data = cq.get("data", "")
        try:
            tg_api("answerCallbackQuery", {"callback_query_id": cq["id"]})
        except Exception:
            pass
        if user.get("id") not in ADMINS or chat is None:
            return
        if data.startswith("lang:") and norm_lang(data[5:]):
            lang = norm_lang(data[5:])
            try:
                tg_api("editMessageText", {"chat_id": chat, "message_id": cq["message"]["message_id"],
                                           "text": t("lang_set", lang, name=LANGS[lang])})
            except Exception:
                pass
            self.set_lang(chat, lang, announce=False)
        elif data == "srv" or data.startswith(("srv:", "do:", "do!:", "pl:", "pa:", "pa!:", "con:", "con!:", "pw:",
                                               "pws:", "pw!:")):
            lang = lang_for(chat)
            text, markup = self.servers_callback(data, user, chat, lang)
            edit(chat, cq["message"]["message_id"], text, markup)

    # ---------- /servers ----------

    def players_on(self, name):
        inst = self.instances.get(name)
        return len(inst.online) if inst else 0

    def servers_view(self, lang):
        if not self.amp.configured:
            return t("amp_off", lang), None
        try:
            insts = self.amp.instances()
        except Exception as e:
            return t("amp_error", lang, err=esc(e)), {"inline_keyboard": [[self.btn("btn_refresh", "srv", lang)]]}
        if not insts:
            return t("srv_none", lang), None
        rows = []
        for i in insts:
            emoji, _ = amp_state(i, lang)
            n = self.players_on(i["name"])
            rows.append([{"text": f"{emoji} {i['friendly']}" + (f" 👥{n}" if n else ""),
                          "callback_data": f"srv:{i['name']}"[:64]}])
        rows.append([self.btn("btn_refresh", "srv", lang)])
        return t("srv_title", lang), {"inline_keyboard": rows}

    @staticmethod
    def btn(key, data, lang):
        return {"text": t(key, lang), "callback_data": data[:64]}

    def handle_text(self, msg):
        chat, user = msg["chat"]["id"], msg.get("from", {})
        if user.get("id") not in ADMINS:
            return
        lang = lang_for(chat)
        wait = self.awaiting.pop(str(chat))
        text = msg["text"].strip()
        if wait["kind"] == "console":
            self.awaiting[str(chat)] = {"kind": "console_ready", "name": wait["name"], "cmd": text}
            send(t("con_confirm", lang, name=esc(wait["name"]), cmd=esc(text)), chat,
                 markup={"inline_keyboard": [[self.btn("btn_yes", f"con!:{wait['name']}", lang),
                                              self.btn("btn_cancel", f"srv:{wait['name']}", lang)]]})
        elif wait["kind"] == "password":
            try:  # haslo nie zostaje w historii czatu
                tg_api("deleteMessage", {"chat_id": chat, "message_id": msg["message_id"]})
            except Exception:
                pass
            value = "" if text == "." else text
            self.awaiting[str(chat)] = {"kind": "password_ready", "name": wait["name"], "node": wait["node"],
                                        "setting": wait["setting"], "value": value}
            send(t("pw_confirm", lang, setting=esc(wait["setting"]), name=esc(wait["name"]), n=len(value)), chat,
                 markup={"inline_keyboard": [[self.btn("btn_yes", f"pw!:{wait['name']}", lang),
                                              self.btn("btn_cancel", f"srv:{wait['name']}", lang)]]})

    def audit(self, user, chat, action, name):
        who = user.get("first_name") or str(user.get("id"))
        log(f"AMP: {who} -> {action} {name}")
        if str(chat) != str(CHAT_ID):  # admin dostaje slad kazdej akcji wykonanej z innego czatu
            send(t("srv_audit", who=esc(who), action=esc(action), name=esc(name)))

    def players_view(self, name, chat, lang):
        back = [self.btn("btn_back", f"srv:{name}", lang)]
        try:
            players = self.amp.users(name)
        except Exception as e:
            return t("amp_error", lang, err=esc(e)), {"inline_keyboard": [back]}
        self.cache[(str(chat), "players", name)] = players
        if not players:
            return t("pl_title", lang, name=esc(name)) + "\n" + t("pl_none", lang), {"inline_keyboard": [back]}
        rows = [[{"text": f"👤 {p}", "callback_data": "noop"},
                 self.btn("act_kick", f"pa:kick:{i}:{name}", lang), self.btn("act_ban", f"pa:ban:{i}:{name}", lang)]
                for i, p in enumerate(players[:20])]
        return t("pl_title", lang, name=esc(name)), {"inline_keyboard": rows + [back]}

    def tools_callback(self, data, user, chat, lang):
        """Gracze (kick/ban), konsola i hasla; dane przycisku: <rodzaj>:...:<instancja>."""
        kind, _, rest = data.partition(":")
        if kind == "pl":
            return self.players_view(rest, chat, lang)
        if kind in ("pa", "pa!"):
            act, idx, name = rest.split(":", 2)
            players = self.cache.get((str(chat), "players", name)) or []
            if not idx.isdigit() or int(idx) >= len(players):
                return self.players_view(name, chat, lang)
            player = players[int(idx)]
            if kind == "pa":
                return (t("pl_confirm", lang, action=t("act_" + act, lang), player=esc(player), name=esc(name)),
                        {"inline_keyboard": [[self.btn("btn_yes", f"pa!:{act}:{idx}:{name}", lang),
                                              self.btn("btn_back", f"pl:{name}", lang)]]})
            try:
                out = self.amp.player_action(act, name, player)
            except Exception as e:
                return self.server_view(name, lang, note=t("amp_error", lang, err=esc(e)))
            self.audit(user, chat, f"{t('act_' + act)} {player}", name)
            return self.server_view(name, lang, note=self.console_note(out, lang))
        if kind == "con":
            self.awaiting[str(chat)] = {"kind": "console", "name": rest}
            return t("con_prompt", lang, name=esc(rest)), {"inline_keyboard": [[self.btn("btn_cancel",
                                                                                          f"srv:{rest}", lang)]]}
        if kind == "con!":
            wait = self.awaiting.pop(str(chat), None)
            if not wait or wait.get("kind") != "console_ready" or wait["name"] != rest:
                return self.server_view(rest, lang)
            try:
                out = self.amp.console(rest, wait["cmd"])
            except Exception as e:
                return self.server_view(rest, lang, note=t("amp_error", lang, err=esc(e)))
            self.audit(user, chat, f"⌨️ {wait['cmd']}", rest)
            return self.server_view(rest, lang, note=self.console_note(out, lang))
        if kind == "pw":
            try:
                settings = self.amp.password_settings(rest)
            except Exception as e:
                return self.server_view(rest, lang, note=t("amp_error", lang, err=esc(e)))
            self.cache[(str(chat), "pw", rest)] = settings
            back = [self.btn("btn_back", f"srv:{rest}", lang)]
            if not settings:
                return t("pw_none", lang), {"inline_keyboard": [back]}
            rows = [[{"text": label[:60], "callback_data": f"pws:{i}:{rest}"[:64]}] for i, (label, _) in
                    enumerate(settings[:10])]
            return t("pw_title", lang, name=esc(rest)), {"inline_keyboard": rows + [back]}
        if kind == "pws":
            idx, name = rest.split(":", 1)
            settings = self.cache.get((str(chat), "pw", name)) or []
            if not idx.isdigit() or int(idx) >= len(settings):
                return self.server_view(name, lang)
            label, node = settings[int(idx)]
            self.awaiting[str(chat)] = {"kind": "password", "name": name, "node": node, "setting": label}
            return t("pw_prompt", lang, setting=esc(label)), {"inline_keyboard": [[self.btn("btn_cancel",
                                                                                            f"srv:{name}", lang)]]}
        if kind == "pw!":
            wait = self.awaiting.pop(str(chat), None)
            if not wait or wait.get("kind") != "password_ready" or wait["name"] != rest:
                return self.server_view(rest, lang)
            try:
                self.amp.set_config(rest, wait["node"], wait["value"])
            except Exception as e:
                return self.server_view(rest, lang, note=t("amp_error", lang, err=esc(e)))
            self.audit(user, chat, f"🔑 {wait['setting']}", rest)
            return self.server_view(rest, lang, note=t("pw_done", lang))
        return self.servers_view(lang)

    @staticmethod
    def console_note(lines, lang):
        if not lines:
            return t("con_silent", lang)
        return t("con_sent", lang) + "\n<pre>" + esc("\n".join(lines))[-1500:] + "</pre>"

    def server_view(self, name, lang, note=""):
        try:
            inst = next((i for i in self.amp.instances() if i["name"] == name), None)
        except Exception as e:
            return t("amp_error", lang, err=esc(e)), {"inline_keyboard": [[self.btn("btn_back", "srv", lang)]]}
        if inst is None:
            return t("srv_none", lang), {"inline_keyboard": [[self.btn("btn_back", "srv", lang)]]}
        emoji, state = amp_state(inst, lang)
        lines = [f"{emoji} <b>{esc(inst['friendly'])}</b>", f"🎮 {esc(inst['module'] or '?')} · {esc(state)}",
                 t("srv_players", lang, n=self.players_on(name))]
        if note:
            lines += ["", note]
        up = inst["running"] and inst["state"] not in (0, -1, None)
        acts = ["stop", "restart"] if up else ["start"] + (["stop"] if inst["running"] else [])
        rows = [[self.btn("act_" + a, f"do:{a}:{name}", lang) for a in acts]]
        if inst["running"]:
            rows += [[self.btn("act_update", f"do:update:{name}", lang),
                      self.btn("act_backup", f"do:backup:{name}", lang)],
                     [self.btn("btn_players", f"pl:{name}", lang), self.btn("btn_console", f"con:{name}", lang),
                      self.btn("btn_password", f"pw:{name}", lang)]]
        rows += [[self.btn("btn_refresh", f"srv:{name}", lang), self.btn("btn_back", "srv", lang)]]
        return "\n".join(lines), {"inline_keyboard": rows}

    def servers_callback(self, data, user, chat, lang):
        if not self.amp.configured:
            return t("amp_off", lang), None
        if data == "srv":
            return self.servers_view(lang)
        kind, _, rest = data.partition(":")
        if kind == "srv":
            return self.server_view(rest, lang)
        if kind in ("pl", "pa", "pa!", "con", "con!", "pw", "pws", "pw!"):
            return self.tools_callback(data, user, chat, lang)
        act, _, name = rest.partition(":")
        if act not in Amp.ACTIONS:
            return self.servers_view(lang)
        label = t("act_" + act, lang)
        if kind == "do" and act != "start":  # wszystko poza startem wymaga potwierdzenia
            text = t("srv_confirm", lang, action=label, name=esc(name))
            n = self.players_on(name)
            if n:
                text += "\n" + t("srv_confirm_players", lang, n=n)
            return text, {"inline_keyboard": [[self.btn("btn_yes", f"do!:{act}:{name}", lang),
                                               self.btn("btn_back", f"srv:{name}", lang)]]}
        try:
            self.amp.action(act, name)
        except Exception as e:
            return self.server_view(name, lang, note=t("amp_error", lang, err=esc(e)))
        self.audit(user, chat, t("act_" + act), name)
        return self.server_view(name, lang, note=t("srv_done", lang, action=label, name=esc(name)))

    def set_lang(self, chat, lang, announce=True):
        meta_set(self.db, f"lang:{chat}", lang)
        CHAT_LANGS[str(chat)] = lang
        if announce:
            send(t("lang_set", lang, name=LANGS[lang]), chat)
        send(help_text(lang), chat, markup=NO_KEYBOARD)
        if chat in ADMINS:
            set_menu(chat)

    def update(self, chat, lang, force=False):
        send(t("upd_checking", lang), chat)
        tag = latest_release()
        if version_tuple(tag) <= version_tuple(VERSION) and not force:
            send(t("upd_latest", lang, v=VERSION), chat)
            return
        send(t("upd_downloading", lang, tag=esc(tag)), chat)
        ok, out = install_release(tag)
        if not ok:
            send(t("upd_failed", lang, v=VERSION) + f"\n<pre>{esc(out)}</pre>", chat)
            return
        meta_set(self.db, "updated_from", VERSION)
        send(t("upd_restart", lang, tag=esc(tag)), chat)
        self.restart = True

    def rollback(self, chat, lang):
        bak = BOT_PATH + ".bak"
        if not os.path.exists(bak):
            send(t("rb_none", lang), chat)
            return
        os.replace(bak, BOT_PATH)
        meta_set(self.db, "updated_from", VERSION)
        send(t("rb_restart", lang), chat)
        self.restart = True


# ---------- glowna petla ----------

def run():
    db = open_db()
    load_langs(db)
    instances = {}
    host = HostMonitor()
    commands = Commands(db, instances)
    amp_watch = AmpWatcher(commands.amp)
    updates = UpdateMonitor(commands.amp, db)
    startup = True
    last_scan = last_clean = last_host = 0
    log(f"Start {VERSION}, katalog instancji: {INSTANCES_DIR}, admini: {sorted(ADMINS) or 'brak'}")
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
                            send(t("new_instance", label=esc(inst.label)))
                elif inst.status == "brak":
                    inst.detect()
                if inst.status == "brak":
                    warn_once(db, inst)
                elif inst.status == "ok":
                    db.execute("DELETE FROM warned WHERE instance=?", (name,))
                    db.commit()
            if startup:
                tracked = ", ".join(esc(i.label) for i in instances.values() if i.status == "ok") or t("nothing")
                old = meta_get(db, "updated_from")
                head = t("updated", old=esc(old), v=VERSION) if old else t("startup", v=VERSION)
                if old:
                    db.execute("DELETE FROM meta WHERE key='updated_from'")
                    db.commit()
                send("\n".join([head, t("tracking", list=tracked), t("commands_hint")] + host.startup_notes()),
                     markup=NO_KEYBOARD)
                for admin in ADMINS:
                    set_menu(admin)
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
        amp_watch.poll()
        try:
            updates.poll()
        except Exception as e:
            log(f"Sprawdzanie aktualizacji: {e}")
        commands.poll(POLL_SECONDS)


# ---------- komendy reczne ----------

def print_rows(rows):
    for game, _inst, user, uid, sid, ip, joined, left, note in rows:
        dur = fmt_duration(left - joined) if left else (note_text(note) or "online?")
        ids = " ".join(x for x in (sid and f"SteamID:{sid}", uid and f"ID:{uid}", ip and f"IP:{ip}") if x)
        print(f"{ts(joined)}  {game:<10} {user:<20} {dur:<18} {ids}")


def main():
    args = sys.argv[1:]
    cols = "game, instance, username, userid, steamid, ip, joined, left, note"
    if not args:
        run()
    elif args[0] == "--test":
        send(t("test_msg"))
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
    elif args[0] == "--amp-test":
        sys.exit(amp_test())
    elif args[0] == "--selftest":
        selftest()
    elif args[0] == "--version":
        print(VERSION)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
