"""Command handlers - orchestrate parser → ledger → sheets → response.

Write commands (add, settle, undo) require confirmation before execution.
Read commands (balances, summary, who, help) execute directly.
"""

from decimal import Decimal

from . import ledger, templates
from .audit import log_input
from .fx import convert
from .models import (
    CommandType,
    Expense,
    ParsedCommand,
    ParseError,
    PendingConfirmation,
    SplitType,
    Trip,
)
from .parser import parse_command
from .sheets import (
    SheetsError,
    append_expense,
    append_settlement,
    create_sheet,
    get_sheet_url,
    refresh_computed_tabs,
)
from .state import TripManager

# Commands that require confirmation
WRITE_COMMANDS = {CommandType.ADD_EXPENSE, CommandType.SETTLE, CommandType.UNDO, CommandType.TRIP}


def format_fallback(error: ParseError) -> str:
    """
    Format a fallback message for a parse error.

    Uses error-specific templates for better UX.
    """
    return templates.get_fallback_message(error.error_type)


def format_confirmation(cmd: ParsedCommand, trip: Trip | None = None) -> str:
    """
    Format a parsed command as a human-readable confirmation message.

    Args:
        cmd: Parsed command to confirm
        trip: Current trip (for context like participants)

    Returns:
        Confirmation message string
    """
    if cmd.command_type == CommandType.ADD_EXPENSE:
        assert cmd.amount is not None
        assert cmd.currency is not None
        assert cmd.description is not None
        assert cmd.paid_by is not None
        amount_display = templates.format_currency(cmd.amount, cmd.currency)

        if cmd.split_type == SplitType.CUSTOM:
            assert cmd.custom_splits is not None
            splits_summary = ", ".join(
                f"{person} {templates.format_currency(amount, cmd.currency)}"
                for person, amount in cmd.custom_splits.items()
            )
            custom_total = sum(cmd.custom_splits.values())
            if custom_total != cmd.amount:
                diff = cmd.amount - custom_total
                diff_display = templates.format_currency(abs(diff), cmd.currency)
                warn = (
                    f"⚠️ splits sum to "
                    f"{templates.format_currency(custom_total, cmd.currency)}, "
                    f"{'under' if diff > 0 else 'over'} by {diff_display}. "
                )
            else:
                warn = ""
            return templates.CONFIRM_ADD_EXPENSE_CUSTOM.format(
                description=cmd.description,
                amount_display=amount_display,
                paid_by=cmd.paid_by,
                splits_summary=splits_summary,
                warn=warn,
            )

        elif cmd.split_type == SplitType.ONLY:
            assert cmd.split_among is not None
            participants_str = " & ".join(cmd.split_among)
            n = len(cmd.split_among)
            # Single participant who is also the payer → zero net debt
            if n == 1 and cmd.split_among[0].lower() == cmd.paid_by.lower():
                return templates.CONFIRM_ADD_EXPENSE_ONLY_SELF.format(
                    description=cmd.description,
                    amount_display=amount_display,
                    paid_by=cmd.paid_by,
                )
            per_person = templates.format_currency(
                (cmd.amount / n).quantize(Decimal("0.01")),
                cmd.currency,
            )
            return templates.CONFIRM_ADD_EXPENSE_ONLY.format(
                description=cmd.description,
                amount_display=amount_display,
                paid_by=cmd.paid_by,
                participants=participants_str,
                per_person=per_person,
            )

        else:  # EQUAL split
            # Determine participants
            participants_list: list[str]
            if cmd.split_among:
                participants_list = cmd.split_among
            elif trip and trip.participants:
                participants_list = trip.participants
            else:
                # No participants known — ask rather than silently assume
                return templates.CONFIRM_ADD_EXPENSE_EQUAL_UNKNOWN_PARTICIPANTS.format(
                    description=cmd.description,
                    amount_display=amount_display,
                    paid_by=cmd.paid_by,
                )

            splits = ledger.compute_equal_splits(cmd.amount, cmd.currency, participants_list)
            splits_summary = ", ".join(
                f"{s.person} {templates.format_currency(s.amount, s.currency)}" for s in splits
            )
            return templates.CONFIRM_ADD_EXPENSE_EQUAL.format(
                description=cmd.description,
                amount_display=amount_display,
                paid_by=cmd.paid_by,
                splits_summary=splits_summary,
            )

    elif cmd.command_type == CommandType.SETTLE:
        assert cmd.amount is not None
        assert cmd.currency is not None
        assert cmd.from_person is not None
        assert cmd.to_person is not None
        amount_display = templates.format_currency(cmd.amount, cmd.currency)
        return templates.CONFIRM_SETTLE.format(
            from_person=cmd.from_person,
            to_person=cmd.to_person,
            amount_display=amount_display,
        )

    elif cmd.command_type == CommandType.UNDO:
        if trip:
            # Find what would be undone
            last_expense = trip.expenses[-1] if trip.expenses else None
            last_settlement = trip.settlements[-1] if trip.settlements else None

            if last_expense is None and last_settlement is None:
                return templates.NOTHING_TO_UNDO

            if last_settlement is None or (last_expense and last_expense.ts > last_settlement.ts):
                assert last_expense is not None  # Guaranteed by earlier check
                return templates.CONFIRM_UNDO.format(
                    item_type="expense",
                    description=f"{last_expense.description} {templates.format_currency(last_expense.amount, last_expense.currency)}",
                )
            else:
                assert last_settlement is not None  # Guaranteed by condition
                return templates.CONFIRM_UNDO.format(
                    item_type="settlement",
                    description=f"{last_settlement.from_person} → {last_settlement.to_person} {templates.format_currency(last_settlement.amount, last_settlement.currency)}",
                )
        return templates.NOTHING_TO_UNDO

    elif cmd.command_type == CommandType.TRIP:
        assert cmd.trip_name is not None
        currency = cmd.trip_base_currency or "ILS"
        return templates.CONFIRM_TRIP_CREATE.format(
            trip_name=cmd.trip_name,
            currency=currency,
        )

    return f"Confirm: {cmd.raw_text}?"


