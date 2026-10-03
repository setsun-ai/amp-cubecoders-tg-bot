# amp-cubecoders-tg-bot 🎮

[![CI](https://github.com/setsun-ai/amp-cubecoders-tg-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/setsun-ai/amp-cubecoders-tg-bot/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/setsun-ai/amp-cubecoders-tg-bot)](https://github.com/setsun-ai/amp-cubecoders-tg-bot/releases/latest)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
[![Лицензия: MIT](https://img.shields.io/badge/лицензия-MIT-green)](LICENSE)

🇬🇧 **[English](README.md)** · 🇵🇱 **[Polski](README.pl.md)** · 🇺🇦 **[Українська](README.uk.md)**

**Telegram-бот для игровых серверов в [AMP (CubeCoders)](https://cubecoders.com/AMP).** Сообщает, кто зашёл и вышел, ведёт историю игроков, присылает итоги недели и следит за машиной, на которой работают серверы. Один файл на Python, только стандартная библиотека, без плагинов для AMP. Польский, английский, русский и украинский.

```
🆕 НОВЫЙ ИГРОК!
🟢 Alice заходит на сервер
🎮 Valheim (Valheim01)
🆔 SteamID: 76561198000000000
👥 Онлайн: 1
```

## Что умеет

- **Входы и выходы игроков** на всех инстансах AMP, со временем игры. Valheim: SteamID со ссылкой на профиль. Minecraft: UUID.
- **Новые игры без настройки**: бот берёт правила распознавания игроков, которые уже есть в AMP, из файла `.kvp` каждого инстанса (`Console.UserJoinRegex` / `Console.UserLeaveRegex`). Если у игры их нет, придёт ⚠️ с просьбой прислать строку из лога.
- **🆕 Новый игрок**: оповещение, когда заходит тот, кого бот ещё не видел.
- **💀 Смерти** (Valheim, Minecraft) со счётчиком за день.
- **Итоги недели** в воскресенье вечером: время игры по серверам, рейтинг, самый активный час.
- **Машина**: оповещения, когда батарея ноутбука падает ниже порога, CPU перегревается или падает туннель [playit.gg](https://playit.gg).
- **Команды** (только для админа, в кнопке *Menu* Telegram): `/online`, `/status`, `/history [N]`, `/player НИК`, `/week`, `/lang`, `/version`, `/update`, `/rollback`, `/help`.
- **Языки**: `/lang` с кнопками, запоминается для каждого чата.
- **Самообновление**: `/update` ставит новейший релиз с GitHub, предварительно проверив его на вашем сервере; `/rollback` возвращает прежнюю версию.

Бот читает `AMP_Logs/AMPLOG_*.log` каждого инстанса. Фальшивые входы, написанные в игровом чате (`<Bob> Alice joined the game`), игнорируются. Настоящие IP игроков видны только при прямом подключении; через туннель (например, playit.gg) все приходят с адреса туннеля.

## Установка (Linux, AMP в `/home/amp/.ampdata`)

1. Создайте бота у [@BotFather](https://t.me/BotFather) (`/newbot`) и напишите ему что-нибудь.
2. От root установите скрипт обновления и скачайте бота:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/deploy/update.sh -o /usr/local/bin/amp-tg-bot-update
   chmod +x /usr/local/bin/amp-tg-bot-update
   mkdir -p /opt/amp-tg-bot && chown amp:amp /opt/amp-tg-bot
   curl -fsSL https://raw.githubusercontent.com/setsun-ai/amp-cubecoders-tg-bot/main/bot.py -o /opt/amp-tg-bot/bot.py
   ```

3. Сохраните токен (при вставке его не видно) и узнайте свой chat ID:

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

## Настройки

Всё в `/etc/amp-tg-bot.env` ([пример](deploy/amp-tg-bot.env.example)); после изменения `systemctl restart amp-tg-bot`.

| Переменная | По умолчанию | Значение |
|---|---|---|
| `TG_TOKEN` | – | токен бота от @BotFather |
| `TG_CHAT_ID` | – | куда идут оповещения (ваш личный чат или группа) |
| `TG_ADMINS` | `TG_CHAT_ID` | ID пользователей Telegram, которым доступны команды, через запятую |
| `BOT_LANG` | `pl` | язык по умолчанию: `pl`, `en`, `ru`, `uk` (`/lang` меняет его для чата) |
| `RETENTION_DAYS` | `180` | сколько хранить историю игроков |
| `BATTERY_WARN` | `45` | оповещение, когда батарея ниже этого %; `0` выключает |
| `TEMP_ALERT` | `85` | порог температуры CPU, °C |
| `PLAYIT_SERVICE` | `playit` | служба systemd агента playit.gg |
| `WEEKLY_DAY`, `WEEKLY_HOUR` | `6`, `20` | итоги недели: день (0 = понедельник) и час |
| `AMP_INSTANCES` | `/home/amp/.ampdata/instances` | где AMP хранит инстансы |
| `DB_PATH` | `/var/lib/amp-tg-bot/players.db` | история игроков |

## Обновление

- В Telegram: `/update`. Бот скачивает новейший релиз, один раз запускает его с `--selftest`, заменяет себя и перезапускается. Если проверка не прошла, остаётся старая версия. `/rollback` возвращает предыдущую.
- В терминале, если бот не отвечает: `amp-tg-bot-update` или `amp-tg-bot-update --rollback`.

Файл настроек и история игроков не затрагиваются.

## Разработка

```bash
pip install -r requirements-dev.txt
ruff check . && pytest -q
```

См. [CONTRIBUTING.md](CONTRIBUTING.md). Приватность: [PRIVACY.md](PRIVACY.md). Безопасность: [SECURITY.md](SECURITY.md).

## Лицензия

[MIT](LICENSE)
