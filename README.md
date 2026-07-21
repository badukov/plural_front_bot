# Plural Front Telegram Bot

Telegram-бот для локального фронт-трекинга по экспорту Simply Plural.

## Возможности

Для админов:

- **Фронт** — поиск личности и постановка на фронт.
- **Снять с фронта** — снятие конкретной личности с текущего фронта.
- **Блюр** — очистка фронта.
- **Инфо о фронте** — подробная информация обо всех текущих фронтерах.
- **История** — последние изменения фронта со временем в локальном формате Telegram и кнопкой статистики.
- **Справочник** — просмотр всех личностей, поиск, фильтр по категориям и быстрые действия с фронтом для админов.
- **Оповещения** — включение и выключение рассылки о смене фронта.
- **Управление личностями** — импорт из Florality и JSON-экспорт базы.

Для обычных пользователей:

- **Инфо о фронте**.
- **Оповещения**.
- **История**.
- **Справочник** — просмотр всех личностей, поиск и фильтр по категориям без управления фронтом.
- Поиск по имени обычным текстовым сообщением.

Бот автоматически выбирает язык интерфейса по языку Telegram-профиля и запоминает его для персональных оповещений. Поддерживаются русский, английский и итальянский. Для диагностики язык можно принудительно переключить командами `/language ru`, `/language en`, `/language it`, а `/language auto` возвращает автоматический выбор; отдельная кнопка для этого не добавляется.

Опционально бот может использовать Florality как основную базу личностей: локальная SQLite-база становится копией для Telegram-поиска, фронта и уведомлений. Синхронизация включается только при наличии ключа в `.env`.

## Быстрый запуск на Windows

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python bot.py
```

В `.env` укажите:

```env
BOT_TOKEN=токен_бота
ADMIN_IDS=123456789
DATABASE_PATH=data/bot.sqlite3
AUTO_IMPORT_ON_START=false
```

Для Florality добавьте, если нужно:

```env
FLORALITY_SYNC_ENABLED=true
FLORALITY_SYNC_FRONT_ENABLED=true
FLORALITY_PULL_FRONT_ENABLED=true
FLORALITY_PULL_INTERVAL_SECONDS=60
FLORALITY_HISTORY_PULL_INTERVAL_SECONDS=900
FLORALITY_HISTORY_ACTIVE_DAYS=30
FLORALITY_HISTORY_PAGE_DELAY_SECONDS=1.1
FLORALITY_CREATE_MISSING_MEMBERS_ENABLED=false
FLORALITY_AVATAR_BATCH_SIZE=25
FLORALITY_AVATAR_DELAY_SECONDS=1
FLORALITY_CATEGORY_BATCH_SIZE=25
FLORALITY_CATEGORY_DELAY_SECONDS=1
FLORALITY_API_TOKEN=flv1_...
FLORALITY_API_BASE_URL=https://api.floralitys.com/api/v1
```

Ключу нужны права на чтение/запись members и front, а для загрузки категорий — права на чтение groups и groupLayout. Если у ключа пока нет прав на запись front, можно временно поставить `FLORALITY_SYNC_FRONT_ENABLED=false`: бот не будет отправлять фронт во Florality. Импорт запускается вручную через **Управление личностями → Импорт из Florality**: однозначные совпадения связываются по имени без перезаписи локальных данных, неоднозначные совпадения пропускаются, а действительно отсутствующие личности импортируются вместе с аватарами. Администратор может открыть это меню основной кнопкой, из главной страницы справочника или командой `/manage`; его Telegram ID должен присутствовать в `ADMIN_IDS`. Перед первой записью база копируется в `data/backups` с датой в имени файла; скачанные аватары сохраняются в `data/avatars/florality`. Отдельная кнопка загрузки аватаров автоматически проходит все недостающие файлы пачками по `FLORALITY_AVATAR_BATCH_SIZE`, последовательно, с паузой `FLORALITY_AVATAR_DELAY_SECONDS` и обновлением прогресса после каждой пачки; уже доступные аватары не запрашиваются повторно. Кнопка загрузки категорий читает group layout порциями по `FLORALITY_CATEGORY_BATCH_SIZE` групп с паузой `FLORALITY_CATEGORY_DELAY_SECONDS`, сопоставляет полные пути и только добавляет отсутствующие категории личностям, созданным импортом Florality. Если фронт меняют во Florality, бот проверяет `GET /front` раз в `FLORALITY_PULL_INTERVAL_SECONDS` секунд; если фронтер ещё не найден локально, бот импортирует эту личность из ответа Florality и обновляет локальный фронт. Новые личности во Florality автоматически не создаются, пока `FLORALITY_CREATE_MISSING_MEMBERS_ENABLED=false`. Бот хранит локальное соответствие `member_id` к Florality ID в отдельной служебной таблице и не меняет структуру Simply Plural-данных.

Загрузка категорий после одного нажатия автоматически проходит все сопоставленные группы пачками по `FLORALITY_CATEGORY_BATCH_SIZE`, обновляя прогресс между пачками. Если API временно не ответил, бот оставляет кнопку продолжения с безопасной позиции.

Администраторы, которые запускали бота и оставили уведомления включёнными, получают напоминание проверить актуальность фронта каждые два часа: в 06:30, 08:30, ..., 22:30 по московскому времени. С 00:00 до 06:30 напоминаний нет.

## Запуск на Linux / VPS

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

git clone https://github.com/badukov/plural_front_bot.git
cd plural_front_bot

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env
python3 bot.py
```