def is_confirmation(text: str) -> bool:
    """Check if text is a confirmation response."""
    text = text.strip().lower()
    return text in ("yes", "y", "yep", "yeah", "correct", "confirm", "ok", "👍", "✅")


def is_rejection(text: str) -> bool:
    """Check if text is a rejection response."""
    text = text.strip().lower()
    return text in ("no", "n", "nope", "cancel", "wrong", "👎", "❌")


class CommandHandler:
    """
    Handles command execution with confirmation workflow.

    For write commands:
    1. Parse → format confirmation → store pending → return confirmation text
    2. On "yes" → execute pending → return result

    For read commands:
    1. Parse → execute → return result
    """

    def __init__(
        self,
        trip_manager: TripManager,
        sheets_account: str | None = None,
        create_sheets: bool = True,
    ):
        """
        Initialize command handler.

        Args:
            trip_manager: TripManager instance for state
            sheets_account: Google account for Sheets sync
            create_sheets: Whether to create Google Sheets for new trips
        """
        self.trip_manager = trip_manager
        self.sheets_account = sheets_account
        self.create_sheets = create_sheets

    def handle_message(self, chat_id: str, text: str) -> str:
        """
        Handle an incoming message.

        This is the main entry point for processing user messages.

        Args:
            chat_id: Unique identifier for the chat/conversation
            text: User's message text

        Returns:
            Response message to send back
        """
        original_text = text
        text = text.strip()

        # Check if this is a response to a pending confirmation
        pending = self.trip_manager.get_pending(chat_id)
        if pending:
            if is_confirmation(text):
                log_input(original_text, chat_id, "ok")
                return self._execute_pending(chat_id, pending)
            elif is_rejection(text):
                log_input(original_text, chat_id, "ok")
                self.trip_manager.clear_pending(chat_id)
                return "❌ Cancelled."
            # Not a yes/no, treat as new command (clears pending)
            self.trip_manager.clear_pending(chat_id)

        # Parse the command
        result = parse_command(text)

        if isinstance(result, ParseError):
            # Log the failed parse
            log_input(original_text, chat_id, "error", error_msg=result.message)
            # Return error-specific fallback message
            return format_fallback(result)

        # Log successful parse
        log_input(original_text, chat_id, "ok")

        # Get active trip for this chat
        trip = self.trip_manager.get_active_trip(chat_id)

        # Handle based on command type
        if result.command_type in WRITE_COMMANDS:
            return self._handle_write_command(chat_id, result, trip)
        else:
            return self._handle_read_command(chat_id, result, trip)

    def _handle_write_command(
        self,
        chat_id: str,
        cmd: ParsedCommand,
        trip: Trip | None,
    ) -> str:
        """Handle a write command - requires confirmation."""
        # Special case: TRIP command doesn't need an active trip
        if cmd.command_type == CommandType.TRIP:
            assert cmd.trip_name is not None
            # Check if trip already exists
            existing = self.trip_manager.get_trip(cmd.trip_name)
            if existing:
                # Switch to existing trip
                self.trip_manager.set_active_trip(chat_id, cmd.trip_name)
                debts = ledger.simplified_debts(existing, existing.base_currency)
                debts_text = templates.format_debts_list(debts, existing.base_currency)
                return f"📍 Switched to *{cmd.trip_name}*\n\n{debts_text}"

            # New trip - needs confirmation
            confirmation = format_confirmation(cmd, trip)
            self.trip_manager.set_pending(chat_id, cmd, confirmation, cmd.trip_name)
            return confirmation

        # All other write commands need an active trip
        if not trip:
            return templates.ERROR_NO_TRIP

        # Format confirmation and store pending
        confirmation = format_confirmation(cmd, trip)
        self.trip_manager.set_pending(chat_id, cmd, confirmation, trip.name)
        return confirmation

    def _handle_read_command(
        self,
        chat_id: str,
        cmd: ParsedCommand,
        trip: Trip | None,
    ) -> str:
        """Handle a read command - executes immediately."""
        if cmd.command_type == CommandType.HELP:
            return templates.HELP

        # All other read commands need an active trip
        if not trip:
            return templates.ERROR_NO_TRIP

        if cmd.command_type == CommandType.BALANCES:
            currency = cmd.display_currency or trip.base_currency
            debts = ledger.simplified_debts(trip, currency)

            if not debts:
                return templates.ALL_SETTLED

            debts_text = templates.format_debts_list(debts, currency)
            sheet_link = ""
            if trip.sheet_id:
                sheet_link = f"[View sheet]({get_sheet_url(trip.sheet_id)})"

            return templates.BALANCES.format(
                trip_name=trip.name,
                debts=debts_text,
                sheet_link=sheet_link,
            )

        elif cmd.command_type == CommandType.SUMMARY:
            currency = trip.base_currency
            debts = ledger.simplified_debts(trip, currency)
            debts_text = templates.format_debts_list(debts, currency)

            # Calculate total expenses
            total = sum(
                (convert(e.amount, e.currency, currency) for e in trip.expenses),
                Decimal("0"),
            )
            total_display = templates.format_currency(total, currency)

            sheet_link = ""
            if trip.sheet_id:
                sheet_link = f"[View sheet]({get_sheet_url(trip.sheet_id)})"

            return templates.SUMMARY.format(
                trip_name=trip.name,
                participants=", ".join(trip.participants) or "None yet",
                total_expenses=total_display,
                settlement_count=len(trip.settlements),
                debts=debts_text,
                sheet_link=sheet_link,
            )

        elif cmd.command_type == CommandType.WHO:
            if not trip.participants:
                return f"👥 *{trip.name}*\n\nNo participants yet. Add an expense to add people."

            participant_list = "\n".join(f"• {p}" for p in trip.participants)
            return templates.WHO.format(
                trip_name=trip.name,
                participant_list=participant_list,
            )

        return "Unknown command"

    def _execute_pending(self, chat_id: str, pending: PendingConfirmation) -> str:
        """Execute a confirmed pending command."""
        cmd = pending.command
        self.trip_manager.clear_pending(chat_id)

        if cmd.command_type == CommandType.TRIP:
            return self._execute_trip_create(chat_id, cmd)

        # Get trip for execution
        trip = self.trip_manager.get_trip(pending.trip_name)
        if not trip:
            return templates.ERROR_NO_TRIP

        if cmd.command_type == CommandType.ADD_EXPENSE:
            return self._execute_add_expense(chat_id, cmd, trip)
        elif cmd.command_type == CommandType.SETTLE:
            return self._execute_settle(chat_id, cmd, trip)
        elif cmd.command_type == CommandType.UNDO:
            return self._execute_undo(chat_id, trip)

        return "Unknown command"

    def _execute_trip_create(self, chat_id: str, cmd: ParsedCommand) -> str:
        """Execute trip creation."""
        assert cmd.trip_name is not None
        currency = cmd.trip_base_currency or "ILS"
        sheet_id = None
        sheet_info = ""

        # Create Google Sheet if enabled
        if self.create_sheets:
            try:
                sheet_id = create_sheet(cmd.trip_name, self.sheets_account)
                sheet_info = f"📊 [Google Sheet]({get_sheet_url(sheet_id)})"
            except SheetsError as e:
                sheet_info = f"⚠️ Sheet creation failed: {e}"

        # Create trip
        trip = self.trip_manager.create_trip(
            name=cmd.trip_name,
            base_currency=currency,
            sheet_id=sheet_id,
        )

        # Set as active
        self.trip_manager.set_active_trip(chat_id, trip.name)

        return templates.TRIP_CREATED.format(
            trip_name=trip.name,
            currency=currency,
            sheet_info=sheet_info,
        )

    def _execute_add_expense(
        self,
        chat_id: str,
        cmd: ParsedCommand,
        trip: Trip,
    ) -> str:
        """Execute adding an expense."""
        assert cmd.amount is not None
        assert cmd.currency is not None
        assert cmd.description is not None
        assert cmd.paid_by is not None

        # Compute splits based on type
        if cmd.split_type == SplitType.CUSTOM:
            from .models import Split

            assert cmd.custom_splits is not None
            splits = [
                Split(person=person, amount=amount, currency=cmd.currency)
                for person, amount in cmd.custom_splits.items()
            ]
        elif cmd.split_type == SplitType.ONLY:
            assert cmd.split_among is not None
            splits = ledger.compute_equal_splits(
                cmd.amount,
                cmd.currency,
                cmd.split_among,
            )
        else:  # EQUAL
            participants = cmd.split_among or trip.participants
            if not participants:
                participants = [cmd.paid_by]
            splits = ledger.compute_equal_splits(cmd.amount, cmd.currency, participants)

        # Validate and add expense
        try:
            ledger.validate_splits(splits, cmd.amount)
        except ValueError as e:
            return templates.ERROR_VALIDATION.format(message=str(e))

        new_trip, expense = ledger.add_expense(
            trip,
            description=cmd.description,
            amount=cmd.amount,
            currency=cmd.currency,
            paid_by=cmd.paid_by,
            splits=splits,
        )

        # Save trip
        self.trip_manager.save_trip(new_trip)

        # Sync to sheets
        sheets_error = None
        if new_trip.sheet_id:
            try:
                append_expense(new_trip.sheet_id, expense, self.sheets_account)
                balances = ledger.compute_balances(new_trip)
                debts = ledger.simplified_debts(new_trip)
                refresh_computed_tabs(
                    new_trip.sheet_id,
                    new_trip,
                    balances,
                    debts,
                    new_trip.base_currency,
                    self.sheets_account,
                )
            except SheetsError as e:
                sheets_error = str(e)

        # Format response
        amount_display = templates.format_currency(expense.amount, expense.currency)
        splits_summary = ", ".join(
            f"{s.person} {templates.format_currency(s.amount, s.currency)}" for s in expense.splits
        )
        debts = ledger.simplified_debts(new_trip, new_trip.base_currency)
        debts_summary = templates.format_debts_list(debts, new_trip.base_currency)

        response = templates.EXPENSE_ADDED.format(
            description=expense.description,
            amount_display=amount_display,
            paid_by=expense.paid_by,
            splits_summary=splits_summary,
            debts_summary=debts_summary,
        )

        if sheets_error:
            response += "\n\n" + templates.ERROR_SHEETS.format(error=sheets_error)

        return response

    def _execute_settle(
        self,
        chat_id: str,
        cmd: ParsedCommand,
        trip: Trip,
    ) -> str:
        """Execute a settlement."""
        assert cmd.from_person is not None
        assert cmd.to_person is not None
        assert cmd.amount is not None
        assert cmd.currency is not None

        new_trip, settlement = ledger.add_settlement(
            trip,
            from_person=cmd.from_person,
            to_person=cmd.to_person,
            amount=cmd.amount,
            currency=cmd.currency,
        )

        # Save trip
        self.trip_manager.save_trip(new_trip)

        # Sync to sheets
        sheets_error = None
        if new_trip.sheet_id:
            try:
                append_settlement(new_trip.sheet_id, settlement, self.sheets_account)
                balances = ledger.compute_balances(new_trip)
                debts = ledger.simplified_debts(new_trip)
                refresh_computed_tabs(
                    new_trip.sheet_id,
                    new_trip,
                    balances,
                    debts,
                    new_trip.base_currency,
                    self.sheets_account,
                )
            except SheetsError as e:
                sheets_error = str(e)

        # Format response
        amount_display = templates.format_currency(settlement.amount, settlement.currency)
        debts = ledger.simplified_debts(new_trip, new_trip.base_currency)
        debts_summary = templates.format_debts_list(debts, new_trip.base_currency)

        response = templates.SETTLE_ADDED.format(
            from_person=settlement.from_person,
            to_person=settlement.to_person,
            amount_display=amount_display,
            debts_summary=debts_summary,
        )

        if sheets_error:
            response += "\n\n" + templates.ERROR_SHEETS.format(error=sheets_error)

        return response

    def _execute_undo(self, chat_id: str, trip: Trip) -> str:
        """Execute undo of last action."""
        new_trip, removed = ledger.undo_last(trip)

        if removed is None:
            return templates.NOTHING_TO_UNDO

        # Save trip
        self.trip_manager.save_trip(new_trip)

        # Format description
        if isinstance(removed, Expense):
            desc = f"{removed.description} {templates.format_currency(removed.amount, removed.currency)}"
        else:  # Settlement
            desc = f"{removed.from_person} → {removed.to_person} {templates.format_currency(removed.amount, removed.currency)}"

        debts = ledger.simplified_debts(new_trip, new_trip.base_currency)
        debts_summary = templates.format_debts_list(debts, new_trip.base_currency)

        return templates.UNDO_SUCCESS.format(
            description=desc,
            debts_summary=debts_summary,
        )
