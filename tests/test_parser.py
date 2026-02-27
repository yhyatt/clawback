"""Tests for Clawback parser - zero-LLM command parsing."""

from decimal import Decimal

from clawback.models import CommandType, ParseError, SplitType
from clawback.parser import (
    get_currency_symbol,
    normalize_currency,
    parse_amount_currency,
    parse_command,
    parse_custom_splits,
    parse_names_list,
)


class TestNormalizeCurrency:
    """Tests for currency normalization."""

    def test_shekel_symbol(self) -> None:
        """Test ₪ → ILS."""
        assert normalize_currency("₪") == "ILS"

    def test_shekel_codes(self) -> None:
        """Test various shekel codes."""
        assert normalize_currency("nis") == "ILS"
        assert normalize_currency("NIS") == "ILS"
        assert normalize_currency("ils") == "ILS"
        assert normalize_currency("ILS") == "ILS"
        assert normalize_currency("shekel") == "ILS"
        assert normalize_currency("shekels") == "ILS"

    def test_euro(self) -> None:
        """Test € and EUR."""
        assert normalize_currency("€") == "EUR"
        assert normalize_currency("eur") == "EUR"
        assert normalize_currency("euro") == "EUR"

    def test_dollar(self) -> None:
        """Test $ and USD."""
        assert normalize_currency("$") == "USD"
        assert normalize_currency("usd") == "USD"
        assert normalize_currency("dollar") == "USD"

    def test_pound(self) -> None:
        """Test £ and GBP."""
        assert normalize_currency("£") == "GBP"
        assert normalize_currency("gbp") == "GBP"

    def test_yen(self) -> None:
        """Test ¥ and JPY."""
        assert normalize_currency("¥") == "JPY"
        assert normalize_currency("jpy") == "JPY"

    def test_unknown_currency_uppercase(self) -> None:
        """Test that unknown currencies are uppercased."""
        assert normalize_currency("chf") == "CHF"


class TestGetCurrencySymbol:
    """Tests for getting currency symbols."""

    def test_ils_symbol(self) -> None:
        """Test ILS → ₪."""
        assert get_currency_symbol("ILS") == "₪"

    def test_eur_symbol(self) -> None:
        """Test EUR → €."""
        assert get_currency_symbol("EUR") == "€"

    def test_usd_symbol(self) -> None:
        """Test USD → $."""
        assert get_currency_symbol("USD") == "$"

    def test_unknown_returns_code(self) -> None:
        """Test unknown currency returns the code."""
        assert get_currency_symbol("CHF") == "CHF"


class TestParseAmountCurrency:
    """Tests for amount/currency parsing."""

    def test_shekel_before_amount(self) -> None:
        """Test ₪100."""
        result = parse_amount_currency("₪100")
        assert result == (Decimal("100"), "ILS")

    def test_shekel_after_amount(self) -> None:
        """Test 100₪."""
        result = parse_amount_currency("100₪")
        assert result == (Decimal("100"), "ILS")

    def test_dollar_before_amount(self) -> None:
        """Test $50.50."""
        result = parse_amount_currency("$50.50")
        assert result == (Decimal("50.50"), "USD")

    def test_euro_before_amount(self) -> None:
        """Test €30."""
        result = parse_amount_currency("€30")
        assert result == (Decimal("30"), "EUR")

    def test_amount_with_code(self) -> None:
        """Test 100 ILS."""
        result = parse_amount_currency("100 ILS")
        assert result == (Decimal("100"), "ILS")

    def test_amount_with_code_no_space(self) -> None:
        """Test 100ILS."""
        result = parse_amount_currency("100ILS")
        assert result == (Decimal("100"), "ILS")

    def test_amount_with_code_lowercase(self) -> None:
        """Test 100 eur."""
        result = parse_amount_currency("100 eur")
        assert result == (Decimal("100"), "EUR")

    def test_amount_with_comma(self) -> None:
        """Test 1,000₪."""
        result = parse_amount_currency("1,000₪")
        assert result == (Decimal("1000"), "ILS")

    def test_decimal_amount(self) -> None:
        """Test ₪99.99."""
        result = parse_amount_currency("₪99.99")
        assert result == (Decimal("99.99"), "ILS")

    def test_invalid_returns_none(self) -> None:
        """Test that invalid input returns None."""
        assert parse_amount_currency("abc") is None
        assert parse_amount_currency("100") is None  # No currency


