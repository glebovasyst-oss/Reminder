"""
main.py — точка входа. Интерфейс на tkinter, связывает БД и уведомления.
Запуск:  python main.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime, timedelta

import db
import notifications


class ReminderApp:
    """Главное окно приложения."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Напоминалка")
        self.root.geometry("720x480")
        self.root.minsize(560, 360)

        # Инициализация БД
        db.init_db()

        # Запуск фонового потока уведомлений
        notifications.start()

        # При закрытии окна — останавливаем поток
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_list()

    # ── Интерфейс ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # --- Панель кнопок ---
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Button(btn_frame, text="Добавить", command=self._add_dialog).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(btn_frame, text="Удалить", command=self._delete_selected).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(
            btn_frame, text="Отметить «Готово»", command=self._mark_done
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            btn_frame, text="Отменить", command=self._mark_cancelled
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Обновить", command=self._refresh_list).pack(
            side=tk.LEFT, padx=2
        )

        # --- Фильтр по статусу ---
        filter_frame = ttk.Frame(self.root)
        filter_frame.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(filter_frame, text="Фильтр:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar(value="Все")
        self.filter_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_var,
            state="readonly",
            width=15,
            values=["Все", "Ожидает", "Готово", "Просрочено", "Отменено"],
        )
        self.filter_combo.pack(side=tk.LEFT, padx=4)
        self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        # --- Таблица ---
        columns = ("id", "title", "description", "due_at", "status")
        self.tree = ttk.Treeview(
            self.root, columns=columns, show="headings", selectmode="browse"
        )

        self.tree.heading("id", text="ID")
        self.tree.heading("title", text="Заголовок")
        self.tree.heading("description", text="Описание")
        self.tree.heading("due_at", text="Когда")
        self.tree.heading("status", text="Статус")

        self.tree.column("id", width=40, anchor=tk.CENTER)
        self.tree.column("title", width=180)
        self.tree.column("description", width=240)
        self.tree.column("due_at", width=130, anchor=tk.CENTER)
        self.tree.column("status", width=90, anchor=tk.CENTER)

        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        # Цветовая раскраска статусов
        self.tree.tag_configure("Ожидает", foreground="#0066cc")
        self.tree.tag_configure("Готово", foreground="#2a8c2a")
        self.tree.tag_configure("Просрочено", foreground="#cc3300")
        self.tree.tag_configure("Отменено", foreground="#888888")

        # Статус-бар
        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(
            self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W
        ).pack(fill=tk.X, padx=8, pady=(0, 4))

    # ── Действия ──────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        # Очищаем текущие записи
        for item in self.tree.get_children():
            self.tree.delete(item)

        status_filter = self.filter_var.get()
        reminders = db.get_all_reminders(
            status_filter if status_filter != "Все" else None
        )

        for r in reminders:
            self.tree.insert(
                "",
                tk.END,
                values=(r["id"], r["title"], r["description"], r["due_at"], r["status"]),
                tags=(r["status"],),
            )

        self.status_var.set(f"Всего записей: {len(reminders)}")

    def _add_dialog(self) -> None:
        """Диалог добавления напоминания."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Новое напоминание")
        dialog.geometry("380x320")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Поля
        ttk.Label(dialog, text="Заголовок:").pack(pady=(12, 2))
        title_entry = ttk.Entry(dialog, width=40)
        title_entry.pack(pady=2)

        ttk.Label(dialog, text="Описание:").pack(pady=(4, 2))
        desc_text = tk.Text(dialog, width=40, height=4)
        desc_text.pack(pady=2)

        ttk.Label(dialog, text="Дата и время (ГГГГ-ММ-ДД ЧЧ:ММ):").pack(pady=(4, 2))

        time_frame = ttk.Frame(dialog)
        time_frame.pack(pady=2)

        # По умолчанию — через час
        default_dt = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        time_entry = ttk.Entry(time_frame, width=22)
        time_entry.insert(0, default_dt)
        time_entry.pack(side=tk.LEFT, padx=4)

        ttk.Button(
            time_frame,
            text="+1ч",
            width=4,
            command=lambda: time_entry.delete(0, tk.END)
            or time_entry.insert(
                0,
                (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),
            ),
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            time_frame,
            text="+1д",
            width=4,
            command=lambda: time_entry.delete(0, tk.END)
            or time_entry.insert(
                0,
                (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
            ),
        ).pack(side=tk.LEFT, padx=2)

        error_label = ttk.Label(dialog, text="", foreground="red")
        error_label.pack()

        def save():
            title = title_entry.get().strip()
            description = desc_text.get("1.0", tk.END).strip()
            due_at = time_entry.get().strip()

            if not title:
                error_label.config(text="Введите заголовок")
                return

            # Валидация даты
            try:
                datetime.strptime(due_at, "%Y-%m-%d %H:%M")
            except ValueError:
                error_label.config(text="Формат: ГГГГ-ММ-ДД ЧЧ:ММ")
                return

            db.add_reminder(title, description, due_at)
            dialog.destroy()
            self._refresh_list()
            messagebox.showinfo("Добавлено", f"Напоминание «{title}» добавлено.")

        ttk.Button(dialog, text="Сохранить", command=save).pack(pady=10)

    def _delete_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Удаление", "Выберите напоминание для удаления.")
            return

        values = self.tree.item(selected[0], "values")
        if messagebox.askyesno(
            "Удаление", f"Удалить напоминание «{values[1]}»?"
        ):
            db.delete_reminder(int(values[0]))
            self._refresh_list()

    def _mark_done(self) -> None:
        self._change_status("Готово")

    def _mark_cancelled(self) -> None:
        self._change_status("Отменено")

    def _change_status(self, status: str) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Статус", "Выберите напоминание.")
            return
        values = self.tree.item(selected[0], "values")
        db.update_status(int(values[0]), status)
        self._refresh_list()

    def _on_close(self) -> None:
        notifications.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = ReminderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
