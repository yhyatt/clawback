"""Google Sheets sync via gog CLI subprocess."""

import json
import os
import subprocess
from decimal import Decimal
from typing import Any

from .models import Expense, Settlement, Trip


class SheetsError(Exception):
    """Error interacting with Google Sheets."""

    pass


def _run_gog(
    args: list[str],
    account: str | None = None,
    input_data: str | None = None,
) -> dict[str, Any]:
    """
    Run a gog command and return parsed JSON output.

    Args:
        args: Command arguments (without 'gog' prefix)
        account: Google account to use
        input_data: Optional stdin data

    Returns:
        Parsed JSON response

    Raises:
        SheetsError: If command fails
    """
    cmd = ["gog"] + args

    if account:
        cmd.extend(["--account", account])

    env = os.environ.copy()
    # GOG_KEYRING_PASSWORD should be set in environment

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=input_data,
            env=env,
            timeout=30,
        )

        if result.returncode != 0:
            raise SheetsError(f"gog command failed: {result.stderr}")

        # Try to parse JSON output
        if result.stdout.strip():
            try:
                parsed: dict[str, Any] = json.loads(result.stdout)
                return parsed
            except json.JSONDecodeError:
                # Some commands return plain text
                return {"output": result.stdout.strip()}

        return {}

    except subprocess.TimeoutExpired as e:
        raise SheetsError(f"gog command timed out: {e}") from e
    except FileNotFoundError as e:
        raise SheetsError("gog CLI not found. Install with: npm install -g gog") from e


def create_sheet(trip_name: str, account: str | None = None) -> str:
    """
    Create a new Google Sheet for a trip.

    Creates the sheet with 5 tabs:
    - Expenses (append-only)
    - Splits (append-only)
    - Settlements (append-only)
    - Balances (rewritten)
    - Summary (rewritten)

    Args:
        trip_name: Name for the sheet
        account: Google account to use

    Returns:
        Sheet ID
    """
    # Create the spreadsheet
    result = _run_gog(
        ["sheets", "create", f"Clawback - {trip_name}", "--json"],
        account=account,
    )

    sheet_id_value = result.get("spreadsheetId") or result.get("id")
    if not sheet_id_value:
        raise SheetsError("Failed to get sheet ID from create response")
    sheet_id: str = str(sheet_id_value)

    # Add tabs (sheets already has Sheet1, rename it and add others)
    tabs = ["Expenses", "Splits", "Settlements", "Balances", "Summary"]

    for i, tab_name in enumerate(tabs):
        if i == 0:
            # Rename default Sheet1
            _run_gog(
                ["sheets", "rename-tab", sheet_id, "Sheet1", tab_name],
                account=account,
            )
        else:
            _run_gog(
                ["sheets", "add-tab", sheet_id, tab_name],
                account=account,
            )

    # Add headers to each tab
    headers = {
        "Expenses": ["expense_id", "timestamp", "description", "amount", "currency", "paid_by"],
        "Splits": ["expense_id", "person", "amount_owed", "currency"],
        "Settlements": ["settlement_id", "timestamp", "from", "to", "amount", "currency", "notes"],
        "Balances": ["person", "net_balance", "currency"],
        "Summary": ["from", "to", "amount", "currency"],
    }

    for tab_name, header_row in headers.items():
        _run_gog(
            ["sheets", "append", sheet_id, tab_name, "--json"],
            account=account,
            input_data=json.dumps([header_row]),
        )

    return sheet_id


def append_expense(
    sheet_id: str,
    expense: Expense,
    account: str | None = None,
) -> None:
    """
    Append an expense to the Expenses and Splits tabs.

    Args:
        sheet_id: Google Sheet ID
        expense: Expense to append
        account: Google account to use
    """
    # Append to Expenses tab
    expense_row = [
        str(expense.id),
        expense.ts.isoformat(),
        expense.description,
        str(expense.amount),
        expense.currency,
        expense.paid_by,
    ]

    _run_gog(
        ["sheets", "append", sheet_id, "Expenses", "--json"],
        account=account,
        input_data=json.dumps([expense_row]),
    )

    # Append splits to Splits tab
    split_rows = []
    for split in expense.splits:
        split_rows.append(
            [
                str(expense.id),
                split.person,
                str(split.amount),
                split.currency,
            ]
        )

    if split_rows:
        _run_gog(
            ["sheets", "append", sheet_id, "Splits", "--json"],
            account=account,
            input_data=json.dumps(split_rows),
        )


def append_settlement(
    sheet_id: str,
    settlement: Settlement,
    account: str | None = None,
) -> None:
    """
    Append a settlement to the Settlements tab.

    Args:
        sheet_id: Google Sheet ID
        settlement: Settlement to append
        account: Google account to use
    """
    row = [
        str(settlement.id),
        settlement.ts.isoformat(),
        settlement.from_person,
        settlement.to_person,
        str(settlement.amount),
        settlement.currency,
        settlement.notes,
    ]

    _run_gog(
        ["sheets", "append", sheet_id, "Settlements", "--json"],
        account=account,
        input_data=json.dumps([row]),
    )


def refresh_computed_tabs(
    sheet_id: str,
    trip: Trip,
    balances: dict[str, Decimal],
    debts: list[tuple[str, str, Decimal]],
    base_currency: str,
    account: str | None = None,
) -> None:
    """
    Rewrite the Balances and Summary tabs with current data.

    Args:
        sheet_id: Google Sheet ID
        trip: Trip data
        balances: Current balances per person
        debts: Simplified debt list
        base_currency: Currency for display
        account: Google account to use
    """
    # Clear and rewrite Balances tab
    _run_gog(
        ["sheets", "clear", sheet_id, "Balances", "--range", "A2:Z1000"],
        account=account,
    )

    balance_rows = [["person", "net_balance", "currency"]]
    for person, balance in sorted(balances.items()):
        balance_rows.append([person, str(balance), base_currency])

    _run_gog(
        ["sheets", "write", sheet_id, "Balances", "--range", "A1", "--json"],
        account=account,
        input_data=json.dumps(balance_rows),
    )

    # Clear and rewrite Summary tab
    _run_gog(
        ["sheets", "clear", sheet_id, "Summary", "--range", "A2:Z1000"],
        account=account,
    )

    summary_rows = [["from", "to", "amount", "currency"]]
    for debtor, creditor, amount in debts:
        summary_rows.append([debtor, creditor, str(amount), base_currency])

    _run_gog(
        ["sheets", "write", sheet_id, "Summary", "--range", "A1", "--json"],
        account=account,
        input_data=json.dumps(summary_rows),
    )


def get_sheet_url(sheet_id: str) -> str:
    """Get the URL for a Google Sheet."""
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}"
