#!/usr/bin/env python3
"""Daily Expense Tracker — web UI (Flask).

Thin routes only: each handler parses and validates its HTTP input,
calls one service function from :mod:`expense`, then renders a page or
redirects. All rules (validation, ids, totals, categories) live in
``expense.py``; nothing about records is decided here.

Run it with:

    pip install -r requirements.txt
    python app.py

Then open http://127.0.0.1:5000 in your browser.
Set the PORT environment variable to use a different port.
The command-line app still works exactly as before: python3 expense.py --help
"""

from __future__ import annotations

import os
import sys
from datetime import date

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import expense

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-key")

APP_NAME = "Daily Expense Tracker"
APP_TAGLINE = "Income and expenses by category, with summaries and monthly reports"


def parse_date_field(value: str | None) -> date | None:
    """Parse a ``YYYY-MM-DD`` form value; ``None`` when blank.

    Raises :class:`expense.ExpenseError` on a malformed date.
    """
    value = (value or "").strip()
    if not value:
        return None
    return expense.parse_date(value)


@app.context_processor
def inject_globals() -> dict:
    """Make the app name and tagline available to every template."""
    return {"app_name": APP_NAME, "app_tagline": APP_TAGLINE}


@app.route("/")
def index() -> str:
    """Dashboard: stat cards, add-record form, filtered records,
    per-category summary and the monthly report."""
    type_filter = request.args.get("type", "")
    category_filter = request.args.get("category", "").strip()
    month_filter = request.args.get("month", "").strip()
    report_month = request.args.get("report_month", "").strip()
    if not report_month:
        report_month = date.today().strftime("%Y-%m")
    try:
        records = expense.list_records(
            record_type=type_filter or None,
            category=category_filter or None,
            month=month_filter or None, reverse=True)
    except expense.ExpenseError as exc:
        flash(str(exc), "error")
        records = []
    stats = expense.summarize_records(records)
    try:
        report = expense.monthly_report(report_month)
    except expense.ExpenseError as exc:
        flash(str(exc), "error")
        report = expense.monthly_report(date.today())
    return render_template(
        "index.html", records=records, stats=stats,
        expense_totals=stats["expense_totals"],
        income_totals=stats["income_totals"],
        categories=expense.categories(), type_filter=type_filter,
        category_filter=category_filter, month_filter=month_filter,
        report=report, fmt=expense.fmt, today=date.today().isoformat())


@app.route("/add", methods=["POST"])
def add() -> str:
    """Add a record from the dashboard form, then go back to the list."""
    try:
        amount = float(request.form.get("amount", ""))
    except ValueError:
        flash("Amount must be a number.", "error")
        return redirect(url_for("index"))
    try:
        record_date = parse_date_field(request.form.get("date"))
        record = expense.add_record(
            request.form.get("type", "expense"), amount,
            request.form.get("category", ""), record_date,
            request.form.get("note", ""))
    except expense.ExpenseError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))
    flash(f"Added {record['type']} [{record['id']}] "
          f"{expense.fmt(record['amount'])} in '{record['category']}' "
          f"on {record['date']}.", "success")
    return redirect(url_for("index"))


@app.route("/delete/<int:record_id>", methods=["POST"])
def delete(record_id: int) -> str:
    """Delete a record, then go back to the list."""
    try:
        record = expense.delete_record(record_id)
    except expense.ExpenseError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))
    flash(f"Deleted {record['type']} [{record_id}] "
          f"{expense.fmt(record['amount'])}.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port)