class TestParseNamesList:
    """Tests for parsing name lists."""

    def test_comma_separated(self) -> None:
        """Test Dan, Sara, Avi."""
        result = parse_names_list("Dan, Sara, Avi")
        assert result == ["Dan", "Sara", "Avi"]

    def test_and_separated(self) -> None:
        """Test Dan and Sara."""
        result = parse_names_list("Dan and Sara")
        assert result == ["Dan", "Sara"]

    def test_ampersand_separated(self) -> None:
        """Test Dan & Sara."""
        result = parse_names_list("Dan & Sara")
        assert result == ["Dan", "Sara"]

    def test_mixed_separators(self) -> None:
        """Test Dan, Sara & Avi and Ben."""
        result = parse_names_list("Dan, Sara & Avi and Ben")
        assert result == ["Dan", "Sara", "Avi", "Ben"]

    def test_lowercase_capitalized(self) -> None:
        """Test names are capitalized."""
        result = parse_names_list("dan, sara")
        assert result == ["Dan", "Sara"]


class TestParseCustomSplits:
    """Tests for custom split parsing."""

    def test_colon_format(self) -> None:
        """Test Dan:50, Sara:30."""
        result = parse_custom_splits("Dan:50, Sara:30")
        assert result == {"Dan": Decimal("50"), "Sara": Decimal("30")}

    def test_space_format(self) -> None:
        """Test Dan 50, Sara 30."""
        result = parse_custom_splits("Dan 50, Sara 30")
        assert result == {"Dan": Decimal("50"), "Sara": Decimal("30")}

    def test_decimal_amounts(self) -> None:
        """Test Dan:50.50."""
        result = parse_custom_splits("Dan:50.50")
        assert result == {"Dan": Decimal("50.50")}

    def test_invalid_returns_none(self) -> None:
        """Test that invalid input returns None."""
        assert parse_custom_splits("gibberish") is None


