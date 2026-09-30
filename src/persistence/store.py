import json
import sqlite3
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS processed_events (
                idempotency_key TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                label TEXT,
                processed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS call_attempts (
                contact_id TEXT PRIMARY KEY,
                attempts INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS reminders (
                reminder_id TEXT PRIMARY KEY,
                contact_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dnc_records (
                contact_id TEXT PRIMARY KEY,
                phone TEXT NOT NULL,
                channel TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cut_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id TEXT NOT NULL,
                call_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                operation TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        self.connection.commit()

    def get_processed_event(self, idempotency_key: str) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT *
            FROM processed_events
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        )

        return cursor.fetchone()

    def save_processed_event(
        self,
        idempotency_key: str,
        event_id: str,
        processed_at: str,
        label: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO processed_events (
                idempotency_key,
                event_id,
                label,
                processed_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (idempotency_key, event_id, label, processed_at),
        )

        self.connection.commit()

    def get_call_attempts(self, contact_id: str) -> int:
        cursor = self.connection.execute(
            """
            SELECT attempts
            FROM call_attempts
            WHERE contact_id = ?
            """,
            (contact_id,),
        )

        row = cursor.fetchone()

        if row is None:
            return 0

        return row["attempts"]

    def increment_call_attempts(self, contact_id: str) -> int:
        current_attempts = self.get_call_attempts(contact_id)
        new_attempts = current_attempts + 1

        self.connection.execute(
            """
            INSERT INTO call_attempts (contact_id, attempts)
            VALUES (?, ?)
            ON CONFLICT(contact_id)
            DO UPDATE SET attempts = excluded.attempts
            """,
            (contact_id, new_attempts),
        )

        self.connection.commit()

        return new_attempts

    def save_reminder(
        self,
        reminder_id: str,
        contact_id: str,
        channel: str,
        created_at: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO reminders (
                reminder_id,
                contact_id,
                channel,
                status,
                created_at
            )
            VALUES (?, ?, ?, 'scheduled', ?)
            """,
            (
                reminder_id,
                contact_id,
                channel,
                created_at,
            ),
        )

        self.connection.commit()

    def get_pending_reminders(self, contact_id: str) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT *
            FROM reminders
            WHERE contact_id = ?
              AND status = 'scheduled'
            ORDER BY created_at
            """,
            (contact_id,),
        )

        return cursor.fetchall()

    def cancel_reminder(self, reminder_id: str) -> None:
        self.connection.execute(
            """
            UPDATE reminders
            SET status = 'cancelled'
            WHERE reminder_id = ?
              AND status = 'scheduled'
            """,
            (reminder_id,),
        )

        self.connection.commit()

    def save_dnc(
        self,
        contact_id: str,
        phone: str,
        channel: str,
        created_at: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO dnc_records (
                contact_id,
                phone,
                channel,
                created_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(contact_id)
            DO UPDATE SET
                phone = excluded.phone,
                channel = excluded.channel,
                created_at = excluded.created_at
            """,
            (
                contact_id,
                phone,
                channel,
                created_at,
            ),
        )

        self.connection.commit()

    def is_dnc(self, contact_id: str) -> bool:
        cursor = self.connection.execute(
            """
            SELECT 1
            FROM dnc_records
            WHERE contact_id = ?
            """,
            (contact_id,),
        )

        return cursor.fetchone() is not None

    def save_cut_call(
        self,
        contact_id: str,
        call_id: str,
        created_at: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO cut_calls (
                contact_id,
                call_id,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                contact_id,
                call_id,
                created_at,
            ),
        )

        self.connection.commit()

    def count_cut_calls(self, contact_id: str) -> int:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM cut_calls
            WHERE contact_id = ?
            """,
            (contact_id,),
        )

        row = cursor.fetchone()

        return row["count"]

    def save_order(
        self,
        order_id: str,
        event_id: str,
        idempotency_key: str,
        operation: str,
        body: dict[str, Any],
        created_at: str,
    ) -> bool:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO orders (
                order_id,
                event_id,
                idempotency_key,
                operation,
                body,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                event_id,
                idempotency_key,
                operation,
                json.dumps(body, ensure_ascii=False),
                created_at,
            ),
        )

        self.connection.commit()

        return cursor.rowcount == 1

    def get_order(self, idempotency_key: str) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT *
            FROM orders
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        )

        return cursor.fetchone()

    def close(self) -> None:
        self.connection.close()