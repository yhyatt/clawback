"""Tests for Clawback state management."""

from datetime import datetime, timedelta
from pathlib import Path

from clawback.models import CommandType, ParsedCommand
from clawback.state import TripManager


class TestTripManager:
    """Tests for TripManager."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that TripManager creates state directory."""
        state_dir = tmp_path / "clawback"
        TripManager(state_dir)  # Creates directory on init
        assert state_dir.exists()

    def test_create_trip(self, tmp_path: Path) -> None:
        """Test creating a trip."""
        manager = TripManager(tmp_path)
        trip = manager.create_trip("Beach Vacation", "EUR")

        assert trip.name == "Beach Vacation"
        assert trip.base_currency == "EUR"

    def test_get_trip(self, tmp_path: Path) -> None:
        """Test getting a trip by name."""
        manager = TripManager(tmp_path)
        manager.create_trip("Test Trip")

        trip = manager.get_trip("Test Trip")
        assert trip is not None
        assert trip.name == "Test Trip"

    def test_get_nonexistent_trip(self, tmp_path: Path) -> None:
        """Test getting a trip that doesn't exist."""
        manager = TripManager(tmp_path)
        trip = manager.get_trip("NonExistent")
        assert trip is None

    def test_save_trip(self, tmp_path: Path) -> None:
        """Test saving an updated trip."""
        manager = TripManager(tmp_path)
        trip = manager.create_trip("Test Trip")
        trip.participants.append("Dan")
        manager.save_trip(trip)

        # Reload
        manager2 = TripManager(tmp_path)
        loaded = manager2.get_trip("Test Trip")
        assert "Dan" in loaded.participants

    def test_list_trips(self, tmp_path: Path) -> None:
        """Test listing all trips."""
        manager = TripManager(tmp_path)
        manager.create_trip("Trip 1")
        manager.create_trip("Trip 2")

        trips = manager.list_trips()
        assert len(trips) == 2
        assert "Trip 1" in trips
        assert "Trip 2" in trips

    def test_delete_trip(self, tmp_path: Path) -> None:
        """Test deleting a trip."""
        manager = TripManager(tmp_path)
        manager.create_trip("Test Trip")

        assert manager.delete_trip("Test Trip")
        assert manager.get_trip("Test Trip") is None

    def test_delete_nonexistent_trip(self, tmp_path: Path) -> None:
        """Test deleting a trip that doesn't exist."""
        manager = TripManager(tmp_path)
        assert not manager.delete_trip("NonExistent")

    def test_active_trip(self, tmp_path: Path) -> None:
        """Test active trip management."""
        manager = TripManager(tmp_path)
        manager.create_trip("Test Trip")

        manager.set_active_trip("chat123", "Test Trip")
        trip = manager.get_active_trip("chat123")

        assert trip is not None
        assert trip.name == "Test Trip"

    def test_get_active_trip_none(self, tmp_path: Path) -> None:
        """Test getting active trip when none set."""
        manager = TripManager(tmp_path)
        trip = manager.get_active_trip("chat123")
        assert trip is None

    def test_active_trip_persistence(self, tmp_path: Path) -> None:
        """Test that active trip persists across manager instances."""
        manager = TripManager(tmp_path)
        manager.create_trip("Test Trip")
        manager.set_active_trip("chat123", "Test Trip")

        # New manager instance
        manager2 = TripManager(tmp_path)
        trip = manager2.get_active_trip("chat123")
        assert trip is not None
        assert trip.name == "Test Trip"


