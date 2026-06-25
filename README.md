# MiniStock

Минимальный складской Telegram-бот + веб-панель для учёта комплектующих: приход, расход, остатки, список к закупке, история, отчёты и AI-вопросы.

## Что уже есть

- SQLite-база в одном файле.
- Два склада по умолчанию: `МСК` и `ТВЕРЬ`.
- Валюты по умолчанию: `RUB`, `USD`, `EUR`.
- Telegram-меню: `Приход`, `Расход`, `Остатки`, `Закупки`, `История`, `Отчёт`, `AI`.
- Команда `/backup` — мгновенный бэкап базы прямо в Telegram.
- Ежедневное напоминание о закупках (конфигурируется через `PURCHASE_ALERT_HOUR`).
- Автозагрузка курсов USD/EUR с ЦБ РФ (раз в 6 часов).
- История операций за 7/30/90/365 дней.
- Excel-отчёт (остатки + движения).
- Веб-панель view-only с HTTP Basic Auth.
- Gemini AI для свободных вопросов по данным (только SELECT-запросы).
- Поддержка прокси для Telegram через `TELEGRAM_PROXY_URL`.

## Настройка

Проект рассчитан на **Python 3.12–3.13**. Не используйте Python 3.14 для локального запуска на Windows: часть зависимостей пока может устанавливаться только через сборку C/Rust-модулей.

1. Создайте бота у `@BotFather` и получите токен.
2. Узнайте свой Telegram ID: временно оставьте `ADMIN_TELEGRAM_IDS` пустым, запустите бота и отправьте `/id`.
3. Скопируйте `.env.example` в `.env` и заполните значения.

```env
TELEGRAM_BOT_TOKEN=123456:token
ADMIN_TELEGRAM_IDS=123456789
DATABASE_PATH=data/minstock.sqlite3
TELEGRAM_PROXY_URL=socks5://127.0.0.1:1080
GEMINI_API_KEY=your_gemini_key
WEB_AUTH_SECRET=ChangeMePlease
PURCHASE_ALERT_HOUR=9
```

Если сервер ходит в Telegram напрямую, оставьте `TELEGRAM_PROXY_URL` пустым.

Пароль `WEB_AUTH_SECRET` защищает веб-интерфейс. Оставьте пустым, чтобы отключить авторизацию.

```bash
# только бот
python -m minstock.bot

# только веб-панель
python -m uvicorn minstock.web:app --host 0.0.0.0 --port 8080
```

## Запуск через Docker

```bash
docker compose up -d --build
```

## Локальный запуск без Docker

На Windows используйте установленный Python 3.12 или 3.13:

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m minstock.bot
```

На Linux:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m minstock.bot
```

## Первичное заполнение

Добавить поставщика:

```text
/add_supplier ООО Сталь; +7 999 000-00-00
```

Добавить товар:

```text
/add_item N-001; Нож 2мм; шт; 50; 14
```

Формат товара: `артикул; название; ед; минимальный_остаток; срок_поставки_дней`.

## Примечания

- AI работает только с безопасными `SELECT`-запросами и не может изменить данные.
- Веб-интерфейс доступен по `http://<vps-ip>:8080` после запуска `minstock-web`.
