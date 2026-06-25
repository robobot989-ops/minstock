from __future__ import annotations

import logging
import re
import sqlite3

import aiohttp

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Ты — ассистент складского учёта MiniStock.

База данных SQLite содержит следующие таблицы:

1. items — номенклатура: id, article (артикул), name (название), unit (ед.изм), min_stock (мин.остаток), lead_time_days (срок поставки)
2. suppliers — поставщики: id, name (название), contact_info
3. warehouses — склады: id, name (название)
4. currencies — валюты: id, code (RUB/USD/EUR)
5. supplier_prices — цены поставщиков: supplier_id, item_id, price, currency_id
6. exchange_rates — курсы: currency_id, rate_to_rub, date
7. operations — движения: type ('receipt'=приход / 'consumption'=расход), item_id, qty, warehouse_id, supplier_id, price, currency_id, exchange_rate, comment, created_at

Пользователь задаёт вопрос на русском по складскому учёту.
Ответь понятно. Если нужна выборка данных — напиши SQL-запрос в теге ```sql ... ```.
Если запрос не нужен — просто ответи текстом.
Не выдумывай данные, которых нет в таблицах.
"""


def _build_user_prompt(db_path: str, question: str) -> str:
    conn = sqlite3.connect(db_path)
    try:
        items_sample = conn.execute(
            "SELECT article, name FROM items WHERE is_active = 1 LIMIT 5"
        ).fetchall()
        suppliers_sample = conn.execute(
            "SELECT name FROM suppliers WHERE is_active = 1 LIMIT 5"
        ).fetchall()
        warehouses = conn.execute("SELECT name FROM warehouses").fetchall()
    finally:
        conn.close()

    lines = [f"Вопрос: {question}"]
    lines.append(f"\nСклады: {', '.join(r[0] for r in warehouses)}")
    lines.append(f"\nПримеры товаров (5 из базы):")
    for art, name in items_sample:
        lines.append(f"  {art} — {name}")
    lines.append(f"\nПоставщики (5 из базы):")
    for (sname,) in suppliers_sample:
        lines.append(f"  {sname}")
    return "\n".join(lines)


def _extract_sql(text: str) -> str | None:
    match = re.search(r"```sql\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _format_rows(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return "Нет данных."
    keys = rows[0].keys()
    lines: list[str] = []
    for row in rows[:15]:
        lines.append("  " + " | ".join(str(row[k]) for k in keys))
    if len(rows) > 15:
        lines.append(f"  ... и ещё {len(rows) - 15} строк")
    return "\n".join(lines)


async def ask(
    question: str,
    db_conn: sqlite3.Connection,
    db_path: str,
    gemini_api_key: str,
    http_session: aiohttp.ClientSession,
    model: str = "gemini-2.0-flash",
) -> str:
    user_text = _build_user_prompt(db_path, question)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_api_key}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n\n" + user_text}]}
        ]
    }

    try:
        async with http_session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if not resp.ok:
                error_text = await resp.text()
                logger.error("Gemini API error %s: %s", resp.status, error_text)
                return f"Ошибка API Gemini: {resp.status}"
            data = await resp.json(content_type=None)
    except Exception as exc:
        logger.exception("Gemini request failed")
        return f"Ошибка при обращении к Gemini: {exc}"

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return "Gemini не дал ответа."

    sql = _extract_sql(text)
    if sql:
        try:
            result = db_conn.execute(sql).fetchall()
            formatted = _format_rows(result)
            clean_sql = sql.replace("\n", " ")
            return (
                f"Запрос: <code>{clean_sql[:200]}</code>\n"
                f"Результат:\n<pre>{formatted}</pre>"
            )
        except Exception as exc:
            return (
                f"Gemini предложил запрос, но он не выполнился:\n"
                f"<code>{sql[:300]}</code>\n\nОшибка: {exc}"
            )

    return text
