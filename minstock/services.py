from __future__ import annotations

import sqlite3


class InventoryService:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def add_supplier(self, name: str, contact_info: str = "") -> int:
        cursor = self.connection.execute(
            "INSERT INTO suppliers(name, contact_info) VALUES (?, ?)",
            (name.strip(), contact_info.strip()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def add_item(
        self,
        article: str,
        name: str,
        unit: str = "шт",
        min_stock: float = 0,
        lead_time_days: int = 14,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO items(article, name, unit, min_stock, lead_time_days)
            VALUES (?, ?, ?, ?, ?)
            """,
            (article.strip(), name.strip(), unit.strip(), min_stock, lead_time_days),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def search_items(self, query: str, limit: int = 10) -> list[sqlite3.Row]:
        like_query = f"%{query.strip()}%"
        return self.connection.execute(
            """
            SELECT * FROM items
            WHERE is_active = 1 AND (article LIKE ? OR name LIKE ?)
            ORDER BY article
            LIMIT ?
            """,
            (like_query, like_query, limit),
        ).fetchall()

    def list_suppliers(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM suppliers WHERE is_active = 1 ORDER BY name"
        ).fetchall()

    def list_warehouses(self) -> list[sqlite3.Row]:
        return self.connection.execute("SELECT * FROM warehouses ORDER BY name").fetchall()

    def list_currencies(self) -> list[sqlite3.Row]:
        return self.connection.execute("SELECT * FROM currencies ORDER BY code").fetchall()

    def get_currency_id(self, code: str) -> int:
        row = self.connection.execute(
            "SELECT id FROM currencies WHERE code = ?",
            (code.upper(),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown currency: {code}")
        return int(row["id"])

    def record_receipt(
        self,
        item_id: int,
        qty: float,
        warehouse_id: int,
        supplier_id: int,
        price: float,
        currency_id: int,
        created_by: int,
        comment: str = "",
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO operations(
                type, item_id, qty, warehouse_id, supplier_id, price,
                currency_id, comment, created_by
            ) VALUES ('receipt', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (item_id, qty, warehouse_id, supplier_id, price, currency_id, comment, created_by),
        )
        self.connection.execute(
            """
            INSERT INTO supplier_prices(supplier_id, item_id, price, currency_id)
            VALUES (?, ?, ?, ?)
            """,
            (supplier_id, item_id, price, currency_id),
        )
        self.connection.commit()

    def record_consumption(
        self,
        item_id: int,
        qty: float,
        warehouse_id: int,
        created_by: int,
        comment: str = "",
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO operations(type, item_id, qty, warehouse_id, comment, created_by)
            VALUES ('consumption', ?, ?, ?, ?, ?)
            """,
            (item_id, qty, warehouse_id, comment, created_by),
        )
        self.connection.commit()

    def stock_for_item_warehouse(self, item_id: int, warehouse_id: int) -> float:
        row = self.connection.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN type = 'receipt' THEN qty ELSE -qty END), 0) AS qty
            FROM operations
            WHERE item_id = ? AND warehouse_id = ?
            """,
            (item_id, warehouse_id),
        ).fetchone()
        return float(row["qty"])

    def stock_rows(self, limit: int = 100) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            WITH movement AS (
                SELECT
                    item_id,
                    warehouse_id,
                    SUM(CASE WHEN type = 'receipt' THEN qty ELSE -qty END) AS qty
                FROM operations
                GROUP BY item_id, warehouse_id
            )
            SELECT
                i.id,
                i.article,
                i.name,
                i.unit,
                i.min_stock,
                COALESCE(SUM(CASE WHEN w.name = 'МСК' THEN m.qty ELSE 0 END), 0) AS msk_qty,
                COALESCE(SUM(CASE WHEN w.name = 'ТВЕРЬ' THEN m.qty ELSE 0 END), 0) AS tver_qty,
                COALESCE(SUM(m.qty), 0) AS total_qty,
                MAX(0, i.min_stock - COALESCE(SUM(m.qty), 0)) AS need_qty
            FROM items i
            LEFT JOIN movement m ON m.item_id = i.id
            LEFT JOIN warehouses w ON w.id = m.warehouse_id
            WHERE i.is_active = 1
            GROUP BY i.id
            ORDER BY need_qty DESC, i.article
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def purchase_rows(self) -> list[sqlite3.Row]:
        return [row for row in self.stock_rows() if row["need_qty"] > 0]
