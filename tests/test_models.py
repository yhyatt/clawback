"""Tests for Clawback models."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from clawback.models import (
    CommandType,
    Expense,
    ParsedCommand,
    ParseError,
    PendingConfirmation,
    Settlement,
    Split,
    SplitType,
    Trip,
)


class TestSplit:
    """Tests for Split model."""

    def test_create_split(self) -> None:
        """Test creating a basic split."""
        split = Split(person="Dan", amount=Decimal("50.00"), currency="ILS")
        assert split.person == "Dan"
        assert split.amount == Decimal("50.00")
        assert split.currency == "ILS"

    def test_split_coerces_float(self) -> None:
        """Test that float amounts are converted to Decimal."""
        split = Split(person="Dan", amount=50.00, currency="ILS")  # type: ignore
        assert isinstance(split.amount, Decimal)
        assert split.amount == Decimal("50.0")

    def test_split_serialization(self) -> None:
        """Test that Split serializes amount as string."""
        split = Split(person="Dan", amount=Decimal("50.00"), currency="ILS")
        data = split.model_dump()
        assert data["amount"] == "50.00"


class TestExpense:
    """Tests for Expense model."""

    def test_create_expense(self) -> None:
        """Test creating a basic expense."""
        splits = [
            Split(person="Dan", amount=Decimal("50"), currency="ILS"),
            Split(person="Sara", amount=Decimal("50"), currency="ILS"),
        ]
        expense = Expense(
            description="Dinner",
            amount=Decimal("100"),
            currency="ILS",
            paid_by="Dan",
            splits=splits,
        )
        assert expense.description == "Dinner"
        assert expense.amount == Decimal("100")
        assert len(expense.splits) == 2
        assert isinstance(expense.id, UUID)
        assert isinstance(expense.ts, datetime)

    def test_expense_default_notes(self) -> None:
        """Test that notes defaults to empty string."""
        expense = Expense(
            description="Test",
            amount=Decimal("100"),
            currency="ILS",
            paid_by="Dan",
            splits=[],
        )
        assert expense.notes == ""


class TestSettlement:
    """Tests for Settlement model."""

    def test_create_settlement(self) -> None:
        """Test creating a settlement."""
        settlement = Settlement(
            from_person="Sara",
            to_person="Dan",
            amount=Decimal("50"),
            currency="ILS",
        )
        assert settlement.from_person == "Sara"
        assert settlement.to_person == "Dan"
        assert settlement.amount == Decimal("50")
        assert isinstance(settlement.id, UUID)


class TestTrip:
    """Tests for Trip model."""

    def test_create_trip(self) -> None:
        """Test creating a trip with defaults."""
        trip = Trip(name="Summer Vacation")
        assert trip.name == "Summer Vacation"
        assert trip.base_currency == "ILS"
        assert trip.participants == []
        assert trip.expenses == []
        assert trip.settlements == []
        assert trip.sheet_id is None

    def test_trip_with_participants(self) -> None:
        """Test creating a trip with participants."""
        trip = Trip(
            name="Beach Trip",
            participants=["Dan", "Sara", "Avi"],
            base_currency="EUR",
        )
        assert trip.participants == ["Dan", "Sara", "Avi"]
        assert trip.base_currency == "EUR"

    def test_trip_serialization(self) -> None:
        """Test that Trip can be serialized to JSON."""
        trip = Trip(name="Test", participants=["Dan"])
        data = trip.model_dump(mode="json")
        assert "name" in data
        assert "participants" in data
        assert "created_at" in data


class TestParsedCommand:
    """Tests for ParsedCommand model."""

    def test_create_add_expense_command(self) -> None:
        """Test creating an add expense command."""
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="kai add dinner ₪100 paid by Dan",
            description="dinner",
            amount=Decimal("100"),
            currency="ILS",
            paid_by="Dan",
            split_type=SplitType.EQUAL,
        )
        assert cmd.command_type == CommandType.ADD_EXPENSE
        assert cmd.amount == Decimal("100")

    def test_create_settle_command(self) -> None:
        """Test creating a settle command."""
        cmd = ParsedCommand(
            command_type=CommandType.SETTLE,
            raw_text="kai settle Sara paid Dan ₪50",
            from_person="Sara",
            to_person="Dan",
            amount=Decimal("50"),
            currency="ILS",
        )
        assert cmd.command_type == CommandType.SETTLE
        assert cmd.from_person == "Sara"

    def test_command_with_custom_splits(self) -> None:
        """Test command with custom splits."""
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="test",
            custom_splits={"Dan": Decimal("30"), "Sara": Decimal("70")},
        )
        assert cmd.custom_splits["Dan"] == Decimal("30")


class TestParseError:
    """Tests for ParseError model."""

    def test_create_parse_error(self) -> None:
        """Test creating a parse error."""
        error = ParseError(
            raw_text="gibberish",
            message="Could not understand",
            suggestions=["Try this", "Or this"],
        )
        assert error.raw_text == "gibberish"
        assert len(error.suggestions) == 2


class TestPendingConfirmation:
    """Tests for PendingConfirmation model."""

    def test_create_pending_confirmation(self) -> None:
        """Test creating a pending confirmation."""
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="test",
        )
        pending = PendingConfirmation(
            chat_id="123",
            command=cmd,
            confirmation_text="Confirm?",
            trip_name="Test Trip",
        )
        assert pending.chat_id == "123"
        assert pending.command.command_type == CommandType.ADD_EXPENSE
        assert isinstance(pending.created_at, datetime)
