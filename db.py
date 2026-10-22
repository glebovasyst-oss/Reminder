"""
db.py — слой базы данных для приложения-напоминалки.
SQLite3, автоматическое создание таблиц, CRUD-операции.
"""

import calendar
import sqlite3
from datetime import datetime, timedelta

DB_PATH = "reminders.db"

VALID_STATUSES = ("Ожидает", "Готово", "Просрочено", "Отменено")

# Варианты повтора. Пустая строка — разовое напоминание.
REPEAT_NONE = ""
REPEAT_DAILY = "Ежедневно"
REPEAT_WEEKLY = "Еженедельно"
REPEAT_MONTHLY = "Ежемесячно"
REPEAT_RULES = (REPEAT_NONE, REPEAT_DAILY, REPEAT_WEEKLY, REPEAT_MONTHLY)

DATE_FORMAT = "%Y-%m-%d %H:%M"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Создаёт таблицу reminders, если её нет, и применяет миграции."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                description TEXT    DEFAULT '',
                due_at      TEXT    NOT NULL,   -- ISO 8601: 'YYYY-MM-DD HH:MM'
                status      TEXT    NOT NULL DEFAULT 'Ожидает',
                repeat_rule TEXT    NOT NULL DEFAULT '',  -- '' | 'Ежедневно' | ...
                created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            )
            """
        )

        # Миграция для баз, созданных до появления повторяющихся напоминаний.
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(reminders)").fetchall()
        }
        if "repeat_rule" not in columns:
            conn.execute(
                "ALTER TABLE reminders "
                "ADD COLUMN repeat_rule TEXT NOT NULL DEFAULT ''"
            )

        conn.commit()


# ── Работа с датами ───────────────────────────────────────────────────

def parse_due(due_at: str) -> datetime:
    """Разбирает строку 'YYYY-MM-DD HH:MM' (допускается вариант с секундами)."""
    for fmt in (DATE_FORMAT, "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(due_at, fmt)
        except ValueError:
            continue
    raise ValueError(f"Некорректная дата: {due_at!r}")


def _next_month_start(dt: datetime) -> datetime:
    """Следующий месяц с той же датой (или последним днём месяца)."""
    year = dt.year + (dt.month // 12)
    month = dt.month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _step(dt: datetime, repeat_rule: str) -> datetime | None:
    """Возвращает следующий момент срабатывания для правила повтора."""
    if repeat_rule == REPEAT_DAILY:
        return dt + timedelta(days=1)
    if repeat_rule == REPEAT_WEEKLY:
        return dt + timedelta(weeks=1)
    if repeat_rule == REPEAT_MONTHLY:
        return _next_month_start(dt)
    return None


def next_occurrence(
    due_at: str, repeat_rule: str, after: datetime | None = None
) -> str | None:
    """Вычисляет ближайшее срабатывание строго после момента `after`.

    Пропускает все пропущенные циклы (например, если приложение было
    закрыто несколько дней). Возвращает строку 'YYYY-MM-DD HH:MM'
    или None для разового напоминания.
    """
    after = after or datetime.now()
    nxt = _step(parse_due(due_at), repeat_rule)
    if nxt is None:
        return None

    # Ограничение защищает от бесконечного цикла при испорченных данных.
    for _ in range(10000):
        if nxt > after:
            return nxt.strftime(DATE_FORMAT)
        nxt = _step(nxt, repeat_rule)
    return nxt.strftime(DATE_FORMAT)


# ── CRUD ──────────────────────────────────────────────────────────────

def add_reminder(
    title: str, description: str, due_at: str, repeat_rule: str = ""
) -> int:
    """Добавляет напоминание. due_at — 'YYYY-MM-DD HH:MM'. Возвращает id."""
    if repeat_rule not in REPEAT_RULES:
        raise ValueError(f"Недопустимое правило повтора: {repeat_rule}")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (title, description, due_at, repeat_rule) "
            "VALUES (?, ?, ?, ?)",
            (title, description, due_at, repeat_rule),
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


def update_due_at(reminder_id: int, due_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reminders SET due_at = ? WHERE id = ?",
            (due_at, reminder_id),
        )
        conn.commit()


def advance_reminder(reminder_id: int, after: datetime | None = None) -> str | None:
    """Переносит повторяющееся напоминание на следующий цикл.

    Статус снова становится «Ожидает». Возвращает новую дату или None,
    если напоминание разовое.
    """
    reminder = get_reminder_by_id(reminder_id)
    if not reminder or not reminder["repeat_rule"]:
        return None

    new_due = next_occurrence(reminder["due_at"], reminder["repeat_rule"], after)
    if new_due is None:
        return None

    with _connect() as conn:
        conn.execute(
            "UPDATE reminders SET due_at = ?, status = 'Ожидает' WHERE id = ?",
            (new_due, reminder_id),
        )
        conn.commit()
    return new_due


def complete_reminder(reminder_id: int) -> str | None:
    """Отмечает напоминание выполненным.

    Для повторяющегося напоминания серия не завершается: время сдвигается
    на следующий цикл, а статус остаётся «Ожидает». Возвращает новую дату
    или None для разового напоминания.
    """
    reminder = get_reminder_by_id(reminder_id)
    if reminder and reminder["repeat_rule"]:
        return advance_reminder(reminder_id)
    update_status(reminder_id, "Готово")
    return None


def snooze_reminder(reminder_id: int, minutes: int = 30) -> str | None:
    """Откладывает напоминание на `minutes` минут и снова делает его ожидающим."""
    reminder = get_reminder_by_id(reminder_id)
    if not reminder:
        return None

    try:
        base = parse_due(reminder["due_at"])
    except ValueError:
        base = datetime.now()

    # Если время уже прошло — отсчитываем от текущего момента.
    base = max(base, datetime.now())
    new_due = (base + timedelta(minutes=minutes)).strftime(DATE_FORMAT)

    with _connect() as conn:
        conn.execute(
            "UPDATE reminders SET due_at = ?, status = 'Ожидает' WHERE id = ?",
            (new_due, reminder_id),
        )
        conn.commit()
    return new_due


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
    now = datetime.now().strftime(DATE_FORMAT)
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE status = 'Ожидает' AND due_at <= ?",
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_overdue() -> int:
    """Переводит просроченные разовые напоминания из 'Ожидает' в 'Просрочено'.
    Повторяющиеся напоминания не трогает — их переносит advance_reminder().
    Возвращает количество затронутых строк."""
    now = datetime.now().strftime(DATE_FORMAT)
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE reminders SET status = 'Просрочено' "
            "WHERE status = 'Ожидает' AND due_at < ? AND repeat_rule = ''",
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
