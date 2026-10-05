# amp-cubecoders-tg-bot 🎮

[![CI](https://github.com/setsun-ai/amp-cubecoders-tg-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/setsun-ai/amp-cubecoders-tg-bot/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/setsun-ai/amp-cubecoders-tg-bot)](https://github.com/setsun-ai/amp-cubecoders-tg-bot/releases/latest)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
[![Ліцензія: MIT](https://img.shields.io/badge/ліцензія-MIT-green)](LICENSE)

🇬🇧 **[English](README.md)** · 🇵🇱 **[Polski](README.pl.md)** · 🇷🇺 **[Русский](README.ru.md)**

**Telegram-бот для ігрових серверів в [AMP (CubeCoders)](https://cubecoders.com/AMP).** Повідомляє, хто зайшов і вийшов, веде історію гравців, надсилає підсумки тижня й стежить за машиною, на якій працюють сервери. Один файл на Python, лише стандартна бібліотека, без плагінів для AMP. Польська, англійська, російська та українська.

```
🆕 НОВИЙ ГРАВЕЦЬ!
🟢 Alice заходить на сервер
🎮 Valheim (Valheim01)
🆔 SteamID: 76561198000000000
👥 Онлайн: 1
```

## Що вміє

- **Входи й виходи гравців** на всіх інстансах AMP, із часом гри. Valheim: SteamID із посиланням на профіль. Minecraft: UUID.
- **Нові ігри без налаштування**: бот бере правила розпізнавання гравців, які вже є в AMP, з файлу `.kvp` кожного інстансу (`Console.UserJoinRegex` / `Console.UserLeaveRegex`). Якщо гра їх не має, прийде ⚠️ з проханням надіслати рядок із логу.
- **🆕 Новий гравець**: сповіщення, коли заходить той, кого бот ще не бачив.
- **💀 Смерті** (Valheim, Minecraft) з лічильником за день.
- **Підсумки тижня** в неділю ввечері: час гри за серверами, рейтинг, найактивніша година.
- **Машина**: сповіщення, коли батарея ноутбука падає нижче порогу, CPU перегрівається або падає тунель [playit.gg](https://playit.gg).
- **Команди** (лише для адміна, у кнопці *Menu* Telegram): `/online`, `/servers`, `/friends`, `/updates`, `/status`, `/history [N]`, `/player НІК`, `/week`, `/dota`, `/lang`, `/version`, `/update`, `/rollback`, `/help`.
- **Керування серверами** (`/servers`): запуск, зупинка, перезапуск, оновлення гри й бекап інстансів AMP, список гравців онлайн із кіком і баном, ігрова консоль (з відповіддю сервера) і пароль сервера – усе кнопками, з підтвердженням і попередженням, якщо хтось грає. Потрібен окремий користувач AMP для бота (`AMP_URL`, `AMP_USER`, `AMP_PASS`); перевірка: `python3 /opt/amp-tg-bot/bot.py --amp-test`. Інстанс і ігровий сервер – різні речі: ⏻ вмикає й вимикає інстанс AMP, ▶️/⏹ запускають і зупиняють лише ігровий сервер (інстанс лишається ввімкненим, його можна оновлювати), а ▶️ при вимкненому інстансі робить і те, і те. Кожна дія має одне повідомлення, що стежить за нею до кінця – стан, час, прогрес – і закінчується ✅, ❌ з останніми рядками консолі або ⚠️, якщо AMP чекає на клік у панелі. Повторне натискання під час дії нічого не робить.
- **Моди** (лише адмін: `/servers` → сервер → 🧩): Minecraft (Forge, NeoForge, Fabric – завантажувач і версія гри беруться із сервера) з Modrinth та ігри на BepInEx, наприклад Valheim, з Thunderstore – за назвою чи посиланням, з обов'язковими залежностями; або надішли файл (.jar чи .zip/.dll для BepInEx, до 20 МБ). Видалені моди потрапляють до теки `.tg-trash`, а не зникають назавжди; твої конфіги BepInEx не перезаписуються.
- **Dota 2** (`/dota`): `/dota add ID` (Friend ID з профілю в Доті або посилання на профіль OpenDota/Dotabuff/Steam) - після кожного нового матчу гравця приходить одне повідомлення: перемога/поразка, герой, KDA, GPM/XPM, режим і ранг, із посиланням на OpenDota. Безкоштовний API OpenDota без ключа; у гравця має бути ввімкнено *Expose Public Match Data* (бот перевіряє). Перевірка щогодини (`DOTA_CHECK_MINUTES`, `0` = вимк.).
- **Розбан** (👥 Гравці → ♻️): обираєш сервер, і бот надсилає команду розбану гри (`pardon` у Minecraft, `unban` в інших). Друзі можуть робити це на своїх серверах.
- **Налаштування** (`/servers` → сервер → ⚙️): усі налаштування інстансу як у панелі AMP – групи, пошук (наприклад `motd`, `difficulty`), списки кнопками, увімк./вимк. одним натисканням, текст вводиться. Також тип і версія гри (наприклад Forge або Vanilla), з нагадуванням оновити гру. Без паролів (🔑 окремо) і налаштувань самого AMP (порти, логіни).
- **Друзі** (`/friends`): друг пише боту `/start`, ти отримуєш запит із кнопкою і позначаєш сервери, якими він може керувати. Він бачить лише їх: запуск, зупинка, перезапуск, оновлення гри, бекап, гравці (кік/бан) і консоль – без паролів, без сповіщень про гравців і без історії. Про кожну його дію тобі приходить повідомлення. 🗑 забирає доступ. З `TG_FRIENDS_TOKEN` друзі користуються окремим ботом (той самий процес і база), а головний лишається лише твоїм. У друзів немає консолі й завантаження модів.
- **Панель AMP у Telegram**: оновлення, бекапи й завантаження, запущені з бота чи панелі, приходять одним повідомленням із живим прогрес-баром (▓▓▓▓░░░░░░ 40%), яке оновлюється до ✅ готово або ❌ помилка; запуск, зупинка й падіння сервера теж приходять у чат (`AMP_NOTIFY=0` вимикає).
- **Оновлення** (`/updates`): раз на кілька годин бот перевіряє пакети системи (apt) і пише, коли є оновлення безпеки або важливі (Tailscale, playit, Webmin, пакет AMP, ядро), коли потрібне перезавантаження і коли вийшла нова версія AMP – лише якщо з'явилося щось нове. Спочатку бот сам оновлює списки пакетів (у свою теку, без root), тому показує те саме, що Webmin; пакети, які Ubuntu затримує (phased updates, kept back), ідуть окремо – `apt upgrade` їх поки не встановить.
- **Мови**: `/lang` із кнопками, запам'ятовується для кожного чату.
- **Самооновлення**: `/update` встановлює найновіший реліз із GitHub, попередньо перевіривши його на вашому сервері; `/rollback` повертає попередню версію.

Бот читає `AMP_Logs/AMPLOG_*.log` кожного інстансу. Фальшиві входи, написані в ігровому чаті (`<Bob> Alice joined the game`), ігноруються. Справжні IP гравців видно лише при прямому підключенні; через тунель (наприклад, playit.gg) усі приходять з адреси тунелю.

## Встановлення (Linux, AMP у `/home/amp/.ampdata`)

1. Створіть бота в [@BotFather](https://t.me/BotFather) (`/newbot`) і напишіть йому будь-що.
2. Від root встановіть скрипт оновлення та завантажте бота:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/deploy/update.sh -o /usr/local/bin/amp-tg-bot-update
   chmod +x /usr/local/bin/amp-tg-bot-update
   mkdir -p /opt/amp-tg-bot && chown amp:amp /opt/amp-tg-bot
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/bot.py -o /opt/amp-tg-bot/bot.py
   ```

3. Збережіть токен (під час вставлення його не видно) і дізнайтеся свій chat ID:

   ```bash
   read -rsp "Token: " T && printf 'TG_TOKEN=%s\n' "$T" > /etc/amp-tg-bot.env && chmod 600 /etc/amp-tg-bot.env
   python3 /opt/amp-tg-bot/bot.py --chatid
   echo 'TG_CHAT_ID=123456789' >> /etc/amp-tg-bot.env
   python3 /opt/amp-tg-bot/bot.py --test
   ```

4. Служба systemd:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/deploy/amp-tg-bot.service -o /etc/systemd/system/amp-tg-bot.service
   systemctl daemon-reload && systemctl enable --now amp-tg-bot
   amp-tg-bot-update
   ```

## Налаштування

Усе в `/etc/amp-tg-bot.env` ([приклад](deploy/amp-tg-bot.env.example)); після зміни `systemctl restart amp-tg-bot`.

| Змінна | За замовчуванням | Значення |
|---|---|---|
| `TG_TOKEN` | – | токен бота від @BotFather |
| `TG_CHAT_ID` | – | куди йдуть сповіщення (ваш особистий чат або група) |
| `TG_ADMINS` | `TG_CHAT_ID` | ID користувачів Telegram, яким доступні команди, через кому |
| `TG_FRIENDS_TOKEN` | – | Другий бот (від BotFather) для друзів: вони пишуть йому, ти керуєш доступом із головного, який тоді лише твій |
| `BOT_LANG` | `pl` | мова за замовчуванням: `pl`, `en`, `ru`, `uk` (`/lang` змінює її для чату) |
| `AMP_URL` | – | адреса панелі AMP, наприклад `http://127.0.0.1:8080` (для `/servers`) |
| `AMP_USER`, `AMP_PASS` | – | окремий користувач AMP для бота (без 2FA) |
| `AMP_NOTIFY` | `1` | завдання AMP із прогресом і зміни стану серверів у Telegram; `0` = вимкнено |
| `AMP_TASK_MIN_SECONDS` | `15` | завдання AMP коротші за це не потрапляють у чат |
| `AMP_TASK_IGNORE` | `remote sources\|refreshing\|checking for` | завдання AMP, які бот не показує (регулярний вираз) |
| `UPDATES_CHECK_HOURS` | `6` | як часто перевіряти оновлення; `0` = ніколи |
| `RETENTION_DAYS` | `180` | скільки зберігати історію гравців |
| `BATTERY_WARN` | `45` | сповіщення, коли батарея нижче цього %; `0` вимикає |
| `TEMP_ALERT` | `85` | поріг температури CPU, °C |
| `PLAYIT_SERVICE` | `playit` | служба systemd агента playit.gg |
| `WEEKLY_DAY`, `WEEKLY_HOUR` | `6`, `20` | підсумки тижня: день (0 = понеділок) і година |
| `AMP_INSTANCES` | `/home/amp/.ampdata/instances` | де AMP зберігає інстанси |
| `DB_PATH` | `/var/lib/amp-tg-bot/players.db` | історія гравців |

## Оновлення

- У Telegram: `/update`. Бот завантажує найновіший реліз, один раз запускає його з `--selftest`, замінює себе й перезапускається. Якщо перевірка не пройшла, лишається стара версія. `/rollback` повертає попередню.
- У терміналі, якщо бот не відповідає: `amp-tg-bot-update` або `amp-tg-bot-update --rollback`.

Файл налаштувань та історія гравців не змінюються.

## Розробка

```bash
pip install -r requirements-dev.txt
ruff check . && pytest -q
```

Див. [CONTRIBUTING.md](CONTRIBUTING.md). Приватність: [PRIVACY.md](PRIVACY.md). Безпека: [SECURITY.md](SECURITY.md).

## Ліцензія

[MIT](LICENSE)
