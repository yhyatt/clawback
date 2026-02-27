"""Shared test fixtures for Clawback tests."""

import tempfile
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clawback.models import Expense, Split, Trip
from clawback.state import TripManager


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --haiku flag to pytest."""
    parser.addoption(
        "--haiku",
        action="store_true",
        default=False,
        help="Enable Haiku validation layer for confirmation messages",
    )

@pytest.fixture
def sample_trip() -> Trip:
    """Create a sample trip for testing."""
    return Trip(
        name="Test Trip",
        base_currency="ILS",
        participants=["Dan", "Sara", "Avi"],
    )


@pytest.fixture
def trip_with_expenses() -> Trip:
    """Create a trip with some expenses for testing."""
    trip = Trip(
        name="Beach Trip",
        base_currency="ILS",
        participants=["Dan", "Sara", "Avi"],
    )

    # Dan paid 300 ILS for dinner, split equally
    expense1 = Expense(
        description="Dinner",
        amount=Decimal("300"),
        currency="ILS",
        paid_by="Dan",
        splits=[
            Split(person="Dan", amount=Decimal("100"), currency="ILS"),
            Split(person="Sara", amount=Decimal("100"), currency="ILS"),
            Split(person="Avi", amount=Decimal("100"), currency="ILS"),
        ],
    )
    trip.expenses.append(expense1)

    # Sara paid 150 ILS for gas, split equally
    expense2 = Expense(
        description="Gas",
        amount=Decimal("150"),
        currency="ILS",
        paid_by="Sara",
        splits=[
            Split(person="Dan", amount=Decimal("50"), currency="ILS"),
            Split(person="Sara", amount=Decimal("50"), currency="ILS"),
            Split(person="Avi", amount=Decimal("50"), currency="ILS"),
        ],
    )
    trip.expenses.append(expense2)

    return trip


@pytest.fixture
def temp_state_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for state files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def trip_manager(temp_state_dir: Path) -> TripManager:
    """Create a TripManager with a temporary state directory."""
    return TripManager(temp_state_dir)


@pytest.fixture
def mock_fx_rate() -> Generator[MagicMock, None, None]:
    """Mock FX rate fetching to avoid network calls."""
    with patch("clawback.fx.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rates": {"ILS": Decimal("3.95"), "USD": Decimal("1.08")}
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        yield mock_get


@pytest.fixture
def mock_gog() -> Generator[MagicMock, None, None]:
    """Mock gog CLI subprocess calls."""
    with patch("clawback.sheets.subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"spreadsheetId": "test-sheet-id"}'
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        yield mock_run
