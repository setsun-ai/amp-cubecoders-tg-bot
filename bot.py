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

VERSION = "2.1.0"
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
# osobny bot dla znajomych (ten sam proces i baza); pusto = znajomi korzystaja z glownego bota
FRIENDS_TOKEN = os.environ.get("TG_FRIENDS_TOKEN", "")
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
# Dota 2 przez OpenDota (darmowe API bez klucza; ok. 2000 zapytan dziennie): co ile minut sprawdzac mecze
DOTA_CHECK_MINUTES = float(os.environ.get("DOTA_CHECK_MINUTES", "60"))  # 0 = wylaczone
DOTA_SLOW_HOURS = 24  # gracze bez publicznych meczow i ranga wszystkich: raz na dobe
OPENDOTA_API = "https://api.opendota.com/api"
STEAM64_BASE = 76561197960265728
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
    "fr_requested": ("⛔ To prywatny bot – właściciel dostał twoją prośbę o dostęp.",
                     "⛔ This is a private bot – the owner got your request for access.",
                     "⛔ Это приватный бот – владелец получил твой запрос на доступ.",
                     "⛔ Це приватний бот – власник отримав твій запит на доступ."),
    "btn_grant": ("➕ Daj dostęp", "➕ Give access", "➕ Дать доступ", "➕ Надати доступ"),
    "c_friends": ("Znajomi: dostęp do serwerów", "Friends: server access", "Друзья: доступ к серверам",
                  "Друзі: доступ до серверів"),
    "fr_title": ("👥 <b>Znajomi</b> – dotknij osoby, żeby zmienić jej serwery:",
                 "👥 <b>Friends</b> – tap a person to change their servers:",
                 "👥 <b>Друзья</b> – нажми на человека, чтобы изменить его серверы:",
                 "👥 <b>Друзі</b> – натисни на людину, щоб змінити її сервери:"),
    "fr_none": ("Nikt jeszcze nie ma dostępu. Znajomy pisze /start do bota znajomych (albo do tego, jeśli osobnego "
                "nie ma), a ty dostajesz prośbę z przyciskiem.",
                "Nobody has access yet. A friend sends /start to the friends' bot (or to this one, if there's no "
                "separate bot) and you get a request with a button.",
                "Пока ни у кого нет доступа. Друг пишет /start боту для друзей (или этому, если отдельного нет), "
                "а ты получаешь запрос с кнопкой.",
                "Поки ні в кого немає доступу. Друг пише /start боту для друзів (або цьому, якщо окремого немає), "
                "а ти отримуєш запит із кнопкою."),
    "fr_pick": ("👤 <b>{who}</b> – zaznacz serwery, którymi może zarządzać (start, stop, restart, aktualizacja, "
                "kopia, gracze, ustawienia; bez konsoli, haseł i modów). Powiadomień o graczach nie dostaje.",
                "👤 <b>{who}</b> – tick the servers they may manage (start, stop, restart, update, backup, players, "
                "settings; no console, passwords or mods). They get no player alerts.",
                "👤 <b>{who}</b> – отметь серверы, которыми он может управлять (запуск, стоп, перезапуск, обновление, "
                "бэкап, игроки, настройки; без консоли, паролей и модов). Уведомлений об игроках он не получает.",
                "👤 <b>{who}</b> – познач сервери, якими він може керувати (запуск, стоп, перезапуск, оновлення, "
                "бекап, гравці, налаштування; без консолі, паролів і модів). Сповіщень про гравців не отримує."),
    "btn_save": ("💾 Zapisz", "💾 Save", "💾 Сохранить", "💾 Зберегти"),
    "btn_remove": ("🗑 Usuń dostęp", "🗑 Remove access", "🗑 Убрать доступ", "🗑 Прибрати доступ"),
    "fr_saved": ("✅ {who}: {list}", "✅ {who}: {list}", "✅ {who}: {list}", "✅ {who}: {list}"),
    "fr_removed": ("🗑 {who} nie ma już dostępu.", "🗑 {who} no longer has access.", "🗑 У {who} больше нет доступа.",
                   "🗑 {who} більше не має доступу."),
    "fr_granted": ("✅ Masz dostęp do serwerów: {list}. Otwórz /servers.",
                   "✅ You have access to the servers: {list}. Open /servers.",
                   "✅ У тебя есть доступ к серверам: {list}. Открой /servers.",
                   "✅ У тебе є доступ до серверів: {list}. Відкрий /servers."),
    "fr_revoked": ("ℹ️ Twój dostęp do serwerów został usunięty.", "ℹ️ Your access to the servers was removed.",
                   "ℹ️ Твой доступ к серверам удалён.", "ℹ️ Твій доступ до серверів видалено."),
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
    "act_start": ("▶️ Uruchom serwer", "▶️ Start server", "▶️ Запустить сервер", "▶️ Запустити сервер"),
    "act_stop": ("⏹ Zatrzymaj serwer", "⏹ Stop server", "⏹ Остановить сервер", "⏹ Зупинити сервер"),
    "act_on": ("⏻ Włącz instancję", "⏻ Turn instance on", "⏻ Включить инстанс", "⏻ Увімкнути інстанс"),
    "act_off": ("⏻ Wyłącz instancję", "⏻ Turn instance off", "⏻ Выключить инстанс", "⏻ Вимкнути інстанс"),
    "op_started": ("⏳ {action} – postęp pokażę w wiadomości poniżej.",
                   "⏳ {action} – I'll show the progress in the message below.",
                   "⏳ {action} – прогресс покажу в сообщении ниже.",
                   "⏳ {action} – прогрес покажу в повідомленні нижче."),
    "op_busy": ("⏳ Już trwa: {action}. Poczekaj, aż się skończy (wiadomość poniżej).",
                "⏳ Already running: {action}. Wait until it ends (message below).",
                "⏳ Уже выполняется: {action}. Подожди, пока закончится (сообщение ниже).",
                "⏳ Вже виконується: {action}. Зачекай, доки закінчиться (повідомлення нижче)."),
    "op_done": ("✅ Gotowe ({dur}).", "✅ Done ({dur}).", "✅ Готово ({dur}).", "✅ Готово ({dur})."),
    "op_update_none": ("✅ Gotowe – AMP nie pokazał pobierania, gra była pewnie aktualna.",
                       "✅ Done – AMP showed no download, the game was probably up to date.",
                       "✅ Готово – AMP не показал загрузки, игра, наверное, была актуальной.",
                       "✅ Готово – AMP не показав завантаження, гра, мабуть, була актуальна."),
    "op_failed": ("❌ Nie udało się – AMP zgłasza błąd.", "❌ Failed – AMP reports an error.",
                  "❌ Не получилось – AMP сообщает об ошибке.", "❌ Не вдалося – AMP повідомляє про помилку."),
    "op_waiting": ("⚠️ AMP czeka na reakcję w panelu (np. komunikat do potwierdzenia) – otwórz panel AMP.",
                   "⚠️ AMP is waiting for input in its panel (e.g. a message to confirm) – open the AMP panel.",
                   "⚠️ AMP ждёт действия в панели (например, подтвердить сообщение) – открой панель AMP.",
                   "⚠️ AMP чекає на дію в панелі (наприклад, підтвердити повідомлення) – відкрий панель AMP."),
    "op_timeout": ("⚠️ Trwa to podejrzanie długo ({dur}) – sprawdź panel AMP.",
                   "⚠️ This takes suspiciously long ({dur}) – check the AMP panel.",
                   "⚠️ Это подозрительно долго ({dur}) – проверь панель AMP.",
                   "⚠️ Це підозріло довго ({dur}) – перевір панель AMP."),
    "op_console": ("Ostatnie linie konsoli:", "Last console lines:", "Последние строки консоли:",
                   "Останні рядки консолі:"),
    "st_waiting": ("czeka na reakcję w panelu", "waiting for input in the panel", "ждёт действия в панели",
                   "чекає на дію в панелі"),
    "lang_first": ("🌐 Wybierz język / Choose a language / Выбери язык / Обери мову",
                   "🌐 Wybierz język / Choose a language / Выбери язык / Обери мову",
                   "🌐 Wybierz język / Choose a language / Выбери язык / Обери мову",
                   "🌐 Wybierz język / Choose a language / Выбери язык / Обери мову"),
    "bio_main_short": ("Twój panel serwerów gier AMP: gracze, start i stop, aktualizacje, kopie, ustawienia, alerty.",
                       "Your AMP game server panel: players, start/stop, updates, backups, settings and alerts.",
                       "Твоя панель игровых серверов AMP: игроки, запуск и стоп, обновления, бэкапы, настройки.",
                       "Твоя панель ігрових серверів AMP: гравці, запуск і стоп, оновлення, бекапи, налаштування."),
    "bio_main": ("Prywatny bot do serwerów gier na AMP (CubeCoders). Pisze, kto wchodzi i wychodzi, pilnuje laptopa, "
                 "playit i aktualizacji systemu, a przyciskami włączasz, zatrzymujesz, aktualizujesz i backupujesz "
                 "serwery, zmieniasz ustawienia świata i banujesz graczy – z postępem każdej akcji. Odpowiada tylko "
                 "właścicielowi.",
                 "A private bot for AMP (CubeCoders) game servers. It tells you who joins and leaves, watches the "
                 "machine, playit and system updates, and lets you start, stop, update and back up servers, change "
                 "world settings and ban players with buttons – with the progress of every action. It answers its "
                 "owner only.",
                 "Приватный бот для игровых серверов на AMP (CubeCoders). Сообщает, кто заходит и выходит, следит "
                 "за ноутбуком, playit и обновлениями системы, а кнопками можно запускать, останавливать, обновлять "
                 "и бэкапить серверы, менять настройки мира и банить игроков – с прогрессом каждого действия. "
                 "Отвечает только владельцу.",
                 "Приватний бот для ігрових серверів на AMP (CubeCoders). Повідомляє, хто заходить і виходить, "
                 "стежить за ноутбуком, playit і оновленнями системи, а кнопками можна запускати, зупиняти, "
                 "оновлювати й бекапити сервери, змінювати налаштування світу й банити гравців – з прогресом кожної "
                 "дії. Відповідає лише власнику."),
    "bio_friends_short": ("Zarządzaj serwerami gier, do których masz dostęp: start, stop, aktualizacja, gracze.",
                          "Manage the game servers you were given: start, stop, update, players, settings.",
                          "Управляй игровыми серверами, к которым есть доступ: запуск, стоп, обновление, игроки.",
                          "Керуй ігровими серверами, до яких маєш доступ: запуск, стоп, оновлення, гравці."),
    "bio_friends": ("Bot do serwerów gier dla znajomych. Napisz /start, wybierz język i poproś o dostęp – właściciel "
                    "przydzieli ci serwery. Potem włączasz je i zatrzymujesz, aktualizujesz, robisz kopie, wyrzucasz, "
                    "banujesz i odbanowujesz graczy oraz zmieniasz ustawienia świata. Właściciel widzi każdą akcję.",
                    "A game server bot for friends. Send /start, pick your language and ask for access – the owner "
                    "assigns you servers. Then you start and stop them, update them, make backups, kick, ban and unban "
                    "players and change world settings. The owner sees every action.",
                    "Бот игровых серверов для друзей. Напиши /start, выбери язык и попроси доступ – владелец выдаст "
                    "тебе серверы. Потом ты их запускаешь и останавливаешь, обновляешь, делаешь бэкапы, кикаешь, "
                    "банишь и разбаниваешь игроков и меняешь настройки мира. Владелец видит каждое действие.",
                    "Бот ігрових серверів для друзів. Напиши /start, обери мову й попроси доступ – власник видасть "
                    "тобі сервери. Потім ти їх запускаєш і зупиняєш, оновлюєш, робиш бекапи, кікаєш, баниш і "
                    "розбанюєш гравців та змінюєш налаштування світу. Власник бачить кожну дію."),
    "act_restart": ("🔁 Restart", "🔁 Restart", "🔁 Перезапуск", "🔁 Перезапуск"),
    "act_update": ("⬆️ Aktualizacja gry", "⬆️ Game update", "⬆️ Обновление игры", "⬆️ Оновлення гри"),
    "act_backup": ("💾 Backup", "💾 Backup", "💾 Бэкап", "💾 Бекап"),
    "act_kick": ("👢 Kick", "👢 Kick", "👢 Кик", "👢 Кік"),
    "act_ban": ("🚫 Ban", "🚫 Ban", "🚫 Бан", "🚫 Бан"),
    "act_unban": ("♻️ Unban", "♻️ Unban", "♻️ Разбан", "♻️ Розбан"),
    "c_dota": ("Dota 2: mecze graczy", "Dota 2: players' matches", "Dota 2: матчи игроков", "Dota 2: матчі гравців"),
    "dota_guide": (
        "🎮 <b>Dota 2</b> – powiadomienia o meczach (OpenDota).\n\nDodaj gracza: <code>/dota add ID</code>\n"
        "ID to <b>Friend ID</b> z profilu w Docie (liczba przy nicku) albo numer z linku opendota.com/players/…, "
        "dotabuff.com/players/… lub steamcommunity.com/profiles/….\n\nGracz musi mieć w Docie włączone "
        "<i>Expose Public Match Data</i> (Ustawienia → Opcje → Społeczność). Bot sprawdzi to przy dodawaniu.",
        "🎮 <b>Dota 2</b> – match notifications (OpenDota).\n\nAdd a player: <code>/dota add ID</code>\n"
        "The ID is the <b>Friend ID</b> from the Dota profile (the number by the nick) or the number from an "
        "opendota.com/players/…, dotabuff.com/players/… or steamcommunity.com/profiles/… link.\n\nThe player "
        "needs <i>Expose Public Match Data</i> on in Dota (Settings → Options → Social). The bot checks it when "
        "adding.",
        "🎮 <b>Dota 2</b> – уведомления о матчах (OpenDota).\n\nДобавить игрока: <code>/dota add ID</code>\n"
        "ID – это <b>Friend ID</b> из профиля в Доте (число у ника) или номер из ссылки opendota.com/players/…, "
        "dotabuff.com/players/… или steamcommunity.com/profiles/….\n\nУ игрока в Доте должно быть включено "
        "<i>Expose Public Match Data</i> (Настройки → Опции → Сообщество). Бот проверит это при добавлении.",
        "🎮 <b>Dota 2</b> – сповіщення про матчі (OpenDota).\n\nДодати гравця: <code>/dota add ID</code>\n"
        "ID – це <b>Friend ID</b> з профілю в Доті (число біля ніку) або номер із посилання opendota.com/players/…, "
        "dotabuff.com/players/… чи steamcommunity.com/profiles/….\n\nУ гравця в Доті має бути ввімкнено "
        "<i>Expose Public Match Data</i> (Налаштування → Опції → Спільнота). Бот перевірить це під час додавання."),
    "dota_title": ("🎮 <b>Dota 2</b> – obserwowani gracze (🗑 usuwa):",
                   "🎮 <b>Dota 2</b> – watched players (🗑 removes):",
                   "🎮 <b>Dota 2</b> – отслеживаемые игроки (🗑 удаляет):",
                   "🎮 <b>Dota 2</b> – гравці, яких стежимо (🗑 видаляє):"),
    "dota_added": ("✅ Dodano: {name} ({rank}). Ostatni mecz: {last}.",
                   "✅ Added: {name} ({rank}). Last match: {last}.",
                   "✅ Добавлен: {name} ({rank}). Последний матч: {last}.",
                   "✅ Додано: {name} ({rank}). Останній матч: {last}."),
    "dota_private": ("⚠️ {name}: OpenDota nie widzi żadnych meczów – pewnie wyłączone <i>Expose Public Match Data</i> "
                     "(Dota: Ustawienia → Opcje → Społeczność). Po włączeniu mecze pojawią się same.",
                     "⚠️ {name}: OpenDota sees no matches – <i>Expose Public Match Data</i> is probably off "
                     "(Dota: Settings → Options → Social). Once it's on, matches show up by themselves.",
                     "⚠️ {name}: OpenDota не видит матчей – наверное, выключено <i>Expose Public Match Data</i> "
                     "(Дота: Настройки → Опции → Сообщество). После включения матчи появятся сами.",
                     "⚠️ {name}: OpenDota не бачить матчів – мабуть, вимкнено <i>Expose Public Match Data</i> "
                     "(Дота: Налаштування → Опції → Спільнота). Після ввімкнення матчі з'являться самі."),
    "dota_not_found": ("❌ OpenDota nie zna gracza {id} – sprawdź numer.", "❌ OpenDota doesn't know player {id} – "
                       "check the number.", "❌ OpenDota не знает игрока {id} – проверь номер.",
                       "❌ OpenDota не знає гравця {id} – перевір номер."),
    "dota_bad_id": ("❌ To nie wygląda na ID gracza – podaj Friend ID (liczbę) albo link do profilu.",
                    "❌ That doesn't look like a player ID – give the Friend ID (a number) or a profile link.",
                    "❌ Это не похоже на ID игрока – укажи Friend ID (число) или ссылку на профиль.",
                    "❌ Це не схоже на ID гравця – вкажи Friend ID (число) або посилання на профіль."),
    "dota_removed": ("🗑 Usunięto: {name}", "🗑 Removed: {name}", "🗑 Удалён: {name}", "🗑 Видалено: {name}"),
    "dota_error": ("❌ OpenDota nie odpowiada: {err}", "❌ OpenDota doesn't answer: {err}",
                   "❌ OpenDota не отвечает: {err}", "❌ OpenDota не відповідає: {err}"),
    "dota_win": ("✅ Wygrana", "✅ Win", "✅ Победа", "✅ Перемога"),
    "dota_loss": ("❌ Przegrana", "❌ Loss", "❌ Поражение", "❌ Поразка"),
    "dota_unranked": ("bez rangi", "unranked", "без ранга", "без рангу"),
    "dota_never": ("brak", "none", "нет", "немає"),
    "dota_ranked": ("rankingowy", "ranked", "рейтинговый", "рейтинговий"),
    "dota_rank_up": ("📈 <b>{name}</b>: {old} → {new}", "📈 <b>{name}</b>: {old} → {new}",
                     "📈 <b>{name}</b>: {old} → {new}", "📈 <b>{name}</b>: {old} → {new}"),
    "dota_rank_down": ("📉 <b>{name}</b>: {old} → {new}", "📉 <b>{name}</b>: {old} → {new}",
                       "📉 <b>{name}</b>: {old} → {new}", "📉 <b>{name}</b>: {old} → {new}"),
    "c_unban": ("Odbanuj gracza", "Unban a player", "Разбанить игрока", "Розбанити гравця"),
    "ub_prompt": ("♻️ <b>{name}</b>: napisz nick (albo SteamID) gracza do odbanowania.",
                  "♻️ <b>{name}</b>: type the nick (or SteamID) of the player to unban.",
                  "♻️ <b>{name}</b>: напиши ник (или SteamID) игрока для разбана.",
                  "♻️ <b>{name}</b>: напиши нік (або SteamID) гравця для розбану."),
    "ub_usage": ("Użycie: /unban NICK – potem wybierzesz serwer.", "Usage: /unban NICK – then pick the server.",
                 "Использование: /unban НИК – потом выберешь сервер.",
                 "Використання: /unban НІК – потім обереш сервер."),
    "ub_pick": ("♻️ Odbanować <b>{player}</b>? Wybierz serwer:", "♻️ Unban <b>{player}</b>? Pick the server:",
                "♻️ Разбанить <b>{player}</b>? Выбери сервер:", "♻️ Розбанити <b>{player}</b>? Обери сервер:"),
    "upd_held": ("⏸ Wstrzymane przez Ubuntu (phased / kept back) – apt upgrade ich jeszcze nie zainstaluje: {list}",
                 "⏸ Held back by Ubuntu (phased / kept back) – apt upgrade won't install them yet: {list}",
                 "⏸ Задержаны Ubuntu (phased / kept back) – apt upgrade их пока не установит: {list}",
                 "⏸ Затримані Ubuntu (phased / kept back) – apt upgrade їх поки не встановить: {list}"),
    "upd_stale": ("⚠️ Nie udało się odświeżyć listy pakietów – dane apt z {date}.",
                  "⚠️ Couldn't refresh the package lists – apt data from {date}.",
                  "⚠️ Не удалось обновить списки пакетов – данные apt от {date}.",
                  "⚠️ Не вдалося оновити списки пакетів – дані apt від {date}."),
    "btn_players": ("👥 Gracze", "👥 Players", "👥 Игроки", "👥 Гравці"),
    "btn_console": ("⌨️ Konsola", "⌨️ Console", "⌨️ Консоль", "⌨️ Консоль"),
    "btn_password": ("🔑 Hasło", "🔑 Password", "🔑 Пароль", "🔑 Пароль"),
    "btn_cancel": ("✖️ Anuluj", "✖️ Cancel", "✖️ Отмена", "✖️ Скасувати"),
    "btn_settings": ("⚙️ Ustawienia", "⚙️ Settings", "⚙️ Настройки", "⚙️ Налаштування"),
    "btn_search": ("🔎 Szukaj", "🔎 Search", "🔎 Поиск", "🔎 Пошук"),
    "btn_change": ("✏️ Zmień", "✏️ Change", "✏️ Изменить", "✏️ Змінити"),
    "set_on": ("✅ Włącz", "✅ Turn on", "✅ Включить", "✅ Увімкнути"),
    "set_off": ("⬜ Wyłącz", "⬜ Turn off", "⬜ Выключить", "⬜ Вимкнути"),
    "set_title": ("⚙️ <b>{name}</b> – ustawienia (jak w panelu AMP). Wybierz grupę albo wyszukaj:",
                 "⚙️ <b>{name}</b> – settings (as in the AMP panel). Pick a group or search:",
                 "⚙️ <b>{name}</b> – настройки (как в панели AMP). Выбери группу или найди:",
                 "⚙️ <b>{name}</b> – налаштування (як у панелі AMP). Обери групу або знайди:"),
    "set_none": ("Ta instancja nie podaje ustawień (czy działa w AMP?).",
                "This instance doesn't report its settings (is it running in AMP?).",
                "Этот инстанс не отдаёт настройки (он запущен в AMP?).",
                "Цей інстанс не віддає налаштування (він запущений в AMP?)."),
    "set_search_prompt": ("🔎 Napisz fragment nazwy ustawienia, np. difficulty, motd, seed, version:",
                         "🔎 Type part of a setting's name, e.g. difficulty, motd, seed, version:",
                         "🔎 Напиши часть названия настройки, например difficulty, motd, seed, version:",
                         "🔎 Напиши частину назви налаштування, наприклад difficulty, motd, seed, version:"),
    "set_found": ("🔎 „{q}”: znaleziono {n}", "🔎 \"{q}\": {n} found", "🔎 «{q}»: найдено {n}",
                  "🔎 «{q}»: знайдено {n}"),
    "set_now": ("Teraz: {value}", "Now: {value}", "Сейчас: {value}", "Зараз: {value}"),
    "set_prompt": ("✏️ Napisz nową wartość dla „{setting}” (teraz: {value}). Kropka = puste.",
                  "✏️ Type the new value for \"{setting}\" (now: {value}). A dot = empty.",
                  "✏️ Напиши новое значение для «{setting}» (сейчас: {value}). Точка = пусто.",
                  "✏️ Напиши нове значення для «{setting}» (зараз: {value}). Крапка = порожньо."),
    "set_done": ("✅ {setting}: {old} → {new}\nZmiany zwykle działają po restarcie serwera.",
                "✅ {setting}: {old} → {new}\nChanges usually take effect after a server restart.",
                "✅ {setting}: {old} → {new}\nИзменения обычно вступают в силу после перезапуска сервера.",
                "✅ {setting}: {old} → {new}\nЗміни зазвичай діють після перезапуску сервера."),
    "set_update_hint": ("⬆️ To zmienia wersję gry – kliknij potem „Aktualizacja gry”, żeby ją pobrać.",
                       "⬆️ This changes the game version – then tap \"Game update\" to download it.",
                       "⬆️ Это меняет версию игры – потом нажми «Обновление игры», чтобы её скачать.",
                       "⬆️ Це змінює версію гри – потім натисни «Оновлення гри», щоб її завантажити."),
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


