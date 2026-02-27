"""Pure financial logic for trip expense management. No I/O, no side effects."""

from collections import defaultdict
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from .fx import convert
from .models import Expense, Settlement, Split, Trip


def validate_splits(
    splits: list[Split], total: Decimal, tolerance: Decimal = Decimal("0.01")
) -> None:
    """
    Validate that splits sum to the total expense amount.

    Args:
        splits: List of splits to validate
        total: Expected total amount
        tolerance: Acceptable difference (default 0.01 for rounding)

    Raises:
        ValueError: If splits don't sum to total within tolerance
    """
    splits_sum = sum(s.amount for s in splits)
    diff = abs(splits_sum - total)
    if diff > tolerance:
        raise ValueError(
            f"Splits sum to {splits_sum} but expense total is {total} "
            f"(difference: {diff}, tolerance: {tolerance})"
        )


def compute_equal_splits(
    total: Decimal,
    currency: str,
    participants: Sequence[str],
) -> list[Split]:
    """
    Compute equal splits among participants, handling rounding correctly.

    The last person gets any rounding remainder to ensure splits sum exactly to total.

    Args:
        total: Total amount to split
        currency: Currency code
        participants: List of participant names

    Returns:
        List of Split objects
    """
    if not participants:
        raise ValueError("Cannot split among zero participants")

    n = len(participants)
    base_share = (total / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    splits = []

    for i, person in enumerate(participants):
        if i == n - 1:
            # Last person gets remainder to ensure exact sum
            already_allocated = base_share * (n - 1)
            final_share = total - already_allocated
            splits.append(Split(person=person, amount=final_share, currency=currency))
        else:
            splits.append(Split(person=person, amount=base_share, currency=currency))

    return splits


def compute_balances(trip: Trip, base_currency: str | None = None) -> dict[str, Decimal]:
    """
    Compute net balance per person in the base currency.

    Positive balance = person is owed money (paid more than their share)
    Negative balance = person owes money (paid less than their share)

    Args:
        trip: Trip with expenses and settlements
        base_currency: Currency to convert to (defaults to trip.base_currency)

    Returns:
        Dict mapping person name to net balance
    """
    base = base_currency or trip.base_currency
    balances: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    # Process expenses
    for expense in trip.expenses:
        # Convert expense amount to base currency
        paid_amount = convert(expense.amount, expense.currency, base)
        balances[expense.paid_by] += paid_amount

        # Subtract each person's share
        for split in expense.splits:
            split_amount = convert(split.amount, split.currency, base)
            balances[split.person] -= split_amount

    # Process settlements
    for settlement in trip.settlements:
        amount = convert(settlement.amount, settlement.currency, base)
        balances[settlement.from_person] += amount  # Payer's debt reduced
        balances[settlement.to_person] -= amount  # Recipient's credit reduced

    # Round all balances
    return {
        person: balance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for person, balance in balances.items()
    }


def simplified_debts(
    trip: Trip,
    base_currency: str | None = None,
) -> list[tuple[str, str, Decimal]]:
    """
    Compute minimum transactions needed to settle all debts.

    Uses the min-cash-flow algorithm for optimal debt simplification.

    Args:
        trip: Trip with expenses and settlements
        base_currency: Currency to convert to (defaults to trip.base_currency)

    Returns:
        List of (debtor, creditor, amount) tuples representing minimum transfers
    """
    balances = compute_balances(trip, base_currency)

    # Filter out zero balances
    balances = {p: b for p, b in balances.items() if b != Decimal("0")}

    if not balances:
        return []

    # Separate into debtors (negative) and creditors (positive)
    debtors: list[tuple[str, Decimal]] = []
    creditors: list[tuple[str, Decimal]] = []

    for person, balance in balances.items():
        if balance < 0:
            debtors.append((person, -balance))  # Store as positive debt amount
        elif balance > 0:
            creditors.append((person, balance))

    # Sort for consistent, optimal pairing (largest first)
    debtors.sort(key=lambda x: x[1], reverse=True)
    creditors.sort(key=lambda x: x[1], reverse=True)

    transactions: list[tuple[str, str, Decimal]] = []

    # Greedy matching - pair largest debtor with largest creditor
    while debtors and creditors:
        debtor, debt = debtors[0]
        creditor, credit = creditors[0]

        # Transfer the smaller of the two amounts
        transfer = min(debt, credit)

        if transfer > Decimal("0"):
            transactions.append((debtor, creditor, transfer))

        # Update balances
        new_debt = debt - transfer
        new_credit = credit - transfer

        # Remove or update debtor
        debtors.pop(0)
        if new_debt > Decimal("0.01"):
            debtors.insert(0, (debtor, new_debt))
            debtors.sort(key=lambda x: x[1], reverse=True)

        # Remove or update creditor
        creditors.pop(0)
        if new_credit > Decimal("0.01"):
            creditors.insert(0, (creditor, new_credit))
            creditors.sort(key=lambda x: x[1], reverse=True)

    return transactions


def add_expense(
    trip: Trip,
    description: str,
    amount: Decimal,
    currency: str,
    paid_by: str,
    splits: list[Split],
    notes: str = "",
) -> tuple[Trip, Expense]:
    """
    Add an expense to a trip (immutable - returns new Trip).

    Args:
        trip: Original trip
        description: What the expense was for
        amount: Total amount
        currency: Currency code
        paid_by: Who paid
        splits: How the expense is split
        notes: Optional notes

    Returns:
        Tuple of (new Trip, created Expense)
    """
    validate_splits(splits, amount)

    expense = Expense(
        id=uuid4(),
        description=description,
        amount=amount,
        currency=currency,
        paid_by=paid_by,
        splits=splits,
        notes=notes,
    )

    # Create new trip with expense added
    new_trip = trip.model_copy(deep=True)
    new_trip.expenses.append(expense)

    # Add any new participants
    all_people = {paid_by} | {s.person for s in splits}
    for person in all_people:
        if person not in new_trip.participants:
            new_trip.participants.append(person)

    return new_trip, expense


def add_settlement(
    trip: Trip,
    from_person: str,
    to_person: str,
    amount: Decimal,
    currency: str,
    notes: str = "",
) -> tuple[Trip, Settlement]:
    """
    Add a settlement (payment between people) to a trip.

    Args:
        trip: Original trip
        from_person: Who paid
        to_person: Who received
        amount: Amount paid
        currency: Currency code
        notes: Optional notes

    Returns:
        Tuple of (new Trip, created Settlement)
    """
    settlement = Settlement(
        id=uuid4(),
        from_person=from_person,
        to_person=to_person,
        amount=amount,
        currency=currency,
        notes=notes,
    )

    new_trip = trip.model_copy(deep=True)
    new_trip.settlements.append(settlement)

    return new_trip, settlement


def undo_last(trip: Trip) -> tuple[Trip, Expense | Settlement | None]:
    """
    Remove the most recent expense or settlement.

    Args:
        trip: Original trip

    Returns:
        Tuple of (new Trip, removed item or None if nothing to undo)
    """
    new_trip = trip.model_copy(deep=True)

    # Find the most recent item by timestamp
    last_expense = new_trip.expenses[-1] if new_trip.expenses else None
    last_settlement = new_trip.settlements[-1] if new_trip.settlements else None

    if last_expense is None and last_settlement is None:
        return new_trip, None

    if last_settlement is None or (last_expense and last_expense.ts > last_settlement.ts):
        removed_expense = new_trip.expenses.pop()
        return new_trip, removed_expense
    else:
        removed_settlement = new_trip.settlements.pop()
        return new_trip, removed_settlement
