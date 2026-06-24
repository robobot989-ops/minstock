# MiniStock

Минимальный складской Telegram-бот для учета комплектующих: приход, расход, остатки и список к закупке.

## Что уже есть

- SQLite-база в одном файле.
- Два склада по умолчанию: `МСК` и `ТВЕРЬ`.
- Валюты по умолчанию: `RUB`, `USD`, `EUR`.
- Telegram-меню: `Приход`, `Расход`, `Остатки`, `Закупки`.
- Команды для первичного заполнения справочников.
- Поддержка прокси для Telegram через `TELEGRAM_PROXY_URL`.

## Настройка

1. Создайте бота у `@BotFather` и получите токен.
2. Узнайте свой Telegram ID: временно оставьте `ADMIN_TELEGRAM_IDS` пустым, запустите бота и отправьте `/id`.
3. Скопируйте `.env.example` в `.env` и заполните значения.

```env
TELEGRAM_BOT_TOKEN=123456:token
ADMIN_TELEGRAM_IDS=123456789
DATABASE_PATH=data/minstock.sqlite3
TELEGRAM_PROXY_URL=socks5://127.0.0.1:1080
```

Если сервер ходит в Telegram напрямую, оставьте `TELEGRAM_PROXY_URL` пустым.

## Запуск через Docker

```bash
docker compose up -d --build
```

## Локальный запуск без Docker

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m minstock.bot
```

На Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

## Следующие этапы

- Автозагрузка курсов ЦБ РФ.
- История операций и Excel-отчеты.
- Локальный web-экран только для просмотра.
- Gemini AI для вопросов в свободной форме.
