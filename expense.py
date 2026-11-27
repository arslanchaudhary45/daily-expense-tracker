#!/usr/bin/env python3
"""Daily Expense Tracker — income and expenses by category, with
summaries and monthly reports. Records are stored in ``expenses.json``
next to this file. Standard library only.

Architecture
------------
This module is the **service layer**: pure functions that own the data
and the rules (``load_records`` / ``save_records`` plus ``add_record``,
``list_records``, ``delete_record``, ``summarize_records``,
``summary`` and ``monthly_report``). They raise :class:`ExpenseError`
on bad input or a missing record instead of printing or exiting, so
the command-line app and the Flask web app (``app.py``) can both use
them.

The ``cmd_*`` functions at the bottom are the thin command-line
wrappers: they turn parsed arguments into service calls and print the
results. ``app.py`` does the same for HTTP requests.

Usage examples:
    python3 expense.py add expense 2500 --category food --date 2026-11-27 --note "Groceries"
    python3 expense.py add income 150000 --category salary --date 2026-11-01 --note "Nov salary"
    python3 expense.py list --type expense --category food
    python3 expense.py summary
    python3 expense.py report 2026-11
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expenses.json")

RECORD_TYPES = ("income", "expense")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class ExpenseError(ValueError):
    """Raised when an expense operation is invalid (bad input, missing record)."""


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_records() -> list[dict]:
    """Load all records from :data:`DATA_FILE`.

    Returns an empty list when the file does not exist yet, and also
    when it is corrupted (a warning is printed to stderr in that case).
    """
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {DATA_FILE} is corrupted; starting with an "
                  "empty list.", file=sys.stderr)
            return []
    return data if isinstance(data, list) else []


def save_records(records: list[dict]) -> None:
    """Persist ``records`` to :data:`DATA_FILE` as indented JSON."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Pure helpers (no I/O)
# ---------------------------------------------------------------------------

def parse_date(value: str, name: str = "date") -> date:
    """Parse a ``YYYY-MM-DD`` string into a :class:`datetime.date`.

    Raises :class:`ExpenseError` on bad input. (``argparse`` treats a
    ``ValueError`` from a ``type=`` callable as an invalid value, so
    this doubles as the CLI date parser.)
    """
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ExpenseError(f"invalid {name} {value!r}: expected YYYY-MM-DD")


def parse_month(value: str) -> date:
    """Parse a ``YYYY-MM`` string into a date (day 1 of that month).

    Raises :class:`ExpenseError` on bad input. (``argparse`` treats a
    ``ValueError`` from a ``type=`` callable as an invalid value, so
    this doubles as the CLI month parser.)
    """
    try:
        parsed = datetime.strptime(value, "%Y-%m").date()
    except ValueError:
        raise ExpenseError(f"invalid month {value!r}: expected YYYY-MM")
    return parsed


def _validate_month(value: str) -> str:
    """Return ``value`` when it is a ``YYYY-MM`` month, else raise."""
    if not _MONTH_RE.match(value or ""):
        raise ExpenseError(f"invalid month {value!r}: expected YYYY-MM")
    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError:
        raise ExpenseError(f"invalid month {value!r}: expected YYYY-MM")
    return value


def next_id(records: list[dict]) -> int:
    """Return the next free record id for ``records``."""
    return max((r["id"] for r in records), default=0) + 1


def find_record(records: list[dict], record_id: int) -> dict | None:
    """Return the record with ``record_id``, or ``None`` when missing."""
    for record in records:
        if record["id"] == record_id:
            return record
    return None


def fmt(amount: float) -> str:
    """Format an amount with thousands separators and two decimals."""
    return f"{amount:,.2f}"


def format_record(record: dict) -> str:
    """Render one record as a single line for the command line."""
    sign = "+" if record["type"] == "income" else "-"
    note = f" | {record['note']}" if record.get("note") else ""
    return (f"[{record['id']}] {record['date']}  {sign}{fmt(record['amount'])}  "
            f"{record['type']:7} {record['category']}{note}")


