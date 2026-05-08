from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings
from app.db import connect_database, init_db
from app.services import (
    CATEGORIES,
    add_expense,
    add_income,
    add_recurring,
    delete_expense,
    delete_income,
    delete_recurring,
    format_month_label,
    get_monthly_expenses,
    get_monthly_income,
    get_monthly_summary,
    get_recurring,
    list_available_months,
    money_label,
    parse_money_to_cents,
    seed_month_if_new,
    update_expense_amount,
    update_recurring_amount,
)


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["money"] = money_label
templates.env.filters["month_label"] = format_month_label


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = connect_database(resolved_settings.database_url)
        init_db(conn)
        conn.close()
        yield

    app = FastAPI(title="Controle de Despesas", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.add_middleware(SessionMiddleware, secret_key=resolved_settings.session_secret)
    app.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "static")),
        name="static",
    )

    def open_conn():
        conn = connect_database(resolved_settings.database_url)
        try:
            yield conn
        finally:
            conn.close()

    def is_logged_in(request: Request) -> bool:
        return bool(request.session.get("logged_in"))

    def require_login(request: Request) -> None:
        if not is_logged_in(request):
            raise LoginRequired()

    def render_dashboard(
        request: Request,
        conn,
        month: str,
        *,
        status_message: str | None = None,
        error_message: str | None = None,
    ) -> HTMLResponse:
        summary = get_monthly_summary(conn, month)
        income_list = get_monthly_income(conn, month)
        expenses_list = get_monthly_expenses(conn, month)
        available_months = list_available_months(conn)
        recurring = get_recurring(conn)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "summary": summary,
                "income_list": income_list,
                "expenses_list": expenses_list,
                "available_months": available_months,
                "current_month": month,
                "categories": CATEGORIES,
                "today": date.today().isoformat(),
                "recurring": recurring,
                "status_message": status_message,
                "error_message": error_message,
            },
        )

    @app.exception_handler(LoginRequired)
    async def login_required_handler(request: Request, exc: LoginRequired):
        return RedirectResponse(url=str(request.url_for("login_form")), status_code=303)

    @app.get("/healthz", name="healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.get("/login", response_class=HTMLResponse, name="login_form")
    async def login_form(request: Request) -> HTMLResponse:
        if is_logged_in(request):
            return RedirectResponse(url=str(request.url_for("dashboard")), status_code=303)
        return templates.TemplateResponse(request, "login.html", {"error": None})

    @app.post("/login", name="login")
    async def login(request: Request, password: str = Form(...)):
        if secure_text_equals(password, resolved_settings.admin_password):
            request.session["logged_in"] = True
            return RedirectResponse(url=str(request.url_for("dashboard")), status_code=303)
        return templates.TemplateResponse(
            request, "login.html", {"error": "Senha incorreta."}, status_code=401
        )

    @app.post("/logout", name="logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse(url=str(request.url_for("login_form")), status_code=303)

    @app.get("/", response_class=HTMLResponse, name="dashboard")
    async def dashboard(
        request: Request,
        month: str | None = None,
        status: str | None = None,
        conn=Depends(open_conn),
        _: None = Depends(require_login),
    ) -> HTMLResponse:
        if not month:
            month = date.today().strftime("%Y-%m")
        seed_month_if_new(conn, month)
        msg = _status_message(status)
        return render_dashboard(request, conn, month, status_message=msg)

    # ── Renda ──────────────────────────────────────────────────────────────────

    @app.post("/income", name="add_income_route")
    async def post_income(
        request: Request,
        amount: str = Form(...),
        description: str = Form(...),
        month: str = Form(...),
        conn=Depends(open_conn),
        _: None = Depends(require_login),
    ):
        try:
            cents = parse_money_to_cents(amount)
            add_income(conn, cents, description, month)
        except ValueError as exc:
            return render_dashboard(request, conn, month, error_message=str(exc))
        return RedirectResponse(
            url=f"{request.url_for('dashboard')}?month={month}&status=income_added",
            status_code=303,
        )

    @app.post("/income/{income_id}/delete", name="delete_income_route")
    async def post_delete_income(
        request: Request,
        income_id: int,
        month: str = Form(...),
        conn=Depends(open_conn),
        _: None = Depends(require_login),
    ):
        delete_income(conn, income_id)
        return RedirectResponse(
            url=f"{request.url_for('dashboard')}?month={month}&status=income_deleted",
            status_code=303,
        )

    # ── Despesas ───────────────────────────────────────────────────────────────

    @app.post("/expenses", name="add_expense_route")
    async def post_expense(
        request: Request,
        amount: str = Form(...),
        description: str = Form(...),
        category: str = Form(...),
        expense_date: str = Form(...),
        month: str = Form(...),
        conn=Depends(open_conn),
        _: None = Depends(require_login),
    ):
        try:
            cents = parse_money_to_cents(amount)
            add_expense(conn, cents, description, category, expense_date, month)
        except ValueError as exc:
            return render_dashboard(request, conn, month, error_message=str(exc))
        return RedirectResponse(
            url=f"{request.url_for('dashboard')}?month={month}&status=expense_added",
            status_code=303,
        )

    @app.post("/expenses/{expense_id}/edit", name="edit_expense_route")
    async def post_edit_expense(
        request: Request,
        expense_id: int,
        amount: str = Form(...),
        month: str = Form(...),
        conn=Depends(open_conn),
        _: None = Depends(require_login),
    ):
        try:
            cents = parse_money_to_cents(amount)
            update_expense_amount(conn, expense_id, cents)
        except ValueError as exc:
            return render_dashboard(request, conn, month, error_message=str(exc))
        return RedirectResponse(
            url=f"{request.url_for('dashboard')}?month={month}&status=expense_edited",
            status_code=303,
        )

    @app.post("/expenses/{expense_id}/delete", name="delete_expense_route")
    async def post_delete_expense(
        request: Request,
        expense_id: int,
        month: str = Form(...),
        conn=Depends(open_conn),
        _: None = Depends(require_login),
    ):
        delete_expense(conn, expense_id)
        return RedirectResponse(
            url=f"{request.url_for('dashboard')}?month={month}&status=expense_deleted",
            status_code=303,
        )

    # ── Recorrentes ────────────────────────────────────────────────────────────

    @app.post("/recurring", name="add_recurring_route")
    async def post_add_recurring(
        request: Request,
        amount: str = Form(...),
        description: str = Form(...),
        category: str = Form(...),
        month: str = Form(...),
        conn=Depends(open_conn),
        _: None = Depends(require_login),
    ):
        try:
            cents = parse_money_to_cents(amount)
            add_recurring(conn, description, cents, category)
        except ValueError as exc:
            return render_dashboard(request, conn, month, error_message=str(exc))
        return RedirectResponse(
            url=f"{request.url_for('dashboard')}?month={month}&status=recurring_added",
            status_code=303,
        )

    @app.post("/recurring/{recurring_id}/edit", name="edit_recurring_route")
    async def post_edit_recurring(
        request: Request,
        recurring_id: int,
        amount: str = Form(...),
        month: str = Form(...),
        conn=Depends(open_conn),
        _: None = Depends(require_login),
    ):
        try:
            cents = parse_money_to_cents(amount)
            update_recurring_amount(conn, recurring_id, cents)
        except ValueError as exc:
            return render_dashboard(request, conn, month, error_message=str(exc))
        return RedirectResponse(
            url=f"{request.url_for('dashboard')}?month={month}&status=recurring_edited",
            status_code=303,
        )

    @app.post("/recurring/{recurring_id}/delete", name="delete_recurring_route")
    async def post_delete_recurring(
        request: Request,
        recurring_id: int,
        month: str = Form(...),
        conn=Depends(open_conn),
        _: None = Depends(require_login),
    ):
        delete_recurring(conn, recurring_id)
        return RedirectResponse(
            url=f"{request.url_for('dashboard')}?month={month}&status=recurring_deleted",
            status_code=303,
        )

    return app


class LoginRequired(Exception):
    pass


def _status_message(status: str | None) -> str | None:
    messages = {
        "income_added":      "Renda registrada com sucesso.",
        "income_deleted":    "Renda removida.",
        "expense_added":     "Despesa registrada com sucesso.",
        "expense_deleted":   "Despesa removida.",
        "expense_edited":    "Valor da despesa atualizado.",
        "recurring_added":   "Despesa recorrente adicionada.",
        "recurring_edited":  "Valor da recorrente atualizado.",
        "recurring_deleted": "Despesa recorrente removida.",
    }
    return messages.get(status or "")


def secure_text_equals(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


app = create_app()
