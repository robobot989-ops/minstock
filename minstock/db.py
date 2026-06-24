from __future__ import annotations

from pathlib import Path
import sqlite3


def connect(database_path: str) -> sqlite3.Connection:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            contact_info TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            unit TEXT NOT NULL DEFAULT 'шт',
            min_stock REAL NOT NULL DEFAULT 0,
            lead_time_days INTEGER NOT NULL DEFAULT 14,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS warehouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS currencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS supplier_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
            item_id INTEGER NOT NULL REFERENCES items(id),
            price REAL NOT NULL,
            currency_id INTEGER NOT NULL REFERENCES currencies(id),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS exchange_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            currency_id INTEGER NOT NULL REFERENCES currencies(id),
            rate_to_rub REAL NOT NULL,
            date TEXT NOT NULL,
            UNIQUE(currency_id, date)
        );

        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('receipt', 'consumption')),
            item_id INTEGER NOT NULL REFERENCES items(id),
            qty REAL NOT NULL CHECK(qty > 0),
            warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
            supplier_id INTEGER REFERENCES suppliers(id),
            price REAL,
            currency_id INTEGER REFERENCES currencies(id),
            exchange_rate REAL,
            comment TEXT NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    _seed(connection)
    connection.commit()


def _seed(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT OR IGNORE INTO warehouses(name) VALUES (?)",
        [("МСК",), ("ТВЕРЬ",)],
    )
    connection.executemany(
        "INSERT OR IGNORE INTO currencies(code) VALUES (?)",
        [("RUB",), ("USD",), ("EUR",)],
    )
