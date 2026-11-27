"""Unit tests for the Daily Expense Tracker service layer (expense.py).

Run from the project folder with:

    pip install -r requirements-dev.txt
    pytest

Tests use a temporary data file (``expense.DATA_FILE`` is pointed at
``tmp_path``), so they never touch the real ``expenses.json``.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

import expense


@pytest.fixture(autouse=True)
def isolated_data_file(tmp_path, monkeypatch):
    """Point the service at a fresh temporary data file per test."""
    monkeypatch.setattr(expense, "DATA_FILE", str(tmp_path / "expenses.json"))


def test_add_record_defaults_to_today():
    """A new record gets an id, today's date and an empty note by default."""
    record = expense.add_record("expense", 2500, "food")
    assert record["id"] == 1
    assert record["type"] == "expense"
    assert record["amount"] == 2500
    assert record["category"] == "food"
    assert record["date"] == date.today().isoformat()
    assert record["note"] == ""


def test_add_record_stores_given_date_note_and_rounds():
    """Given dates/notes are stored; amounts round to two decimals."""
    record = expense.add_record("income", 150000.456, " salary ",
                                date(2026, 11, 1), " Nov salary ")
    assert record["amount"] == 150000.46
    assert record["category"] == "salary"
    assert record["date"] == "2026-11-01"
    assert record["note"] == "Nov salary"


def test_add_record_rejects_bad_type():
    """Anything outside income/expense is refused."""
    with pytest.raises(expense.ExpenseError, match="Invalid type"):
        expense.add_record("gift", 100, "food")


def test_add_record_rejects_non_positive_amount():
    """Zero and negative amounts are refused."""
    with pytest.raises(expense.ExpenseError, match="greater than 0"):
        expense.add_record("expense", 0, "food")
    with pytest.raises(expense.ExpenseError, match="greater than 0"):
        expense.add_record("expense", -50, "food")


def test_add_record_rejects_non_numeric_amount():
    """A non-numeric amount is refused with a clear error."""
    with pytest.raises(expense.ExpenseError, match="must be a number"):
        expense.add_record("expense", "lots", "food")


def test_add_record_rejects_blank_category():
    """A blank category is refused."""
    with pytest.raises(expense.ExpenseError, match="Category is required"):
        expense.add_record("expense", 100, "   ")


def test_ids_increment():
    """Ids keep increasing across adds."""
    first = expense.add_record("expense", 100, "food")
    second = expense.add_record("income", 200, "salary")
    assert (first["id"], second["id"]) == (1, 2)


def test_list_records_filters_and_sorts():
    """Type, category and month filters work; rows sort by date then id."""
    expense.add_record("expense", 300, "food", date(2026, 11, 27))
    expense.add_record("income", 5000, "salary", date(2026, 11, 1))
    expense.add_record("expense", 150, "Food", date(2026, 10, 5))
    assert [r["id"] for r in expense.list_records(record_type="expense")] == [3, 1]
    assert [r["id"] for r in expense.list_records(category="FOOD")] == [3, 1]
    assert [r["id"] for r in expense.list_records(month="2026-11")] == [2, 1]
    assert [r["id"] for r in expense.list_records(
        record_type="expense", month="2026-11")] == [1]
    assert [r["id"] for r in expense.list_records(reverse=True)] == [1, 2, 3]


def test_list_records_rejects_bad_type():
    """An unknown type filter raises instead of silently misbehaving."""
    with pytest.raises(expense.ExpenseError, match="Invalid type"):
        expense.list_records(record_type="gift")


def test_list_records_empty_store():
    """An empty store lists nothing."""
    assert expense.list_records() == []


def test_delete_record_removes_and_missing_raises():
    """Deleting removes the record; a missing id is an error."""
    expense.add_record("expense", 100, "food")
    deleted = expense.delete_record(1)
    assert deleted["category"] == "food"
    assert expense.load_records() == []
    with pytest.raises(expense.ExpenseError, match="No record with id 1"):
        expense.delete_record(1)


