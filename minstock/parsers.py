from __future__ import annotations

import asyncio
import logging
from datetime import date as Date

import aiohttp

logger = logging.getLogger(__name__)

CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
TARGET_CURRENCIES = {"USD", "EUR"}


async def fetch_cbr_rates(session: aiohttp.ClientSession) -> dict[str, float]:
    async with session.get(CBR_URL, timeout=aiohttp.ClientTimeout(total=15)) as response:
        response.raise_for_status()
        data = await response.json(content_type=None)
    rates: dict[str, float] = {}
    valutes = data.get("Valute", {})
    for code in TARGET_CURRENCIES:
        if code in valutes:
            rates[code] = float(valutes[code]["Value"])
    return rates


async def update_rates_periodically(
    db_conn,
    session: aiohttp.ClientSession,
    interval_hours: int = 6,
) -> None:
    from minstock.services import InventoryService

    service = InventoryService(db_conn)
    while True:
        try:
            rates = await fetch_cbr_rates(session)
            today = Date.today().isoformat()
            for code, rate in rates.items():
                currency_id = service.get_currency_id(code)
                db_conn.execute(
                    "INSERT OR IGNORE INTO exchange_rates(currency_id, rate_to_rub, date) VALUES (?, ?, ?)",
                    (currency_id, rate, today),
                )
            db_conn.commit()
            logger.info("CBR rates updated: %s", rates)
        except Exception:
            logger.exception("Failed to fetch CBR rates")
        await asyncio.sleep(interval_hours * 3600)