class TestParseCommand:
    """Tests for full command parsing."""

    # === HELP ===
    def test_parse_help(self) -> None:
        """Test parsing help command."""
        result = parse_command("kai help")
        assert result.command_type == CommandType.HELP

    def test_parse_help_no_prefix(self) -> None:
        """Test help without kai prefix."""
        result = parse_command("help")
        assert result.command_type == CommandType.HELP

    # === WHO ===
    def test_parse_who(self) -> None:
        """Test parsing who command."""
        result = parse_command("kai who")
        assert result.command_type == CommandType.WHO

    # === SUMMARY ===
    def test_parse_summary(self) -> None:
        """Test parsing summary command."""
        result = parse_command("kai summary")
        assert result.command_type == CommandType.SUMMARY

    # === UNDO ===
    def test_parse_undo(self) -> None:
        """Test parsing undo command."""
        result = parse_command("kai undo")
        assert result.command_type == CommandType.UNDO

    # === BALANCES ===
    def test_parse_balances(self) -> None:
        """Test parsing balances command."""
        result = parse_command("kai balances")
        assert result.command_type == CommandType.BALANCES
        assert result.display_currency is None

    def test_parse_balances_in_currency(self) -> None:
        """Test parsing balances in EUR."""
        result = parse_command("kai balances in EUR")
        assert result.command_type == CommandType.BALANCES
        assert result.display_currency == "EUR"

    def test_parse_balance_singular(self) -> None:
        """Test balance (singular) works."""
        result = parse_command("balance")
        assert result.command_type == CommandType.BALANCES

    def test_parse_status(self) -> None:
        """Test status as alias for balances."""
        result = parse_command("status")
        assert result.command_type == CommandType.BALANCES

    def test_parse_debts(self) -> None:
        """Test debts as alias for balances."""
        result = parse_command("debts")
        assert result.command_type == CommandType.BALANCES

    # === TRIP ===
    def test_parse_trip_create(self) -> None:
        """Test parsing trip creation."""
        result = parse_command("kai trip Beach Vacation")
        assert result.command_type == CommandType.TRIP
        assert result.trip_name == "Beach Vacation"
        assert result.trip_base_currency is None

    def test_parse_trip_with_base_currency(self) -> None:
        """Test parsing trip with base currency."""
        result = parse_command("kai trip Euro Trip base EUR")
        assert result.command_type == CommandType.TRIP
        assert result.trip_name == "Euro Trip"
        assert result.trip_base_currency == "EUR"

    # === SETTLE ===
    def test_parse_settle(self) -> None:
        """Test parsing settle command."""
        result = parse_command("kai settle Dan paid Sara ₪100")
        assert result.command_type == CommandType.SETTLE
        assert result.from_person == "Dan"
        assert result.to_person == "Sara"
        assert result.amount == Decimal("100")
        assert result.currency == "ILS"

    def test_parse_settle_without_prefix(self) -> None:
        """Test settle without kai prefix."""
        result = parse_command("Dan paid Sara $50")
        assert result.command_type == CommandType.SETTLE
        assert result.from_person == "Dan"
        assert result.to_person == "Sara"
        assert result.amount == Decimal("50")
        assert result.currency == "USD"

    # === ADD EXPENSE ===
    def test_parse_add_basic(self) -> None:
        """Test basic add expense."""
        result = parse_command("kai add Dinner ₪340 paid by Yonatan")
        assert result.command_type == CommandType.ADD_EXPENSE
        assert result.description == "Dinner"
        assert result.amount == Decimal("340")
        assert result.currency == "ILS"
        assert result.paid_by == "Yonatan"
        assert result.split_type == SplitType.EQUAL

    def test_parse_add_with_only(self) -> None:
        """Test add expense with only split."""
        result = parse_command("kai add dinner ₪340 paid by Dan only Dan & Sara")
        assert result.command_type == CommandType.ADD_EXPENSE
        assert result.split_type == SplitType.ONLY
        assert result.split_among == ["Dan", "Sara"]

    def test_parse_add_with_custom(self) -> None:
        """Test add expense with custom split."""
        result = parse_command("kai add wine €60 paid by Avi custom Dan:30, Sara:20, Avi:10")
        assert result.command_type == CommandType.ADD_EXPENSE
        assert result.split_type == SplitType.CUSTOM
        assert result.custom_splits["Dan"] == Decimal("30")
        assert result.custom_splits["Sara"] == Decimal("20")
        assert result.custom_splits["Avi"] == Decimal("10")

    def test_parse_add_with_between(self) -> None:
        """Test add expense with split between."""
        result = parse_command("kai add Gas ₪150 paid by Sara between Dan, Sara, Avi")
        assert result.command_type == CommandType.ADD_EXPENSE
        assert result.split_among == ["Dan", "Sara", "Avi"]

    def test_parse_add_with_split_equally(self) -> None:
        """Test add expense with split equally between."""
        result = parse_command("kai add Lunch ₪200 paid by Dan split equally between Dan and Sara")
        assert result.command_type == CommandType.ADD_EXPENSE
        assert result.split_type == SplitType.EQUAL
        assert result.split_among == ["Dan", "Sara"]

    def test_parse_add_euro(self) -> None:
        """Test add expense with euro."""
        result = parse_command("add coffee €5 paid by Dan")
        assert result.amount == Decimal("5")
        assert result.currency == "EUR"

    def test_parse_add_dollar(self) -> None:
        """Test add expense with dollar."""
        result = parse_command("add taxi $20 paid by Sara")
        assert result.amount == Decimal("20")
        assert result.currency == "USD"

    # === PARSE ERRORS ===
    def test_parse_gibberish(self) -> None:
        """Test that gibberish returns ParseError."""
        result = parse_command("asdfghjkl qwerty")
        assert isinstance(result, ParseError)
        assert "suggestions" in result.model_dump()

    def test_parse_incomplete_add(self) -> None:
        """Test incomplete add command."""
        result = parse_command("kai add dinner")
        assert isinstance(result, ParseError)

    # === CASE INSENSITIVITY ===
    def test_case_insensitive_commands(self) -> None:
        """Test commands are case insensitive."""
        assert parse_command("KAI HELP").command_type == CommandType.HELP
        assert parse_command("Kai Summary").command_type == CommandType.SUMMARY

    def test_case_insensitive_paid_by(self) -> None:
        """Test paid by is case insensitive."""
        result = parse_command("add dinner ₪100 PAID BY dan")
        assert result.command_type == CommandType.ADD_EXPENSE
        assert result.paid_by == "Dan"  # Capitalized

    # === WHITESPACE TOLERANCE ===
    def test_extra_whitespace(self) -> None:
        """Test handling extra whitespace."""
        result = parse_command("  kai   add   dinner   ₪100   paid by   Dan  ")
        assert result.command_type == CommandType.ADD_EXPENSE
        assert result.description == "dinner"