def test_summarize_records_totals():
    """Summaries count income, expense, balance and per-category totals."""
    expense.add_record("income", 1000, "salary", date(2026, 11, 1))
    expense.add_record("expense", 300, "food", date(2026, 11, 2))
    expense.add_record("expense", 100, "food", date(2026, 11, 3))
    expense.add_record("expense", 50, "transport", date(2026, 11, 4))
    result = expense.summarize_records(expense.load_records())
    assert result["income"] == 1000
    assert result["expense"] == 450
    assert result["balance"] == 550
    assert result["count"] == 4
    assert result["expense_totals"] == {"food": 400, "transport": 50}
    assert result["income_totals"] == {"salary": 1000}


def test_summary_all_time_and_month():
    """Summary covers all time by default and one month when asked."""
    expense.add_record("expense", 100, "food", date(2026, 10, 5))
    expense.add_record("expense", 200, "food", date(2026, 11, 5))
    all_time = expense.summary()
    assert all_time["month"] is None
    assert all_time["expense"] == 300
    november = expense.summary("2026-11")
    assert november["month"] == "2026-11"
    assert november["expense"] == 200
    assert november["count"] == 1


def test_summary_rejects_bad_month():
    """A malformed month is an error, not an empty summary."""
    with pytest.raises(expense.ExpenseError, match="invalid month"):
        expense.summary("2026-13")
    with pytest.raises(expense.ExpenseError, match="invalid month"):
        expense.summary("November")


def test_monthly_report_by_string_and_date():
    """Monthly reports accept a YYYY-MM string or a date."""
    expense.add_record("income", 1000, "salary", date(2026, 11, 1))
    expense.add_record("expense", 100, "food", date(2026, 12, 1))
    report = expense.monthly_report("2026-11")
    assert report["month"] == "2026-11"
    assert report["count"] == 1
    assert report["income"] == 1000
    assert report["expense"] == 0
    assert expense.monthly_report(date(2026, 12, 15))["month"] == "2026-12"


def test_monthly_report_empty_month():
    """A month with no records reports zeroes."""
    report = expense.monthly_report("2026-11")
    assert report == {"count": 0, "income": 0, "expense": 0, "balance": 0,
                      "expense_totals": {}, "income_totals": {},
                      "month": "2026-11"}


def test_monthly_report_rejects_bad_month():
    """A malformed month is an error."""
    with pytest.raises(expense.ExpenseError, match="invalid month"):
        expense.monthly_report("11/2026")


def test_categories_lists_unique_sorted():
    """Categories are the sorted unique categories in the store."""
    expense.add_record("expense", 100, "food")
    expense.add_record("expense", 50, "transport")
    expense.add_record("income", 1000, "food")
    assert expense.categories() == ["food", "transport"]


def test_parse_date_valid_and_invalid():
    """Valid dates parse; anything else raises ExpenseError."""
    assert expense.parse_date("2026-11-27") == date(2026, 11, 27)
    with pytest.raises(expense.ExpenseError, match="expected YYYY-MM-DD"):
        expense.parse_date("27/11/2026")
    with pytest.raises(expense.ExpenseError, match="expected YYYY-MM-DD"):
        expense.parse_date("2026-02-30")


def test_parse_month_valid_and_invalid():
    """Valid months parse to day 1; anything else raises ExpenseError."""
    assert expense.parse_month("2026-11") == date(2026, 11, 1)
    with pytest.raises(expense.ExpenseError, match="expected YYYY-MM"):
        expense.parse_month("2026-13")
    with pytest.raises(expense.ExpenseError, match="expected YYYY-MM"):
        expense.parse_month("Nov 2026")


def test_load_records_survives_corrupted_file(tmp_path, monkeypatch):
    """A corrupted expenses.json starts empty instead of crashing."""
    bad_file = tmp_path / "expenses.json"
    bad_file.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(expense, "DATA_FILE", str(bad_file))
    assert expense.load_records() == []


def test_load_records_survives_non_list_file(tmp_path, monkeypatch):
    """A JSON file holding a non-list starts empty instead of crashing."""
    bad_file = tmp_path / "expenses.json"
    bad_file.write_text('{"a": 1}', encoding="utf-8")
    monkeypatch.setattr(expense, "DATA_FILE", str(bad_file))
    assert expense.load_records() == []


def test_save_and_load_round_trip():
    """Saved records load back exactly."""
    expense.add_record("expense", 2500, "food", date(2026, 11, 27),
                       "Groceries")
    stored = json.loads(open(expense.DATA_FILE, encoding="utf-8").read())
    assert stored[0]["note"] == "Groceries"
    assert expense.load_records()[0]["note"] == "Groceries"
