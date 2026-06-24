from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    admin_telegram_ids: set[int]
    database_path: str
    telegram_proxy_url: str | None


def load_settings() -> Settings:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    raw_admin_ids = os.getenv("ADMIN_TELEGRAM_IDS", "").strip()
    admin_ids = {
        int(value.strip())
        for value in raw_admin_ids.split(",")
        if value.strip()
    }

    return Settings(
        telegram_bot_token=token,
        admin_telegram_ids=admin_ids,
        database_path=os.getenv("DATABASE_PATH", "data/minstock.sqlite3").strip(),
        telegram_proxy_url=os.getenv("TELEGRAM_PROXY_URL", "").strip() or None,
    )
