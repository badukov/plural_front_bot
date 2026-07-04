# Plural Front Telegram Bot

Telegram-бот для локального фронт-трекинга по экспорту Simply Plural.

## Возможности

Для админов:

- **Фронт** — поиск личности и постановка на фронт.
- **Снять с фронта** — снятие конкретной личности с текущего фронта.
- **Блюр** — очистка фронта.
- **Инфо о фронте** — подробная информация обо всех текущих фронтерах.
- **Справочник** — просмотр всех личностей, поиск, фильтр по категориям и быстрые действия с фронтом для админов.
- **Оповещения** — включение и выключение рассылки о смене фронта.
- **Управление личностями** — импорт из Florality и JSON-экспорт базы.

Для обычных пользователей:

- **Инфо о фронте**.
- **Справочник**.
- **Оповещения**.
- Поиск по имени обычным текстовым сообщением.

Бот автоматически выбирает язык интерфейса по языку Telegram-профиля и запоминает его для персональных оповещений. Поддерживаются русский, английский и итальянский.

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
FLORALITY_CREATE_MISSING_MEMBERS_ENABLED=false
FLORALITY_API_TOKEN=flv1_...
FLORALITY_API_BASE_URL=https://api.floralitys.com/api/v1
```

Ключу нужны права на чтение/запись members и front. Если у ключа пока нет прав на запись front, можно временно поставить `FLORALITY_SYNC_FRONT_ENABLED=false`: бот не будет отправлять фронт во Florality. Проверка запускается вручную через **Управление личностями → Импорт из Florality**: бот показывает имена записей, которые отличаются, отсутствуют локально или отсутствуют в активном списке Florality. В SQLite записываются только фронтеры из Florality, которых ещё нет локально; перед такой записью база копируется в `data/backups` с датой в имени файла. Если фронт меняют во Florality, бот проверяет `GET /front` раз в `FLORALITY_PULL_INTERVAL_SECONDS` секунд; если фронтер ещё не найден локально, бот импортирует эту личность из ответа Florality и обновляет локальный фронт. Новые личности во Florality автоматически не создаются, пока `FLORALITY_CREATE_MISSING_MEMBERS_ENABLED=false`. Бот хранит локальное соответствие `member_id` к Florality ID в отдельной служебной таблице и не меняет структуру Simply Plural-данных.

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

Основные таблицы Simply Plural не требуют миграций для обычной работы. При работе через Florality локальная база обновляется только для отсутствующих локально фронтеров; остальные расхождения показываются в Telegram-сообщении.
