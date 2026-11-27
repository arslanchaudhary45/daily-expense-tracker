# Daily Expense Tracker

A command-line tool to track daily income and expenses by category, with
summaries and monthly reports. Records are stored in `expenses.json` next
to the code. Python 3.12, standard library only — no third-party packages
for the CLI; the web app adds Flask.

## Setup

```bash
cd daily-expense-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Web app

```bash
cd daily-expense-tracker
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser. The web app covers the
same features as the command line: add income/expense records, list them
with type, category and month filters, see income/expense/balance stat
cards and per-category breakdowns, and view a monthly report for any
`YYYY-MM`. Set the `PORT` environment variable to run on a different port.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests in `tests/` cover the service layer in `expense.py`: adding
records, validation errors, list filters, deleting records, summaries
and monthly reports, and corrupted data files.

## Architecture

- `expense.py` — the service layer: record rules, validation and storage
  (typed functions, `ExpenseError` on bad input). The `cmd_*` functions
  at the bottom are thin command-line wrappers around it.
- `app.py` — the Flask web UI: thin routes that validate HTTP input
  and call the service. No record rules live in the routes.
- `templates/` + `static/` — the web pages and the shared design
  system (same layout, colors and components as the other projects).
- `expenses.json` — the data file (created on first use).

## How to run

```bash
cd daily-expense-tracker
python3 expense.py --help
```

## Commands

### Add a record

```bash
python3 expense.py add expense 2500 --category food --date 2026-11-27 --note "Groceries"
python3 expense.py add income 150000 --category salary --date 2026-11-01 --note "Nov salary"
python3 expense.py add expense 300 --category transport   # date defaults to today
```

The first argument is the type (`income` or `expense`), the second is the
amount (must be positive). `--category` is required; `--date` is `YYYY-MM-DD`
(default: today); `--note` is optional.

### List records

```bash
python3 expense.py list
python3 expense.py list --type expense
python3 expense.py list --category food
python3 expense.py list --month 2026-11
```

The list ends with totals for the records shown (income, expenses, balance).

### Summary (totals by category)

```bash
python3 expense.py summary                # all time
python3 expense.py summary --month 2026-11
```

### Monthly report

```bash
python3 expense.py report 2026-11
```

Prints, for the given `YYYY-MM`: number of records, income total, expense
total, balance, and per-category breakdowns (with percentages) for both
income and expenses.

## Data

Records are saved in `expenses.json` in this folder. Each record has an id,
type (`income`/`expense`), amount, category, date and note.
