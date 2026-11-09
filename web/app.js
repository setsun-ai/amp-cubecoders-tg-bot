/* AMP • Dota Hub — vanilla JS Telegram Mini App, no build chain. */
'use strict';

// Every text the panel shows, in the bot's language order: pl, en, ru, uk. {name} marks a value.
// err_<code> are the server's error codes (miniapp.APIError). tests/test_panel_text.py checks it is complete.
const STRINGS = {
  "loading_panel": ["Wczytywanie panelu", "Loading the panel", "Загрузка панели", "Завантаження панелі"],
  "connecting": ["Łączenie z botem…", "Connecting to the bot…", "Подключение к боту…", "Підключення до бота…"],
  "nav_amp": ["Serwery AMP", "AMP servers", "Серверы AMP", "Сервери AMP"],
  "nav_dota": ["Dota 2", "Dota 2", "Dota 2", "Dota 2"],
  "reload": ["Odśwież dane", "Refresh data", "Обновить данные", "Оновити дані"],
  "no_date": ["Brak daty", "No date", "Нет даты", "Немає дати"],
  "rank_unknown": ["Ranga nieznana", "Rank unknown", "Ранг неизвестен", "Ранг невідомий"],
  "rank": ["Ranga", "Rank", "Ранг", "Ранг"],
  "mode": ["Tryb {n}", "Mode {n}", "Режим {n}", "Режим {n}"],
  "timeout": ["Serwer zbyt długo nie odpowiada", "The server takes too long to answer", "Сервер слишком долго не отвечает", "Сервер надто довго не відповідає"],
  "offline": ["Brak połączenia z panelem", "No connection to the panel", "Нет связи с панелью", "Немає зв'язку з панеллю"],
  "http_error": ["Błąd HTTP {status}", "HTTP error {status}", "Ошибка HTTP {status}", "Помилка HTTP {status}"],
  "dota_title": ["Dota 2 · Obserwowani", "Dota 2 · Watched", "Dota 2 · Отслеживаемые", "Dota 2 · Відстежувані"],
  "dota_lead": ["Ostatnie mecze, historia bohaterów i wyniki. Bez przewijania powiadomień Telegrama.", "Recent matches, hero history and results, without scrolling through Telegram notifications.", "Последние матчи, история героев и результаты — без прокрутки уведомлений Telegram.", "Останні матчі, історія героїв і результати — без гортання сповіщень Telegram."],
  "st_watched": ["Obserwowani", "Watched", "Отслеживаются", "Відстежуються"],
  "st_matches": ["Mecze w historii", "Matches in history", "Матчей в истории", "Матчів в історії"],
  "st_winrate": ["Win rate", "Win rate", "Винрейт", "Вінрейт"],
  "watched_players": ["Obserwowani gracze", "Watched players", "Отслеживаемые игроки", "Відстежувані гравці"],
  "add": ["+ Dodaj", "+ Add", "+ Добавить", "+ Додати"],
  "nobody_watched": ["Nikogo jeszcze nie obserwujesz", "You aren't watching anyone yet", "Вы пока никого не отслеживаете", "Ви ще нікого не відстежуєте"],
  "nobody_watched_hint": ["Dodaj Friend ID z Dota 2 lub adres profilu OpenDota.", "Add a Dota 2 Friend ID or an OpenDota profile link.", "Добавьте Friend ID из Dota 2 или ссылку на профиль OpenDota.", "Додайте Friend ID з Dota 2 або посилання на профіль OpenDota."],
  "match_history": ["Historia meczów", "Match history", "История матчей", "Історія матчів"],
  "refresh": ["↻ Odśwież", "↻ Refresh", "↻ Обновить", "↻ Оновити"],
  "all_players": ["Wszyscy", "Everyone", "Все", "Усі"],
  "all_results": ["Wszystkie", "All", "Все", "Усі"],
  "wins": ["Wygrane", "Wins", "Победы", "Перемоги"],
  "losses": ["Przegrane", "Losses", "Поражения", "Поразки"],
  "no_matches_filter": ["Brak meczów dla tych filtrów", "No matches for these filters", "Нет матчей для этих фильтров", "Немає матчів для цих фільтрів"],
  "no_matches_hint": ["Historia zapełnia się podczas synchronizacji OpenDota.", "The history fills up as OpenDota syncs.", "История заполняется при синхронизации с OpenDota.", "Історія заповнюється під час синхронізації з OpenDota."],
  "notif_title": ["Bot pisze na czacie o nowych meczach", "The bot posts new matches in the chat", "Бот пишет в чат о новых матчах", "Бот пише в чат про нові матчі"],
  "notif_hint": ["Historia w panelu zapisuje się zawsze, także gdy bot milczy.", "The panel keeps the history either way, even when the bot stays quiet.", "История в панели сохраняется всегда, даже когда бот молчит.", "Історія в панелі зберігається завжди, навіть коли бот мовчить."],
  "notif_on": ["🔔 Włączone", "🔔 On", "🔔 Включены", "🔔 Увімкнено"],
  "notif_off": ["🔕 Wyłączone", "🔕 Off", "🔕 Выключены", "🔕 Вимкнено"],
  "notif_changed": ["Zmieniono powiadomienia", "Notifications changed", "Уведомления изменены", "Сповіщення змінено"],
  "pct_wins": ["{pct}% wygranych", "{pct}% won", "{pct}% побед", "{pct}% перемог"],
  "no_matches": ["Brak meczów", "No matches", "Нет матчей", "Немає матчів"],
  "no_public": ["Brak publicznych meczów", "No public matches", "Нет публичных матчей", "Немає публічних матчів"],
  "matches_btn": ["Mecze", "Matches", "Матчи", "Матчі"],
  "victory": ["ZWYCIĘSTWO", "VICTORY", "ПОБЕДА", "ПЕРЕМОГА"],
  "defeat": ["PORAŻKA", "DEFEAT", "ПОРАЖЕНИЕ", "ПОРАЗКА"],
  "watch_title": ["Obserwuj gracza", "Watch a player", "Отслеживать игрока", "Відстежувати гравця"],
  "watch_hint": ["Friend ID (Steam32) albo link do profilu Steam, Dotabuff lub OpenDota.", "Friend ID (Steam32) or a Steam, Dotabuff or OpenDota profile link.", "Friend ID (Steam32) или ссылка на профиль Steam, Dotabuff или OpenDota.", "Friend ID (Steam32) або посилання на профіль Steam, Dotabuff чи OpenDota."],
  "example_id": ["Np. 123456789", "E.g. 123456789", "Напр. 123456789", "Напр. 123456789"],
  "watch_add": ["Dodaj do obserwowanych", "Start watching", "Отслеживать", "Відстежувати"],
  "enter_id": ["Wpisz ID gracza", "Enter the player ID", "Введите ID игрока", "Введіть ID гравця"],
  "added": ["Dodano gracza", "Player added", "Игрок добавлен", "Гравця додано"],
  "remove_q": ["Usunąć {name}?", "Remove {name}?", "Удалить {name}?", "Видалити {name}?"],
  "remove_hint": ["Wraz z obserwacją usunięta zostanie jego historia w lokalnej bazie.", "Their match history in the local database goes too.", "Вместе с отслеживанием удалится и его история в локальной базе.", "Разом із відстеженням буде видалено і його історію в локальній базі."],
  "remove": ["Usuń", "Remove", "Удалить", "Видалити"],
  "removed": ["Usunięto gracza", "Player removed", "Игрок удалён", "Гравця видалено"],
  "cancel": ["Anuluj", "Cancel", "Отмена", "Скасувати"],
  "won": ["Wygrana", "Win", "Победа", "Перемога"],
  "lost": ["Przegrana", "Loss", "Поражение", "Поразка"],
  "loading_match": ["Pobieranie szczegółów meczu…", "Loading match details…", "Загрузка деталей матча…", "Завантаження деталей матчу…"],
  "open_opendota": ["Otwórz mecz w OpenDota ↗", "Open the match on OpenDota ↗", "Открыть матч в OpenDota ↗", "Відкрити матч в OpenDota ↗"],
  "team_kills": ["{n} zabójstw", "{n} kills", "убийств: {n}", "вбивств: {n}"],
  "no_team_data": ["Brak danych graczy w OpenDota", "OpenDota has no player data", "В OpenDota нет данных игроков", "В OpenDota немає даних гравців"],
  "hero_n": ["Bohater #{id}", "Hero #{id}", "Герой #{id}", "Герой #{id}"],
  "amp_title": ["Centrum instancji", "Instance centre", "Центр инстансов", "Центр інстансів"],
  "amp_lead": ["Sterowanie serwerami, stan graczy i parametry maszyny z jednego miejsca.", "Server control, players and machine load in one place.", "Управление серверами, игроки и нагрузка машины в одном месте.", "Керування серверами, гравці та навантаження машини в одному місці."],
  "st_instances": ["Instancje", "Instances", "Инстансы", "Інстанси"],
  "st_games_online": ["Gry online", "Games online", "Игр онлайн", "Ігор онлайн"],
  "st_players_online": ["Gracze online", "Players online", "Игроков онлайн", "Гравців онлайн"],
  "your_servers": ["Twoje serwery", "Your servers", "Ваши серверы", "Ваші сервери"],
  "amp_down": ["AMP jest niedostępny", "AMP is unavailable", "AMP недоступен", "AMP недоступний"],
  "amp_unconfigured": ["AMP nie jest skonfigurowany", "AMP isn't configured", "AMP не настроен", "AMP не налаштовано"],
  "amp_unconfigured_hint": ["Ustaw AMP_URL, AMP_USER i AMP_PASS w /etc/amp-tg-bot.env.", "Set AMP_URL, AMP_USER and AMP_PASS in /etc/amp-tg-bot.env.", "Укажите AMP_URL, AMP_USER и AMP_PASS в /etc/amp-tg-bot.env.", "Вкажіть AMP_URL, AMP_USER і AMP_PASS у /etc/amp-tg-bot.env."],
  "no_instances": ["Brak dostępnych instancji", "No instances available", "Нет доступных инстансов", "Немає доступних інстансів"],
  "no_instances_hint": ["Nie znaleziono instancji przypisanych do tego konta.", "No instances are assigned to this account.", "К этой учётной записи не привязаны инстансы.", "До цього облікового запису не прив'язано інстансів."],
  "amp_conn_lost": ["Brak połączenia z AMP", "No connection to AMP", "Нет связи с AMP", "Немає зв'язку з AMP"],
  "no_data": ["Brak danych", "No data", "Нет данных", "Немає даних"],
  "game": ["Gra", "Game", "Игра", "Гра"],
  "n_online": ["{n} online", "{n} online", "{n} онлайн", "{n} онлайн"],
  "badge_busy": ["W TOKU", "BUSY", "ИДЁТ", "ТРИВАЄ"],
  "badge_online": ["ONLINE", "ONLINE", "ОНЛАЙН", "ОНЛАЙН"],
  "badge_ready": ["GOTOWA", "READY", "ГОТОВ", "ГОТОВИЙ"],
  "badge_offline": ["OFFLINE", "OFFLINE", "ВЫКЛ", "ВИМК"],
  "inst_gone": ["Instancja niedostępna", "Instance unavailable", "Инстанс недоступен", "Інстанс недоступний"],
  "inst_gone_hint": ["Odśwież listę serwerów.", "Refresh the server list.", "Обновите список серверов.", "Оновіть список серверів."],
  "inst_status": ["STATUS INSTANCJI", "INSTANCE STATUS", "СТАТУС ИНСТАНСА", "СТАТУС ІНСТАНСУ"],
  "unknown": ["Nieznany", "Unknown", "Неизвестно", "Невідомо"],
  "n_players_online": ["{n} graczy online", "{n} players online", "игроков онлайн: {n}", "гравців онлайн: {n}"],
  "op_running": ["Operacja w toku: {op}", "Operation in progress: {op}", "Идёт операция: {op}", "Триває операція: {op}"],
  "tab_control": ["Sterowanie", "Control", "Управление", "Керування"],
  "tab_players": ["Gracze", "Players", "Игроки", "Гравці"],
  "tab_settings": ["Ustawienia", "Settings", "Настройки", "Налаштування"],
  "tab_console": ["Konsola", "Console", "Консоль", "Консоль"],
  "server_actions": ["Akcje serwera", "Server actions", "Действия с сервером", "Дії з сервером"],
  "act_start": ["Start", "Start", "Старт", "Старт"],
  "act_stop": ["Stop", "Stop", "Стоп", "Стоп"],
  "act_restart": ["Restart", "Restart", "Перезапуск", "Перезапуск"],
  "act_on": ["Instancja ON", "Instance ON", "Инстанс ВКЛ", "Інстанс УВІМК"],
  "act_off": ["Instancja OFF", "Instance OFF", "Инстанс ВЫКЛ", "Інстанс ВИМК"],
  "act_update": ["Aktualizuj", "Update", "Обновить", "Оновити"],
  "act_backup": ["Backup", "Backup", "Бэкап", "Бекап"],
  "actions_hint": ["Start/Stop gry i włączenie/wyłączenie instancji AMP to osobne operacje. Potwierdzaj operacje mogące przerwać grę.", "Game Start/Stop and turning the AMP instance on/off are separate operations. Anything that can interrupt a game asks first.", "Старт/стоп игры и включение/выключение инстанса AMP — разные операции. То, что может прервать игру, требует подтверждения.", "Старт/стоп гри та увімкнення/вимкнення інстансу AMP — різні операції. Те, що може перервати гру, потребує підтвердження."],
  "confirm_disruptive": ["Czy wykonać „{action}” na {inst}? Gracze online: {n}.", "Run “{action}” on {inst}? Players online: {n}.", "Выполнить «{action}» на {inst}? Игроков онлайн: {n}.", "Виконати «{action}» на {inst}? Гравців онлайн: {n}."],
  "confirm_plain": ["Wykonać „{action}” dla {inst}?", "Run “{action}” for {inst}?", "Выполнить «{action}» для {inst}?", "Виконати «{action}» для {inst}?"],
  "warn_hint": ["Przy ostrzeżeniu bot spróbuje wysłać komunikat w grze i odczeka {s} s. Nie każda gra to obsługuje.", "With a warning the bot tries to post a message in the game and waits {s} s. Not every game supports it.", "С предупреждением бот попробует написать в игре и подождёт {s} с. Не все игры это поддерживают.", "З попередженням бот спробує написати в грі й зачекає {s} с. Не всі ігри це підтримують."],
  "warn_and_wait": ["⏳ Ostrzeż i odczekaj {s} s", "⏳ Warn and wait {s} s", "⏳ Предупредить и подождать {s} с", "⏳ Попередити й зачекати {s} с"],
  "run_now": ["⚡ Wykonaj teraz", "⚡ Run now", "⚡ Выполнить сейчас", "⚡ Виконати зараз"],
  "confirm": ["Potwierdź", "Confirm", "Подтвердить", "Підтвердити"],
  "queued": ["Zlecono: {action}. Postęp widać tutaj i w Telegramie.", "Started: {action}. Progress shows here and in Telegram.", "Запущено: {action}. Ход виден здесь и в Telegram.", "Запущено: {action}. Перебіг видно тут і в Telegram."],
  "op_done": ["✓ {inst}: {op} — zakończone", "✓ {inst}: {op} — finished", "✓ {inst}: {op} — завершено", "✓ {inst}: {op} — завершено"],
  "why_busy": ["Przyciski czekają, aż skończy się: {op}.", "The buttons wait until this finishes: {op}.", "Кнопки ждут окончания: {op}.", "Кнопки чекають, доки завершиться: {op}."],
  "why_off": ["Instancja AMP jest wyłączona, więc działa tylko „{start}” i „{on}”.", "The AMP instance is off, so only “{start}” and “{on}” work.", "Инстанс AMP выключен, поэтому работают только «{start}» и «{on}».", "Інстанс AMP вимкнено, тому працюють лише «{start}» і «{on}»."],
  "loading_players": ["Wczytywanie graczy", "Loading players", "Загрузка игроков", "Завантаження гравців"],
  "loading_players_hint": ["Pobieranie listy z AMP…", "Fetching the list from AMP…", "Получение списка из AMP…", "Отримання списку з AMP…"],
  "error": ["Błąd", "Error", "Ошибка", "Помилка"],
  "nobody_plays": ["Nikt nie gra", "Nobody is playing", "Никто не играет", "Ніхто не грає"],
  "nobody_plays_hint": ["Serwer nie zgłasza aktywnych graczy.", "The server reports no active players.", "Сервер не сообщает об активных игроках.", "Сервер не повідомляє про активних гравців."],
  "config": ["Konfiguracja", "Configuration", "Конфигурация", "Конфігурація"],
  "search_settings": ["Szukaj: MOTD, difficulty, world…", "Search: MOTD, difficulty, world…", "Поиск: MOTD, difficulty, world…", "Пошук: MOTD, difficulty, world…"],
  "loading_settings": ["Wczytywanie ustawień", "Loading settings", "Загрузка настроек", "Завантаження налаштувань"],
  "loading_settings_hint": ["Pobieranie konfiguracji z AMP…", "Fetching the configuration from AMP…", "Получение конфигурации из AMP…", "Отримання конфігурації з AMP…"],
  "config_error": ["Błąd konfiguracji", "Configuration error", "Ошибка конфигурации", "Помилка конфігурації"],
  "edit": ["Edytuj", "Edit", "Изменить", "Змінити"],
  "no_settings": ["Brak ustawień", "No settings", "Нет настроек", "Немає налаштувань"],
  "no_settings_hint": ["Zmień wyszukiwaną frazę.", "Try another search.", "Измените запрос.", "Змініть запит."],
  "on": ["Włączone", "On", "Включено", "Увімкнено"],
  "off": ["Wyłączone", "Off", "Выключено", "Вимкнено"],
  "value": ["Wartość", "Value", "Значение", "Значення"],
  "save_setting": ["Zapisz ustawienie", "Save setting", "Сохранить", "Зберегти"],
  "saved": ["Zapisano ustawienie", "Setting saved", "Настройка сохранена", "Налаштування збережено"],
  "loading": ["Ładowanie…", "Loading…", "Загрузка…", "Завантаження…"],
  "no_console": ["Brak ostatnich wpisów.", "No recent lines.", "Нет последних записей.", "Немає останніх записів."],
  "console_placeholder": ["Komenda do konsoli gry", "Game console command", "Команда для консоли игры", "Команда для консолі гри"],
  "console_label": ["Komenda (tylko administrator)", "Command (admin only)", "Команда (только админ)", "Команда (лише адмін)"],
  "send": ["Wyślij", "Send", "Отправить", "Надіслати"],
  "sent": ["Wysłano komendę", "Command sent", "Команда отправлена", "Команду надіслано"],
  "console_hint": ["Komendy konsoli wykonują się z uprawnieniami AMP. Nie udostępniaj tej funkcji znajomym.", "Console commands run with AMP's permissions. Don't give this to friends.", "Команды консоли выполняются с правами AMP. Не давайте это друзьям.", "Команди консолі виконуються з правами AMP. Не давайте це друзям."],
  "connected": ["Połączono • {name} • {time}", "Connected • {name} • {time}", "Подключено • {name} • {time}", "Підключено • {name} • {time}"],
  "refreshed": ["Dane odświeżone", "Data refreshed", "Данные обновлены", "Дані оновлено"],
  "cant_open": ["Nie można otworzyć panelu", "Can't open the panel", "Не удаётся открыть панель", "Не вдається відкрити панель"],
  "open_via_tg": ["Otwórz panel przez Telegrama", "Open the panel from Telegram", "Откройте панель через Telegram", "Відкрийте панель через Telegram"],
  "open_via_tg_hint": ["Ta aplikacja wymaga poprawnie podpisanej sesji Telegram Mini Apps. Sam link w przeglądarce nie daje dostępu.", "This app needs a signed Telegram Mini App session; the link alone in a browser gives no access.", "Приложению нужна подписанная сессия Telegram Mini Apps; сама ссылка в браузере доступа не даёт.", "Застосунку потрібна підписана сесія Telegram Mini Apps; саме посилання в браузері доступу не дає."],
  "no_session": ["Brak sesji Telegrama", "No Telegram session", "Нет сессии Telegram", "Немає сесії Telegram"],
  "err_open_in_telegram": ["Otwórz panel w Telegramie", "Open the panel in Telegram", "Откройте панель в Telegram", "Відкрийте панель у Telegram"],
  "err_bad_session": ["Nieprawidłowe dane sesji Telegrama", "Invalid Telegram session data", "Неверные данные сессии Telegram", "Невірні дані сесії Telegram"],
  "err_session_expired": ["Sesja Telegrama wygasła. Otwórz panel ponownie", "The Telegram session expired. Open the panel again", "Сессия Telegram истекла. Откройте панель заново", "Сесія Telegram закінчилася. Відкрийте панель знову"],
  "err_bad_signature": ["Nieprawidłowy podpis Telegrama", "Invalid Telegram signature", "Неверная подпись Telegram", "Невірний підпис Telegram"],
  "err_opendota_no_match_data": ["OpenDota nie zwróciła danych meczu", "OpenDota returned no match data", "OpenDota не вернула данные матча", "OpenDota не повернула даних матчу"],
  "err_opendota_bad_match_data": ["OpenDota zwróciła nieprawidłowe dane meczu", "OpenDota returned invalid match data", "OpenDota вернула неверные данные матча", "OpenDota повернула невірні дані матчу"],
  "err_not_found": ["Nie ma takiej strony", "No such page", "Нет такой страницы", "Немає такої сторінки"],
  "err_method_not_allowed": ["Metoda niedostępna", "Method not allowed", "Метод недоступен", "Метод недоступний"],
  "err_bad_request_data": ["Nieprawidłowe dane zadania", "Invalid request data", "Неверные данные запроса", "Невірні дані запиту"],
  "err_json_object_expected": ["Oczekiwano obiektu JSON", "A JSON object was expected", "Ожидался объект JSON", "Очікувався об'єкт JSON"],
  "err_bad_json": ["Nieprawidłowy JSON", "Invalid JSON", "Неверный JSON", "Невірний JSON"],
  "err_panel_error": ["Błąd panelu. Sprawdź log usługi", "Panel error. Check the service log", "Ошибка панели. Проверьте лог службы", "Помилка панелі. Перевірте лог служби"],
  "err_server_busy": ["Serwer jest zajęty", "The server is busy", "Сервер занят", "Сервер зайнятий"],
  "err_no_reply": ["Panel nie otrzymał odpowiedzi. Sprawdź stan przed ponowieniem operacji", "The panel got no reply. Check the state before trying again", "Панель не получила ответа. Проверьте состояние перед повтором", "Панель не отримала відповіді. Перевірте стан перед повтором"],
  "err_operation_failed": ["Operacja nie powiodła się. Sprawdź log bota", "The operation failed. Check the bot log", "Операция не удалась. Проверьте лог бота", "Операція не вдалася. Перевірте лог бота"],
  "err_admin_only_bot": ["Ten bot jest przeznaczony tylko dla administratora", "This bot is for the administrator only", "Этот бот только для администратора", "Цей бот лише для адміністратора"],
  "err_no_access": ["Brak przyznanego dostępu", "You haven't been given access", "Доступ не выдан", "Доступ не надано"],
  "err_no_instance_access": ["Brak dostępu do instancji", "No access to this instance", "Нет доступа к инстансу", "Немає доступу до інстансу"],
  "err_admin_required": ["Ta funkcja wymaga uprawnień administratora", "This needs administrator rights", "Нужны права администратора", "Потрібні права адміністратора"],
  "err_no_request_id": ["Brak identyfikatora operacji", "Missing operation ID", "Нет идентификатора операции", "Немає ідентифікатора операції"],
  "err_enabled_bool": ["Podaj enabled: true lub false", "Send enabled: true or false", "Укажите enabled: true или false", "Вкажіть enabled: true або false"],
  "err_opendota_rate_limited": ["Odświeżanie OpenDota: ponów za kilka minut", "OpenDota refresh: try again in a few minutes", "Обновление OpenDota: повторите через несколько минут", "Оновлення OpenDota: повторіть за кілька хвилин"],
  "err_opendota_sync_off": ["Synchronizacja OpenDota jest wyłączona", "OpenDota sync is off", "Синхронизация OpenDota выключена", "Синхронізацію OpenDota вимкнено"],
  "err_match_not_watched": ["Nie ma meczu w obserwowanej historii", "That match isn't in the watched history", "Этого матча нет в истории", "Цього матчу немає в історії"],
  "err_unknown_endpoint": ["Nieznany endpoint", "Unknown endpoint", "Неизвестный endpoint", "Невідомий endpoint"],
  "err_bad_friend_id": ["Podaj prawidłowe Friend ID lub link do profilu", "Enter a valid Friend ID or profile link", "Укажите верный Friend ID или ссылку на профиль", "Вкажіть правильний Friend ID або посилання на профіль"],
  "err_opendota_down": ["OpenDota nie odpowiada", "OpenDota isn't answering", "OpenDota не отвечает", "OpenDota не відповідає"],
  "err_opendota_unknown_player": ["OpenDota nie rozpoznaje gracza", "OpenDota doesn't know this player", "OpenDota не знает этого игрока", "OpenDota не знає цього гравця"],
  "err_already_watched": ["Gracz jest już obserwowany", "This player is already watched", "Игрок уже отслеживается", "Гравець уже відстежується"],
  "err_no_player_id": ["Brak ID gracza", "Missing player ID", "Нет ID игрока", "Немає ID гравця"],
  "err_setting_unavailable": ["Ustawienie niedostępne", "Setting unavailable", "Настройка недоступна", "Налаштування недоступне"],
  "err_bad_enum_value": ["Nieprawidłowa wartość z listy", "Invalid value for this list", "Неверное значение из списка", "Невірне значення зі списку"],
  "err_bool_expected": ["Oczekiwano true/false", "Expected true/false", "Ожидалось true/false", "Очікувалося true/false"],
  "err_bad_setting_value": ["Nieprawidłowa wartość ustawienia", "Invalid setting value", "Неверное значение настройки", "Невірне значення налаштування"],
  "err_unknown_action": ["Nieznana operacja", "Unknown operation", "Неизвестная операция", "Невідома операція"],
  "err_operation_running": ["Dla tej instancji trwa już operacja", "An operation is already running on this instance", "На этом инстансе уже идёт операция", "На цьому інстансі вже триває операція"],
  "err_confirm_required": ["Potwierdź operację", "Confirm the operation", "Подтвердите операцию", "Підтвердіть операцію"],
  "err_bad_console_command": ["Komenda musi być pojedynczą linią (maks. 200 znaków)", "The command must be a single line (max 200 characters)", "Команда должна быть одной строкой (до 200 символов)", "Команда має бути одним рядком (до 200 символів)"],
  "err_items_too_big": ["Lista przedmiotów jest za duża", "The item list is too big", "Список предметов слишком большой", "Список предметів завеликий"],
  "err_items_unavailable": ["Nie można pobrać listy przedmiotów", "Can't fetch the item list", "Не удаётся получить список предметов", "Не вдається отримати список предметів"],
  "err_bad_match_id": ["Nieprawidłowe ID meczu", "Invalid match ID", "Неверный ID матча", "Невірний ID матчу"],
  "err_opendota_too_big": ["Odpowiedź OpenDota jest za duża", "The OpenDota reply is too big", "Ответ OpenDota слишком большой", "Відповідь OpenDota завелика"],
  "err_opendota_unavailable": ["OpenDota jest obecnie niedostępna", "OpenDota is unavailable right now", "OpenDota сейчас недоступна", "OpenDota зараз недоступна"]
};
const LANG_ORDER = ['pl', 'en', 'ru', 'uk'];
const LOCALES = { pl: 'pl-PL', en: 'en-GB', ru: 'ru-RU', uk: 'uk-UA' };