BOT = {"token": ""}  # bot, ktory wlasnie odpowiada ("" = glowny); patrz via()


class via:
    """`with via(FRIENDS_TOKEN):` - odpowiedzi (send/edit) ida przez bota znajomych."""

    def __init__(self, token):
        self.token, self.saved = token, None

    def __enter__(self):
        self.saved, BOT["token"] = BOT["token"], self.token

    def __exit__(self, *exc):
        BOT["token"] = self.saved


def tg_api(method, params=None, timeout=10, token=None):
    data = urllib.parse.urlencode(params or {}).encode()
    url = f"https://api.telegram.org/bot{token or BOT['token'] or TOKEN}/{method}"
    with urllib.request.urlopen(url, data, timeout=timeout) as r:
        return json.loads(r.read().decode())


def send(text, chat_id=None, markup=None):
    if chat_id is None:  # powiadomienia do admina zawsze glownym botem
        with via(""):
            return send(text, CHAT_ID, markup)
    if not TOKEN or not chat_id:
        log("[brak TG_TOKEN/TG_CHAT_ID] " + text)
        return
    if len(text) > 4000:
        text = text[:3990] + "\n…"
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": "true"}
    if markup:
        params["reply_markup"] = json.dumps(markup)
    token = BOT["token"] or TOKEN  # bot, ktory wlasnie odpowiada (do admina: glowny, patrz wyzej)
    for attempt in range(3):
        try:
            return (tg_api("sendMessage", params, token=token).get("result") or {}).get("message_id")
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
        CREATE TABLE IF NOT EXISTS friends(user_id INTEGER PRIMARY KEY, name TEXT, instances TEXT, added INTEGER);
        CREATE TABLE IF NOT EXISTS dota(account_id INTEGER PRIMARY KEY, name TEXT, last_match INTEGER, added INTEGER);
    """)
    for column in ("rank_tier INTEGER", "rank_at INTEGER", "matches_at INTEGER", "public INTEGER"):
        try:  # baza z 1.9.0: dopisujemy kolumny
            db.execute(f"ALTER TABLE dota ADD COLUMN {column}")
        except sqlite3.OperationalError:
            pass
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


def friend_get(db, user_id):
    """Znajomy z dostepem do wybranych instancji AMP: {"name", "instances"} albo None."""
    row = db.execute("SELECT name, instances FROM friends WHERE user_id=?", (user_id,)).fetchone()
    return {"name": row[0], "instances": json.loads(row[1] or "[]")} if row else None


def friends_all(db):
    return [(uid, name, json.loads(insts or "[]"))
            for uid, name, insts in db.execute("SELECT user_id, name, instances FROM friends ORDER BY name")]


def friend_set(db, user_id, name, instances):
    db.execute("INSERT OR REPLACE INTO friends(user_id, name, instances, added) VALUES (?,?,?,?)",
               (user_id, name, json.dumps(sorted(instances)), int(time.time())))
    db.commit()


def friend_remove(db, user_id):
    db.execute("DELETE FROM friends WHERE user_id=?", (user_id,))
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

    def settings(self, name):
        """
        Ustawienia instancji jak w panelu AMP: [(grupa, [{"name", "node", "desc", "type", "enum", "value"}])].
        Bez hasel (osobny przycisk), ukrytych, tylko do odczytu i ustawien samego AMP (Core.*: porty, loginy).
        """
        inst = self.find(name)
        spec = self.instance_call(inst["id"], "Core/GetSettingsSpec") or {}
        groups = []
        for group, items in (spec.items() if isinstance(spec, dict) else []):
            out = []
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                node, label = str(item.get("Node", "")), str(item.get("Name") or item.get("Node", ""))
                kind = str(item.get("InputType") or "text").lower()
                text = f"{node} {label}".lower()
                if (not node or item.get("Hidden") or item.get("ReadOnly") or kind == "password"
                        or "password" in text or node.startswith("Core.")):
                    continue
                enum = item.get("EnumValues")
                out.append({"name": label, "node": node, "desc": str(item.get("Description") or ""), "type": kind,
                            "enum": [(str(k), str(v)) for k, v in enum.items()] if isinstance(enum, dict) else [],
                            "value": item.get("CurrentValue")})
            if out:
                groups.append((str(group).replace(":", " › "), out))
        return groups

    def get_config(self, name, node):
        inst = self.find(name)
        r = self.instance_call(inst["id"], "Core/GetConfig", node=node)
        return r.get("CurrentValue") if isinstance(r, dict) else r

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
                # po nazwie i opisie, nie po Id: panel potrafi pokazac jedno uruchamianie jako dwa zadania
                # (albo zmienic mu Id) - wtedy szly dwie identyczne wiadomosci
                found.setdefault((label, f"{task['name']}|{task['desc']}"), task)
        return found

    # on/off = sama instancja AMP (offline <-> gotowa); start/stop = serwer gry w wlaczonej instancji
    ACTIONS = ("on", "start", "stop", "off", "restart", "update", "backup")
    # komendy konsoli dla kick/ban/unban; {player} = nick; klucz = fragment nazwy modulu AMP
    GAME_COMMANDS = {"default": {"kick": "kick {player}", "ban": "ban {player}", "unban": "unban {player}"},
                     "minecraft": {"kick": "kick {player}", "ban": "ban {player}", "unban": "pardon {player}"}}

    def action(self, act, name):
        """
        on: wlacza instancje (gra zostaje zatrzymana, mozna aktualizowac); off: wylacza cala instancje;
        start: serwer gry (z wylaczonej instancji: najpierw ja wlacza, gre uruchamia AmpWatcher, gdy instancja
        wstanie); stop: tylko serwer gry; restart: gra; update: aktualizacja gry (SteamCMD itp.); backup: kopia.
        Postep sledzi AmpWatcher.track.
        """
        inst = self.find(name)
        if act == "off":
            return self.call("ADSModule/StopInstance", InstanceName=name)
        if act in ("on", "start") and not inst["running"]:
            return self.call("ADSModule/StartInstance", InstanceName=name)
        if act == "on":
            return None  # juz wlaczona
        if not inst["running"]:
            raise AmpError(t("srv_need_running"))
        if act == "start":
            return self.instance_call(inst["id"], "Core/Start")
        if act == "stop":
            return self.instance_call(inst["id"], "Core/Stop")
        if act == "restart":
            return self.instance_call(inst["id"], "Core/Restart")
        if act == "update":
            return self.instance_call(inst["id"], "Core/UpdateApplication")
        title = datetime.now().strftime("Telegram %Y-%m-%d %H:%M")
        return self.instance_call(inst["id"], "LocalFileBackupPlugin/TakeBackup", Title=title,
                                  Description="amp-tg-bot", Sticky=False)

    def console_tail(self, name, n=6):
        """Ostatnie linie konsoli (do wiadomosci o bledzie)."""
        try:
            inst = self.find(name)
            updates = self.instance_call(inst["id"], "Core/GetUpdates") if inst["running"] else {}
        except Exception:
            return []
        entries = updates.get("ConsoleEntries") if isinstance(updates, dict) else None
        return [str(e.get("Contents", "")) for e in entries or [] if isinstance(e, dict)][-n:]

    def player_action(self, act, name, player):
        module = (self.find(name)["module"] or "").lower()
        commands = next((c for key, c in self.GAME_COMMANDS.items() if key != "default" and key in module),
                        self.GAME_COMMANDS["default"])
        return self.console(name, commands[act].format(player=player))


# AppState z AMP -> (emoji, klucz tekstu)
AMP_STATES = {0: ("🔴", "st_stopped"), 5: ("🟡", "st_starting"), 7: ("🟡", "st_starting"), 10: ("🟡", "st_starting"),
              20: ("🟢", "st_ready"), 30: ("🟡", "st_starting"), 40: ("🟠", "st_stopping"), 45: ("🟠", "st_stopping"),
              50: ("💤", "st_sleeping"), 70: ("⬆️", "st_updating"), 75: ("⬆️", "st_updating"),
              80: ("⚠️", "st_waiting"), 100: ("❌", "st_failed")}


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
        self.last_tasks = self.last_states = self.last_ops = 0
        self.ops = {}  # instancja -> akcja z bota, ktorej postep pokazujemy w jednej wiadomosci

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

    # ---------- akcje z bota: jedna wiadomosc z postepem az do konca ----------

    OP_TIMEOUT = {"update": 3600, "backup": 3600}  # sekundy; reszta 15 min
    OP_EDIT_SECONDS = 5

    def busy(self, name):
        op = self.ops.get(name)
        return op["act"] if op else None

    def track(self, name, act, chat, lang):
        """Po akcji z bota: wiadomosc na czacie, ktory ja zlecil (tym samym botem), edytowana az do wyniku."""
        try:
            friendly = self.amp.find(name)["friendly"]
        except Exception:
            friendly = name
        op = {"name": name, "act": act, "chat": chat, "lang": lang, "token": BOT["token"], "friendly": friendly,
              "started": time.time(), "seen": set(), "kicked": act != "start", "tasks_seen": False,
              "text": None, "edited": 0}
        op["text"] = self.op_text(op, None, None, None)
        op["msg"] = send(op["text"], chat)
        self.ops[name] = op

    def op_text(self, op, inst, pct, result, extra=""):
        lang = op["lang"]
        head = {"done": "✅", "failed": "❌", "waiting": "⚠️", "timeout": "⚠️"}.get(result, "⏳")
        lines = [f"{head} <b>{esc(op['friendly'])}</b>: {t('act_' + op['act'], lang)}"]
        dur = fmt_duration(time.time() - op["started"], lang)
        if inst is not None:
            emoji, state = amp_state(inst, lang)
            lines.append(f"{emoji} {esc(state)} · {dur}")
        if pct is not None and not result:
            lines.append(progress_bar(pct))
        if result == "done":
            lines.append(t("op_update_none", lang) if op["act"] == "update" and not op["seen"] & {70, 75}
                         and not op["tasks_seen"] else t("op_done", lang, dur=dur))
        elif result in ("failed", "waiting", "timeout"):
            lines.append(t("op_" + result, lang, dur=dur))
        if extra:
            lines.append(extra)
        return "\n".join(lines)

    def op_result(self, op, inst, state, busy, elapsed):
        act = op["act"]
        if state == 100:
            return "failed"
        if state == 80:
            return "waiting"
        running = inst["running"]
        if act == "on" and running and state in (0, 20, 50):
            return "done"
        if act == "start" and state == 20:
            return "done"
        if act == "stop" and running and state == 0:
            return "done"
        if act == "off" and not running:
            return "done"
        if act == "restart" and state == 20 and (op["seen"] - {20} or elapsed > 20):
            return "done"
        if act == "update" and state in (0, 20) and not busy and elapsed > 15 and (
                op["seen"] & {70, 75} or op["tasks_seen"] or elapsed > 90):
            return "done"
        if act == "backup" and not busy and (op["tasks_seen"] and elapsed > 5 or elapsed > 30):
            return "done"
        if elapsed > self.OP_TIMEOUT.get(act, 900):
            return "timeout"
        return None

    def check_ops(self):
        insts = {i["name"]: i for i in self.amp.instances()}
        tasks = self.amp.tasks(list(insts.values())) if any(op["act"] in ("update", "backup")
                                                            for op in self.ops.values()) else {}
        now = time.time()
        for name, op in list(self.ops.items()):
            inst = insts.get(name)
            if inst is None:
                self.ops.pop(name)
                continue
            state = inst["state"] if inst["running"] else -1
            op["seen"].add(state)
            if not op["kicked"] and inst["running"] and state == 0:  # start z wylaczonej: instancja wstala
                try:
                    self.amp.instance_call(inst["id"], "Core/Start")
                    op["kicked"] = True
                except Exception as e:
                    log(f"AMP start {name}: {e}")
            mine = [task for (label, _), task in tasks.items()
                    if label == inst["friendly"] or name in f"{task['name']} {task['desc']}"]
            op["tasks_seen"] = op["tasks_seen"] or bool(mine)
            pct = next((task["pct"] for task in mine if task["pct"] is not None), None)
            result = self.op_result(op, inst, state, bool(mine), now - op["started"])
            extra = ""
            if result in ("failed", "waiting", "timeout"):
                tail = self.amp.console_tail(name)
                if tail:
                    extra = t("op_console", op["lang"]) + "\n<pre>" + esc("\n".join(tail))[-1200:] + "</pre>"
            text = self.op_text(op, inst, pct, result, extra)
            if text != op["text"] and (result or now - op["edited"] >= self.OP_EDIT_SECONDS):
                with via(op["token"]):
                    if op["msg"]:
                        edit(op["chat"], op["msg"], text)
                    else:
                        op["msg"] = send(text, op["chat"])
                op.update(text=text, edited=now)
            if result:
                self.ops.pop(name)

    def quiet(self, label, task=None):
        """Czy instancja ma akcje z bota - wtedy jej zadania i stany pokazuje wiadomosc tej akcji."""
        for op in self.ops.values():
            if label == op["friendly"] or (task and op["name"] in f"{task['name']} {task['desc']}"):
                return True
        return False

    def check_tasks(self):
        current = {k: v for k, v in self.amp.tasks(self.instances).items()
                   if not AMP_TASK_IGNORE.search(v["name"]) and not self.quiet(k[0], v)}
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
                if (before is not None and before != states[inst["name"]] and self.stable(inst)
                        and inst["name"] not in self.ops):
                    emoji, state = amp_state(inst)
                    send(t("state_change", emoji=emoji, inst=esc(inst["friendly"]), state=esc(state)))
        self.states = states

    @staticmethod
    def stable(inst):
        # stany przejsciowe (uruchamia sie, zatrzymuje sie) widac w zadaniach; tu tylko wynik
        return not inst["running"] or inst["state"] in (0, 20, 50, 80, 100)

    def poll(self):
        now = time.time()
        if self.ops and now - self.last_ops >= self.OP_EDIT_SECONDS:
            self.last_ops = now
            try:
                self.check_ops()
            except Exception as e:
                log(f"AMP akcje: {e}")
        if not (AMP_NOTIFY and self.amp.configured):
            return
        try:
            if now - self.last_states >= AMP_STATE_SECONDS:
                self.last_states = now
                self.check_states()
            if now - self.last_tasks >= AMP_TASK_SECONDS:
                self.last_tasks = now
                self.check_tasks()
        except Exception as e:  # AMP chwilowo niedostepny: sprobujemy przy nastepnym obrocie
            log(f"AMP watcher: {e}")


APT_DIR = os.path.join(os.path.dirname(DB_PATH), "apt")
APT_STALE = {}  # data systemowej listy pakietow, gdy wlasnej nie udalo sie odswiezyc (do raportu)


def apt_options():
    """Wlasne listy pakietow bota: odswiezane bez roota, system ich nie widzi i nie blokuje."""
    return ["-o", f"Dir::State::Lists={APT_DIR}/lists", "-o", f"Dir::Cache={APT_DIR}/cache",
            "-o", "Debug::NoLocking=1"]


def apt_run(args, timeout=120):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env={**os.environ, "LANG": "C"})


def apt_refresh():
    """apt-get update do katalogu bota (bot nie jest rootem). True, gdy listy sa swieze."""
    try:
        os.makedirs(f"{APT_DIR}/lists/partial", exist_ok=True)
        os.makedirs(f"{APT_DIR}/cache/archives/partial", exist_ok=True)
        return apt_run(["apt-get", "update", "-qq", *apt_options()], timeout=600).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def system_lists_date():
    stamps = [os.path.getmtime(p) for p in glob.glob("/var/lib/apt/lists/*Release")]
    return ts(max(stamps)) if stamps else "?"


def parse_held(text):
    """`apt-get -s upgrade`: pakiety "kept back" i odlozone przez phased updates."""
    held, take = set(), False
    for line in text.splitlines():
        if line.startswith("The following"):
            take = "kept back" in line or "phasing" in line
        elif take and line.startswith("  "):
            held.update(line.split())
        else:
            take = False
    return held


def apt_upgradable(refresh=True):
    """
    Pakiety do aktualizacji: [{"name", "new", "old", "security", "held"}]. Najpierw swieze listy (inaczej
    stary cache mowi "aktualny", a Webmin po swoim apt update pokazuje cos innego), potem `held` = te,
    ktorych Ubuntu jeszcze nie da zainstalowac (phased updates / kept back).
    """
    fresh = apt_refresh() if refresh else False
    opts = apt_options() if fresh else []
    APT_STALE.clear()
    if refresh and not fresh:
        APT_STALE["date"] = system_lists_date()
    try:
        pkgs = parse_apt(apt_run(["apt", "list", "--upgradable", *opts]).stdout)
        held = parse_held(apt_run(["apt-get", "-s", "upgrade", *opts]).stdout)
    except (OSError, subprocess.SubprocessError):
        return None
    for p in pkgs:
        p["held"] = p["name"] in held
    return pkgs


def parse_apt(text):
    pkgs = []
    for line in text.splitlines():
        m = re.match(r"^([^/\s]+)/(\S+)\s+(\S+)\s+\S+\s+\[upgradable from:\s*([^\]]+)\]", line)
        if m:
            pkgs.append({"name": m.group(1), "new": m.group(3), "old": m.group(4).strip(),
                         "security": "-security" in m.group(2), "held": False})
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
    if APT_STALE.get("date"):
        lines.append(t("upd_stale", lang, date=esc(APT_STALE["date"])))
    ready = [p for p in pkgs or [] if not p.get("held")]
    held = [p for p in pkgs or [] if p.get("held")]
    if pkgs is None:
        lines.append(t("upd_apt_unknown", lang))
    elif ready:
        security = [p for p in ready if p["security"]]
        lines.append(t("upd_apt", lang, n=len(ready), sec=len(security)))
        important = [p for p in ready if p["security"] or p["name"].startswith(IMPORTANT_PACKAGES)]
        for p in important[:15]:
            mark = " 🛡" if p["security"] else ""
            lines.append(f"  • <code>{esc(p['name'])}</code> {esc(p['old'])} → {esc(p['new'])}{mark}")
        if len(ready) > len(important[:15]):
            lines.append(t("upd_more", lang, n=len(ready) - len(important[:15])))
    else:
        lines.append(t("upd_apt_none", lang))
    if held:
        lines.append(t("upd_held", lang, list=esc(", ".join(p["name"] for p in held[:10]))
                       + (f" (+{len(held) - 10})" if len(held) > 10 else "")))
    if reboot is not None:
        lines.append(t("upd_reboot", lang, pkgs=esc(", ".join(reboot[:8]) or "?")))
    if amp_available:
        lines.append(t("upd_amp", lang, version=esc(amp_version or "?")))
    if ready:
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
        keys = sorted(f"{p['name']}={p['new']}" for p in pkgs if not p.get("held")
                      and (p["security"] or p["name"].startswith(IMPORTANT_PACKAGES)))
        signature = json.dumps([keys, reboot, amp_info[0] and amp_info[1]])
        if signature == meta_get(self.db, "updates_seen"):
            return
        meta_set(self.db, "updates_seen", signature)
        if keys or reboot is not None or amp_info[0]:
            send(updates_report(self.amp, pkgs=pkgs, reboot=reboot, amp_info=amp_info))


# ---------- Dota 2 (OpenDota) ----------

DOTA_MEDALS = {1: "Herald", 2: "Guardian", 3: "Crusader", 4: "Archon", 5: "Legend", 6: "Ancient", 7: "Divine",
               8: "Immortal"}
DOTA_MODES = {1: "All Pick", 2: "Captains Mode", 3: "Random Draft", 4: "Single Draft", 5: "All Random",
              16: "Captains Draft", 18: "Ability Draft", 19: "Event", 20: "All Random Deathmatch", 21: "1v1 Mid",
              22: "All Pick", 23: "Turbo"}


def opendota(path, post=False):
    req = urllib.request.Request(f"{OPENDOTA_API}/{path}", data=b"" if post else None,
                                 headers={"User-Agent": f"amp-tg-bot/{VERSION}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def dota_account_id(text):
    """Friend ID (Steam32), SteamID64 albo link opendota/dotabuff/steamcommunity -> Steam32 albo None."""
    text = (text or "").strip()
    m = re.search(r"(?:players|profiles)/(\d+)", text) or re.fullmatch(r"(\d+)", text)
    if not m:
        return None
    n = int(m.group(1))
    if n > STEAM64_BASE:
        n -= STEAM64_BASE
    return n if 0 < n < 2 ** 32 else None


def dota_rank(profile, lang=None):
    tier = (profile or {}).get("rank_tier")
    if not tier:
        return t("dota_unranked", lang)
    medal = DOTA_MEDALS.get(tier // 10, "?")
    if tier // 10 == 8:
        place = profile.get("leaderboard_rank")
        return f"{medal} #{place}" if place else medal
    return f"{medal} {tier % 10}" if tier % 10 else medal


def dota_match_text(name, m, heroes, rank="", lang=None):
    radiant = m.get("player_slot", 0) < 128
    won = bool(m.get("radiant_win")) == radiant
    mode = DOTA_MODES.get(m.get("game_mode"), f"mode {m.get('game_mode')}")
    if m.get("lobby_type") == 7:
        mode += f" ({t('dota_ranked', lang)})"
    lines = [f"🎮 <b>{esc(name)}</b>: {t('dota_win' if won else 'dota_loss', lang)} – "
             f"{esc(heroes.get(str(m.get('hero_id')), '?'))}",
             f"KDA {m.get('kills', 0)}/{m.get('deaths', 0)}/{m.get('assists', 0)} · GPM {m.get('gold_per_min', 0)}"
             f" · XPM {m.get('xp_per_min', 0)} · {fmt_duration(m.get('duration', 0), lang)} · {esc(mode)}"
             + (f" · {esc(rank)}" if rank else ""),
             f'<a href="https://www.opendota.com/matches/{m.get("match_id")}">OpenDota</a>']
    return "\n".join(lines)


class DotaWatcher:
    """Co DOTA_CHECK_MINUTES: nowe mecze obserwowanych graczy -> jedna wiadomosc na mecz (na czat admina)."""

    def __init__(self, db):
        self.db = db
        self.last = 0
        self.heroes, self.heroes_at = {}, 0

    def hero_names(self):
        if not self.heroes or time.time() - self.heroes_at > 86400:
            try:
                data = opendota("constants/heroes")
                self.heroes = {str(k): v.get("localized_name", "?") for k, v in data.items()}
                self.heroes_at = time.time()
            except Exception as e:
                log(f"OpenDota heroes: {e}")
        return self.heroes

    def poll(self):
        """
        Mecze co DOTA_CHECK_MINUTES (gracze bez publicznych meczow raz na dobe); ranga wszystkich raz na dobe -
        z karty profilu, wiec dziala tez przy ukrytych meczach. Ok. 6 graczy = ok. 160 zapytan dziennie.
        """
        now = time.time()
        if not DOTA_CHECK_MINUTES or now - self.last < DOTA_CHECK_MINUTES * 60:
            return
        self.last = now
        rows = self.db.execute("SELECT account_id, name, last_match, rank_tier, rank_at, matches_at, public "
                               "FROM dota").fetchall()
        for account, name, last, tier, rank_at, matches_at, public in rows:
            if now - (rank_at or 0) >= DOTA_SLOW_HOURS * 3600:
                self.check_rank(account, name, tier)
            if public == 0 and now - (matches_at or 0) < DOTA_SLOW_HOURS * 3600:
                continue
            try:
                matches = opendota(f"players/{account}/recentMatches") or []
            except Exception as e:
                log(f"OpenDota {account}: {e}")
                continue
            self.db.execute("UPDATE dota SET matches_at=?, public=? WHERE account_id=?",
                            (int(now), 1 if matches else 0, account))
            self.db.commit()
            new = sorted((m for m in matches if m.get("match_id", 0) > (last or 0)), key=lambda m: m["match_id"])
            if not new:
                continue
            row = self.db.execute("SELECT rank_tier FROM dota WHERE account_id=?", (account,)).fetchone()
            rank = dota_rank({"rank_tier": row[0]}) if row and row[0] else ""
            heroes = self.hero_names()
            for m in new[-5:]:  # po dlugiej przerwie bota - tylko kilka ostatnich
                send(dota_match_text(name, m, heroes, rank))
            self.db.execute("UPDATE dota SET last_match=? WHERE account_id=?", (new[-1]["match_id"], account))
            self.db.commit()

    def check_rank(self, account, name, old):
        """Ranga z OpenDota; prosba o odswiezenie profilu, zeby jutro byla swieza."""
        try:
            profile = opendota(f"players/{account}")
            opendota(f"players/{account}/refresh", post=True)
        except Exception as e:
            log(f"OpenDota rank {account}: {e}")
            return
        tier = (profile or {}).get("rank_tier")
        self.db.execute("UPDATE dota SET rank_tier=?, rank_at=? WHERE account_id=?", (tier, int(time.time()), account))
        self.db.commit()
        if old and tier and tier != old:
            key = "dota_rank_up" if tier > old else "dota_rank_down"
            send(t(key, name=esc(name), old=esc(dota_rank({"rank_tier": old})), new=esc(dota_rank(profile))))


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
COMMANDS = [("online", ""), ("servers", ""), ("friends", ""), ("updates", ""), ("status", ""), ("history", " [N]"),
            ("player", " NICK"), ("unban", " NICK"), ("week", ""), ("dota", " [add ID]"), ("lang", ""),
            ("version", ""), ("update", ""), ("rollback", ""), ("help", "")]
# znajomi: tylko przydzielone serwery
FRIEND_COMMANDS = [("servers", ""), ("unban", " NICK"), ("lang", ""), ("help", "")]
# przyciski edytora ustawien: st (grupy), stc (grupa, strona), sti (ustawienie), ste (strona listy wyboru),
# stv (wybrana wartosc), stw (wpisz wartosc), sts (szukaj)
SETTINGS_KINDS = ("st:", "stc:", "sti:", "ste:", "stv:", "stw:", "sts:")
SETTINGS_PAGE = 10
# stare polskie nazwy z 1.0.0 dalej dzialaja
ALIASES = {"historia": "history", "gracz": "player", "tydzien": "week", "tydzień": "week", "wersja": "version",
           "pomoc": "help", "start": "help", "jezyk": "lang", "język": "lang", "language": "lang",
           "znajomi": "friends", "odbanuj": "unban", "pardon": "unban"}
# komendy sa tylko pod przyciskiem "Menu"; to chowa klawiature z przyciskami z wersji 1.0.0-1.1.0
NO_KEYBOARD = {"remove_keyboard": True}
LANG_BUTTONS = {"inline_keyboard": [[{"text": LANGS[c], "callback_data": f"lang:{c}"} for c in ("pl", "en")],
                                    [{"text": LANGS[c], "callback_data": f"lang:{c}"} for c in ("ru", "uk")]]}


def help_text(lang, commands=None):
    lines = [t("help_title", lang, v=VERSION)]
    lines += [f"/{cmd}{esc(args)} – {t('c_' + cmd, lang)}" for cmd, args in commands or COMMANDS]
    return "\n".join(lines)


def set_menu(chat_id, commands=None):
    """Menu komend (przycisk 'Menu' w Telegramie) na czacie admina albo znajomego, w jego jezyku."""
    lang = lang_for(chat_id)
    commands = json.dumps([{"command": c, "description": t("c_" + c, lang)} for c, _ in commands or COMMANDS])
    try:
        tg_api("setMyCommands", {"commands": commands, "scope": json.dumps({"type": "chat", "chat_id": chat_id})})
    except Exception as e:
        log(f"setMyCommands: {getattr(e, 'code', type(e).__name__)}")


def set_descriptions(token, kind):
    """Opis bota ("Co potrafi ten bot?") i krotkie bio w 4 jezykach; tylko gdy teksty sie zmienily."""
    texts = {lang: (t(f"bio_{kind}", lang), t(f"bio_{kind}_short", lang)) for lang in LANG_ORDER}
    signature = json.dumps(texts, sort_keys=True)
    if not token or DESCRIPTIONS.get(kind) == signature:
        return
    try:
        for lang, (full, short) in list(texts.items()) + [("", texts["en"])]:
            extra = {"language_code": lang} if lang else {}
            tg_api("setMyDescription", {"description": full[:512], **extra}, token=token)
            tg_api("setMyShortDescription", {"short_description": short[:120], **extra}, token=token)
        DESCRIPTIONS[kind] = signature
    except Exception as e:
        log(f"setMyDescription: {getattr(e, 'code', type(e).__name__)}")


DESCRIPTIONS = {}  # rodzaj bota -> ostatnio ustawione teksty


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
        help_text(lang, FRIEND_COMMANDS)
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
        self.offsets = {}  # token bota ("" = glowny) -> offset getUpdates
        self.friend_bot = False  # czy wlasnie obslugujemy bota znajomych
        self.restart = False
        self.amp = Amp()
        self.awaiting = {}  # chat -> {"kind": "console"/"password", ...}: nastepna wiadomosc to dane
        self.cache = {}  # chat -> listy (gracze, ustawienia), do ktorych odwoluja sie przyciski po numerze
        self.scope = None  # None = admin; zbior instancji = znajomy, ktorego wiadomosc wlasnie obslugujemy
        self.watcher = None  # AmpWatcher: postep akcji z bota (ustawiany w run())
        self.chat_key = ""  # czat, ktorego edytor ustawien wlasnie obslugujemy (klucz w self.cache)

    def poll(self, timeout, token=""):
        """Czeka na wiadomosci do `timeout` sekund (zastepuje sleep w glownej petli); token = bot znajomych."""
        if not (token or TOKEN):
            time.sleep(timeout)
            return
        params = {"timeout": timeout, "allowed_updates": json.dumps(["message", "callback_query"])}
        if self.offsets.get(token) is not None:
            params["offset"] = self.offsets[token]
        try:
            res = tg_api("getUpdates", params, timeout=timeout + 10, token=token or TOKEN)
        except Exception as e:
            log(f"getUpdates{' (znajomi)' if token else ''}: {getattr(e, 'code', type(e).__name__)}")
            time.sleep(timeout)
            return
        with via(token):
            self.friend_bot = bool(token)
            try:
                self.handle_updates(res.get("result", []), token)
            finally:
                self.friend_bot = False
        if self.restart:
            # potwierdzamy odebrane wiadomosci, zeby po restarcie /update nie wykonal sie drugi raz
            try:
                tg_api("getUpdates", {"offset": self.offsets.get(""), "timeout": 0}, token=TOKEN)
            except Exception:
                pass
            log("Restart po aktualizacji")
            sys.exit(0)  # systemd (Restart=always) uruchomi nowa wersje

    def handle_updates(self, updates, token):
        for upd in updates:
            self.offsets[token] = upd["update_id"] + 1
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

    @staticmethod
    def who(user):
        who = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x) or str(user.get("id"))
        return who + (f" @{user['username']}" if user.get("username") else "")

    def reject(self, user, chat):
        # dostep daje bot znajomych (albo glowny, gdy osobnego nie ma); glowny jest wtedy tylko admina
        grants = self.friend_bot or not FRIENDS_TOKEN
        key = f"{'stranger' if grants else 'outsider'}:{user.get('id')}"
        lang = CHAT_LANGS.get(str(chat)) or norm_lang(user.get("language_code")) or "en"
        if meta_get(self.db, key):
            send(t("private", lang), chat)
            return
        # admin dostaje wiadomosc tylko raz o kazdej osobie; z przyciskiem, gdy to prosba o dostep
        meta_set(self.db, key, int(time.time()))
        if not grants:
            send(t("stranger", who=esc(self.who(user)), id=user.get("id")))
            send(t("private", lang), chat)
            return
        meta_set(self.db, f"who:{user.get('id')}", json.dumps({"name": self.who(user), "lang": lang}))
        send(t("stranger", who=esc(self.who(user)), id=user.get("id")),
             markup={"inline_keyboard": [[self.btn("btn_grant", f"fr:{user.get('id')}", None)]]})
        send(t("fr_requested", lang), chat)

    def friend_scope(self, user):
        """None dla admina, zbior instancji dla znajomego, False dla obcego."""
        if user.get("id") in ADMINS:
            return None
        if FRIENDS_TOKEN and not self.friend_bot:  # glowny bot jest tylko admina
            return False
        friend = friend_get(self.db, user.get("id"))
        return set(friend["instances"]) if friend else False

    def handle(self, msg):
        chat = msg["chat"]["id"]
        user = msg.get("from", {})
        self.scope = self.friend_scope(user)
        if self.scope is False:
            if self.friend_bot and str(chat) not in CHAT_LANGS:  # nowa osoba: najpierw jezyk, potem prosba
                send(t("lang_first"), chat, markup=LANG_BUTTONS)
                return
            self.reject(user, chat)
            return
        lang = lang_for(chat)
        parts = msg["text"].split()
        cmd, args = parts[0][1:].split("@")[0].lower(), parts[1:]
        cmd = ALIASES.get(cmd, cmd)
        if self.scope is not None:  # znajomy: tylko swoje serwery i jezyk
            if cmd in ("servers", "serwery", "server"):
                text, markup = self.servers_view(lang)
                send(text, chat, markup=markup)
            elif cmd == "unban":
                self.unban_command(chat, args, lang)
            elif cmd == "lang":
                self.lang_command(chat, args, lang)
            else:
                send(help_text(lang, FRIEND_COMMANDS), chat, markup=NO_KEYBOARD)
            return
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
        elif cmd == "friends":
            text, markup = self.friends_view(lang)
            send(text, chat, markup=markup)
        elif cmd == "unban":
            self.unban_command(chat, args, lang)
        elif cmd == "dota":
            self.dota_command(chat, args, lang)
        elif cmd == "lang":
            self.lang_command(chat, args, lang)
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

    def unban_command(self, chat, args, lang):
        """/unban NICK: wybor serwera jest zarazem potwierdzeniem."""
        if not args:
            send(t("ub_usage", lang), chat)
            return
        if not self.amp.configured:
            send(t("amp_off", lang), chat)
            return
        player = " ".join(args)
        try:
            insts = [i for i in self.amp.instances() if self.scope is None or i["name"] in self.scope]
        except Exception as e:
            send(t("amp_error", lang, err=esc(e)), chat)
            return
        if not insts:
            send(t("srv_none", lang), chat)
            return
        self.awaiting[str(chat)] = {"kind": "unban_ready", "player": player, "name": None}
        rows = [[{"text": f"♻️ {i['friendly']}", "callback_data": f"ub!:{i['name']}"[:64]}] for i in insts]
        send(t("ub_pick", lang, player=esc(player)), chat,
             markup={"inline_keyboard": rows + [[self.btn("btn_cancel", "srv", lang)]]})

    def dota_view(self, lang):
        rows = [[{"text": f"🗑 {name}"[:60], "callback_data": f"dr:{acc}"}]
                for acc, name in self.db.execute("SELECT account_id, name FROM dota ORDER BY name")]
        if not rows:
            return t("dota_guide", lang), None
        return t("dota_title", lang) + "\n\n" + t("dota_guide", lang), {"inline_keyboard": rows}

    def dota_command(self, chat, args, lang):
        """/dota - lista i instrukcja; /dota add ID - sprawdza gracza w OpenDota i zaczyna go obserwowac."""
        if args and args[0].lower() in ("add", "dodaj"):
            args = args[1:]
        if not args:
            text, markup = self.dota_view(lang)
            send(text, chat, markup=markup)
            return
        account = dota_account_id(args[0])
        if account is None:
            send(t("dota_bad_id", lang), chat)
            return
        try:
            profile = opendota(f"players/{account}")
            matches = opendota(f"players/{account}/recentMatches") or []
        except Exception as e:
            send(t("dota_error", lang, err=esc(getattr(e, "code", e))), chat)
            return
        name = ((profile or {}).get("profile") or {}).get("personaname")
        if not name:
            send(t("dota_not_found", lang, id=account), chat)
            return
        last = max((m.get("match_id", 0) for m in matches), default=0)  # stare mecze nie wpadna jako nowe
        now = int(time.time())
        self.db.execute("INSERT OR REPLACE INTO dota(account_id, name, last_match, added, rank_tier, rank_at, "
                        "matches_at, public) VALUES (?,?,?,?,?,?,?,?)",
                        (account, name, last, now, profile.get("rank_tier"), now, now, 1 if matches else 0))
        self.db.commit()
        when = ts(max(m.get("start_time", 0) for m in matches)) if matches else t("dota_never", lang)
        send(t("dota_added", lang, name=esc(name), rank=esc(dota_rank(profile, lang)), last=when), chat)
        if not matches:
            send(t("dota_private", lang, name=esc(name)), chat)

    def lang_command(self, chat, args, lang):
        if args and norm_lang(args[0]):
            self.set_lang(chat, norm_lang(args[0]))
        else:
            send(t("lang_choose", lang), chat, markup=LANG_BUTTONS)

    def handle_callback(self, cq):
        user = cq.get("from", {})
        chat = cq.get("message", {}).get("chat", {}).get("id")
        data = cq.get("data", "")
        try:
            tg_api("answerCallbackQuery", {"callback_query_id": cq["id"]})
        except Exception:
            pass
        self.scope = self.friend_scope(user)
        if self.scope is False and self.friend_bot and chat is not None and norm_lang(data[5:]) \
                and data.startswith("lang:"):  # nowa osoba wybrala jezyk: zapamietujemy i wysylamy prosbe
            lang = norm_lang(data[5:])
            meta_set(self.db, f"lang:{chat}", lang)
            CHAT_LANGS[str(chat)] = lang
            edit(chat, cq["message"]["message_id"], t("lang_set", lang, name=LANGS[lang]))
            self.reject(user, chat)
            return
        if self.scope is False or chat is None:
            return
        if self.scope is not None and not self.friend_may(data):
            return
        if data.startswith("dr:") and self.scope is None:
            acc = data[3:]
            row = self.db.execute("SELECT name FROM dota WHERE account_id=?", (acc,)).fetchone()
            self.db.execute("DELETE FROM dota WHERE account_id=?", (acc,))
            self.db.commit()
            lang = lang_for(chat)
            text, markup = self.dota_view(lang)
            edit(chat, cq["message"]["message_id"],
                 (t("dota_removed", lang, name=esc(row[0])) + "\n\n" if row else "") + text, markup)
            return
        if data == "frl" or data.startswith(("fr:", "frt:", "frs:", "frd:")):
            text, markup = self.friends_callback(data, lang_for(chat))
            edit(chat, cq["message"]["message_id"], text, markup)
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
                                               "pws:", "pw!:", "ub:", "ub!:") + SETTINGS_KINDS):
            lang = lang_for(chat)
            text, markup = self.servers_callback(data, user, chat, lang)
            edit(chat, cq["message"]["message_id"], text, markup)

    def friend_may(self, data):
        """Przyciski znajomego: jezyk, lista serwerow i jego instancje - bez hasel i bez /friends."""
        if data.startswith("lang:") or data == "srv":
            return True
        kind, _, rest = data.partition(":")
        if kind not in ("srv", "do", "do!", "pl", "pa", "pa!", "ub", "ub!") + tuple(
                k[:-1] for k in SETTINGS_KINDS):
            return False
        return rest.rsplit(":", 1)[-1] in self.scope

    # ---------- /friends ----------

    def friends_view(self, lang):
        rows = [[{"text": f"👤 {name} – {', '.join(insts) or '—'}"[:60], "callback_data": f"fr:{uid}"}]
                for uid, name, insts in friends_all(self.db)]
        known = {r[0]["callback_data"] for r in rows}
        for key, value in self.db.execute("SELECT key, value FROM meta WHERE key LIKE 'who:%' ORDER BY key"):
            if f"fr:{key[4:]}" not in known:  # prosili o dostep, jeszcze go nie maja
                rows.append([{"text": f"❓ {json.loads(value)['name']}"[:60], "callback_data": f"fr:{key[4:]}"}])
        return (t("fr_title", lang) if rows else t("fr_none", lang)), ({"inline_keyboard": rows} if rows else None)

    def friend_name(self, uid):
        friend = friend_get(self.db, uid)
        if friend:
            return friend["name"]
        who = meta_get(self.db, f"who:{uid}")
        return json.loads(who)["name"] if who else str(uid)

    def friend_picker(self, uid, lang):
        pick = self.cache[("fr", uid)]
        rows = [[{"text": ("☑️ " if i["name"] in pick["sel"] else "⬜ ") + i["friendly"],
                  "callback_data": f"frt:{uid}:{n}"}] for n, i in enumerate(pick["insts"])]
        last = [self.btn("btn_save", f"frs:{uid}", lang)]
        if friend_get(self.db, uid):
            last.append(self.btn("btn_remove", f"frd:{uid}", lang))
        rows += [last, [self.btn("btn_back", "frl", lang)]]
        return t("fr_pick", lang, who=esc(self.friend_name(uid))), {"inline_keyboard": rows}

    def friends_callback(self, data, lang):
        if data == "frl":
            return self.friends_view(lang)
        kind, _, rest = data.partition(":")
        uid = int(rest.split(":")[0]) if rest.split(":")[0].isdigit() else 0
        if not uid:
            return self.friends_view(lang)
        if kind == "fr" or ("fr", uid) not in self.cache:
            if not self.amp.configured:
                return t("amp_off", lang), None
            try:
                insts = self.amp.instances()
            except Exception as e:
                return t("amp_error", lang, err=esc(e)), {"inline_keyboard": [[self.btn("btn_back", "frl", lang)]]}
            current = (friend_get(self.db, uid) or {}).get("instances", [])
            self.cache[("fr", uid)] = {"insts": insts, "sel": set(current)}
            if kind == "fr":
                return self.friend_picker(uid, lang)
        pick = self.cache[("fr", uid)]
        if kind == "frt":
            n = rest.split(":")[1]
            if n.isdigit() and int(n) < len(pick["insts"]):
                pick["sel"] ^= {pick["insts"][int(n)]["name"]}
            return self.friend_picker(uid, lang)
        name = self.friend_name(uid)
        if kind == "frs" and pick["sel"]:
            friend_set(self.db, uid, name, pick["sel"])
            labels = ", ".join(i["friendly"] for i in pick["insts"] if i["name"] in pick["sel"])
            if not meta_get(self.db, f"lang:{uid}"):  # znajomy dostaje wiadomosci w swoim jezyku z Telegrama
                who = json.loads(meta_get(self.db, f"who:{uid}") or "{}")
                meta_set(self.db, f"lang:{uid}", who.get("lang", "en"))
                CHAT_LANGS[str(uid)] = norm_lang(who.get("lang")) or "en"
            with via(FRIENDS_TOKEN):  # znajomy pisze z botem znajomych (jesli jest)
                send(t("fr_granted", lang_for(uid), list=esc(labels)), uid)
                set_menu(uid, FRIEND_COMMANDS)
            self.cache.pop(("fr", uid), None)
            text, markup = self.friends_view(lang)
            return t("fr_saved", lang, who=esc(name), list=esc(labels)) + "\n\n" + text, markup
        if kind in ("frs", "frd"):  # zapis bez zadnego serwera = usuniecie dostepu
            had = friend_get(self.db, uid)
            friend_remove(self.db, uid)
            self.cache.pop(("fr", uid), None)
            if had:
                with via(FRIENDS_TOKEN):
                    send(t("fr_revoked", lang_for(uid)), uid)
                    try:
                        tg_api("deleteMyCommands", {"scope": json.dumps({"type": "chat", "chat_id": uid})})
                    except Exception:
                        pass
            text, markup = self.friends_view(lang)
            return t("fr_removed", lang, who=esc(name)) + "\n\n" + text, markup
        return self.friends_view(lang)

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
        if self.scope is not None:  # znajomy widzi tylko przydzielone instancje
            insts = [i for i in insts if i["name"] in self.scope]
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
        self.scope = self.friend_scope(user)
        wait = self.awaiting.get(str(chat), {})
        if self.scope is False or (self.scope is not None and (
                wait.get("kind") not in ("setting", "setting_search", "unban")
                or wait.get("name") not in self.scope)):
            return
        lang = lang_for(chat)
        wait = self.awaiting.pop(str(chat))
        text = msg["text"].strip()
        if wait["kind"] == "console":
            self.awaiting[str(chat)] = {"kind": "console_ready", "name": wait["name"], "cmd": text}
            send(t("con_confirm", lang, name=esc(wait["name"]), cmd=esc(text)), chat,
                 markup={"inline_keyboard": [[self.btn("btn_yes", f"con!:{wait['name']}", lang),
                                              self.btn("btn_cancel", f"srv:{wait['name']}", lang)]]})
        elif wait["kind"] == "unban":
            self.awaiting[str(chat)] = {"kind": "unban_ready", "name": wait["name"], "player": text}
            send(t("pl_confirm", lang, action=t("act_unban", lang), player=esc(text), name=esc(wait["name"])), chat,
                 markup={"inline_keyboard": [[self.btn("btn_yes", f"ub!:{wait['name']}", lang),
                                              self.btn("btn_cancel", f"pl:{wait['name']}", lang)]]})
        elif wait["kind"] == "setting":
            text, markup = self.apply_setting(user, chat, wait["name"], wait["ci"], wait["si"],
                                              "" if text == "." else text, lang)
            send(text, chat, markup=markup)
        elif wait["kind"] == "setting_search":
            text, markup = self.search_settings(chat, wait["name"], text, lang)
            send(text, chat, markup=markup)
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
        who = self.who(user)
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
        unban = [self.btn("act_unban", f"ub:{name}", lang)]
        if not players:
            return t("pl_title", lang, name=esc(name)) + "\n" + t("pl_none", lang), {"inline_keyboard": [unban, back]}
        rows = [[{"text": f"👤 {p}", "callback_data": "noop"},
                 self.btn("act_kick", f"pa:kick:{i}:{name}", lang), self.btn("act_ban", f"pa:ban:{i}:{name}", lang)]
                for i, p in enumerate(players[:20])]
        return t("pl_title", lang, name=esc(name)), {"inline_keyboard": rows + [unban, back]}

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
        if kind == "ub":
            self.awaiting[str(chat)] = {"kind": "unban", "name": rest}
            return t("ub_prompt", lang, name=esc(rest)), {"inline_keyboard": [[self.btn("btn_cancel",
                                                                                         f"pl:{rest}", lang)]]}
        if kind == "ub!":
            wait = self.awaiting.pop(str(chat), None)
            if not wait or wait.get("kind") != "unban_ready" or wait.get("name") not in (None, rest):
                return self.server_view(rest, lang)
            try:
                out = self.amp.player_action("unban", rest, wait["player"])
            except Exception as e:
                return self.server_view(rest, lang, note=t("amp_error", lang, err=esc(e)))
            self.audit(user, chat, f"{t('act_unban')} {wait['player']}", rest)
            return self.server_view(rest, lang, note=self.console_note(out, lang))
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

    # ---------- ustawienia instancji ----------

    @staticmethod
    def setting_value(s, lang):
        value = s["value"]
        if s["type"] == "checkbox" or isinstance(value, bool):
            return "✅" if str(value).lower() == "true" else "⬜"
        label = dict(s["enum"]).get(str(value))
        text = label or ("—" if value in (None, "") else str(value))
        return text if len(text) <= 40 else text[:39] + "…"

    def settings_home(self, name, lang):
        groups = self.cache[(self.chat_key, "set", name)]
        rows = [[{"text": f"{group} ({len(items)})"[:60], "callback_data": f"stc:{i}:0:{name}"[:64]}]
                for i, (group, items) in enumerate(groups)]
        rows += [[self.btn("btn_search", f"sts:{name}", lang), self.btn("btn_back", f"srv:{name}", lang)]]
        return t("set_title", lang, name=esc(name)), {"inline_keyboard": rows}

    def group_view(self, name, gi, page, lang, title=None):
        group, items = self.cache[(self.chat_key, "set", name)][gi]
        pages = max(1, (len(items) - 1) // SETTINGS_PAGE + 1)
        page = min(max(page, 0), pages - 1)
        first = page * SETTINGS_PAGE
        rows = [[{"text": f"{s['name']}: {self.setting_value(s, lang)}"[:60],
                  "callback_data": f"sti:{gi}:{si}:{name}"[:64]}]
                for si, s in enumerate(items[first:first + SETTINGS_PAGE], first)]
        if pages > 1:
            nav = [{"text": "◀", "callback_data": f"stc:{gi}:{page - 1}:{name}"[:64]}] if page else []
            nav.append({"text": f"{page + 1}/{pages}", "callback_data": f"stc:{gi}:{page}:{name}"[:64]})
            if page < pages - 1:
                nav.append({"text": "▶", "callback_data": f"stc:{gi}:{page + 1}:{name}"[:64]})
            rows.append(nav)
        rows.append([self.btn("btn_back", f"st:{name}", lang)])
        return title or f"⚙️ <b>{esc(name)}</b> › {esc(group)}", {"inline_keyboard": rows}

    def setting_view(self, name, gi, si, lang, note="", page=0):
        s = self.cache[(self.chat_key, "set", name)][gi][1][si]
        if s["value"] is None:
            try:
                s["value"] = self.amp.get_config(name, s["node"])
            except Exception:
                pass
        lines = [f"⚙️ <b>{esc(s['name'])}</b>"]
        if s["desc"]:
            lines.append(f"<i>{esc(s['desc'][:300])}</i>")
        lines.append(t("set_now", lang, value=esc(self.setting_value(s, lang))))
        if note:
            lines += ["", note]
        rows = []
        if s["type"] == "checkbox":
            rows.append([self.btn("set_on", f"stv:{gi}:{si}:1:{name}", lang),
                         self.btn("set_off", f"stv:{gi}:{si}:0:{name}", lang)])
        elif s["enum"]:
            per = 12
            first = page * per
            for n, (key, label) in enumerate(s["enum"][first:first + per], first):
                mark = "• " if key == str(s["value"]) else ""
                rows.append([{"text": (mark + label)[:60], "callback_data": f"stv:{gi}:{si}:{n}:{name}"[:64]}])
            pages = (len(s["enum"]) - 1) // per + 1
            if pages > 1:
                nav = [{"text": "◀", "callback_data": f"ste:{gi}:{si}:{page - 1}:{name}"[:64]}] if page else []
                nav.append({"text": f"{page + 1}/{pages}", "callback_data": f"ste:{gi}:{si}:{page}:{name}"[:64]})
                if page < pages - 1:
                    nav.append({"text": "▶", "callback_data": f"ste:{gi}:{si}:{page + 1}:{name}"[:64]})
                rows.append(nav)
        else:
            rows.append([self.btn("btn_change", f"stw:{gi}:{si}:{name}", lang)])
        rows.append([self.btn("btn_back", f"stc:{gi}:{si // SETTINGS_PAGE}:{name}", lang)])
        return "\n".join(lines), {"inline_keyboard": rows}

    def apply_setting(self, user, chat, name, gi, si, value, lang):
        self.chat_key = str(chat)
        s = self.cache[(self.chat_key, "set", name)][gi][1][si]
        old = self.setting_value(s, lang)
        try:
            self.amp.set_config(name, s["node"], value)
        except Exception as e:
            return self.setting_view(name, gi, si, lang, note=t("amp_error", lang, err=esc(e)))
        s["value"] = value
        new = self.setting_value(s, lang)
        self.audit(user, chat, f"⚙️ {s['name']}: {old} → {new}", name)
        note = t("set_done", lang, setting=esc(s["name"]), old=esc(old), new=esc(new))
        if re.search(r"version|wersj|server ?type|release|branch|loader|forge|fabric",
                     f"{s['node']} {s['name']}", re.I):
            note += "\n" + t("set_update_hint", lang)
        return self.setting_view(name, gi, si, lang, note=note)

    def search_settings(self, chat, name, query, lang):
        self.chat_key = str(chat)
        key = (self.chat_key, "set", name)
        if key not in self.cache:
            self.cache[key] = self.amp.settings(name)
        groups = [g for g in self.cache[key] if not g[0].startswith("🔎")]
        q = query.lower()
        found = [s for _, items in groups for s in items if q in f"{s['name']} {s['node']} {s['desc']}".lower()]
        self.cache[key] = groups + [(f"🔎 {query}", found)]
        if not found:
            return t("set_found", lang, q=esc(query), n=0), {"inline_keyboard": [
                [self.btn("btn_search", f"sts:{name}", lang), self.btn("btn_back", f"st:{name}", lang)]]}
        return self.group_view(name, len(groups), 0, lang, title=t("set_found", lang, q=esc(query), n=len(found)))

    def settings_callback(self, data, user, chat, lang):
        self.chat_key = str(chat)
        kind, _, rest = data.partition(":")
        parts = rest.split(":")
        name, nums = parts[-1], [int(x) for x in parts[:-1] if x.isdigit()]
        key = (self.chat_key, "set", name)
        if kind == "st" or key not in self.cache:
            try:
                self.cache[key] = self.amp.settings(name)
            except Exception as e:
                return self.server_view(name, lang, note=t("amp_error", lang, err=esc(e)))
            if not self.cache[key]:
                return self.server_view(name, lang, note=t("set_none", lang))
            if kind == "st":
                return self.settings_home(name, lang)
        groups = self.cache[key]
        if kind == "sts":
            self.awaiting[self.chat_key] = {"kind": "setting_search", "name": name}
            return t("set_search_prompt", lang), {"inline_keyboard": [[self.btn("btn_cancel", f"st:{name}", lang)]]}
        if not nums or nums[0] >= len(groups):
            return self.settings_home(name, lang)
        gi = nums[0]
        if kind == "stc":
            return self.group_view(name, gi, nums[1] if len(nums) > 1 else 0, lang)
        if len(nums) < 2 or nums[1] >= len(groups[gi][1]):
            return self.group_view(name, gi, 0, lang)
        si = nums[1]
        s = groups[gi][1][si]
        if kind == "ste":
            return self.setting_view(name, gi, si, lang, page=nums[2] if len(nums) > 2 else 0)
        if kind == "stw":
            self.awaiting[self.chat_key] = {"kind": "setting", "name": name, "ci": gi, "si": si}
            return (t("set_prompt", lang, setting=esc(s["name"]), value=esc(self.setting_value(s, lang))),
                    {"inline_keyboard": [[self.btn("btn_cancel", f"sti:{gi}:{si}:{name}", lang)]]})
        if kind == "stv" and len(nums) > 2:
            if s["type"] == "checkbox":
                return self.apply_setting(user, chat, name, gi, si, "true" if nums[2] else "false", lang)
            if nums[2] < len(s["enum"]):
                return self.apply_setting(user, chat, name, gi, si, s["enum"][nums[2]][0], lang)
        return self.setting_view(name, gi, si, lang)

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
        state = inst["state"] if inst["running"] else -1

        def row(*acts):
            return [self.btn("act_" + a, f"do:{a}:{name}", lang) for a in acts]

        if not inst["running"]:  # instancja wylaczona: wlacz sama instancje albo od razu serwer
            rows = [row("start"), row("on")]
        elif state == 20:  # serwer gry dziala
            rows = [row("stop", "restart"), row("update", "backup"),
                    [self.btn("btn_players", f"pl:{name}", lang)]
                    + ([self.btn("btn_console", f"con:{name}", lang)] if self.scope is None else [])]
        elif state in (0, 100, 80):  # instancja wlaczona, gra zatrzymana (albo blad) - tu sie aktualizuje
            rows = [row("start"), row("update", "backup"), [self.btn("btn_players", f"pl:{name}", lang)]]
        else:  # uruchamia sie, zatrzymuje, aktualizuje - tylko podglad
            rows = [row("stop")]
        if inst["running"]:
            rows += [[self.btn("btn_settings", f"st:{name}", lang)]
                     + ([self.btn("btn_password", f"pw:{name}", lang)] if self.scope is None else []),
                     row("off")]
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
        if kind in ("pl", "pa", "pa!", "con", "con!", "pw", "pws", "pw!", "ub", "ub!"):
            return self.tools_callback(data, user, chat, lang)
        if kind + ":" in SETTINGS_KINDS:
            return self.settings_callback(data, user, chat, lang)
        act, _, name = rest.partition(":")
        if act not in Amp.ACTIONS:
            return self.servers_view(lang)
        label = t("act_" + act, lang)
        running = self.watcher.busy(name) if self.watcher else None
        if running:  # drugie klikniecie w trakcie - nic nie wysylamy drugi raz
            return self.server_view(name, lang, note=t("op_busy", lang, action=t("act_" + running, lang)))
        if kind == "do" and act not in ("on", "start", "backup"):  # reszta wymaga potwierdzenia
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
        if self.watcher:
            self.watcher.track(name, act, chat, lang)
            return self.server_view(name, lang, note=t("op_started", lang, action=label))
        return self.server_view(name, lang, note=t("srv_done", lang, action=label, name=esc(name)))

    def set_lang(self, chat, lang, announce=True):
        meta_set(self.db, f"lang:{chat}", lang)
        CHAT_LANGS[str(chat)] = lang
        if announce:
            send(t("lang_set", lang, name=LANGS[lang]), chat)
        friend = self.scope is not None or self.friend_bot
        send(help_text(lang, FRIEND_COMMANDS if friend else None), chat, markup=NO_KEYBOARD)
        set_menu(chat, FRIEND_COMMANDS if friend else None)

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
    commands.watcher = amp_watch
    updates = UpdateMonitor(commands.amp, db)
    dota = DotaWatcher(db)
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
                set_descriptions(TOKEN, "main")
                set_descriptions(FRIENDS_TOKEN, "friends")
                if FRIENDS_TOKEN:  # menu dla nowych osob w bocie znajomych: start i jezyk
                    with via(FRIENDS_TOKEN):
                        try:
                            tg_api("setMyCommands", {"commands": json.dumps(
                                [{"command": "start", "description": "Start"},
                                 {"command": "lang", "description": "Język / Language / Язык / Мова"}])})
                        except Exception as e:
                            log(f"setMyCommands (znajomi): {getattr(e, 'code', type(e).__name__)}")
                with via(FRIENDS_TOKEN):
                    for uid, _name, _insts in friends_all(db):
                        set_menu(uid, FRIEND_COMMANDS)
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
        try:
            dota.poll()
        except Exception as e:
            log(f"Dota: {e}")
        if FRIENDS_TOKEN:  # dwa boty na zmiane, kazdy krotko
            commands.poll(1)
            commands.poll(1, FRIENDS_TOKEN)
        else:
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
