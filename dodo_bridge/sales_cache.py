from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from dodo_bridge.audit import utc_now_iso


class SalesSummaryCache:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS dodo_sales_summary_daily (
                    unit_id TEXT NOT NULL,
                    day TEXT NOT NULL,
                    unit_name TEXT,
                    orders INTEGER NOT NULL,
                    products INTEGER NOT NULL,
                    sales_with_discount REAL NOT NULL,
                    sales_without_discount REAL NOT NULL,
                    discount REAL NOT NULL,
                    refreshed_at TEXT NOT NULL,
                    PRIMARY KEY (unit_id, day)
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dodo_sales_summary_daily_day
                ON dodo_sales_summary_daily(day)
                """
            )

    def fetch_daily(
        self,
        *,
        unit_ids: list[str],
        days: list[str],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        if not unit_ids or not days:
            return {}

        self.initialize()
        unit_placeholders = ",".join("?" for _ in unit_ids)
        day_placeholders = ",".join("?" for _ in days)
        query = f"""
            SELECT *
            FROM dodo_sales_summary_daily
            WHERE unit_id IN ({unit_placeholders})
              AND day IN ({day_placeholders})
        """
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(query, (*unit_ids, *days)).fetchall()
        return {(_text(row["unit_id"]), _text(row["day"])): _row_to_item(row) for row in rows}

    def upsert_daily(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0

        self.initialize()
        refreshed_at = utc_now_iso()
        values = [
            (
                row["unitId"],
                row["day"],
                row.get("unitName"),
                int(row["orders"]),
                int(row["products"]),
                float(row["salesWithDiscount"]),
                float(row["salesWithoutDiscount"]),
                float(row["salesWithoutDiscount"]) - float(row["salesWithDiscount"]),
                refreshed_at,
            )
            for row in rows
        ]
        with sqlite3.connect(self.path) as db:
            db.executemany(
                """
                INSERT INTO dodo_sales_summary_daily (
                    unit_id, day, unit_name, orders, products,
                    sales_with_discount, sales_without_discount, discount,
                    refreshed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(unit_id, day) DO UPDATE SET
                    unit_name = excluded.unit_name,
                    orders = excluded.orders,
                    products = excluded.products,
                    sales_with_discount = excluded.sales_with_discount,
                    sales_without_discount = excluded.sales_without_discount,
                    discount = excluded.discount,
                    refreshed_at = excluded.refreshed_at
                """,
                values,
            )
        return len(values)


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "unitId": _text(row["unit_id"]),
        "day": _text(row["day"]),
        "unitName": row["unit_name"],
        "orders": int(row["orders"]),
        "products": int(row["products"]),
        "salesWithDiscount": float(row["sales_with_discount"]),
        "salesWithoutDiscount": float(row["sales_without_discount"]),
        "discount": float(row["discount"]),
        "refreshedAt": _text(row["refreshed_at"]),
    }


def _text(value: Any) -> str:
    return str(value or "")