const tg = window.Telegram?.WebApp;
const root = document.querySelector('#app');
const modalRoot = document.querySelector('#modal-root');
const conn = document.querySelector('#connection');
const toastBox = document.querySelector('#toast');
const state = {
  me: null, dota: null, amp: null, tab: 'dota', server: null, serverTab: 'overview',
  settings: {}, search: '', player: 'all', outcome: 'all', loading: false,
  busy: false, lastUpdate: null,
};
let toastTimer;
// Until /api/me says which language the user picked in the bot, guess from the Telegram app's language.
let lang = pickLang(tg?.initDataUnsafe?.user?.language_code);

function pickLang(code) {
  const short = String(code || '').slice(0, 2).toLowerCase();
  return LANG_ORDER.includes(short) ? short : 'en';
}
function t(key, vars = {}) {
  const row = STRINGS[key];
  const text = row ? row[LANG_ORDER.indexOf(lang)] : key;
  return text.replace(/\{(\w+)\}/g, (whole, name) => (name in vars ? String(vars[name]) : whole));
}
function locale() { return LOCALES[lang]; }
function applyLanguage(code) {
  lang = pickLang(code);
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-t]').forEach(n => { n.textContent = t(n.dataset.t); });
  const reload = document.querySelector('#reload');
  reload.title = t('reload'); reload.setAttribute('aria-label', t('reload'));
}

