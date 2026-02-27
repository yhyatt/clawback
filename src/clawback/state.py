"""Trip state management - load/save trips and pending confirmations."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from .models import ParsedCommand, PendingConfirmation, Trip


class TripManager:
    """
    Manages trip state and pending confirmations.

    State is persisted to ~/.clawback/trips.json
    Pending confirmations are stored in ~/.clawback/pending.json
    """

    def __init__(self, state_dir: str | Path | None = None):
        """
        Initialize TripManager.

        Args:
            state_dir: Directory for state files (default: ~/.clawback)
        """
        if state_dir is None:
            state_dir = Path.home() / ".clawback"
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.trips_file = self.state_dir / "trips.json"
        self.pending_file = self.state_dir / "pending.json"
        self.active_file = self.state_dir / "active.json"

        self._trips: dict[str, Trip] = {}
        self._pending: dict[str, PendingConfirmation] = {}
        self._active_trip: dict[str, str] = {}  # chat_id -> trip_name

        self._load()

    def _load(self) -> None:
        """Load state from disk."""
        # Load trips
        if self.trips_file.exists():
            try:
                with open(self.trips_file) as f:
                    data = json.load(f)
                self._trips = {name: Trip.model_validate(trip) for name, trip in data.items()}
            except (json.JSONDecodeError, Exception):
                self._trips = {}

        # Load pending confirmations
        if self.pending_file.exists():
            try:
                with open(self.pending_file) as f:
                    data = json.load(f)
                self._pending = {
                    chat_id: PendingConfirmation.model_validate(pending)
                    for chat_id, pending in data.items()
                }
            except (json.JSONDecodeError, Exception):
                self._pending = {}

        # Load active trip mappings
        if self.active_file.exists():
            try:
                with open(self.active_file) as f:
                    self._active_trip = json.load(f)
            except (json.JSONDecodeError, Exception):
                self._active_trip = {}

    def _save(self) -> None:
        """Save state to disk."""
        # Save trips
        with open(self.trips_file, "w") as f:
            json.dump(
                {name: trip.model_dump(mode="json") for name, trip in self._trips.items()},
                f,
                indent=2,
                default=str,
            )

        # Save pending confirmations
        with open(self.pending_file, "w") as f:
            json.dump(
                {
                    chat_id: pending.model_dump(mode="json")
                    for chat_id, pending in self._pending.items()
                },
                f,
                indent=2,
                default=str,
            )

        # Save active trip mappings
        with open(self.active_file, "w") as f:
            json.dump(self._active_trip, f, indent=2)

    def get_trip(self, name: str) -> Trip | None:
        """Get a trip by name."""
        return self._trips.get(name)

    def get_active_trip(self, chat_id: str) -> Trip | None:
        """Get the active trip for a chat."""
        trip_name = self._active_trip.get(chat_id)
        if trip_name:
            return self._trips.get(trip_name)
        return None

    def set_active_trip(self, chat_id: str, trip_name: str) -> None:
        """Set the active trip for a chat."""
        self._active_trip[chat_id] = trip_name
        self._save()

    def create_trip(
        self,
        name: str,
        base_currency: str = "ILS",
        sheet_id: str | None = None,
    ) -> Trip:
        """Create a new trip."""
        trip = Trip(
            name=name,
            base_currency=base_currency,
            sheet_id=sheet_id,
        )
        self._trips[name] = trip
        self._save()
        return trip

    def save_trip(self, trip: Trip) -> None:
        """Save/update a trip."""
        self._trips[trip.name] = trip
        self._save()

    def list_trips(self) -> list[str]:
        """List all trip names."""
        return list(self._trips.keys())

    def delete_trip(self, name: str) -> bool:
        """Delete a trip. Returns True if deleted."""
        if name in self._trips:
            del self._trips[name]
            # Remove from active mappings
            self._active_trip = {k: v for k, v in self._active_trip.items() if v != name}
            self._save()
            return True
        return False

    # === Pending Confirmations ===

    def set_pending(
        self,
        chat_id: str,
        command: ParsedCommand,
        confirmation_text: str,
        trip_name: str,
    ) -> PendingConfirmation:
        """Store a pending confirmation for a chat."""
        pending = PendingConfirmation(
            chat_id=chat_id,
            command=command,
            confirmation_text=confirmation_text,
            trip_name=trip_name,
        )
        self._pending[chat_id] = pending
        self._save()
        return pending

    def get_pending(self, chat_id: str) -> PendingConfirmation | None:
        """Get pending confirmation for a chat, if any and not expired."""
        pending = self._pending.get(chat_id)
        if pending:
            # Expire after 5 minutes
            if datetime.now() - pending.created_at > timedelta(minutes=5):
                self.clear_pending(chat_id)
                return None
        return pending

    def clear_pending(self, chat_id: str) -> None:
        """Clear pending confirmation for a chat."""
        if chat_id in self._pending:
            del self._pending[chat_id]
            self._save()

    def cleanup_expired_pending(self) -> int:
        """Remove all expired pending confirmations. Returns count removed."""
        now = datetime.now()
        expired = [
            chat_id
            for chat_id, pending in self._pending.items()
            if now - pending.created_at > timedelta(minutes=5)
        ]
        for chat_id in expired:
            del self._pending[chat_id]
        if expired:
            self._save()
        return len(expired)
