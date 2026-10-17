"""
notifications.py — фоновый поток проверки напоминаний и показ уведомлений.
Работает независимо от того, свёрнуто окно tkinter или нет.
"""

import threading
import time
from datetime import datetime

import db

# Интервал проверки в секундах
CHECK_INTERVAL = 30

# Флаг для остановки потока
_running = threading.Event()


def _show_notification(title: str, message: str) -> None:
    """Показывает системное уведомление Windows.
    Пытается использовать win10toast, при отсутствии — plyer,
    в крайнем случае — tkinter messagebox (как запасной вариант).
    """
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(
            title,
            message,
            duration=10,
            threaded=True,
        )
    except ImportError:
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="Напоминалка",
                timeout=10,
            )
        except ImportError:
            # Запасной вариант — всплывающее окно tkinter поверх всех окон
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.attributes("-topmost", True)
            root.withdraw()
            messagebox.showwarning(title, message)
            root.destroy()


def _check_loop() -> None:
    """Главный цикл потока: проверяет наступившие напоминания."""
    while _running.is_set():
        # Сначала помечаем просроченные
        db.mark_overdue()

        # Берём напоминания, чьё время пришло
        due = db.get_pending_reminders()
        for r in due:
            msg = r["description"] or "Без описания"
            _show_notification(r["title"], msg)
            # Помечаем как "Просрочено", чтобы не повторять уведомление
            db.update_status(r["id"], "Просрочено")

        time.sleep(CHECK_INTERVAL)


def start() -> None:
    """Запускает фоновый поток проверки."""
    if _running.is_set():
        return
    _running.set()
    t = threading.Thread(target=_check_loop, daemon=True, name="ReminderChecker")
    t.start()


def stop() -> None:
    """Останавливает фоновый поток."""
    _running.clear()