def totals_by_category(records: list[dict], record_type: str) -> dict[str, float]:
    """Return ``{category: total}`` for ``record_type``, largest first."""
    totals: dict[str, float] = {}
    for r in records:
        if r["type"] == record_type:
            totals[r["category"]] = totals.get(r["category"], 0) + r["amount"]
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def summarize_records(records: list[dict]) -> dict:
    """Return totals for ``records``: income, expense, balance, count
    and per-category breakdowns for both types."""
    total_in = sum(r["amount"] for r in records if r["type"] == "income")
    total_out = sum(r["amount"] for r in records if r["type"] == "expense")
    return {
        "count": len(records),
        "income": total_in,
        "expense": total_out,
        "balance": total_in - total_out,
        "expense_totals": totals_by_category(records, "expense"),
        "income_totals": totals_by_category(records, "income"),
    }


def categories() -> list[str]:
    """Return the sorted unique categories of all stored records."""
    return sorted({r["category"] for r in load_records()})


def print_category_breakdown(totals: dict[str, float], grand_total: float,
                             label: str) -> None:
    """Print one per-category breakdown (with shares) for the CLI."""
    if not totals:
        print(f"  (no {label} records)")
        return
    for category, amount in totals.items():
        pct = (amount / grand_total * 100) if grand_total else 0
        print(f"  {category:<20} {fmt(amount):>12}  ({pct:5.1f}%)")


# ---------------------------------------------------------------------------
# Service operations (load, validate, mutate, save, return the result)
# ---------------------------------------------------------------------------

def add_record(record_type: str, amount: float,
               category: str, record_date: date | None = None,
               note: str = "") -> dict:
    """Create a record, persist it and return it.

    Raises :class:`ExpenseError` when the type is not ``income`` /
    ``expense``, the amount is not greater than 0, or the category is
    blank. ``record_date`` defaults to today.
    """
    if record_type not in RECORD_TYPES:
        raise ExpenseError(f"Invalid type {record_type!r}: "
                           f"expected one of {', '.join(RECORD_TYPES)}.")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ExpenseError("Amount must be a number.")
    if amount <= 0:
        raise ExpenseError("Amount must be greater than 0.")
    category = (category or "").strip()
    if not category:
        raise ExpenseError("Category is required.")
    records = load_records()
    record = {
        "id": next_id(records),
        "type": record_type,
        "amount": round(amount, 2),
        "category": category,
        "date": (record_date or date.today()).isoformat(),
        "note": (note or "").strip(),
    }
    records.append(record)
    save_records(records)
    return record


def list_records(record_type: str | None = None,
                 category: str | None = None,
                 month: str | None = None,
                 reverse: bool = False) -> list[dict]:
    """Return records filtered by type, category and/or month prefix,
    sorted by date then id (newest first when ``reverse`` is true).

    Raises :class:`ExpenseError` on an unknown record type.
    """
    if record_type is not None and record_type not in RECORD_TYPES:
        raise ExpenseError(f"Invalid type {record_type!r}: "
                           f"expected one of {', '.join(RECORD_TYPES)}.")
    records = load_records()
    if record_type:
        records = [r for r in records if r["type"] == record_type]
    if category:
        records = [r for r in records
                   if r["category"].lower() == category.lower()]
    if month:
        records = [r for r in records if r["date"].startswith(month)]
    records.sort(key=lambda r: (r["date"], r["id"]), reverse=reverse)
    return records


def delete_record(record_id: int) -> dict:
    """Delete a record and return it.

    Raises :class:`ExpenseError` when the record is missing.
    """
    records = load_records()
    record = find_record(records, record_id)
    if record is None:
        raise ExpenseError(f"No record with id {record_id}.")
    records.remove(record)
    save_records(records)
    return record


def summary(month: str | None = None) -> dict:
    """Return totals for one month (``YYYY-MM``) or all time.

    The result is :func:`summarize_records` plus a ``"month"`` key
    (the month, or ``None`` for all time).
    """
    if month:
        _validate_month(month)
    records = list_records(month=month) if month else load_records()
    result = summarize_records(records)
    result["month"] = month
    return result


