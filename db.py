"""
db.py — слой базы данных для приложения-напоминалки.
SQLite3, автоматическое создание таблиц, CRUD-операции.
"""

import sqlite3
from datetime import datetime

DB_PATH = "reminders.db"

VALID_STATUSES = ("Ожидает", "Готово", "Просрочено", "Отменено")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Создаёт таблицу reminders, если её нет."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                description TEXT    DEFAULT '',
                due_at      TEXT    NOT NULL,   -- ISO 8601: 'YYYY-MM-DD HH:MM'
                status      TEXT    NOT NULL DEFAULT 'Ожидает',
                created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            )
            """
        )
        conn.commit()


# ── CRUD ──────────────────────────────────────────────────────────────

def add_reminder(title: str, description: str, due_at: str) -> int:
    """Добавляет напоминание. due_at — 'YYYY-MM-DD HH:MM'. Возвращает id."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (title, description, due_at) VALUES (?, ?, ?)",
            (title, description, due_at),
        )
        conn.commit()
        return cur.lastrowid


def delete_reminder(reminder_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        conn.commit()


def update_status(reminder_id: int, status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Недопустимый статус: {status}")
    with _connect() as conn:
        conn.execute(
            "UPDATE reminders SET status = ? WHERE id = ?",
            (status, reminder_id),
        )
        conn.commit()


def get_all_reminders(status_filter: str | None = None) -> list[dict]:
    """Возвращает список словарей. Если status_filter=None — все."""
    with _connect() as conn:
        if status_filter and status_filter != "Все":
            rows = conn.execute(
                "SELECT * FROM reminders WHERE status = ? ORDER BY due_at",
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reminders ORDER BY due_at"
            ).fetchall()
        return [dict(r) for r in rows]


def get_pending_reminders() -> list[dict]:
    """Возвращает напоминания в статусе 'Ожидает', чьё время уже наступило."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE status = 'Ожидает' AND due_at <= ?",
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_overdue() -> int:
    """Переводит просроченные напоминания из 'Ожидает' в 'Просрочено'.
    Возвращает количество затронутых строк."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE reminders SET status = 'Просрочено' "
            "WHERE status = 'Ожидает' AND due_at < ?",
            (now,),
        )
        conn.commit()
        return cur.rowcount


def get_reminder_by_id(reminder_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()
        return dict(row) if row else None
