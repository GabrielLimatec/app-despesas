from __future__ import annotations

import sqlite3
from datetime import date


CATEGORIES = [
    "Alimentação",
    "Moradia",
    "Transporte",
    "Saúde",
    "Lazer",
    "Educação",
    "Vestuário",
    "Contas e Serviços",
    "Outros",
]

CATEGORY_ICONS = {
    "Alimentação": "🍴",
    "Moradia": "⌂",
    "Transporte": "🚗",
    "Saúde": "♥",
    "Lazer": "♪",
    "Educação": "🎓",
    "Vestuário": "◇",
    "Contas e Serviços": "⚡",
    "Outros": "•",
}


def money_label(cents: int) -> str:
    value = cents / 100
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def category_icon(category: str) -> str:
    return CATEGORY_ICONS.get(category, "•")


def parse_money_to_cents(raw: str) -> int:
    cleaned = raw.strip().replace("R$", "").strip()
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError(f"Valor inválido: {raw!r}")
    if value <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    return round(value * 100)


# ── Renda ──────────────────────────────────────────────────────────────────────

def add_income(conn: sqlite3.Connection, amount_cents: int, description: str, category: str, month: str) -> None:
    conn.execute(
        "INSERT INTO income (amount_cents, description, category, month) VALUES (?, ?, ?, ?)",
        (amount_cents, description, category, month),
    )
    conn.commit()


def delete_income(conn: sqlite3.Connection, income_id: int) -> None:
    conn.execute("DELETE FROM income WHERE id = ?", (income_id,))
    conn.commit()


def update_income_amount(conn: sqlite3.Connection, income_id: int, amount_cents: int) -> None:
    conn.execute(
        "UPDATE income SET amount_cents = ? WHERE id = ?",
        (amount_cents, income_id),
    )
    conn.commit()


def get_monthly_income(conn: sqlite3.Connection, month: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM income WHERE month = ? ORDER BY created_at DESC",
        (month,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Despesas ───────────────────────────────────────────────────────────────────

def add_expense(
    conn: sqlite3.Connection,
    amount_cents: int,
    description: str,
    category: str,
    expense_date: str,
    month: str,
) -> None:
    conn.execute(
        "INSERT INTO expenses (amount_cents, description, category, expense_date, month) VALUES (?, ?, ?, ?, ?)",
        (amount_cents, description, category, expense_date, month),
    )
    conn.commit()


def update_expense_amount(conn: sqlite3.Connection, expense_id: int, amount_cents: int) -> None:
    conn.execute(
        "UPDATE expenses SET amount_cents = ? WHERE id = ?",
        (amount_cents, expense_id),
    )
    conn.commit()


def delete_expense(conn: sqlite3.Connection, expense_id: int) -> None:
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()


def get_monthly_expenses(conn: sqlite3.Connection, month: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM expenses WHERE month = ? ORDER BY description COLLATE NOCASE ASC",
        (month,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Recorrentes ────────────────────────────────────────────────────────────────

def get_recurring(conn: sqlite3.Connection, month: str | None = None) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM recurring_expenses ORDER BY sort_order, id"
    ).fetchall()
    items = [dict(r) for r in rows]
    target_month = month or date.today().strftime("%Y-%m")
    paid_ids = {
        row[0]
        for row in conn.execute(
            "SELECT recurring_id FROM recurring_payments WHERE month = ?",
            (target_month,),
        ).fetchall()
    }
    for item in items:
        item["paid"] = item["id"] in paid_ids
    return items


def add_recurring(
    conn: sqlite3.Connection,
    description: str,
    amount_cents: int,
    category: str,
    due_day: int = 1,
) -> None:
    if not 1 <= due_day <= 31:
        raise ValueError("O dia de vencimento deve estar entre 1 e 31.")
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM recurring_expenses"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO recurring_expenses (description, amount_cents, category, due_day, sort_order) VALUES (?, ?, ?, ?, ?)",
        (description, amount_cents, category, due_day, max_order + 1),
    )
    conn.commit()


def update_recurring_amount(
    conn: sqlite3.Connection, recurring_id: int, amount_cents: int, due_day: int = 1
) -> None:
    if not 1 <= due_day <= 31:
        raise ValueError("O dia de vencimento deve estar entre 1 e 31.")
    conn.execute(
        "UPDATE recurring_expenses SET amount_cents = ?, due_day = ? WHERE id = ?",
        (amount_cents, due_day, recurring_id),
    )
    conn.commit()


def delete_recurring(conn: sqlite3.Connection, recurring_id: int) -> None:
    conn.execute("DELETE FROM recurring_expenses WHERE id = ?", (recurring_id,))
    conn.commit()


def get_recurring_summary(recurring: list[dict]) -> dict:
    total = sum(item.get("amount_cents", 0) for item in recurring)
    paid = sum(item.get("amount_cents", 0) for item in recurring if item.get("paid"))
    pending = total - paid
    return {
        "total_cents": total,
        "paid_cents": paid,
        "pending_cents": pending,
    }


def toggle_recurring_payment(conn: sqlite3.Connection, recurring_id: int, month: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM recurring_payments WHERE recurring_id = ? AND month = ?",
        (recurring_id, month),
    ).fetchone()
    if row:
        conn.execute(
            "DELETE FROM recurring_payments WHERE recurring_id = ? AND month = ?",
            (recurring_id, month),
        )
    else:
        conn.execute(
            "INSERT INTO recurring_payments (recurring_id, month) VALUES (?, ?)",
            (recurring_id, month),
        )
    conn.commit()


def seed_month_if_new(conn: sqlite3.Connection, month: str) -> None:
    already = conn.execute(
        "SELECT 1 FROM seeded_months WHERE month = ?", (month,)
    ).fetchone()
    if already:
        return

    conn.execute("INSERT INTO seeded_months (month) VALUES (?)", (month,))
    conn.commit()


# ── Resumo ─────────────────────────────────────────────────────────────────────

def get_monthly_summary(conn: sqlite3.Connection, month: str) -> dict:
    total_income = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM income WHERE month = ?", (month,)
    ).fetchone()[0]

    total_expenses = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM expenses WHERE month = ?", (month,)
    ).fetchone()[0]

    balance = total_income - total_expenses
    pct = round((total_expenses / total_income * 100)) if total_income > 0 else 0

    category_rows = conn.execute(
        """
        SELECT category, COALESCE(SUM(amount_cents), 0) as total
        FROM expenses
        WHERE month = ?
        GROUP BY category
        ORDER BY total DESC
        """,
        (month,),
    ).fetchall()

    return {
        "total_income_cents": total_income,
        "total_expenses_cents": total_expenses,
        "balance_cents": balance,
        "spent_pct": pct,
        "by_category": [dict(r) for r in category_rows],
    }


def list_available_months(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT month FROM income
        UNION
        SELECT DISTINCT month FROM expenses
        UNION
        SELECT DISTINCT month FROM seeded_months
        ORDER BY month DESC
        """
    ).fetchall()
    months = [r[0] for r in rows]
    current = date.today().strftime("%Y-%m")
    if current not in months:
        months.insert(0, current)
    return months


def format_month_label(month: str) -> str:
    names = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    try:
        year, m = month.split("-")
        return f"{names[int(m) - 1]} {year}"
    except Exception:
        return month