def monthly_report(month: str | date) -> dict:
    """Return the monthly report for ``month`` (``YYYY-MM`` or a date).

    The result is :func:`summarize_records` for that month plus a
    ``"month"`` key holding the ``YYYY-MM`` string. Raises
    :class:`ExpenseError` on a malformed month.
    """
    if isinstance(month, date):
        month_str = month.strftime("%Y-%m")
    else:
        month_str = _validate_month(str(month))
    result = summarize_records(list_records(month=month_str))
    result["month"] = month_str
    return result


# ---------------------------------------------------------------------------
# Command-line wrappers (thin: arguments -> service -> printed output)
# ---------------------------------------------------------------------------

def cmd_add(args: argparse.Namespace) -> int:
    """Add a record from parsed CLI arguments."""
    try:
        record = add_record(args.type, args.amount, args.category,
                            args.date, args.note)
    except ExpenseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Added {record['type']} [{record['id']}] "
          f"{fmt(record['amount'])} in '{record['category']}' on {record['date']}.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List records from parsed CLI arguments."""
    try:
        records = list_records(args.type, args.category, args.month)
    except ExpenseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not records:
        print("No records found.")
        return 0
    for record in records:
        print(format_record(record))
    totals = summarize_records(records)
    print(f"\nShowing {len(records)} record(s): "
          f"income {fmt(totals['income'])}, "
          f"expenses {fmt(totals['expense'])}, "
          f"balance {fmt(totals['balance'])}")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    """Print the summary (totals by category) from CLI arguments."""
    try:
        result = summary(args.month)
    except ExpenseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    scope = f" for {args.month}" if args.month else " (all time)"
    print(f"Summary{scope}")
    print(f"  Total income:  {fmt(result['income'])}")
    print(f"  Total expense: {fmt(result['expense'])}")
    print(f"  Balance:       {fmt(result['balance'])}")
    print("  Expenses by category:")
    print_category_breakdown(result["expense_totals"], result["expense"],
                             "expense")
    print("  Income by category:")
    print_category_breakdown(result["income_totals"], result["income"],
                             "income")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Print the monthly report from parsed CLI arguments."""
    try:
        result = monthly_report(args.month)
    except ExpenseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    month = result["month"]
    print(f"Monthly report — {month}")
    print(f"  Records:       {result['count']}")
    print(f"  Total income:  {fmt(result['income'])}")
    print(f"  Total expense: {fmt(result['expense'])}")
    print(f"  Balance:       {fmt(result['balance'])}")
    print("  Expenses by category:")
    print_category_breakdown(result["expense_totals"], result["expense"],
                             "expense")
    print("  Income by category:")
    print_category_breakdown(result["income_totals"], result["income"],
                             "income")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="expense.py",
        description="Daily Expense Tracker — income, expenses, categories "
                    "and monthly reports.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add an income or expense record.")
    p_add.add_argument("type", choices=("income", "expense"),
                       help="Record type.")
    p_add.add_argument("amount", type=float, help="Amount (must be positive).")
    p_add.add_argument("--category", required=True,
                       help="Category, e.g. food, transport, salary, rent.")
    p_add.add_argument("--date", type=parse_date, default=None,
                       help="Date as YYYY-MM-DD (default: today).")
    p_add.add_argument("--note", default=None, help="Optional note.")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List records.")
    p_list.add_argument("--type", choices=("income", "expense"), default=None,
                        help="Filter by type.")
    p_list.add_argument("--category", default=None, help="Filter by category.")
    p_list.add_argument("--month", type=str, default=None,
                        help="Filter by month as YYYY-MM.")
    p_list.set_defaults(func=cmd_list)

    p_summary = sub.add_parser("summary", help="Totals by category.")
    p_summary.add_argument("--month", type=str, default=None,
                           help="Limit to a month as YYYY-MM.")
    p_summary.set_defaults(func=cmd_summary)

    p_report = sub.add_parser("report", help="Monthly report for YYYY-MM.")
    p_report.add_argument("month", type=parse_month,
                          help="Month as YYYY-MM, e.g. 2026-11.")
    p_report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the command-line app."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "amount", None) is not None and args.amount <= 0:
        parser.error("amount must be greater than 0")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