class TestPendingConfirmations:
    """Tests for pending confirmation management."""

    def test_set_and_get_pending(self, tmp_path: Path) -> None:
        """Test setting and getting pending confirmation."""
        manager = TripManager(tmp_path)
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="test",
        )

        pending = manager.set_pending("chat123", cmd, "Confirm?", "Test Trip")
        assert pending.chat_id == "chat123"

        retrieved = manager.get_pending("chat123")
        assert retrieved is not None
        assert retrieved.confirmation_text == "Confirm?"

    def test_get_pending_none(self, tmp_path: Path) -> None:
        """Test getting pending when none exists."""
        manager = TripManager(tmp_path)
        assert manager.get_pending("chat123") is None

    def test_clear_pending(self, tmp_path: Path) -> None:
        """Test clearing pending confirmation."""
        manager = TripManager(tmp_path)
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="test",
        )
        manager.set_pending("chat123", cmd, "Confirm?", "Test Trip")

        manager.clear_pending("chat123")
        assert manager.get_pending("chat123") is None

    def test_clear_pending_nonexistent(self, tmp_path: Path) -> None:
        """Test clearing pending that doesn't exist (no error)."""
        manager = TripManager(tmp_path)
        manager.clear_pending("chat123")  # Should not raise

    def test_pending_expiration(self, tmp_path: Path) -> None:
        """Test that pending confirmations expire after 5 minutes."""
        manager = TripManager(tmp_path)
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="test",
        )
        pending = manager.set_pending("chat123", cmd, "Confirm?", "Test Trip")

        # Manually set created_at to 6 minutes ago
        pending.created_at = datetime.now() - timedelta(minutes=6)
        manager._pending["chat123"] = pending
        manager._save()

        # Should return None due to expiration
        assert manager.get_pending("chat123") is None

    def test_cleanup_expired_pending(self, tmp_path: Path) -> None:
        """Test cleanup of expired pending confirmations."""
        manager = TripManager(tmp_path)
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="test",
        )

        # Create two pending - one fresh, one expired
        manager.set_pending("chat1", cmd, "Confirm?", "Trip")

        pending2 = manager.set_pending("chat2", cmd, "Confirm?", "Trip")
        pending2.created_at = datetime.now() - timedelta(minutes=10)
        manager._pending["chat2"] = pending2
        manager._save()

        count = manager.cleanup_expired_pending()
        assert count == 1

        # chat1 should still exist, chat2 should be gone
        assert manager.get_pending("chat1") is not None
        assert manager.get_pending("chat2") is None

    def test_pending_persistence(self, tmp_path: Path) -> None:
        """Test that pending persists across manager instances."""
        manager = TripManager(tmp_path)
        cmd = ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text="test",
        )
        manager.set_pending("chat123", cmd, "Confirm?", "Test Trip")

        # New manager instance
        manager2 = TripManager(tmp_path)
        pending = manager2.get_pending("chat123")
        assert pending is not None


class TestStatePersistence:
    """Tests for state file persistence."""

    def test_corrupt_trips_file(self, tmp_path: Path) -> None:
        """Test handling of corrupt trips.json."""
        # Create corrupt file
        trips_file = tmp_path / "trips.json"
        trips_file.write_text("not valid json {{{")

        # Should not raise, just start with empty state
        manager = TripManager(tmp_path)
        assert manager.list_trips() == []

    def test_corrupt_pending_file(self, tmp_path: Path) -> None:
        """Test handling of corrupt pending.json."""
        pending_file = tmp_path / "pending.json"
        pending_file.write_text("not valid json")

        manager = TripManager(tmp_path)
        assert manager.get_pending("chat123") is None

    def test_corrupt_active_file(self, tmp_path: Path) -> None:
        """Test handling of corrupt active.json."""
        active_file = tmp_path / "active.json"
        active_file.write_text("not valid json")

        manager = TripManager(tmp_path)
        assert manager.get_active_trip("chat123") is None

    def test_delete_trip_clears_active(self, tmp_path: Path) -> None:
        """Test that deleting a trip clears it from active mappings."""
        manager = TripManager(tmp_path)
        manager.create_trip("Test Trip")
        manager.set_active_trip("chat123", "Test Trip")

        manager.delete_trip("Test Trip")
        assert manager.get_active_trip("chat123") is None
