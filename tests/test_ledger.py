"""Tests for Clawback ledger - pure financial logic."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from clawback import ledger
from clawback.models import Expense, Settlement, Split, Trip


class TestValidateSplits:
    """Tests for split validation."""

    def test_valid_splits(self) -> None:
        """Test that valid splits pass validation."""
        splits = [
            Split(person="Dan", amount=Decimal("50"), currency="ILS"),
            Split(person="Sara", amount=Decimal("50"), currency="ILS"),
        ]
        # Should not raise
        ledger.validate_splits(splits, Decimal("100"))

    def test_invalid_splits_too_low(self) -> None:
        """Test that splits that sum too low fail."""
        splits = [
            Split(person="Dan", amount=Decimal("40"), currency="ILS"),
            Split(person="Sara", amount=Decimal("50"), currency="ILS"),
        ]
        with pytest.raises(ValueError, match="Splits sum to"):
            ledger.validate_splits(splits, Decimal("100"))

    def test_invalid_splits_too_high(self) -> None:
        """Test that splits that sum too high fail."""
        splits = [
            Split(person="Dan", amount=Decimal("60"), currency="ILS"),
            Split(person="Sara", amount=Decimal("50"), currency="ILS"),
        ]
        with pytest.raises(ValueError, match="Splits sum to"):
            ledger.validate_splits(splits, Decimal("100"))

    def test_splits_within_tolerance(self) -> None:
        """Test that splits within 0.01 tolerance pass."""
        splits = [
            Split(person="Dan", amount=Decimal("33.33"), currency="ILS"),
            Split(person="Sara", amount=Decimal("33.33"), currency="ILS"),
            Split(person="Avi", amount=Decimal("33.33"), currency="ILS"),
        ]
        # Sum is 99.99, total is 100, diff is 0.01 - should pass
        ledger.validate_splits(splits, Decimal("100"))


class TestComputeEqualSplits:
    """Tests for equal split computation."""

    def test_even_split(self) -> None:
        """Test evenly divisible split."""
        splits = ledger.compute_equal_splits(Decimal("100"), "ILS", ["Dan", "Sara"])
        assert len(splits) == 2
        assert splits[0].amount == Decimal("50.00")
        assert splits[1].amount == Decimal("50.00")

    def test_uneven_split_three_ways(self) -> None:
        """Test ₪100 split 3 ways → ₪33.33, ₪33.33, ₪33.34."""
        splits = ledger.compute_equal_splits(Decimal("100"), "ILS", ["Dan", "Sara", "Avi"])
        assert len(splits) == 3
        # First two get rounded share
        assert splits[0].amount == Decimal("33.33")
        assert splits[1].amount == Decimal("33.33")
        # Last gets remainder (ensures exact sum)
        assert splits[2].amount == Decimal("33.34")
        # Total should be exactly 100
        total = sum(s.amount for s in splits)
        assert total == Decimal("100")

    def test_uneven_split_four_ways(self) -> None:
        """Test ₪100 split 4 ways."""
        splits = ledger.compute_equal_splits(Decimal("100"), "ILS", ["A", "B", "C", "D"])
        total = sum(s.amount for s in splits)
        assert total == Decimal("100")

    def test_single_person_split(self) -> None:
        """Test split among one person."""
        splits = ledger.compute_equal_splits(Decimal("100"), "ILS", ["Dan"])
        assert len(splits) == 1
        assert splits[0].amount == Decimal("100")

    def test_zero_participants_raises(self) -> None:
        """Test that empty participants list raises error."""
        with pytest.raises(ValueError, match="zero participants"):
            ledger.compute_equal_splits(Decimal("100"), "ILS", [])


class TestComputeBalances:
    """Tests for balance computation."""

    def test_single_expense_equal_split(self) -> None:
        """Test balances with one expense split equally."""
        trip = Trip(name="Test", participants=["Dan", "Sara"])
        trip.expenses.append(
            Expense(
                description="Dinner",
                amount=Decimal("100"),
                currency="ILS",
                paid_by="Dan",
                splits=[
                    Split(person="Dan", amount=Decimal("50"), currency="ILS"),
                    Split(person="Sara", amount=Decimal("50"), currency="ILS"),
                ],
            )
        )

        balances = ledger.compute_balances(trip)

        # Dan paid 100, owes 50 → net +50
        assert balances["Dan"] == Decimal("50")
        # Sara paid 0, owes 50 → net -50
        assert balances["Sara"] == Decimal("-50")

    def test_multiple_expenses(self, trip_with_expenses: Trip) -> None:
        """Test balances with multiple expenses."""
        # From fixture:
        # Dan paid 300, owes 100+50=150 → net +150
        # Sara paid 150, owes 100+50=150 → net 0
        # Avi paid 0, owes 100+50=150 → net -150
        balances = ledger.compute_balances(trip_with_expenses)

        assert balances["Dan"] == Decimal("150")
        assert balances["Sara"] == Decimal("0")
        assert balances["Avi"] == Decimal("-150")

    def test_settlement_affects_balances(self) -> None:
        """Test that settlements reduce debts."""
        trip = Trip(name="Test", participants=["Dan", "Sara"])
        trip.expenses.append(
            Expense(
                description="Dinner",
                amount=Decimal("100"),
                currency="ILS",
                paid_by="Dan",
                splits=[
                    Split(person="Dan", amount=Decimal("50"), currency="ILS"),
                    Split(person="Sara", amount=Decimal("50"), currency="ILS"),
                ],
            )
        )
        # Sara pays Dan ₪30
        trip.settlements.append(
            Settlement(
                from_person="Sara",
                to_person="Dan",
                amount=Decimal("30"),
                currency="ILS",
            )
        )

        balances = ledger.compute_balances(trip)

        # Dan: +50 (expense) - 30 (received) = +20
        assert balances["Dan"] == Decimal("20")
        # Sara: -50 (expense) + 30 (paid) = -20
        assert balances["Sara"] == Decimal("-20")

    @patch("clawback.ledger.convert")
    def test_multi_currency_conversion(self, mock_convert) -> None:
        """Test that multi-currency expenses are converted."""

        # Mock conversion: 1 EUR = 4 ILS
        def side_effect(amount, from_ccy, to_ccy):
            if from_ccy == "EUR" and to_ccy == "ILS":
                return amount * Decimal("4")
            return amount

        mock_convert.side_effect = side_effect

        trip = Trip(name="Test", base_currency="ILS", participants=["Dan", "Sara"])
        trip.expenses.append(
            Expense(
                description="Wine",
                amount=Decimal("25"),  # 25 EUR = 100 ILS
                currency="EUR",
                paid_by="Dan",
                splits=[
                    Split(person="Dan", amount=Decimal("12.50"), currency="EUR"),
                    Split(person="Sara", amount=Decimal("12.50"), currency="EUR"),
                ],
            )
        )

        balances = ledger.compute_balances(trip, "ILS")

        # Dan paid 100 ILS, owes 50 ILS → net +50
        assert balances["Dan"] == Decimal("50")
        # Sara paid 0, owes 50 ILS → net -50
        assert balances["Sara"] == Decimal("-50")


class TestSimplifiedDebts:
    """Tests for debt simplification."""

    def test_simple_debt(self) -> None:
        """Test simple debt with one debtor/creditor."""
        trip = Trip(name="Test", participants=["Dan", "Sara"])
        trip.expenses.append(
            Expense(
                description="Dinner",
                amount=Decimal("100"),
                currency="ILS",
                paid_by="Dan",
                splits=[
                    Split(person="Dan", amount=Decimal("50"), currency="ILS"),
                    Split(person="Sara", amount=Decimal("50"), currency="ILS"),
                ],
            )
        )

        debts = ledger.simplified_debts(trip)

        assert len(debts) == 1
        assert debts[0] == ("Sara", "Dan", Decimal("50"))

    def test_chain_simplification(self) -> None:
        """Test A→B ₪100, B→C ₪100 simplifies to A→C ₪100."""
        trip = Trip(name="Test", participants=["A", "B", "C"])

        # A pays B ₪100 (A owes B)
        trip.expenses.append(
            Expense(
                description="Expense 1",
                amount=Decimal("100"),
                currency="ILS",
                paid_by="B",
                splits=[Split(person="A", amount=Decimal("100"), currency="ILS")],
            )
        )

        # B pays C ₪100 (B owes C)
        trip.expenses.append(
            Expense(
                description="Expense 2",
                amount=Decimal("100"),
                currency="ILS",
                paid_by="C",
                splits=[Split(person="B", amount=Decimal("100"), currency="ILS")],
            )
        )

        debts = ledger.simplified_debts(trip)

        # Should simplify to single transaction A→C ₪100
        assert len(debts) == 1
        assert debts[0] == ("A", "C", Decimal("100"))

    def test_complex_web_simplification(self) -> None:
        """Test 4-person complex web minimizes transactions."""
        trip = Trip(name="Test", participants=["A", "B", "C", "D"])

        # Create complex web of expenses
        # A pays ₪400, split among all 4 (each owes ₪100)
        trip.expenses.append(
            Expense(
                description="Big dinner",
                amount=Decimal("400"),
                currency="ILS",
                paid_by="A",
                splits=[
                    Split(person="A", amount=Decimal("100"), currency="ILS"),
                    Split(person="B", amount=Decimal("100"), currency="ILS"),
                    Split(person="C", amount=Decimal("100"), currency="ILS"),
                    Split(person="D", amount=Decimal("100"), currency="ILS"),
                ],
            )
        )

        # B pays ₪200, split between B and C
        trip.expenses.append(
            Expense(
                description="Activity",
                amount=Decimal("200"),
                currency="ILS",
                paid_by="B",
                splits=[
                    Split(person="B", amount=Decimal("100"), currency="ILS"),
                    Split(person="C", amount=Decimal("100"), currency="ILS"),
                ],
            )
        )

        debts = ledger.simplified_debts(trip)

        # Verify total transactions are minimized
        # A: paid 400, owes 100 = +300
        # B: paid 200, owes 100+100 = 0
        # C: paid 0, owes 100+100 = -200
        # D: paid 0, owes 100 = -100
        # Minimum: 2 transactions (C→A, D→A)
        assert len(debts) <= 3  # Should be 2 optimal, 3 acceptable

        # Verify amounts are correct
        total_flow = sum(d[2] for d in debts)
        assert total_flow == Decimal("300")

    def test_zero_balance_excluded(self) -> None:
        """Test that people with zero balance are excluded."""
        trip = Trip(name="Test", participants=["Dan", "Sara", "Avi"])
        trip.expenses.append(
            Expense(
                description="Dinner",
                amount=Decimal("100"),
                currency="ILS",
                paid_by="Dan",
                splits=[
                    Split(person="Dan", amount=Decimal("50"), currency="ILS"),
                    Split(person="Sara", amount=Decimal("50"), currency="ILS"),
                ],
            )
        )

        debts = ledger.simplified_debts(trip)

        # Avi should not appear in debts (zero balance)
        people_in_debts = {d[0] for d in debts} | {d[1] for d in debts}
        assert "Avi" not in people_in_debts

    def test_all_settled_returns_empty(self) -> None:
        """Test that settled trip returns empty list."""
        trip = Trip(name="Test", participants=["Dan", "Sara"])
        trip.expenses.append(
            Expense(
                description="Dinner",
                amount=Decimal("100"),
                currency="ILS",
                paid_by="Dan",
                splits=[
                    Split(person="Dan", amount=Decimal("50"), currency="ILS"),
                    Split(person="Sara", amount=Decimal("50"), currency="ILS"),
                ],
            )
        )
        trip.settlements.append(
            Settlement(
                from_person="Sara",
                to_person="Dan",
                amount=Decimal("50"),
                currency="ILS",
            )
        )

        debts = ledger.simplified_debts(trip)

        assert debts == []


class TestAddExpense:
    """Tests for adding expenses."""

    def test_add_expense_returns_new_trip(self) -> None:
        """Test that add_expense returns a new trip (immutable)."""
        trip = Trip(name="Test", participants=["Dan"])
        splits = [Split(person="Dan", amount=Decimal("100"), currency="ILS")]

        new_trip, expense = ledger.add_expense(
            trip,
            description="Dinner",
            amount=Decimal("100"),
            currency="ILS",
            paid_by="Dan",
            splits=splits,
        )

        # Original trip unchanged
        assert len(trip.expenses) == 0
        # New trip has expense
        assert len(new_trip.expenses) == 1
        assert new_trip.expenses[0].description == "Dinner"

    def test_add_expense_adds_participants(self) -> None:
        """Test that new people in expense are added to participants."""
        trip = Trip(name="Test", participants=["Dan"])
        splits = [
            Split(person="Dan", amount=Decimal("50"), currency="ILS"),
            Split(person="Sara", amount=Decimal("50"), currency="ILS"),
        ]

        new_trip, _ = ledger.add_expense(
            trip,
            description="Dinner",
            amount=Decimal("100"),
            currency="ILS",
            paid_by="Dan",
            splits=splits,
        )

        assert "Sara" in new_trip.participants

    def test_add_expense_validates_splits(self) -> None:
        """Test that invalid splits raise error."""
        trip = Trip(name="Test", participants=["Dan"])
        splits = [Split(person="Dan", amount=Decimal("50"), currency="ILS")]

        with pytest.raises(ValueError, match="Splits sum"):
            ledger.add_expense(
                trip,
                description="Dinner",
                amount=Decimal("100"),  # Splits sum to 50, not 100
                currency="ILS",
                paid_by="Dan",
                splits=splits,
            )


class TestAddSettlement:
    """Tests for adding settlements."""

    def test_add_settlement(self) -> None:
        """Test adding a settlement."""
        trip = Trip(name="Test", participants=["Dan", "Sara"])

        new_trip, settlement = ledger.add_settlement(
            trip,
            from_person="Sara",
            to_person="Dan",
            amount=Decimal("50"),
            currency="ILS",
        )

        assert len(new_trip.settlements) == 1
        assert settlement.from_person == "Sara"
        assert settlement.to_person == "Dan"


class TestUndoLast:
    """Tests for undo functionality."""

    def test_undo_expense(self) -> None:
        """Test undoing the last expense."""
        trip = Trip(name="Test", participants=["Dan"])
        splits = [Split(person="Dan", amount=Decimal("100"), currency="ILS")]
        trip, _ = ledger.add_expense(trip, "Dinner", Decimal("100"), "ILS", "Dan", splits)

        new_trip, removed = ledger.undo_last(trip)

        assert len(new_trip.expenses) == 0
        assert removed is not None
        assert removed.description == "Dinner"

    def test_undo_settlement(self) -> None:
        """Test undoing the last settlement."""
        trip = Trip(name="Test", participants=["Dan", "Sara"])
        trip, _ = ledger.add_settlement(trip, "Sara", "Dan", Decimal("50"), "ILS")

        new_trip, removed = ledger.undo_last(trip)

        assert len(new_trip.settlements) == 0
        assert removed is not None
        assert removed.from_person == "Sara"

    def test_undo_empty_trip(self) -> None:
        """Test undo on empty trip returns None."""
        trip = Trip(name="Test")

        new_trip, removed = ledger.undo_last(trip)

        assert removed is None
        assert new_trip.name == "Test"
