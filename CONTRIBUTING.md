# Contributing / Współpraca / Участие / Участь

🇬🇧 English below · 🇵🇱 [po polsku](#po-polsku) · 🇷🇺 [по-русски](#по-русски) · 🇺🇦 [українською](#українською)

Contributions are welcome, from a typo fix to support for a new game.

```bash
git clone https://github.com/setsun-ai/amp-cubecoders-tg-bot.git && cd amp-cubecoders-tg-bot
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt      # Windows: .venv\Scripts\pip ...
.venv/bin/python -m pytest -q                       # must pass: no network, no AMP, no Telegram
.venv/bin/python -m ruff check .                    # must be clean
```

## Rules of thumb

- **One file, standard library only.** The bot must run on a stock Python 3.11+ without `pip install`.
- **Every user-facing text goes through `t("key")`.** Add the key to `STRINGS` in `bot.py` in **all four** languages (pl, en, ru, uk) with the same `{placeholders}`; a test checks this.
- **A new game** that AMP doesn't recognise: add a rules class like `MinecraftRules`, pick it in `detect_rules()` and add a test with sample log lines.
- **Nothing personal in the repository.** No real player names, SteamIDs, server names or addresses in tests or examples.
- **Releases:** bump `VERSION` in `bot.py`, add a `## X.Y.Z` section to `CHANGELOG.md`, push the tag `vX.Y.Z`. GitHub Actions runs the tests and publishes the release that `/update` installs.

---

## Po polsku

Mile widziane poprawki i obsługa nowych gier. Zasady: jeden plik i sama biblioteka standardowa; każdy tekst dla użytkownika przez `t("klucz")` we wszystkich czterech językach; nowa gra = klasa reguł + test z przykładowymi liniami logu; żadnych prawdziwych nicków, SteamID ani adresów w repo. Przed PR: `pytest -q` i `ruff check .`.

## По-русски

Исправления и поддержка новых игр приветствуются. Правила: один файл и только стандартная библиотека; любой текст для пользователя через `t("ключ")` на всех четырёх языках; новая игра = класс правил + тест с примерами строк лога; никаких настоящих ников, SteamID и адресов в репозитории. Перед PR: `pytest -q` и `ruff check .`.

## Українською

Виправлення й підтримка нових ігор вітаються. Правила: один файл і лише стандартна бібліотека; будь-який текст для користувача через `t("ключ")` усіма чотирма мовами; нова гра = клас правил + тест із прикладами рядків логу; жодних справжніх ніків, SteamID та адрес у репозиторії. Перед PR: `pytest -q` і `ruff check .`.
