import sqlite3
import unittest

from app.db import init_db
from app.services import (
    add_expense,
    expense_icon,
    get_monthly_expenses,
    get_recurring,
    get_recurring_summary,
    seed_month_if_new,
    toggle_recurring_payment,
    update_expense,
)


class ServicesRegressionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def test_manual_expenses_are_not_replaced_by_recurring_seed(self):
        add_expense(self.conn, 2500, "Mercado", "Alimentação", "2024-01-05", "2024-01")
        seed_month_if_new(self.conn, "2024-01")
        self.assertEqual(len(get_monthly_expenses(self.conn, "2024-01")), 1)

    def test_recurring_summary_and_toggle_are_valid(self):
        recurring = get_recurring(self.conn, "2024-01")
        self.assertGreater(len(recurring), 0)

        summary = get_recurring_summary(recurring)
        self.assertTrue(summary["total_cents"] > 0)
        self.assertEqual(summary["pending_cents"], summary["total_cents"])

        toggle_recurring_payment(self.conn, recurring[0]["id"], "2024-01")
        updated = get_recurring(self.conn, "2024-01")
        self.assertTrue(any(item["id"] == recurring[0]["id"] and item["paid"] for item in updated))

    def test_expense_category_can_be_updated_and_icons_match_descriptions(self):
        add_expense(self.conn, 10000, "Internet residencial", "Contas e Serviços", "2024-01-05", "2024-01")
        expense_id = self.conn.execute("SELECT id FROM expenses").fetchone()[0]
        update_expense(self.conn, expense_id, 10000, "Moradia")
        category = self.conn.execute("SELECT category FROM expenses WHERE id = ?", (expense_id,)).fetchone()[0]
        self.assertEqual(category, "Moradia")
        self.assertEqual(expense_icon("Internet residencial", "Contas e Serviços"), "📶")


if __name__ == "__main__":
    unittest.main()
