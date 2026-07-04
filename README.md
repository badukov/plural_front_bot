# Plural Front Telegram Bot

Telegram-бот для локального фронт-трекинга по экспорту Simply Plural.

## Возможности

Для админов:

- **Фронт** — поиск личности и постановка на фронт.
- **Снять с фронта** — снятие конкретной личности с текущего фронта.
- **Блюр** — очистка фронта.
- **Инфо о фронте** — подробная информация обо всех текущих фронтерах.
- **Справочник** — просмотр всех личностей, поиск и фильтр по категориям.
- **Оповещения** — включение и выключение рассылки о смене фронта.
- **Добавить личность** — мастер добавления новой личности и JSON-экспорт базы.

Для обычных пользователей:

- **Инфо о фронте**.
- **Справочник**.
- **Оповещения**.
- Поиск по имени обычным текстовым сообщением.

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
