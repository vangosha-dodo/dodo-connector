from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SECRET_MARKERS = ("token", "authorization", "password", "secret", "api_key", "key")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if any(marker in key.lower() for marker in SECRET_MARKERS):
                redacted[key] = "***"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def json_dumps(value: Any) -> str:
    return json.dumps(redact(value), ensure_ascii=False, default=str, sort_keys=True)


class AuditStore:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    actor TEXT,
                    intent TEXT,
                    tool_name TEXT,
                    connector TEXT,
                    decision TEXT NOT NULL,
                    reason TEXT,
                    outcome TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    response_chars INTEGER NOT NULL DEFAULT 0,
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    audit_id INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    comment TEXT,
                    labels_json TEXT NOT NULL,
                    FOREIGN KEY(audit_id) REFERENCES events(id)
                )
                """
            )

    def record_event(
        self,
        *,
        actor: str | None,
        intent: str | None,
        tool_name: str,
        connector: str | None,
        decision: str,
        reason: str,
        outcome: str,
        params: dict[str, Any],
        response_chars: int = 0,
        latency_ms: int = 0,
        error: str | None = None,
    ) -> int:
        self.initialize()
        with sqlite3.connect(self.path) as db:
            cursor = db.execute(
                """
                INSERT INTO events (
                    created_at, actor, intent, tool_name, connector, decision, reason,
                    outcome, params_json, response_chars, latency_ms, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now_iso(),
                    actor,
                    intent,
                    tool_name,
                    connector,
                    decision,
                    reason,
                    outcome,
                    json_dumps(params),
                    response_chars,
                    latency_ms,
                    error,
                ),
            )
            return int(cursor.lastrowid)

    def add_feedback(
        self,
        *,
        audit_id: int,
        score: int,
        comment: str | None,
        labels: list[str],
    ) -> int:
        self.initialize()
        with sqlite3.connect(self.path) as db:
            cursor = db.execute(
                """
                INSERT INTO feedback (created_at, audit_id, score, comment, labels_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (utc_now_iso(), audit_id, score, comment, json_dumps(labels)),
            )
            return int(cursor.lastrowid)

    def fetch_denied_counts(self) -> list[sqlite3.Row]:
        return self._fetch_all(
            """
            SELECT tool_name, reason, COUNT(*) AS count
            FROM events
            WHERE decision IN ('deny', 'approval_required')
            GROUP BY tool_name, reason
            ORDER BY count DESC
            """
        )

    def fetch_negative_feedback_counts(self) -> list[sqlite3.Row]:
        return self._fetch_all(
            """
            SELECT e.tool_name, COUNT(*) AS count
            FROM feedback f
            JOIN events e ON e.id = f.audit_id
            WHERE f.score < 0
            GROUP BY e.tool_name
            ORDER BY count DESC
            """
        )

    def fetch_large_response_counts(self, threshold: int) -> list[sqlite3.Row]:
        return self._fetch_all(
            """
            SELECT tool_name, COUNT(*) AS count, MAX(response_chars) AS max_response_chars
            FROM events
            WHERE response_chars >= ?
            GROUP BY tool_name
            ORDER BY count DESC
            """,
            (threshold,),
        )

    def _fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        self.initialize()
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return list(db.execute(query, params))