function el(tag, className = '', text = null) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== null && text !== undefined) n.textContent = String(text);
  return n;
}
function add(parent, ...children) {
  for (const child of children.flat()) if (child !== null && child !== undefined) parent.append(child);
  return parent;
}
function btn(label, callback, className = 'btn') {
  const n = el('button', className, label);
  n.type = 'button';
  n.addEventListener('click', callback);
  return n;
}
function field(label, input) {
  const holder = el('div', 'field');
  const l = el('label', '', label);
  input.id = `f-${Math.random().toString(36).slice(2)}`;
  l.htmlFor = input.id;
  return add(holder, l, input);
}
// Enter in a one-line field does what the dialog's main button does.
function submitOnEnter(input, button) {
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); button.click(); }
  });
  return button;
}
// Follow the Telegram app: its light theme gets the light palette (style.css), anything else the dark one.
function applyScheme() {
  const light = tg?.colorScheme === 'light';
  document.documentElement.dataset.scheme = light ? 'light' : 'dark';
  tg?.setBackgroundColor?.(light ? 'secondary_bg_color' : '#0d1117');
  tg?.setHeaderColor?.(light ? 'secondary_bg_color' : '#0d1117');
}
function notice(text, error = false) {
  clearTimeout(toastTimer);
  toastBox.textContent = text;
  toastBox.style.borderColor = error ? '#9a484a' : '';
  toastBox.classList.add('visible');
  toastTimer = setTimeout(() => toastBox.classList.remove('visible'), 3200);
  if (error) tg?.HapticFeedback?.notificationOccurred('error');
}
function dateLabel(seconds) {
  if (!seconds) return t('no_date');
  return new Intl.DateTimeFormat(locale(), { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(seconds * 1000));
}
function duration(seconds) {
  if (!Number.isFinite(Number(seconds))) return '—';
  const x = Math.max(0, Math.round(seconds));
  return `${Math.floor(x / 60)}:${String(x % 60).padStart(2, '0')}`;
}
function percent(x) { return typeof x === 'number' && Number.isFinite(x) ? `${Math.round(x)}%` : '—'; }
function safeNum(x, fallback = '—') { return x == null ? fallback : Number(x).toLocaleString(locale()); }
function rankName(tier) {
  if (!tier) return t('rank_unknown');
  const names = {1:'Herald',2:'Guardian',3:'Crusader',4:'Archon',5:'Legend',6:'Ancient',7:'Divine',8:'Immortal'};
  const n = Number(tier);
  return (names[Math.floor(n/10)] || t('rank')) + (n < 80 ? ` ${n%10 || ''}` : '');
}
function modeName(m) {
  const names = { 1: 'All Pick', 2: 'Captains Mode', 3: 'Random Draft', 4: 'Single Draft', 22: 'All Pick', 23: 'Turbo' };
  return `${names[m.game_mode] || t('mode', { n: m.game_mode ?? '?' })}${m.lobby_type === 7 ? ' • Ranked' : ''}`;
}
function requestId() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  const arr = new Uint8Array(16);
  crypto.getRandomValues(arr);
  return Array.from(arr, b => b.toString(16).padStart(2, '0')).join('');
}
function errorText(code, status) {
  if (code && STRINGS[`err_${code}`]) return t(`err_${code}`);
  return code || t('http_error', { status });
}
async function api(path, data) {
  const opts = { method: data === undefined ? 'GET' : 'POST', cache: 'no-store',
    headers: { 'X-Telegram-Init-Data': tg?.initData || '' }, signal: AbortSignal.timeout(55000) };
  if (data !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(data);
  }
  let response;
  try { response = await fetch(path, opts); }
  catch (e) { throw new Error(e.name === 'TimeoutError' ? t('timeout') : t('offline')); }
  const json = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errorText(json.error, response.status));
  return json;
}
function setConnection(ok, label) {
  conn.classList.toggle('online', ok);
  conn.classList.toggle('error', !ok);
  conn.querySelector('span:last-child').textContent = label;
}
function closeModal() {
  modalRoot.replaceChildren();
  tg?.BackButton?.hide();
  syncBackButton();
}
function modal(title, subtitle = '') {
  closeModal();
  const scrim = el('div', 'modal-scrim');
  const box = el('div', 'modal');
  const close = btn('✕', closeModal, 'modal-close');
  add(box, close, el('h2', '', title));
  if (subtitle) add(box, el('p', 'modal-sub', subtitle));
  add(scrim, box);
  scrim.addEventListener('click', event => { if (event.target === scrim) closeModal(); });
  modalRoot.append(scrim);
  tg?.BackButton?.show();
  return box;
}
function syncBackButton() {
  if (!tg?.BackButton) return;
  if (modalRoot.children.length || state.server) tg.BackButton.show();
  else tg.BackButton.hide();
}
function goBack() {
  if (modalRoot.children.length) return closeModal();
  if (state.server) { state.server = null; state.serverTab = 'overview'; render(); }
}
function section(parent, title, actionText = null, action = null) {
  const line = el('div', 'section-header');
  line.append(el('h2', 'section-title', title));
  if (actionText) line.append(btn(actionText, action, 'section-action'));
  parent.append(line);
}
function stat(value, label, tone = '') {
  const box = el('div', 'stat');
  add(box, el('div', 'num ' + tone, value), el('div', 'desc', label));
  return box;
}
function empty(title, detail, symbol = '◈') {
  const box = el('div', 'empty');
  return add(box, el('div', 'symbol', symbol), el('strong', '', title), el('div', '', detail));
}
function heroPortrait(m) {
  const box = el('div', 'hero-portrait', '✦');
  if (m.hero_slug && /^[a-z0-9_]+$/.test(m.hero_slug)) {
    const img = el('img');
    img.alt = m.hero_name || '';
    img.loading = 'lazy';
    img.referrerPolicy = 'no-referrer';
    img.src = `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/${m.hero_slug}.png`;
    img.addEventListener('error', () => img.remove());
    box.append(img);
  }
  return box;
}
function opName(op) { return STRINGS[`act_${op}`] ? t(`act_${op}`) : String(op); }
function setTab(name) {
  state.tab = name;
  state.server = null;
  state.search = '';
  document.querySelectorAll('.nav-btn').forEach(n => n.classList.toggle('active', n.dataset.tab === name));
  render();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function render() {
  if (!state.me) return;
  root.replaceChildren();
  if (state.server) renderServer();
  else if (state.tab === 'dota' && state.me.admin) renderDota();
  else renderAmp();
  syncBackButton();
}

/* --- Dota 2 --- */
function renderDota() {
  const data = state.dota || { players: [], matches: [], totals: {}, notifications: true };
  const hero = el('div', 'hero');
  add(hero, el('div', 'section-kicker', 'MATCH INTELLIGENCE'), el('h1', '', t('dota_title')),
    el('p', '', t('dota_lead')));
  root.append(hero);
  const summaries = data.matches || [];
  const wins = summaries.filter(x => x.win).length;
  const stats = el('div', 'stats-row');
  add(stats, stat(data.players.length, t('st_watched')),
    stat(summaries.length, t('st_matches')),
    stat(summaries.length ? `${Math.round(100 * wins / summaries.length)}%` : '—', t('st_winrate'), 'green'));
  root.append(stats, notificationSwitch(data));
  section(root, t('watched_players'), t('add'), showWatchModal);
  const profiles = el('div', 'profile-list');
  if (!data.players.length) profiles.append(empty(t('nobody_watched'), t('nobody_watched_hint'), '🎯'));
  for (const p of data.players) profiles.append(playerCard(p, data.totals?.[p.account_id]));
  root.append(profiles);
  section(root, t('match_history'), t('refresh'), () => refresh(true));
  const filters = el('div', 'filters');
  const players = [{ value: 'all', name: t('all_players') }, ...data.players.map(p => ({ value: String(p.account_id), name: p.name }))];
  for (const p of players) filters.append(btn(p.name, () => { state.player = p.value; render(); },
    'chip' + (state.player === p.value ? ' active' : '')));
  root.append(filters);
  const results = el('div', 'filters');
  for (const [value, label] of [['all', t('all_results')], ['win', t('wins')], ['loss', t('losses')]]) {
    results.append(btn(label, () => { state.outcome = value; render(); },
      'chip' + (state.outcome === value ? ' active' : '')));
  }
  root.append(results);
  const visible = summaries.filter(m => (state.player === 'all' || String(m.account_id) === state.player)
    && (state.outcome === 'all' || (state.outcome === 'win') === m.win));
  const matches = el('div', 'match-list');
  if (!visible.length) matches.append(empty(t('no_matches_filter'), t('no_matches_hint'), '▤'));
  for (const m of visible.slice(0, 250)) matches.append(matchCard(m));
  root.append(matches);
}
// Right under the numbers: whether the bot also posts each new match in the chat (the panel keeps them either way).
function notificationSwitch(data) {
  const toggle = el('div', 'panel spaced switch-row');
  const label = add(el('div'), el('strong', '', t('notif_title')), el('div', 'sub', t('notif_hint')));
  const turn = btn(data.notifications ? t('notif_on') : t('notif_off'), async () => {
    try { await api('/api/dota/notifications', { enabled: !data.notifications });
      data.notifications = !data.notifications; notice(t('notif_changed')); render(); }
    catch (e) { notice(e.message, true); }
  }, 'btn small' + (data.notifications ? ' on' : ''));
  turn.setAttribute('aria-pressed', String(Boolean(data.notifications)));
  return add(toggle, label, turn);
}
function playerCard(p, total = {}) {
  const box = el('div', 'profile');
  const avatar = el('div', 'avatar', (p.name || '?').slice(0, 1).toUpperCase());
  const center = el('div', 'content');
  const wr = total.total ? t('pct_wins', { pct: Math.round(total.wins / total.total * 100) }) : t('no_matches');
  add(center, el('strong', '', p.name), el('div', 'sub', `${rankName(p.rank_tier)} • ${wr}${p.public === 0 ? ` • ${t('no_public')}` : ''}`));
  const actions = el('div', 'profile-actions');
  add(actions, btn(t('matches_btn'), () => { state.player = String(p.account_id); state.outcome = 'all'; render();
    document.querySelector('.match-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 'btn small'),
  btn('✕', () => removePlayer(p), 'ghost'));
  return add(box, avatar, center, actions);
}
function matchCard(m) {
  const box = el('button', 'match'); box.type = 'button';
  const content = el('div', 'match-content');
  add(content, add(el('div', 'match-top'), el('strong', '', m.hero_name)),
    add(el('div', 'match-bottom'), el('span', '', m.player_name), el('span', '', '·'),
      el('span', '', dateLabel(m.start_time)), el('span', '', '·'), el('span', '', duration(m.duration))));
  const right = el('div', 'match-right');
  add(right, el('span', `badge ${m.win ? 'win' : 'loss'}`, m.win ? t('victory') : t('defeat')),
    el('span', 'muted', `${m.kills ?? 0}/${m.deaths ?? 0}/${m.assists ?? 0} KDA`));
  add(box, heroPortrait(m), content, right);
  box.addEventListener('click', () => openMatch(m));
  return box;
}
function showWatchModal() {
  const box = modal(t('watch_title'), t('watch_hint'));
  const input = el('input'); input.placeholder = t('example_id'); input.autocomplete = 'off';
  box.append(field('Dota Friend ID / URL', input));
  box.append(submitOnEnter(input, btn(t('watch_add'), async () => {
    const id = input.value.trim();
    if (!id) return notice(t('enter_id'), true);
    try { await api('/api/dota/watch', { account_id: id, request_id: requestId() });
      closeModal(); notice(t('added')); await refresh(); }
    catch (e) { notice(e.message, true); }
  }, 'btn btn-primary full')));
  input.focus();
}
function removePlayer(p) {
  const box = modal(t('remove_q', { name: p.name }), t('remove_hint'));
  add(box, btn(t('remove'), async () => {
    try { await api('/api/dota/unwatch', { account_id: p.account_id, request_id: requestId() });
      if (state.player === String(p.account_id)) state.player = 'all';
      closeModal(); notice(t('removed')); await refresh(); }
    catch (e) { notice(e.message, true); }
  }, 'btn btn-danger full'), btn(t('cancel'), closeModal, 'btn full'));
}
async function openMatch(m) {
  const box = modal(`${m.hero_name} • ${m.win ? t('won') : t('lost')}`,
    `${m.player_name} • ${dateLabel(m.start_time)} • ${modeName(m)} • ${duration(m.duration)}`);
  box.append(add(el('div', 'stats-row'), stat(`${m.kills ?? 0}/${m.deaths ?? 0}/${m.assists ?? 0}`, 'K / D / A'),
    stat(safeNum(m.gpm), 'GPM'), stat(safeNum(m.xpm), 'XPM')));
  const loading = el('p', 'muted tiny', t('loading_match')); box.append(loading);
  const link = el('a', 'btn full spaced', t('open_opendota'));
  link.href = `https://www.opendota.com/matches/${m.match_id}`;
  link.target = '_blank'; link.rel = 'noopener noreferrer';
  box.append(link);
  try {
    const [result, itemData] = await Promise.all([
      api(`/api/dota/matches/${m.match_id}`),
      api('/api/dota/items').catch(() => ({ items: {} })),
    ]);
    const items = itemData.items || {};
    if (!box.isConnected) return;
    const table = el('div');
    const teams = [{ team: 'Radiant', members: result.players.filter(x => Number(x.player_slot) < 128), score: result.radiant_score },
      { team: 'Dire', members: result.players.filter(x => Number(x.player_slot) >= 128), score: result.dire_score }];
    for (const tm of teams) {
      const h = el('div', 'team-bar');
      add(h, el('span', tm.team === 'Radiant' ? 'green' : 'red', tm.team), el('span', '', t('team_kills', { n: safeNum(tm.score) })));
      table.append(h);
      if (!tm.members.length) table.append(el('div', 'sub', t('no_team_data')));
      for (const p of tm.members) {
        const h = state.dota?.heroes?.[String(p.hero_id)] || {};
        const name = el('strong', '', p.personaname || h.name || `Hero #${p.hero_id || '?'}`);
        const info = el('div', 'sub', `${h.name || t('hero_n', { id: p.hero_id || '?' })} · GPM ${safeNum(p.gold_per_min)}`);
        const itemLine = el('div', 'item-strip');
        for (const id of [p.item_0, p.item_1, p.item_2, p.item_3, p.item_4, p.item_5]) {
          if (!Number(id)) continue;
          const item = items[String(id)] || {};
          const holder = el('span', 'item-icon', String(id)); holder.title = item.name || `Item #${id}`;
          if (item.img && /^\/apps\/dota2\/images\/[a-z0-9_/-]+\.png$/.test(item.img)) {
            const img = el('img'); img.loading = 'lazy'; img.alt = item.name || '';
            img.referrerPolicy = 'no-referrer';
            img.src = 'https://cdn.cloudflare.steamstatic.com' + item.img;
            img.addEventListener('error', () => img.remove()); holder.append(img);
          }
          itemLine.append(holder);
        }
        table.append(add(el('div', 'player-score'), add(el('div'), name, info, itemLine),
          el('span', 'score', `${p.kills ?? '—'}/${p.deaths ?? '—'}/${p.assists ?? '—'}`)));
      }
    }
    loading.replaceWith(table);
  } catch (e) { loading.textContent = e.message; }
}

/* --- AMP --- */
function renderAmp() {
  const header = el('div', 'hero amp-hero');
  add(header, el('div', 'section-kicker', 'CUBECODERS AMP'), el('h1', '', t('amp_title')),
    el('p', '', t('amp_lead')));
  root.append(header);
  const instances = state.amp?.instances || [];
  const active = instances.filter(i => i.running && i.state === 20).length;
  const metrics = el('div', 'stats-row');
  add(metrics, stat(instances.length, t('st_instances')), stat(active, t('st_games_online'), 'green'),
    stat(instances.reduce((sum, i) => sum + (i.players || 0), 0), t('st_players_online')));
  root.append(metrics);
  section(root, t('your_servers'), t('refresh'), () => refresh(true));
  const list = el('div', 'server-list');
  if (state.amp?.error) list.append(empty(t('amp_down'), state.amp.error, '⚠'));
  else if (state.amp && !state.amp.configured) list.append(empty(t('amp_unconfigured'),
    t('amp_unconfigured_hint'), '▣'));
  else if (!instances.length) list.append(empty(t('no_instances'),
    t('no_instances_hint'), '▣'));
  for (const inst of instances) list.append(serverCard(inst));
  root.append(list);
}
function metricLabel(m, isMemory = false) {
  if (!m || !Number.isFinite(Number(m.raw))) return t('no_data');
  if (!isMemory) return `${percent(m.pct)}`;
  const factor = (m.units || '').toUpperCase().startsWith('GB') ? 1 : 1024;
  return `${(m.raw / factor).toFixed(1)} GB${m.max ? ` / ${(m.max / factor).toFixed(1)} GB` : ''}`;
}
function meter(m, name, mem = false) {
  const outer = el('div');
  const label = el('div', 'meter-label');
  add(label, el('span', '', name), el('span', '', metricLabel(m, mem)));
  const progress = el('div', 'progress');
  const bar = el('i');
  bar.style.width = `${Math.min(100, Math.max(0, Number(m?.pct) || 0))}%`;
  progress.append(bar);
  return add(outer, label, progress);
}
function serverCard(inst) {
  const card = el('button', 'server-card'); card.type = 'button';
  const heading = el('div', 'server-header');
  const title = el('div', 'server-name');
  add(title, el('strong', '', inst.friendly || inst.name), el('div', 'sub', `${inst.module || t('game')} • ${t('n_online', { n: inst.players || 0 })}`));
  add(heading, el('div', 'server-icon', '▣'), title,
    el('span', `badge ${inst.busy ? 'busy' : inst.running && inst.state === 20 ? 'running' : 'stopped'}`,
      inst.busy ? t('badge_busy') : inst.running && inst.state === 20 ? t('badge_online') : inst.running ? t('badge_ready') : t('badge_offline')));
  add(card, heading, add(el('div', 'meter-row'), meter(inst.cpu, 'CPU'), meter(inst.mem, 'RAM', true)));
  card.addEventListener('click', () => { state.server = inst.name; state.serverTab = 'overview';
    state.search = ''; render(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
  return card;
}
function renderServer() {
  const inst = state.amp?.instances?.find(i => i.name === state.server);
  const header = el('div', 'breadcrumb');
  add(header, btn('‹', goBack, 'back'), el('h2', '', inst?.friendly || state.server));
  root.append(header);
  if (!inst) { root.append(empty(t('inst_gone'), t('inst_gone_hint'))); return; }
  const banner = el('div', 'panel');
  const label = el('div', 'section-kicker', t('inst_status'));
  const status = el('h2', '', inst.state_text || t('unknown')); status.style.margin = '9px 0';
  add(banner, label, status, el('div', 'sub', `${inst.module || t('game')} • ${t('n_players_online', { n: inst.players || 0 })}`));
  if (inst.busy) add(banner, el('p', 'gold tiny live', t('op_running', { op: opName(inst.busy) })));
  root.append(banner);
  const tabs = el('div', 'tabstrip');
  const choices = [['overview', t('tab_control')], ['players', t('tab_players')], ['settings', t('tab_settings')]];
  if (state.me.admin) choices.push(['console', t('tab_console')]);
  for (const [id, label] of choices) tabs.append(btn(label, () => {
    state.serverTab = id; render(); if (id === 'settings') ensureSettings(inst.name);
    if (id === 'players') loadPlayers(inst.name); if (id === 'console') loadConsole(inst.name);
  }, state.serverTab === id ? 'active' : ''));
  root.append(tabs);
  if (state.serverTab === 'overview') renderServerOverview(inst);
  if (state.serverTab === 'players') renderPlayers(inst);
  if (state.serverTab === 'settings') renderSettings(inst);
  if (state.serverTab === 'console' && state.me.admin) renderConsole(inst);
}
function renderServerOverview(inst) {
  root.append(add(el('div', 'stats-row'), stat(percent(inst.cpu?.pct), 'CPU'),
    stat(percent(inst.mem?.pct), 'RAM'), stat(inst.players ?? 0, t('tab_players'))));
  section(root, t('server_actions'));
  // Say why some buttons are grey before the user taps them.
  const why = inst.busy ? t('why_busy', { op: opName(inst.busy) }) :
    !inst.running ? t('why_off', { start: t('act_start'), on: t('act_on') }) : '';
  if (why) root.append(el('p', 'gold tiny why', why));
  const grid = el('div', 'actions-grid');
  const actions = [
    { id: 'start', icon: '▶' }, { id: 'stop', icon: '■', danger: true },
    { id: 'restart', icon: '↻', danger: true }, { id: 'on', icon: '⏻' },
    { id: 'off', icon: '◉', danger: true },
    { id: 'update', icon: '⇡', danger: true }, { id: 'backup', icon: '▤' }
  ];
  for (const a of actions) {
    a.label = t(`act_${a.id}`);
    const item = el('button', 'action-btn' + (a.danger ? ' danger' : '')); item.type = 'button';
    add(item, el('span', 'action-icon', a.icon), el('span', '', a.label));
    item.disabled = !!inst.busy || (!inst.running && !['start', 'on'].includes(a.id)) ||
      (inst.running && a.id === 'on');
    item.addEventListener('click', () => confirmAction(inst, a));
    grid.append(item);
  }
  root.append(grid);
  root.append(el('p', 'sub spaced', t('actions_hint')));
}
function confirmAction(inst, action) {
  const potentiallyDisruptive = ['stop', 'off', 'restart', 'update'].includes(action.id);
  const subtitle = potentiallyDisruptive ?
    t('confirm_disruptive', { action: action.label, inst: inst.friendly, n: inst.players || 0 }) :
    t('confirm_plain', { action: action.label, inst: inst.friendly });
  const box = modal(action.label + ' · ' + inst.friendly, subtitle);
  const hasPlayers = potentiallyDisruptive && !!inst.players && state.me.warn_seconds > 0;
  if (hasPlayers) box.append(el('p', 'gold tiny', t('warn_hint', { s: state.me.warn_seconds })));
  const choices = [];
  if (hasPlayers) choices.push({ label: t('warn_and_wait', { s: state.me.warn_seconds }), warn: true, css: 'btn btn-primary full' });
  choices.push({ label: potentiallyDisruptive ? t('run_now') : t('confirm'), warn: false,
    css: potentiallyDisruptive ? 'btn btn-danger full' : 'btn btn-primary full' });
  for (const choice of choices) box.append(btn(choice.label, async () => {
    const id = requestId();
    try { await api(`/api/amp/instances/${encodeURIComponent(inst.name)}/action`,
      { action: action.id, confirmed: true, warn: choice.warn, request_id: id });
      closeModal(); notice(t('queued', { action: action.label }));
      tg?.HapticFeedback?.notificationOccurred('success');
      state.watchUntil = Date.now() + 30000; await refresh(); }
    catch (e) { notice(e.message, true); }
  }, choice.css));
  box.append(btn(t('cancel'), closeModal, 'btn full'));
}
async function loadPlayers(name) {
  try { state.players = { name, loading: true }; render();
    const data = await api(`/api/amp/instances/${encodeURIComponent(name)}/players`);
    state.players = { name, list: data.players }; render(); }
  catch (e) { state.players = { name, error: e.message }; render(); }
}
function renderPlayers(inst) {
  section(root, t('st_players_online'), '↻', () => loadPlayers(inst.name));
  const data = state.players?.name === inst.name ? state.players : null;
  if (!data || data.loading) return root.append(empty(t('loading_players'), t('loading_players_hint'), '◌'));
  if (data.error) return root.append(empty(t('error'), data.error));
  const list = el('div', 'profile-list');
  if (!data.list?.length) list.append(empty(t('nobody_plays'), t('nobody_plays_hint'), '◉'));
  for (const name of data.list || []) {
    const item = el('div', 'profile');
    add(item, el('div', 'avatar', '◉'), el('strong', '', name));
    list.append(item);
  }
  root.append(list);
}
async function ensureSettings(name, force = false) {
  if (state.settings[name] && !force) return;
  state.settings[name] = { loading: true }; render();
  try { const data = await api(`/api/amp/instances/${encodeURIComponent(name)}/settings`);
    state.settings[name] = { groups: data.groups }; render(); }
  catch (e) { state.settings[name] = { error: e.message }; render(); }
}
function renderSettings(inst) {
  section(root, t('config'), '↻', () => ensureSettings(inst.name, true));
  const search = el('input', 'search-input'); search.placeholder = t('search_settings');
  search.value = state.search;
  search.addEventListener('input', event => { state.search = event.target.value; showSettingGroups(inst); });
  root.append(search);
  const container = el('div', 'spaced'); container.id = 'setting-groups'; root.append(container);
  showSettingGroups(inst);
}
function showSettingGroups(inst) {
  const target = document.querySelector('#setting-groups');
  if (!target) return;
  target.replaceChildren();
  const data = state.settings[inst.name];
  if (!data || data.loading) return target.append(empty(t('loading_settings'), t('loading_settings_hint'), '⚙'));
  if (data.error) return target.append(empty(t('config_error'), data.error));
  let found = 0;
  for (const group of data.groups || []) {
    const items = (group.items || []).filter(s =>
      `${s.name} ${s.node} ${s.desc}`.toLowerCase().includes(state.search.toLowerCase()));
    if (!items.length) continue;
    found += items.length;
    const details = el('details', 'setting-group'); details.open = Boolean(state.search.trim());
    details.append(el('summary', '', `${group.name} (${items.length})`));
    const body = el('div', 'setting-items');
    for (const s of items) {
      const item = el('div', 'setting-item');
      const main = add(el('div', 'setting-main'), el('strong', '', s.name),
        el('small', '', s.desc || s.node));
      const value = s.enum?.length ? s.enum.find(x => String(x[0]) === String(s.value))?.[1] || s.value : s.value;
      add(item, main, el('div', 'setting-val', String(value ?? '—')),
        btn(t('edit'), () => editSetting(inst.name, s), 'btn small'));
      body.append(item);
    }
    details.append(body); target.append(details);
  }
  if (!found) target.append(empty(t('no_settings'), t('no_settings_hint')));
}
function editSetting(name, setting) {
  const box = modal(setting.name, setting.desc || setting.node);
  let input;
  if (setting.enum?.length) {
    input = el('select');
    for (const [key, label] of setting.enum) {
      const opt = el('option', '', label); opt.value = String(key); input.append(opt);
    }
    input.value = String(setting.value ?? '');
  } else if (setting.type === 'checkbox') {
    input = el('select');
    for (const [value, label] of [['true', t('on')], ['false', t('off')]]) {
      const opt = el('option', '', label); opt.value = value; input.append(opt);
    }
    input.value = String(setting.value).toLowerCase() === 'true' ? 'true' : 'false';
  } else {
    input = el('input'); input.value = String(setting.value ?? '');
    input.maxLength = 1000;
  }
  box.append(field(t('value'), input));
  box.append(submitOnEnter(input, btn(t('save_setting'), async () => {
    try {
      await api(`/api/amp/instances/${encodeURIComponent(name)}/settings`,
        { node: setting.node, value: input.value, request_id: requestId() });
      closeModal(); notice(t('saved')); await ensureSettings(name, true);
    } catch (e) { notice(e.message, true); }
  }, 'btn btn-primary full')));
  box.append(btn(t('cancel'), closeModal, 'btn full'));
}
async function loadConsole(name) {
  state.console = { name, loading: true }; render();
  try { const data = await api(`/api/amp/instances/${encodeURIComponent(name)}/console`);
    state.console = { name, lines: data.lines }; render(); }
  catch (e) { state.console = { name, error: e.message }; render(); }
}
function renderConsole(inst) {
  section(root, t('tab_console'), '↻', () => loadConsole(inst.name));
  const data = state.console?.name === inst.name ? state.console : null;
  const output = el('pre', 'console', data?.loading ? t('loading') :
    data?.error || (data?.lines || []).join('\n') || t('no_console'));
  root.append(output);
  const input = el('input'); input.placeholder = t('console_placeholder'); input.autocomplete = 'off'; input.maxLength = 200;
  const f = field(t('console_label'), input);
  const submit = btn(t('send'), async () => {
    if (!input.value.trim()) return;
    try { const data = await api(`/api/amp/instances/${encodeURIComponent(inst.name)}/console`,
      { command: input.value, request_id: requestId() });
      notice(t('sent')); input.value = '';
      state.console = { name: inst.name, lines: data.lines }; render(); }
    catch (e) { notice(e.message, true); }
  }, 'btn btn-primary full');
  submitOnEnter(input, submit);
  add(root, f, submit, el('p', 'sub spaced', t('console_hint')));
  output.scrollTop = output.scrollHeight;  // newest lines in view
}

/* --- Bootstrap, polling and accessibility --- */
async function refresh(interactive = false) {
  if (state.busy) return;
  state.busy = true;
  if (interactive) document.querySelector('#reload').textContent = '◌';
  try {
    const me = await api('/api/me');
    state.me = me;
    if (me.lang && me.lang !== lang) applyLanguage(me.lang);
    if (!me.admin) {
      state.tab = 'amp';
      const tab = document.querySelector('[data-tab="dota"]');
      if (tab) tab.style.display = 'none';
    }
    const tasks = [api('/api/amp/instances')];
    if (me.admin) tasks.push(api('/api/dota'));
    const [ampResult, dotaResult] = await Promise.allSettled(tasks);
    state.amp = ampResult.status === 'fulfilled' ? ampResult.value :
      { configured: false, instances: [], error: ampResult.reason?.message || t('amp_conn_lost') };
    if (me.admin) {
      if (dotaResult?.status === 'fulfilled') state.dota = dotaResult.value;
      else if (!state.dota) state.dota = { players: [], matches: [], totals: {}, notifications: true };
    }
    noteFinished(state.amp.instances || []);
    state.lastUpdate = new Date();
    setConnection(true, t('connected', { name: me.name,
      time: new Intl.DateTimeFormat(locale(), { hour: '2-digit', minute: '2-digit' }).format(state.lastUpdate) }));
    document.querySelectorAll('.nav-btn').forEach(n => n.classList.toggle('active', n.dataset.tab === state.tab));
    render();
    if (interactive) notice(t('refreshed'));
  } catch (e) {
    if (!state.me) root.replaceChildren(empty(t('cant_open'), e.message,
      '⚠'));
    setConnection(false, e.message);
    if (interactive) notice(e.message, true);
  } finally {
    state.busy = false;
    document.querySelector('#reload').textContent = '↻';
    scheduleProgress();
  }
}
// While an operation runs (or for 30 s after one was started) the server list is re-read every 3 s, so the
// badge and the banner move on their own and the end of the operation shows up here, not only in the chat.
let progressTimer = null;
function scheduleProgress() {
  clearTimeout(progressTimer);
  const running = (state.amp?.instances || []).some(i => i.busy);
  if (running || Date.now() < (state.watchUntil || 0)) progressTimer = setTimeout(pollProgress, 3000);
}
async function pollProgress() {
  if (state.busy || document.visibilityState !== 'visible') return scheduleProgress();
  try {
    const amp = await api('/api/amp/instances');
    state.amp = amp;
    noteFinished(amp.instances || []);
    if (!interacting()) render();
  } catch (e) { /* the 20 s refresh reports connection problems */ }
  scheduleProgress();
}
function noteFinished(instances) {
  const before = state.running || {};
  state.running = Object.fromEntries(instances.filter(i => i.busy).map(i => [i.name, i.busy]));
  for (const [name, op] of Object.entries(before)) {
    if (state.running[name]) continue;
    const inst = instances.find(i => i.name === name);
    if (!inst) continue;  // AMP didn't answer this time: no news, not "finished"
    notice(t('op_done', { inst: inst.friendly || name, op: opName(op) }));
    tg?.HapticFeedback?.notificationOccurred('success');
    state.watchUntil = 0;
  }
}
// Re-rendering would steal focus, typed text or an open dialog.
function interacting() {
  return modalRoot.children.length > 0 ||
    Boolean(state.server && ['settings', 'console'].includes(state.serverTab)) ||
    Boolean(document.activeElement?.matches('input,textarea,select'));
}
function start() {
  applyLanguage(lang);
  tg?.ready(); tg?.expand();
  applyScheme();
  tg?.onEvent?.('themeChanged', applyScheme);
  tg?.BackButton?.onClick(goBack);
  document.querySelector('#reload').addEventListener('click', () => refresh(true));
  document.querySelectorAll('[data-tab]').forEach(n => n.addEventListener('click', () => {
    if (n.dataset.tab === 'dota' && state.me && !state.me.admin) return;
    setTab(n.dataset.tab);
  }));
  if (!tg?.initData) {
    root.replaceChildren(empty(t('open_via_tg'), t('open_via_tg_hint'), '◈'));
    setConnection(false, t('no_session'));
    return;
  }
  refresh();
  setInterval(() => {
    // Keep focus, text edits and expanded settings groups stable while interacting.
    if (document.visibilityState !== 'visible' || interacting()) return;
    refresh();
  }, 20000);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && !interacting() &&
        Date.now() - (state.lastUpdate?.getTime() || 0) > 30000) refresh();
  });
}
start();
