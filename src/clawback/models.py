"""Pydantic models for Clawback expense tracking."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_serializer, field_validator


class Split(BaseModel):
    """A single person's share of an expense."""

    person: str
    amount: Decimal
    currency: str

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            return Decimal(str(v))
        return Decimal(v) if not isinstance(v, Decimal) else v

    @field_serializer("amount")
    def serialize_amount(self, v: Decimal) -> str:
        return str(v)


class Expense(BaseModel):
    """A single expense in a trip."""

    id: UUID = Field(default_factory=uuid4)
    ts: datetime = Field(default_factory=datetime.now)
    description: str
    amount: Decimal
    currency: str
    paid_by: str
    splits: list[Split]
    notes: str = ""

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            return Decimal(str(v))
        return Decimal(v) if not isinstance(v, Decimal) else v

    @field_serializer("amount")
    def serialize_amount(self, v: Decimal) -> str:
        return str(v)


class Settlement(BaseModel):
    """A payment from one person to another to settle debt."""

    id: UUID = Field(default_factory=uuid4)
    ts: datetime = Field(default_factory=datetime.now)
    from_person: str
    to_person: str
    amount: Decimal
    currency: str
    notes: str = ""

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            return Decimal(str(v))
        return Decimal(v) if not isinstance(v, Decimal) else v

    @field_serializer("amount")
    def serialize_amount(self, v: Decimal) -> str:
        return str(v)


class Trip(BaseModel):
    """A trip with participants, expenses, and settlements."""

    name: str
    sheet_id: str | None = None
    participants: list[str] = Field(default_factory=list)
    base_currency: str = "ILS"
    created_at: datetime = Field(default_factory=datetime.now)
    expenses: list[Expense] = Field(default_factory=list)
    settlements: list[Settlement] = Field(default_factory=list)


class CommandType(str, Enum):
    """Types of parsed commands."""

    ADD_EXPENSE = "add_expense"
    SETTLE = "settle"
    BALANCES = "balances"
    SUMMARY = "summary"
    UNDO = "undo"
    TRIP = "trip"
    WHO = "who"
    HELP = "help"


class SplitType(str, Enum):
    """How an expense is split."""

    EQUAL = "equal"
    ONLY = "only"  # Equal split among specified people only
    CUSTOM = "custom"  # Specific amounts per person
    PERCENTAGE = "percentage"  # Percentage-based split


class ParsedCommand(BaseModel):
    """Result of parsing a natural language command."""

    command_type: CommandType
    raw_text: str

    # For ADD_EXPENSE
    description: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    paid_by: str | None = None
    split_type: SplitType | None = None
    split_among: list[str] | None = None  # For equal/only splits
    custom_splits: dict[str, Decimal] | None = None  # For custom splits

    # For SETTLE
    from_person: str | None = None
    to_person: str | None = None

    # For BALANCES
    display_currency: str | None = None

    # For TRIP
    trip_name: str | None = None
    trip_base_currency: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Decimal | None:
        if v is None:
            return None
        if isinstance(v, float):
            return Decimal(str(v))
        return Decimal(v) if not isinstance(v, Decimal) else v

    @field_serializer("amount")
    def serialize_amount(self, v: Decimal | None) -> str | None:
        return str(v) if v is not None else None

    @field_validator("custom_splits", mode="before")
    @classmethod
    def coerce_custom_splits(cls, v: Any) -> dict[str, Decimal] | None:
        if v is None:
            return None
        return {
            k: Decimal(str(val)) if isinstance(val, float) else Decimal(val) for k, val in v.items()
        }

    @field_serializer("custom_splits")
    def serialize_custom_splits(self, v: dict[str, Decimal] | None) -> dict[str, str] | None:
        return {k: str(val) for k, val in v.items()} if v else None


class ParseError(BaseModel):
    """Error when parsing fails."""

    raw_text: str
    message: str
    suggestions: list[str] = Field(default_factory=list)


class PendingConfirmation(BaseModel):
    """A pending command awaiting user confirmation."""

    model_config = {"arbitrary_types_allowed": True}

    chat_id: str
    command: ParsedCommand
    confirmation_text: str
    created_at: datetime = Field(default_factory=datetime.now)
    trip_name: str
