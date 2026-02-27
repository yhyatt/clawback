"""Zero-LLM deterministic command parser using regex patterns."""

import re
from decimal import Decimal, InvalidOperation

from .models import CommandType, ParsedCommand, ParseError, SplitType

# Currency symbol/code mappings
CURRENCY_MAP: dict[str, str] = {
    "₪": "ILS",
    "nis": "ILS",
    "ils": "ILS",
    "shekel": "ILS",
    "shekels": "ILS",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "$": "USD",
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "£": "GBP",
    "gbp": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "¥": "JPY",
    "jpy": "JPY",
    "yen": "JPY",
}

# Currency symbols for display
CURRENCY_SYMBOLS: dict[str, str] = {
    "ILS": "₪",
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "JPY": "¥",
}


def normalize_currency(currency_str: str) -> str:
    """Convert currency symbol/name to standard code."""
    return CURRENCY_MAP.get(currency_str.lower(), currency_str.upper())


def get_currency_symbol(currency_code: str) -> str:
    """Get display symbol for currency code."""
    return CURRENCY_SYMBOLS.get(currency_code.upper(), currency_code)


def parse_amount_currency(text: str) -> tuple[Decimal, str] | None:
    """
    Parse an amount with currency from text.

    Handles: ₪100, 100₪, $50, 50USD, €30, 30 EUR, etc.
    """
    # Pattern: symbol + amount or amount + symbol/code
    patterns = [
        # Symbol before amount: ₪100, $50.50, €30
        r"([₪€$£¥])\s*([\d,]+(?:\.\d{1,2})?)",
        # Amount before symbol: 100₪, 50$
        r"([\d,]+(?:\.\d{1,2})?)\s*([₪€$£¥])",
        # Amount + code: 100 ILS, 50USD, 30 EUR
        r"([\d,]+(?:\.\d{1,2})?)\s*([a-zA-Z]{3})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            # Determine which group is amount vs currency
            if groups[0] in "₪€$£¥" or groups[0].lower() in CURRENCY_MAP:
                currency_str, amount_str = groups[0], groups[1]
            elif groups[1] in "₪€$£¥" or groups[1].lower() in CURRENCY_MAP:
                amount_str, currency_str = groups[0], groups[1]
            else:
                # Check if second group looks like currency code
                if re.match(r"^[a-zA-Z]{3}$", groups[1]) and groups[1].upper() in (
                    "ILS",
                    "EUR",
                    "USD",
                    "GBP",
                    "JPY",
                    "NIS",
                ):
                    amount_str, currency_str = groups[0], groups[1]
                else:
                    continue

            try:
                amount = Decimal(amount_str.replace(",", ""))
                currency = normalize_currency(currency_str)
                return amount, currency
            except InvalidOperation:
                continue

    return None


def parse_names_list(text: str) -> list[str]:
    """Parse a comma/and separated list of names."""
    # Split on comma, &, and, or whitespace when no other delimiter
    text = re.sub(r"\s+and\s+", ",", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*&\s*", ",", text)
    text = re.sub(r"\s*,\s*", ",", text)

    names = [n.strip() for n in text.split(",") if n.strip()]
    return [n.capitalize() for n in names]


def parse_custom_splits(text: str) -> dict[str, Decimal] | None:
    """
    Parse custom split specifications.

    Format: "Dan:50, Sara:30, Avi:20" or "Dan 50, Sara 30"
    """
    # Pattern: name:amount or name amount, separated by comma
    pattern = r"([a-zA-Z]+)\s*[:\s]\s*([\d.]+)"
    matches = re.findall(pattern, text)

    if not matches:
        return None

    splits = {}
    for name, amount_str in matches:
        try:
            splits[name.capitalize()] = Decimal(amount_str)
        except InvalidOperation:
            return None

    return splits if splits else None


def parse_command(text: str) -> ParsedCommand | ParseError:
    """
    Parse a natural language command into a structured ParsedCommand.

    Supports:
        kai add <desc> <amount><currency> paid by <person> split equally [between <people>]
        kai add <desc> <amount><currency> paid by <person> only <people>
        kai add <desc> <amount><currency> paid by <person> custom <person>:<amount>[, ...]
        kai settle <person> paid <person> <amount><currency>
        kai balances [in <currency>]
        kai summary
        kai undo
        kai trip <name> [base <currency>]
        kai who
        kai help
    """
    original_text = text
    text = text.strip()

    # Remove "kai" prefix if present (case insensitive)
    text = re.sub(r"^kai\s+", "", text, flags=re.IGNORECASE)

    # === HELP ===
    if re.match(r"^help\b", text, re.IGNORECASE):
        return ParsedCommand(command_type=CommandType.HELP, raw_text=original_text)

    # === WHO ===
    if re.match(r"^who\b", text, re.IGNORECASE):
        return ParsedCommand(command_type=CommandType.WHO, raw_text=original_text)

    # === SUMMARY ===
    if re.match(r"^summary\b", text, re.IGNORECASE):
        return ParsedCommand(command_type=CommandType.SUMMARY, raw_text=original_text)

    # === UNDO ===
    if re.match(r"^undo\b", text, re.IGNORECASE):
        return ParsedCommand(command_type=CommandType.UNDO, raw_text=original_text)

    # === BALANCES ===
    balance_match = re.match(
        r"^(?:balances?|status|debts?)\s*(?:in\s+([a-zA-Z₪€$£¥]{1,3}))?\s*$",
        text,
        re.IGNORECASE,
    )
    if balance_match:
        display_ccy = balance_match.group(1)
        if display_ccy:
            display_ccy = normalize_currency(display_ccy)
        return ParsedCommand(
            command_type=CommandType.BALANCES,
            raw_text=original_text,
            display_currency=display_ccy,
        )

    # === TRIP ===
    trip_match = re.match(
        r"^trip\s+([a-zA-Z0-9_\- ]+?)(?:\s+base\s+([a-zA-Z₪€$£¥]{1,3}))?\s*$",
        text,
        re.IGNORECASE,
    )
    if trip_match:
        trip_name = trip_match.group(1).strip()
        base_ccy = trip_match.group(2)
        if base_ccy:
            base_ccy = normalize_currency(base_ccy)
        return ParsedCommand(
            command_type=CommandType.TRIP,
            raw_text=original_text,
            trip_name=trip_name,
            trip_base_currency=base_ccy,
        )

    # === SETTLE ===
    # Pattern: settle <person> paid <person> <amount> or <person> paid <person> <amount>
    settle_match = re.match(
        r"^(?:settle\s+)?([a-zA-Z]+)\s+paid\s+([a-zA-Z]+)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if settle_match:
        from_person = settle_match.group(1).capitalize()
        to_person = settle_match.group(2).capitalize()
        amount_text = settle_match.group(3)

        parsed_amount = parse_amount_currency(amount_text)
        if parsed_amount:
            amount, currency = parsed_amount
            return ParsedCommand(
                command_type=CommandType.SETTLE,
                raw_text=original_text,
                from_person=from_person,
                to_person=to_person,
                amount=amount,
                currency=currency,
            )

    # === ADD EXPENSE ===
    # Try multiple patterns for flexibility

    # Pattern 1: add <desc> <amount> paid by <person> [split options]
    add_match = re.match(
        r"^add\s+(.+?)\s+([\d₪€$£¥,.\s]+[a-zA-Z₪€$£¥]*)\s+paid\s+(?:by\s+)?([a-zA-Z]+)\s*(.*)$",
        text,
        re.IGNORECASE,
    )

    if add_match:
        description = add_match.group(1).strip()
        amount_text = add_match.group(2).strip()
        paid_by = add_match.group(3).capitalize()
        split_text = add_match.group(4).strip()

        parsed_amount = parse_amount_currency(amount_text)
        if not parsed_amount:
            return ParseError(
                raw_text=original_text,
                message=f"Could not parse amount from '{amount_text}'",
                suggestions=["Use format: ₪100, $50, 30EUR"],
                error_type="invalid_amount",
            )

        amount, currency = parsed_amount

        # Parse split options
        split_type = SplitType.EQUAL
        split_among: list[str] | None = None
        custom_splits: dict[str, Decimal] | None = None

        if split_text:
            # Check for "only <people>"
            only_match = re.match(r"^only\s+(.+)$", split_text, re.IGNORECASE)
            if only_match:
                split_type = SplitType.ONLY
                split_among = parse_names_list(only_match.group(1))

            # Check for "custom <person>:<amount>, ..."
            elif re.match(r"^custom\s+", split_text, re.IGNORECASE):
                custom_text = re.sub(r"^custom\s+", "", split_text, flags=re.IGNORECASE)
                custom_splits = parse_custom_splits(custom_text)
                if custom_splits:
                    split_type = SplitType.CUSTOM
                else:
                    return ParseError(
                        raw_text=original_text,
                        message=f"Could not parse custom splits from '{custom_text}'",
                        suggestions=["Use format: custom Dan:50, Sara:30, Avi:20"],
                        error_type="invalid_custom_split",
                    )

            # Check for "split equally between <people>"
            elif re.match(
                r"^(?:split\s+)?equal(?:ly)?\s+(?:between\s+)?(.+)$", split_text, re.IGNORECASE
            ):
                between_match = re.match(
                    r"^(?:split\s+)?equal(?:ly)?\s+(?:between\s+)?(.+)$",
                    split_text,
                    re.IGNORECASE,
                )
                if between_match:
                    split_among = parse_names_list(between_match.group(1))

            # Check for just "between <people>" or bare names
            elif re.match(r"^(?:between\s+)?([a-zA-Z,&\s]+)$", split_text, re.IGNORECASE):
                names_match = re.match(r"^(?:between\s+)?(.+)$", split_text, re.IGNORECASE)
                if names_match:
                    split_among = parse_names_list(names_match.group(1))

        return ParsedCommand(
            command_type=CommandType.ADD_EXPENSE,
            raw_text=original_text,
            description=description,
            amount=amount,
            currency=currency,
            paid_by=paid_by,
            split_type=split_type,
            split_among=split_among,
            custom_splits=custom_splits,
        )

    # No pattern matched - try to determine specific error type
    text_lower = text.lower()
    error_type = "unknown_command"

    # Check for partial add command patterns
    if text_lower.startswith("add"):
        if "paid" not in text_lower:
            error_type = "missing_paid_by"
        elif not any(c in text for c in "₪€$£¥") and not re.search(r"\d", text):
            error_type = "missing_amount"
        else:
            error_type = "missing_amount"  # Default for malformed add

    return ParseError(
        raw_text=original_text,
        message="Could not understand command",
        suggestions=[
            "kai add <desc> <amount> paid by <person>",
            "kai settle <person> paid <person> <amount>",
            "kai balances",
            "kai help",
        ],
        error_type=error_type,
    )
