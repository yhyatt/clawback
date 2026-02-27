"""Tests for Clawback CLI."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from clawback.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_state(tmp_path: Path) -> str:
    """Create a temporary state directory path."""
    return str(tmp_path / "clawback-state")


class TestCLI:
    """Tests for CLI commands."""

    def test_version(self, runner: CliRunner) -> None:
        """Test --version flag."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help(self, runner: CliRunner) -> None:
        """Test help command."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Token-efficient" in result.output


class TestParseCommand:
    """Tests for parse CLI command."""

    def test_parse_valid_command(self, runner: CliRunner) -> None:
        """Test parsing a valid command."""
        result = runner.invoke(cli, ["parse", "kai", "help"])
        assert result.exit_code == 0
        assert "Parsed: help" in result.output

    def test_parse_add_expense(self, runner: CliRunner) -> None:
        """Test parsing add expense command."""
        result = runner.invoke(cli, ["parse", "kai", "add", "dinner", "₪100", "paid", "by", "Dan"])
        assert result.exit_code == 0
        assert "Parsed: add_expense" in result.output
        assert "description: dinner" in result.output

    def test_parse_invalid_command(self, runner: CliRunner) -> None:
        """Test parsing an invalid command."""
        result = runner.invoke(cli, ["parse", "gibberish", "nonsense"])
        assert result.exit_code == 1
        assert "Parse Error" in result.output


class TestHandleCommand:
    """Tests for handle CLI command."""

    def test_handle_help(self, runner: CliRunner, temp_state: str) -> None:
        """Test handling help command."""
        result = runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "kai",
                "help",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )
        assert result.exit_code == 0
        assert "Clawback" in result.output

    def test_handle_trip_creation(self, runner: CliRunner, temp_state: str) -> None:
        """Test handling trip creation."""
        # Create trip
        result = runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "kai",
                "trip",
                "Test",
                "Trip",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )
        assert result.exit_code == 0
        assert "Create new trip" in result.output

        # Confirm
        result = runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "yes",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )
        assert result.exit_code == 0
        assert "created" in result.output

    def test_handle_no_active_trip(self, runner: CliRunner, temp_state: str) -> None:
        """Test handling command without active trip."""
        result = runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "kai",
                "balances",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )
        assert result.exit_code == 0
        assert "No active trip" in result.output


class TestTripsCommand:
    """Tests for trips CLI command."""

    def test_trips_empty(self, runner: CliRunner, temp_state: str) -> None:
        """Test listing trips when none exist."""
        result = runner.invoke(cli, ["trips", "--state-dir", temp_state])
        assert result.exit_code == 0
        assert "No trips found" in result.output

    def test_trips_with_trip(self, runner: CliRunner, temp_state: str) -> None:
        """Test listing trips after creating one."""
        # Create a trip first
        runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "kai",
                "trip",
                "Beach",
                "Vacation",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )
        runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "yes",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )

        # List trips
        result = runner.invoke(cli, ["trips", "--state-dir", temp_state])
        assert result.exit_code == 0
        assert "Beach Vacation" in result.output


class TestBalancesCommand:
    """Tests for balances CLI command."""

    def test_balances_trip_not_found(self, runner: CliRunner, temp_state: str) -> None:
        """Test balances for non-existent trip."""
        result = runner.invoke(cli, ["balances", "NonExistent", "--state-dir", temp_state])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_balances_all_settled(self, runner: CliRunner, temp_state: str) -> None:
        """Test balances when all settled."""
        # Create trip
        runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "kai",
                "trip",
                "Test",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )
        runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "yes",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )

        # Check balances
        result = runner.invoke(cli, ["balances", "Test", "--state-dir", temp_state])
        assert result.exit_code == 0
        assert "settled up" in result.output

    def test_balances_with_debts(self, runner: CliRunner, temp_state: str) -> None:
        """Test balances with debts."""
        # Create trip and add expense
        runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "kai",
                "trip",
                "Test",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )
        runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "yes",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )
        runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "kai",
                "add",
                "dinner",
                "₪100",
                "paid",
                "by",
                "Dan",
                "only",
                "Dan,",
                "Sara",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )
        runner.invoke(
            cli,
            [
                "handle",
                "chat123",
                "yes",
                "--state-dir",
                temp_state,
                "--no-sheets",
            ],
        )

        # Check balances
        result = runner.invoke(cli, ["balances", "Test", "--state-dir", temp_state])
        assert result.exit_code == 0
        assert "Balances" in result.output


class TestCleanupCommand:
    """Tests for cleanup CLI command."""

    def test_cleanup(self, runner: CliRunner, temp_state: str) -> None:
        """Test cleanup command."""
        result = runner.invoke(cli, ["cleanup", "--state-dir", temp_state])
        assert result.exit_code == 0
        assert "Cleaned up" in result.output
