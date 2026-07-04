# Plural Front Telegram Bot

Telegram-бот для локального фронт-трекинга по экспорту Simply Plural.

## Что умеет

Админские кнопки:

- **Фронт** — поиск личности по базе и постановка на фронт.
- **Снять с фронта** — выбор личности из текущего фронта и снятие.
- **Блюр** — очистить фронт. Пустой фронт = блюр.
- **Инфо о фронте** — посмотреть подробную информацию.

Пользовательская кнопка:

- **Инфо о фронте** — показывает текущих фронтеров, местоимения и блок **Категории:** со всеми папками Simply Plural, где состоит личность.

## Важная приватность

В архиве есть готовая SQLite-база `data/bot.sqlite3`, собранная из вашего экспорта:

- перенесены `members`;
- перенесены `groups`;
- перенесены связи `member -> groups`;
- перенесены `customFields`;
- не перенесены API tokens, IP/security logs, friend request logs, export keys.

База всё равно содержит приватные описания личностей. Не выкладывайте её в публичный GitHub.

## Быстрый запуск на Windows

1. Установите Python 3.11 или новее.

2. Распакуйте архив.

3. В папке проекта создайте виртуальное окружение:

```bash
python -m venv .venv
```

4. Активируйте:

```bash
.venv\Scripts\activate
```

5. Установите зависимости:

```bash
pip install -r requirements.txt
```

6. Скопируйте `.env.example` в `.env`.

7. Вставьте токен от `@BotFather`:

```env
BOT_TOKEN=сюда_токен
```

8. Вставьте ваши Telegram ID:

```env
ADMIN_IDS=123456789
```

Узнать ID можно у `@userinfobot`.

9. Запустите:

```bash
python bot.py
```

10. Откройте своего бота в Telegram и нажмите `/start`.

## Запуск на Linux / VPS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python bot.py
```

## Импорт нового экспорта Simply Plural

Положите новый JSON в:

```text
data/simply_plural_export.json
```

Затем в `.env` поставьте:

```env
AUTO_IMPORT_ON_START=true
```

И запустите:

```bash
python bot.py
```

Или импортируйте вручную:

```bash
python -m app.import_sp data/simply_plural_export.json --db data/bot.sqlite3
```

## Как работает статус

Если таблица текущего фронта пустая:

```text
блюр
```

Если на фронте одна или несколько личностей:

```text
фронт - Имя
фронт - Имя, Имя 2
```

Кнопка **Блюр** очищает весь фронт.

## Как работает информация о фронте

Бот показывает:

```text
Имя

Местоимения: ...

Категории:
- Папка
- Родитель / Вложенная папка

Описание:
...

Дополнительная информация:
Subsystem:
...
Relatives:
...
Couple:
...
Description from managers:
...
Description from other alters:
...
```

Внутренние упоминания Simply Plural вида `<###@id###>` автоматически заменяются на имена личностей, если эти ID есть в базе.

## Если обычный пользователь попробует управлять фронтом

Бот не выполнит действие. Проверка идёт не только по кнопкам, но и по Telegram user id.

## Файлы

```text
bot.py
app/
data/bot.sqlite3
requirements.txt
.env.example
README.md
```
