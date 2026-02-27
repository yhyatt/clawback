"""Currency exchange rates via frankfurter.app (free, no auth required)."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import ClassVar

import requests


class FXError(Exception):
    """Error fetching exchange rates."""

    pass


class FXCache:
    """In-memory cache for exchange rates with 1h TTL."""

    _cache: ClassVar[dict[str, tuple[Decimal, datetime]]] = {}
    _ttl: ClassVar[timedelta] = timedelta(hours=1)

    @classmethod
    def get(cls, key: str) -> Decimal | None:
        """Get cached rate if not expired."""
        if key in cls._cache:
            rate, cached_at = cls._cache[key]
            if datetime.now() - cached_at < cls._ttl:
                return rate
            del cls._cache[key]
        return None

    @classmethod
    def set(cls, key: str, rate: Decimal) -> None:
        """Cache a rate."""
        cls._cache[key] = (rate, datetime.now())

    @classmethod
    def clear(cls) -> None:
        """Clear all cached rates."""
        cls._cache.clear()


def get_rate(from_ccy: str, to_ccy: str) -> Decimal:
    """
    Get exchange rate from one currency to another.

    Uses frankfurter.app API with in-memory caching.

    Args:
        from_ccy: Source currency code (e.g., "EUR", "USD")
        to_ccy: Target currency code (e.g., "ILS", "GBP")

    Returns:
        Exchange rate as Decimal

    Raises:
        FXError: If API call fails or currency not supported
    """
    from_ccy = from_ccy.upper()
    to_ccy = to_ccy.upper()

    # Same currency - no conversion needed
    if from_ccy == to_ccy:
        return Decimal("1")

    cache_key = f"{from_ccy}->{to_ccy}"

    # Check cache first
    cached = FXCache.get(cache_key)
    if cached is not None:
        return cached

    try:
        # frankfurter.app uses EUR as base, so we need to handle this
        # Fetch rates for both currencies relative to EUR
        url = f"https://api.frankfurter.app/latest?from={from_ccy}&to={to_ccy}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if "rates" not in data or to_ccy not in data["rates"]:
            raise FXError(f"Currency {to_ccy} not found in response")

        rate = Decimal(str(data["rates"][to_ccy]))

        # Cache the rate
        FXCache.set(cache_key, rate)

        return rate

    except requests.RequestException as e:
        raise FXError(f"Failed to fetch exchange rate {from_ccy}->{to_ccy}: {e}") from e
    except (KeyError, ValueError) as e:
        raise FXError(f"Invalid response from exchange rate API: {e}") from e


def convert(amount: Decimal, from_ccy: str, to_ccy: str) -> Decimal:
    """
    Convert an amount from one currency to another.

    Args:
        amount: Amount to convert
        from_ccy: Source currency code
        to_ccy: Target currency code

    Returns:
        Converted amount as Decimal, rounded to 2 decimal places
    """
    if from_ccy.upper() == to_ccy.upper():
        return amount

    rate = get_rate(from_ccy, to_ccy)
    converted = amount * rate
    return converted.quantize(Decimal("0.01"))
