"""Tests for Clawback FX module - currency exchange."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import requests

from clawback.fx import FXCache, FXError, convert, get_rate


class TestFXCache:
    """Tests for FX rate caching."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        FXCache.clear()

    def test_cache_miss(self) -> None:
        """Test cache returns None on miss."""
        assert FXCache.get("EUR->ILS") is None

    def test_cache_hit(self) -> None:
        """Test cache returns value on hit."""
        FXCache.set("EUR->ILS", Decimal("3.95"))
        assert FXCache.get("EUR->ILS") == Decimal("3.95")

    def test_cache_clear(self) -> None:
        """Test cache clearing."""
        FXCache.set("EUR->ILS", Decimal("3.95"))
        FXCache.clear()
        assert FXCache.get("EUR->ILS") is None


class TestGetRate:
    """Tests for get_rate function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        FXCache.clear()

    def test_same_currency(self) -> None:
        """Test same currency returns 1."""
        assert get_rate("EUR", "EUR") == Decimal("1")
        assert get_rate("ILS", "ils") == Decimal("1")  # Case insensitive

    @patch("clawback.fx.requests.get")
    def test_api_call(self, mock_get: MagicMock) -> None:
        """Test API call for rate."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"rates": {"ILS": 3.95}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        rate = get_rate("EUR", "ILS")

        assert rate == Decimal("3.95")
        mock_get.assert_called_once()

    @patch("clawback.fx.requests.get")
    def test_cache_used(self, mock_get: MagicMock) -> None:
        """Test that cache is used on second call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"rates": {"ILS": 3.95}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # First call - API
        get_rate("EUR", "ILS")
        # Second call - cache
        get_rate("EUR", "ILS")

        # Only one API call
        assert mock_get.call_count == 1

    @patch("clawback.fx.requests.get")
    def test_api_error(self, mock_get: MagicMock) -> None:
        """Test FXError on API failure."""
        mock_get.side_effect = requests.RequestException("Network error")

        with pytest.raises(FXError, match="Failed to fetch"):
            get_rate("EUR", "ILS")

    @patch("clawback.fx.requests.get")
    def test_missing_currency_in_response(self, mock_get: MagicMock) -> None:
        """Test FXError when currency not in response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"rates": {"USD": 1.08}}  # No ILS
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with pytest.raises(FXError, match="not found in response"):
            get_rate("EUR", "ILS")


class TestConvert:
    """Tests for convert function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        FXCache.clear()

    def test_same_currency(self) -> None:
        """Test conversion with same currency."""
        result = convert(Decimal("100"), "EUR", "EUR")
        assert result == Decimal("100")

    @patch("clawback.fx.get_rate")
    def test_conversion(self, mock_rate: MagicMock) -> None:
        """Test currency conversion."""
        mock_rate.return_value = Decimal("4")

        result = convert(Decimal("100"), "EUR", "ILS")

        assert result == Decimal("400.00")

    @patch("clawback.fx.get_rate")
    def test_conversion_rounding(self, mock_rate: MagicMock) -> None:
        """Test conversion rounds to 2 decimal places."""
        mock_rate.return_value = Decimal("3.953")

        result = convert(Decimal("100"), "EUR", "ILS")

        assert result == Decimal("395.30")

    @patch("clawback.fx.get_rate")
    def test_small_amount_conversion(self, mock_rate: MagicMock) -> None:
        """Test small amount conversion."""
        mock_rate.return_value = Decimal("0.25")

        result = convert(Decimal("1"), "ILS", "EUR")

        assert result == Decimal("0.25")
