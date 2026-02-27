"""Tests for Clawback sheets module - Google Sheets sync."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from clawback.models import Expense, Settlement, Split, Trip
from clawback.sheets import (
    SheetsError,
    append_expense,
    append_settlement,
    create_sheet,
    get_sheet_url,
    refresh_computed_tabs,
)


class TestCreateSheet:
    """Tests for create_sheet function."""

    @patch("clawback.sheets.subprocess.run")
    def test_create_sheet_success(self, mock_run: MagicMock) -> None:
        """Test successful sheet creation."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"spreadsheetId": "abc123"}'
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        sheet_id = create_sheet("Test Trip")

        assert sheet_id == "abc123"
        # Should call: create, rename-tab, 4x add-tab, 5x append (headers)
        assert mock_run.call_count >= 6

    @patch("clawback.sheets.subprocess.run")
    def test_create_sheet_with_account(self, mock_run: MagicMock) -> None:
        """Test sheet creation with account parameter."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"spreadsheetId": "abc123"}'
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        create_sheet("Test Trip", account="test@example.com")

        # Check that --account was passed
        calls = mock_run.call_args_list
        first_call_args = calls[0][1]["args"] if "args" in calls[0][1] else calls[0][0][0]
        assert "--account" in first_call_args

    @patch("clawback.sheets.subprocess.run")
    def test_create_sheet_error(self, mock_run: MagicMock) -> None:
        """Test sheet creation error handling."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Authentication failed"
        mock_run.return_value = mock_result

        with pytest.raises(SheetsError, match="gog command failed"):
            create_sheet("Test Trip")

    @patch("clawback.sheets.subprocess.run")
    def test_create_sheet_no_id_in_response(self, mock_run: MagicMock) -> None:
        """Test error when no sheet ID in response."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "{}"  # No spreadsheetId
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        with pytest.raises(SheetsError, match="Failed to get sheet ID"):
            create_sheet("Test Trip")


class TestAppendExpense:
    """Tests for append_expense function."""

    @patch("clawback.sheets.subprocess.run")
    def test_append_expense(self, mock_run: MagicMock) -> None:
        """Test appending an expense."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "{}"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        expense = Expense(
            description="Dinner",
            amount=Decimal("100"),
            currency="ILS",
            paid_by="Dan",
            splits=[
                Split(person="Dan", amount=Decimal("50"), currency="ILS"),
                Split(person="Sara", amount=Decimal("50"), currency="ILS"),
            ],
        )

        append_expense("sheet-123", expense)

        # Should call twice: once for expense, once for splits
        assert mock_run.call_count == 2

    @patch("clawback.sheets.subprocess.run")
    def test_append_expense_with_account(self, mock_run: MagicMock) -> None:
        """Test appending expense with account."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "{}"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        expense = Expense(
            description="Test",
            amount=Decimal("100"),
            currency="ILS",
            paid_by="Dan",
            splits=[],
        )

        append_expense("sheet-123", expense, account="test@example.com")

        calls = mock_run.call_args_list
        first_call_args = calls[0][1]["args"] if "args" in calls[0][1] else calls[0][0][0]
        assert "--account" in first_call_args


class TestAppendSettlement:
    """Tests for append_settlement function."""

    @patch("clawback.sheets.subprocess.run")
    def test_append_settlement(self, mock_run: MagicMock) -> None:
        """Test appending a settlement."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "{}"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        settlement = Settlement(
            from_person="Sara",
            to_person="Dan",
            amount=Decimal("50"),
            currency="ILS",
        )

        append_settlement("sheet-123", settlement)

        assert mock_run.call_count == 1


class TestRefreshComputedTabs:
    """Tests for refresh_computed_tabs function."""

    @patch("clawback.sheets.subprocess.run")
    def test_refresh_computed_tabs(self, mock_run: MagicMock) -> None:
        """Test refreshing computed tabs."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "{}"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        trip = Trip(name="Test", participants=["Dan", "Sara"])
        balances = {"Dan": Decimal("50"), "Sara": Decimal("-50")}
        debts = [("Sara", "Dan", Decimal("50"))]

        refresh_computed_tabs("sheet-123", trip, balances, debts, "ILS")

        # Should call: clear balances, write balances, clear summary, write summary
        assert mock_run.call_count == 4


class TestGetSheetUrl:
    """Tests for get_sheet_url function."""

    def test_get_sheet_url(self) -> None:
        """Test URL generation."""
        url = get_sheet_url("abc123xyz")
        assert url == "https://docs.google.com/spreadsheets/d/abc123xyz"


class TestGogNotFound:
    """Tests for gog CLI not found error."""

    @patch("clawback.sheets.subprocess.run")
    def test_gog_not_found(self, mock_run: MagicMock) -> None:
        """Test error when gog CLI not found."""
        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(SheetsError, match="gog CLI not found"):
            create_sheet("Test Trip")
