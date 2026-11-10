"""A durable send fence; an ambiguous send is never replayed after restart."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class DeliveryJournal:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS deliveries ("
            "id TEXT PRIMARY KEY, status TEXT NOT NULL, platform_id TEXT, error TEXT, "
            "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        self.connection.execute(
            "UPDATE deliveries SET status='unknown', error='process_interrupted_during_send' "
            "WHERE status='sending'"
        )
        self.connection.commit()

    def reserve(self, delivery_id: str) -> bool:
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO deliveries(id,status) VALUES (?, 'sending')", (delivery_id,)
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def finish(self, delivery_id: str, status: str, platform_id: str | None = None,
               error: str | None = None) -> None:
        if status not in {"sent", "failed", "unknown"}:
            raise ValueError("invalid delivery status")
        self.connection.execute(
            "UPDATE deliveries SET status=?,platform_id=?,error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, platform_id, error, delivery_id),
        )
        self.connection.commit()

    def get(self, delivery_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT status,platform_id,error FROM deliveries WHERE id=?", (delivery_id,)
        ).fetchone()
        return {"status": row[0], "platform_message_id": row[1], "error": row[2]} if row else None

    def close(self) -> None:
        self.connection.close()
