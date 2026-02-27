"""Tests for Clawback templates."""

from decimal import Decimal

from clawback.templates import (
    format_currency,
    format_debts_list,
    format_splits_summary,
)


class TestFormatCurrency:
    """Tests for format_currency."""

    def test_ils_currency(self) -> None:
        """Test ILS formatting."""
        result = format_currency(Decimal("100"), "ILS")
        assert result == "₪100"

    def test_usd_currency(self) -> None:
        """Test USD formatting (symbol before)."""
        result = format_currency(Decimal("50.50"), "USD")
        assert result == "$50.50"

    def test_eur_currency(self) -> None:
        """Test EUR formatting."""
        result = format_currency(Decimal("30"), "EUR")
        assert result == "€30"

    def test_unknown_currency(self) -> None:
        """Test unknown currency uses code."""
        result = format_currency(Decimal("100"), "CHF")
        assert result == "CHF100"


class TestFormatSplitsSummary:
    """Tests for format_splits_summary."""

    def test_single_split(self) -> None:
        """Test formatting single split."""
        splits = [{"person": "Dan", "amount": Decimal("50"), "currency": "ILS"}]
        result = format_splits_summary(splits)
        assert result == "Dan ₪50"

    def test_multiple_splits(self) -> None:
        """Test formatting multiple splits."""
        splits = [
            {"person": "Dan", "amount": Decimal("30"), "currency": "ILS"},
            {"person": "Sara", "amount": Decimal("20"), "currency": "ILS"},
        ]
        result = format_splits_summary(splits)
        assert "Dan ₪30" in result
        assert "Sara ₪20" in result
        assert ", " in result


class TestFormatDebtsList:
    """Tests for format_debts_list."""

    def test_empty_debts(self) -> None:
        """Test formatting empty debts list."""
        result = format_debts_list([], "ILS")
        assert "settled up" in result

    def test_single_debt(self) -> None:
        """Test formatting single debt."""
        debts = [("Sara", "Dan", Decimal("50"))]
        result = format_debts_list(debts, "ILS")
        assert "Sara → Dan" in result
        assert "₪50" in result

    def test_multiple_debts(self) -> None:
        """Test formatting multiple debts."""
        debts = [
            ("Sara", "Dan", Decimal("50")),
            ("Avi", "Dan", Decimal("30")),
        ]
        result = format_debts_list(debts, "ILS")
        assert "Sara → Dan" in result
        assert "Avi → Dan" in result
        assert "₪50" in result
        assert "₪30" in result
