"""Tests for Clawback commands - end-to-end command handling."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clawback.commands import (
    CommandHandler,
    format_confirmation,
    is_confirmation,
    is_rejection,
)
from clawback.models import CommandType, ParsedCommand, SplitType, Trip
from clawback.state import TripManager


class TestConfirmationHelpers:
    """Tests for confirmation/rejection detection."""

    def test_is_confirmation(self) -> None:
        """Test confirmation detection."""
        assert is_confirmation("yes")
        assert is_confirmation("Yes")
        assert is_confirmation("YES")
        assert is_confirmation("y")
        assert is_confirmation("yep")
        assert is_confirmation("yeah")
        assert is_confirmation("correct")
        assert is_confirmation("confirm")
        assert is_confirmation("ok")
        assert is_confirmation("👍")
        assert is_confirmation("✅")
        assert is_confirmation("  yes  ")  # With whitespace

    def test_is_not_confirmation(self) -> None:
        """Test non-confirmations."""
        assert not is_confirmation("no")
        assert not is_confirmation("maybe")
        assert not is_confirmation("yesss")  # Extra chars
        assert not is_confirmation("kai add")

    def test_is_rejection(self) -> None:
        """Test rejection detection."""
        assert is_rejection("no")
        assert is_rejection("No")
        assert is_rejection("NO")
        assert is_rejection("n")
        assert is_rejection("nope")
        assert is_rejection("cancel")
        assert is_rejection("wrong")
        assert is_rejection("👎")
        assert is_rejection("❌")

    def test_is_not_rejection(self) -> None:
        """Test non-rejections."""
        assert not is_rejection("yes")
        assert not is_rejection("maybe")


class TestFormatConfirmation:
    """Tests for confirmation message formatting."""

    def test_format_add_expense_equal(self) -> None:
        """Test formatting equal split expense confirmation."""
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="kai add Dinner ₪340 paid by Yonatan",
            description="Dinner",
            amount=Decimal("340"),
            currency="ILS",
            paid_by="Yonatan",
            split_type=SplitType.EQUAL,
            split_among=["Yonatan", "Dan", "Sara", "Avi"],
        )
        trip = Trip(name="Test", participants=["Yonatan", "Dan", "Sara", "Avi"])

        result = format_confirmation(cmd, trip)

        assert "Dinner" in result
        assert "₪340" in result
        assert "Yonatan" in result
        assert "yes/no" in result

    def test_format_add_expense_only(self) -> None:
        """Test formatting 'only' split expense confirmation."""
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="test",
            description="Wine",
            amount=Decimal("60"),
            currency="EUR",
            paid_by="Dan",
            split_type=SplitType.ONLY,
            split_among=["Dan", "Yonatan"],
        )

        result = format_confirmation(cmd)

        assert "Wine" in result
        assert "€60" in result
        assert "Dan & Yonatan" in result
        assert "each €30" in result

    def test_format_add_expense_custom(self) -> None:
        """Test formatting custom split expense confirmation."""
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="test",
            description="Gifts",
            amount=Decimal("100"),
            currency="ILS",
            paid_by="Sara",
            split_type=SplitType.CUSTOM,
            custom_splits={"Dan": Decimal("30"), "Sara": Decimal("70")},
        )

        result = format_confirmation(cmd)

        assert "Gifts" in result
        assert "custom split" in result
        assert "Dan" in result
        assert "Sara" in result

    def test_format_settle(self) -> None:
        """Test formatting settlement confirmation."""
        cmd = ParsedCommand(
            command_type=CommandType.SETTLE,
            raw_text="test",
            from_person="Dan",
            to_person="Yonatan",
            amount=Decimal("200"),
            currency="ILS",
        )

        result = format_confirmation(cmd)

        assert "Dan → Yonatan" in result
        assert "₪200" in result
        assert "Mark as paid" in result

    def test_format_trip_create(self) -> None:
        """Test formatting trip creation confirmation."""
        cmd = ParsedCommand(
            command_type=CommandType.TRIP,
            raw_text="test",
            trip_name="Beach Vacation",
            trip_base_currency="EUR",
        )

        result = format_confirmation(cmd)

        assert "Beach Vacation" in result
        assert "EUR" in result
        assert "Create new trip" in result


class TestCommandHandler:
    """Tests for CommandHandler end-to-end flows."""

    @pytest.fixture
    def handler(self, temp_state_dir: Path) -> CommandHandler:
        """Create a handler with mocked sheets."""
        manager = TripManager(temp_state_dir)
        return CommandHandler(manager, create_sheets=False)

    def test_help_command(self, handler: CommandHandler) -> None:
        """Test help command returns help text."""
        response = handler.handle_message("chat1", "kai help")
        assert "Clawback" in response
        assert "Add expenses" in response

    def test_no_active_trip_error(self, handler: CommandHandler) -> None:
        """Test error when no active trip for commands that need one."""
        response = handler.handle_message("chat1", "kai balances")
        assert "No active trip" in response

    def test_trip_creation_flow(self, handler: CommandHandler) -> None:
        """Test full trip creation flow with confirmation."""
        # Send trip command
        response = handler.handle_message("chat1", "kai trip Beach Vacation")
        assert "Create new trip" in response
        assert "yes/no" in response

        # Confirm
        response = handler.handle_message("chat1", "yes")
        assert "Trip" in response
        assert "Beach Vacation" in response
        assert "created" in response

    def test_trip_creation_cancel(self, handler: CommandHandler) -> None:
        """Test trip creation cancellation."""
        handler.handle_message("chat1", "kai trip Test Trip")
        response = handler.handle_message("chat1", "no")
        assert "Cancelled" in response

    def test_switch_to_existing_trip(self, handler: CommandHandler) -> None:
        """Test switching to an existing trip."""
        # Create trip first
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")

        # Switch to it from another chat
        response = handler.handle_message("chat2", "kai trip Test Trip")
        assert "Switched to" in response

    def test_add_expense_flow(self, handler: CommandHandler) -> None:
        """Test full add expense flow."""
        # Create trip
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")

        # Add expense
        response = handler.handle_message(
            "chat1", "kai add Dinner ₪300 paid by Dan only Dan, Sara, Avi"
        )
        assert "Got it" in response
        assert "Dinner" in response
        assert "₪300" in response

        # Confirm
        response = handler.handle_message("chat1", "yes")
        assert "✅" in response
        assert "Dinner" in response

    def test_settle_flow(self, handler: CommandHandler) -> None:
        """Test full settlement flow."""
        # Setup: create trip and add expense
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")
        handler.handle_message("chat1", "kai add Dinner ₪100 paid by Dan only Dan, Sara")
        handler.handle_message("chat1", "yes")

        # Settle
        response = handler.handle_message("chat1", "kai settle Sara paid Dan ₪50")
        assert "Settle" in response
        assert "Sara → Dan" in response

        # Confirm
        response = handler.handle_message("chat1", "yes")
        assert "✅" in response
        assert "settled" in response

    def test_balances_command(self, handler: CommandHandler) -> None:
        """Test balances command after expenses."""
        # Setup
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")
        handler.handle_message("chat1", "kai add Dinner ₪100 paid by Dan only Dan, Sara")
        handler.handle_message("chat1", "yes")

        # Check balances
        response = handler.handle_message("chat1", "kai balances")
        assert "Balances" in response
        assert "Sara → Dan" in response

    def test_summary_command(self, handler: CommandHandler) -> None:
        """Test summary command."""
        # Setup
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")
        handler.handle_message("chat1", "kai add Dinner ₪100 paid by Dan only Dan, Sara")
        handler.handle_message("chat1", "yes")

        response = handler.handle_message("chat1", "kai summary")
        assert "Summary" in response
        assert "Participants" in response
        assert "Total expenses" in response

    def test_who_command(self, handler: CommandHandler) -> None:
        """Test who command."""
        # Setup
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")
        handler.handle_message("chat1", "kai add Dinner ₪100 paid by Dan only Dan, Sara")
        handler.handle_message("chat1", "yes")

        response = handler.handle_message("chat1", "kai who")
        assert "Participants" in response
        assert "Dan" in response
        assert "Sara" in response

    def test_undo_flow(self, handler: CommandHandler) -> None:
        """Test undo command flow."""
        # Setup
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")
        handler.handle_message("chat1", "kai add Dinner ₪100 paid by Dan only Dan, Sara")
        handler.handle_message("chat1", "yes")

        # Undo
        response = handler.handle_message("chat1", "kai undo")
        assert "Undo last" in response

        # Confirm
        response = handler.handle_message("chat1", "yes")
        assert "Undid" in response

    def test_new_command_clears_pending(self, handler: CommandHandler) -> None:
        """Test that sending a new command clears pending confirmation."""
        # Create trip
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")

        # Start an expense
        handler.handle_message("chat1", "kai add Dinner ₪100 paid by Dan only Dan, Sara")

        # Send new command instead of yes/no
        response = handler.handle_message("chat1", "kai help")
        assert "Clawback" in response  # Help shown, not expense

    def test_parse_error_response(self, handler: CommandHandler) -> None:
        """Test error response for unparseable command."""
        response = handler.handle_message("chat1", "gibberish asdfgh")
        assert "Didn't understand" in response
        assert "Try:" in response

    def test_all_settled_message(self, handler: CommandHandler) -> None:
        """Test 'all settled' message when no debts."""
        # Setup: create trip with balanced expense
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")
        handler.handle_message("chat1", "kai add Dinner ₪100 paid by Dan only Dan")
        handler.handle_message("chat1", "yes")

        response = handler.handle_message("chat1", "kai balances")
        assert "settled up" in response

    @patch("clawback.commands.create_sheet")
    def test_sheets_integration(self, mock_create: MagicMock, temp_state_dir: Path) -> None:
        """Test sheets integration when enabled."""
        mock_create.return_value = "sheet-123"

        manager = TripManager(temp_state_dir)
        handler = CommandHandler(manager, create_sheets=True)

        # Create trip
        handler.handle_message("chat1", "kai trip Test Trip")
        response = handler.handle_message("chat1", "yes")

        assert mock_create.called
        assert "Google Sheet" in response or "sheet-123" in response

    def test_undo_settlement(self, handler: CommandHandler) -> None:
        """Test undoing a settlement (not expense)."""
        # Setup: create trip, add expense, settle
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")
        handler.handle_message("chat1", "kai add Dinner ₪100 paid by Dan only Dan, Sara")
        handler.handle_message("chat1", "yes")
        handler.handle_message("chat1", "kai settle Sara paid Dan ₪50")
        handler.handle_message("chat1", "yes")

        # Undo - should undo settlement (most recent)
        response = handler.handle_message("chat1", "kai undo")
        assert "settlement" in response.lower() or "Sara → Dan" in response

    def test_undo_nothing_to_undo(self, handler: CommandHandler) -> None:
        """Test undo when nothing to undo."""
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")

        response = handler.handle_message("chat1", "kai undo")
        assert "Nothing to undo" in response

    def test_format_undo_settlement_confirmation(self) -> None:
        """Test formatting undo confirmation for a settlement."""
        from clawback.models import Settlement

        trip = Trip(name="Test", participants=["Dan", "Sara"])
        settlement = Settlement(
            from_person="Sara",
            to_person="Dan",
            amount=Decimal("50"),
            currency="ILS",
        )
        trip.settlements.append(settlement)

        cmd = ParsedCommand(
            command_type=CommandType.UNDO,
            raw_text="kai undo",
        )

        result = format_confirmation(cmd, trip)
        assert "settlement" in result.lower()
        assert "Sara → Dan" in result

    def test_equal_split_uses_trip_participants(self, handler: CommandHandler) -> None:
        """Test that equal split uses trip participants when none specified."""
        handler.handle_message("chat1", "kai trip Test Trip")
        handler.handle_message("chat1", "yes")

        # Add first expense with specific people
        handler.handle_message("chat1", "kai add Dinner ₪100 paid by Dan only Dan, Sara, Avi")
        handler.handle_message("chat1", "yes")

        # Add second expense without specifying split - should use trip participants
        response = handler.handle_message("chat1", "kai add Lunch ₪90 paid by Sara")
        # Should show all 3 participants in the confirmation
        assert "Dan" in response
        assert "Sara" in response
        assert "Avi" in response

    @patch("clawback.commands.create_sheet")
    def test_sheets_creation_failure(self, mock_create: MagicMock, temp_state_dir: Path) -> None:
        """Test handling of sheets creation failure."""
        from clawback.sheets import SheetsError

        mock_create.side_effect = SheetsError("Auth failed")

        manager = TripManager(temp_state_dir)
        handler = CommandHandler(manager, create_sheets=True)

        handler.handle_message("chat1", "kai trip Test Trip")
        response = handler.handle_message("chat1", "yes")

        # Trip should still be created, just with warning about sheets
        assert "Test Trip" in response
        assert "failed" in response.lower() or "created" in response

    @patch("clawback.commands.append_expense")
    def test_sheets_append_failure(self, mock_append: MagicMock, temp_state_dir: Path) -> None:
        """Test handling of sheets append failure."""
        from clawback.sheets import SheetsError

        mock_append.side_effect = SheetsError("Network error")

        manager = TripManager(temp_state_dir)
        # Create trip with sheet_id manually
        manager.create_trip("Test Trip", sheet_id="test-sheet")
        manager.set_active_trip("chat1", "Test Trip")

        handler = CommandHandler(manager, create_sheets=False)

        handler.handle_message("chat1", "kai add Dinner ₪100 paid by Dan only Dan, Sara")
        response = handler.handle_message("chat1", "yes")

        # Expense should be added, with sheets error message
        assert "✅" in response
        assert "Sheets sync failed" in response or "sync failed" in response.lower()

    def test_format_confirmation_fallback(self) -> None:
        """Test format_confirmation fallback for unknown command type."""
        # Create a command that doesn't match any specific formatter
        cmd = ParsedCommand(
            command_type=CommandType.HELP,  # HELP doesn't have special formatting
            raw_text="some text",
        )

        result = format_confirmation(cmd)
        assert "Confirm:" in result or "some text" in result
