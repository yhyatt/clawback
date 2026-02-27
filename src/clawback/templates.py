"""Response message templates - all user-facing text lives here.

This module contains all templates for user-facing messages.
Templates are designed to be:
1. Human-readable without LLM involvement
2. Easily swappable or customizable
3. Simple enough for a small model (Haiku) to reword if needed
"""

from decimal import Decimal
from typing import Any

from .parser import get_currency_symbol


def format_currency(amount: Decimal, currency: str) -> str:
    """Format amount with currency symbol."""
    symbol = get_currency_symbol(currency)
    # Put symbol before for $, after for others
    if currency == "USD":
        return f"${amount}"
    return f"{symbol}{amount}"


def format_splits_summary(splits: list[dict[str, Any]]) -> str:
    """Format a list of splits for display."""
    parts = []
    for split in splits:
        parts.append(f"{split['person']} {format_currency(split['amount'], split['currency'])}")
    return ", ".join(parts)


def format_debts_list(debts: list[tuple[str, str, Decimal]], currency: str) -> str:
    """Format list of debts for display."""
    if not debts:
        return "✨ All settled up!"

    lines = []
    for debtor, creditor, amount in debts:
        lines.append(f"• {debtor} → {creditor}: {format_currency(amount, currency)}")
    return "\n".join(lines)


# === CONFIRMATION TEMPLATES (for write commands) ===

CONFIRM_ADD_EXPENSE_EQUAL = (
    "💬 Got it: *{description}* {amount_display} paid by {paid_by}, "
    "split equally → {splits_summary}. Add this? (yes/no)"
)

CONFIRM_ADD_EXPENSE_ONLY = (
    "💬 Got it: *{description}* {amount_display} paid by {paid_by}, "
    "only {participants} → each {per_person}. Add this? (yes/no)"
)

CONFIRM_ADD_EXPENSE_CUSTOM = (
    "💬 Got it: *{description}* {amount_display} paid by {paid_by}, "
    "custom split → {splits_summary}. Add this? (yes/no)"
)

CONFIRM_SETTLE = "💬 Settle: {from_person} → {to_person}: {amount_display}. Mark as paid? (yes/no)"

CONFIRM_UNDO = "💬 Undo last {item_type}: *{description}*? (yes/no)"

CONFIRM_TRIP_CREATE = "💬 Create new trip *{trip_name}* with base currency {currency}? (yes/no)"


# === SUCCESS TEMPLATES ===

EXPENSE_ADDED = (
    "✅ *{description}* {amount_display} (paid by {paid_by})\n"
    "{splits_summary}\n\n"
    "📊 Running debts:\n{debts_summary}"
)

SETTLE_ADDED = (
    "✅ {from_person} → {to_person}: {amount_display} settled\n\n📊 Remaining:\n{debts_summary}"
)

UNDO_SUCCESS = "↩️ Undid: *{description}*\n\n📊 Updated debts:\n{debts_summary}"

TRIP_CREATED = "🎉 Trip *{trip_name}* created!\nBase currency: {currency}\n{sheet_info}"


# === READ COMMAND TEMPLATES ===

BALANCES = "📊 *{trip_name}* Balances\n\n{debts}\n\n{sheet_link}"

SUMMARY = (
    "📋 *{trip_name}* Summary\n\n"
    "👥 Participants: {participants}\n"
    "💰 Total expenses: {total_expenses}\n"
    "🔄 Settlements: {settlement_count}\n\n"
    "📊 To settle up:\n{debts}\n\n"
    "{sheet_link}"
)

WHO = "👥 *{trip_name}* Participants\n\n{participant_list}"

HELP = """🧾 *Clawback* - Group Expense Splitter

*Add expenses:*
• `kai add <desc> <amount> paid by <person>`
• `kai add dinner ₪340 paid by Dan only Dan & Sara`
• `kai add wine €60 paid by Avi custom Dan:30, Sara:20, Avi:10`

*Settle up:*
• `kai settle Dan paid Sara ₪100`

*View status:*
• `kai balances` - who owes what
• `kai summary` - full trip summary
• `kai who` - list participants

*Manage:*
• `kai undo` - undo last action
• `kai trip <name>` - create/switch trip

Currencies: ₪/ILS, $/USD, €/EUR, £/GBP, ¥/JPY"""


# === ERROR TEMPLATES ===

ERROR_NO_TRIP = "⚠️ No active trip. Create one first:\n`kai trip <name>`"

ERROR_PARSE = "❓ Didn't understand: {raw_text}\n\n{message}\n\nTry:\n{suggestions}"

ERROR_VALIDATION = "⚠️ {message}"

ERROR_SHEETS = (
    "⚠️ Expense saved locally but Google Sheets sync failed:\n{error}\n\n"
    "The expense is recorded - sheet will sync on next update."
)


# === NOTHING TO DO ===

NOTHING_TO_UNDO = "🤷 Nothing to undo."

ALL_SETTLED = "✨ All settled up! No outstanding debts."