Локальные файлы окружения и данные передаются на сервер отдельно от Git:

```bash
mkdir -p data
```

С Windows можно передать базу так:

```powershell
scp E:\Tools\plural_front_bot\data\bot.sqlite3 admin@SERVER:~/plural_front_bot/data/bot.sqlite3
```

## Systemd

Создайте сервис:

```bash
sudo nano /etc/systemd/system/plural-front-bot.service
```

Пример:

```ini
[Unit]
Description=Plural Front Telegram Bot
After=network.target

[Service]
WorkingDirectory=/home/admin/plural_front_bot
ExecStart=/home/admin/plural_front_bot/.venv/bin/python /home/admin/plural_front_bot/bot.py
Restart=always
RestartSec=5
User=admin

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable plural-front-bot
sudo systemctl start plural-front-bot
sudo systemctl status plural-front-bot
```

Логи:

```bash
journalctl -u plural-front-bot -f
```

## Обновление

```bash
cd ~/plural_front_bot
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart plural-front-bot
```

## Импорт Simply Plural

Автоимпорт при старте:

```env
SP_EXPORT_PATH=data/simply_plural_export.json
AUTO_IMPORT_ON_START=true
```

Ручной импорт:

```bash
python -m app.import_sp data/simply_plural_export.json --db data/bot.sqlite3
```

## Проверка

```bash
python tools/check_db.py
python tools/sanity_checks.py
```

На Linux вместо `python` может использоваться `python3`.

## Данные

Основные таблицы Simply Plural не требуют миграций для обычной работы. При импорте из Florality однозначно совпавшие личности получают только служебную связь ID, неоднозначные совпадения пропускаются, а отсутствующие локально личности добавляются вместе с доступными аватарами; остальные расхождения показываются в Telegram-сообщении.

История фронта хранится отдельно в SQLite как сжатые gzip+base64 JSON-снимки текущего фронта после каждого изменения. Дополнительно бот при первом запуске постепенно загружает историю сессий Florality, затем раз в `FLORALITY_HISTORY_PULL_INTERVAL_SECONDS` перепроверяет последние `FLORALITY_HISTORY_ACTIVE_DAYS` дней и обновляет сессии по их стабильному Florality ID — поэтому исправленное задним числом время не создаёт дубль. Завершённые сессии старше активного окна переносятся в архивную таблицу SQLite, но не удаляются. Кнопка статистики показывает последние 30 дней; команды `/stats 90` и `/stats all` читают в том числе архив. В сообщениях истории используется встроенный Telegram-формат времени, поэтому клиент показывает дату и время в привычном для пользователя виде.
